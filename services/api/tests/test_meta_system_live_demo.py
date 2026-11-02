"""Zero-billing tests for one-shot real Meta + synthetic Edge -> local Inbox chain."""
import asyncio
import json

import httpx
import pytest

from app.meta_budget import MetaBudget
from app.meta_live import MODEL, MetaProviderUnavailable
from app.meta_system_live_demo import run_live_synthetic_system


def model_response():
    return {
        "model": MODEL,
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "verdict": "uncertain",
                    "visible_observations": ["Uniform green test image, no human"],
                    "uncertainties": ["No sequential frames or fall evidence"],
                    "supporting_frame_indices": [],
                }),
            },
        }],
        "usage": {"prompt_tokens": 233, "completion_tokens": 163},
    }


def test_full_synthetic_pipeline_with_mocked_external_meta(tmp_path):
    requests = []

    def responder(request):
        requests.append(request)
        assert str(request.url) == "https://api.meta.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer LLM_fake_offline_test"
        body = json.loads(request.content)
        assert body["model"] == MODEL
        assert body["reasoning_effort"] == "minimal"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert len(body["messages"]) == 2
        assert body["messages"][1]["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return httpx.Response(200, json=model_response())

    budget = MetaBudget(path=tmp_path / "local-model-ledger.sqlite3")
    result = asyncio.run(run_live_synthetic_system(
        api_key="LLM_fake_offline_test",
        budget=budget,
        transport=httpx.MockTransport(responder),
    ))
    assert result["status"] == "LIVE_META_SYSTEM_SYNTHETIC_INTEGRATION_PASS"
    assert result["actual_meta_response_validated"] is True
    assert result["meta_input_is_canonical_solid_png_not_edge_evidence"] is True
    assert result["edge_candidate_accepted_over_real_local_tcp"] is True
    assert result["edge_source_timestamp_ms"] == 850
    assert result["sitting_generated_no_candidate"] is True
    assert result["meta_verdict"] == "uncertain"
    assert result["meta_route"] == "require_follow_up"
    assert result["caregiver_inbox_remains_synthetic_without_live_meta_claim"] is True
    assert result["fall_confirmed"] is False
    assert result["notifications_sent"] is False
    assert result["emergency_dispatch_authorized"] is False
    assert result["real_people_or_camera_frames_sent"] == 0
    assert result["prompt_tokens"] == 233
    assert result["completion_tokens"] == 163
    assert result["temporary_sqlite_removed"] is True
    assert result["temporary_http_server_stopped"] is True
    assert len(requests) == 1
    assert budget.status()[0] == 1


def test_failed_provider_response_cannot_promote_synthetic_inbox(tmp_path):
    calls = []

    def responder(request):
        calls.append(request)
        body = model_response()
        body["choices"][0]["message"]["content"] = json.dumps({
            "verdict": "fall_likely",
            "visible_observations": ["Fictional person is falling"],
            "uncertainties": [],
            "supporting_frame_indices": [0],
        })
        return httpx.Response(200, json=body)

    budget = MetaBudget(path=tmp_path / "failure-ledger.sqlite3")
    with pytest.raises(MetaProviderUnavailable, match="safety validation"):
        asyncio.run(run_live_synthetic_system(
            api_key="LLM_fake_offline_test",
            budget=budget,
            transport=httpx.MockTransport(responder),
        ))
    assert len(calls) == 1
    assert budget.status()[0] == 1
