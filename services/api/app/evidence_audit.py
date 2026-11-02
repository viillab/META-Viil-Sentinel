"""Synthetic-only consent denial and transaction-bound SQLite audit hash chain.

No upload permission, human consent decision, real-media ingress, real-person
identifiers, images, network calls or external provider requests. SHA256
chains detect accidental/local modifications but are NOT tamperproof against
an attacker with direct database write access.
"""
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.synthetic_evidence import SyntheticEvidenceManifest
from app.synthetic_fixtures import SYNTHETIC_SOURCE

GENESIS = "0" * 64
ACTION = "synthetic_manifest_registered"
MAX_AUDIT_RECORDS = 10_000
SCHEMA = "viil.synthetic.evidence_audit.v1"


class EvidenceAuditFailure(ValueError):
    """The audit history does not agree with the candidate/manifest ledger."""


class SyntheticConsentDecision(BaseModel):
    """A mandatory denial, NEVER a grant of real-media consent."""

    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["viil.synthetic.consent_gate.v1"] = (
        "viil.synthetic.consent_gate.v1"
    )
    source_id: Literal["synthetic-clip-01"] = SYNTHETIC_SOURCE
    state: Literal["not_verified_for_real_media"] = "not_verified_for_real_media"
    reason: Literal["no_independent_real_person_consent_authority"] = (
        "no_independent_real_person_consent_authority"
    )
    external_upload_authorized: Literal[False] = False
    human_evidence_authorized: Literal[False] = False
    meta_call_permitted: Literal[False] = False


class EvidenceAuditReceipt(BaseModel):
    """Metadata-only audit record; never a production consent certificate."""

    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["viil.synthetic.evidence_audit.v1"] = SCHEMA
    sequence: int = Field(ge=1, le=MAX_AUDIT_RECORDS)
    event_id: UUID
    source_id: Literal["synthetic-clip-01"] = SYNTHETIC_SOURCE
    action: Literal["synthetic_manifest_registered"] = ACTION
    occurred_at_utc: datetime
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    consent_state: Literal["not_verified_for_real_media"] = "not_verified_for_real_media"
    external_upload_authorized: Literal[False] = False
    meta_call_permitted: Literal[False] = False
    chain_verified: Literal[True] = True


def require_synthetic_consent_block(manifest: SyntheticEvidenceManifest) -> SyntheticConsentDecision:
    """Fail closed for even the most convincing synthetic fixture.

    This helper has NO approval path. An actual consent verifier is entirely
    separate future work and must never reuse this all-deny gate.
    """
    if (
        type(manifest) is not SyntheticEvidenceManifest
        or manifest.source_id != SYNTHETIC_SOURCE
        or not manifest.simulated
        or manifest.contains_real_person
        or manifest.external_upload_authorized
        or manifest.consent_for_real_media_verified
        or manifest.meta_inference_performed
        or manifest.permanent_storage_allowed
        or manifest.fall_confirmed
    ):
        raise EvidenceAuditFailure("No independent real-person consent authority")
    return SyntheticConsentDecision()


def _payload(
    *, sequence: int, event_id: str, source_id: str,
    occurred_at_utc: str, candidate_sha256: str,
    manifest_sha256: str, previous_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "sequence": sequence,
        "event_id": event_id,
        "source_id": source_id,
        "action": ACTION,
        "occurred_at_utc": occurred_at_utc,
        "candidate_sha256": candidate_sha256,
        "manifest_sha256": manifest_sha256,
        "previous_hash": previous_hash,
        "consent_state": "not_verified_for_real_media",
        "external_upload_authorized": False,
        "meta_call_permitted": False,
    }


def _entry_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def create_audit_schema(connection: sqlite3.Connection) -> None:
    """Call only within the caller's existing SQLite write transaction."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS synthetic_evidence_audit ("
        "sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
        "event_id TEXT NOT NULL UNIQUE,"
        "source_id TEXT NOT NULL,"
        "action TEXT NOT NULL,"
        "occurred_at_utc TEXT NOT NULL,"
        "candidate_sha256 TEXT NOT NULL,"
        "manifest_sha256 TEXT NOT NULL,"
        "previous_hash TEXT NOT NULL,"
        "entry_hash TEXT NOT NULL,"
        "consent_state TEXT NOT NULL,"
        "external_upload_authorized INTEGER NOT NULL DEFAULT 0)"
    )


def _read_rows(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        "SELECT sequence, event_id, source_id, action, occurred_at_utc,"
        "candidate_sha256, manifest_sha256, previous_hash, entry_hash,"
        "consent_state, external_upload_authorized "
        "FROM synthetic_evidence_audit ORDER BY sequence ASC"
    ).fetchall()


def verify_audit_chain(connection: sqlite3.Connection) -> list[EvidenceAuditReceipt]:
    """Check ALL links and exact agreement with the source ledger and registry.

    Returns only validated schema records. A missing audit table when registry
    data exists is rejected, rather than silently treating old rows as audited.
    """
    tables = {
        name for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name IN ('synthetic_evidence_registry','synthetic_evidence_audit','candidates')"
        )
    }
    if "synthetic_evidence_registry" not in tables:
        return []
    if "candidates" not in tables or "synthetic_evidence_audit" not in tables:
        raise EvidenceAuditFailure("Synthetic registry is missing its audit ledger")
    rows = _read_rows(connection)
    if len(rows) > MAX_AUDIT_RECORDS:
        raise EvidenceAuditFailure("Audit history exceeds bounded capacity")
    records: list[EvidenceAuditReceipt] = []
    previous = GENESIS
    for sequence_expected, row in enumerate(rows, 1):
        (
            sequence, event_id, source_id, action, timestamp,
            candidate_digest, manifest_digest, previous_hash, entry_hash,
            consent_state, external_upload,
        ) = row
        if (
            type(sequence) is not int or sequence != sequence_expected
            or type(event_id) is not str or type(source_id) is not str
            or type(action) is not str or type(timestamp) is not str
            or type(candidate_digest) is not str or type(manifest_digest) is not str
            or type(previous_hash) is not str or type(entry_hash) is not str
            or action != ACTION or source_id != SYNTHETIC_SOURCE
            or consent_state != "not_verified_for_real_media"
            or type(external_upload) is not int or external_upload != 0
            or not hmac.compare_digest(previous_hash, previous)
        ):
            raise EvidenceAuditFailure("Synthetic audit chain entry was modified")
        canonical = _payload(
            sequence=sequence, event_id=event_id,
            source_id=source_id, occurred_at_utc=timestamp,
            candidate_sha256=candidate_digest,
            manifest_sha256=manifest_digest, previous_hash=previous_hash,
        )
        if not hmac.compare_digest(_entry_hash(canonical), entry_hash):
            raise EvidenceAuditFailure("Synthetic audit link digest mismatch")
        try:
            verified = EvidenceAuditReceipt(
                **{
                    **canonical,
                    "event_id": UUID(event_id),
                    "occurred_at_utc": datetime.fromisoformat(timestamp),
                },
                entry_hash=entry_hash,
                chain_verified=True,
            )
        except (TypeError, ValueError):
            raise EvidenceAuditFailure("Invalid synthetic audit metadata") from None
        if verified.occurred_at_utc.tzinfo is None:
            raise EvidenceAuditFailure("Audit timestamp is not UTC-aware")
        if verified.occurred_at_utc.utcoffset().total_seconds() != 0:
            raise EvidenceAuditFailure("Audit timestamp is not UTC")
        records.append(verified)
        previous = entry_hash

    joined = connection.execute(
        "SELECT r.event_id, r.source_id, r.candidate_sha256,"
        "r.manifest_json, c.source_id, c.digest "
        "FROM synthetic_evidence_registry AS r "
        "LEFT JOIN candidates AS c ON c.event_id=r.event_id "
        "ORDER BY r.event_id"
    ).fetchall()
    if len(joined) != len(records):
        raise EvidenceAuditFailure("Audit chain does not cover all registered evidence")
    verified_by_id = {str(record.event_id): record for record in records}
    for event_id, source_id, digest, manifest_json, candidate_source, candidate_digest in joined:
        if (
            type(event_id) is not str
            or type(digest) is not str
            or type(manifest_json) is not str
            or type(candidate_digest) is not str
            or source_id != SYNTHETIC_SOURCE
            or candidate_source != SYNTHETIC_SOURCE
            or event_id not in verified_by_id
        ):
            raise EvidenceAuditFailure("Audit missing signed source candidate")
        audit = verified_by_id[event_id]
        if (
            not hmac.compare_digest(digest, candidate_digest)
            or not hmac.compare_digest(audit.candidate_sha256, digest)
            or not hmac.compare_digest(
                audit.manifest_sha256,
                hashlib.sha256(manifest_json.encode("utf-8")).hexdigest(),
            )
        ):
            raise EvidenceAuditFailure("Audit no longer matches registered evidence")
    return records


def append_registered_audit(
    connection: sqlite3.Connection, *,
    event_id: UUID, manifest: SyntheticEvidenceManifest, timestamp: str,
) -> EvidenceAuditReceipt:
    """Write once after the registry insert, in the SAME BEGIN IMMEDIATE txn."""
    require_synthetic_consent_block(manifest)
    # Prior chain must remain valid and agree with previous registered rows;
    # new row already exists so verify the prior links separately here.
    existing = _read_rows(connection)
    if not existing:
        previous = GENESIS
        sequence = 1
    else:
        last = existing[-1]
        previous = last[8]
        sequence = len(existing) + 1
    if sequence > MAX_AUDIT_RECORDS:
        raise EvidenceAuditFailure("Synthetic audit capacity exhausted")
    canonical = _payload(
        sequence=sequence, event_id=str(event_id),
        source_id=manifest.source_id,
        occurred_at_utc=timestamp,
        candidate_sha256=manifest.candidate_sha256,
        manifest_sha256=hashlib.sha256(
            manifest.model_dump_json().encode("utf-8")
        ).hexdigest(),
        previous_hash=previous,
    )
    digest = _entry_hash(canonical)
    connection.execute(
        "INSERT INTO synthetic_evidence_audit "
        "(sequence, event_id, source_id, action, occurred_at_utc,"
        "candidate_sha256, manifest_sha256, previous_hash, entry_hash,"
        "consent_state, external_upload_authorized) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sequence, str(event_id), manifest.source_id, ACTION, timestamp,
            manifest.candidate_sha256, canonical["manifest_sha256"],
            previous, digest, "not_verified_for_real_media", 0,
        ),
    )
    verified = verify_audit_chain(connection)
    if verified[-1].entry_hash != digest:
        raise EvidenceAuditFailure("Appended audit could not be reverified")
    return verified[-1]
