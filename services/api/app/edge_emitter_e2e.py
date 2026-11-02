"""Real Member-1 Python detector -> signed Backend -> local Caregiver Inbox smoke.

Runs only two SHA256-pinned synthetic mathematical pose traces, not a video,
human frame, camera, external API, model upload or caregiver notification.
The Edge subprocess is isolated from developer API keys and credentials.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import EdgeCandidate, parse_candidate, sign_candidate
from app.config import Settings
from app.main import create_app
from app.synthetic_fixtures import (
    EDGE_ROOT,
    EXPECTED_TRACE_HASHES,
    SYNTHETIC_ROOT,
    SYNTHETIC_SOURCE,
)

EDGE_HMAC_SECRET = "fake-offline-edge-synthetic-signature-key-used-only-in-this-smoke"
CAREGIVER_TOKEN = "fake-offline-caregiver-read-token-independent-from-edge-hmac"
MAX_PRODUCER_OUTPUT_BYTES = 8192
MAX_TRACE_FILE_BYTES = 65536


class EdgeProducerSmokeError(RuntimeError):
    """The known synthetic producer changed, failed, or was unsafe to execute."""


def edge_candidates_from_trace(name: str, *, timeout_seconds: float = 10) -> list[bytes]:
    """Run the actual source-owned Edge v1 emitter on an immutable known fixture."""
    if name not in EXPECTED_TRACE_HASHES:
        raise EdgeProducerSmokeError("Only pinned synthetic fall/sitting fixtures are allowed")
    trace = SYNTHETIC_ROOT / f"{name}.jsonl"
    if trace.is_symlink() or not trace.is_file() or trace.stat().st_size > MAX_TRACE_FILE_BYTES:
        raise EdgeProducerSmokeError("Missing or unexpected synthetic trace")
    digest = hashlib.sha256(trace.read_bytes()).hexdigest()
    if digest != EXPECTED_TRACE_HASHES[name]:
        raise EdgeProducerSmokeError("Synthetic trace checksum mismatch")
    # Pass only OS/Python necessities; strip all Meta, camera and tenant secrets.
    # This producer imports only Python stdlib and the local sentinel_edge package.
    keep = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT"}
    isolated_env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    isolated_env["PYTHONPATH"] = str(EDGE_ROOT)
    isolated_env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated_env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "-m", "sentinel_edge.handoff_cli",
        "--trace", str(trace), "--source-id", SYNTHETIC_SOURCE,
        "--provenance", "synthetic_pose_trace",
    ]
    try:
        process = subprocess.run(
            cmd, cwd=EDGE_ROOT, env=isolated_env,
            capture_output=True, text=False, timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise EdgeProducerSmokeError("Offline Edge producer did not complete safely") from None
    if process.returncode != 0 or process.stderr or len(process.stdout) > MAX_PRODUCER_OUTPUT_BYTES:
        raise EdgeProducerSmokeError("Offline Edge producer failed or exceeded output limits")
    if not process.stdout:
        return []
    lines = process.stdout.splitlines()
    if len(lines) > 1:
        raise EdgeProducerSmokeError("Synthetic trace emitted too many events")
    for raw in lines:
        try:
            parsed = parse_candidate(raw)
        except ValueError:
            raise EdgeProducerSmokeError("Edge emitted an invalid v1 candidate") from None
        if parsed.source_id != SYNTHETIC_SOURCE:
            raise EdgeProducerSmokeError("Edge emitted an unregistered source")
    return lines


def run_edge_emitter_e2e() -> dict[str, object]:
    """Complete offline bridge; asserts the original synthetic fall/sitting behavior."""
    generated = edge_candidates_from_trace("fall")
    no_fall = edge_candidates_from_trace("sitting")
    if len(generated) != 1 or no_fall:
        raise EdgeProducerSmokeError("Frozen fall/sitting output behavior changed")
    event = EdgeCandidate.model_validate_json(generated[0], strict=True)
    expected = json.loads(
        (SYNTHETIC_ROOT / "candidate_v1.example.json").read_text(encoding="utf-8")
    )
    actual = json.loads(generated[0])
    if ({k: v for k, v in actual.items() if k != "event_id"}
        != {k: v for k, v in expected.items() if k != "event_id"}):
        raise EdgeProducerSmokeError("Producer deviated from the frozen example contract")

    with tempfile.TemporaryDirectory(prefix="viil-edge-producer-e2e-") as directory:
        settings = Settings(
            _env_file=None,
            meta_provider="mock",
            meta_model_api_key=None,
            meta_live_enabled=False,
            demo_mode=False,
            edge_candidate_ingest_enabled=True,
            edge_candidate_source_id=SYNTHETIC_SOURCE,
            edge_candidate_hmac_secret=SecretStr(EDGE_HMAC_SECRET),
            edge_candidate_ledger_path=str(Path(directory) / "receipts.sqlite3"),
            caregiver_inbox_enabled=True,
            caregiver_inbox_token=SecretStr(CAREGIVER_TOKEN),
        )
        app = create_app(settings)
        with TestClient(app) as client:
            before = client.get(
                "/api/v1/caregiver/inbox",
                headers={"authorization": f"Bearer {CAREGIVER_TOKEN}"},
            )
            timestamp = str(int(time.time()))

            def send(raw: bytes, *, signature: str | None = None):
                computed_signature = sign_candidate(
                    EDGE_HMAC_SECRET.encode("ascii"),
                    source=SYNTHETIC_SOURCE, timestamp=timestamp, body=raw,
                )
                return client.post(
                    "/api/v1/edge/candidates",
                    content=raw,
                    headers={
                        "content-type": "application/json",
                        "x-viil-source-id": SYNTHETIC_SOURCE,
                        "x-viil-timestamp": timestamp,
                        "x-viil-signature": signature or computed_signature,
                    },
                )

            received = send(generated[0])
            retried = send(generated[0])
            forged = send(generated[0], signature="sha256=" + "0" * 64)
            unsafe = {
                **actual, "simulated": False, "input_provenance": "authorized_local_camera",
            }
            reject_real_camera = send(json.dumps(unsafe).encode("utf-8"))
            unauthenticated = client.get("/api/v1/caregiver/inbox")
            inbox = client.get(
                "/api/v1/caregiver/inbox",
                headers={"authorization": f"Bearer {CAREGIVER_TOKEN}"},
            )
            advisories = inbox.json().get("advisories", []) if inbox.status_code == 200 else []
            if not (
                before.status_code == 200
                and before.json()["advisories"] == []
                and received.status_code == 201
                and retried.status_code == 200
                and retried.json()["duplicate"] is True
                and forged.status_code == 401
                and reject_real_camera.status_code == 422
                and unauthenticated.status_code == 401
                and inbox.status_code == 200
                and len(advisories) == 1
                and advisories[0]["advisory_id"] == actual["event_id"]
                and advisories[0]["source_id"] == SYNTHETIC_SOURCE
                and advisories[0]["stage"] == "edge_candidate"
                and advisories[0]["meta_provenance"] == "none"
                and advisories[0]["delivery_state"] == "not_sent"
                and advisories[0]["fall_confirmed"] is False
                and advisories[0]["simulated"] is True
                and received.json()["meta_called"] is False
                and received.json()["notification_sent"] is False
            ):
                raise EdgeProducerSmokeError("Actual Edge->Backend->Inbox bridge failed")
    return {
        "result": "REAL_EDGE_SYNTHETIC_TO_INBOX_PASS",
        "edge_emitter": "sentinel_edge.handoff_cli",
        "actual_python_detector": True,
        "source_data": "sha256-pinned synthetic pose only",
        "fall_candidate_count": len(generated),
        "sitting_candidate_count": len(no_fall),
        "fall_source_timestamp_ms": event.source_timestamp_ms,
        "uncalibrated_heuristic_score": event.detector_score,
        "signed_api_accepted": True,
        "duplicate_event_rejected_without_new_advisory": True,
        "forged_signature_rejected": True,
        "real_camera_provenance_rejected": True,
        "caregiver_metadata_inbox_verified": True,
        "caregiver_login_production_ready": False,
        "meta_api_called": False,
        "notifications_sent": False,
        "real_camera_used": False,
        "network_port_opened": False,
        "storage": "temporary SQLite removed",
    }


if __name__ == "__main__":
    print(json.dumps(run_edge_emitter_e2e(), sort_keys=True))
