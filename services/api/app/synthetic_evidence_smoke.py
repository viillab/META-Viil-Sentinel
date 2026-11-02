"""One-command OFFLINE synthetic event-bound image and candidate demo.

Real localhost TCP to FastAPI, real Member 1 Python detector, pinned synthetic
trace -> a deterministic schematic PNG, strict SHA256 manifest and a MOCK
Meta JSON contract check. NO paid Meta requests or real-person media.
"""
import json
import secrets
import tempfile
import time
from pathlib import Path

import httpx
from pydantic import SecretStr

from app.candidate_ingest import sign_candidate
from app.config import Settings
from app.edge_emitter_e2e import (
    SYNTHETIC_SOURCE,
    EdgeProducerSmokeError,
    edge_candidates_from_trace,
)
from app.evidence_registry import SyntheticEvidenceRegistry
from app.local_http_demo import loopback_http_server
from app.main import create_app
from app.meta_first_contract import TrustedMetaCallContext, meta_first_route
from app.meta_live import MODEL, read_checked_response
from app.synthetic_evidence import (
    build_offline_pose_meta_request,
    build_synthetic_evidence,
    verify_synthetic_evidence,
)


def run_synthetic_event_bound_smoke() -> dict[str, object]:
    fall = edge_candidates_from_trace("fall")
    sitting = edge_candidates_from_trace("sitting")
    if len(fall) != 1 or sitting:
        raise EdgeProducerSmokeError("Pinned synthetic detector output changed")
    source_bytes = fall[0]
    event_id = json.loads(source_bytes)["event_id"]

    edge_key, caregiver_key = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    with tempfile.TemporaryDirectory(prefix="viil-synthetic-evidence-") as tmp:
        settings = Settings(
            _env_file=None,
            meta_provider="mock",
            meta_model_api_key=None,
            meta_live_enabled=False,
            demo_mode=False,
            edge_candidate_ingest_enabled=True,
            edge_candidate_source_id=SYNTHETIC_SOURCE,
            edge_candidate_hmac_secret=SecretStr(edge_key),
            edge_candidate_ledger_path=str(Path(tmp) / "events.sqlite3"),
            caregiver_inbox_enabled=True,
            caregiver_inbox_token=SecretStr(caregiver_key),
            evidence_registry_enabled=True,
        )
        with loopback_http_server(create_app(settings)) as base_url:  # noqa: SIM117
            with httpx.Client(
                base_url=base_url, trust_env=False, timeout=3,
                follow_redirects=False,
            ) as client:
                timestamp = str(int(time.time()))
                signed_headers = {
                    "Content-Type": "application/json",
                    "X-VIIL-Source-Id": SYNTHETIC_SOURCE,
                    "X-VIIL-Timestamp": timestamp,
                    "X-VIIL-Signature": sign_candidate(
                        edge_key.encode("utf-8"),
                        source=SYNTHETIC_SOURCE, timestamp=timestamp,
                        body=source_bytes,
                    ),
                }
                receipt = client.post(
                    "/api/v1/edge/candidates",
                    content=source_bytes, headers=signed_headers,
                )
                if (
                    receipt.status_code != 201
                    or receipt.json().get("event_id") != event_id
                ):
                    raise EdgeProducerSmokeError("Candidate was not received under its UUID")

                # The manifest is constructed from the SAME exact raw HTTP
                # candidate bytes that were signed and accepted by FastAPI.
                bundle = build_synthetic_evidence(source_bytes)
                verify_synthetic_evidence(source_bytes, bundle)
                if str(bundle.manifest.event_id) != receipt.json()["event_id"]:
                    raise EdgeProducerSmokeError("Evidence UUID differs from accepted event")
                registry = SyntheticEvidenceRegistry(Path(tmp) / "events.sqlite3")
                registered, duplicate = registry.register(
                    raw_candidate=source_bytes, evidence=bundle,
                )
                repeated, duplicate_again = registry.register(
                    raw_candidate=source_bytes, evidence=bundle,
                )
                registry_read = client.get(
                    "/api/v1/caregiver/evidence/" + event_id,
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                if not (
                    duplicate is False and duplicate_again is True
                    and registered == repeated
                    and registry_read.status_code == 200
                    and registry_read.headers.get("cache-control") == "no-store"
                    and registry_read.json()["event_id"] == event_id
                    and registry_read.json()["image_bytes_stored"] is False
                    and registry_read.json()["external_upload_authorized"] is False
                    and registry_read.json()["consent_state"] == "not_verified_for_real_media"
                    and registry_read.json()["meta_called"] is False
                ):
                    raise EdgeProducerSmokeError("Offline registry verification failed")
                offline_request = build_offline_pose_meta_request(source_bytes, bundle)
                if offline_request["model"] != MODEL:
                    raise EdgeProducerSmokeError("Offline model request mismatch")

                # Explicit MOCK provider response; the paid Meta client still
                # REFUSES this schematic and the 4-call local budget is frozen.
                response = {
                    "model": MODEL,
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({
                            "verdict": "uncertain",
                            "visible_observations": ["Three synthetic stick-pose panels"],
                            "uncertainties": ["No real-person video or temporal camera proof"],
                            "supporting_frame_indices": [],
                        })},
                    }],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                }
                assessment, _, _ = read_checked_response(response)
                route = meta_first_route(
                    assessment,
                    TrustedMetaCallContext(
                        provider="mock",
                        actual_provider_request_succeeded=False,
                        source_authenticated=True,
                        media_licensed_and_consented=True,
                        evidence_frame_count=3,
                        validated_evidence=False,
                    ),
                )
                inbox = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                rows = inbox.json().get("advisories", []) if inbox.status_code == 200 else []
                if not (
                    route.route == "require_follow_up"
                    and route.fall_confirmed is False
                    and route.emergency_dispatch_authorized is False
                    and len(rows) == 1
                    and rows[0]["advisory_id"] == event_id
                    and rows[0]["meta_provenance"] == "none"
                    and rows[0]["delivery_state"] == "not_sent"
                    and rows[0]["fall_confirmed"] is False
                    and rows[0]["simulated"] is True
                ):
                    raise EdgeProducerSmokeError("Synthetic image would be misrepresented")
    return {
        "status": "SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS",
        "edge_candidate_accepted_over_real_local_http": True,
        "candidate_event_id_matches_manifest": True,
        "candidate_sha256": bundle.manifest.candidate_sha256,
        "trace_sha256": bundle.manifest.trace_sha256,
        "image_sha256": bundle.manifest.image_sha256,
        "image_dimensions": [336, 112],
        "rendered_source_timestamps_ms": list(bundle.manifest.frame_timestamps_ms),
        "evidence_origin": bundle.manifest.image_origin,
        "offline_meta_request_prepared": True,
        "registry_same_signed_event_verified": True,
        "registry_read_via_local_http_verified": True,
        "registry_deduplicated": True,
        "registry_real_media_consent_verified": False,
        "registry_image_bytes_stored": False,
        "meta_response_was_mocked": True,
        "real_meta_api_called": False,
        "meta_budget_modified": False,
        "inbox_remains_unconfirmed_and_synthetic": True,
        "real_camera_media_processed": False,
        "real_person_media_sent": False,
        "images_persisted": False,
        "temporary_local_http_stopped": True,
        "temporary_sqlite_deleted": True,
    }


if __name__ == "__main__":
    print(json.dumps(run_synthetic_event_bound_smoke(), sort_keys=True))
