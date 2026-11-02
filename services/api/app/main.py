"""Local-only FastAPI MVP foundation for VIIL Sentinel."""
import hmac
import sqlite3
import time
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.agent import InvalidTransition, human_review
from app.candidate_ingest import (
    DEFAULT_LEDGER_PATH,
    MAX_BODY_BYTES,
    CandidateLedger,
    CandidateReceipt,
    IntakeConflict,
    IntakeRateExceeded,
    IntakeStorageFull,
    InvalidEdgeCandidate,
    parse_candidate,
    verify_candidate_auth,
)
from app.caregiver_inbox import CaregiverInbox, build_inbox
from app.config import Settings, get_settings
from app.evidence_audit import EvidenceAuditFailure, EvidenceAuditReceipt
from app.evidence_registry import (
    EvidenceRegistryRecord,
    EvidenceRegistryRejected,
    EvidenceRegistryUnavailable,
    SyntheticEvidenceRegistry,
)
from app.local_security import is_local_test_client
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
    candidate_ledger = CandidateLedger(
        Path(config.edge_candidate_ledger_path)
        if config.edge_candidate_ledger_path else DEFAULT_LEDGER_PATH
    )

    audit_key = config.evidence_audit_anchor_secret
    evidence_registry = SyntheticEvidenceRegistry(
        candidate_ledger.path,
        anchor_required=config.evidence_audit_anchor_required,
        anchor_path=(
            Path(config.evidence_audit_anchor_path)
            if config.evidence_audit_anchor_path else None
        ),
        anchor_secret=(
            audit_key.get_secret_value().encode("utf-8") if audit_key else None
        ),
    )

    def authorize_caregiver_read(request: Request) -> None:
        """Shared loopback and independent-token check for readonly caregiver views."""
        configured = config.caregiver_inbox_token
        token = configured.get_secret_value() if configured else ""
        signer = config.edge_candidate_hmac_secret
        if (len(token.encode("utf-8")) < 32 or (
            signer is not None and token == signer.get_secret_value()
        )):
            raise HTTPException(503, "Caregiver views require an independent secret")
        if not is_local_test_client(request):
            raise HTTPException(403, "Caregiver views are loopback-only")
        headers = request.headers.getlist("authorization")
        if len(headers) != 1 or not headers[0].startswith("Bearer "):
            raise HTTPException(401, "Caregiver bearer token required")
        supplied = headers[0][7:]
        if not 32 <= len(supplied.encode("utf-8")) <= 160 or not hmac.compare_digest(
            supplied, token
        ):
            raise HTTPException(401, "Invalid caregiver bearer token")

    @app.post(
        "/api/v1/edge/candidates",
        response_model=CandidateReceipt,
        status_code=201,
    )
    async def receive_synthetic_candidate(request: Request, response: Response) -> CandidateReceipt:
        """HMAC-authenticated metadata-only ingestion, closed to any real camera."""
        if not config.edge_candidate_ingest_enabled:
            raise HTTPException(404, "Synthetic candidate intake is disabled")
        key = config.edge_candidate_hmac_secret
        secret = key.get_secret_value().encode("utf-8") if key else b""
        source = config.edge_candidate_source_id
        if len(secret) < 32 or not source.startswith("synthetic-"):
            raise HTTPException(503, "Synthetic intake is not safely configured")
        if not is_local_test_client(request):
            raise HTTPException(403, "Synthetic intake is loopback-only")
        if request.headers.get("content-type") != "application/json":
            raise HTTPException(415, "JSON content type is required")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise HTTPException(413, "Candidate metadata exceeds size limit")
        source_header = request.headers.getlist("x-viil-source-id")
        timestamp_header = request.headers.getlist("x-viil-timestamp")
        signature_header = request.headers.getlist("x-viil-signature")
        if any(len(values) != 1 for values in (
            source_header, timestamp_header, signature_header,
        )):
            raise HTTPException(401, "Candidate authentication required")
        now = int(time.time())
        if not verify_candidate_auth(
            secret=secret,
            configured_source=source,
            header_source=source_header[0],
            header_timestamp=timestamp_header[0],
            header_signature=signature_header[0],
            body=bytes(body),
            now_seconds=now,
        ):
            raise HTTPException(401, "Invalid or expired source signature")
        try:
            candidate = parse_candidate(bytes(body))
        except InvalidEdgeCandidate:
            raise HTTPException(422, "Invalid Edge v1 metadata") from None
        if candidate.source_id != source_header[0]:
            raise HTTPException(403, "Candidate source does not match registered signer")
        try:
            receipt = candidate_ledger.accept(candidate, raw=bytes(body), now_seconds=now)
        except IntakeConflict:
            raise HTTPException(409, "Candidate event ID was already used") from None
        except IntakeRateExceeded:
            raise HTTPException(429, "Synthetic intake rate cap exceeded") from None
        except (IntakeStorageFull, sqlite3.DatabaseError, OSError):
            raise HTTPException(503, "Synthetic intake ledger unavailable") from None
        response.status_code = 200 if receipt.duplicate else 201
        return receipt

    @app.get("/api/v1/caregiver/inbox", response_model=CaregiverInbox)
    def caregiver_inbox(request: Request, response: Response) -> CaregiverInbox:
        """Explicit local caregiver token; read-only synthetic metadata."""
        if not config.caregiver_inbox_enabled:
            raise HTTPException(404, "Caregiver inbox is disabled")
        authorize_caregiver_read(request)
        response.headers["Cache-Control"] = "no-store"
        try:
            return build_inbox(
                ledger_path=candidate_ledger.path,
                source_id=config.edge_candidate_source_id,
            )
        except (sqlite3.DatabaseError, OSError, ValueError):
            raise HTTPException(503, "Caregiver inbox data unavailable") from None

    @app.get(
        "/api/v1/caregiver/evidence/{event_id}",
        response_model=EvidenceRegistryRecord,
    )
    def caregiver_evidence(
        event_id: UUID, request: Request, response: Response,
    ) -> EvidenceRegistryRecord:
        """Metadata ONLY; no PNG/body/consent grant, never calls the model."""
        if not config.evidence_registry_enabled:
            raise HTTPException(404, "Synthetic evidence registry reads disabled")
        authorize_caregiver_read(request)
        response.headers["Cache-Control"] = "no-store"
        try:
            record = evidence_registry.get(
                event_id=event_id, source_id=config.edge_candidate_source_id,
            )
        except (EvidenceRegistryRejected, EvidenceAuditFailure):
            raise HTTPException(503, "Synthetic evidence integrity failed") from None
        except EvidenceRegistryUnavailable:
            raise HTTPException(503, "Synthetic evidence registry unavailable") from None
        if record is None:
            raise HTTPException(404, "Synthetic evidence record not found")
        return record

    @app.get(
        "/api/v1/caregiver/evidence/{event_id}/audit",
        response_model=EvidenceAuditReceipt,
    )
    def caregiver_evidence_audit(
        event_id: UUID, request: Request, response: Response,
    ) -> EvidenceAuditReceipt:
        """Read validated synthetic-only audit metadata, never upload permission."""
        if not config.evidence_registry_enabled:
            raise HTTPException(404, "Synthetic evidence audit is disabled")
        authorize_caregiver_read(request)
        response.headers["Cache-Control"] = "no-store"
        try:
            record = evidence_registry.get_audit(
                event_id=event_id, source_id=config.edge_candidate_source_id,
            )
        except (EvidenceRegistryRejected, EvidenceAuditFailure):
            raise HTTPException(503, "Synthetic audit integrity failed") from None
        except EvidenceRegistryUnavailable:
            raise HTTPException(503, "Synthetic evidence audit unavailable") from None
        if record is None:
            raise HTTPException(404, "Synthetic audit record not found")
        return record

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "DEMO" if config.demo_mode else "PRODUCTION_DISABLED"}

    @app.get("/api/v1/incidents", response_model=list[Incident])
    def list_incidents(request: Request) -> list[Incident]:
        if not config.demo_mode:
            raise HTTPException(403, "Incident reads require scoped authentication")
        if not is_local_test_client(request):
            raise HTTPException(403, "Demo incident feed is local-only")
        return repository.list()

    @app.get("/api/v1/incidents/{incident_id}", response_model=Incident)
    def get_incident(request: Request, incident_id: UUID) -> Incident:
        if not config.demo_mode:
            raise HTTPException(403, "Incident reads require scoped authentication")
        if not is_local_test_client(request):
            raise HTTPException(403, "Demo incident details are local-only")
        incident = repository.get(incident_id)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        return incident

    @app.post("/api/v1/incidents/demo", response_model=Incident, status_code=201)
    async def create_demo_incident(request: Request, payload: NewIncident) -> Incident:
        if not config.demo_mode:
            raise HTTPException(403, "Demo event creation is disabled")
        if not is_local_test_client(request):
            raise HTTPException(403, "Demo event creation is local-only")
        return await service.create_demo(payload)

    @app.post("/api/v1/incidents/{incident_id}/review", response_model=Incident)
    def review_incident(request: Request, incident_id: UUID, payload: ReviewRequest) -> Incident:
        if not config.demo_mode:
            raise HTTPException(403, "Unauthenticated review is disabled outside demo mode")
        if not is_local_test_client(request):
            raise HTTPException(403, "Demo incident review is local-only")
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
