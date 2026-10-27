"""Orchestrates a clearly simulated event end-to-end without contacting rescue services."""
from app.agent import advance
from app.meta import IncidentInterpreter
from app.models import Incident, IncidentStatus, NewIncident
from app.store import IncidentRepository


class IncidentService:
    def __init__(self, store: IncidentRepository, interpreter: IncidentInterpreter) -> None:
        self.store = store
        self.interpreter = interpreter

    async def create_demo(self, payload: NewIncident) -> Incident:
        incident = self.store.add(
            Incident(source_id=payload.source_id, confidence=payload.confidence, simulated=True)
        )
        incident = advance(incident, IncidentStatus.ANALYZING, actor="orchestrator")
        self.store.update(incident)
        try:
            incident.observation = await self.interpreter.interpret(
                source_id=incident.source_id, confidence=incident.confidence
            )
        except Exception:  # noqa: BLE001  # Fail closed on unknown inference-provider failure.
            # Never fabricate a successful AI report when interpretation fails.
            incident.observation = None
        incident = advance(incident, IncidentStatus.REVIEW_REQUIRED, actor="orchestrator")
        self.store.update(incident)
        # 'sent' means added to the in-app demo feed, not SMS/email or emergency dispatch.
        incident.notification_sent = True
        incident = advance(incident, IncidentStatus.NOTIFIED, actor="notification-demo")
        return self.store.update(incident)
