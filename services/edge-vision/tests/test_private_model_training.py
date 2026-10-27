"""No real faces/videos/pose windows stored in tests; strict private fitted JSON."""
from copy import deepcopy
import json
from hashlib import sha256

import numpy as np
import pytest

from sentinel_edge import private_model_training as training
from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate


def example():
    manifest, windows = synthetic_demo()
    model, report = train_and_evaluate(manifest, windows)
    return manifest, windows, model, report


def test_trained_artifact_has_real_weights_but_no_person_data():
    manifest, windows, model, report = example()
    item = training.checked_artifact(
        model, manifest_digest="a" * 64, proposal_digest="b" * 64,
        dataset="example-dataset",
    )
    assert item["dimension"] == 30
    assert len(item["weights"]) == 30
    assert sum(abs(x) for x in item["weights"]) > 0
    assert item["threshold"] == model.threshold
    assert item["model_deployed"] is False
    assert item["publisher_labels_only"] is True
    payload = json.dumps(item)
    assert "fictional-" not in payload
    assert "features" not in payload
    assert "landmarks" not in payload
    assert "clip_id" not in payload
    assert model.model_bytes == 736
    assert report["trained_on"] == "declared train subjects only"


def test_saved_private_model_reloads_with_identical_probabilities(monkeypatch, tmp_path):
    _, _, model, _ = example()
    root = tmp_path / "repo"
    area = root / "data" / "private"
    area.mkdir(parents=True)
    fake_module = root / "services" / "edge-vision" / "sentinel_edge"
    monkeypatch.setattr(training, "__file__", str(fake_module / "private_model_training.py"))
    item = training.checked_artifact(
        model, manifest_digest=sha256(b"fake-manifest").hexdigest(),
        proposal_digest=sha256(b"fake-proposals").hexdigest(), dataset="fictional"
    )
    out = area / "model.json"
    out.write_text(json.dumps(item), encoding="utf-8")
    reloaded = training.read_private_artifact(out)
    features = np.random.default_rng(10).normal(size=(12, 30))
    np.testing.assert_allclose(reloaded.predict_probability(features),
                               model.predict_probability(features), atol=1e-14)
    assert reloaded.threshold == model.threshold
    assert reloaded.model_bytes == model.model_bytes


def test_private_model_rejects_nonprivate_path(monkeypatch, tmp_path):
    _, _, model, _ = example()
    fake_module = tmp_path / "repo" / "services" / "edge-vision" / "sentinel_edge"
    monkeypatch.setattr(training, "__file__", str(fake_module / "private_model_training.py"))
    item = training.checked_artifact(
        model, manifest_digest="a" * 64, proposal_digest="b" * 64, dataset="synthetic"
    )
    output = tmp_path / "unsafe.json"
    output.write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(ValueError, match="data/private"):
        training.read_private_artifact(output)


@pytest.mark.parametrize("changed", [
    {"dimension": 40},
    {"publisher_labels_only": False},
    {"model_deployed": True},
    {"training_stage": "deployed"},
    {"threshold": 100},
    {"mean": [0.0] * 29},
    {"weights": [float("inf")] * 30},
    {"scale": [0.0] * 30},
])
def test_private_model_strict_validation(monkeypatch, tmp_path, changed):
    _, _, model, _ = example()
    root = tmp_path / "repo"
    area = root / "data" / "private"
    area.mkdir(parents=True)
    fake_module = root / "services" / "edge-vision" / "sentinel_edge"
    monkeypatch.setattr(training, "__file__", str(fake_module / "private_model_training.py"))
    item = training.checked_artifact(
        model, manifest_digest="a" * 64, proposal_digest="b" * 64, dataset="synthetic"
    )
    item.update(changed)
    output = area / "mutated.json"
    output.write_text(json.dumps(item, allow_nan=True), encoding="utf-8")
    with pytest.raises((ValueError, TypeError, OverflowError)):
        training.read_private_artifact(output)


def test_heldout_features_and_labels_never_change_fitted_weights_or_threshold():
    manifest, bundle = synthetic_demo()
    _, _, base, _ = example()
    changed_manifest = deepcopy(manifest)
    changed_bundle = deepcopy(bundle)
    test_ids = {c["clip_id"] for c in manifest["clips"] if c["split"] == "test"}
    for c in changed_manifest["clips"]:
        if c["clip_id"] in test_ids:
            c["expected_fall"] = not c["expected_fall"]
    for w in changed_bundle["windows"]:
        if w["clip_id"] in test_ids:
            w["features"] = [[1.0, 2.0, 3.0, 4.0, 0.5, 1] for _ in range(30)]
    modified, _ = train_and_evaluate(changed_manifest, changed_bundle)
    np.testing.assert_array_equal(base.mean, modified.mean)
    np.testing.assert_array_equal(base.scale, modified.scale)
    np.testing.assert_array_equal(base.weights, modified.weights)
    assert base.threshold == modified.threshold
    assert base.bias == modified.bias


def test_cli_requires_acknowledgements_without_accessing_private_data():
    with pytest.raises(SystemExit) as exc:
        training.main([
            "--root", "none", "--groups", "none", "--proposals", "none",
            "--pose-model", "none", "--output", "none",
        ])
    assert exc.value.code == 2
