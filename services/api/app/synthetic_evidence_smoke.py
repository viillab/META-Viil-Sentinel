"""One-command OFFLINE synthetic event-bound image and candidate demo.

Real localhost TCP to FastAPI, real Member 1 Python detector, pinned synthetic
trace -> a deterministic schematic PNG, strict SHA256 manifest and a MOCK
Meta JSON contract check. NO paid Meta requests or real-person media.
"""
import asyncio
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
from app.evidence_anchor import capture_checkpoint, verify_checkpoint
from app.evidence_registry import EvidenceRegistryRejected, SyntheticEvidenceRegistry
from app.local_http_demo import loopback_http_server
from app.main import create_app
from app.meta_budget import MetaBudget
from app.meta_copilot import (
    MetaCopilotUnavailable,
    build_offline_meta_planner_request,
    offline_proposal,
)
from app.meta_copilot_mock_transport import MockOnlyMetaPlanner
from app.meta_copilot_shadow_ledger import MetaCopilotShadowLedger
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
    anchor_key = secrets.token_urlsafe(48)
    with tempfile.TemporaryDirectory(prefix="viil-synthetic-evidence-") as tmp:
        checkpoint = Path(tmp) / "separate-anchor" / "signed-head.json"
        checkpoint.parent.mkdir()
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
            meta_copilot_preview_enabled=True,
            evidence_audit_anchor_required=True,
            evidence_audit_anchor_path=str(checkpoint),
            evidence_audit_anchor_secret=SecretStr(anchor_key),
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
                # Strict HTTP reads must fail closed UNTIL the independent
                # checkpoint is explicitly exported by the operator.
                header = {"Authorization": f"Bearer {caregiver_key}"}
                before_anchor = client.get(
                    "/api/v1/caregiver/evidence/" + event_id, headers=header,
                )
                copilot_before_anchor = client.get(
                    "/api/v1/caregiver/copilot/" + event_id, headers=header,
                )
                readiness_before_anchor = client.get(
                    "/api/v1/caregiver/copilot/" + event_id + "/readiness",
                    headers=header,
                )
                signed = capture_checkpoint(
                    db_path=Path(tmp) / "events.sqlite3",
                    checkpoint_path=checkpoint,
                    secret=anchor_key.encode("utf-8"),
                )
                checked = verify_checkpoint(
                    db_path=Path(tmp) / "events.sqlite3",
                    checkpoint_path=checkpoint,
                    secret=anchor_key.encode("utf-8"),
                )
                registry_read = client.get(
                    "/api/v1/caregiver/evidence/" + event_id,
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                audit_read = client.get(
                    "/api/v1/caregiver/evidence/" + event_id + "/audit",
                    headers={"Authorization": f"Bearer {caregiver_key}"},
                )
                copilot_read = client.get(
                    "/api/v1/caregiver/copilot/" + event_id, headers=header,
                )
                readiness_read = client.get(
                    "/api/v1/caregiver/copilot/" + event_id + "/readiness",
                    headers=header,
                )
                anchored_registry = SyntheticEvidenceRegistry(
                    Path(tmp) / "events.sqlite3", anchor_required=True,
                    anchor_path=checkpoint, anchor_secret=anchor_key.encode("utf-8"),
                )
                local_evidence = anchored_registry.get(
                    event_id=bundle.manifest.event_id, source_id=SYNTHETIC_SOURCE,
                )
                local_audit = anchored_registry.get_audit(
                    event_id=bundle.manifest.event_id, source_id=SYNTHETIC_SOURCE,
                )
                if local_evidence is None or local_audit is None:
                    raise EdgeProducerSmokeError("Missing anchored synthetic facts")
                planner_request = build_offline_meta_planner_request(
                    local_evidence, local_audit,
                )
                simulated_requests = []

                def mock_meta_planner(request):
                    simulated_requests.append(request)
                    payload = json.loads(request.content)
                    if (
                        request.method != "POST"
                        or request.url.host != "api.meta.ai"
                        or "authorization" in request.headers
                        or payload["response_format"]["json_schema"]["strict"] is not True
                        or "data:image" in request.content.decode("utf-8")
                    ):
                        raise EdgeProducerSmokeError("Unexpected mock Meta request contract")
                    return httpx.Response(200, json={
                        "model": "muse-spark-1.3",
                        "choices": [{
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": offline_proposal(
                                    bundle.manifest.event_id
                                ).model_dump_json(),
                            },
                        }],
                        "usage": {"prompt_tokens": 235, "completion_tokens": 84},
                    })

                mock_planner = MockOnlyMetaPlanner(
                    transport=httpx.MockTransport(mock_meta_planner),
                )
                shadow_ledger = MetaCopilotShadowLedger(
                    Path(tmp) / "private-shadow" / "runs.sqlite3",
                )
                budget_observer = MetaBudget(
                    path=Path(tmp) / "private-budget" / "spend.sqlite3",
                )
                mock_result = asyncio.run(
                    shadow_ledger.run_mock_once(
                        registry=anchored_registry,
                        event_id=bundle.manifest.event_id,
                        mock_planner=mock_planner,
                        budget=budget_observer,
                    ),
                )
                cached_result = asyncio.run(
                    MetaCopilotShadowLedger(shadow_ledger.path).run_mock_once(
                        registry=anchored_registry,
                        event_id=bundle.manifest.event_id,
                        mock_planner=mock_planner,
                        budget=budget_observer,
                    ),
                )
                if not (
                    duplicate is False and duplicate_again is True
                    and registered == repeated
                    and audit_read.status_code == 200
                    and audit_read.headers.get("cache-control") == "no-store"
                    and audit_read.json()["sequence"] == 1
                    and audit_read.json()["event_id"] == event_id
                    and audit_read.json()["chain_verified"] is True
                    and audit_read.json()["consent_state"] == "not_verified_for_real_media"
                    and audit_read.json()["external_upload_authorized"] is False
                    and audit_read.json()["meta_call_permitted"] is False
                    and before_anchor.status_code == 503
                    and copilot_before_anchor.status_code == 503
                    and readiness_before_anchor.status_code == 503
                    and readiness_read.status_code == 200
                    and readiness_read.json()["real_provider_allowed"] is False
                    and readiness_read.json()["meta_api_called"] is False
                    and readiness_read.json()["official_meta_billing_verified"] is False
                    and copilot_read.status_code == 200
                    and copilot_read.headers.get("cache-control") == "no-store"
                    and copilot_read.json()["event_id"] == event_id
                    and copilot_read.json()["mode"] == "offline_readonly_shadow"
                    and copilot_read.json()["meta_api_called"] is False
                    and copilot_read.json()["human_review_required"] is True
                    and copilot_read.json()["fall_confirmed"] is False
                    and len(copilot_read.json()["actions"]) == 3
                    and planner_request["model"] == "muse-spark-1.3"
                    and planner_request["response_format"]["json_schema"]["strict"] is True
                    and mock_result.total_mock_provider_calls_for_event == 1
                    and mock_result.outcome == "mock_completed"
                    and mock_result.mock_provider_invoked_this_call is True
                    and mock_result.meta_api_called is False
                    and mock_result.budget_modified is False
                    and mock_result.readiness.real_provider_allowed is False
                    and mock_result.readiness.meta_budget_calls_observed == 0
                    and cached_result.outcome == "duplicate_from_shadow_cache"
                    and cached_result.mock_provider_invoked_this_call is False
                    and cached_result.preview == mock_result.preview
                    and mock_result.preview.event_id == bundle.manifest.event_id
                    and mock_result.preview.model_has_executed_tools is False
                    and len(simulated_requests) == 1
                    and len(mock_result.preview.actions) == 3
                    and signed == checked
                    and signed.record_count == 1
                    and registry_read.status_code == 200
                    and registry_read.headers.get("cache-control") == "no-store"
                    and registry_read.json()["event_id"] == event_id
                    and registry_read.json()["image_bytes_stored"] is False
                    and registry_read.json()["external_upload_authorized"] is False
                    and registry_read.json()["consent_state"] == "not_verified_for_real_media"
                    and registry_read.json()["meta_called"] is False
                ):
                    raise EdgeProducerSmokeError("Offline registry verification failed")
                # Even the fully coherent SQLite audit must not be trusted
                # when its separate HMAC checkpoint is changed.
                checkpoint.write_bytes(b'{"untrusted":true}')
                forged_read = client.get(
                    "/api/v1/caregiver/evidence/" + event_id, headers=header,
                )
                forged_audit = client.get(
                    "/api/v1/caregiver/evidence/" + event_id + "/audit",
                    headers=header,
                )
                forged_copilot = client.get(
                    "/api/v1/caregiver/copilot/" + event_id, headers=header,
                )
                forged_readiness = client.get(
                    "/api/v1/caregiver/copilot/" + event_id + "/readiness",
                    headers=header,
                )
                if (
                    forged_read.status_code != 503 or forged_audit.status_code != 503
                    or forged_copilot.status_code != 503
                    or forged_readiness.status_code != 503
                ):
                    raise EdgeProducerSmokeError("Independent anchor corruption not detected")
                try:
                    asyncio.run(shadow_ledger.run_mock_once(
                        registry=anchored_registry,
                        event_id=bundle.manifest.event_id,
                        mock_planner=mock_planner,
                        budget=budget_observer,
                    ))
                except (MetaCopilotUnavailable, EvidenceRegistryRejected):
                    pass
                else:
                    raise EdgeProducerSmokeError("Mock model bypassed damaged signed anchor")
                if len(simulated_requests) != 1:
                    raise EdgeProducerSmokeError("Mock model retried after evidence corruption")
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
        "audit_read_via_local_http_verified": True,
        "audit_chain_verified": True,
        "independent_hmac_audit_anchor_verified": True,
        "read_without_anchor_rejected": True,
        "tampered_independent_anchor_rejected_over_http": True,
        "audit_idempotent_one_registration_entry": True,
        "consent_gate_real_media_upload_blocked": True,
        "audit_never_permits_meta_calls": True,
        "meta_copilot_offline_preview_verified_over_http": True,
        "meta_copilot_workplan_tasks": 3,
        "meta_copilot_no_anchor_rejected": True,
        "meta_copilot_corrupt_anchor_rejected": True,
        "meta_copilot_model_request_prepared_not_sent": True,
        "meta_copilot_mock_provider_contract_verified": True,
        "meta_copilot_mock_provider_rejected_after_anchor_corruption": True,
        "meta_copilot_mock_provider_calls": 1,
        "shadow_ledger_one_mock_call_per_event": True,
        "shadow_ledger_duplicate_cached": True,
        "shadow_ledger_readiness_denies_live_meta": True,
        "shadow_readiness_verified_over_local_http": True,
        "shadow_readiness_rejects_corrupt_anchor_over_http": True,
        "shadow_ledger_cache_invalidated_by_bad_anchor": True,
        "shadow_budget_ledger_unmodified": True,
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
