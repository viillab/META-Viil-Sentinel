"""Durable, no-billing Meta Copilot SHADOW admission and event de-duplication.

A model-shaped mock response is useful for testing, but a real safety
system must prevent duplicate attempts across process restarts. This module
reserves ONE synthetic event in its own private SQLite ledger BEFORE the
mock-only provider adapter; a failed or interrupted reservation is never
automatically retried. Cache reads *always* reverify independent evidence
and audit anchor; no cached answer is ever a consent or fall decision.

There is deliberately NO live HTTP provider, API-key handling, Meta spend
reservation, real-media authorization or notification implementation here.
"""
import hashlib
import hmac
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.evidence_registry import SyntheticEvidenceRegistry
from app.meta_budget import (
    MAX_APPROVED_LOCAL_CALLS,
    MAX_APPROVED_LOCAL_MICRO_USD,
    RESERVATION_MICRO_USD,
    MetaBudget,
)
from app.meta_copilot import MetaCopilotPreview, build_offline_meta_planner_request
from app.meta_copilot_mock_transport import MockOnlyMetaPlanner
from app.synthetic_fixtures import SYNTHETIC_SOURCE

MAX_SHADOW_EVENTS = 10_000
DEFAULT_SHADOW_LEDGER = (
    Path(__file__).resolve().parents[3] / "data" / "private"
    / "meta_copilot_shadow.sqlite3"
)


class ShadowPlannerDenied(ValueError):
    """Unverified event, reused event identifier, or unsafe local shadow ledger."""


class ShadowPlannerPreviouslyAttempted(RuntimeError):
    """Fail closed: a reserved/failed mock run must never be automatically retried."""


class ShadowPlannerUnavailable(RuntimeError):
    """The shadow record cannot be safely opened, verified, or committed."""


class ShadowPlannerCapacity(RuntimeError):
    """Bounded mock-only admission table is full."""


class ShadowReadiness(BaseModel):
    """Describe real-provider admission WITHOUT granting any real permissions."""

    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["viil.meta.planner_readiness.v1"] = (
        "viil.meta.planner_readiness.v1"
    )
    event_id: UUID
    mode: Literal["shadow_mock_only"] = "shadow_mock_only"
    real_provider_allowed: Literal[False] = False
    real_provider_denial: Literal["synthetic_consent_not_verified_and_budget_unapproved"] = (
        "synthetic_consent_not_verified_and_budget_unapproved"
    )
    meta_budget_calls_observed: int
    meta_budget_reserved_micro_usd: int
    local_budget_ledger_present: bool
    local_approved_cap_exhausted: bool
    official_meta_billing_verified: Literal[False] = False
    real_media_upload_authorized: Literal[False] = False
    alert_dispatch_authorized: Literal[False] = False
    meta_api_called: Literal[False] = False


class ShadowRunReceipt(BaseModel):
    """No personal information, provider response or paid credentials."""

    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["viil.meta.shadow_run.v1"] = "viil.meta.shadow_run.v1"
    event_id: UUID
    source_id: Literal["synthetic-clip-01"] = SYNTHETIC_SOURCE
    outcome: Literal["mock_completed", "duplicate_from_shadow_cache"]
    mock_provider_invoked_this_call: bool
    total_mock_provider_calls_for_event: Literal[1] = 1
    meta_api_called: Literal[False] = False
    budget_modified: Literal[False] = False
    fall_confirmed: Literal[False] = False
    alert_dispatched: Literal[False] = False
    real_media_sent: Literal[False] = False
    preview: MetaCopilotPreview
    readiness: ShadowReadiness


@dataclass(frozen=True, slots=True)
class _TrustedFacts:
    event_id: UUID
    candidate_digest: str
    audit_digest: str
    request_digest: str


def _facts(registry: SyntheticEvidenceRegistry, event_id: UUID) -> _TrustedFacts:
    if type(registry) is not SyntheticEvidenceRegistry or not registry.anchor_required:
        raise ShadowPlannerDenied("Independent signed evidence anchor is required")
    if not isinstance(event_id, UUID):
        raise ShadowPlannerDenied("Invalid event identifier")
    # Both reads verify the complete source ledger, audit hash chain and
    # independent HMAC checkpoint. Fail closed if either has been revoked.
    evidence = registry.get(event_id=event_id, source_id=SYNTHETIC_SOURCE)
    audit = registry.get_audit(event_id=event_id, source_id=SYNTHETIC_SOURCE)
    if evidence is None or audit is None:
        raise ShadowPlannerDenied("Unknown or unverified synthetic event")
    body = build_offline_meta_planner_request(evidence, audit)
    serialized = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return _TrustedFacts(
        event_id=event_id,
        candidate_digest=evidence.candidate_sha256,
        audit_digest=audit.entry_hash,
        request_digest=hashlib.sha256(serialized).hexdigest(),
    )


def _readiness(event_id: UUID, budget: MetaBudget) -> ShadowReadiness:
    # Read-only. In particular: never call reserve_once(), create a new
    # budget ledger, or infer the organization's Meta Billing balance.
    try:
        if budget.path.is_symlink():
            raise ShadowPlannerUnavailable("Meta budget ledger path is unsafe")
        ledger_present = budget.path.is_file()
        attempts, reserved = budget.status()
    except (sqlite3.DatabaseError, OSError):
        raise ShadowPlannerUnavailable("Meta budget ledger could not be read") from None
    if (
        type(attempts) is not int or type(reserved) is not int
        or attempts < 0 or reserved < 0
    ):
        raise ShadowPlannerUnavailable("Meta budget ledger has invalid counters")
    return ShadowReadiness(
        event_id=event_id,
        meta_budget_calls_observed=attempts,
        meta_budget_reserved_micro_usd=reserved,
        local_budget_ledger_present=ledger_present,
        local_approved_cap_exhausted=(
            attempts >= MAX_APPROVED_LOCAL_CALLS
            or reserved + RESERVATION_MICRO_USD > MAX_APPROVED_LOCAL_MICRO_USD
        ),
    )


def _schema(con: sqlite3.Connection) -> None:
    # No raw Meta responses, access tokens, patient images or camera data.
    con.execute(
        "CREATE TABLE IF NOT EXISTS meta_copilot_shadow_runs ("
        "event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, "
        "candidate_sha256 TEXT NOT NULL, audit_entry_sha256 TEXT NOT NULL, "
        "request_sha256 TEXT NOT NULL, state TEXT NOT NULL "
        "CHECK(state IN ('reserved', 'completed', 'failed')), "
        "preview_json TEXT, created_at_utc TEXT NOT NULL)"
    )


def inspect_shadow_readiness(
    *, registry: SyntheticEvidenceRegistry, event_id: UUID,
    budget: MetaBudget,
) -> ShadowReadiness:
    """Read-only authenticated-UI status, no case/Meta/budget DB mutations."""
    if type(budget) is not MetaBudget:
        raise ShadowPlannerDenied("Only local budget status is accepted")
    _facts(registry, event_id)
    return _readiness(event_id, budget)


class MetaCopilotShadowLedger:
    def __init__(self, path: Path = DEFAULT_SHADOW_LEDGER) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ShadowPlannerDenied("Shadow ledger symlink is not permitted")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=5.0)

    def _claim(self, facts: _TrustedFacts) -> MetaCopilotPreview | None:
        try:
            with closing(self._connect()) as con, con:
                con.execute("BEGIN IMMEDIATE")
                _schema(con)
                row = con.execute(
                    "SELECT source_id, candidate_sha256, audit_entry_sha256, "
                    "request_sha256, state, preview_json "
                    "FROM meta_copilot_shadow_runs WHERE event_id=?",
                    (str(facts.event_id),),
                ).fetchone()
                if row is not None:
                    source, candidate, audit, request, state, preview_json = row
                    if (
                        source != SYNTHETIC_SOURCE
                        or any(type(x) is not str for x in (candidate, audit, request))
                        or not hmac.compare_digest(candidate, facts.candidate_digest)
                        or not hmac.compare_digest(audit, facts.audit_digest)
                        or not hmac.compare_digest(request, facts.request_digest)
                    ):
                        raise ShadowPlannerDenied("Event reused or signed evidence changed")
                    if state != "completed" or type(preview_json) is not str:
                        raise ShadowPlannerPreviouslyAttempted(
                            "Shadow planner already reserved/failed; automatic retry disabled"
                        )
                    try:
                        preview = MetaCopilotPreview.model_validate_json(preview_json)
                    except (ValueError, TypeError):
                        raise ShadowPlannerDenied("Cached synthetic preview is malformed") from None
                    if (
                        preview.event_id != facts.event_id
                        or preview.candidate_sha256 != facts.candidate_digest
                        or preview.audit_entry_sha256 != facts.audit_digest
                    ):
                        raise ShadowPlannerDenied("Cached preview does not match signed evidence")
                    return preview
                count = con.execute(
                    "SELECT COUNT(*) FROM meta_copilot_shadow_runs"
                ).fetchone()[0]
                if count >= MAX_SHADOW_EVENTS:
                    raise ShadowPlannerCapacity("Bounded shadow ledger reached capacity")
                con.execute(
                    "INSERT INTO meta_copilot_shadow_runs "
                    "(event_id,source_id,candidate_sha256,audit_entry_sha256,"
                    "request_sha256,state,preview_json,created_at_utc) "
                    "VALUES (?,?,?,?,?,'reserved',NULL,?)",
                    (
                        str(facts.event_id), SYNTHETIC_SOURCE, facts.candidate_digest,
                        facts.audit_digest, facts.request_digest,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                con.commit()
            return None
        except (sqlite3.DatabaseError, OSError):
            raise ShadowPlannerUnavailable("Shadow ledger write/read is unavailable") from None

    def _finish(self, facts: _TrustedFacts, *, state: str,
                preview: MetaCopilotPreview | None = None) -> None:
        if state not in ("completed", "failed"):
            raise ShadowPlannerDenied("Unsupported state transition")
        try:
            with closing(self._connect()) as con, con:
                con.execute("BEGIN IMMEDIATE")
                body = preview.model_dump_json() if preview is not None else None
                changed = con.execute(
                    "UPDATE meta_copilot_shadow_runs SET state=?, preview_json=? "
                    "WHERE event_id=? AND state='reserved' AND source_id=? "
                    "AND candidate_sha256=? AND audit_entry_sha256=? AND request_sha256=?",
                    (
                        state, body, str(facts.event_id), SYNTHETIC_SOURCE,
                        facts.candidate_digest, facts.audit_digest,
                        facts.request_digest,
                    ),
                ).rowcount
                if changed != 1:
                    raise ShadowPlannerDenied("Shadow reservation changed before commit")
                con.commit()
        except (sqlite3.DatabaseError, OSError):
            raise ShadowPlannerUnavailable("Shadow run completion unavailable") from None

    async def run_mock_once(
        self, *, event_id: UUID, registry: SyntheticEvidenceRegistry,
        mock_planner: MockOnlyMetaPlanner, budget: MetaBudget,
    ) -> ShadowRunReceipt:
        """A failed/interrupted event is never auto-retried; no paid API route."""
        if type(mock_planner) is not MockOnlyMetaPlanner:
            raise ShadowPlannerDenied("Only mock transport planner is supported")
        if type(budget) is not MetaBudget:
            raise ShadowPlannerDenied("Only the local read-only budget observer is supported")
        facts = _facts(registry, event_id)
        readiness = _readiness(event_id, budget)
        # This read-only readiness is categorically NOT an external-upload
        # permission. An offline shadow run is allowed for synthetic data.
        cached = self._claim(facts)
        if cached is not None:
            return ShadowRunReceipt(
                event_id=event_id, outcome="duplicate_from_shadow_cache",
                mock_provider_invoked_this_call=False, preview=cached,
                readiness=readiness,
            )
        try:
            result = await mock_planner.propose_for_verified_event(
                registry=registry, event_id=event_id
            )
            preview = result.preview
            if (
                result.meta_api_called or result.meta_budget_modified
                or result.real_media_sent or result.state_changed
                or preview.event_id != event_id
                or preview.candidate_sha256 != facts.candidate_digest
                or preview.audit_entry_sha256 != facts.audit_digest
            ):
                raise ShadowPlannerDenied("Mock provider attempted unapproved effect")
            # Confirm the anchor has not changed between mock response and
            # our final durable write, independent of the mock's own checks.
            latest = _facts(registry, event_id)
            if latest != facts:
                raise ShadowPlannerDenied("Signed synthetic evidence changed during mock run")
            self._finish(facts, state="completed", preview=preview)
        except Exception:
            # Reservation is deliberately permanent after any failure to
            # prevent retry storms; errors are NOT logged or stored verbatim.
            self._finish(facts, state="failed")
            raise
        return ShadowRunReceipt(
            event_id=event_id, outcome="mock_completed",
            mock_provider_invoked_this_call=True, preview=preview,
            readiness=readiness,
        )
