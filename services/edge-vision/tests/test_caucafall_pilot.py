"""End-to-end *fictional* publisher-labeled motion training integration."""
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.caucafall_curator import curate, publisher_label_pilot
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
