"""Strict private numeric model weight schema: version 2 and verified legacy 1.

Only invented NumPy model coefficients in this test. No personal/media data.
"""
from copy import deepcopy
import json

import numpy as np
import pytest

from sentinel_edge import private_model_training as private
from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate

CONTRACT = "train_only_zscore_clamp_minus12_plus12"


def _artifact():
    manifest, windows = synthetic_demo()
    model, _ = train_and_evaluate(manifest, windows)
    return private.checked_artifact(
        model, manifest_digest="a" * 64, proposal_digest="b" * 64,
        dataset="fully-fictional",
    ), model


def _private_path(tmp_path, monkeypatch, name="model.json"):
    root = tmp_path / "repo"
    folder = root / "data" / "private"
    folder.mkdir(parents=True, exist_ok=True)
    fake_module = root / "services" / "edge-vision" / "sentinel_edge"
    monkeypatch.setattr(private, "__file__",
                        str(fake_module / "private_model_training.py"))
    return folder / name


def test_new_artifact_binds_preprocessing_and_never_contains_derived_poses():
    artifact, _ = _artifact()
    assert artifact["version"] == 2
    assert artifact["inference_preprocessing"] == CONTRACT
    assert set(artifact) == private.MODEL_FIELDS
    serialized = json.dumps(artifact)
    assert all(fragment not in serialized for fragment in (
        "fictional-", "landmarks", "video", "frames", "source_id",
        "clip_id", "features",
    ))
    assert not artifact["model_deployed"]
    assert not artifact["automated_fall_alerting_authorized"]


def test_new_model_reloads_and_predictions_match_old_trained_arrays(tmp_path, monkeypatch):
    item, model = _artifact()
    path = _private_path(tmp_path, monkeypatch)
    path.write_text(json.dumps(item), encoding="utf-8")
    loaded = private.read_private_artifact(path)
    samples = np.random.default_rng(11).normal(size=(8, 30))
    samples[0, 0] = 1e9
    np.testing.assert_allclose(model.predict_probability(samples),
                               loaded.predict_probability(samples), rtol=0, atol=0)
    assert loaded.threshold == model.threshold
    assert loaded.model_bytes == model.model_bytes


def test_old_exact_version_one_artifact_can_still_load_read_only(tmp_path, monkeypatch):
    item, model = _artifact()
    legacy = deepcopy(item)
    legacy["version"] = 1
    del legacy["inference_preprocessing"]
    assert set(legacy) == private.LEGACY_MODEL_FIELDS
    path = _private_path(tmp_path, monkeypatch)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    loaded = private.read_private_artifact(path)
    np.testing.assert_array_equal(loaded.weights, model.weights)
    np.testing.assert_array_equal(loaded.mean, model.mean)


@pytest.mark.parametrize("mutation", [
    {"version": True}, {"version": 3}, {"version": 1},
    {"inference_preprocessing": "unbounded_zscore"},
    {"inference_preprocessing": None},
    {"inference_preprocessing": ""},
    {"inference_preprocessing": "train_only_zscore_clamp_minus12_plus12\n"},
    {"legacy_override": True}, {"weights": [0.0] * 29},
    {"mean": [float("nan")] * 30}, {"scale": [0.0] * 30},
    {"publisher_labels_only": False}, {"model_deployed": True},
])
def test_corrupt_v2_versions_tags_extras_or_coefficients_are_rejected(
    tmp_path, monkeypatch, mutation,
):
    artifact, _ = _artifact()
    artifact.update(mutation)
    path = _private_path(tmp_path, monkeypatch)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises((ValueError, TypeError, OverflowError)):
        private.read_private_artifact(path)


@pytest.mark.parametrize("mutation", [
    {"version": 2},
    {"inference_preprocessing": CONTRACT},
    {"version": False},
])
def test_legacy_artifact_cannot_masquerade_as_version_two(
    tmp_path, monkeypatch, mutation,
):
    artifact, _ = _artifact()
    artifact["version"] = 1
    del artifact["inference_preprocessing"]
    artifact.update(mutation)
    path = _private_path(tmp_path, monkeypatch)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        private.read_private_artifact(path)
