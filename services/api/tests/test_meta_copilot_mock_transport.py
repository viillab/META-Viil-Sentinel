"""Zero-spend provider-envelope and tool-plan hardening for Meta Copilot."""
import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.candidate_ingest import CandidateLedger, parse_candidate
from app.edge_emitter_e2e import edge_candidates_from_trace
from app.evidence_anchor import capture_checkpoint
from app.evidence_registry import SyntheticEvidenceRegistry
from app.meta_budget import MetaBudget
from app.meta_copilot import offline_proposal
from app.meta_copilot_mock_transport import (
    MockMetaPlannerRejected,
    MockOnlyMetaPlanner,
)
from app.synthetic_evidence import build_synthetic_evidence

KEY = b"mock-only-meta-copilot-signed-anchored-test-key-12345678"


def prepared(tmp_path):
    raw = edge_candidates_from_trace("fall")[0]
    event = parse_candidate(raw).event_id
    ledger = tmp_path / "candidate-ledger" / "receipts.sqlite3"
    anchor = tmp_path / "independent-anchor" / "head.json"
    anchor.parent.mkdir()
    CandidateLedger(ledger).accept(parse_candidate(raw), raw=raw)
    SyntheticEvidenceRegistry(ledger).register(
        raw_candidate=raw, evidence=build_synthetic_evidence(raw),
    )
    capture_checkpoint(db_path=ledger, checkpoint_path=anchor, secret=KEY)
    return event, ledger, anchor, SyntheticEvidenceRegistry(
        ledger, anchor_required=True, anchor_path=anchor, anchor_secret=KEY,
    )


def wire_response(event_id, *, finish="stop", usage=None):
    return {
        "model": "muse-spark-1.3",
        "choices": [{
            "finish_reason": finish,
            "message": {
                "role": "assistant",
                "content": offline_proposal(event_id).model_dump_json(),
            },
        }],
        "usage": usage or {"prompt_tokens": 234, "completion_tokens": 83},
    }


def test_real_provider_contract_over_mock_transport_no_key_or_media(tmp_path, monkeypatch):
    event, _, _, registry = prepared(tmp_path)
    requests = []
    budget = MetaBudget(path=tmp_path / "private" / "meta-spend.sqlite3")
    monkeypatch.setenv("META_MODEL_API_KEY", "LLM_fake_do_not_send")
    monkeypatch.setenv("HTTP_PROXY", "http://localhost:9000")
    monkeypatch.setenv("HTTPS_PROXY", "http://localhost:9000")

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://api.meta.ai/v1/chat/completions"
        assert "authorization" not in request.headers
        assert "LLM_fake_do_not_send" not in request.content.decode("utf-8")
        body = json.loads(request.content)
        assert body["model"] == "muse-spark-1.3"
        assert body["reasoning_effort"] == "minimal"
        assert body["max_completion_tokens"] == 512
        assert body["response_format"]["json_schema"]["strict"] is True
        assert len(body["messages"]) == 2
        context = json.loads(body["messages"][1]["content"])
        assert context["event_id"] == str(event)
        assert context["source_id"] == "synthetic-clip-01"
        assert context["input_kind"] == "synthetic_pose_diagram_metadata_only"
        assert context["human_consent_verified"] is False
        assert context["all_external_actions_permitted"] is False
        assert "data:image" not in request.content.decode()
        assert "cookie" not in request.headers
        return httpx.Response(200, json=wire_response(event))

    planner = MockOnlyMetaPlanner(transport=httpx.MockTransport(handler))
    outcome = asyncio.run(planner.propose_for_verified_event(
        registry=registry, event_id=event,
    ))
    assert outcome.event_id == event
    assert outcome.mock_transport_request_count == 1
    assert outcome.provider_response_simulated is True
    assert outcome.meta_api_called is False
    assert outcome.meta_budget_modified is False
    assert outcome.real_media_sent is False
    assert outcome.state_changed is False
    assert outcome.prompt_tokens_from_mock == 234
    assert outcome.completion_tokens_from_mock == 83
    assert outcome.preview.mode == "offline_readonly_shadow"
    assert outcome.preview.meta_api_called is False
    assert outcome.preview.model_has_executed_tools is False
    assert outcome.preview.human_review_required is True
    assert outcome.preview.fall_confirmed is False
    assert outcome.preview.notification_sent is False
    assert len(outcome.preview.actions) == 3
    assert all(not tool.is_external_action for tool in outcome.preview.actions)
    assert len(requests) == 1
    assert budget.status() == (0, 0)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"model": "wrong-model"}),
    lambda d: d.update({"choices": []}),
    lambda d: d.update({"choices": d["choices"] * 2}),
    lambda d: d["choices"][0].update({"finish_reason": "length"}),
    lambda d: d["choices"][0].update({"finish_reason": "tool_calls"}),
    lambda d: d["choices"][0]["message"].update({"role": "tool"}),
    lambda d: d["choices"][0]["message"].update({"refusal": "no"}),
    lambda d: d["choices"][0]["message"].update({"tool_calls": [{"name": "run_shell"}]}),
    lambda d: d["choices"][0]["message"].update({"content": "x" * 5000}),
    lambda d: d["choices"][0]["message"].update({"content": "not-json"}),
    lambda d: d["choices"][0]["message"].update({"content": "{}"}),
    lambda d: d["choices"][0]["message"].update({"content": json.dumps({
        "schema_version": "viil.meta.copilot.proposal.v1",
        "event_id": str(uuid4()),
        "tools": [],
    })}),
    lambda d: d.update({"usage": {"prompt_tokens": 7, "completion_tokens": 100000}}),
    lambda d: d.update({"usage": {"prompt_tokens": "7", "completion_tokens": 2}}),
    lambda d: d.update({"usage": "bad"}),
])
def test_bad_simulated_provider_response_never_creates_preview(tmp_path, mutate):
    event, _, _, registry = prepared(tmp_path)
    response = wire_response(event)
    mutate(response)
    planner = MockOnlyMetaPlanner(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    )
    with pytest.raises(MockMetaPlannerRejected):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_mock_provider_http_failure_no_retry_or_raw_provider_body(tmp_path, status):
    event, _, _, registry = prepared(tmp_path)
    called = []

    def handler(req):
        called.append(req)
        return httpx.Response(status, text="INTERNAL_META_SECRET_SHOULD_NOT_LEAK")
    planner = MockOnlyMetaPlanner(transport=httpx.MockTransport(handler))
    with pytest.raises(MockMetaPlannerRejected) as error:
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))
    assert "INTERNAL_META_SECRET_SHOULD_NOT_LEAK" not in str(error.value)
    assert len(called) == 1


def test_model_cannot_grant_consent_trigger_emergency_or_cross_event(tmp_path):
    event, _, _, registry = prepared(tmp_path)
    payload = wire_response(event)
    raw = json.loads(payload["choices"][0]["message"]["content"])
    raw["tools"].append({"tool": "notify_emergency", "event_id": str(event)})
    payload["choices"][0]["message"]["content"] = json.dumps(raw)
    planner = MockOnlyMetaPlanner(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    with pytest.raises(MockMetaPlannerRejected):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))


def test_missing_or_corrupt_independent_anchor_denies_before_mock_request(tmp_path):
    event, _, anchor, registry = prepared(tmp_path)
    calls = []
    planner = MockOnlyMetaPlanner(
        transport=httpx.MockTransport(lambda req: calls.append(req) or
            httpx.Response(200, json=wire_response(event)))
    )
    anchor.write_bytes(b'{"malicious":true}')
    with pytest.raises(ValueError):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))
    assert calls == []
    anchor.unlink()
    with pytest.raises(ValueError):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))
    assert calls == []


def test_no_unsigned_anchor_no_unknown_event_no_mock_call(tmp_path):
    event, db, _, _ = prepared(tmp_path)
    calls = []
    planner = MockOnlyMetaPlanner(
        transport=httpx.MockTransport(lambda req: calls.append(req) or
            httpx.Response(200, json=wire_response(event)))
    )
    with pytest.raises(ValueError):
        asyncio.run(planner.propose_for_verified_event(
            registry=SyntheticEvidenceRegistry(db), event_id=event,
        ))
    assert not calls


def test_wrong_transport_cannot_contact_live_provider():
    with pytest.raises(ValueError, match="MockTransport"):
        MockOnlyMetaPlanner(transport=httpx.AsyncHTTPTransport())


def test_duplicate_provider_envelope_keys_are_rejected(tmp_path):
    event, _, _, registry = prepared(tmp_path)
    original = json.dumps(wire_response(event))
    malicious = original[:-1] + ', "model": "muse-spark-1.3"}'
    planner = MockOnlyMetaPlanner(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=malicious.encode())
        )
    )
    with pytest.raises(MockMetaPlannerRejected, match="Duplicate"):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))


def test_midflight_anchor_revocation_drops_mock_proposal_before_preview(tmp_path):
    event, _, anchor, registry = prepared(tmp_path)
    call_count = []

    def handler(request):
        call_count.append(request)
        anchor.write_bytes(b'{"revoked":true}')
        return httpx.Response(200, json=wire_response(event))

    planner = MockOnlyMetaPlanner(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        asyncio.run(planner.propose_for_verified_event(
            registry=registry, event_id=event,
        ))
    assert len(call_count) == 1


def test_raw_provider_payload_size_and_nonfinite_values_rejected(tmp_path):
    event, _, _, registry = prepared(tmp_path)
    for raw in (
        b"X" * 9_000,
        b'{"model":NaN}',
        b"{",
    ):
        planner = MockOnlyMetaPlanner(
            transport=httpx.MockTransport(
                lambda _, raw=raw: httpx.Response(200, content=raw)
            )
        )
        with pytest.raises(MockMetaPlannerRejected):
            asyncio.run(planner.propose_for_verified_event(
                registry=registry, event_id=event,
            ))
