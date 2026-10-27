"""Synthetic gate metrics do not imply clinical model performance."""
from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.signal_diagnostics import diagnose_pose_signals


def pose(t: int, horizontal: bool = False) -> PoseFrame:
    if horizontal:
        sx, sy, hx, hy = .23, .78, .57, .78
    else:
        sx, sy, hx, hy = .5, .25, .5, .53
    return PoseFrame(timestamp_ms=t, source_id="fake-01", landmarks={
        11: Landmark(sx - .045, sy, .98),
        12: Landmark(sx + .045, sy, .98),
        23: Landmark(hx - .05, hy, .98),
        24: Landmark(hx + .05, hy, .98),
    })


def test_synthetic_upright_to_horizontal_reports_gate_run():
    seq = [pose(t) for t in (0, 100, 200)]
    seq.extend(pose(t, True) for t in (300, 500, 700, 850))
    d = diagnose_pose_signals(seq)
    assert d["analyzed_frames"] == 7
    assert d["valid_torso_frames"] == 7
    assert d["upright_frames"] == 3
    assert d["horizontal_frames"] == 4
    assert d["horizontal_with_descent_frames"] == 4
    assert d["max_horizontal_descent_hold_ms"] == 550
    assert d["max_observed_descent"] > 0.13


def test_pose_occlusion_resets_sequence():
    seq = [pose(0), pose(100)]
    seq.append(PoseFrame(timestamp_ms=200, source_id="fake-01", landmarks={}))
    seq.extend(pose(t, True) for t in (300, 500, 700))
    d = diagnose_pose_signals(seq)
    assert d["valid_torso_frames"] == 5
    assert d["horizontal_frames"] == 3
    assert d["horizontal_with_descent_frames"] == 0
    assert d["max_horizontal_descent_hold_ms"] == 0
