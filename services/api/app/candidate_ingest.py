"""Offline-only Edge candidate v1 intake gate.

This accepts *only synthetic pose trace metadata*, never live camera frames,
consent claims, images, or real-person incidents. Source-scoped HMAC proof,
strict v1 envelope, bounded requests and a durable SQLite dedup ledger protect
the local development bridge. No Meta call or caregiver notification occurs.
"""
import hashlib
import hmac
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError

DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "private" / "edge_candidate_ingest.sqlite3"
)
MAX_BODY_BYTES = 4096
MAX_CLOCK_SKEW_SECONDS = 60
MAX_REQUESTS_PER_MINUTE = 30
MAX_STORED_EVENTS = 10_000
SOURCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
SIGNATURE_PATTERN = re.compile(r"^sha256=[0-9a-f]{64}$")
TIMESTAMP_PATTERN = re.compile(r"^[1-9][0-9]{9,11}$")


class EdgeCandidate(BaseModel):
    """Exact frozen Edge v1 fields, further restricted to synthetic-only intake."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["viil.edge.candidate.v1"]
    event_type: Literal["FALL_CANDIDATE"]
    event_id: UUID
    source_id: str = Field(pattern=SOURCE_PATTERN, min_length=1, max_length=80)
    source_timestamp_ms: int = Field(ge=0, le=86_400_000)
    timestamp_basis: Literal["relative_to_source_start"]
    detector: str = Field(pattern=SOURCE_PATTERN, min_length=1, max_length=80)
    model_sha256: None
    input_provenance: Literal["synthetic_pose_trace"]
    detector_score: FiniteFloat = Field(ge=0, le=1)
    detector_score_type: Literal["uncalibrated_heuristic"]
    score_calibrated: Literal[False]
    confirmed_fall: Literal[False]
    human_review_required: Literal[True]
    medical_assessment_performed: Literal[False]
    simulated: Literal[True]
    evidence_refs: list[str] = Field(max_length=0)
    delivery_mode: Literal["local_stdout_only"]


class CandidateReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["viil.backend.candidate_receipt.v1"] = (
        "viil.backend.candidate_receipt.v1"
    )
    event_id: UUID
    source_id: str
    accepted: Literal[True] = True
    duplicate: bool
    review_required: Literal[True] = True
    confirmed_fall: Literal[False] = False
    meta_called: Literal[False] = False
    notification_sent: Literal[False] = False
    source_timestamp_basis: Literal["relative_to_source_start"] = (
        "relative_to_source_start"
    )
    received_at_utc: datetime


class InvalidEdgeCandidate(ValueError):
    pass


class IntakeRateExceeded(RuntimeError):
    pass


class IntakeStorageFull(RuntimeError):
    pass


class IntakeConflict(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEdgeCandidate("Duplicate JSON key")
        result[key] = value
    return result


def parse_candidate(body: bytes) -> EdgeCandidate:
    if not body or len(body) > MAX_BODY_BYTES:
        raise InvalidEdgeCandidate("Invalid candidate body length")
    try:
        json.loads(
            body,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(
                InvalidEdgeCandidate("Non-finite value")
            ),
        )
        return EdgeCandidate.model_validate_json(body, strict=True)
    except (ValueError, TypeError, UnicodeError, ValidationError):
        raise InvalidEdgeCandidate("Invalid or unsupported Edge v1 candidate") from None


def _signed_message(source: str, timestamp: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return f"viil.edge.candidate.v1\n{source}\n{timestamp}\n{digest}".encode("ascii")


def sign_candidate(secret: bytes, *, source: str, timestamp: str, body: bytes) -> str:
    """Source-bound request signature; caller owns nonce-free 60-second TTL."""
    digest = hmac.new(
        secret, _signed_message(source, timestamp, body), hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def verify_candidate_auth(
    *,
    secret: bytes,
    configured_source: str,
    header_source: str | None,
    header_timestamp: str | None,
    header_signature: str | None,
    body: bytes,
    now_seconds: int | None = None,
) -> bool:
    if len(secret) < 32 or not configured_source.startswith("synthetic-"):
        return False
    if header_source != configured_source:
        return False
    if not header_timestamp or not TIMESTAMP_PATTERN.fullmatch(header_timestamp):
        return False
    if not header_signature or not SIGNATURE_PATTERN.fullmatch(header_signature):
        return False
    now = int(time.time()) if now_seconds is None else now_seconds
    if abs(now - int(header_timestamp)) > MAX_CLOCK_SKEW_SECONDS:
        return False
    expected = sign_candidate(
        secret, source=header_source, timestamp=header_timestamp, body=body
    )
    return hmac.compare_digest(expected, header_signature)


class CandidateLedger:
    """Persistent dedup + per-source rate cap under a single SQLite transaction."""

    def __init__(self, path: Path = DEFAULT_LEDGER_PATH) -> None:
        self.path = Path(path)

    def accept(
        self, candidate: EdgeCandidate, *, raw: bytes, now_seconds: int | None = None
    ) -> CandidateReceipt:
        now = int(time.time()) if now_seconds is None else now_seconds
        digest = hashlib.sha256(raw).hexdigest()
        received_at = datetime.fromtimestamp(now, tz=UTC)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3.Connection.__exit__ commits/rolls back but does NOT close.
        # closing() prevents Windows file locks after a finished request.
        with closing(sqlite3.connect(self.path, timeout=5.0)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS candidates ("
                "event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, "
                "digest TEXT NOT NULL, received_at_utc TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rate_windows ("
                "source_id TEXT PRIMARY KEY, window_start INTEGER NOT NULL, "
                "request_count INTEGER NOT NULL)"
            )
            rate_row = connection.execute(
                "SELECT window_start, request_count FROM rate_windows WHERE source_id=?",
                (candidate.source_id,),
            ).fetchone()
            if rate_row and now < rate_row[0] + 60:
                if rate_row[1] >= MAX_REQUESTS_PER_MINUTE:
                    raise IntakeRateExceeded("Synthetic intake rate limit exceeded")
                connection.execute(
                    "UPDATE rate_windows SET request_count=request_count+1 WHERE source_id=?",
                    (candidate.source_id,),
                )
            else:
                connection.execute(
                    "INSERT INTO rate_windows (source_id, window_start, request_count) "
                    "VALUES (?, ?, 1) ON CONFLICT(source_id) DO UPDATE SET "
                    "window_start=excluded.window_start, request_count=1",
                    (candidate.source_id, now),
                )
            existing = connection.execute(
                "SELECT source_id, digest, received_at_utc FROM candidates WHERE event_id=?",
                (str(candidate.event_id),),
            ).fetchone()
            if existing:
                if existing[0] != candidate.source_id or existing[1] != digest:
                    raise IntakeConflict("Candidate ID already used for other content")
                receipt = CandidateReceipt(
                    event_id=candidate.event_id,
                    source_id=candidate.source_id,
                    duplicate=True,
                    received_at_utc=datetime.fromisoformat(existing[2]),
                )
            else:
                count = connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
                if count >= MAX_STORED_EVENTS:
                    raise IntakeStorageFull("Candidate ledger capacity reached")
                connection.execute(
                    "INSERT INTO candidates VALUES (?, ?, ?, ?)",
                    (
                        str(candidate.event_id), candidate.source_id,
                        digest, received_at.isoformat(),
                    ),
                )
                receipt = CandidateReceipt(
                    event_id=candidate.event_id, source_id=candidate.source_id,
                    duplicate=False, received_at_utc=received_at,
                )
            connection.commit()
            return receipt
