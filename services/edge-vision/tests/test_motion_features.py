"""Research-only temporal features; no raw video and no model claims."""
from dataclasses import asdict
from math import isfinite

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.motion_features import TemporalFeatureEncoder, FEATURE_NAMES


def pose(t, *, sx=0.5, sy=0.23, hy=0.53, source="fake", visible=1.0):
    return PoseFrame(timestamp_ms=t, source_id=source, landmarks={
        11: Landmark(sx - 0.05, sy, visible),
        12: Landmark(sx + 0.05, sy, visible),
        23: Landmark(0.45, hy, visible),
        24: Landmark(0.55, hy, visible),
    })


def test_time_aware_hip_and_rotation_velocity():
    encoder = TemporalFeatureEncoder(window_size=3)
    encoder.process(pose(0))
    w = encoder.process(pose(200, sx=0.65, hy=0.65))
    assert w.features[-1][2] == pytest.approx(0.6)  # 0.12 / .2 seconds
    assert w.features[-1][3] > 0  # Rotating toward horizontal
    assert w.features[-1][5] == 1.0
    assert len(w.features) == 2
    assert w.feature_names == FEATURE_NAMES
    assert w.model_status == "FEATURES_ONLY_NOT_TRAINED"
    assert "source" not in asdict(w)
    assert "landmarks" not in asdict(w)


def test_non_uniform_fps_changes_velocity_denominator():
    a, b = TemporalFeatureEncoder(), TemporalFeatureEncoder()
    a.process(pose(100))
    b.process(pose(100))
    va = a.process(pose(200, hy=0.63)).features[-1][2]
    vb = b.process(pose(300, hy=0.63)).features[-1][2]
    assert va == pytest.approx(1.0)
    assert vb == pytest.approx(0.5)


def test_occlusion_mask_and_no_velocity_across_occlusion():
    encoder = TemporalFeatureEncoder(window_size=5)
    encoder.process(pose(0))
    occluded = encoder.process(pose(100, visible=0.2)).features[-1]
    assert occluded == (0.0,) * 6
    after = encoder.process(pose(200, hy=0.8)).features[-1]
    assert after[2] == 0 and after[3] == 0
    assert after[5] == 1.0


def test_source_switch_gap_and_duplicate_timestamp_guard():
    encoder = TemporalFeatureEncoder(window_size=4)
    encoder.process(pose(0))
    encoder.process(pose(100, hy=0.65))
    assert len(encoder.process(pose(200, source="other")).features) == 1
    assert len(encoder.process(pose(2000, source="other")).features) == 1
    with pytest.raises(ValueError, match="strictly"):
        encoder.process(pose(2000, source="other"))


def test_bounded_memory_and_masks_on_left_padding():
    encoder = TemporalFeatureEncoder(window_size=3)
    assert encoder.padded_window().features == ((0.0,) * 6,) * 3
    for i in range(700):
        window = encoder.process(pose(i * 100))
        assert len(window.features) <= 3
        assert all(all(isfinite(v) for v in row) for row in window.features)
    assert len(encoder.padded_window().features) == 3
    assert encoder.padded_window().features[-1][5] == 1.0


@pytest.mark.parametrize("kwargs", [
    {"window_size": 1}, {"window_size": True}, {"window_size": 257},
    {"min_visibility": -0.1}, {"min_visibility": float("nan")},
    {"max_gap_ms": 0}, {"max_gap_ms": 10001},
])
def test_invalid_config_fails(kwargs):
    with pytest.raises(ValueError):
        TemporalFeatureEncoder(**kwargs)
