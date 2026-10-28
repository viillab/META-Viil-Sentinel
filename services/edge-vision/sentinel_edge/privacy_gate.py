"""Fail-closed, signed *operator authorization* gate for live camera research.

This is a technical control and tamper-evidence, NOT proof of legal compliance.
Only permits local staged processing of explicitly approved source IDs.
Jurisdiction-specific legal determinations, DPIAs and data-subject rights
remain the responsibility of accountable humans and authorities.
"""
from datetime import date
import hashlib
import hmac
import json
import os
from pathlib import Path
import re

POLICY_SCHEMA = "viil.edge.privacy_approval.v1"
KEY_ENV = "VIIL_PRIVACY_APPROVAL_KEY"
MAX_POLICY_BYTES = 16_384
MAX_VALID_DAYS = 90
REF_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{3,79}$", re.ASCII)
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$", re.ASCII)
CAMERA_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$", re.ASCII)
BASIS_CODES = frozenset({
    "consent", "legitimate_interest", "public_task", "legal_obligation",
    "vital_interests", "contract",
})
REQUIRED_FIELDS = frozenset({
    "schema_version", "approval_ref", "purpose", "jurisdictions",
    "legal_basis_by_jurisdiction", "controller_ref", "notice_ref",
    "privacy_impact_review_ref", "sensitive_data_review_ref",
    "rights_procedure_ref", "approved_camera_ids", "valid_from", "expires_on",
    "site_authorization_confirmed", "notices_confirmed",
    "human_review_required", "local_only", "raw_frame_retention_days",
    "cloud_transfer_enabled", "face_identification_enabled",
    "training_reuse_enabled", "automatic_emergency_dispatch_enabled",
})
POLICY_FIELDS = REQUIRED_FIELDS | {"signature_hmac_sha256"}


class PrivacyGateDenied(ValueError):
    """Generic, deliberately content-free failure for all denied processing."""


def _deny() -> None:
    raise PrivacyGateDenied("Live camera privacy approval missing, expired or invalid (redacted)")


def _no_duplicates(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = val
    return result


def _body_bytes(policy: dict) -> bytes:
    return json.dumps(policy, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sign_policy(policy: dict, secret: bytes) -> dict:
    """Explicit authorized offline signer helper; never logs or stores the key."""
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Reviewer signing secret must be at least 32 bytes")
    if not isinstance(policy, dict) or set(policy) != REQUIRED_FIELDS:
        raise ValueError("Unsigned policy has invalid fields")
    signed = dict(policy)
    signed["signature_hmac_sha256"] = hmac.new(
        secret, _body_bytes(policy), hashlib.sha256,
    ).hexdigest()
    return signed


def verify_privacy_approval(
    path: Path, *, camera_id: str, today: date | None = None,
    environment: dict[str, str] | None = None,
) -> dict:
    """Validate operator authorization BEFORE opening any live capture.

    Caller must choose an authorized camera_id; no media or secrets are
    retained. Returned summary contains only non-identifying references.
    """
    try:
        if (not path.is_file() or path.is_symlink()
                or not 0 < path.stat().st_size <= MAX_POLICY_BYTES):
            _deny()
        raw = path.read_text(encoding="utf-8")
        policy = json.loads(raw, object_pairs_hook=_no_duplicates,
                            parse_constant=lambda _: _deny())
        if not isinstance(policy, dict) or set(policy) != POLICY_FIELDS:
            _deny()
        secret_str = (os.environ if environment is None else environment).get(KEY_ENV)
        if (not isinstance(secret_str, str)
                or len(secret_str.encode("utf-8")) < 32):
            _deny()
        secret = secret_str.encode("utf-8")
        signature = policy["signature_hmac_sha256"]
        if (not isinstance(signature, str) or len(signature) != 64
                or not re.fullmatch(r"[0-9a-f]{64}", signature)):
            _deny()
        body = {name: policy[name] for name in REQUIRED_FIELDS}
        correct = hmac.new(secret, _body_bytes(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, correct):
            _deny()
        if policy["schema_version"] != POLICY_SCHEMA:
            _deny()
        refs = ("approval_ref", "controller_ref", "notice_ref",
                "privacy_impact_review_ref", "sensitive_data_review_ref",
                "rights_procedure_ref")
        if any(not isinstance(policy[k], str) or
               REF_PATTERN.fullmatch(policy[k]) is None for k in refs):
            _deny()
        if policy["purpose"] != "consented_staged_fall_candidate_research":
            _deny()
        jurisdictions = policy["jurisdictions"]
        if (not isinstance(jurisdictions, list)
                or not 1 <= len(jurisdictions) <= 10
                or any(not isinstance(j, str) or
                       COUNTRY_PATTERN.fullmatch(j) is None for j in jurisdictions)
                or len(set(jurisdictions)) != len(jurisdictions)):
            _deny()
        legal_bases = policy["legal_basis_by_jurisdiction"]
        if (not isinstance(legal_bases, dict)
                or set(legal_bases) != set(jurisdictions)
                or any(type(v) is not str or v not in BASIS_CODES
                       for v in legal_bases.values())):
            _deny()
        cameras = policy["approved_camera_ids"]
        if (not isinstance(cameras, list) or not 1 <= len(cameras) <= 16
                or any(not isinstance(c, str) or
                       CAMERA_PATTERN.fullmatch(c) is None for c in cameras)
                or len(set(cameras)) != len(cameras)
                or camera_id not in cameras):
            _deny()
        start = date.fromisoformat(policy["valid_from"])
        end = date.fromisoformat(policy["expires_on"])
        current = today if today is not None else date.today()
        if (type(current) is not date or end < start
                or (end - start).days > MAX_VALID_DAYS
                or not start <= current <= end):
            _deny()
        required_true = (
            "site_authorization_confirmed", "notices_confirmed",
            "human_review_required", "local_only",
        )
        required_false = (
            "cloud_transfer_enabled", "face_identification_enabled",
            "training_reuse_enabled", "automatic_emergency_dispatch_enabled",
        )
        if (any(policy[key] is not True for key in required_true)
                or any(policy[key] is not False for key in required_false)
                or type(policy["raw_frame_retention_days"]) is not int
                or policy["raw_frame_retention_days"] != 0):
            _deny()
    except (OSError, UnicodeError, TypeError, ValueError, KeyError, OverflowError):
        _deny()
    return {
        "schema_version": POLICY_SCHEMA,
        "authorization_verified": True,
        "scope": "local_staged_research_only",
        "approval_ref": policy["approval_ref"],
        "approved_camera_id": camera_id,
        "jurisdictions": list(jurisdictions),
        "lawfulness_or_full_regulatory_compliance_certified": False,
        "human_legal_review_still_required": True,
        "raw_frame_retention_days": 0,
        "cross_border_transfers_permitted": False,
        "automated_emergency_dispatch_permitted": False,
    }
