"""Zero-billing Meta Copilot tests: allowlisted proposals and anchored case reads."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import CandidateLedger, parse_candidate
from app.config import Settings
from app.edge_emitter_e2e import edge_candidates_from_trace
from app.evidence_anchor import capture_checkpoint
from app.evidence_registry import SyntheticEvidenceRegistry
from app.main import create_app
from app.meta_copilot import (
    CANONICAL_ORDER,
    META_COPILOT_JSON_SCHEMA,
    MetaCopilotUnavailable,
    MetaProposalRejected,
    MetaTool,
    build_copilot_preview,
    build_offline_meta_planner_request,
    offline_proposal,
    validate_meta_proposal,
)
from app.synthetic_evidence import build_synthetic_evidence
from app.synthetic_fixtures import SYNTHETIC_SOURCE

KEY = b"offline-meta-copilot-anchoring-key-only-for-tests-12345678"
TOKEN = "offline-copilot-caretaker-independent-read-token-only-001"


def prepared(tmp_path):
    events = edge_candidates_from_trace("fall")
    assert len(events) == 1
    raw = events[0]
    db = tmp_path / "ledger" / "events.sqlite3"
    anchor = tmp_path / "independent" / "checkpoint.json"
    anchor.parent.mkdir()
    receipt = CandidateLedger(db).accept(parse_candidate(raw), raw=raw)
    registry = SyntheticEvidenceRegistry(db)
    record, duplicate = registry.register(
        raw_candidate=raw, evidence=build_synthetic_evidence(raw),
    )
    assert duplicate is False
    assert receipt.event_id == record.event_id
    captured = capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    assert captured.record_count == 1
    anchored = SyntheticEvidenceRegistry(
        db, anchor_required=True, anchor_path=anchor, anchor_secret=KEY,
    )
    return receipt.event_id, db, anchor, anchored


def settings(db, anchor, **overrides):
    options = {
        "_env_file": None,
        "meta_provider": "mock",
        "meta_model_api_key": None,
        "meta_live_enabled": False,
        "demo_mode": False,
        "edge_candidate_ledger_path": str(db),
        "caregiver_inbox_token": SecretStr(TOKEN),
        "evidence_registry_enabled": True,
        "evidence_audit_anchor_required": True,
        "evidence_audit_anchor_path": str(anchor),
        "evidence_audit_anchor_secret": SecretStr(KEY.decode()),
        "meta_copilot_preview_enabled": True,
    }
    options.update(overrides)
    return Settings(**options)


def test_offline_copilot_executes_three_fixed_readonly_tasks(tmp_path):
    event_id, _, _, registry = prepared(tmp_path)
    report = build_copilot_preview(registry=registry, event_id=event_id)
    assert report is not None
    assert report.mode == "offline_readonly_shadow"
    assert report.prospective_model == "muse-spark-1.3"
    assert report.meta_api_called is False
    assert report.meta_inference_performed is False
    assert report.model_has_executed_tools is False
    assert report.human_review_required is True
    assert report.evidence_verified is True
    assert report.independent_audit_anchor_verified is True
    assert report.real_media_upload_authorized is False
    assert report.fall_confirmed is False
    assert report.notification_sent is False
    assert report.emergency_dispatch_authorized is False
    assert report.persistent_mutation_performed is False
    assert report.priority_code == "human_review_non_emergency"
    assert tuple(action.tool for action in report.actions) == CANONICAL_ORDER
    assert len(report.actions) == 3
    assert all(action.is_external_action is False for action in report.actions)
    assert all(action.completed_by_meta is False for action in report.actions)
    assert all(action.performed_as in (
        "read_only_verification", "nonbinding_review_draft",
    ) for action in report.actions)


def test_future_meta_proposal_can_reorder_only_allowlisted_readonly_tools(tmp_path):
    event_id, _, _, registry = prepared(tmp_path)
    props = offline_proposal(event_id)
    props.tools.reverse()
    parsed = validate_meta_proposal(
        props.model_dump_json().encode(), event_id=event_id,
    )
    result = build_copilot_preview(registry=registry, event_id=event_id, plan=parsed)
    assert result is not None
    assert [action.tool for action in result.actions] == [
        tool.tool for tool in parsed.tools
    ]
    assert result.meta_api_called is False
    assert result.model_has_executed_tools is False


@pytest.mark.parametrize("attack", [
    {"tools": []},
    {"tools": [{"tool": "notify_emergency", "event_id": "fake"}]},
    {"tools": [{"tool": "run_shell", "event_id": "fake"}]},
    {"tools": [{"tool": "send_to_meta", "event_id": "fake"}]},
    {"tools": [{"tool": "grant_consent", "event_id": "fake"}]},
    {"tools": [{"tool": "check_event_linkage", "event_id": "fake"}]},
    {"schema_version": "viil.meta.copilot.proposal.v99"},
    {"fall_confirmed": True},
    {"admin_access": True},
    {"event_id": "00000000-0000-4000-8000-000000000000"},
])
def test_model_attacks_are_never_executed(tmp_path, attack):
    event_id, _, _, _ = prepared(tmp_path)
    payload = json.loads(offline_proposal(event_id).model_dump_json())
    payload.update(attack)
    with pytest.raises(MetaProposalRejected):
        validate_meta_proposal(
            json.dumps(payload).encode("utf-8"), event_id=event_id,
        )


def test_nested_unknown_arguments_duplicate_fields_or_nonfinite_rejected(tmp_path):
    event_id, _, _, _ = prepared(tmp_path)
    source = offline_proposal(event_id).model_dump_json()
    nested = json.loads(source)
    nested["tools"][0]["command"] = "rm -rf"
    for raw in (
        json.dumps(nested).encode(),
        source[:-1].encode() + b', "event_id": "' + str(event_id).encode() + b'"}',
        b'{"schema_version":NaN}',
        b"x" * 5000,
        b"[]",
        b"{}",
    ):
        with pytest.raises(MetaProposalRejected):
            validate_meta_proposal(raw, event_id=event_id)


def test_duplicate_cross_event_and_partial_model_tool_plans_rejected(tmp_path):
    event_id, _, _, _ = prepared(tmp_path)
    source = json.loads(offline_proposal(event_id).model_dump_json())
    source["tools"][1]["tool"] = source["tools"][0]["tool"]
    for case in (
        source,
        {**json.loads(offline_proposal(event_id).model_dump_json()),
         "tools": [{"tool": MetaTool.CHECK_EVENT_LINKAGE, "event_id": str(event_id)}]},
        {**json.loads(offline_proposal(event_id).model_dump_json()),
         "tools": [
             {"tool": tool, "event_id": str(uuid4())} for tool in CANONICAL_ORDER
         ]},
    ):
        with pytest.raises(MetaProposalRejected):
            validate_meta_proposal(json.dumps(case).encode(), event_id=event_id)


def test_model_plan_is_no_permission_to_skip_signed_anchor(tmp_path):
    event_id, db, anchor, registry = prepared(tmp_path)
    model_plan = offline_proposal(event_id)
    anchor.unlink()
    with pytest.raises(ValueError):
        build_copilot_preview(registry=registry, event_id=event_id, plan=model_plan)
    loose_registry = SyntheticEvidenceRegistry(db)
    with pytest.raises(MetaCopilotUnavailable, match="independent audit anchor"):
        build_copilot_preview(registry=loose_registry, event_id=event_id, plan=model_plan)


def test_offline_meta_prompt_contains_only_synthetic_metadata_and_fixed_schema(tmp_path):
    event_id, _, _, registry = prepared(tmp_path)
    evidence = registry.get(event_id=event_id, source_id=SYNTHETIC_SOURCE)
    audit = registry.get_audit(event_id=event_id, source_id=SYNTHETIC_SOURCE)
    assert evidence is not None and audit is not None
    payload = build_offline_meta_planner_request(evidence, audit)
    assert payload["model"] == "muse-spark-1.3"
    assert payload["reasoning_effort"] == "minimal"
    assert payload["max_completion_tokens"] == 512
    assert payload["response_format"] == META_COPILOT_JSON_SCHEMA
    assert payload["response_format"]["json_schema"]["strict"] is True
    request_str = json.dumps(payload)
    assert str(event_id) in request_str
    assert evidence.candidate_sha256 in request_str
    assert "all_external_actions_permitted" in request_str
    assert "false" in request_str
    assert "data:image" not in request_str
    assert "Bearer " not in request_str
    assert "LLM_" not in request_str
    assert TOKEN not in request_str
    assert KEY.decode() not in request_str


def test_caregiver_preview_opt_in_auth_and_scope_over_http(tmp_path):
    event_id, db, anchor, _ = prepared(tmp_path)
    url = f"/api/v1/caregiver/copilot/{event_id}"
    with TestClient(create_app(settings(db, anchor))) as client:
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.get(url, headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["meta_api_called"] is False
        assert data["mode"] == "offline_readonly_shadow"
        assert data["event_id"] == str(event_id)
        assert data["independent_audit_anchor_verified"] is True
        assert data["human_review_required"] is True
        assert data["notification_sent"] is False
        assert "image_url" not in response.text
        assert "api_key" not in response.text
        assert client.post(url, json={}).status_code == 405
        assert client.put(url, json={}).status_code == 405
        assert client.delete(url).status_code == 405
        assert client.get(
            f"/api/v1/caregiver/copilot/{uuid4()}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ).status_code == 404
    with TestClient(create_app(settings(db, anchor)),
                    client=("203.0.113.42", 3211)) as remote:
        assert remote.get(
            url, headers={
                "Authorization": f"Bearer {TOKEN}",
                "X-Forwarded-For": "127.0.0.1",
            },
        ).status_code == 403


def test_copilot_is_default_off_and_requires_signed_anchor(tmp_path):
    event_id, db, anchor, _ = prepared(tmp_path)
    url = f"/api/v1/caregiver/copilot/{event_id}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings(
        db, anchor, meta_copilot_preview_enabled=False,
    ))) as client:
        assert client.get(url, headers=headers).status_code == 404
    with TestClient(create_app(settings(
        db, anchor, evidence_audit_anchor_required=False,
    ))) as client:
        assert client.get(url, headers=headers).status_code == 503
    with TestClient(create_app(settings(
        db, anchor, evidence_registry_enabled=False,
    ))) as client:
        assert client.get(url, headers=headers).status_code == 503
    with TestClient(create_app(settings(
        db, anchor, evidence_audit_anchor_secret=SecretStr("bad-key"),
    ))) as client:
        assert client.get(url, headers=headers).status_code == 503
    anchor.unlink()
    with TestClient(create_app(settings(db, anchor))) as client:
        assert client.get(url, headers=headers).status_code == 503
