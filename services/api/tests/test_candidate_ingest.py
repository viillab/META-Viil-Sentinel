"""Synthetic Edge candidate v1 -> signed backend -> durable metadata receipt tests.

No camera, frames, Meta, network connection or user credentials are used.
"""
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import (
    MAX_BODY_BYTES,
    MAX_REQUESTS_PER_MINUTE,
    CandidateLedger,
    EdgeCandidate,
    sign_candidate,
)
from app.config import Settings
from app.main import create_app
from app.synthetic_intake_smoke import run_smoke

SOURCE = "synthetic-clip-01"
KEY = "unit-test-only-synthetic-hmac-secret-with-more-than-32-bytes"
EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "edge-vision" / "examples" / "synthetic" / "candidate_v1.example.json"
)
SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "edge-vision" / "docs" / "edge_candidate_v1.schema.json"
)


def sample(*, event_id=None, **patch):
    candidate = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    candidate["event_id"] = str(event_id or uuid4())
    candidate.update(patch)
    return candidate


def new_client(tmp_path, **settings):
    options = {
        "meta_provider": "mock",
        "demo_mode": True,
        "edge_candidate_ingest_enabled": True,
        "edge_candidate_hmac_secret": SecretStr(KEY),
        "edge_candidate_source_id": SOURCE,
        "edge_candidate_ledger_path": str(tmp_path / "candidate-ledger.sqlite3"),
    }
    options.update(settings)
    return TestClient(create_app(Settings(_env_file=None, **options)))


def request(api, candidate, *, key=KEY, timestamp=None, source=SOURCE, headers=None, raw=None):
    body = raw if raw is not None else json.dumps(candidate).encode("utf-8")
    sent = str(int(time.time()) if timestamp is None else timestamp)
    signed_headers = {
        "content-type": "application/json",
        "x-viil-source-id": source,
        "x-viil-timestamp": sent,
        "x-viil-signature": sign_candidate(key.encode(), source=source, timestamp=sent, body=body),
    }
    if headers:
        signed_headers.update(headers)
    return api.post("/api/v1/edge/candidates", content=body, headers=signed_headers)


def test_canonical_v1_contract_is_frozen_and_strict():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(EdgeCandidate.model_fields)
    assert set(schema["properties"]) == set(EdgeCandidate.model_fields)
    assert schema["properties"]["confirmed_fall"]["const"] is False
    assert schema["properties"]["evidence_refs"]["maxItems"] == 0
    assert schema["properties"]["timestamp_basis"]["const"] == "relative_to_source_start"
    assert schema["properties"]["delivery_mode"]["const"] == "local_stdout_only"
    assert EdgeCandidate.model_validate_json(EXAMPLE.read_bytes(), strict=True)


def test_default_disabled_even_if_demo_api_is_on(tmp_path):
    config = Settings(
        _env_file=None,
        meta_provider="mock",
        demo_mode=True,
        edge_candidate_ingest_enabled=False,
        edge_candidate_ledger_path=str(tmp_path / "unused.sqlite3"),
    )
    with TestClient(create_app(config)) as api:
        result = request(api, sample())
        assert result.status_code == 404
    assert not (tmp_path / "unused.sqlite3").exists()


def test_missing_or_weak_key_fails_closed(tmp_path):
    for secret in (None, SecretStr("tiny")):
        with new_client(tmp_path, edge_candidate_hmac_secret=secret) as api:
            assert request(api, sample()).status_code == 503
    assert not (tmp_path / "candidate-ledger.sqlite3").exists()


def test_authenticated_synthetic_event_is_durable_and_idempotent(tmp_path):
    payload = sample()
    with new_client(tmp_path) as api:
        response = request(api, payload)
        assert response.status_code == 201
        receipt = response.json()
        assert receipt["event_id"] == payload["event_id"]
        assert receipt["schema_version"] == "viil.backend.candidate_receipt.v1"
        assert receipt["accepted"] is True and receipt["duplicate"] is False
        assert receipt["confirmed_fall"] is False
        assert receipt["meta_called"] is False and receipt["notification_sent"] is False
        assert receipt["review_required"] is True
        assert receipt["source_timestamp_basis"] == "relative_to_source_start"
        assert "confidence" not in receipt
        assert "camera_url" not in receipt
        assert request(api, payload).status_code == 200
    with new_client(tmp_path) as second_api:
        second = request(second_api, payload)
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["received_at_utc"] == receipt["received_at_utc"]
    assert CandidateLedger(tmp_path / "candidate-ledger.sqlite3").path.is_file()


@pytest.mark.parametrize("change", [
    {"input_provenance": "authorized_local_camera", "simulated": False},
    {"input_provenance": "consented_staged_video"},
    {"confirmed_fall": True},
    {"human_review_required": False},
    {"medical_assessment_performed": True},
    {"score_calibrated": True},
    {"detector_score_type": "calibrated_probability"},
    {"model_sha256": "a" * 64},
    {"evidence_refs": ["private-camera-frame"]},
    {"simulated": False},
    {"delivery_mode": "https"},
    {"timestamp_basis": "unix_epoch"},
    {"source_timestamp_ms": -1},
    {"source_timestamp_ms": True},
    {"source_timestamp_ms": 24 * 60 * 60 * 1000 + 1},
    {"detector_score": 2},
    {"detector_score": "0.99"},
    {"detector_score": False},
    {"source_id": "../secret"},
    {"source_id": "patient@example.com"},
    {"detector": "invalid detector"},
    {"raw_image": "private_person_data"},
    {"medical_severity": "critical"},
    {"camera_password": "no"},
])
def test_signed_but_unsafe_payloads_are_rejected(tmp_path, change):
    with new_client(tmp_path) as api:
        result = request(api, sample(**change))
        assert result.status_code in (403, 422)
        assert "private_person_data" not in result.text


def test_forged_signed_body_cannot_change_source_identity(tmp_path):
    with new_client(tmp_path) as api:
        payload = sample()
        body = json.dumps(payload).encode()
        assert request(api, payload, key="bad-key", raw=body).status_code == 401
        assert request(api, payload, source="another-synthetic").status_code == 401
        assert request(
            api, payload, headers={"x-viil-signature": "sha256=" + "0" * 64},
        ).status_code == 401
        assert request(api, sample(), timestamp=int(time.time()) - 70).status_code == 401
        assert request(api, sample(), timestamp=int(time.time()) + 70).status_code == 401


def test_body_size_content_type_and_duplicate_key_are_rejected(tmp_path):
    with new_client(tmp_path) as api:
        assert request(
            api, sample(), headers={"content-type": "text/plain"},
        ).status_code == 415
        assert request(api, sample(), raw=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
        duplicate = EXAMPLE.read_text(encoding="utf-8").replace(
            '"confirmed_fall": false', '"confirmed_fall": false, "confirmed_fall": false',
        ).encode()
        assert request(api, sample(), raw=duplicate).status_code == 422
        assert request(
            api, sample(), raw=b'{"schema_version": "viil.edge.candidate.v1", '
            b'"detector_score": NaN}',
        ).status_code == 422


def test_conflicting_duplicate_event_id_is_never_overwritten(tmp_path):
    event_id = uuid4()
    with new_client(tmp_path) as api:
        assert request(api, sample(event_id=event_id)).status_code == 201
        assert request(api, sample(event_id=event_id, detector_score=0.4)).status_code == 409
        assert request(api, sample(event_id=event_id)).status_code == 200


def test_persistent_source_rate_limit_blocks_replay_flood(tmp_path):
    with new_client(tmp_path) as api:
        for _ in range(MAX_REQUESTS_PER_MINUTE):
            assert request(api, sample()).status_code == 201
        assert request(api, sample()).status_code == 429
    with new_client(tmp_path) as restarted:
        assert request(restarted, sample()).status_code == 429


def test_authentication_is_required_even_when_demo_mode_is_off(tmp_path):
    with new_client(tmp_path, demo_mode=False) as api:
        assert api.get("/api/v1/incidents").status_code == 403
        assert api.get("/api/v1/incidents/00000000-0000-4000-8000-000000000000").status_code == 403
        assert request(api, sample()).status_code == 201
        assert api.get("/api/v1/incidents").status_code == 403


def test_does_not_trust_unregistered_source_even_if_signature_matches(tmp_path):
    with new_client(tmp_path, edge_candidate_source_id="camera-01") as api:
        assert request(api, sample()).status_code == 503


def test_remote_client_is_denied_even_with_valid_source_hmac(tmp_path):
    settings = Settings(
        _env_file=None,
        meta_provider="mock",
        edge_candidate_ingest_enabled=True,
        edge_candidate_source_id=SOURCE,
        edge_candidate_hmac_secret=SecretStr(KEY),
        edge_candidate_ledger_path=str(tmp_path / "remote-denied.sqlite3"),
    )
    with TestClient(
        create_app(settings), client=("203.0.113.10", 12345),
    ) as remote:
        assert request(remote, sample()).status_code == 403
    assert not (tmp_path / "remote-denied.sqlite3").exists()


def test_no_network_end_to_end_cli_uses_real_member1_fixture():
    result = run_smoke()
    assert result["result"] == "OFFLINE_SYNTHETIC_INTAKE_PASS"
    assert result["deduplicated_on_retry"] is True
    assert result["real_camera_provenance_rejected"] is True
    assert result["public_network_used"] is False
    assert result["meta_called"] is False
    assert result["caregiver_notification_sent"] is False
