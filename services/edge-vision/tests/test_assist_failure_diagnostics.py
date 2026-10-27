"""Synthetic-only fall-miss attribution, no camera/real human landmarks."""
import pytest

from sentinel_edge.assist_external import _evaluate_one, summarize_failure_diagnostics
from sentinel_edge.contracts import Landmark, PoseFrame


class FixedModel:
    threshold = .53

    def predict_probability(self, _features):
        return .31


def fake_collector(video, *, clip_id, model, max_frames, frame_consumer,
                   event_consumer):
    assert video.name == "imaginary.mp4"
    assert clip_id == "invented-fall"
    assert max_frames == 6000
    assert model.name == "imaginary.task"
    for i in range(31):
        pts = {
            11: Landmark(.45, .2, 1), 12: Landmark(.55, .2, 1),
            23: Landmark(.45, .55, 1), 24: Landmark(.55, .55, 1),
        }
        frame_consumer(PoseFrame(timestamp_ms=i * 100, source_id=clip_id,
                                 landmarks=pts))
    return [], {"frames_processed": 31, "invalid_pose_frames": 0,
                "candidate_events": 1}


def test_streamed_forensic_counts_diverge_from_original_heuristic(tmp_path):
    video = tmp_path / "imaginary.mp4"
    result = _evaluate_one(
        video, "fall", "invented-fall", 3000,
        tmp_path / "imaginary.task", FixedModel(),
        collector=fake_collector, diagnostics=True,
    )
    assert result["any_window_fall_candidate"] is False
    diag = result["failure_diagnostic"]
    assert diag["decoded_frames"] == 31
    assert diag["torso_adapter_available_frames"] == 31
    assert diag["motion_geometry_eligible_frames"] == 31
    assert diag["unavailable_at_adapter_frames"] == 0
    assert diag["unavailable_at_geometry_after_adapter"] == 0
    assert diag["eligible_window_sampled_visible_frames"] >= 10
    assert diag["legacy_heuristic_event_count"] == 1
    assert diag["frozen_score_bands"] == {
        "clearly_below": 1, "near_below": 0, "candidate": 0,
    }


def test_diagnostics_disabled_retains_exact_old_clip_contract(tmp_path):
    video = tmp_path / "imaginary.mp4"
    result = _evaluate_one(
        video, "fall", "invented-fall", 3000,
        tmp_path / "imaginary.task", FixedModel(),
        collector=fake_collector,
    )
    assert "failure_diagnostic" not in result
    assert result["fully_pose_covered"] is True
    assert result["any_window_fall_candidate"] is False


def test_aggregate_requires_counter_consistency(tmp_path):
    row = _evaluate_one(
        tmp_path / "imaginary.mp4", "fall", "invented-fall", 3000,
        tmp_path / "imaginary.task", FixedModel(),
        collector=fake_collector, diagnostics=True,
    )
    report = summarize_failure_diagnostics([row], "fall")
    assert report["videos_with_original_heuristic_candidates"] == 1
    assert report["videos_with_frozen_classification_candidates"] == 0
    assert report["original_heuristic_and_classification_not_same_event_contract"]
    assert "landmarks" not in str(report)
    broken = dict(row)
    broken["failure_diagnostic"] = dict(row["failure_diagnostic"])
    broken["failure_diagnostic"]["unavailable_at_adapter_frames"] = 100
    with pytest.raises(ValueError, match="Inconsistent"):
        summarize_failure_diagnostics([broken], "fall")


def test_incomplete_diagnostic_cannot_be_summarized(tmp_path):
    row = _evaluate_one(
        tmp_path / "imaginary.mp4", "adl", "invented-fall", 3000,
        tmp_path / "imaginary.task", FixedModel(),
        collector=fake_collector,
    )
    with pytest.raises(ValueError, match="complete counters"):
        summarize_failure_diagnostics([row], "adl")
    with pytest.raises(ValueError, match="Invalid diagnostic"):
        summarize_failure_diagnostics([row], "unknown")
