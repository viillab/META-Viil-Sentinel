"""Synthetic pose-sequence tests; NOT clinical or benchmark validation."""
import pytest

from sentinel_edge.contracts import (
    LEFT_HIP,
    LEFT_SHOULDER,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    Landmark,
    PoseFeatures,
    PoseFrame,
)
from sentinel_edge.detector import DetectorConfig, TemporalFallDetector


def pose(t, *, hip_y=0.53, shoulder_y=0.25, shoulder_x=0.5, hip_x=0.5,
         visibility=0.98, source="staged-01"):
    return PoseFrame(
        timestamp_ms=t,
        source_id=source,
        landmarks={
            LEFT_SHOULDER: Landmark(shoulder_x - 0.045, shoulder_y, visibility),
            RIGHT_SHOULDER: Landmark(shoulder_x + 0.045, shoulder_y, visibility),
            LEFT_HIP: Landmark(hip_x - 0.05, hip_y, visibility),
            RIGHT_HIP: Landmark(hip_x + 0.05, hip_y, visibility),
        },
    )


def lying_pose(t, *, hip_y=0.78, source="staged-01", visibility=0.98):
    return pose(t, hip_y=hip_y, shoulder_y=0.78,
                shoulder_x=0.23, hip_x=0.57, source=source, visibility=visibility)


def test_detects_sustained_pose_transition():
    d = TemporalFallDetector()
    sequence = [
        pose(0), pose(100), pose(200), pose(300),
        lying_pose(400), lying_pose(550), lying_pose(700), lying_pose(880),
    ]
    events = [event for frame in sequence if (event := d.process(frame)) is not None]
    assert len(events) == 1
    assert events[0].timestamp_ms == 880
    assert events[0].source_id == "staged-01"
    assert events[0].confidence < 1
    assert not events[0].simulated
    assert events[0].evidence_refs == []
    assert "heuristic" in events[0].detector


def test_stationary_lying_pose_does_not_trigger():
    d = TemporalFallDetector()
    assert not any(d.process(lying_pose(t)) for t in range(0, 1500, 100))


def test_sitting_or_bending_without_horizontal_transition_does_not_trigger():
    d = TemporalFallDetector()
    frames = [pose(t) for t in (0, 100, 200)]
    frames += [pose(t, hip_y=0.78, shoulder_y=0.45, shoulder_x=0.5)
               for t in range(300, 1400, 100)]
    assert not any(d.process(frame) for frame in frames)


def test_horizontal_pose_without_downward_hip_drop_does_not_trigger():
    d = TemporalFallDetector()
    frames = [pose(t) for t in (0, 100, 200)]
    frames += [lying_pose(t, hip_y=0.59) for t in range(300, 1100, 100)]
    assert not any(d.process(frame) for frame in frames)


def test_low_visibility_clears_pending_candidate():
    d = TemporalFallDetector()
    for f in (pose(0), pose(100), lying_pose(200), lying_pose(300)):
        assert d.process(f) is None
    assert d.process(lying_pose(350, visibility=0.1)) is None
    # Not enough sustained valid horizontal frames since loss.
    assert d.process(lying_pose(400)) is None
    assert d.process(lying_pose(600)) is None


def test_gap_and_cross_camera_do_not_leak_fall_context():
    d = TemporalFallDetector()
    d.process(pose(0))
    d.process(pose(100))
    assert d.process(lying_pose(2000)) is None  # time gap discards baseline
    assert d.process(lying_pose(2200, source="other-camera")) is None


def test_duplicate_timestamp_rejected():
    d = TemporalFallDetector()
    d.process(pose(100))
    with pytest.raises(ValueError, match="strictly increase"):
        d.process(pose(100))


def test_cooldown_prevents_repeat_events_while_horizontal():
    d = TemporalFallDetector(DetectorConfig(cooldown_ms=3000))
    frames = [pose(0), pose(100), pose(200)]
    frames.extend(lying_pose(t) for t in range(300, 3100, 100))
    assert sum(d.process(f) is not None for f in frames) == 1


def test_invalid_landmarks_and_config():
    with pytest.raises(ValueError):
        Landmark(float("nan"), 0.2, 1.0)
    with pytest.raises(ValueError):
        DetectorConfig(horizontal_min_angle_deg=10)
    assert PoseFeatures.from_frame(PoseFrame(0, {}), min_visibility=0.4) is None


def test_frame_source_switch_resets_historical_pose():
    d = TemporalFallDetector()
    d.process(pose(0))
    d.process(pose(100))
    assert d.process(lying_pose(200, source="different-camera")) is None
    assert d.process(lying_pose(900, source="different-camera")) is None
