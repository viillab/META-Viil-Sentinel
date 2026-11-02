"""Contract/auth acceptance for synthetic-only caregiver inbox projection.

All tokens and candidates are fictional. No Meta calls, real cameras,
push delivery, HTTP servers, or real caregiver identity are involved.
"""
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import CandidateLedger, EdgeCandidate, sign_candidate
from app.config import Settings
from app.main import create_app

SOURCE = "synthetic-clip-01"
CAREGIVER_TOKEN = "test-local-caregiver-token-unique-from-edge-hmac-123456"
EDGE_KEY = "test-local-edge-hmac-other-unique-secret-123456789"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "edge-vision" / "examples" / "synthetic" / "candidate_v1.example.json"
SCHEMA = ROOT.parent / "handoff" / "team" / "caregiver_inbox.v1.schema.json"


def settings(tmp_path, **overrides):
    options = {
        "_env_file": None,
        "meta_provider": "mock",
        "demo_mode": False,
        "caregiver_inbox_enabled": True,
        "caregiver_inbox_token": SecretStr(CAREGIVER_TOKEN),
        "edge_candidate_source_id": SOURCE,
        "edge_candidate_ingest_enabled": True,
        "edge_candidate_hmac_secret": SecretStr(EDGE_KEY),
        "edge_candidate_ledger_path": str(tmp_path / "inbox.sqlite3"),
    }
    options.update(overrides)
    return Settings(**options)


def synthetic_candidate(*, source=SOURCE, event_id=None):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["source_id"] = source
    payload["event_id"] = str(event_id or uuid4())
    return payload


def post_candidate(client, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("ascii")
    stamp = str(int(time.time()))
    signature = sign_candidate(
        EDGE_KEY.encode("ascii"), source=payload["source_id"],
        timestamp=stamp, body=body,
    )
    return client.post(
        "/api/v1/edge/candidates",
        content=body,
        headers={
            "content-type": "application/json",
            "x-viil-source-id": payload["source_id"],
            "x-viil-timestamp": stamp,
            "x-viil-signature": signature,
        },
    )


def inbox_request(client, token=CAREGIVER_TOKEN):
    return client.get("/api/v1/caregiver/inbox", headers={"Authorization": f"Bearer {token}"})


def test_caregiver_inbox_disabled_by_default_does_not_create_db(tmp_path):
    config = settings(tmp_path, caregiver_inbox_enabled=False)
    with TestClient(create_app(config)) as client:
        assert inbox_request(client).status_code == 404
    assert not (tmp_path / "inbox.sqlite3").exists()


def test_strong_independent_secret_is_required(tmp_path):
    for token in (None, SecretStr("short"), SecretStr(EDGE_KEY)):
        with TestClient(create_app(settings(tmp_path, caregiver_inbox_token=token))) as client:
            assert inbox_request(client).status_code == 503
    assert not (tmp_path / "inbox.sqlite3").exists()


def test_inbox_empty_when_no_candidates_and_no_database_side_effect(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        response = inbox_request(client)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["schema_version"] == "viil.backend.caregiver_inbox.v1"
        assert data["access_scope"] == "authenticated_caregiver"
        assert data["advisories"] == []
        assert datetime.fromisoformat(data["generated_at"]).tzinfo is not None
    assert not (tmp_path / "inbox.sqlite3").exists()


def test_reads_verified_synthetic_receipt_and_maps_exact_ui_schema(tmp_path):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item_schema = schema["properties"]["advisories"]["items"]
    payload = synthetic_candidate()
    with TestClient(create_app(settings(tmp_path))) as client:
        assert post_candidate(client, payload).status_code == 201
        response = inbox_request(client)
        assert response.status_code == 200
        data = response.json()
        assert set(data) == set(schema["required"]) == set(schema["properties"])
        assert data["schema_version"] == "viil.backend.caregiver_inbox.v1"
        assert data["access_scope"] == "authenticated_caregiver"
        assert len(data["advisories"]) == 1
        item = data["advisories"][0]
        assert set(item) == set(item_schema["required"]) == set(item_schema["properties"])
        assert item["advisory_id"] == payload["event_id"]
        assert item["source_id"] == payload["source_id"]
        assert item["stage"] == "edge_candidate"
        assert item["context_code"] == "unknown"
        assert item["meta_provenance"] == "none"
        assert item["delivery_state"] == "not_sent"
        assert item["receipt_verified"] is False
        assert item["review_state"] == "pending"
        assert item["simulated"] is True
        assert item["fall_confirmed"] is False
        assert item["emergency_dispatch_authorized"] is False
        assert item["human_follow_up_required"] is True
        assert datetime.fromisoformat(item["occurred_at"]).tzinfo is not None
        assert "detector_score" not in response.text
        assert "digest" not in response.text
        assert "model_sha256" not in response.text
        assert "evidence_refs" not in response.text
        assert post_candidate(client, payload).status_code == 200
        assert len(inbox_request(client).json()["advisories"]) == 1


def test_inbox_never_exposes_unauthorized_cross_source_rows(tmp_path):
    db = tmp_path / "inbox.sqlite3"
    for source in (SOURCE, "synthetic-other-01"):
        payload = synthetic_candidate(source=source)
        raw = json.dumps(payload).encode("ascii")
        cand = EdgeCandidate.model_validate_json(raw, strict=True)
        CandidateLedger(db).accept(cand, raw=raw)
    with TestClient(create_app(settings(tmp_path))) as client:
        response = inbox_request(client)
        assert response.status_code == 200
        advisories = response.json()["advisories"]
        assert len(advisories) == 1
        assert advisories[0]["source_id"] == SOURCE
        assert "synthetic-other-01" not in response.text


def test_source_scope_must_fit_ui_contract_and_be_synthetic(tmp_path):
    for source in ("synthetic.with.dot", "camera-01", "../folder"):
        with TestClient(create_app(settings(tmp_path, edge_candidate_source_id=source))) as client:
            assert inbox_request(client).status_code == 503


def test_caregiver_auth_missing_wrong_oversized_duplicate_and_remote(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/api/v1/caregiver/inbox").status_code == 401
        assert client.get("/api/v1/caregiver/inbox", headers={"Authorization": "basic foo"}).status_code == 401
        assert inbox_request(client, token="wrong-token-other-example-with-more-than-32-bytes").status_code == 401
        assert inbox_request(client, token="a" * 512).status_code == 401
        duplicate = client.get(
            "/api/v1/caregiver/inbox",
            headers=[
                ("Authorization", f"Bearer {CAREGIVER_TOKEN}"),
                ("Authorization", f"Bearer {CAREGIVER_TOKEN}"),
            ],
        )
        assert duplicate.status_code == 401
    with TestClient(
        create_app(settings(tmp_path)),
        client=("203.0.113.9", 54321),
    ) as remote:
        assert inbox_request(remote).status_code == 403


def test_max_30_records_no_person_data_and_source_receipt_time(tmp_path):
    db = tmp_path / "inbox.sqlite3"
    base_time = int(datetime(2026, 11, 2, tzinfo=UTC).timestamp())
    for n in range(35):
        payload = synthetic_candidate()
        raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
        CandidateLedger(db).accept(
            EdgeCandidate.model_validate_json(raw, strict=True),
            raw=raw,
            now_seconds=base_time + (n * 61),
        )
    with TestClient(create_app(settings(tmp_path))) as client:
        response = inbox_request(client)
        assert response.status_code == 200
        advisories = response.json()["advisories"]
        assert len(advisories) == 30
        dates = [datetime.fromisoformat(item["occurred_at"]) for item in advisories]
        assert dates == sorted(dates, reverse=True)
        assert all(item["meta_provenance"] == "none" for item in advisories)
        assert all(item["delivery_state"] == "not_sent" for item in advisories)
        assert all(item["fall_confirmed"] is False for item in advisories)
        assert all(item["emergency_dispatch_authorized"] is False for item in advisories)
        assert len(response.content) < 32 * 1024


def test_non_demo_ingest_and_inbox_coexist_but_no_incident_read(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert post_candidate(client, synthetic_candidate()).status_code == 201
        assert inbox_request(client).status_code == 200
        assert client.get("/api/v1/incidents").status_code == 403
        assert client.post("/api/v1/incidents/demo", json={}).status_code == 403
        assert client.post(
            "/api/v1/incidents/00000000-0000-4000-8000-000000000000/review",
            json={"action": "ACKNOWLEDGE", "actor": "untrusted"},
        ).status_code == 403
