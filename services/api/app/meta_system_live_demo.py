"""One opt-in, real Meta vision call inside a safe local Edge->Backend demo.

Only fixed synthetic pose traces are ingested by FastAPI and only an
independently generated uniform-color non-person PNG is uploaded to Meta.
The PNG is NOT Edge fall evidence. The Meta result is informational test
telemetry only and never becomes an inbox advisory or alert.
"""
import argparse
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
from app.local_http_demo import loopback_http_server
from app.main import create_app
from app.meta_budget import MetaBudget, MetaBudgetExceeded
from app.meta_live import (
    MetaLiveDisabled,
    MetaProviderUnavailable,
    MetaSyntheticVisionClient,
    synthetic_png,
)

META_INPUT_PRICE_PER_M = 1.25
META_OUTPUT_PRICE_PER_M = 4.25


async def run_live_synthetic_system(
    *,
    api_key: str,
    budget: MetaBudget,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    """Trace -> signed local TCP API -> bounded live Meta -> safe read-only inbox."""
    fall_events = edge_candidates_from_trace("fall")
    sitting_events = edge_candidates_from_trace("sitting")
    if len(fall_events) != 1 or sitting_events:
        raise EdgeProducerSmokeError("Unexpected synthetic detector output")
    candidate = json.loads(fall_events[0])
    assert candidate["simulated"] is True

    edge_secret = secrets.token_urlsafe(48)
    caregiver_secret = secrets.token_urlsafe(48)
    with tempfile.TemporaryDirectory(prefix="viil-meta-live-integration-") as tmp:
        config = Settings(
            _env_file=None,
            demo_mode=False,
            meta_provider="mock",  # Backend routes can NEVER spend or call Meta.
            meta_model_api_key=None,
            meta_live_enabled=False,
            edge_candidate_ingest_enabled=True,
            edge_candidate_source_id=SYNTHETIC_SOURCE,
            edge_candidate_hmac_secret=SecretStr(edge_secret),
            edge_candidate_ledger_path=str(Path(tmp) / "synthetic.sqlite3"),
            caregiver_inbox_enabled=True,
            caregiver_inbox_token=SecretStr(caregiver_secret),
        )
        # Keep client lifetime inside server lifetime; release client first.
        with loopback_http_server(create_app(config)) as base_url:  # noqa: SIM117
            # Don't use an environment proxy, external redirects, or any
            # persisted API secrets for localhost transport.
            with httpx.Client(
                base_url=base_url,
                timeout=3, trust_env=False, follow_redirects=False,
            ) as client:
                stamp = str(int(time.time()))
                headers = {
                    "content-type": "application/json",
                    "x-viil-source-id": SYNTHETIC_SOURCE,
                    "x-viil-timestamp": stamp,
                    "x-viil-signature": sign_candidate(
                        edge_secret.encode("utf-8"),
                        source=SYNTHETIC_SOURCE,
                        timestamp=stamp,
                        body=fall_events[0],
                    ),
                }
                inserted = client.post(
                    "/api/v1/edge/candidates",
                    content=fall_events[0],
                    headers=headers,
                )
                if (
                    inserted.status_code != 201
                    or inserted.json().get("event_id") != candidate["event_id"]
                ):
                    raise EdgeProducerSmokeError(
                        "Signed local Edge candidate was not accepted"
                    )
                # No Meta inference is made until signed local intake works.
                meta = MetaSyntheticVisionClient(
                    api_key=api_key,
                    live_enabled=True,
                    budget=budget,
                    transport=transport,
                )
                model_result = await meta.assess(image=synthetic_png())

                if (
                    model_result.route.route != "require_follow_up"
                    or model_result.route.fall_confirmed
                    or model_result.route.emergency_dispatch_authorized
                ):
                    raise EdgeProducerSmokeError(
                        "Unverified synthetic probe must require follow-up"
                    )
                feed = client.get(
                    "/api/v1/caregiver/inbox",
                    headers={"Authorization": f"Bearer {caregiver_secret}"},
                )
                rows = (
                    feed.json().get("advisories", [])
                    if feed.status_code == 200 else []
                )
                if (
                    len(rows) != 1
                    or rows[0]["advisory_id"] != candidate["event_id"]
                    or rows[0]["simulated"] is not True
                    or rows[0]["meta_provenance"] != "none"
                    or rows[0]["delivery_state"] != "not_sent"
                    or rows[0]["fall_confirmed"] is not False
                    or rows[0]["emergency_dispatch_authorized"] is not False
                ):
                    raise EdgeProducerSmokeError(
                        "Inbox incorrectly promoted the synthetic Meta probe"
                    )

    input_count, output_count = (
        model_result.prompt_tokens,
        model_result.completion_tokens,
    )
    return {
        "status": "LIVE_META_SYSTEM_SYNTHETIC_INTEGRATION_PASS",
        "provider": "meta_model_api",
        "model": model_result.model,
        "api_call_attempt_number": model_result.local_call_number,
        "actual_meta_response_validated": True,
        "meta_input_is_canonical_solid_png_not_edge_evidence": True,
        "edge_candidate_accepted_over_real_local_tcp": True,
        "edge_source_timestamp_ms": candidate["source_timestamp_ms"],
        "edge_score_is_uncalibrated_heuristic": True,
        "sitting_generated_no_candidate": True,
        "meta_verdict": model_result.assessment.verdict.value,
        "meta_route": model_result.route.route.value,
        "caregiver_inbox_remains_synthetic_without_live_meta_claim": True,
        "fall_confirmed": False,
        "notifications_sent": False,
        "emergency_dispatch_authorized": False,
        "temporary_http_server_stopped": True,
        "temporary_sqlite_removed": True,
        "real_people_or_camera_frames_sent": 0,
        "prompt_tokens": input_count,
        "completion_tokens": output_count,
        "upper_estimated_token_charge_usd": (
            round(
                input_count * META_INPUT_PRICE_PER_M / 1_000_000
                + output_count * META_OUTPUT_PRICE_PER_M / 1_000_000, 6
            )
            if input_count is not None and output_count is not None
            else None
        ),
        "cumulative_conservative_local_reservation_usd": (
            model_result.reserved_micro_usd / 1_000_000
        ),
        "production_fall_detection_verified": False,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in ONE actual Meta Model API call in synthetic backend smoke"
    )
    parser.add_argument("--live-once", action="store_true")
    parser.add_argument("--approve-two-extra-tests", action="store_true")
    args = parser.parse_args()
    if not args.live_once or not args.approve_two_extra_tests:
        print(json.dumps({
            "mode": "OFFLINE_NO_META_BILLING",
            "required_flags": ["--live-once", "--approve-two-extra-tests"],
            "sent_request": False,
        }))
        return 0
    config = Settings()
    secret = config.meta_model_api_key
    budget = MetaBudget(approved_extra_tests=True)
    try:
        report = await run_live_synthetic_system(
            api_key=secret.get_secret_value() if secret else "",
            budget=budget,
        )
    except (MetaLiveDisabled, MetaProviderUnavailable, MetaBudgetExceeded,
            EdgeProducerSmokeError, httpx.HTTPError, OSError, ValueError) as exc:
        # Never forward provider HTTP response bodies or API keys.
        print(json.dumps({
            "status": "LIVE_META_SYSTEM_INTEGRATION_NOT_VERIFIED",
            "reason": str(exc),
            "attempts_total": budget.status()[0],
            "no_real_camera_used": True,
        }))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
