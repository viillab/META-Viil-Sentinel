"""Research-only V1/V2 train/inference normalization parity regression.

Synthetic matrices only; no real subjects or accuracy conclusions.
"""
import numpy as np
import pytest

from sentinel_edge.model_quality import _fit_candidate
from sentinel_edge.temporal_training import TemporalLinearModel


def _linear():
    return TemporalLinearModel(
        mean=np.zeros(30), scale=np.ones(30),
        weights=np.array([1., *([0.] * 29)]),
        bias=-2., threshold=.5,
    )




def test_research_reports_expose_explicit_inference_preprocessing_contract():
    from sentinel_edge.model_quality import compare_models
    from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate

    manifest, bundle = synthetic_demo()
    _, v1 = train_and_evaluate(manifest, bundle)
    _, v2 = compare_models(manifest, bundle)
    for report in (v1, v2):
        assert report["inference_preprocessing"] == (
            "train_only_zscore_clamp_minus12_plus12"
        )
        assert report["automated_fall_alerting_authorized"] is False


@pytest.mark.parametrize("bad_scale", [0.0, -1.0, np.nan, np.inf])
def test_nonpositive_or_nonfinite_fitted_normalizer_refused(bad_scale):
    model = _linear()
    model.scale[0] = bad_scale
    with pytest.raises(ValueError, match="normalization parameters"):
        model.predict_probability(np.zeros(30))

def test_v1_vector_and_batch_outliers_use_train_clip_bounds():
    model = _linear()
    rows = np.zeros((3, 30))
    rows[:, 0] = [-1e9, 0., 1e9]
    normalized = np.clip(rows[:, 0], -12, 12)
    expected = 1 / (1 + np.exp(-np.clip(normalized - 2, -45, 45)))
    np.testing.assert_allclose(model.predict_probability(rows), expected,
                               rtol=0, atol=1e-12)
    for i in range(3):
        assert model.predict_probability(rows[i]) == pytest.approx(
            expected[i], abs=1e-12,
        )


@pytest.mark.parametrize("invalid", [
    np.ones(29), np.ones((2, 29)), np.ones((1, 1, 30)),
    np.full(30, np.nan), np.full(30, np.inf),
    np.zeros((0, 30)),
])
def test_v1_rejects_invalid_feature_shape_or_nonfinite_values(invalid):
    with pytest.raises(ValueError, match="finite|shape|30"):
        _linear().predict_probability(invalid)


def _v2_fixture(dim=30):
    training = np.zeros((4, dim))
    training[:, 0] = [-1., 0.5, -0.5, 1.]
    y = np.array([0, 0, 1, 1])
    predict, _, _, _ = _fit_candidate(training, y, training, y)
    return predict, training


@pytest.mark.parametrize("dim", [30, 40])
def test_v2_predictor_matches_frozen_normalized_training_extremes(dim):
    predict, training = _v2_fixture(dim)
    mean, std = training[:, 0].mean(), training[:, 0].std()
    extreme = np.zeros((2, dim))
    extreme[:, 0] = [-1e8, 1e8]
    clipped = np.zeros((2, dim))
    clipped[:, 0] = [mean - 12 * std, mean + 12 * std]
    np.testing.assert_allclose(predict(extreme), predict(clipped),
                               rtol=0, atol=1e-12)
    assert predict(extreme[0]) == pytest.approx(predict(clipped[0]), abs=1e-12)


@pytest.mark.parametrize("invalid", [
    np.ones(29), np.ones((2, 29)), np.ones((1, 1, 30)),
    np.full(30, np.nan), np.full(30, np.inf),
    np.zeros((0, 30)),
])
def test_v2_rejects_invalid_feature_shape_or_nonfinite_values(invalid):
    predict, _ = _v2_fixture()
    with pytest.raises(ValueError, match="finite|shape|30"):
        predict(invalid)
