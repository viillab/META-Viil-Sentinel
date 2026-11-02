"""Opt-in, budget-gated Meta Model API vision adapter for *synthetic-only* testing.

DO NOT route real cameras/patient imagery here. A future permitted-evidence
pipeline requires independent source auth, privacy approval and validation.
This adapter never emits caregiver alerts or upgrades safety state.
"""
import base64
import json
import struct
import zlib
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.meta_budget import MAX_OUTPUT_TOKENS, MetaBudget
from app.meta_first_contract import (
    META_FIRST_JSON_SCHEMA,
    MetaRouteDecision,
    MetaVisibleAssessment,
    TrustedMetaCallContext,
    meta_first_route,
)

ENDPOINT = "https://api.meta.ai/v1/chat/completions"
MODEL = "muse-spark-1.3"  # Standard mode only; contributor would grant training rights.
MAX_IMAGE_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 24_576
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

SYSTEM_PROMPT = (
    "You are evaluating one SYNTHETIC non-human test image for an API "
    "contract test, not a real safety incident. Do not identify any person, "
    "invent a person, motion, fall or severity. Only visible pixels count. "
    "Choose 'uncertain' unless temporal real-person evidence is present "
    "(there is none here). supporting_frame_indices must be empty. "
    "No medical recommendation, emergency dispatch or certainty."
)


class MetaLiveDisabled(RuntimeError):
    pass


class MetaProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MetaSyntheticResult:
    model: str
    assessment: MetaVisibleAssessment
    route: MetaRouteDecision
    prompt_tokens: int | None
    completion_tokens: int | None
    reserved_micro_usd: int
    local_call_number: int


def synthetic_png() -> bytes:
    """Canonical, locally constructed 64x64 flat-color test fixture."""
    width = height = 64
    raw = b"".join(b"\x00" + b"\x33\x99\x66" * width for _ in range(height))

    def chunk(name: bytes, data: bytes) -> bytes:
        body = name + data
        return (
            struct.pack(">I", len(data)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def validate_synthetic_png(frame: bytes) -> None:
    """Reject *all* user-supplied images, including valid PNG person photos."""
    if not isinstance(frame, bytes) or not 48 <= len(frame) <= MAX_IMAGE_BYTES:
        raise ValueError("Synthetic PNG size is invalid")
    if frame != synthetic_png():
        raise ValueError("Only the canonical generated test image is allowed")


def build_synthetic_request(image: bytes) -> dict:
    validate_synthetic_png(image)
    url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    return {
        "model": MODEL,
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    "This is a synthetic non-person PNG. Give cautious visible "
                    "observations only. Return the exact JSON schema."
                )},
                {"type": "image_url", "image_url": {"url": url}},
            ]},
        ],
        "response_format": META_FIRST_JSON_SCHEMA,
    }


def read_checked_response(data: object) -> tuple[MetaVisibleAssessment, int | None, int | None]:
    """Fail closed on model refusals, truncation, hallucinated extra fields."""
    try:
        if not isinstance(data, dict):
            raise TypeError("Invalid response")
        if data.get("model") != MODEL:
            raise MetaProviderUnavailable("Meta returned unexpected model identifier")
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("Invalid choices")
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise MetaProviderUnavailable("Meta response incomplete or token-capped")
        message = choice["message"]
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise MetaProviderUnavailable("Meta response missing structured text")
        content = message["content"]
        if len(content) > 8192:
            raise ValueError("Oversized answer")
        # JSON-mode Pydantic accepts enum wire strings while preserving
        # strict field checking; Python-mode strict parsing rejects them.
        result = MetaVisibleAssessment.model_validate_json(content)
        # A single synthetic image cannot ground temporal fall inference.
        if result.verdict.value == "fall_likely":
            raise MetaProviderUnavailable("Meta safety validation rejected fall claim on synthetic data")
        if any(i != 0 for i in result.supporting_frame_indices):
            raise MetaProviderUnavailable("Meta safety validation rejected synthetic evidence index")
        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}

        def usage_count(name: str) -> int | None:
            val = usage.get(name)
            return val if type(val) is int and 0 <= val <= 200_000 else None

        return result, usage_count("prompt_tokens"), usage_count("completion_tokens")
    except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
        raise MetaProviderUnavailable("Meta response failed local safety validation") from None


class MetaSyntheticVisionClient:
    """One explicit operator run, no retries, no web search, no user images."""

    def __init__(
        self,
        *, api_key: str | None, live_enabled: bool,
        budget: MetaBudget | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._enabled = live_enabled
        self._budget = budget or MetaBudget()
        self._transport = transport

    async def assess(self, *, image: bytes) -> MetaSyntheticResult:
        validate_synthetic_png(image)
        if not self._enabled:
            raise MetaLiveDisabled("Meta live test is disabled by default")
        if not self._api_key or not self._api_key.startswith("LLM_"):
            raise MetaLiveDisabled("No valid Meta backend key is configured")
        payload = build_synthetic_request(image)
        call_number, reserved_total = self._budget.reserve_once()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(15, connect=5),
                trust_env=False,
                follow_redirects=False,
            ) as client, client.stream(
                "POST", ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code != 200:
                    # Never log native provider bodies (may contain secrets).
                    raise MetaProviderUnavailable(
                        f"Meta HTTP status {response.status_code}; no retry performed"
                    )
                size = 0
                chunks = []
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise MetaProviderUnavailable("Meta response exceeded size cap")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks))
            assessment, prompt_tokens, completion_tokens = read_checked_response(data)
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
            raise MetaProviderUnavailable("Meta transport or JSON validation failed") from None
        # Synthetic evidence always routes to follow-up, even after real Meta
        # API success. The model has no authority to notify or confirm a fall.
        context = TrustedMetaCallContext(
            provider="meta_model_api",
            actual_provider_request_succeeded=True,
            source_authenticated=False,
            media_licensed_and_consented=True,
            evidence_frame_count=1,
            validated_evidence=False,
        )
        decision = meta_first_route(assessment, context)
        return MetaSyntheticResult(
            model=MODEL, assessment=assessment, route=decision,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            reserved_micro_usd=reserved_total, local_call_number=call_number,
        )
