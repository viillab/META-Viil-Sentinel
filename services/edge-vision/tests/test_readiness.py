"""Readiness guardrails cannot mistake all-positive data for high accuracy."""
import pytest

from sentinel_edge.readiness import benchmark_readiness


def report(tp=1, fn=7, fp=0, tn=0):
    return {
        "ground_truth_balance": {"fall_clips": tp + fn, "no_fall_clips": fp + tn},
        "metrics": {
            "true_positive": tp, "false_negative": fn,
            "false_positive": fp, "true_negative": tn,
        },
        "clips": [
            {"expected_fall": True, "annotated_onset_ms": None}
            for _ in range(tp + fn)
        ] + [
            {"expected_fall": False, "annotated_onset_ms": None}
            for _ in range(fp + tn)
        ],
    }


def test_ikar_positive_only_raises_evidence_gaps():
    result = benchmark_readiness(report())
    assert result["reliable_fall_alerting_ready"] is False
    assert result["automated_emergency_action_authorized"] is False
    assert result["pose_inference_functional"] is None  # Not implied by scores.
    assert "NO_NORMAL_ACTIVITY_NEGATIVES" in result["evidence_gaps"]
    assert "MISSED_FALLS_OBSERVED" in result["evidence_gaps"]
    assert "PARTICIPANT_DISJOINT_HOLDOUT_NOT_VERIFIED" in result["evidence_gaps"]


def test_even_good_scores_cannot_self_authorize_real_alerts():
    result = benchmark_readiness(report(tp=40, fn=0, tn=40))
    assert result["reliable_fall_alerting_ready"] is False
    assert result["automated_emergency_action_authorized"] is False
    assert "PARTICIPANT_DISJOINT_HOLDOUT_NOT_VERIFIED" in result["evidence_gaps"]


def test_negative_only_cannot_prove_fall_recall():
    result = benchmark_readiness(report(tp=0, fn=0, tn=5))
    assert "NO_FALL_POSITIVES" in result["evidence_gaps"]


@pytest.mark.parametrize("bad", [
    {"ground_truth_balance": {"fall_clips": True, "no_fall_clips": 0}},
    {"ground_truth_balance": {"fall_clips": -1, "no_fall_clips": 0}},
    {"ground_truth_balance": {"fall_clips": 9, "no_fall_clips": 0}},
])
def test_fail_closed_on_inconsistent_counts(bad):
    r = report()
    r.update(bad)
    with pytest.raises(ValueError):
        benchmark_readiness(r)


def test_bad_confusion_data_refused():
    r = report()
    r["metrics"]["true_positive"] = True
    with pytest.raises(ValueError, match="confusion"):
        benchmark_readiness(r)
