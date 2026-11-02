"""A real-loopback HTTP demonstration of the Member1 synthetic Edge handoff.

Uses a briefly-lived ephemeral 127.0.0.1 TCP socket, the actual Edge CLI,
signed v1 bytes, SQLite, and the guarded caregiver API. Never forwards real
data, credentials, camera content or any Meta model API request.
"""
import json
import secrets
import socket
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from pydantic import SecretStr

from app.candidate_ingest import sign_candidate
from app.config import Settings
from app.edge_emitter_e2e import (
    SYNTHETIC_SOURCE,
    EdgeProducerSmokeError,
    edge_candidates_from_trace,
)
from app.main import create_app

LOOPBACK_HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 8.0
SERVER_SHUTDOWN_SECONDS = 8.0


@contextmanager
def loopback_http_server(app: object) -> Iterator[str]:
    """Bind a random loopback-only port; stop and close socket on all outcomes."""
    listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listening.bind((LOOPBACK_HOST, 0))
        listening.listen(8)
        port = listening.getsockname()[1]
        config = uvicorn.Config(
            app,
            host=LOOPBACK_HOST,
            port=port,
            log_level="critical",
            access_log=False,
            lifespan="off",
            proxy_headers=False,
            server_header=False,
            timeout_keep_alive=1,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listening]},
            name="viil-local-http-synthetic-smoke",
            daemon=True,
        )
        thread.start()
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise EdgeProducerSmokeError("Loopback HTTP demo did not start")
                time.sleep(0.025)
            yield f"http://{LOOPBACK_HOST}:{port}"
        finally:
            server.should_exit = True
            thread.join(SERVER_SHUTDOWN_SECONDS)
            if thread.is_alive():
                raise EdgeProducerSmokeError("Loopback HTTP demo did not shut down")
    finally:
        listening.close()


def run_local_http_demo() -> dict[str, object]:
    """Validate the genuine TCP route, not TestClient or a production service."""
    generated = edge_candidates_from_trace("fall")
    sitting = edge_candidates_from_trace("sitting")
    if len(generated) != 1 or sitting:
        raise EdgeProducerSmokeError("Unexpected synthetic Edge detector output")
    source_event = json.loads(generated[0])

    # Secrets exist only in this Python process and are random on every run.
    # Never read .env: the real user's Meta API key is not needed.
    edge_key = secrets.token_urlsafe(48)
    caregiver_key = secrets.token_urlsafe(48)
    with tempfile.TemporaryDirectory(prefix="viil-local-http-synthetic-") as folder:
        settings = Settings(
            _env_file=None,
            meta_provider="mock",
            meta_model_api_key=None,
            meta_live_enabled=False,
            demo_mode=False,
            edge_candidate_ingest_enabled=True,
            edge_candidate_source_id=SYNTHETIC_SOURCE,
            edge_candidate_hmac_secret=SecretStr(edge_key),
            edge_candidate_ledger_path=str(Path(folder) / "synthetic.sqlite3"),
            caregiver_inbox_enabled=True,
            caregiver_inbox_token=SecretStr(caregiver_key),
        )
        # Deliberate nested scopes keep the HTTP client closed before stopping the server.
        with loopback_http_server(create_app(settings)) as base_url:  # noqa: SIM117
            with httpx.Client(
                base_url=base_url,
                trust_env=False,
                timeout=3.0,
                follow_redirects=False,
            ) as client:
                health = client.get("/health")
                initial_inbox = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                stamp = str(int(time.time()))
                signature = sign_candidate(
                    edge_key.encode("utf-8"),
                    source=SYNTHETIC_SOURCE,
                    timestamp=stamp,
                    body=generated[0],
                )
                signed_headers = {
                    "Content-Type": "application/json",
                    "X-VIIL-Source-Id": SYNTHETIC_SOURCE,
                    "X-VIIL-Timestamp": stamp,
                    "X-VIIL-Signature": signature,
                }
                created = client.post(
                    "/api/v1/edge/candidates",
                    content=generated[0], headers=signed_headers,
                )
                replay = client.post(
                    "/api/v1/edge/candidates",
                    content=generated[0], headers=signed_headers,
                )
                forged = client.post(
                    "/api/v1/edge/candidates",
                    content=generated[0],
                    headers={**signed_headers, "X-VIIL-Signature": "sha256=" + "0" * 64},
                )
                missing_auth = client.get("/api/v1/caregiver/inbox")
                wrong_auth = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={"Authorization": f"Bearer {edge_key}"},
                )
                inbox = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                malicious_origin = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={
                        "Authorization": f"Bearer {caregiver_key}",
                        "Origin": "https://untrusted.example",
                    },
                )
                demo_post = client.post("/api/v1/incidents/demo", json={})
                advisories = (
                    inbox.json().get("advisories", []) if inbox.status_code == 200 else []
                )
                if not (
                    health.status_code == 200
                    and health.json()["mode"] == "PRODUCTION_DISABLED"
                    and initial_inbox.status_code == 200
                    and initial_inbox.json()["advisories"] == []
                    and created.status_code == 201
                    and created.json()["event_id"] == source_event["event_id"]
                    and created.json()["meta_called"] is False
                    and created.json()["notification_sent"] is False
                    and replay.status_code == 200
                    and replay.json()["duplicate"] is True
                    and forged.status_code == 401
                    and missing_auth.status_code == 401
                    and wrong_auth.status_code == 401
                    and inbox.status_code == 200
                    and inbox.headers.get("cache-control") == "no-store"
                    and len(advisories) == 1
                    and advisories[0]["advisory_id"] == source_event["event_id"]
                    and advisories[0]["simulated"] is True
                    and advisories[0]["fall_confirmed"] is False
                    and advisories[0]["meta_provenance"] == "none"
                    and advisories[0]["delivery_state"] == "not_sent"
                    and "access-control-allow-origin" not in malicious_origin.headers
                    and demo_post.status_code == 403
                ):
                    raise EdgeProducerSmokeError("Local HTTP Edge->Inbox acceptance failed")
    return {
        "result": "LOCAL_TCP_HTTP_EDGE_TO_INBOX_PASS",
        "transport": "ephemeral 127.0.0.1 TCP HTTP",
        "actual_edge_python_emitter": True,
        "signed_edge_candidate_accepted": True,
        "sitting_emits_zero_candidates": True,
        "deduplication_verified": True,
        "caregiver_read_only_inbox_verified": True,
        "unsigned_and_forged_requests_rejected": True,
        "untrusted_browser_origin_rejected_by_cors": True,
        "demo_incidents_disabled": True,
        "server_stopped": True,
        "temporary_sqlite_removed": True,
        "real_camera_used": False,
        "meta_api_called": False,
        "notifications_sent": False,
        "caregiver_production_login_enabled": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_local_http_demo(), sort_keys=True))
