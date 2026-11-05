"""All cases use fictional MediaPipe-like objects, never actual pose data."""
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.assist_external import (
    _evaluate_one, aggregate_pose_rejection_reasons,
)
from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.pose_adapter import extract_torso_landmarks
from sentinel_edge.pose_rejection_diagnostics import REASONS, pose_adapter_reason


def human_like(**overrides):
    item = dict(x=.5, y=.3, visibility=.99, presence=.99)
    item.update(overrides)
    return NS(pose_landmarks=[[
        NS(**item) for _ in range(33)
    ]])


@pytest.mark.parametrize(("kind", "result"), [
    ("accepted", human_like()),
    ("no_person", NS(pose_landmarks=[])),
    ("multiple_people", NS(pose_landmarks=[[NS()] * 33, [NS()] * 33])),
    ("malformed_result", NS(pose_landmarks=None)),
    ("malformed_torso", NS(pose_landmarks=[[NS(x=.5)] * 5])),
    ("missing_visibility", human_like(visibility=None)),
    ("invalid_numeric", human_like(x=float("nan"))),
    ("invalid_numeric", human_like(presence=float("inf"))),
    ("out_of_frame", human_like(y=1.10)),
    ("low_visibility", human_like(visibility=.33)),
    ("low_presence", human_like(presence=.21)),
])
def test_reason_matches_unmodified_production_adapter(kind, result):
    reason = pose_adapter_reason(result)
    assert reason == kind
    assert (bool(extract_torso_landmarks(result)) == (reason == "accepted"))
    assert kind in REASONS


@pytest.mark.parametrize("bad", [-.1, 1.2, float("nan")])
def test_reason_extractor_rejects_invalid_min_visibility(bad):
    with pytest.raises(ValueError, match="min_confidence"):
        pose_adapter_reason(human_like(), min_confidence=bad)


def _fake_collector(path, *, clip_id, model, max_frames, frame_consumer,
                    event_consumer, pose_reason_consumer=None):
    assert path.name == "fiction.mp4"
    assert model.name == "fiction.task"
    assert clip_id == "fictional-case"
    assert max_frames == 6000
    accepted = 0
    for i in range(31):
        if i % 2 == 0:
            accepted += 1
            landmarks = {
                11: Landmark(.45, .25, 1), 12: Landmark(.55, .25, 1),
                23: Landmark(.45, .55, 1), 24: Landmark(.55, .55, 1),
            }
            reason = "accepted"
        else:
            landmarks = {}
            reason = "no_person"
        frame_consumer(PoseFrame(timestamp_ms=i * 100, source_id=clip_id,
                                 landmarks=landmarks))
        if pose_reason_consumer:
            pose_reason_consumer(reason)
    return [], {"frames_processed": 31, "invalid_pose_frames": 31 - accepted,
                "candidate_events": 0}


class _StaticClassifier:
    threshold = .53
    def predict_probability(self, x):
        return .21


def test_detailed_counts_match_fictional_frame_stream(tmp_path):
    row = _evaluate_one(
        tmp_path / "fiction.mp4", "fall", "fictional-case", 3000,
        tmp_path / "fiction.task", _StaticClassifier(),
        collector=_fake_collector, diagnostics=True, detailed_reasons=True,
    )
    counts = row["pose_rejection_reasons"]
    assert counts["accepted"] == 16
    assert counts["no_person"] == 15
    assert set(counts) == set(REASONS)
    report = aggregate_pose_rejection_reasons([row], "fall")
    assert report["accepted_frames"] == 16
    assert report["rejected_frames"] == 15
    assert report["decoded_frames"] == 31
    assert report["raw_pose_recorded"] is False
    assert "landmarks" not in str(report)


def test_rejection_counters_fail_closed_on_wrong_stream_totals(tmp_path):
    def corrupted(*args, **kwargs):
        return _fake_collector(*args, **kwargs)
    # An unexpected extra callback should not be quietly ignored.
    def extra(*args, pose_reason_consumer=None, **kwargs):
        out = corrupted(*args, pose_reason_consumer=pose_reason_consumer, **kwargs)
        pose_reason_consumer("no_person")
        return out
    with pytest.raises(ValueError, match="counters contradict"):
        _evaluate_one(
            tmp_path / "fiction.mp4", "adl", "fictional-case", 3000,
            tmp_path / "fiction.task", _StaticClassifier(), collector=extra,
            diagnostics=True, detailed_reasons=True,
        )


def test_normal_diagnostic_does_not_require_extra_callback(tmp_path):
    result = _evaluate_one(
        tmp_path / "fiction.mp4", "fall", "fictional-case", 3000,
        tmp_path / "fiction.task", _StaticClassifier(),
        collector=_fake_collector, diagnostics=True,
    )
    assert "pose_rejection_reasons" not in result
    assert "failure_diagnostic" in result


def test_rejection_detail_requires_diagnostics(tmp_path):
    with pytest.raises(ValueError, match="require failure diagnostics"):
        _evaluate_one(
            tmp_path / "fiction.mp4", "fall", "fictional-case", 3000,
            tmp_path / "fiction.task", _StaticClassifier(),
            collector=_fake_collector, detailed_reasons=True,
        )
