"""Deterministic human-in-the-loop state machine, not autonomous rescue dispatch."""
from app.models import (
    AuditEvent, Incident, IncidentAction, IncidentStatus, ReviewRequest, utc_now,
)

ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.ANALYZING},
    IncidentStatus.ANALYZING: {IncidentStatus.REVIEW_REQUIRED},
    IncidentStatus.REVIEW_REQUIRED: {IncidentStatus.NOTIFIED},
    IncidentStatus.NOTIFIED: {IncidentStatus.ACKNOWLEDGED},
    IncidentStatus.ACKNOWLEDGED: {IncidentStatus.VERIFIED, IncidentStatus.FALSE_ALERT},
    IncidentStatus.VERIFIED: {IncidentStatus.RESOLVED},
    IncidentStatus.FALSE_ALERT: {IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: set(),
}
REVIEW_TRANSITIONS = {
    IncidentAction.ACKNOWLEDGE: IncidentStatus.ACKNOWLEDGED,
    IncidentAction.VERIFY: IncidentStatus.VERIFIED,
    IncidentAction.MARK_FALSE_ALERT: IncidentStatus.FALSE_ALERT,
    IncidentAction.RESOLVE: IncidentStatus.RESOLVED,
}


class InvalidTransition(ValueError):
    pass


def advance(incident: Incident, new_status: IncidentStatus, *, actor: str) -> Incident:
    if new_status not in ALLOWED_TRANSITIONS[incident.status]:
        raise InvalidTransition(f"Cannot transition from {incident.status} to {new_status}")
    previous = incident.status
    incident.status = new_status
    incident.updated_at = utc_now()
    incident.history.append(
        AuditEvent(
            event="state_transition",
            actor=actor,
            from_status=previous,
            to_status=new_status,
        )
    )
    return incident


def human_review(incident: Incident, request: ReviewRequest) -> Incident:
    if not request.actor.strip():
        raise InvalidTransition("A named human reviewer is required")
    return advance(incident, REVIEW_TRANSITIONS[request.action], actor=request.actor.strip())
