"""Persist only validated synthetic evidence metadata, never images or consent claims.

This registry is NOT a real-media consent verifier. It fails closed for every
non-synthetic source, claims no human permission, and is only usable locally.
The authoritative signed Edge candidate must already exist in the SAME SQLite
ledger before a manifest can be registered. No Meta API calls or alerts.
"""
import hashlib
import hmac
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.candidate_ingest import MAX_STORED_EVENTS, parse_candidate
from app.evidence_anchor import AnchorRejected, verify_checkpoint_snapshot
from app.evidence_audit import (
    EvidenceAuditFailure,
    EvidenceAuditReceipt,
    append_registered_audit,
    create_audit_schema,
    require_synthetic_consent_block,
    verify_audit_chain,
)
from app.synthetic_evidence import (
    RENDERER_VERSION,
    SOURCE_TIMES,
    SyntheticEvidence,
    SyntheticEvidenceManifest,
    verify_synthetic_evidence,
)
from app.synthetic_fixtures import EXPECTED_TRACE_HASHES, SYNTHETIC_SOURCE

# SHA256-pinned rendered diagram from the mathematical fixture. No raw media.
EXPECTED_IMAGE_SHA256 = "5b1f8bf80108bc2281d699211e91a78db249e5646ceed0a637f520538ca27cf2"


class EvidenceRegistryRejected(ValueError):
    """Event, source, blob, consent claim or registry record failed verification."""


class EvidenceRegistryUnavailable(RuntimeError):
    """The existing local candidate ledger cannot be trusted/read."""


class EvidenceRegistryFull(RuntimeError):
    """Bounded demo registry capacity exceeded."""


class EvidenceRegistryRecord(BaseModel):
    """Non-sensitive read-only UI metadata; no PNG bytes, raw pose or consent grant."""

    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["viil.backend.synthetic_evidence_registry.v1"] = (
        "viil.backend.synthetic_evidence_registry.v1"
    )
    event_id: UUID
    source_id: Literal["synthetic-clip-01"] = "synthetic-clip-01"
    registered_at_utc: datetime
    source_timestamp_ms: Literal[850] = 850
    candidate_sha256: str
    trace_sha256: str
    image_sha256: str
    image_origin: Literal["pinned_mathematical_pose_trace"] = "pinned_mathematical_pose_trace"
    consent_state: Literal["not_verified_for_real_media"] = "not_verified_for_real_media"
    simulated: Literal[True] = True
    external_upload_authorized: Literal[False] = False
    real_person_evidence_verified: Literal[False] = False
    image_bytes_stored: Literal[False] = False
    meta_called: Literal[False] = False
    fall_confirmed: Literal[False] = False
    notification_sent: Literal[False] = False


def _checked_manifest(manifest_json: str, *, event_id: UUID,
                      source_id: str, ledger_digest: str) -> SyntheticEvidenceManifest:
    try:
        manifest = SyntheticEvidenceManifest.model_validate_json(manifest_json)
    except (TypeError, ValueError):
        raise EvidenceRegistryRejected("Stored registry manifest is invalid") from None
    if (
        type(ledger_digest) is not str
        or manifest.event_id != event_id
        or manifest.source_id != source_id
        or not hmac.compare_digest(manifest.candidate_sha256, ledger_digest)
        or manifest.trace_sha256 != EXPECTED_TRACE_HASHES["fall"]
        or manifest.image_sha256 != EXPECTED_IMAGE_SHA256
        or manifest.frame_timestamps_ms != SOURCE_TIMES
        or manifest.renderer_version != RENDERER_VERSION
        or manifest.external_upload_authorized
        or manifest.consent_for_real_media_verified
        or manifest.meta_inference_performed
        or manifest.contains_real_person
        or manifest.permanent_storage_allowed
        or manifest.fall_confirmed
    ):
        raise EvidenceRegistryRejected("Stored registry manifest is not a verified synthetic trace")
    return manifest


def _summary(manifest: SyntheticEvidenceManifest, registered_at: str) -> EvidenceRegistryRecord:
    try:
        timestamp = datetime.fromisoformat(registered_at)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Registry receipt time is not timezone aware")
        return EvidenceRegistryRecord(
            event_id=manifest.event_id,
            registered_at_utc=timestamp,
            candidate_sha256=manifest.candidate_sha256,
            trace_sha256=manifest.trace_sha256,
            image_sha256=manifest.image_sha256,
        )
    except (TypeError, ValueError):
        raise EvidenceRegistryRejected("Invalid registry receipt") from None


def _schema(connection: sqlite3.Connection) -> None:
    # No BLOB, original JPEG, PNG, landmarks or API response fields exist here.
    connection.execute(
        "CREATE TABLE IF NOT EXISTS synthetic_evidence_registry ("
        "event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,"
        "candidate_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL,"
        "registered_at_utc TEXT NOT NULL)"
    )


class SyntheticEvidenceRegistry:
    """Same-file metadata-only registry tied to the existing signed candidate receipt."""

    def __init__(
        self, path: Path, *, anchor_required: bool = False,
        anchor_path: Path | None = None, anchor_secret: bytes | None = None,
    ) -> None:
        self.path = Path(path)
        self.anchor_required = anchor_required
        self.anchor_path = Path(anchor_path) if anchor_path is not None else None
        self.anchor_secret = anchor_secret

    def _require_signed_snapshot(self, records: list[EvidenceAuditReceipt]) -> None:
        if not self.anchor_required:
            return
        if self.anchor_path is None or self.anchor_secret is None:
            raise EvidenceRegistryRejected("Independent audit anchor not configured")
        try:
            verify_checkpoint_snapshot(
                records=records, db_path=self.path,
                checkpoint_path=self.anchor_path, secret=self.anchor_secret,
            )
        except AnchorRejected:
            raise EvidenceRegistryRejected("Independent signed audit anchor not verified") from None

    def register(
        self, *, raw_candidate: bytes, evidence: SyntheticEvidence
    ) -> tuple[EvidenceRegistryRecord, bool]:
        """Atomic receipt lookup and immutable registration, with duplicate detection."""
        if self.anchor_required:
            raise EvidenceRegistryRejected("Signed-anchor mode is read-only; export checkpoints separately")
        verify_synthetic_evidence(raw_candidate, evidence)
        candidate = parse_candidate(raw_candidate)
        expected_digest = hashlib.sha256(raw_candidate).hexdigest()
        if candidate.source_id != SYNTHETIC_SOURCE:
            raise EvidenceRegistryRejected("Only the pinned synthetic source is supported")
        if self.path.is_symlink() or not self.path.is_file():
            raise EvidenceRegistryUnavailable("Signed candidate ledger does not exist")

        try:
            # SQLite.Connection context does NOT close its handle on Windows.
            with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                receipt = connection.execute(
                    "SELECT source_id, digest FROM candidates WHERE event_id=?",
                    (str(candidate.event_id),),
                ).fetchone()
                if (
                    receipt is None or receipt[0] != candidate.source_id
                    or type(receipt[1]) is not str
                    or not hmac.compare_digest(receipt[1], expected_digest)
                ):
                    raise EvidenceRegistryRejected(
                        "No matching signed Edge candidate receipt for these exact bytes"
                    )
                _schema(connection)
                create_audit_schema(connection)
                verify_audit_chain(connection)
                require_synthetic_consent_block(evidence.manifest)
                stored = connection.execute(
                    "SELECT manifest_json, registered_at_utc FROM synthetic_evidence_registry "
                    "WHERE event_id=?",
                    (str(candidate.event_id),),
                ).fetchone()
                canonical_manifest = evidence.manifest.model_dump_json()
                if stored is not None:
                    if type(stored[0]) is not str or not hmac.compare_digest(
                        stored[0], canonical_manifest
                    ):
                        raise EvidenceRegistryRejected("Event UUID reused for different evidence")
                    verified = _checked_manifest(
                        stored[0], event_id=candidate.event_id,
                        source_id=candidate.source_id, ledger_digest=receipt[1],
                    )
                    return _summary(verified, stored[1]), True
                used = connection.execute(
                    "SELECT COUNT(*) FROM synthetic_evidence_registry"
                ).fetchone()[0]
                if used >= MAX_STORED_EVENTS:
                    raise EvidenceRegistryFull("Synthetic evidence registry is full")
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    "INSERT INTO synthetic_evidence_registry "
                    "(event_id, source_id, candidate_sha256, manifest_json, registered_at_utc) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(candidate.event_id), candidate.source_id, expected_digest,
                        canonical_manifest, now,
                    ),
                )
                verified_audit = append_registered_audit(
                    connection, event_id=candidate.event_id,
                    manifest=evidence.manifest, timestamp=now,
                )
                if str(verified_audit.event_id) != str(candidate.event_id):
                    raise EvidenceRegistryRejected("Audit and registry event mismatch")
                connection.commit()
                verified = _checked_manifest(
                    canonical_manifest, event_id=candidate.event_id,
                    source_id=candidate.source_id, ledger_digest=receipt[1],
                )
                return _summary(verified, now), False
        except (sqlite3.DatabaseError, OSError):
            raise EvidenceRegistryUnavailable("Registry or signed candidate ledger unavailable") from None

    def get(self, *, event_id: UUID, source_id: str) -> EvidenceRegistryRecord | None:
        """Read-only lookup; never creates a DB, never leaks cross-source records."""
        if source_id != SYNTHETIC_SOURCE or not isinstance(event_id, UUID):
            raise EvidenceRegistryRejected("Unsupported registry lookup scope")
        if self.path.is_symlink():
            raise EvidenceRegistryUnavailable("Registry file is not permitted")
        if not self.path.is_file():
            return None
        try:
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=3)) as connection:
                connection.execute("BEGIN")
                present = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='synthetic_evidence_registry'"
                ).fetchone()
                if present is None:
                    return None
                try:
                    verified_chain = verify_audit_chain(connection)
                except EvidenceAuditFailure:
                    raise EvidenceRegistryRejected("Evidence audit integrity failed") from None
                if any(record.source_id != source_id for record in verified_chain):
                    raise EvidenceAuditFailure("Unscoped synthetic audit history")
                self._require_signed_snapshot(verified_chain)
                row = connection.execute(
                    "SELECT r.source_id, r.candidate_sha256, r.manifest_json, "
                    "r.registered_at_utc, c.source_id, c.digest "
                    "FROM synthetic_evidence_registry AS r "
                    "JOIN candidates AS c ON c.event_id=r.event_id "
                    "WHERE r.event_id=? AND r.source_id=?",
                    (str(event_id), source_id),
                ).fetchone()
            if row is None:
                return None
            registered_source, stored_digest, json_manifest, when, candidate_source, digest = row
            if (
                registered_source != source_id or candidate_source != source_id
                or type(stored_digest) is not str or type(digest) is not str
                or not hmac.compare_digest(stored_digest, digest)
            ):
                raise EvidenceRegistryRejected("Registry and ledger disagree")
            verified = _checked_manifest(
                json_manifest, event_id=event_id, source_id=source_id, ledger_digest=digest,
            )
            return _summary(verified, when)
        except (sqlite3.DatabaseError, OSError):
            raise EvidenceRegistryUnavailable("Registry read is unavailable") from None

    def get_audit(
        self, *, event_id: UUID, source_id: str
    ) -> EvidenceAuditReceipt | None:
        """Return validated metadata-only audit entry for this exact synthetic UUID."""
        if source_id != SYNTHETIC_SOURCE or not isinstance(event_id, UUID):
            raise EvidenceRegistryRejected("Unsupported audit lookup scope")
        if self.path.is_symlink():
            raise EvidenceRegistryUnavailable("Audit file is not permitted")
        if not self.path.is_file():
            return None
        try:
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=3.0)) as connection:
                connection.execute("BEGIN")
                receipts = verify_audit_chain(connection)
                self._require_signed_snapshot(receipts)
            return next(
                (entry for entry in receipts if entry.event_id == event_id), None
            )
        except (sqlite3.DatabaseError, OSError):
            raise EvidenceRegistryUnavailable("Audit read is unavailable") from None
