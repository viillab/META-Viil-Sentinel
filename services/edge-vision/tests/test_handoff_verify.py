"""Synthetic, offline-only Member 1 bundle download verification tests."""
from hashlib import sha256
import json

import pytest

from sentinel_edge import causal_1500ms_artifact as artifact
from sentinel_edge import handoff_verify as verifier
from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    pkg = repo / "services" / "edge-vision" / "sentinel_edge"
    private = repo / "data" / "private"
    models = repo / "models"
    private.mkdir(parents=True)
    models.mkdir(parents=True)
    monkeypatch.setattr(verifier, "__file__", str(pkg / "handoff_verify.py"))
    monkeypatch.setattr(artifact, "__file__", str(pkg / "causal_1500ms_artifact.py"))
    manifest, windows = synthetic_demo()
    fitted, _ = train_and_evaluate(manifest, windows)
    content = artifact.checked_causal_artifact(
        fitted, manifest_digest="a" * 64, proposal_digest="b" * 64,
        dataset="synthetic-only",
    )
    classifier = private / "synthetic-model.json"
    classifier.write_text(json.dumps(content, separators=(",", ":")), encoding="utf-8")
    task = models / "synthetic-pose.task"
    task.write_bytes(b"offline-fake-pose-task")
    monkeypatch.setattr(verifier, "CLASSIFIER_FILE_BYTES", classifier.stat().st_size)
    monkeypatch.setattr(verifier, "CLASSIFIER_SHA256", sha256(classifier.read_bytes()).hexdigest())
    monkeypatch.setattr(verifier, "POSE_FILE_BYTES", task.stat().st_size)
    monkeypatch.setattr(verifier, "POSE_SHA256", sha256(task.read_bytes()).hexdigest())
    return classifier, task


def test_exact_synthetic_bundle_accepted_and_private_data_not_exported(bundle):
    classifier, task = bundle
    state = verifier.verify_handoff_bundle(classifier=classifier, pose_task=task)
    assert state["validation"] == "passed_offline_sha256_and_model_contract"
    assert state["model_files_checked"] == 2
    assert state["linear_numeric_parameters_bytes"] == 736
    assert state["context_ms"] == 1500 and state["shadow_hop_ms"] == 250
    assert state["model_deployed"] is False
    assert state["live_fall_detection_authorized"] is False
    assert state["alert_or_network_action_performed"] is False
    exported = json.dumps(state)
    assert str(classifier) not in exported
    assert str(task) not in exported
    assert '"weights"' not in exported
    assert '"mean"' not in exported
    assert "synthetic-only" not in exported


@pytest.mark.parametrize("which", ["classifier", "task"])
def test_tampered_files_rejected_even_if_original_size_remains(bundle, which):
    classifier, task = bundle
    path = classifier if which == "classifier" else task
    raw = bytearray(path.read_bytes())
    raw[-1] = (raw[-1] + 1) % 256
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verifier.verify_handoff_bundle(classifier=classifier, pose_task=task)


@pytest.mark.parametrize("which", ["classifier", "task"])
def test_file_size_mismatch_abstains_before_parsing(bundle, which):
    classifier, task = bundle
    path = classifier if which == "classifier" else task
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(ValueError, match="file size"):
        verifier.verify_handoff_bundle(classifier=classifier, pose_task=task)


def test_pose_extension_must_match(bundle):
    classifier, task = bundle
    renamed = task.with_suffix(".json")
    renamed.write_bytes(task.read_bytes())
    with pytest.raises(ValueError, match=".task"):
        verifier.verify_handoff_bundle(classifier=classifier, pose_task=renamed)


def test_escape_from_private_directory_refused(bundle):
    classifier, task = bundle
    outside = task.with_suffix(".json")
    outside.write_bytes(classifier.read_bytes())
    with pytest.raises(ValueError, match="data/private"):
        verifier.verify_handoff_bundle(classifier=outside, pose_task=task)


def test_old_eight_second_artifact_fails_to_load_even_if_rehashed(bundle, monkeypatch):
    classifier, task = bundle
    altered = json.loads(classifier.read_text())
    altered["temporal_context_ms"] = 8000
    classifier.write_text(json.dumps(altered, separators=(",", ":")), encoding="utf-8")
    monkeypatch.setattr(verifier, "CLASSIFIER_FILE_BYTES", classifier.stat().st_size)
    monkeypatch.setattr(
        verifier, "CLASSIFIER_SHA256", sha256(classifier.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="1500ms"):
        verifier.verify_handoff_bundle(classifier=classifier, pose_task=task)


def test_command_prints_safe_aggregate_json_and_exits_cleanly(bundle, capsys):
    classifier, task = bundle
    assert verifier.main(["--classifier", str(classifier),
                          "--pose-task", str(task)]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["model_files_checked"] == 2
    assert result["not_an_accuracy_or_latency_benchmark"]
    assert "weights" not in output and str(classifier) not in output


def test_missing_file_is_refused(bundle):
    classifier, task = bundle
    with pytest.raises(OSError):
        verifier.verify_handoff_bundle(classifier=classifier.parent / "missing.json",
                                       pose_task=task)


def test_hard_pinned_original_model_hashes_are_documented():
    assert verifier.POSE_FILE_BYTES == 5_777_746
    assert verifier.CLASSIFIER_FILE_BYTES == 2_654
    assert verifier.POSE_SHA256 == (
        "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
    )
    assert verifier.CLASSIFIER_SHA256 == (
        "2faad54ea929f9f44ed8e1bfb733c59d907cb4516fe3979cc4b5f551697f3abb"
    )
