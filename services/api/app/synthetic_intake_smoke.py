"""Single-command OFFLINE Edge v1 -> FastAPI -> SQLite smoke.

Uses a fake locally scoped signer, the canonical synthetic Member 1 fixture,
an in-process HTTP client and a temporary SQLite database. No real device,
public port, Meta API, credentials, email, notification or cloud calls.
"""
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import sign_candidate
from app.config import Settings
from app.main import create_app

SYNTHETIC_SOURCE = "synthetic-clip-01"
SMOKE_KEY = "test-only-ephemeral-synthetic-candidate-signer-not-a-real-secret"
SMOKE_CAREGIVER_TOKEN = "test-only-ephemeral-caregiver-readonly-token-separate-from-signer"
EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "edge-vision" / "examples" / "synthetic" / "candidate_v1.example.json"
)


def run_smoke() -> dict:
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert example["source_id"] == SYNTHETIC_SOURCE
    with tempfile.TemporaryDirectory(prefix="viil-edge-api-smoke-") as tmp:
        settings = Settings(
            _env_file=None,
            meta_provider="mock",
            demo_mode=False,
            meta_model_api_key=None,
            edge_candidate_ingest_enabled=True,
            edge_candidate_source_id=SYNTHETIC_SOURCE,
            edge_candidate_hmac_secret=SecretStr(SMOKE_KEY),
            edge_candidate_ledger_path=str(Path(tmp) / "candidate-test.sqlite3"),
            caregiver_inbox_enabled=True,
            caregiver_inbox_token=SecretStr(SMOKE_CAREGIVER_TOKEN),
        )
        app = create_app(settings)
        body = json.dumps(example, separators=(",", ":")).encode("utf-8")
        stamp = str(int(time.time()))

        def post(data: bytes) -> object:
            signature = sign_candidate(
                SMOKE_KEY.encode(),
                source=SYNTHETIC_SOURCE,
                timestamp=stamp,
                body=data,
            )
            return client.post(
                "/api/v1/edge/candidates",
                content=data,
                headers={
                    "content-type": "application/json",
                    "x-viil-source-id": SYNTHETIC_SOURCE,
                    "x-viil-timestamp": stamp,
                    "x-viil-signature": signature,
                },
            )

        with TestClient(app) as client:
            initial = post(body)
            repeated = post(body)
            unauthorized = client.post(
                "/api/v1/edge/candidates",
                content=body,
                headers={"content-type": "application/json"},
            )
            unsafe_data = {**example, "input_provenance": "authorized_local_camera"}
            unsafe = post(json.dumps(unsafe_data).encode("utf-8"))
            ordinary_reads = client.get("/api/v1/incidents")
            unauthenticated_inbox = client.get("/api/v1/caregiver/inbox")
            caregiver_inbox = client.get(
                "/api/v1/caregiver/inbox",
                headers={"Authorization": f"Bearer {SMOKE_CAREGIVER_TOKEN}"},
            )
            if not (
                initial.status_code == 201
                and repeated.status_code == 200
                and repeated.json()["duplicate"] is True
                and unauthorized.status_code == 401
                and unsafe.status_code == 422
                and ordinary_reads.status_code == 403
                and unauthenticated_inbox.status_code == 401
                and caregiver_inbox.status_code == 200
                and caregiver_inbox.headers["cache-control"] == "no-store"
                and caregiver_inbox.json()["access_scope"] == "authenticated_caregiver"
                and len(caregiver_inbox.json()["advisories"]) == 1
                and caregiver_inbox.json()["advisories"][0]["advisory_id"] == example["event_id"]
                and caregiver_inbox.json()["advisories"][0]["meta_provenance"] == "none"
                and caregiver_inbox.json()["advisories"][0]["delivery_state"] == "not_sent"
                and initial.json()["notification_sent"] is False
                and initial.json()["meta_called"] is False
                and initial.json()["confirmed_fall"] is False
            ):
                raise RuntimeError("Offline candidate intake smoke did not pass")
            return {
                "result": "OFFLINE_SYNTHETIC_INTAKE_PASS",
                "candidate_schema": example["schema_version"],
                "accepted_once": True,
                "deduplicated_on_retry": True,
                "unsigned_request_rejected": True,
                "real_camera_provenance_rejected": True,
                "non_demo_incident_read_rejected": True,
                "caregiver_inbox_schema": "viil.backend.caregiver_inbox.v1",
                "caregiver_readonly_projection_passed": True,
                "caregiver_inbox_auth_required": True,
                "meta_called": False,
                "caregiver_notification_sent": False,
                "real_camera_tested": False,
                "public_network_used": False,
                "storage": "temporary SQLite (removed after test)",
            }


if __name__ == "__main__":
    print(json.dumps(run_smoke(), sort_keys=True))
