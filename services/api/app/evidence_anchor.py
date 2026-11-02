"""Opt-in, independent HMAC checkpoint for the synthetic evidence audit.

An anchored snapshot detects coordinated rewrites of the *SQLite* chain
when the separate checkpoint AND signing key remain outside the attacker's
control. Not WORM, not a production audit authority, not a consent grant.
No images, real media, paid API or network transport.
"""
import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.evidence_audit import EvidenceAuditFailure, EvidenceAuditReceipt, verify_audit_chain
from app.synthetic_fixtures import SYNTHETIC_SOURCE

DOMAIN = b"viil.synthetic.audit.anchor.v1\n"
MAX_ANCHOR_SIZE = 4096
ANCHOR_SCHEMA = "viil.synthetic.audit_anchor.v1"


class AnchorRejected(ValueError):
    """Missing, invalid, stale or mismatched independent anchor. Fail closed."""


class AuditAnchor(BaseModel):
    """Signed checkpoint only; never contains a secret or personal media."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["viil.synthetic.audit_anchor.v1"] = ANCHOR_SCHEMA
    source_id: Literal["synthetic-clip-01"] = SYNTHETIC_SOURCE
    created_at_utc: datetime
    record_count: int = Field(ge=1, le=10_000)
    first_event_id: UUID
    last_event_id: UUID
    first_entry_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    last_entry_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    consent_state: Literal["not_verified_for_real_media"] = "not_verified_for_real_media"
    external_upload_authorized: Literal[False] = False
    meta_call_permitted: Literal[False] = False
    hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _safe_paths(db: Path, checkpoint: Path) -> tuple[Path, Path]:
    try:
        if (
            db.is_symlink() or checkpoint.is_symlink()
            or checkpoint.parent.is_symlink()
            or not db.is_file() or not checkpoint.parent.is_dir()
        ):
            raise AnchorRejected("Audit ledger or independent checkpoint location unavailable")
        db_abs, cp_abs = db.resolve(), checkpoint.resolve()
    except OSError:
        raise AnchorRejected("Audit checkpoint path cannot be inspected") from None
    if db_abs == cp_abs or db_abs.parent == cp_abs.parent:
        raise AnchorRejected("Checkpoint must be in a separate directory from SQLite")
    if cp_abs.suffix.lower() != ".json":
        raise AnchorRejected("Checkpoint must be a standalone JSON file")
    return db_abs, cp_abs


def _safe_secret(secret: bytes) -> None:
    if type(secret) is not bytes or not 32 <= len(secret) <= 4096:
        raise AnchorRejected("Independent anchor HMAC key must be 32-4096 bytes")


def _no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, value in pairs:
        if key in data:
            raise AnchorRejected("Duplicate signed JSON field")
        data[key] = value
    return data


def _read_checkpoint(path: Path, secret: bytes) -> AuditAnchor:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ANCHOR_SIZE:
            raise AnchorRejected("Independent signed audit anchor is missing or oversized")
        raw = path.read_bytes()
    except OSError:
        raise AnchorRejected("Independent signed audit anchor cannot be read") from None
    try:
        mapping = json.loads(
            raw, object_pairs_hook=_no_duplicate_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(AnchorRejected("Invalid constant")),
        )
        if not isinstance(mapping, dict):
            raise AnchorRejected("Invalid signed anchor shape")
        supplied_mac = mapping.pop("hmac_sha256", None)
        if type(supplied_mac) is not str or len(supplied_mac) != 64:
            raise AnchorRejected("Missing audit checkpoint MAC")
        expected = hmac.new(secret, DOMAIN + _canonical(mapping), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_mac):
            raise AnchorRejected("Independent audit checkpoint HMAC mismatch")
        # Strict Pydantic model: JSON UUID/date need parsing, other fields remain strict.
        anchor = AuditAnchor.model_validate_json(raw, strict=True)
    except (UnicodeError, ValueError, TypeError, ValidationError, OSError):
        raise AnchorRejected("Independent signed audit anchor is invalid") from None
    if anchor.created_at_utc.tzinfo is None or anchor.created_at_utc.utcoffset() is None:
        raise AnchorRejected("Audit checkpoint has no UTC timezone")
    if anchor.created_at_utc.utcoffset().total_seconds() != 0:
        raise AnchorRejected("Audit checkpoint was not created in UTC")
    return anchor


def _signed_anchor(records: list[EvidenceAuditReceipt], secret: bytes) -> AuditAnchor:
    if not records:
        raise AnchorRejected("Cannot anchor an empty or unaudited synthetic registry")
    now = datetime.now(UTC)
    content: dict[str, object] = {
        "schema_version": ANCHOR_SCHEMA,
        "source_id": SYNTHETIC_SOURCE,
        "created_at_utc": now.isoformat(),
        "record_count": len(records),
        "first_event_id": str(records[0].event_id),
        "last_event_id": str(records[-1].event_id),
        "first_entry_hash": records[0].entry_hash,
        "last_entry_hash": records[-1].entry_hash,
        "consent_state": "not_verified_for_real_media",
        "external_upload_authorized": False,
        "meta_call_permitted": False,
    }
    unsigned = AuditAnchor(
        **{
            **content,
            "created_at_utc": now,
            "first_event_id": records[0].event_id,
            "last_event_id": records[-1].event_id,
        },
        hmac_sha256="0" * 64,
    )
    # Sign the exact JSON representation that is eventually persisted.
    payload = unsigned.model_dump(mode="json", exclude={"hmac_sha256"})
    mac = hmac.new(secret, DOMAIN + _canonical(payload), hashlib.sha256).hexdigest()
    return unsigned.model_copy(update={"hmac_sha256": mac})


def _read_records(db: Path) -> list[EvidenceAuditReceipt]:
    if db.is_symlink() or not db.is_file():
        raise AnchorRejected("Synthetic SQLite ledger is unavailable")
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as conn:
            conn.execute("BEGIN")
            return verify_audit_chain(conn)
    except (sqlite3.DatabaseError, OSError, EvidenceAuditFailure):
        raise AnchorRejected("Synthetic audit chain failed independent verification") from None


def _match_anchor(anchor: AuditAnchor, records: list[EvidenceAuditReceipt],
                  *, require_latest: bool) -> None:
    if not records or anchor.record_count > len(records):
        raise AnchorRejected("Signed audit checkpoint refers to missing history")
    if require_latest and anchor.record_count != len(records):
        raise AnchorRejected("Signed audit checkpoint is stale; refresh explicitly")
    first = records[0]
    last = records[anchor.record_count - 1]
    if (
        anchor.first_event_id != first.event_id
        or anchor.last_event_id != last.event_id
        or not hmac.compare_digest(anchor.first_entry_hash, first.entry_hash)
        or not hmac.compare_digest(anchor.last_entry_hash, last.entry_hash)
    ):
        raise AnchorRejected("SQLite audit chain disagrees with independent signed checkpoint")


def verify_checkpoint_snapshot(
    *, db_path: Path, checkpoint_path: Path, secret: bytes,
    records: list[EvidenceAuditReceipt],
) -> AuditAnchor:
    """Verify an anchor against a chain already checked in ONE SQLite snapshot."""
    _safe_secret(secret)
    _, checkpoint = _safe_paths(Path(db_path), Path(checkpoint_path))
    anchor = _read_checkpoint(checkpoint, secret)
    _match_anchor(anchor, records, require_latest=True)
    return anchor


def verify_checkpoint(
    *, db_path: Path, checkpoint_path: Path, secret: bytes,
) -> AuditAnchor:
    """Read-only strict verification of a separate HMAC-anchored snapshot."""
    _safe_secret(secret)
    db, checkpoint = _safe_paths(Path(db_path), Path(checkpoint_path))
    anchor = _read_checkpoint(checkpoint, secret)
    _match_anchor(anchor, _read_records(db), require_latest=True)
    return anchor


def capture_checkpoint(
    *, db_path: Path, checkpoint_path: Path, secret: bytes,
) -> AuditAnchor:
    """Operator-triggered export. Rejects rollback or rewriting an older anchor.

    Snapshot capture is NOT atomic with later SQLite writes. Verification
    requires an exact current head; explicitly refresh after new commits.
    External checkpoint retention and key custody are operator responsibilities.
    """
    _safe_secret(secret)
    db, target = _safe_paths(Path(db_path), Path(checkpoint_path))
    records = _read_records(db)
    if not records:
        raise AnchorRejected("Cannot sign empty or pre-audit evidence history")
    if target.exists():
        older = _read_checkpoint(target, secret)
        _match_anchor(older, records, require_latest=False)
        # A checkpoint with the same head is idempotently re-used.
        if older.record_count == len(records):
            return older
    new_anchor = _signed_anchor(records, secret)
    encoded = new_anchor.model_dump_json().encode("utf-8")
    if len(encoded) > MAX_ANCHOR_SIZE:
        raise AnchorRejected("Signed audit checkpoint too large")
    fd = None
    staging = None
    try:
        fd, temp = tempfile.mkstemp(
            prefix=".viil-anchor-", suffix=".tmp", dir=target.parent
        )
        staging = Path(temp)
        try:
            os.chmod(staging, 0o600)
        except OSError:
            pass  # ACL requirements differ by OS; never treat chmod as a guarantee.
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, target)
        staging = None
    except OSError:
        raise AnchorRejected("Could not persist independent audit checkpoint") from None
    finally:
        if fd is not None:
            os.close(fd)
        if staging is not None:
            staging.unlink(missing_ok=True)
    return new_anchor


def main() -> int:
    """Opt-in maintenance CLI. No keys in command arguments or output."""
    parser = argparse.ArgumentParser(description="Offline synthetic audit checkpoint")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--capture", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not (args.capture or args.verify):
        print(json.dumps({"mode": "OFFLINE_NO_CHANGES", "key_loaded": False}))
        return 0
    if args.ledger is None or args.checkpoint is None:
        parser.error("Choose both --ledger and --checkpoint")
    # Deliberately separate from all Edge, caregiver and Meta keys.
    secret = os.getenv("VIIL_SYNTHETIC_AUDIT_ANCHOR_KEY", "").encode("utf-8")
    try:
        result = (capture_checkpoint if args.capture else verify_checkpoint)(
            db_path=args.ledger, checkpoint_path=args.checkpoint, secret=secret,
        )
    except AnchorRejected:
        print(json.dumps({"status": "AUDIT_ANCHOR_NOT_VERIFIED", "safe_to_trust": False}))
        return 1
    print(json.dumps({
        "status": "SYNTHETIC_AUDIT_ANCHOR_VERIFIED",
        "record_count": result.record_count,
        "first_event_id": str(result.first_event_id),
        "last_event_id": str(result.last_event_id),
        "safe_for_real_media": False,
        "meta_called": False,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
