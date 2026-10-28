"""Fictional-only causal 1500ms shadow contracts, no production alerts."""
import json

import numpy as np
import pytest

from sentinel_edge.causal_1500ms_shadow import (
    Causal1500msModelShadow, CONTEXT_MS, HOP_MS, MAX_BUFFERED_FRAMES,
)
from sentinel_edge.contracts import Landmark, PoseFrame


class SyntheticPredictor:
    # Synthetic metadata imitates the 1.5s trained model interface ONLY.
    temporal_context_ms = 1500
    input_dimensions = 30
    threshold = .5

    def __init__(self, score=.8):
        self.score = score
        self.calls = 0
        self.descriptors = []

    def predict_probability(self, x):
        assert x.shape == (30,)
        assert np.isfinite(x).all()
        self.calls += 1
        self.descriptors.append(x.copy())
        return self.score


def pose(t, *, source="fictional-a", visible=True, hip=.50):
    landmarks = (
        {
            11: Landmark(.45, hip - .20, .98),
            12: Landmark(.55, hip - .20, .98),
            23: Landmark(.45, hip, .98),
            24: Landmark(.55, hip, .98),
        } if visible else {}
    )
    return PoseFrame(timestamp_ms=t, source_id=source, landmarks=landmarks)


def test_no_predictions_before_1500ms_and_hops_are_fixed():
    predictor = SyntheticPredictor()
    shadow = Causal1500msModelShadow(predictor)
    for t in range(0, 1500, 50):
        assert shadow.observe(pose(t)) is None
    assert predictor.calls == 0
    for t in range(1500, 2250, 50):
        assert shadow.observe(pose(t)) is None
    data = shadow.summary()
    assert data["incoming_frames"] == 45
    assert data["scored_windows"] == 3
    assert data["positive_windows"] == 3
    assert data["pose_abstained_windows"] == 0
    assert data["context_ms"] == CONTEXT_MS
    assert data["hop_ms"] == HOP_MS
    assert data["shadow_research_only_no_incident_or_dispatch"]
    assert data["max_buffered_frames_seen"] <= MAX_BUFFERED_FRAMES


def test_one_second_of_later_future_frames_cannot_change_previous_score():
    def replay(future_hip):
        predictor = SyntheticPredictor()
        shadow = Causal1500msModelShadow(predictor)
        for t in range(0, 2300, 50):
            shadow.observe(pose(t, hip=(.49 if t <= 1500 else future_hip)))
        return predictor.descriptors[0]
    np.testing.assert_array_equal(replay(.40), replay(.90))


def test_missing_pose_is_abstention_not_assumed_nonfall():
    predictor = SyntheticPredictor()
    shadow = Causal1500msModelShadow(predictor)
    for t in range(0, 1600, 50):
        shadow.observe(pose(t, visible=t >= 1400))
    result = shadow.summary()
    assert predictor.calls == 0
    assert result["pose_abstained_windows"] == 1
    assert result["negative_windows"] == 0


def test_reset_on_timestamp_gap_or_source_switch():
    predictor = SyntheticPredictor()
    shadow = Causal1500msModelShadow(predictor)
    for t in range(0, 1700, 50):
        shadow.observe(pose(t))
    assert predictor.calls == 1
    shadow.observe(pose(2800))  # >700ms from 1650
    assert predictor.calls == 1
    assert shadow.summary()["timestamp_gap_resets"] == 1
    shadow.observe(pose(0, source="fictional-b"))
    assert shadow.summary()["source_resets"] == 1
    for t in range(50, 1600, 50):
        shadow.observe(pose(t, source="fictional-b"))
    assert predictor.calls == 2


def test_duplicate_timestamps_fail_closed():
    shadow = Causal1500msModelShadow(SyntheticPredictor())
    shadow.observe(pose(0))
    with pytest.raises(ValueError, match="increasing"):
        shadow.observe(pose(0))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.1,
                                  "0.75", True])
def test_invalid_predictions_refused(bad):
    predictor = SyntheticPredictor(score=bad)
    shadow = Causal1500msModelShadow(predictor)
    with pytest.raises(ValueError, match="probability"):
        for t in range(0, 1600, 50):
            shadow.observe(pose(t))


@pytest.mark.parametrize("threshold", [0.0, 1.0, "0.5", True, float("nan")])
def test_invalid_or_untrained_threshold_refused(threshold):
    predictor = SyntheticPredictor()
    predictor.threshold = threshold
    with pytest.raises(ValueError, match="valid fitted"):
        Causal1500msModelShadow(predictor)


def test_bounds_memory_and_does_not_export_private_pose_or_model_data():
    predictor = SyntheticPredictor(score=.1)
    shadow = Causal1500msModelShadow(predictor)
    for t in range(0, 12000, 20):
        shadow.observe(pose(t, source="private-source-serial", hip=.55))
    result = shadow.summary()
    assert result["max_buffered_frames_seen"] < MAX_BUFFERED_FRAMES
    assert result["scored_windows"] == result["negative_windows"]
    assert result["positive_windows"] == 0
    text = json.dumps(result, sort_keys=True)
    assert "private-source-serial" not in text
    assert "landmarks" not in result
    assert "hip_y" not in result
    assert "confidence" not in text
    assert "0.1" not in text
    assert "timestamp_ms" not in text
    assert result["no_source_ids_raw_landmarks_model_probabilities_or_timestamps_exported"]


def test_buffer_overflow_reset_cannot_use_incomplete_old_context():
    predictor = SyntheticPredictor()
    shadow = Causal1500msModelShadow(predictor)
    # 1 ms gaps deliberately overflow the fixed RAM cap before 1500ms.
    for t in range(300):
        shadow.observe(pose(t))
    assert shadow.summary()["buffer_overflow_resets"] >= 1
    assert predictor.calls == 0


def test_real_numpy_scalar_probability_supported():
    predictor = SyntheticPredictor(score=np.float64(.75))
    shadow = Causal1500msModelShadow(predictor)
    for t in range(0, 1600, 50):
        shadow.observe(pose(t))
    assert shadow.summary()["positive_windows"] == 1




@pytest.mark.parametrize("bad_context,bad_dimension", [
    (8000, 30), (1500, 40), (None, 30),
    ("1500", 30), (True, 30), (1500, False),
])
def test_reject_incompatible_frozen_eight_second_model_and_invalid_tags(
    bad_context, bad_dimension,
):
    predictor = SyntheticPredictor()
    predictor.temporal_context_ms = bad_context
    predictor.input_dimensions = bad_dimension
    with pytest.raises(ValueError, match="1500ms 30D"):
        Causal1500msModelShadow(predictor)

@pytest.mark.parametrize("bad_time", [True, 2.5, float("nan")])
def test_bad_timestamp_type_refused_before_time_alignment(bad_time):
    shadow = Causal1500msModelShadow(SyntheticPredictor())
    with pytest.raises(ValueError, match="validated PoseFrame"):
        shadow.observe(PoseFrame(timestamp_ms=bad_time, landmarks={}))


def test_incorrect_input_object_refused():
    shadow = Causal1500msModelShadow(SyntheticPredictor())
    with pytest.raises(ValueError, match="PoseFrame"):
        shadow.observe({"timestamp_ms": 0, "landmarks": {}})
