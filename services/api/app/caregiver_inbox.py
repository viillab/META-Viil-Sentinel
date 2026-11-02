"""Read-only, source-scoped local caregiver inbox over *synthetic* receipts.

No images, names, medical data, model inference, real alert delivery or
review mutation. This is a guarded backend projection for UI integration
testing only; it is NOT production caregiver identity or session RBAC.
"""
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_INBOX_ITEMS = 30
CARE_SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


class CaregiverAdvisory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    advisory_id: UUID
    source_id: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    stage: Literal["edge_candidate"] = "edge_candidate"
    context_code: Literal["unknown"] = "unknown"
    meta_provenance: Literal["none"] = "none"
    delivery_state: Literal["not_sent"] = "not_sent"
    receipt_verified: Literal[False] = False
    review_state: Literal["pending"] = "pending"
    simulated: Literal[True] = True
    fall_confirmed: Literal[False] = False
    emergency_dispatch_authorized: Literal[False] = False
    human_follow_up_required: Literal[True] = True


class CaregiverInbox(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["viil.backend.caregiver_inbox.v1"] = (
        "viil.backend.caregiver_inbox.v1"
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    access_scope: Literal["authenticated_caregiver"] = "authenticated_caregiver"
    advisories: list[CaregiverAdvisory] = Field(max_length=MAX_INBOX_ITEMS)


def build_inbox(*, ledger_path: Path, source_id: str) -> CaregiverInbox:
    """Project committed synthetic-only receipts, never source-relative event time.

    A missing DB yields an empty inbox; failures to read an existing DB are
    surfaced to the caller and must fail closed. The query is strictly
    read-only and filters by a pre-configured, validated source.
    """
    if not CARE_SOURCE_PATTERN.fullmatch(source_id) or not source_id.startswith("synthetic-"):
        raise ValueError("Unsupported or non-synthetic caregiver scope")
    path = Path(ledger_path)
    if not path.is_file():
        return CaregiverInbox(advisories=[])
    # SQLite URI mode=ro cannot silently create a DB if the file disappears.
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=3.0)) as connection:
        rows = connection.execute(
            "SELECT event_id, source_id, received_at_utc FROM candidates "
            "WHERE source_id=? ORDER BY received_at_utc DESC, event_id DESC LIMIT ?",
            (source_id, MAX_INBOX_ITEMS),
        ).fetchall()
    advisories = [
        CaregiverAdvisory(
            advisory_id=UUID(event_id),
            source_id=row_source,
            # Receipt UTC (not the Edge relative timestamp or physical incident time).
            occurred_at=datetime.fromisoformat(received_at),
        )
        for event_id, row_source, received_at in rows
    ]
    if any(item.occurred_at.tzinfo is None for item in advisories):
        raise ValueError("Database receipt lacks timezone")
    return CaregiverInbox(advisories=advisories)
