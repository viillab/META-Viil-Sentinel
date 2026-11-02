import asyncio
import json
from functools import wraps

import httpx
import pytest

from app.meta_budget import (
    MAX_APPROVED_LOCAL_CALLS,
    MAX_LOCAL_CALLS,
    MetaBudget,
    MetaBudgetExceeded,
)
from app.meta_first_contract import MetaAdvisoryRoute
from app.meta_live import (
    ENDPOINT,
    MODEL,
    MetaLiveDisabled,
    MetaProviderUnavailable,
    MetaSyntheticVisionClient,
    build_synthetic_request,
)
from app.meta_live_probe import synthetic_png


def run_sync(coroutine):
    @wraps(coroutine)
    def wrapped(*args, **kwargs):
        return asyncio.run(coroutine(*args, **kwargs))
    return wrapped


def safe_response(**changes):
    data = {
        "model": MODEL,
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "verdict": "uncertain",
                "visible_observations": ["A synthetic solid-color rectangle is visible"],
                "uncertainties": ["No person, movement or temporal event is shown"],
                "supporting_frame_indices": [],
            })},
        }],
        "usage": {"prompt_tokens": 117, "completion_tokens": 64},
    }
    data.update(changes)
    return data


@run_sync
async def test_default_disabled_never_reserves_or_contacts_network(tmp_path):
    budget = MetaBudget(path=tmp_path / "budget.sqlite3")
    hits = []

    def responder(request):
        hits.append(request)
        return httpx.Response(200, json=safe_response())

    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=False,
        budget=budget, transport=httpx.MockTransport(responder),
    )
    with pytest.raises(MetaLiveDisabled):
        await client.assess(image=synthetic_png())
    assert hits == []
    assert budget.status() == (0, 0)


@run_sync
async def test_real_wire_contract_mocked_synthetic_only_no_advisory(tmp_path):
    seen = []
    budget = MetaBudget(path=tmp_path / "budget.sqlite3")

    def responder(request):
        seen.append(request)
        assert request.method == "POST"
        assert str(request.url) == ENDPOINT
        assert request.headers["authorization"] == "Bearer LLM_example-not-real"
        request_json = json.loads(request.content)
        assert request_json["model"] == "muse-spark-1.3"
        assert request_json["max_completion_tokens"] == 1024
        assert request_json["reasoning_effort"] == "minimal"
        assert request_json["response_format"]["type"] == "json_schema"
        parts = request_json["messages"][1]["content"]
        assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "web_search" not in json.dumps(request_json)
        assert len(seen) == 1
        return httpx.Response(200, json=safe_response())

    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=True,
        budget=budget, transport=httpx.MockTransport(responder),
    )
    result = await client.assess(image=synthetic_png())
    assert result.assessment.verdict.value == "uncertain"
    assert result.route.route == MetaAdvisoryRoute.REQUIRE_FOLLOW_UP
    assert not result.route.fall_confirmed
    assert not result.route.emergency_dispatch_authorized
    assert result.prompt_tokens == 117
    assert result.completion_tokens == 64
    assert budget.status() == (1, result.reserved_micro_usd)


@run_sync
async def test_budget_reserves_before_network_failure_and_never_retries(tmp_path):
    calls = []
    budget = MetaBudget(path=tmp_path / "budget.sqlite3")

    def responder(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "private upstream"}})

    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=True,
        budget=budget, transport=httpx.MockTransport(responder),
    )
    for _ in range(MAX_LOCAL_CALLS):
        with pytest.raises(MetaProviderUnavailable, match="429"):
            await client.assess(image=synthetic_png())
    assert len(calls) == MAX_LOCAL_CALLS
    with pytest.raises(MetaBudgetExceeded):
        await client.assess(image=synthetic_png())
    assert len(calls) == MAX_LOCAL_CALLS
    assert budget.status()[0] == MAX_LOCAL_CALLS


@run_sync
async def test_refuses_malicious_provider_output_and_no_real_frames(tmp_path):
    budget = MetaBudget(path=tmp_path / "budget.sqlite3")

    def responder(request):
        assert request.method == "POST"
        body = safe_response()
        body["choices"][0]["message"]["content"] = json.dumps({
            "verdict": "fall_likely",
            "visible_observations": ["A confirmed fall"],
            "uncertainties": [],
            "supporting_frame_indices": [0],
        })
        return httpx.Response(200, json=body)

    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=True,
        budget=budget, transport=httpx.MockTransport(responder),
    )
    with pytest.raises(MetaProviderUnavailable, match="validation"):
        await client.assess(image=synthetic_png())
    with pytest.raises(ValueError):
        build_synthetic_request(b"not-a-picture")
    altered = bytearray(synthetic_png())
    altered[55] ^= 1  # same PNG header, but no longer the canonical generated image
    with pytest.raises(ValueError, match="canonical"):
        build_synthetic_request(bytes(altered))
    assert budget.status()[0] == 1


def test_local_spend_ledger_persists_and_is_shared_by_instances(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = MetaBudget(path=path)
    second = MetaBudget(path=path)
    first.reserve_once()
    second.reserve_once()
    assert first.status()[0] == MAX_LOCAL_CALLS
    with pytest.raises(MetaBudgetExceeded):
        first.reserve_once()


def test_explicit_approved_extension_preserves_prior_two_calls(tmp_path):
    """The operator can approve two new attempts; old ledger is never erased."""
    db = tmp_path / "meta.sqlite3"
    original = MetaBudget(path=db)
    assert original.reserve_once()[0] == 1
    assert original.reserve_once()[0] == MAX_LOCAL_CALLS
    assert original.status()[0] == 2
    with pytest.raises(MetaBudgetExceeded):
        original.reserve_once()

    extended = MetaBudget(path=db, approved_extra_tests=True)
    assert extended.status()[0] == 2
    assert extended.reserve_once()[0] == 3
    assert extended.reserve_once()[0] == MAX_APPROVED_LOCAL_CALLS
    assert original.status() == extended.status()
    with pytest.raises(MetaBudgetExceeded):
        extended.reserve_once()
    assert original.status()[0] == MAX_APPROVED_LOCAL_CALLS


@run_sync
async def test_minimal_reasoning_synthetic_strict_schema_rejects_any_fake_frame(tmp_path):
    budget = MetaBudget(path=tmp_path / "spend.sqlite3")

    def responder(request):
        body = json.loads(request.content)
        assert body["reasoning_effort"] == "minimal"
        assert body["response_format"]["json_schema"]["strict"] is True
        unsafe = safe_response()
        unsafe["choices"][0]["message"]["content"] = json.dumps({
            "verdict": "uncertain",
            "visible_observations": ["Solid color"],
            "uncertainties": ["No temporal evidence"],
            "supporting_frame_indices": [0],
        })
        return httpx.Response(200, json=unsafe)

    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=True,
        budget=budget, transport=httpx.MockTransport(responder),
    )
    with pytest.raises(MetaProviderUnavailable, match="synthetic evidence index"):
        await client.assess(image=synthetic_png())
    assert budget.status()[0] == 1


@run_sync
async def test_diagnostic_reason_for_capped_provider_response(tmp_path):
    budget = MetaBudget(path=tmp_path / "spend.sqlite3")
    truncated = safe_response()
    truncated["choices"][0]["finish_reason"] = "length"
    client = MetaSyntheticVisionClient(
        api_key="LLM_example-not-real", live_enabled=True,
        budget=budget, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=truncated)
        ),
    )
    with pytest.raises(MetaProviderUnavailable, match="finish_reason=length"):
        await client.assess(image=synthetic_png())
    assert budget.status()[0] == 1
