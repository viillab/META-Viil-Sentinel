"""Offline privacy-approval operator workflow; synthetic policies ONLY in tests."""
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from privacy_approval_fixture import make_policy, TEST_KEY
from sentinel_edge import privacy_approval_operator as operator
from sentinel_edge.privacy_gate import PrivacyGateDenied, verify_privacy_approval


def unsigned_from_fixture(tmp_path, monkeypatch, **overrides):
    signed_path = make_policy(
        tmp_path, monkeypatch, camera_ids=("staged-camera-01",), **overrides,
    )
    unsigned = json.loads(signed_path.read_text(encoding="utf-8"))
    del unsigned["signature_hmac_sha256"]
    draft = tmp_path / "reviewed-unsigned.json"
    draft.write_text(json.dumps(unsigned), encoding="utf-8")
    return draft


def args_for_sign(draft: Path, out: Path):
    return [
        "sign", "--unsigned", str(draft), "--output", str(out),
        "--source-id", "staged-camera-01",
        "--confirm-site-authorization", "--confirm-privacy-review",
    ]


def test_template_defaults_denied_and_does_not_contain_signature(capsys):
    assert operator.main(["template", "--source-id", "zone-a"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["approved_camera_ids"] == ["zone-a"]
    assert doc["site_authorization_confirmed"] is False
    assert doc["notices_confirmed"] is False
    assert doc["legal_basis_by_jurisdiction"] == {"TH": "REVIEW_REQUIRED"}
    assert "signature_hmac_sha256" not in doc


def test_template_can_write_private_new_draft_without_approval(tmp_path, capsys):
    path = tmp_path / "new-draft.json"
    assert operator.main(["template", "--output", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["approved"] is False
    assert path.is_file()
    assert json.loads(path.read_text())["site_authorization_confirmed"] is False
    with pytest.raises(SystemExit):
        operator.main(["template", "--output", str(path)])


def test_review_of_default_unsigned_draft_reports_missing_fields(
    tmp_path, capsys,
):
    draft = tmp_path / "draft.json"
    assert operator.main(["template", "--output", str(draft)]) == 0
    capsys.readouterr()
    assert operator.main([
        "review", "--unsigned", str(draft), "--source-id", "staged-camera-01",
    ]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "draft_fields_incomplete"
    assert "site_authorization_confirmed" in result["issues"]
    assert "notices_confirmed" in result["issues"]
    assert "legal_basis_by_jurisdiction" in result["issues"]
    assert "validity_window" in result["issues"]
    assert result["camera_access_granted"] is False
    assert result["signed_policy_verified"] is False


def test_review_of_structurally_complete_draft_does_not_grant_permission(
    tmp_path, monkeypatch, capsys,
):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    assert operator.main([
        "review", "--unsigned", str(draft), "--source-id", "staged-camera-01",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["draft_fields_structurally_complete"] is True
    assert report["issues"] == []
    assert report["genuine_site_permission_confirmed_by_tool"] is False
    assert report["camera_access_granted"] is False
    assert report["signed_policy_verified"] is False
    assert TEST_KEY not in json.dumps(report)


@pytest.mark.parametrize("changes,fields", [
    ({"approved_camera_ids": ["other-cam"]}, ["approved_camera_ids"]),
    ({"approved_camera_ids": [{}]}, ["approved_camera_ids"]),
    ({"jurisdictions": ["th"]}, ["jurisdictions", "legal_basis_by_jurisdiction"]),
    ({"jurisdictions": [["TH"]]}, ["jurisdictions", "legal_basis_by_jurisdiction"]),
    ({"legal_basis_by_jurisdiction": {"TH": "REVIEW_REQUIRED"}}, ["legal_basis_by_jurisdiction"]),
    ({"cloud_transfer_enabled": True}, ["cloud_transfer_enabled"]),
    ({"expires_on": "2035-10-01"}, ["validity_window"]),
    ({"notice_ref": "REPLACE_NOTICE_REF"}, ["notice_ref"]),
])
def test_review_reports_only_field_codes_for_invalid_draft(
    tmp_path, monkeypatch, capsys, changes, fields,
):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    content = json.loads(draft.read_text(encoding="utf-8"))
    content.update(changes)
    draft.write_text(json.dumps(content), encoding="utf-8")
    assert operator.main([
        "review", "--unsigned", str(draft), "--source-id", "staged-camera-01",
    ]) == 2
    report = json.loads(capsys.readouterr().out)
    for field in fields:
        assert field in report["issues"]
    assert "staged-camera-01" not in json.dumps(report)
    assert report["camera_access_granted"] is False


def test_review_rejects_unsigned_file_inside_repo_and_bad_json(
    tmp_path, monkeypatch,
):
    outside = tmp_path / "draft.json"
    outside.write_text('{"dup":1,"dup":2}', encoding="utf-8")
    with pytest.raises(SystemExit):
        operator.main([
            "review", "--unsigned", str(outside), "--source-id", "zone-a",
        ])
    repo_root = Path(__file__).resolve().parents[3]
    with pytest.raises(SystemExit):
        operator.main([
            "review", "--unsigned", str(repo_root / "AGENTS.md"),
            "--source-id", "zone-a",
        ])


def test_explicit_attestation_required_before_signing(tmp_path, monkeypatch):
    unsigned = unsigned_from_fixture(tmp_path, monkeypatch)
    out = tmp_path / "signed.json"
    with pytest.raises(SystemExit):
        operator.main([
            "sign", "--unsigned", str(unsigned), "--output", str(out),
            "--source-id", "staged-camera-01",
        ])
    assert not out.exists()


def test_existing_signing_key_and_reviewer_attestations_work_offline(
    tmp_path, monkeypatch, capsys,
):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    out = tmp_path / "approved-privacy.json"
    assert operator.main(args_for_sign(draft, out)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["cryptographic_and_policy_checks_passed"]
    assert not summary["independent_legal_compliance_certified"]
    content = out.read_text(encoding="utf-8")
    assert "signature_hmac_sha256" in content
    assert TEST_KEY not in content
    assert verify_privacy_approval(out, camera_id="staged-camera-01")[
        "authorization_verified"
    ]
    assert operator.main([
        "verify", "--signed", str(out), "--source-id", "staged-camera-01",
    ]) == 0
    assert "key" not in capsys.readouterr().out.lower()
    # No overwrites of existing signed approvals.
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, out))
    assert out.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("changes", [
    {"site_authorization_confirmed": False},
    {"notices_confirmed": False},
    {"cloud_transfer_enabled": True},
    {"raw_frame_retention_days": 1},
    {"legal_basis_by_jurisdiction": {"TH": "REVIEW_REQUIRED"}},
    {"valid_from": "2035-01-01", "expires_on": "2035-01-07"},
    {"expires_on": (date.today() + timedelta(days=100)).isoformat()},
])
def test_sign_rejects_false_or_unreviewed_legal_claims(
    tmp_path, monkeypatch, changes,
):
    draft = unsigned_from_fixture(tmp_path, monkeypatch, **changes)
    output = tmp_path / "signed.json"
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, output))
    assert not output.exists()


def test_placeholder_references_cannot_be_silently_signed(tmp_path, monkeypatch):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    body = json.loads(draft.read_text(encoding="utf-8"))
    body["notice_ref"] = "REPLACE_NOTICE_REF"
    draft.write_text(json.dumps(body), encoding="utf-8")
    out = tmp_path / "signed.json"
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, out))
    assert not out.exists()


def test_template_is_not_signable_even_with_human_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("VIIL_PRIVACY_APPROVAL_KEY", TEST_KEY)
    draft = tmp_path / "draft.json"
    operator.main(["template", "--output", str(draft)])
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, tmp_path / "signed.json"))
    assert not (tmp_path / "signed.json").exists()


def test_input_duplicate_keys_denied_before_signing(tmp_path, monkeypatch):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    content = draft.read_text(encoding="utf-8")
    draft.write_text(
        content.replace('"schema_version":', '"schema_version":"spoof","schema_version":'),
        encoding="utf-8",
    )
    out = tmp_path / "signed.json"
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, out))
    assert not out.exists()


def test_wrong_camera_scope_refuses_to_issue_approval(tmp_path, monkeypatch):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    out = tmp_path / "signed.json"
    args = args_for_sign(draft, out)
    args[args.index("--source-id") + 1] = "not-approved"
    with pytest.raises(SystemExit):
        operator.main(args)
    assert not out.exists()


def test_invalid_verification_key_refuses_signing(tmp_path, monkeypatch, capsys):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("VIIL_PRIVACY_APPROVAL_KEY", "invalid-too-short")
    out = tmp_path / "signed.json"
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, out))
    assert not out.exists()
    assert "invalid-too-short" not in capsys.readouterr().err


def test_operator_never_writes_signed_file_inside_repository(
    tmp_path, monkeypatch,
):
    draft = unsigned_from_fixture(tmp_path, monkeypatch)
    repo_root = Path(__file__).resolve().parents[3]
    risky_path = repo_root / "approved-privacy-DO-NOT-WRITE.json"
    with pytest.raises(SystemExit):
        operator.main(args_for_sign(draft, risky_path))
    assert not risky_path.exists()
    with pytest.raises(SystemExit):
        operator.main(["template", "--output", str(risky_path)])
    assert not risky_path.exists()


def test_verify_invalid_signature_does_not_touch_network_or_camera(
    tmp_path, monkeypatch, capsys,
):
    unsigned = unsigned_from_fixture(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        operator.main(["verify", "--signed", str(unsigned),
                       "--source-id", "staged-camera-01"])
    assert "key" not in capsys.readouterr().err.lower()


def test_signer_can_be_imported_without_pyav_opencv_or_mediapipe():
    assert callable(operator.sign_reviewed)
    assert callable(operator.unsigned_template)
    assert PrivacyGateDenied.__name__ == "PrivacyGateDenied"
