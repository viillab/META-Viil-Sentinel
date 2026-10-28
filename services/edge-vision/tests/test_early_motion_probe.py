"""Synthetic-only tests, without saving identifiable poses or fake medical claims."""
import json

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.early_motion_probe import (
    CausalMotionProbe, MAX_BUFFERED_POSES,
)
from sentinel_edge.runner import parse_args


def pose(ms, hip=.42, *, upright=True, visible=True, source="fixture"):
    if not visible:
        return PoseFrame(timestamp_ms=ms, source_id=source, landmarks={})
    # Upright torso angle near 0 degrees. The alternative is near 70 degrees.
    shoulder_x = (.45, .55) if upright else (.67, .77)
    shoulder_y = hip - (.25 if upright else .08)
    return PoseFrame(
        timestamp_ms=ms, source_id=source,
        landmarks={
            11: Landmark(shoulder_x[0], shoulder_y, .98),
            12: Landmark(shoulder_x[1], shoulder_y, .98),
            23: Landmark(.45, hip, .98),
            24: Landmark(.55, hip, .98),
        },
    )


def synthetic_descent():
    rows = [pose(i*100) for i in range(6)]
    rows.extend(pose((6+i)*100, .42 + .03*(i+1),
                     upright=(i < 2)) for i in range(8))
    return rows


def test_short_causal_descent_gives_research_proposal_without_8s_model():
    detector = CausalMotionProbe()
    for frame in synthetic_descent():
        assert detector.observe(frame) is None
    s = detector.summary()
    assert s["frames"] == 14
    assert s["pose_accepted_frames"] == 14
    assert s["provisional_motion_proposals"] >= 1
    assert s["lookback_ms"] == 2000
    assert s["not_a_trained_classifier"]
    assert s["not_a_confirmed_fall_or_emergency_incident"]
    assert s["no_model_score_poses_frames_or_timestamps_exported"]
    assert "source_id" not in json.dumps(s)
    assert "hip_y" not in json.dumps(s)


def test_static_and_horizontal_without_prior_upright_do_not_propose():
    p = CausalMotionProbe()
    for i in range(90):
        p.observe(pose(i*33, .42, upright=False))
    assert p.summary()["provisional_motion_proposals"] == 0
    q = CausalMotionProbe()
    for i in range(90):
        q.observe(pose(i*33, .42))
    assert q.summary()["provisional_motion_proposals"] == 0


def test_missing_pose_clears_baseline_not_recovered_from_old_frames():
    p = CausalMotionProbe()
    for i in range(6):
        p.observe(pose(i*100))
    p.observe(pose(600, visible=False))
    for i in range(1, 7):
        p.observe(pose(600 + 100*i, .4 + .04*i, upright=False))
    s = p.summary()
    assert s["pose_abstained_frames"] == 1
    assert s["provisional_motion_proposals"] == 0


def test_gap_and_source_switch_are_fail_closed():
    p = CausalMotionProbe()
    for i in range(5):
        p.observe(pose(i*100))
    p.observe(pose(1300, .65, upright=False))  # 900ms break
    assert p.summary()["timestamp_gap_resets"] == 1
    assert p.summary()["provisional_motion_proposals"] == 0
    for i in range(5):
        p.observe(pose(i*100, .6 + i*.03, upright=False, source="new"))
    assert p.summary()["source_resets"] == 1
    assert p.summary()["provisional_motion_proposals"] == 0


def test_clock_backwards_refused_within_source_but_new_source_allowed():
    p = CausalMotionProbe()
    p.observe(pose(100))
    with pytest.raises(ValueError, match="strictly increase"):
        p.observe(pose(100))
    p.observe(pose(0, source="different"))


def test_cooldown_and_bounded_ram_history_no_raw_state_in_summary():
    p = CausalMotionProbe()
    for i in range(900):
        p.observe(pose(i*33))
    s = p.summary()
    assert s["maximum_pose_history_frames"] <= MAX_BUFFERED_POSES
    assert s["frames"] == 900
    assert s["provisional_motion_proposals"] == 0


def test_cli_requires_explicit_local_research_consent(tmp_path):
    task = tmp_path / "pose.task"
    task.write_bytes(b"synthetic task")
    base = ["--source","0","--model",str(task),"--early-motion-probe"]
    with pytest.raises(SystemExit):
        parse_args(base)
    args = parse_args(base + ["--confirm-consent","--acknowledge-pose-privacy"])
    assert args.early_motion_probe is True
