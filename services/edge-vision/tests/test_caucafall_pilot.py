"""End-to-end *fictional* publisher-labeled motion training integration."""
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.caucafall_curator import (
    _wilson_95, curate, publisher_label_pilot,
)
from test_caucafall_curator import fake_root, mock_video_info


def fake_pose_collector(video: Path, *, clip_id, model, max_frames,
                        frame_consumer, event_consumer):
    assert video.is_file() and model.is_file() and max_frames <= 6000
    positive = "Fall" in video.name
    for i in range(60):
        frac = i / 59
        signal = .35 if positive and frac > .4 else 0.0
        hips = .53 + signal
        shoulders = .25 + .1 * signal
        frame_consumer(PoseFrame(
            timestamp_ms=i*50, source_id=clip_id, landmarks={
                11: Landmark(.45, shoulders), 12: Landmark(.55, shoulders),
                23: Landmark(.45, hips), 24: Landmark(.55, hips),
            },
        ))
    return [], {"frames_processed": 60, "invalid_pose_frames": 0, "candidate_events": 0}


def test_publisher_only_in_memory_training_can_execute_without_manual_review_claim(tmp_path):
    root = fake_root(tmp_path)
    groups, proposals, _ = curate(root, metadata_reader=mock_video_info)
    model = tmp_path / "local.task"
    model.write_bytes(b"FAKE MODEL FOR NUMERIC TEST")
    report = publisher_label_pilot(root, model, groups, proposals,
                                    collector=fake_pose_collector)
    assert report["publisher_labels_only"] is True
    assert report["independent_human_label_review"] is False
    assert report["prototype_research_only"] is True
    assert report["production_alerts_enabled"] is False
    assert report["reliability_proven"] is False
    assert report["raw_features_saved"] is False
    assert report["heldout_test"]["true_positive"] + report["heldout_test"]["false_negative"] == 4
    assert report["heldout_test"]["true_negative"] + report["heldout_test"]["false_positive"] == 4
    assert not list(tmp_path.glob("*.pose.jsonl"))
    assert not list(tmp_path.glob("*windows.json"))
    assert report["pose_quality_filter"]["coverage_by_split_and_label"]["test"] == {
        "fall": {"selected": 4, "eligible": 4, "abstained": 0, "coverage": 1.0},
        "adl": {"selected": 4, "eligible": 4, "abstained": 0, "coverage": 1.0},
    }
    assert report["heldout_uncertainty"]["eligible_only"] is True
    assert report["heldout_uncertainty"]["fall_recall_wilson_95"]["n"] == 4
    assert report["heldout_uncertainty"]["adl_specificity_wilson_95"]["n"] == 4
    assert report["heldout_uncertainty"]["unscored_heldout_clips"] == 0


def test_media_modified_after_curation_blocks_pose_processing(tmp_path):
    root = fake_root(tmp_path)
    groups, proposals, _ = curate(root, metadata_reader=mock_video_info)
    model = tmp_path / "local.task"
    model.write_bytes(b"FAKE")
    source = root / proposals["segments"][0]["video"]
    source.write_bytes(b"tAMPERED")
    used = []
    def forbidden(*args, **kwargs):
        used.append(True)
        raise AssertionError("Must not reach model inference")
    with pytest.raises(ValueError, match="Media changed"):
        publisher_label_pilot(root, model, groups, proposals, collector=forbidden)
    assert not used


def test_wilson_interval_reflects_tiny_heldout_sample():
    assert _wilson_95(2, 4) == {
        "hits": 2, "n": 4, "lower": 0.15, "upper": 0.85,
    }
    perfect_two = _wilson_95(2, 2)
    assert perfect_two["upper"] == 1.0
    assert perfect_two["lower"] < 0.35  # A perfect 2/2 proves very little.
    assert _wilson_95(0, 0)["lower"] is None


def test_publisher_pilot_discloses_missing_pose_test_adl_as_abstention(tmp_path):
    root = fake_root(tmp_path)
    groups, proposals, _ = curate(root, metadata_reader=mock_video_info)
    model = tmp_path / "local.task"
    model.write_bytes(b"FAKE NUMERIC TEST MODEL")

    def one_unreadable_adl(video, *, clip_id, model, max_frames,
                           frame_consumer, event_consumer):
        if "WalkS9_" not in video.name:
            return fake_pose_collector(
                video, clip_id=clip_id, model=model, max_frames=max_frames,
                frame_consumer=frame_consumer, event_consumer=event_consumer,
            )
        for i in range(60):
            frame_consumer(PoseFrame(
                timestamp_ms=i * 50, source_id=clip_id, landmarks={},
            ))
        return [], {"frames_processed": 60, "invalid_pose_frames": 60,
                    "candidate_events": 0}

    report = publisher_label_pilot(root, model, groups, proposals,
                                   collector=one_unreadable_adl)
    coverage = report["pose_quality_filter"]["coverage_by_split_and_label"]["test"]
    assert coverage["adl"] == {
        "selected": 4, "eligible": 3, "abstained": 1, "coverage": 0.75,
    }
    assert report["heldout_uncertainty"]["unscored_heldout_clips"] == 1
    assert report["heldout_uncertainty"]["adl_specificity_wilson_95"]["n"] == 3
    assert report["heldout_uncertainty"]["selected_heldout_clips"] == 8
    assert report["heldout_uncertainty"]["scored_heldout_clips"] == 7
