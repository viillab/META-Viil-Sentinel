"""Synthetic data only; real-source research training is a separate CLI."""
from copy import deepcopy
import json

import numpy as np
import pytest

from sentinel_edge.temporal_training import synthetic_demo
from sentinel_edge.tiny_mlp_training import (
    ARCH, HIDDEN, INPUTS, TinyMLP, check_numeric_artifact,
    choose_validation_threshold, fit_tiny_mlp, pack_numeric_model,
    read_numeric_model, train_compare,
)


def training_toy():
    x = np.array([
        np.full(INPUTS, value, dtype=float)
        for value in (-3., -2., -1., 1., 2., 3.)
    ])
    y = np.array([0, 0, 0, 1, 1, 1], dtype=int)
    return x, y


def test_tiny_real_numpy_gradient_updates_and_candidate_is_deterministic():
    x, y = training_toy()
    first, second = fit_tiny_mlp(x, y), fit_tiny_mlp(x, y)
    assert first.w1.shape == (INPUTS, HIDDEN)
    assert first.w2.shape == (HIDDEN,)
    assert first.bytes < 4096
    assert np.array_equal(first.w1, second.w1)
    assert np.array_equal(first.w2, second.w2)
    probs = first.score(x)
    assert np.isfinite(probs).all()
    assert probs[y == 1].mean() > probs[y == 0].mean()


def test_train_only_fitting_invariant_under_mutated_val_and_test():
    groups, features = synthetic_demo()
    model, report = train_compare(groups, features)
    mutated_groups = deepcopy(groups)
    mutated_bundle = deepcopy(features)
    for c in mutated_groups["clips"]:
        if c["split"] == "test":
            c["expected_fall"] = not c["expected_fall"]
    for row in mutated_bundle["windows"]:
        if row["clip_id"] in {
            c["clip_id"] for c in mutated_groups["clips"] if c["split"] == "test"
        }:
            for frame in row["features"]:
                frame[0] = 10.0
                frame[1] = 10.0
    after, later = train_compare(mutated_groups, mutated_bundle)
    for name in ("mean", "scale", "w1", "b1", "w2"):
        assert np.array_equal(getattr(model, name), getattr(after, name))
    assert model.bias == after.bias and model.threshold == after.threshold
    assert report["tiny_val"] == later["tiny_val"]
    assert report["linear_val"] == later["linear_val"]
    assert report["selected_on_validation"] == later["selected_on_validation"]
    assert report["tiny_old_exposed_test_diagnostic"] != (
        later["tiny_old_exposed_test_diagnostic"]
    )


def test_validation_threshold_is_independent_of_test():
    x, y = training_toy()
    m = fit_tiny_mlp(x, y)
    threshold, balanced = choose_validation_threshold(m, x, y)
    assert .05 <= threshold <= .95
    assert balanced >= .5
    assert threshold == choose_validation_threshold(m, x, y)[0]


def test_synthetic_compare_exposes_only_aggregate_metrics():
    groups, bundle = synthetic_demo()
    tiny, report = train_compare(groups, bundle)
    assert isinstance(tiny, TinyMLP)
    assert report["source_actor_identities_independently_verified"] is False
    assert report["publisher_labels_human_reviewed"] is False
    assert report["production_model_or_alerts_changed"] is False
    assert report["architecture"] == ARCH
    assert report["tiny_parameters_bytes"] < 4096
    assert "windows" not in json.dumps(report)
    assert "fictional-test-00" not in json.dumps(report)


@pytest.mark.parametrize("broken", ["not_enough", "one_class", "nan", "wrong_dim"])
def test_bad_or_leaky_training_inputs_rejected(broken):
    x, y = training_toy()
    if broken == "not_enough":
        x, y = x[:3], y[:3]
    elif broken == "one_class":
        y = np.ones(len(y), dtype=int)
    elif broken == "nan":
        x[0, 0] = float("nan")
    else:
        x = x[:, :29]
    with pytest.raises(ValueError, match="TRAIN"):
        fit_tiny_mlp(x, y)


def test_artifact_numeric_only_strict_reload(tmp_path):
    x, y = training_toy()
    model = fit_tiny_mlp(x, y)
    model.threshold = .71
    raw = pack_numeric_model(model, source_digest="c" * 64)
    assert raw["research_only"] is True
    assert len(json.dumps(raw)) < 10_240
    assert "clip_id" not in str(raw)
    assert "landmarks" not in str(raw)
    assert "subject_id" not in str(raw)
    output = tmp_path / "research-only.json"
    output.write_text(json.dumps(raw), encoding="utf8")
    restored = read_numeric_model(output)
    assert np.array_equal(restored.w1, model.w1)
    assert np.array_equal(restored.scale, model.scale)
    assert restored.threshold == .71
    assert np.array_equal(restored.score(x), model.score(x))


@pytest.mark.parametrize("field,wrong", [
    ("architecture", "fake_tcn"),
    ("research_only", False),
    ("hidden", 9),
    ("w1", [[1.0]]),
    ("scale", [0.0] * INPUTS),
    ("threshold", 1.1),
    ("mean", [float("nan")] * INPUTS),
    ("source_sha256", "nonsense"),
])
def test_private_artifact_tampering_rejected(field, wrong):
    x, y = training_toy()
    m = fit_tiny_mlp(x, y)
    raw = pack_numeric_model(m, source_digest="b" * 64)
    raw[field] = wrong
    with pytest.raises((ValueError, TypeError)):
        check_numeric_artifact(raw)


def test_artifact_malformed_top_level_rejected():
    with pytest.raises(ValueError, match="schema"):
        check_numeric_artifact({"version": 1})
