"""Explicit ephemeral repository. Replace with persistence before any non-demo deployment."""
from uuid import UUID
from threading import RLock
from app.models import Incident


class IncidentRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Incident] = {}
        self._lock = RLock()

    def add(self, incident: Incident) -> Incident:
        with self._lock:
            self._items[incident.id] = incident.model_copy(deep=True)
        return incident.model_copy(deep=True)

    def update(self, incident: Incident) -> Incident:
        with self._lock:
            if incident.id not in self._items:
                raise KeyError(str(incident.id))
            self._items[incident.id] = incident.model_copy(deep=True)
        return incident.model_copy(deep=True)

    def get(self, incident_id: UUID) -> Incident | None:
        with self._lock:
            incident = self._items.get(incident_id)
            return incident.model_copy(deep=True) if incident else None

    def list(self) -> list[Incident]:
        with self._lock:
            items = [item.model_copy(deep=True) for item in self._items.values()]
        return sorted(items, key=lambda item: item.created_at, reverse=True)
