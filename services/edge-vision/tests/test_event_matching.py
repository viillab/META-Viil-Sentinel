"""Synthetic event matching tests: no real fall accuracy is inferred."""
import json

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.evaluation import evaluate_manifest
from sentinel_edge.pose_traces import frame_to_trace_record


def sample(t: int, *, prone: bool = False) -> PoseFrame:
    sx, sy, hx, hy = (
        (0.23, 0.78, 0.57, 0.78) if prone
        else (0.5, 0.25, 0.5, 0.53)
    )
    return PoseFrame(
        timestamp_ms=t, source_id="synthetic",
        landmarks={
            11: Landmark(sx - 0.045, sy, 0.98),
            12: Landmark(sx + 0.045, sy, 0.98),
            23: Landmark(hx - 0.05, hy, 0.98),
            24: Landmark(hx + 0.05, hy, 0.98),
        },
    )


def create_manifest(tmp_path, frames: list[PoseFrame], *, onset: int):
    trace = tmp_path / "synthetic.pose.jsonl"
    trace.write_text(
        "".join(frame_to_trace_record(frame) + "\n" for frame in frames),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "version": 1,
            "permission_basis": "Entirely synthetic geometric landmarks",
            "clips": [
                {
                    "id": "synthetic_positive",
                    "trace": trace.name,
                    "expected_fall": True,
                    "onset_ms": onset,
                }
            ],
        }),
        encoding="utf-8",
    )
    return manifest


def test_pre_onset_candidate_is_not_credit_for_later_ground_truth(tmp_path):
    frames = [sample(t) for t in (0, 100, 200)]
    frames += [sample(t, prone=True) for t in (300, 500, 700, 850, 1000, 1200, 1400)]
    report = evaluate_manifest(create_manifest(tmp_path, frames, onset=1100))
    assert report["metrics"]["true_positive"] == 0
    assert report["metrics"]["false_negative"] == 1
    assert report["false_candidates_before_onset"] == 1
    assert report["false_candidate_total_with_known_labels"] == 1
    entry = report["clips"][0]
    assert entry["predicted_fall"] is False
    assert entry["candidate_count"] == 1
    assert entry["pre_onset_candidate_count"] == 1
    assert entry["first_candidate_ms"] == 850
    assert entry["first_matching_candidate_ms"] is None
    assert entry["latency_ms"] is None
    assert entry["observed_pose_frames"] == len(frames)


def test_outside_recording_onset_fails_instead_of_fabricating_latency(tmp_path):
    frames = [sample(t) for t in (100, 200, 300)]
    with pytest.raises(ValueError, match="outside the observed trace"):
        evaluate_manifest(create_manifest(tmp_path, frames, onset=0))
    with pytest.raises(ValueError, match="outside the observed trace"):
        evaluate_manifest(create_manifest(tmp_path, frames, onset=900))


def test_occlusion_invalidates_old_upright_baseline():
    detector = TemporalFallDetector()
    for t in (0, 100, 200):
        assert detector.process(sample(t)) is None

    # Losing tracking entirely must clear the previously upright baseline.
    assert detector.process(PoseFrame(timestamp_ms=300, landmarks={})) is None
    for t in (400, 600, 800, 1000):
        assert detector.process(sample(t, prone=True)) is None


def test_reestablished_upright_context_can_detect_later_sequence():
    detector = TemporalFallDetector()
    for t in (0, 100):
        detector.process(sample(t))
    detector.process(PoseFrame(timestamp_ms=200, landmarks={}))
    assert detector.process(sample(300, prone=True)) is None
    for t in (400, 500):
        detector.process(sample(t))
    events = [
        event for t in (600, 800, 1000, 1150)
        if (event := detector.process(sample(t, prone=True))) is not None
    ]
    assert len(events) == 1
