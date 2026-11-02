"""Mock-transport-only Meta Copilot provider response contract test.

This is NOT a Meta AI call. It simulates the provider's HTTP envelope with
httpx.MockTransport so exact request/response schema and allowlisted plan
routing can be tested without a provider key, network socket, credit spend,
real-person imagery, notifications or changes to the incident ledger.

A future *separate* live client must pass an independent real-media/privacy
review and use the existing non-resettable MetaBudget. Never relax the
MockTransport-only boundary in this adapter.
"""
import json
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.evidence_registry import (
    EvidenceRegistryRejected,
    EvidenceRegistryUnavailable,
    SyntheticEvidenceRegistry,
)
from app.meta_copilot import (
    MAX_MODEL_PLAN_BYTES,
    META_COPILOT_MODEL,
    MetaCopilotPreview,
    MetaCopilotUnavailable,
    MetaProposalRejected,
    build_copilot_preview,
    build_offline_meta_planner_request,
    validate_meta_proposal,
)
from app.meta_live import ENDPOINT
from app.synthetic_fixtures import SYNTHETIC_SOURCE

MAX_RESPONSE_BYTES = 8192
MAX_COMPLETION_TOKENS = 512


class MockMetaPlannerRejected(RuntimeError):
    """Provider envelope or model tool plan failed verification; no raw body logs."""


@dataclass(frozen=True, slots=True)
class MockMetaPlannerResult:
    """Provenance must not impersonate an actual paid AI inference."""

    event_id: UUID
    preview: MetaCopilotPreview
    mock_transport_request_count: int
    provider_response_simulated: bool
    meta_api_called: bool
    meta_budget_modified: bool
    real_media_sent: bool
    state_changed: bool
    prompt_tokens_from_mock: int | None
    completion_tokens_from_mock: int | None


def _validated_response(data: object, *, event_id: UUID):
    """Validate the provider envelope and the exact typed, constrained plan."""
    try:
        if type(data) is not dict or data.get("model") != META_COPILOT_MODEL:
            raise MockMetaPlannerRejected("Unexpected simulated model response")
        choices = data.get("choices")
        if type(choices) is not list or len(choices) != 1:
            raise MockMetaPlannerRejected("Malformed provider choice envelope")
        choice = choices[0]
        if type(choice) is not dict or choice.get("finish_reason") != "stop":
            raise MockMetaPlannerRejected("Truncated or incomplete simulated provider output")
        message = choice.get("message")
        if type(message) is not dict or message.get("role") != "assistant":
            raise MockMetaPlannerRejected("Invalid simulated assistant role")
        if message.get("refusal") or message.get("tool_calls"):
            raise MockMetaPlannerRejected("Unapproved direct provider tool call or refusal")
        content = message.get("content")
        if type(content) is not str or len(content.encode("utf-8")) > MAX_MODEL_PLAN_BYTES:
            raise MockMetaPlannerRejected("Missing or oversized structured tool plan")
        plan = validate_meta_proposal(content.encode("utf-8"), event_id=event_id)
        usage = data.get("usage")
        if usage is None:
            return plan, None, None
        if type(usage) is not dict:
            raise MockMetaPlannerRejected("Malformed provider usage metadata")
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        if (
            type(prompt) is not int or not 0 <= prompt <= 100_000
            or type(completion) is not int or not 0 <= completion <= MAX_COMPLETION_TOKENS
        ):
            raise MockMetaPlannerRejected("Unexpected simulated token usage")
        return plan, prompt, completion
    except (MetaProposalRejected, KeyError, TypeError, AttributeError):
        raise MockMetaPlannerRejected("Simulated Meta planning response failed validation") from None


def _unique_response_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Do not silently choose the last duplicated provider-envelope field."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MockMetaPlannerRejected("Duplicate simulated provider envelope field")
        result[key] = value
    return result


class MockOnlyMetaPlanner:
    """No way to create a live HTTP transport, even with an environment key."""

    def __init__(self, *, transport: httpx.MockTransport) -> None:
        if type(transport) is not httpx.MockTransport:
            raise ValueError("Offline Meta planner requires exact httpx.MockTransport")
        self._transport = transport

    async def propose_for_verified_event(
        self, *, registry: SyntheticEvidenceRegistry, event_id: UUID,
    ) -> MockMetaPlannerResult:
        """Validate anchored evidence, call mock once, validate output, re-check."""
        if not registry.anchor_required or not isinstance(event_id, UUID):
            raise MetaCopilotUnavailable("Signed audit anchor and event UUID required")
        # No simulated provider request if the backend cannot independently
        # verify the exact source, event, manifest, chain and anchor.
        try:
            evidence = registry.get(event_id=event_id, source_id=SYNTHETIC_SOURCE)
            audit = registry.get_audit(event_id=event_id, source_id=SYNTHETIC_SOURCE)
        except (EvidenceRegistryRejected, EvidenceRegistryUnavailable):
            raise MetaCopilotUnavailable("Synthetic registry verification unavailable") from None
        if evidence is None or audit is None:
            raise MetaCopilotUnavailable("Cannot plan for an unknown synthetic event")
        body = build_offline_meta_planner_request(evidence, audit)
        # This class never accepts API keys, real transport, user-supplied
        # endpoints, custom models, request tool payloads or physical media.
        try:
            async with httpx.AsyncClient(
                transport=self._transport, trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(5, connect=2),
            ) as client, client.stream(
                "POST", ENDPOINT, json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            ) as response:
                if response.status_code != 200:
                    raise MockMetaPlannerRejected(
                        "Simulated provider returned non-success status"
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise MockMetaPlannerRejected(
                            "Simulated provider response exceeded byte limit"
                        )
                    chunks.append(chunk)
            data = json.loads(
                b"".join(chunks),
                object_pairs_hook=_unique_response_fields,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    MockMetaPlannerRejected("Nonfinite provider token")
                ),
            )
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
            raise MockMetaPlannerRejected(
                "Simulated Meta HTTP or JSON response unavailable"
            ) from None
        plan, prompt_tokens, completion_tokens = _validated_response(
            data, event_id=event_id
        )
        # IMPORTANT: Plan authority is not grounded in model output. The
        # backend verifies the independent anchor AGAIN before applying the
        # fixed read-only allowlist (also catches mid-request revocation).
        try:
            preview = build_copilot_preview(
                registry=registry, event_id=event_id, plan=plan,
            )
        except (EvidenceRegistryRejected, EvidenceRegistryUnavailable):
            raise MetaCopilotUnavailable("Signed evidence changed during mock plan") from None
        if preview is None:
            raise MetaCopilotUnavailable("Verified event disappeared during mock plan")
        return MockMetaPlannerResult(
            event_id=event_id,
            preview=preview,
            mock_transport_request_count=1,
            provider_response_simulated=True,
            meta_api_called=False,
            meta_budget_modified=False,
            real_media_sent=False,
            state_changed=False,
            prompt_tokens_from_mock=prompt_tokens,
            completion_tokens_from_mock=completion_tokens,
        )
