"""Offline operator workflow for signed *reviewed* staging camera approvals.

- template: print unsigned, deliberately DENIED-by-default JSON to stdout.
- sign: require two explicit human attestations, an existing key, and a
  reviewed unsigned file; fail closed on semantic or signature validation.
- verify: inspect an existing file using the production camera privacy gate.

No keys are generated, stored, printed, or accepted in CLI arguments. Signing
never substitutes for site permission, consent/notices or legal/privacy review.
"""
from argparse import ArgumentParser
from datetime import date
from getpass import getpass
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from sentinel_edge.privacy_gate import (
    BASIS_CODES, CAMERA_PATTERN, COUNTRY_PATTERN, KEY_ENV, MAX_POLICY_BYTES,
    MAX_VALID_DAYS, POLICY_SCHEMA, REF_PATTERN, REQUIRED_FIELDS,
    PrivacyGateDenied, _no_duplicates, sign_policy, verify_privacy_approval,
)


def unsigned_template(camera_id: str = "staged-camera-01") -> dict:
    """Return an incomplete, non-operational specimen, never an approval."""
    return {
        "schema_version": POLICY_SCHEMA,
        "approval_ref": "REPLACE_APPROVAL_REF",
        "purpose": "consented_staged_fall_candidate_research",
        "jurisdictions": ["TH"],
        "legal_basis_by_jurisdiction": {"TH": "REVIEW_REQUIRED"},
        "controller_ref": "REPLACE_CONTROLLER_REF",
        "notice_ref": "REPLACE_NOTICE_REF",
        "privacy_impact_review_ref": "REPLACE_IMPACT_REVIEW",
        "sensitive_data_review_ref": "REPLACE_SENSITIVE_REVIEW",
        "rights_procedure_ref": "REPLACE_RIGHTS_PROCEDURE",
        "approved_camera_ids": [camera_id],
        "valid_from": "REPLACE_YYYY-MM-DD",
        "expires_on": "REPLACE_YYYY-MM-DD",
        "site_authorization_confirmed": False,
        "notices_confirmed": False,
        "human_review_required": True,
        "local_only": True,
        "raw_frame_retention_days": 0,
        "cloud_transfer_enabled": False,
        "face_identification_enabled": False,
        "training_reuse_enabled": False,
        "automatic_emergency_dispatch_enabled": False,
    }


def inspect_unsigned_draft(unsigned: Path, camera_id: str) -> dict:
    """Offline structural checklist. NEVER claims actual site permission.

    Only publishes field names, not reference values, camera URLs, policy
    contents, individual identities, signing secrets or filesystem paths.
    The authoritative signature/semantic gate remains verify_privacy_approval.
    """
    body = _read_unsigned(unsigned)
    issues = []

    def flag(name: str) -> None:
        issues.append(name)

    if body["schema_version"] != POLICY_SCHEMA:
        flag("schema_version")
    if body["purpose"] != "consented_staged_fall_candidate_research":
        flag("purpose")

    for field in (
        "approval_ref", "controller_ref", "notice_ref",
        "privacy_impact_review_ref", "sensitive_data_review_ref",
        "rights_procedure_ref",
    ):
        value = body[field]
        if (not isinstance(value, str)
                or value.upper().startswith("REPLACE_")
                or REF_PATTERN.fullmatch(value) is None):
            flag(field)

    jurisdictions = body["jurisdictions"]
    valid_jurisdictions = (
        isinstance(jurisdictions, list)
        and 1 <= len(jurisdictions) <= 10
        and all(isinstance(j, str) and COUNTRY_PATTERN.fullmatch(j)
                for j in jurisdictions)
        and len(set(jurisdictions)) == len(jurisdictions)
    ) if isinstance(jurisdictions, list) and all(
        isinstance(j, str) for j in jurisdictions
    ) else False
    if not valid_jurisdictions:
        flag("jurisdictions")
    bases = body["legal_basis_by_jurisdiction"]
    if (not isinstance(bases, dict)
            or not valid_jurisdictions
            or set(bases) != set(jurisdictions)
            or any(type(v) is not str or v not in BASIS_CODES
                   for v in bases.values())):
        flag("legal_basis_by_jurisdiction")

    cameras = body["approved_camera_ids"]
    if (not isinstance(cameras, list)
            or not 1 <= len(cameras) <= 16
            or any(not isinstance(c, str) or
                   CAMERA_PATTERN.fullmatch(c) is None for c in cameras)
            or len(set(cameras)) != len(cameras)
            or camera_id not in cameras):
        flag("approved_camera_ids")

    try:
        start, end = date.fromisoformat(body["valid_from"]), date.fromisoformat(
            body["expires_on"],
        )
        if (end < start or (end - start).days > MAX_VALID_DAYS
                or not start <= date.today() <= end):
            flag("validity_window")
    except (ValueError, TypeError, OverflowError):
        flag("validity_window")

    for field in (
        "site_authorization_confirmed", "notices_confirmed",
        "human_review_required", "local_only",
    ):
        if body[field] is not True:
            flag(field)
    for field in (
        "cloud_transfer_enabled", "face_identification_enabled",
        "training_reuse_enabled", "automatic_emergency_dispatch_enabled",
    ):
        if body[field] is not False:
            flag(field)
    if type(body["raw_frame_retention_days"]) is not int or (
        body["raw_frame_retention_days"] != 0
    ):
        flag("raw_frame_retention_days")

    complete = not issues
    return {
        "type": "viil.camera.unsigned_draft_review.v1",
        "result": "fields_complete_review_still_required" if complete
                  else "draft_fields_incomplete",
        "draft_fields_structurally_complete": complete,
        "issues": issues,
        "genuine_site_permission_confirmed_by_tool": False,
        "independent_legal_compliance_certified": False,
        "signed_policy_verified": False,
        "camera_access_granted": False,
    }


def _key_from_operator() -> str:
    key = os.environ.get(KEY_ENV, "")
    if not key and sys.stdin.isatty():
        key = getpass("Existing authorized privacy signing key (hidden): ")
    if len(key.encode("utf-8")) < 32:
        raise ValueError("Signing/verification key unavailable or too short")
    return key


def _read_unsigned(path: Path) -> dict:
    try:
        repo_root = Path(__file__).resolve().parents[3]
        if path.resolve(strict=False).is_relative_to(repo_root):
            raise ValueError
        if not path.is_file() or path.is_symlink():
            raise ValueError
        if not 0 < path.stat().st_size <= MAX_POLICY_BYTES:
            raise ValueError
        obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
        if not isinstance(obj, dict) or set(obj) != REQUIRED_FIELDS:
            raise ValueError
        return obj
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        raise ValueError("Unsigned policy missing or invalid (redacted)") from None


def _output_is_private_and_new(output: Path) -> bool:
    # The repo and its ancestors are not a private authorization vault.
    repo_root = Path(__file__).resolve().parents[3]
    try:
        target = output.resolve(strict=False)
        return (
            target != repo_root and not target.is_relative_to(repo_root)
            and target.parent.is_dir() and not output.exists()
            and not output.is_symlink()
        )
    except (OSError, RuntimeError, ValueError):
        return False


def _write_new_private_file(output: Path, serialized: str) -> None:
    if not _output_is_private_and_new(output):
        raise ValueError("Output must be a new file outside the repository")
    created = False
    try:
        fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
    except OSError:
        # Only cleanup a file that THIS process exclusively created.
        if created:
            try:
                output.unlink()
            except OSError:
                pass
        raise ValueError("Private output could not be saved (redacted)") from None


def sign_reviewed(
    unsigned: Path, output: Path, *, camera_id: str,
    site_authorized: bool, privacy_reviewed: bool,
) -> None:
    """Sign only an operator-attested, semantically valid approval.

    Checks an ephemeral signed policy using the EXACT production verifier
    before an exclusive-create write outside Git. Neither the ephemeral
    file nor output contains the signing key. No overwrite is possible.
    """
    if site_authorized is not True or privacy_reviewed is not True:
        raise ValueError("Human site authorization and privacy review are required")
    body = _read_unsigned(unsigned)
    # A specimen can otherwise become superficially valid by toggling
    # booleans while leaving reference IDs as unreviewed placeholders.
    reviewed_refs = (
        "approval_ref", "controller_ref", "notice_ref",
        "privacy_impact_review_ref", "sensitive_data_review_ref",
        "rights_procedure_ref",
    )
    if any(not isinstance(body[k], str) or body[k].startswith("REPLACE_")
           for k in reviewed_refs):
        raise ValueError("Unreviewed reference placeholders are not signable")
    key = _key_from_operator()
    try:
        signed = sign_policy(body, key.encode("utf-8"))
        serialized = json.dumps(signed, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        with TemporaryDirectory(prefix="viil-approval-check-") as temporary:
            candidate = Path(temporary) / "candidate.json"
            candidate.write_text(serialized, encoding="utf-8")
            verify_privacy_approval(
                candidate, camera_id=camera_id, environment={KEY_ENV: key},
            )
        _write_new_private_file(output, serialized)
    except (PrivacyGateDenied, ValueError, TypeError, OSError, UnicodeError):
        # Generic errors: never expose contents, secret, or native file path.
        raise ValueError("Approval was not signed or could not be saved (redacted)") from None


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="VIIL authorized camera approval: offline operator tools")
    sub = parser.add_subparsers(dest="command", required=True)
    templ = sub.add_parser("template", help="Print incomplete unsigned specimen (NOT approved)")
    templ.add_argument("--source-id", default="staged-camera-01")
    templ.add_argument("--output", type=Path,
                       help="Create a private unsigned draft outside Git (never overwrite)")
    reviewer = sub.add_parser("review", help="Offline draft field checklist; no approval granted")
    reviewer.add_argument("--unsigned", required=True, type=Path)
    reviewer.add_argument("--source-id", required=True)
    signer = sub.add_parser("sign", help="Operator-only: sign reviewed site approval")
    signer.add_argument("--unsigned", required=True, type=Path)
    signer.add_argument("--output", required=True, type=Path)
    signer.add_argument("--source-id", required=True)
    signer.add_argument("--confirm-site-authorization", action="store_true")
    signer.add_argument("--confirm-privacy-review", action="store_true")
    verify = sub.add_parser("verify", help="Check signed file without accessing camera")
    verify.add_argument("--signed", required=True, type=Path)
    verify.add_argument("--source-id", required=True)
    args = parser.parse_args(argv)

    if args.command == "template":
        draft = json.dumps(unsigned_template(args.source_id), indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(draft, end="")
        else:
            try:
                _write_new_private_file(args.output, draft)
            except ValueError:
                parser.error("Private unsigned draft path unavailable or unsafe (redacted)")
            print(json.dumps({"result": "unsigned_draft_only", "approved": False}))
        return 0
    if args.command == "review":
        try:
            report = inspect_unsigned_draft(args.unsigned, args.source_id)
        except (ValueError, OSError, UnicodeError):
            parser.error("Unsigned draft missing or unsafe (redacted)")
        print(json.dumps(report, sort_keys=True))
        return 0 if report["draft_fields_structurally_complete"] else 2
    try:
        if args.command == "sign":
            sign_reviewed(
                args.unsigned, args.output, camera_id=args.source_id,
                site_authorized=args.confirm_site_authorization,
                privacy_reviewed=args.confirm_privacy_review,
            )
            report = {
                "result": "signed_reviewed_policy_written",
                "cryptographic_and_policy_checks_passed": True,
                "independent_legal_compliance_certified": False,
            }
        else:
            key = _key_from_operator()
            verify_privacy_approval(
                args.signed, camera_id=args.source_id,
                environment={KEY_ENV: key},
            )
            report = {
                "result": "existing_signature_and_policy_verified",
                "cryptographic_and_policy_checks_passed": True,
                "independent_legal_compliance_certified": False,
            }
    except (ValueError, PrivacyGateDenied, OSError, UnicodeError):
        parser.error("Privacy approval missing, unreviewed, invalid, or unsafe (redacted)")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
