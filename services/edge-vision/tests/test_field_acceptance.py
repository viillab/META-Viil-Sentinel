"""Adversarial, offline-only Member 1 competition acceptance gates."""
import json
from pathlib import Path

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge.field_acceptance import (
    check_camera_config, check_ui_contracts, field_acceptance, main,
)
from sentinel_edge.privacy_gate import PrivacyGateDenied


REPO = Path(__file__).resolve().parents[3]


def test_real_checkout_offline_handoff_remains_explicitly_not_production_ready():
    result = field_acceptance(REPO)
    assert result["developer_contract_preflight_passed"] is True
    assert result["synthetic_fall_candidate_count"] == 1
    assert result["synthetic_sitting_candidate_count"] == 0
    assert len(result["member2_ui_contract_versions"]) == 2
    for field in (
        "live_camera_validated", "fall_accuracy_proven", "real_meta_calls_performed",
        "real_notifications_sent", "legal_compliance_certified",
        "production_or_clinical_use_authorized", "network_requests_performed",
    ):
        assert result[field] is False
    assert len(result["unresolved_field_blockers"]) >= 8
    serialized = json.dumps(result)
    assert "rtsp://" not in serialized
    assert "event_id" not in serialized
    assert "api_key" not in serialized
    assert "evidence_frame" not in serialized


def test_cli_emits_one_json_line_no_secret_or_device(tmp_path, capsys):
    assert main([]) == 0
    payload = capsys.readouterr().out
    assert len(payload.splitlines()) == 1
    assert json.loads(payload)["camera_configuration"]["camera_opened"] is False
    assert "C:\\PrivateConfig" not in payload


def make_registry(tmp_path, *rows):
    path = tmp_path / "cameras.json"
    path.write_text(json.dumps({
        "schema_version": "viil.edge.camera_registry.v1", "cameras": list(rows),
    }), encoding="utf-8")
    return path


def test_authorized_usb_config_checks_without_touching_device(tmp_path, monkeypatch):
    reg = make_registry(tmp_path,
        {"id": "zone-a", "kind": "usb", "device_index": 0},
        {"id": "zone-b", "kind": "usb", "device_index": 1})
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a", "zone-b"))
    report = field_acceptance(REPO, camera_registry=reg,
                              camera_ids=["zone-b", "zone-a"], privacy_approval=policy)
    assert report["camera_configuration"] == {
        "status": "passed_config_only_not_live_capture",
        "number_of_selected_cameras": 2,
        "rtsp_count": 0,
        "usb_count": 2,
        "camera_opened": False,
        "network_requests_performed": False,
    }
    assert report["live_camera_validated"] is False


def test_authorized_private_ip_rtsp_and_url_never_reported(tmp_path, monkeypatch):
    reg = make_registry(tmp_path, {"id": "hall", "kind": "rtsp", "rtsp_env": "VIIL_CAM_HALL"})
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("hall",))
    secret = "rtsp://admin:super-secret-password@192.168.0.12:554/staged"
    monkeypatch.setenv("VIIL_CAM_HALL", secret)
    report = check_camera_config(reg, policy, ["hall"])
    serialized = json.dumps(report)
    assert report["rtsp_count"] == 1
    assert "super-secret" not in serialized
    assert "192.168.0.12" not in serialized
    assert "hall" not in serialized


def test_revoked_or_missing_signed_policy_fails_closed(tmp_path, monkeypatch):
    reg = make_registry(tmp_path, {"id": "zone-a", "kind": "usb", "device_index": 0})
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    tampered = json.loads(policy.read_text("utf-8"))
    tampered["notices_confirmed"] = False
    policy.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(PrivacyGateDenied, match="redacted"):
        check_camera_config(reg, policy, ["zone-a"])


@pytest.mark.parametrize("selected", [[], ["unknown"], ["zone-a", "zone-a"],
                                          ["zone-a"] * 5])
def test_invalid_camera_selection_denied(tmp_path, monkeypatch, selected):
    reg = make_registry(tmp_path, {"id": "zone-a", "kind": "usb", "device_index": 0})
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    with pytest.raises((ValueError, PrivacyGateDenied)):
        check_camera_config(reg, policy, selected)


@pytest.mark.parametrize("args", [
    {"camera_ids": ["zone-a"]},
    {"camera_registry": Path("missing.json")},
    {"privacy_approval": Path("missing.json")},
])
def test_partial_live_config_denied(args):
    with pytest.raises(ValueError):
        field_acceptance(REPO, **args)


def test_frontend_handoff_schema_drift_denied(tmp_path):
    # Unit test only the UI schema gate by copying minimum declared fixtures.
    for rel, version, count, name in (
        ("handoff/team/integration_overview.v1.schema.json",
         "viil.backend.integration_overview.v1", 16, "cameras"),
        ("handoff/team/caregiver_inbox.v1.schema.json",
         "viil.backend.caregiver_inbox.v1", 30, "advisories"),
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema_version": {"const": version},
                name: {"type": "array", "maxItems": count,
                       "items": {"type": "object", "additionalProperties": False}},
            }, "required": ["schema_version", name],
        }), encoding="utf-8")
    assert len(check_ui_contracts(tmp_path)) == 2
    p = tmp_path / "handoff/team/caregiver_inbox.v1.schema.json"
    data = json.loads(p.read_text("utf-8"))
    data["properties"]["advisories"]["maxItems"] = 9999
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="drift"):
        check_ui_contracts(tmp_path)


def test_malformed_configuration_and_missing_key_refused_without_camera_open(
    tmp_path, monkeypatch, capsys,
):
    reg = make_registry(tmp_path, {"id": "zone-a", "kind": "usb", "device_index": 0})
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    monkeypatch.delenv("VIIL_PRIVACY_APPROVAL_KEY")
    with pytest.raises(SystemExit) as error:
        main(["--camera-registry", str(reg), "--camera-id", "zone-a",
              "--privacy-approval", str(policy)])
    assert error.value.code != 0
    captured = capsys.readouterr()
    assert "redacted" in captured.err
    assert str(reg) not in captured.err
    assert str(policy) not in captured.err
