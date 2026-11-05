"""Offline competition release gates. Do not assert production readiness."""
import json
from pathlib import Path
from shutil import copyfile

import pytest

from sentinel_edge import submission_readiness as sr


@pytest.fixture
def package(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    for relative in (*sr.APP_FILES, *sr.SHARED_SCHEMAS):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(root / relative, target)
    monkeypatch.setattr(sr, "preflight", lambda _: {
        "network_requests_performed": False,
        "candidate": {
            "synthetic_fall_events": 1, "synthetic_non_fall_events": 0,
        },
    })
    return tmp_path


def test_actual_repository_gate_passes_without_claiming_production_readiness():
    root = Path(__file__).resolve().parents[3]
    result = sr.verify_member1_submission(root)
    assert result["status"] == "member1_offline_artifact_gate_passed"
    assert result["production_ready"] is False
    assert result["real_fall_accuracy_verified"] is False
    assert result["actual_meta_calls"] == 0
    assert result["actual_caregiver_alerts"] == 0
    assert result["offline_demo_scenarios"] == 5
    assert len(result["blocked_on_evidence_or_member2"]) == 6


def test_required_demo_asset_missing_is_fatal(package):
    (package / sr.APP_FILES[0]).unlink()
    with pytest.raises(OSError):
        sr.verify_member1_submission(package)


def test_bad_shared_contract_version_fails(package):
    path = package / "handoff/team/caregiver_inbox.v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["properties"]["schema_version"]["const"] = "v2"
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="contract drifted"):
        sr.verify_member1_submission(package)


def test_caregiver_fall_confirmation_cannot_be_enabled(package):
    path = package / "handoff/team/caregiver_inbox.v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["properties"]["advisories"]["items"]["properties"][
        "fall_confirmed"]["const"] = True
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="Caregiver safety"):
        sr.verify_member1_submission(package)


def test_camera_overview_cannot_allow_unbounded_count(package):
    path = package / "handoff/team/integration_overview.v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["properties"]["cameras"]["maxItems"] = 1000
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="Camera metadata"):
        sr.verify_member1_submission(package)


def test_synthetic_nonfall_regression_fails(package, monkeypatch):
    monkeypatch.setattr(sr, "preflight", lambda _: {
        "network_requests_performed": False,
        "candidate": {
            "synthetic_fall_events": 1, "synthetic_non_fall_events": 1,
        },
    })
    with pytest.raises(ValueError, match="nonfall fixture"):
        sr.verify_member1_submission(package)


def test_network_run_masquerading_as_offline_fails(package, monkeypatch):
    monkeypatch.setattr(sr, "preflight", lambda _: {
        "network_requests_performed": True,
        "candidate": {
            "synthetic_fall_events": 1, "synthetic_non_fall_events": 0,
        },
    })
    with pytest.raises(ValueError, match="network"):
        sr.verify_member1_submission(package)


def test_result_is_small_and_contains_no_personal_or_model_material(package):
    report = sr.verify_member1_submission(package)
    output = json.dumps(report)
    assert len(output) < 2500
    assert "api_key" not in output and "rtsp://" not in output
    assert "weights" not in output and "event_id" not in output
    assert report["scope"] == "demo_source_and_contracts_only"
