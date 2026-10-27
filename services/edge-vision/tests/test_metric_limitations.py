"""Interpretation limitations must be visible for biased datasets."""
from sentinel_edge.evaluation import ClipOutcome, summarize_clips


def outcome(is_fall: bool, predicted: bool):
    return ClipOutcome(
        clip_id="synthetic-pos" if is_fall else "synthetic-neg",
        expected_fall=is_fall, predicted_fall=predicted,
        candidate_count=int(predicted), pre_onset_candidate_count=0,
        first_candidate_ms=None, first_matching_candidate_ms=None,
        annotated_onset_ms=None, latency_ms=None, analyzed_frames=3,
        observed_pose_frames=3, first_frame_ms=0, last_frame_ms=200,
    )


def test_positive_only_metrics_explicitly_warn_about_precision():
    result = summarize_clips([outcome(True, True)], source="synthetic",
                             permission_basis_declared=True)
    assert result["ground_truth_balance"] == {"fall_clips": 1, "no_fall_clips": 0}
    limits = " ".join(result["metric_interpretation_limits"])
    assert "Positive-only" in limits
    assert "false-positive" in limits
    assert "onset_ms" in limits


def test_negative_only_metrics_explicitly_warn_about_recall():
    result = summarize_clips([outcome(False, False)], source="synthetic",
                             permission_basis_declared=True)
    assert result["ground_truth_balance"] == {"fall_clips": 0, "no_fall_clips": 1}
    assert "Negative-only" in " ".join(result["metric_interpretation_limits"])
