"""Synthetic test-only signer. Never reuse this static key for deployments."""
from datetime import date, timedelta
import json

from sentinel_edge.privacy_gate import KEY_ENV, POLICY_SCHEMA, sign_policy

TEST_KEY = "synthetic-only-key-not-for-real-use-1234567890"


def make_policy(
    tmp_path, monkeypatch, camera_ids=("staged-camera-01",),
    jurisdictions=("TH",), **overrides,
):
    monkeypatch.setenv(KEY_ENV, TEST_KEY)
    today = date.today()
    body = {
        "schema_version": POLICY_SCHEMA,
        "approval_ref": "test_approval_0001",
        "purpose": "consented_staged_fall_candidate_research",
        "jurisdictions": list(jurisdictions),
        "legal_basis_by_jurisdiction": {j: "consent" for j in jurisdictions},
        "controller_ref": "test_controller_0001",
        "notice_ref": "test_notice_0001",
        "privacy_impact_review_ref": "test_dpia_0001",
        "sensitive_data_review_ref": "test_sensitive_0001",
        "rights_procedure_ref": "test_rights_0001",
        "approved_camera_ids": list(camera_ids),
        "valid_from": (today - timedelta(days=1)).isoformat(),
        "expires_on": (today + timedelta(days=2)).isoformat(),
        "site_authorization_confirmed": True,
        "notices_confirmed": True,
        "human_review_required": True,
        "local_only": True,
        "raw_frame_retention_days": 0,
        "cloud_transfer_enabled": False,
        "face_identification_enabled": False,
        "training_reuse_enabled": False,
        "automatic_emergency_dispatch_enabled": False,
    }
    body.update(overrides)
    signed = sign_policy(body, TEST_KEY.encode("utf-8"))
    path = tmp_path / "test-approval.json"
    path.write_text(json.dumps(signed), encoding="utf-8")
    return path
