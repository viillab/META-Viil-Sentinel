"""Offline pose coverage tests: no person, camera or frame data is persisted."""
import pytest

from sentinel_edge.pose_coverage import PoseCoverageMonitor


def test_no_pose_gap_once_and_recovery_without_camera_failure_claim():
    monitor = PoseCoverageMonitor(gap_threshold_frames=3)
    assert monitor.observe(False) is None
    assert monitor.observe(False) is None
    gap = monitor.observe(False)
    assert gap["condition"] == "pose_not_observed"
    assert gap["camera_stream_disconnection_inferred"] is False
    assert gap["person_absence_or_fall_inferred"] is False
    assert monitor.observe(False) is None  # No repeated alarms
    resumed = monitor.observe(True)
    assert resumed["condition"] == "pose_observed_again"
    assert resumed["operator_diagnostic_only"] is True
    assert monitor.observe(True) is None
    assert monitor.summary() == {
        "schema_version": "viil.edge.pose_coverage.v1",
        "frames_observed": 6,
        "pose_observed_frames": 2,
        "longest_no_pose_streak_frames": 4,
        "no_pose_streak_at_end_frames": 0,
        "gap_threshold_frames": 3,
        "gap_threshold_ms": 3000,
        "duration_gate_applied": False,
        "longest_no_pose_duration_ms": None,
        "condition": "pose_seen",
        "operator_diagnostic_only": True,
        "person_absence_or_fall_inferred": False,
        "not_a_camera_health_or_safety_certification": True,
    }


def test_timestamp_aware_gap_requires_both_time_and_frames():
    monitor = PoseCoverageMonitor(gap_threshold_frames=3, gap_threshold_ms=3000)
    assert monitor.observe(False, timestamp_ms=100) is None
    assert monitor.observe(False, timestamp_ms=400) is None
    assert monitor.observe(False, timestamp_ms=700) is None
    assert monitor.observe(False, timestamp_ms=1200) is None
    assert monitor.observe(False, timestamp_ms=3100)["condition"] == "pose_not_observed"
    assert monitor.observe(False, timestamp_ms=3500) is None
    assert monitor.observe(True, timestamp_ms=3600)["condition"] == "pose_observed_again"
    summary = monitor.summary()
    assert summary["duration_gate_applied"] is True
    assert summary["longest_no_pose_duration_ms"] == 3400
    assert summary["gap_threshold_ms"] == 3000
    assert summary["condition"] == "pose_seen"


def test_timestamp_gate_avoids_frame_rate_dependent_false_transition():
    fast = PoseCoverageMonitor(gap_threshold_frames=45, gap_threshold_ms=3000)
    # 90 frames at about 30 fps cover less than 3 seconds.
    for index in range(90):
        assert fast.observe(False, timestamp_ms=index * 33) is None
    assert fast.observe(False, timestamp_ms=3001)["condition"] == "pose_not_observed"
    assert fast.summary()["longest_no_pose_duration_ms"] == 3001


def test_reject_time_reversal_and_mixed_timing_mode():
    monitor = PoseCoverageMonitor(gap_threshold_frames=3)
    monitor.observe(False, timestamp_ms=100)
    with pytest.raises(ValueError):
        monitor.observe(False, timestamp_ms=100)
    with pytest.raises(ValueError):
        monitor.observe(False, timestamp_ms=50)
    with pytest.raises(ValueError):
        monitor.observe(False)
    assert monitor.summary()["frames_observed"] == 1


@pytest.mark.parametrize("bad_duration", [0, 249, 30001, True, 2000.0])
def test_reject_bad_duration_threshold(bad_duration):
    with pytest.raises(ValueError):
        PoseCoverageMonitor(gap_threshold_ms=bad_duration)


def test_camera_session_gaps_are_not_inherited_by_new_session():
    old = PoseCoverageMonitor(gap_threshold_frames=3)
    for _ in range(3):
        old.observe(False)
    new = PoseCoverageMonitor(gap_threshold_frames=3)
    assert new.summary()["frames_observed"] == 0
    assert new.observe(False) is None
    assert new.summary()["condition"] == "unverified"
    assert old.summary()["condition"] == "pose_not_observed"


def test_empty_room_and_short_occlusion_do_not_assert_anything():
    monitor = PoseCoverageMonitor(gap_threshold_frames=4)
    assert [monitor.observe(False) for _ in range(3)] == [None] * 3
    assert monitor.summary()["condition"] == "unverified"
    monitor.observe(True)
    monitor.observe(False)
    assert monitor.summary()["condition"] == "pose_seen"
    assert monitor.summary()["no_pose_streak_at_end_frames"] == 1


@pytest.mark.parametrize("limit", [0, -1, 301, 2.5, True])
def test_threshold_must_be_bounded_int(limit):
    with pytest.raises(ValueError):
        PoseCoverageMonitor(gap_threshold_frames=limit)


@pytest.mark.parametrize("flag", ["yes", 1, None, []])
def test_pose_status_must_be_explicit_bool(flag):
    with pytest.raises(ValueError):
        PoseCoverageMonitor().observe(flag)
