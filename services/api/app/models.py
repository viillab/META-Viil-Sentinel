"""Incident contracts shared between detection, agent, and caregiver-facing APIs."""
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    ANALYZING = "ANALYZING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOTIFIED = "NOTIFIED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    VERIFIED = "VERIFIED"
    FALSE_ALERT = "FALSE_ALERT"
    RESOLVED = "RESOLVED"


class IncidentAction(StrEnum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    VERIFY = "VERIFY"
    MARK_FALSE_ALERT = "MARK_FALSE_ALERT"
    RESOLVE = "RESOLVE"


class EvidenceObservation(BaseModel):
    posture: str = "unknown"
    surroundings: str = "unknown"
    uncertainty: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    generated_by: str = "mock"
    medical_severity: None = None  # intentionally never evaluated


class AuditEvent(BaseModel):
    time: datetime = Field(default_factory=utc_now)
    event: str
    actor: str
    from_status: IncidentStatus | None = None
    to_status: IncidentStatus


class Incident(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: str = "staged-camera-01"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: IncidentStatus = IncidentStatus.DETECTED
    confidence: float = Field(ge=0, le=1)
    simulated: bool = True
    observation: EvidenceObservation | None = None
    notification_sent: bool = False
    history: list[AuditEvent] = Field(default_factory=list)


class NewIncident(BaseModel):
    source_id: str = Field(default="staged-camera-01", min_length=1, max_length=128)
    confidence: float = Field(default=0.82, ge=0, le=1)


class ReviewRequest(BaseModel):
    action: IncidentAction
    actor: str = Field(min_length=1, max_length=80)
