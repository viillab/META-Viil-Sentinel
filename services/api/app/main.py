"""Local-only FastAPI MVP foundation for VIIL Sentinel."""
from uuid import UUID
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.agent import InvalidTransition, human_review
from app.config import Settings, get_settings
from app.meta import provider_for
from app.models import Incident, NewIncident, ReviewRequest
from app.service import IncidentService
from app.store import IncidentRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    app = FastAPI(
        title="VIIL Sentinel API",
        version="0.1.0",
        description="LOCAL DEMO ONLY. Non-clinical simulated fall-incident orchestration.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    repository = IncidentRepository()
    service = IncidentService(repository, provider_for(config.meta_provider))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "DEMO" if config.demo_mode else "PRODUCTION_DISABLED"}

    @app.get("/api/v1/incidents", response_model=list[Incident])
    def list_incidents() -> list[Incident]:
        return repository.list()

    @app.get("/api/v1/incidents/{incident_id}", response_model=Incident)
    def get_incident(incident_id: UUID) -> Incident:
        incident = repository.get(incident_id)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        return incident

    @app.post("/api/v1/incidents/demo", response_model=Incident, status_code=201)
    async def create_demo_incident(payload: NewIncident) -> Incident:
        if not config.demo_mode:
            raise HTTPException(403, "Demo event creation is disabled")
        return await service.create_demo(payload)

    @app.post("/api/v1/incidents/{incident_id}/review", response_model=Incident)
    def review_incident(incident_id: UUID, payload: ReviewRequest) -> Incident:
        if not config.demo_mode:
            raise HTTPException(403, "Unauthenticated review is disabled outside demo mode")
        incident = repository.get(incident_id)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        try:
            updated = human_review(incident, payload)
        except InvalidTransition as error:
            raise HTTPException(409, str(error)) from error
        return repository.update(updated)

    return app


app = create_app()
