"""Windows owner-session wrapper tests: fake reviewed policies, no camera access."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge.privacy_approval_operator import unsigned_template

WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell owner preview")
REPO = Path(__file__).resolve().parents[3]
OWNER = REPO / "scripts" / "start-hikvision-owner-preview.ps1"


def invoke_owner(approval: Path, tmp_path: Path, *, confirmations=True):
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path)
    environment["VIIL_PRIVACY_APPROVAL_KEY"] = "INHERITED_KEY_SHOULD_NOT_BE_LOGGED"
    args = [
        "powershell.exe", "-NoProfile", "-File", str(OWNER),
        "-CameraIp", "192.168.10.204",
        "-ReviewedUnsignedApproval", str(approval),
        "-SourceId", "staged-camera-01",
        "-VerifyPolicyOnly",
    ]
    if confirmations:
        args.extend(["-ConfirmSiteOwnership", "-ConfirmPrivacyReviewAndNotices"])
    return subprocess.run(
        args, text=True, capture_output=True, check=False,
        timeout=45, env=environment,
    )


def signed_to_reviewed_unsigned(tmp_path, monkeypatch) -> Path:
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("staged-camera-01",))
    body = json.loads(signed.read_text(encoding="utf-8"))
    del body["signature_hmac_sha256"]
    unsigned = tmp_path / "reviewed-owner.json"
    unsigned.write_text(json.dumps(body), encoding="utf-8")
    return unsigned


def assert_no_temporary_approvals(tmp_path):
    root = tmp_path / "VIIL-Sentinel" / "OwnerPreviewSessions"
    assert not root.exists() or not list(root.glob("session-*"))


@WINDOWS
def test_missing_owner_or_notice_attestation_denied_without_camera(tmp_path):
    path = tmp_path / "unsigned.json"
    path.write_text(json.dumps(unsigned_template()), encoding="utf-8")
    result = invoke_owner(path, tmp_path, confirmations=False)
    assert result.returncode == 2
    assert "OWNER_POLICY_VERIFIED_ONLY" not in result.stdout
    assert "rtsp://" not in result.stdout + result.stderr
    assert "INHERITED_KEY_SHOULD_NOT_BE_LOGGED" not in result.stdout + result.stderr
    assert_no_temporary_approvals(tmp_path)


@WINDOWS
def test_signed_owner_session_uses_real_gate_then_cleans_all_secrets(
    tmp_path, monkeypatch,
):
    reviewed = signed_to_reviewed_unsigned(tmp_path, monkeypatch)
    result = invoke_owner(reviewed, tmp_path)
    assert result.returncode == 0, (result.stdout + result.stderr)[-500:]
    assert "OWNER_POLICY_VERIFIED_ONLY" in result.stdout
    assert "camera_opened=false" in result.stdout
    assert "INHERITED_KEY_SHOULD_NOT_BE_LOGGED" not in result.stdout + result.stderr
    assert_no_temporary_approvals(tmp_path)


@WINDOWS
def test_owner_cannot_sign_unreviewed_template_even_with_confirmation(tmp_path):
    draft = tmp_path / "unsigned.json"
    draft.write_text(json.dumps(unsigned_template()), encoding="utf-8")
    result = invoke_owner(draft, tmp_path)
    assert result.returncode == 2
    assert "OWNER_POLICY_VERIFIED_ONLY" not in result.stdout
    assert_no_temporary_approvals(tmp_path)
