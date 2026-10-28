"""Privacy approval must fail closed before touching cameras or model imports."""
from datetime import date, timedelta
import json
import sys

import pytest

from privacy_approval_fixture import make_policy, TEST_KEY
from sentinel_edge.privacy_gate import (
    KEY_ENV, POLICY_SCHEMA, PrivacyGateDenied, sign_policy, verify_privacy_approval,
)
from sentinel_edge import runner


def test_verified_signed_approval_only_for_selected_camera(tmp_path, monkeypatch):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a", "zone-b"),
                           jurisdictions=("TH", "DE"))
    checked = verify_privacy_approval(approval, camera_id="zone-a")
    assert checked["authorization_verified"] is True
    assert checked["jurisdictions"] == ["TH", "DE"]
    assert checked["raw_frame_retention_days"] == 0
    assert checked["lawfulness_or_full_regulatory_compliance_certified"] is False
    assert checked["cross_border_transfers_permitted"] is False
    assert checked["automated_emergency_dispatch_permitted"] is False
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(approval, camera_id="zone-c")


def test_tampered_or_unsigned_document_rejected(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["cloud_transfer_enabled"] = True
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(path, camera_id="staged-camera-01")
    record.pop("signature_hmac_sha256")
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(path, camera_id="staged-camera-01")


@pytest.mark.parametrize("overrides", [
    {"cloud_transfer_enabled": True},
    {"training_reuse_enabled": True},
    {"raw_frame_retention_days": 1},
    {"face_identification_enabled": True},
    {"automatic_emergency_dispatch_enabled": True},
    {"local_only": False},
    {"notices_confirmed": False},
    {"human_review_required": False},
    {"site_authorization_confirmed": False},
    {"jurisdictions": ["th"]},
    {"jurisdictions": ["DE"], "legal_basis_by_jurisdiction": {"TH": "consent"}},
    {"legal_basis_by_jurisdiction": {"TH": "undefined"}},
    {"approved_camera_ids": ["staged-camera-01", "staged-camera-01"]},
    {"purpose": "face_recognition_for_employment"},
])
def test_risky_or_inconsistent_policy_denied_even_with_valid_hmac(
    tmp_path, monkeypatch, overrides,
):
    path = make_policy(tmp_path, monkeypatch, **overrides)
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(path, camera_id="staged-camera-01")


def test_expired_future_or_overlong_approval_denied(tmp_path, monkeypatch):
    current = date.today()
    for overrides in (
        {"expires_on": (current - timedelta(days=1)).isoformat()},
        {"valid_from": (current + timedelta(days=1)).isoformat()},
        {"expires_on": (current + timedelta(days=365)).isoformat()},
    ):
        path = make_policy(tmp_path, monkeypatch, **overrides)
        with pytest.raises(PrivacyGateDenied):
            verify_privacy_approval(path, camera_id="staged-camera-01", today=current)


def test_key_missing_or_wrong_denied(tmp_path, monkeypatch):
    approval = make_policy(tmp_path, monkeypatch)
    monkeypatch.delenv(KEY_ENV)
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(approval, camera_id="staged-camera-01")
    monkeypatch.setenv(KEY_ENV, "DIFFERENT_TEST_KEY" * 3)
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(approval, camera_id="staged-camera-01")


def test_secret_and_policy_content_not_in_denial(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["site_authorization_confirmed"] = "sensitive-user-secret"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(PrivacyGateDenied) as caught:
        verify_privacy_approval(path, camera_id="staged-camera-01")
    assert "sensitive-user-secret" not in str(caught.value)
    assert "test_approval_0001" not in str(caught.value)
    assert str(path) not in str(caught.value)


def test_duplicate_json_keys_refused(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace('"schema_version":',
                                     '"schema_version": "fake", "schema_version":'),
                    encoding="utf-8")
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(path, camera_id="staged-camera-01")


def test_approval_signing_rejects_short_key_and_unknown_fields():
    with pytest.raises(ValueError):
        sign_policy({"schema_version": POLICY_SCHEMA}, b"short")
    with pytest.raises(ValueError):
        sign_policy({"schema_version": POLICY_SCHEMA}, TEST_KEY.encode("utf-8"))


def test_runner_refuses_live_capture_before_importing_cv2(tmp_path, monkeypatch):
    model = tmp_path / "test.task"
    model.write_bytes(b"mock")
    monkeypatch.setitem(sys.modules, "cv2", None)
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    # The missing approval should win over missing video dependencies.
    with pytest.raises(SystemExit, match="signed privacy approval"):
        runner.main(["--source", "usb:0", "--model", str(model)])
    with pytest.raises(SystemExit, match="signed privacy approval"):
        runner.main(["--source", "rtsp", "--rtsp-env", "VIIL_CAM",
                     "--model", str(model), "--candidate-format", "v1",
                     "--confirm-consent"])
    approval = make_policy(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="privacy approval denied"):
        runner.main(["--source", "rtsp", "--rtsp-env", "VIIL_CAM",
                     "--model", str(model), "--candidate-format", "v1",
                     "--confirm-consent", "--source-id", "unlisted",
                     "--privacy-approval", str(approval)])


def test_no_symlinks_and_large_payload(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    path.write_text("x" * 18000, encoding="utf-8")
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(path, camera_id="staged-camera-01")
    # Symlinks are optional on Windows; validate when OS permits.
    actual = make_policy(tmp_path, monkeypatch)
    link = tmp_path / "alias-approval.json"
    try:
        link.symlink_to(actual)
    except OSError:
        return
    with pytest.raises(PrivacyGateDenied):
        verify_privacy_approval(link, camera_id="staged-camera-01")
