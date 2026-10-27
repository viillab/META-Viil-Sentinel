"""Conservative evidence gate for NON-CLINICAL fall candidate prototype.

This is not an accuracy calibration and does not authorize deployment.
Never infer that missing no-fall examples constitute zero false alarms.
"""
from collections.abc import Mapping


def benchmark_readiness(report: Mapping) -> dict:
    """Summarize minimum evidence gaps; never automatically authorize alerts.

    The model can *run* even when no reliability evidence exists. Benchmarks
    alone cannot prove real-world safety, participant separation, licensing,
    consent or legal fitness. Those require external verified review.
    """
    counts = report.get("ground_truth_balance", {})
    if not isinstance(counts, dict):
        raise ValueError("ground_truth_balance must be an object")
    positives = counts.get("fall_clips")
    negatives = counts.get("no_fall_clips")
    if (type(positives) is not int or type(negatives) is not int
            or positives < 0 or negatives < 0):
        raise ValueError("fall_clips and no_fall_clips must be non-negative integers")
    metrics = report.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    tp, fn = metrics.get("true_positive"), metrics.get("false_negative")
    fp, tn = metrics.get("false_positive"), metrics.get("true_negative")
    for count in (tp, fn, fp, tn):
        if type(count) is not int or count < 0:
            raise ValueError("confusion counts must be non-negative integers")
    if tp + fn != positives or fp + tn != negatives:
        raise ValueError("confusion counts disagree with ground truth")
    if positives + negatives == 0:
        raise ValueError("at least one labeled clip is required")
    problems = []
    if positives == 0:
        problems.append("NO_FALL_POSITIVES")
    if negatives == 0:
        problems.append("NO_NORMAL_ACTIVITY_NEGATIVES")
    if 0 < positives < 30:
        problems.append("SMALL_POSITIVE_SAMPLE")
    if 0 < negatives < 30:
        problems.append("SMALL_NEGATIVE_SAMPLE")
    if fn:
        problems.append("MISSED_FALLS_OBSERVED")
    if fp:
        problems.append("FALSE_ALERTS_OBSERVED")
    labeled = report.get("clips", [])
    if not isinstance(labeled, list) or len(labeled) != positives + negatives:
        raise ValueError("clip records must match ground-truth count")
    if any(not isinstance(item, dict) for item in labeled):
        raise ValueError("each clip record must be an object")
    if any(
        item.get("expected_fall") is True
        and item.get("annotated_onset_ms") is None
        for item in labeled
    ):
        problems.append("FALL_ONSET_NOT_ANNOTATED")
    problems.extend([
        "PARTICIPANT_DISJOINT_HOLDOUT_NOT_VERIFIED",
        "RELIABILITY_ON_TARGET_DEVICE_NOT_VERIFIED",
        "HUMAN_REVIEW_STILL_REQUIRED",
    ])
    return {
        "stage": "research_prototype",
        "pose_inference_functional": None,
        "fall_candidate_pipeline_tested": True,
        "model_calibrated": False,
        "automated_emergency_action_authorized": False,
        "reliable_fall_alerting_ready": False,
        "readiness_checks_are_advisory": True,
        "evidence_gaps": problems,
        "note": (
            "Video scoring proves only that the local detector ran on the "
            "supplied clips. Pose model loading requires a separate real smoke "
            "test. No automatic readiness approval is possible from this report."
        ),
    }
