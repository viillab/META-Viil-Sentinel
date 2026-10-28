"""Opt-in portable SHORT research model checks; synthetic tensors only."""
from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pytest

from sentinel_edge import causal_1500ms_artifact as artifact
from sentinel_edge import private_model_training as old
from sentinel_edge import window_export
from sentinel_edge.causal_1500ms_shadow import Causal1500msModelShadow
from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate


def sample_model():
    manifest, windows = synthetic_demo()
    return train_and_evaluate(manifest, windows)[0]


def private(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    private_root = root / "data" / "private"
    private_root.mkdir(parents=True)
    pkg = root / "services" / "edge-vision" / "sentinel_edge"
    monkeypatch.setattr(artifact, "__file__", str(pkg / "causal_1500ms_artifact.py"))
    monkeypatch.setattr(window_export, "__file__", str(pkg / "window_export.py"))
    monkeypatch.setattr(old, "__file__", str(pkg / "private_model_training.py"))
    groups, proposals = (private_root / "groups.json", private_root / "proposals.json")
    groups.write_text('{"version":2,"synthetic":true}', encoding="utf8")
    proposals.write_text('{"version":1,"synthetic":true}', encoding="utf8")
    return private_root, groups, proposals


def checked(model=None):
    return artifact.checked_causal_artifact(
        model or sample_model(), manifest_digest="a" * 64,
        proposal_digest="b" * 64, dataset="all-synthetic",
    )


def test_exact_short_contract_is_not_eight_second_artifact():
    item = checked()
    assert item["temporal_context_ms"] == 1500
    assert item["sample_slots"] == 30
    assert item["shadow_hop_ms"] == 250
    assert item["format"] == artifact.ARTIFACT_FORMAT
    assert "1500ms" in item["architecture"]
    assert item["model_deployed"] is False
    assert item["automated_fall_alerting_authorized"] is False
    assert item["real_world_accuracy_established"] is False
    assert item["independent_human_label_review"] is False
    assert len(item["mean"]) == 30
    assert not any(k in item for k in (
        "source_id", "subject_id", "video", "landmarks", "clip_id", "features"
    ))


def test_private_exclusive_save_reload_bitwise_and_real_shadow_adapter(tmp_path, monkeypatch):
    root, groups, proposals = private(tmp_path, monkeypatch)
    model = sample_model()
    out = root / "test_causal.json"
    result = artifact.save_causal_artifact(
        model, out, groups_path=groups, proposals_path=proposals, dataset="synthetic",
    )
    assert result["readback_verified"]
    assert result["model_parameters_bytes_in_ram"] == 736
    assert result["artifact_size_bytes"] == out.stat().st_size
    assert result["artifact_size_bytes"] < 5000
    assert result["artifact_stored_only_in_gitignored_private"]
    loaded = artifact.read_causal_artifact(out)
    np.testing.assert_array_equal(loaded.linear.weights, model.weights)
    np.testing.assert_array_equal(loaded.linear.mean, model.mean)
    np.testing.assert_array_equal(loaded.linear.scale, model.scale)
    scores = np.random.default_rng(1).normal(size=(14, 30))
    scores[0, 0] = 1e6
    np.testing.assert_array_equal(
        loaded.predict_probability(scores), model.predict_probability(scores)
    )
    shadow = Causal1500msModelShadow(loaded)
    assert shadow.summary()["scored_windows"] == 0
    with pytest.raises(ValueError, match="already exist|private"):
        artifact.save_causal_artifact(
            model, out, groups_path=groups, proposals_path=proposals, dataset="synthetic",
        )
    # Must NOT be loadable as the old 8-second model.
    with pytest.raises(ValueError):
        old.read_private_artifact(out)


@pytest.mark.parametrize("mutation", [
    {"format": "viil.edge.causal_8000ms.linear_research.v1"},
    {"architecture": old.ARCHITECTURE},
    {"temporal_context_ms": 8000},
    {"temporal_context_ms": True},
    {"sample_slots": 40},
    {"shadow_hop_ms": False},
    {"version": True},
    {"version": 999},
    {"inference_preprocessing": "unbounded"},
    {"model_deployed": True},
    {"model_deployed": 0},
    {"publisher_labels_only": 1},
    {"automated_fall_alerting_authorized": 0},
    {"automated_fall_alerting_authorized": True},
    {"independent_human_label_review": True},
    {"real_world_accuracy_established": True},
    {"research_only_usage": "emergency"},
    {"mean": [0.0] * 29},
    {"scale": [0.0] * 30},
    {"weights": [float("nan")] * 30},
    {"source_manifest_sha256": "short"},
    {"person_id": "fake-private-person"},
])
def test_corrupt_or_misrepresented_short_model_rejected(tmp_path, monkeypatch, mutation):
    root, _, _ = private(tmp_path, monkeypatch)
    item = checked()
    item.update(deepcopy(mutation))
    out = root / "mutated.json"
    out.write_text(json.dumps(item), encoding="utf8")
    with pytest.raises((ValueError, TypeError)):
        artifact.read_causal_artifact(out)


def test_wrong_directory_or_symlink_escape_refused(tmp_path, monkeypatch):
    private(tmp_path, monkeypatch)
    outside = tmp_path / "public.json"
    outside.write_text(json.dumps(checked()), encoding="utf8")
    with pytest.raises(ValueError, match="private"):
        artifact.read_causal_artifact(outside)


def test_duplicate_keys_and_json_nan_refused(tmp_path, monkeypatch):
    root, _, _ = private(tmp_path, monkeypatch)
    blob = json.dumps(checked())
    path = root / "duplicate.json"
    path.write_text(blob[:-1] + ', "version": 2}', encoding="utf8")
    with pytest.raises(ValueError, match="Duplicate"):
        artifact.read_causal_artifact(path)
    path.write_text(blob.replace("0.0", "NaN", 1), encoding="utf8")
    with pytest.raises(ValueError, match="Nonfinite"):
        artifact.read_causal_artifact(path)


def test_invalid_preflight_and_private_export_arguments(tmp_path, monkeypatch):
    root, groups, proposals = private(tmp_path, monkeypatch)
    outside = tmp_path / "outside_model.json"
    with pytest.raises(ValueError, match="private"):
        artifact.save_causal_artifact(
            sample_model(), outside, groups_path=groups,
            proposals_path=proposals, dataset="synthetic",
        )
    assert not outside.exists()
    with pytest.raises((OSError, ValueError)):
        artifact.save_causal_artifact(
            sample_model(), root / "model.json",
            groups_path=tmp_path / "not_an_existing_source.json",
            proposals_path=proposals, dataset="synthetic",
        )


def test_source_digests_are_bytes_exact(tmp_path, monkeypatch):
    root, groups, proposals = private(tmp_path, monkeypatch)
    path = root / "model.json"
    artifact.save_causal_artifact(
        sample_model(), path, groups_path=groups,
        proposals_path=proposals, dataset="synthetic",
    )
    item = json.loads(path.read_text())
    assert item["source_manifest_sha256"] == sha256(groups.read_bytes()).hexdigest()
    assert item["source_proposals_sha256"] == sha256(proposals.read_bytes()).hexdigest()
