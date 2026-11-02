"""Safe one-shot CLI to verify the real Meta multimodal contract on generated pixels.

Default is offline; only --live-once sends ONE synthetic image to Meta.
Never pass a key on the command line. Never send camera or patient imagery.
"""
import argparse
import asyncio
import json

from app.config import Settings
from app.meta_budget import (
    MAX_APPROVED_LOCAL_CALLS,
    MAX_APPROVED_LOCAL_MICRO_USD,
    MAX_LOCAL_CALLS,
    MAX_LOCAL_MICRO_USD,
    RESERVATION_MICRO_USD,
    MetaBudget,
    MetaBudgetExceeded,
)
from app.meta_live import (
    MetaLiveDisabled,
    MetaProviderUnavailable,
    MetaSyntheticVisionClient,
    build_synthetic_request,
    synthetic_png,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Meta one-shot synthetic-only safety probe")
    parser.add_argument("--live-once", action="store_true",
                        help="Spend at most one reserved local API attempt")
    parser.add_argument(
        "--approve-two-extra-tests", action="store_true",
        help="Operator-authorized extension from 2 to 4 cumulative calls; at most $0.75 reserved",
    )
    args = parser.parse_args()
    config = Settings()
    budget = MetaBudget(approved_extra_tests=args.approve_two_extra_tests)
    calls, reserved_micro_usd = budget.status()
    if not args.live_once:
        request = build_synthetic_request(synthetic_png())
        print(json.dumps({
            "mode": "OFFLINE_NO_BILLING",
            "provider": "meta_model_api",
            "model": request["model"],
            "evidence": "SYNTHETIC_PNG_NO_PERSON",
            "messages_count": len(request["messages"]),
            "output_token_cap": request["max_completion_tokens"],
            "max_local_calls": (
                MAX_APPROVED_LOCAL_CALLS if args.approve_two_extra_tests else MAX_LOCAL_CALLS
            ),
            "per_attempt_reservation_usd": RESERVATION_MICRO_USD / 1_000_000,
            "max_local_budget_usd": (
                MAX_APPROVED_LOCAL_MICRO_USD
                if args.approve_two_extra_tests else MAX_LOCAL_MICRO_USD
            ) / 1_000_000,
            "already_reserved_usd": reserved_micro_usd / 1_000_000,
            "already_attempted_calls": calls,
            "key_configured": config.meta_model_api_key is not None,
            "sent_request": False,
        }, sort_keys=True))
        return 0
    key = config.meta_model_api_key
    client = MetaSyntheticVisionClient(
        api_key=key.get_secret_value() if key else None,
        live_enabled=True,  # explicit opt-in CLI flag required
        budget=budget,
    )
    try:
        result = await client.assess(image=synthetic_png())
    except (MetaBudgetExceeded, MetaLiveDisabled, MetaProviderUnavailable, ValueError) as exc:
        # Only safe, locally generated exception classes/messages appear here;
        # native provider errors, URLs and API keys never get printed.
        print(json.dumps({
            "status": "PROBE_NOT_VERIFIED", "reason": str(exc),
            "camera_frames_uploaded": 0, "real_person_evidence": False,
            "local_call_attempts": budget.status()[0],
        }))
        return 1
    print(json.dumps({
        "status": "LIVE_META_RESPONSE_VALIDATED",
        "provider": "meta_model_api",
        "model": result.model,
        "synthetic_only": True,
        "assessment_verdict": result.assessment.verdict,
        "route": result.route.route,
        "fall_confirmed": result.route.fall_confirmed,
        "emergency_dispatch_authorized": result.route.emergency_dispatch_authorized,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "reasoning_effort": "minimal",
        "estimated_upper_token_charge_usd": (
            round(
                result.prompt_tokens * 1.25 / 1_000_000
                + result.completion_tokens * 4.25 / 1_000_000, 6
            )
            if result.prompt_tokens is not None and result.completion_tokens is not None
            else None
        ),
        "local_call_attempts": result.local_call_number,
        "cumulative_conservative_reserved_usd": result.reserved_micro_usd / 1_000_000,
        "camera_frames_uploaded": 0, "real_person_evidence": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
