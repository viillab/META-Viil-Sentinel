"""Experimental, review-only detector invariants — synthetic fixtures only."""
from math import nan

import pytest

# Edge video research dependencies are optional in a backend-only venv.
contracts = pytest.importorskip("sentinel_edge.contracts")
review = pytest.importorskip("app.experimental_review_motion")
Landmark = contracts.Landmark
PoseFrame = contracts.PoseFrame
ExperimentalReviewMotionDetector = review.ExperimentalReviewMotionDetector
ReviewMotionConfig = review.ReviewMotionConfig


def frame(ts, *, hip_y=.42, shoulder_y=.27, shoulder_x=.55,
          hip_x=.5, visible=.99, source="fixture-a"):
    return PoseFrame(
        timestamp_ms=ts, source_id=source,
        landmarks={
            11: Landmark(shoulder_x-.04, shoulder_y, visible),
            12: Landmark(shoulder_x+.04, shoulder_y, visible),
            23: Landmark(hip_x-.04, hip_y, visible),
            24: Landmark(hip_x+.04, hip_y, visible),
        },
    )


def execute(frames):
    detector = ExperimentalReviewMotionDetector()
    return [event for item in frames if (event := detector.process(item)) is not None]


def test_seated_to_semi_horizontal_rapid_drop_is_review_only():
    # Baseline angle ~18deg; not the strict upright->56deg requirement.
    samples = [
        frame(0), frame(100), frame(200),
        frame(340, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(460, hip_y=.66, shoulder_y=.52, shoulder_x=.79),
        frame(610, hip_y=.66, shoulder_y=.52, shoulder_x=.79),
        frame(750, hip_y=.66, shoulder_y=.52, shoulder_x=.79),
    ]
    events = execute(samples)
    assert len(events) == 1
    event = events[0]
    assert event.hypothesis == "rapid_descent_rotation"
    assert event.source_id == "fixture-a"
    assert event.review_only is True
    assert event.fall_confirmed is False
    assert event.notification_authorized is False
    assert event.meta_upload_authorized is False
    assert event.probability_calibrated is False


def test_horizontal_body_rapid_drop_requires_motion_not_just_lying():
    def horizontal(ts, hip):
        return frame(
            ts, hip_y=hip, shoulder_y=hip,
            shoulder_x=.26, hip_x=.52,
        )
    samples = [
        horizontal(0, .45), horizontal(100, .45), horizontal(200, .45),
        horizontal(350, .67), horizontal(500, .68),
        horizontal(650, .68), horizontal(790, .68),
    ]
    events = execute(samples)
    assert len(events) == 1
    assert events[0].hypothesis == "horizontal_descent"
    assert not execute([horizontal(t, .70) for t in range(0, 1800, 100)])


def test_normal_slow_lowers_bending_and_stationary_lie_do_not_fire():
    slowly_lowers = [
        frame(t, hip_y=.42 + .017 * i, shoulder_y=.27 + .017 * i,
              shoulder_x=.58)
        for i, t in enumerate(range(0, 1400, 100))
    ]
    assert not execute(slowly_lowers)
    assert not execute([frame(t) for t in range(0, 1700, 100)])


def test_visibility_break_resets_pending_and_no_cross_camera_inference():
    d = ExperimentalReviewMotionDetector()
    assert d.process(frame(0)) is None
    assert d.process(frame(100)) is None
    assert d.process(frame(240, hip_y=.67, shoulder_y=.53, shoulder_x=.78)) is None
    assert d.process(frame(320, visible=.1)) is None
    assert d.process(frame(450, hip_y=.67, shoulder_y=.53, shoulder_x=.78)) is None
    assert d.process(frame(600, hip_y=.67, shoulder_y=.53, shoulder_x=.78)) is None
    assert d.process(frame(700, source="new-camera",
                           hip_y=.68, shoulder_y=.52, shoulder_x=.78)) is None


def test_frame_gap_and_duplicate_timestamp_rejected():
    d = ExperimentalReviewMotionDetector()
    d.process(frame(0))
    d.process(frame(100))
    with pytest.raises(ValueError, match="increase"):
        d.process(frame(100))
    assert d.process(frame(1500, hip_y=.7,
                           shoulder_y=.56, shoulder_x=.8)) is None


def test_tampered_config_and_cooldown():
    for fields in (
        {"min_rapid_hip_drop": -1},
        {"horizontal_min_angle_deg": 100},
        {"min_angle_change_deg": nan},
        {"max_history_ms": 100, "rapid_window_ms": 300},
        {"cooldown_ms": -1},
        {"stable_hold_ms": 0},
    ):
        with pytest.raises(ValueError):
            ReviewMotionConfig(**fields)
    frames = [
        frame(0), frame(100), frame(200),
        frame(340, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(750, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(950, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(1100, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(1300, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
    ]
    assert len(execute(frames)) <= 1


def test_rapid_nonfall_sitting_is_a_known_review_only_false_alert_risk():
    # From four torso points alone, a rapid voluntary lowering can resemble
    # a fall. This MUST NOT be promoted to an emergency notification.
    fast_sit = [
        frame(0), frame(100), frame(200),
        frame(340, hip_y=.63, shoulder_y=.50, shoulder_x=.76),
        frame(500, hip_y=.64, shoulder_y=.50, shoulder_x=.76),
        frame(650, hip_y=.64, shoulder_y=.50, shoulder_x=.76),
        frame(800, hip_y=.64, shoulder_y=.50, shoulder_x=.76),
    ]
    event = execute(fast_sit)
    assert event, "Known potential overflag must be visible in safety tests"
    assert all(x.review_only and not x.fall_confirmed for x in event)
    assert all(not x.notification_authorized and not x.meta_upload_authorized for x in event)
