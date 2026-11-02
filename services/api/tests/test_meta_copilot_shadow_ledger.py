"""Persistent per-event shadow Copilot admission; never a billable Meta call."""
import asyncio
import json
import sqlite3
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
from app.meta_copilot_shadow_ledger import (
    MetaCopilotShadowLedger,
    ShadowPlannerCapacity,
    ShadowPlannerDenied,
    ShadowPlannerPreviouslyAttempted,
)
from app.synthetic_evidence import build_synthetic_evidence

ANCHOR_KEY = b"shadow-local-test-anchor-only-not-for-production-0123456789"


def fake_model_envelope(event_id):
    return {
        "model": "muse-spark-1.3",
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": offline_proposal(event_id).model_dump_json(),
            },
        }],
        "usage": {"prompt_tokens": 230, "completion_tokens": 100},
    }


def prepared(tmp_path, count=1):
    db = tmp_path / "edge" / "ledger.sqlite3"
    anchor = tmp_path / "different-directory" / "head.json"
    anchor.parent.mkdir()
    registry = SyntheticEvidenceRegistry(db)
    ids = []
    raw = edge_candidates_from_trace("fall")[0]
    for index in range(count):
        payload = json.loads(raw)
        if index:
            payload["event_id"] = str(uuid4())
        candidate_bytes = json.dumps(payload, separators=(",", ":")).encode()
        parsed = parse_candidate(candidate_bytes)
        CandidateLedger(db).accept(parsed, raw=candidate_bytes)
        registry.register(
            raw_candidate=candidate_bytes,
            evidence=build_synthetic_evidence(candidate_bytes),
        )
        ids.append(parsed.event_id)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=ANCHOR_KEY)
    anchored = SyntheticEvidenceRegistry(
        db, anchor_required=True, anchor_path=anchor, anchor_secret=ANCHOR_KEY,
    )
    return ids, db, anchor, anchored


def planner(event_id, calls, *, status=200):
    def handler(req):
        calls.append(req)
        assert req.url.host == "api.meta.ai"
        assert "authorization" not in req.headers
        return httpx.Response(
            status, json=fake_model_envelope(event_id),
        )
    return MockOnlyMetaPlanner(transport=httpx.MockTransport(handler))


def test_one_mock_call_per_event_persists_across_new_ledger_instance(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    calls = []
    mock = planner(event, calls)
    budget = MetaBudget(path=tmp_path / "private" / "meta_spend.sqlite3")
    shadow_path = tmp_path / "shadow" / "runs.sqlite3"
    shadow = MetaCopilotShadowLedger(shadow_path)
    first = asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored, mock_planner=mock, budget=budget,
    ))
    second = asyncio.run(MetaCopilotShadowLedger(shadow_path).run_mock_once(
        event_id=event, registry=anchored, mock_planner=mock, budget=budget,
    ))
    assert len(calls) == 1
    assert first.outcome == "mock_completed"
    assert first.mock_provider_invoked_this_call is True
    assert second.outcome == "duplicate_from_shadow_cache"
    assert second.mock_provider_invoked_this_call is False
    assert first.preview == second.preview
    assert first.total_mock_provider_calls_for_event == 1
    assert first.preview.meta_api_called is False
    assert first.preview.fall_confirmed is False
    assert second.readiness.real_provider_allowed is False
    assert second.readiness.official_meta_billing_verified is False
    assert second.readiness.meta_budget_calls_observed == 0
    assert second.readiness.meta_budget_reserved_micro_usd == 0
    assert budget.status() == (0, 0)
    assert budget.path.exists() is False
    rows = sqlite3.connect(shadow_path)
    try:
        assert rows.execute(
            "SELECT count(*) FROM meta_copilot_shadow_runs"
        ).fetchone()[0] == 1
        record = rows.execute(
            "SELECT state,preview_json FROM meta_copilot_shadow_runs"
        ).fetchone()
        assert record[0] == "completed"
        assert record[1]
    finally:
        rows.close()
    on_disk = shadow_path.read_bytes()
    assert b"data:image" not in on_disk
    assert b"API_KEY" not in on_disk
    assert b"LLM_" not in on_disk


def test_two_independent_events_each_admitted_once(tmp_path):
    ids, _, _, anchored = prepared(tmp_path, count=2)
    calls = []
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    for event in ids:
        result = asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
        assert result.outcome == "mock_completed"
    for event in ids:
        result = asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
        assert result.outcome == "duplicate_from_shadow_cache"
    assert len(calls) == 2


def test_failed_mock_provider_attempt_is_not_retried_on_same_event(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    calls = []
    budget = MetaBudget(path=tmp_path / "private" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    with pytest.raises(MockMetaPlannerRejected):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls, status=429), budget=budget,
        ))
    assert len(calls) == 1
    with pytest.raises(ShadowPlannerPreviouslyAttempted):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
    assert len(calls) == 1
    with sqlite3.connect(shadow.path) as con:
        assert con.execute(
            "SELECT state FROM meta_copilot_shadow_runs"
        ).fetchone()[0] == "failed"
    assert budget.status() == (0, 0)


def test_interrupted_reserved_run_denies_retry(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    from app.meta_copilot_shadow_ledger import _facts
    facts = _facts(anchored, event)
    assert shadow._claim(facts) is None  # simulate process crash after claim
    calls = []
    with pytest.raises(ShadowPlannerPreviouslyAttempted):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
    assert calls == []


def test_concurrent_duplicate_is_blocked_while_first_mock_request_is_in_flight(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    started = asyncio.Event()
    proceed = asyncio.Event()
    calls = []

    async def handler(req):
        calls.append(req)
        started.set()
        await proceed.wait()
        return httpx.Response(200, json=fake_model_envelope(event))

    mock = MockOnlyMetaPlanner(transport=httpx.MockTransport(handler))
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    ledger_path = tmp_path / "shadow" / "runs.sqlite3"

    async def exercise():
        first = asyncio.create_task(MetaCopilotShadowLedger(ledger_path).run_mock_once(
            event_id=event, registry=anchored, mock_planner=mock, budget=budget,
        ))
        await started.wait()
        with pytest.raises(ShadowPlannerPreviouslyAttempted):
            await MetaCopilotShadowLedger(ledger_path).run_mock_once(
                event_id=event, registry=anchored, mock_planner=mock, budget=budget,
            )
        proceed.set()
        outcome = await first
        assert outcome.outcome == "mock_completed"

    asyncio.run(exercise())
    assert len(calls) == 1


def test_anchor_removed_after_success_forbids_even_cached_preview(tmp_path):
    ids, _, anchor, anchored = prepared(tmp_path)
    event = ids[0]
    calls = []
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored, mock_planner=planner(event, calls),
        budget=budget,
    ))
    anchor.unlink()
    with pytest.raises(ValueError):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored, mock_planner=planner(event, calls),
            budget=budget,
        ))
    assert len(calls) == 1


def test_shadow_cache_tamper_and_event_reuse_fails_closed(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    calls = []
    asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored,
        mock_planner=planner(event, calls), budget=budget,
    ))
    with sqlite3.connect(shadow.path) as con:
        con.execute(
            "UPDATE meta_copilot_shadow_runs SET request_sha256=?",
            ("f" * 64,),
        )
    with pytest.raises(ShadowPlannerDenied):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
    assert len(calls) == 1


def test_corrupt_cached_preview_does_not_reexecute(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3")
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    calls = []
    asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored,
        mock_planner=planner(event, calls), budget=budget,
    ))
    with sqlite3.connect(shadow.path) as con:
        con.execute(
            "UPDATE meta_copilot_shadow_runs SET preview_json=?",
            ('{"fall_confirmed":true}',),
        )
    with pytest.raises(ShadowPlannerDenied):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls), budget=budget,
        ))
    assert len(calls) == 1


def test_hard_paid_gate_denial_even_when_test_budget_is_not_exhausted(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    budget = MetaBudget(path=tmp_path / "budget" / "unused.sqlite3",
                        approved_extra_tests=True)
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    result = asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored,
        mock_planner=planner(event, []), budget=budget,
    ))
    assert result.readiness.real_provider_allowed is False
    assert result.readiness.real_provider_denial == (
        "synthetic_consent_not_verified_and_budget_unapproved"
    )
    assert result.readiness.local_approved_cap_exhausted is False
    assert result.readiness.meta_api_called is False
    assert result.readiness.real_media_upload_authorized is False
    assert result.readiness.alert_dispatch_authorized is False


def test_observe_four_attempts_offline_without_consuming_fifth(tmp_path):
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    budget = MetaBudget(path=tmp_path / "budget" / "test.sqlite3",
                        approved_extra_tests=True)
    for _ in range(4):
        budget.reserve_once()  # only creates isolated test fixture ledger
    before = budget.status()
    assert before[0] == 4
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    result = asyncio.run(shadow.run_mock_once(
        event_id=event, registry=anchored,
        mock_planner=planner(event, []), budget=budget,
    ))
    assert result.readiness.meta_budget_calls_observed == 4
    assert result.readiness.local_approved_cap_exhausted is True
    assert budget.status() == before
    assert result.meta_api_called is False
    assert result.budget_modified is False


def test_capacity_enforced_without_provider_invocation(tmp_path, monkeypatch):
    from app import meta_copilot_shadow_ledger as module
    ids, _, _, anchored = prepared(tmp_path)
    event = ids[0]
    monkeypatch.setattr(module, "MAX_SHADOW_EVENTS", 0)
    calls = []
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    with pytest.raises(ShadowPlannerCapacity):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=planner(event, calls),
            budget=MetaBudget(path=tmp_path / "budget" / "none.sqlite3"),
        ))
    assert calls == []


def test_unsigned_registry_and_wrong_transport_are_denied_before_mock(tmp_path):
    ids, db, _, anchored = prepared(tmp_path)
    event = ids[0]
    shadow = MetaCopilotShadowLedger(tmp_path / "shadow" / "runs.sqlite3")
    calls = []
    with pytest.raises(ShadowPlannerDenied):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=SyntheticEvidenceRegistry(db),
            mock_planner=planner(event, calls),
            budget=MetaBudget(path=tmp_path / "budget" / "none.sqlite3"),
        ))
    with pytest.raises(ShadowPlannerDenied):
        asyncio.run(shadow.run_mock_once(
            event_id=event, registry=anchored,
            mock_planner=httpx.AsyncHTTPTransport(),
            budget=MetaBudget(path=tmp_path / "budget" / "none.sqlite3"),
        ))
    assert calls == []


def test_local_readonly_preflight_api_requires_caregiver_and_signed_evidence(tmp_path):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import Settings
    from app.main import create_app

    ids, db, anchor, _ = prepared(tmp_path)
    event = ids[0]
    options = {
        "_env_file": None,
        "demo_mode": False,
        "meta_provider": "mock",
        "meta_model_api_key": None,
        "meta_live_enabled": False,
        "edge_candidate_ledger_path": str(db),
        "caregiver_inbox_token": SecretStr("test-local-independent-caregiver-auth-0123456789"),
        "evidence_registry_enabled": True,
        "evidence_audit_anchor_required": True,
        "evidence_audit_anchor_path": str(anchor),
        "evidence_audit_anchor_secret": SecretStr(ANCHOR_KEY.decode("ascii")),
        "meta_copilot_preview_enabled": True,
    }
    url = f"/api/v1/caregiver/copilot/{event}/readiness"
    auth = {"Authorization": "Bearer test-local-independent-caregiver-auth-0123456789"}
    with TestClient(create_app(Settings(**options))) as client:
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
        result = client.get(url, headers=auth)
        assert result.status_code == 200
        assert result.headers["Cache-Control"] == "no-store"
        body = result.json()
        assert body["event_id"] == str(event)
        assert body["mode"] == "shadow_mock_only"
        assert body["real_provider_allowed"] is False
        assert body["real_media_upload_authorized"] is False
        assert body["official_meta_billing_verified"] is False
        assert body["meta_api_called"] is False
        assert body["meta_budget_calls_observed"] >= 0
        assert isinstance(body["local_budget_ledger_present"], bool)
        assert client.post(url, json={}).status_code == 405
        assert client.put(url, json={}).status_code == 405
        assert client.delete(url).status_code == 405
    with TestClient(create_app(Settings(**{
        **options, "meta_copilot_preview_enabled": False,
    }))) as client:
        assert client.get(url, headers=auth).status_code == 404
    with TestClient(create_app(Settings(**options))) as client:
        anchor.unlink()
        assert client.get(url, headers=auth).status_code == 503
    with TestClient(
        create_app(Settings(**options)), client=("203.0.113.35", 12345),
    ) as remote:
        assert remote.get(url, headers={
            **auth, "X-Forwarded-For": "127.0.0.1",
        }).status_code == 403
