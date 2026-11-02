"""Synthetic evidence registry is private, non-clinical, metadata-only and fail-closed."""
import hashlib
import json
import sqlite3
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import sign_candidate
from app.config import Settings
from app.edge_emitter_e2e import SYNTHETIC_SOURCE, edge_candidates_from_trace
from app.evidence_registry import (
    EvidenceRegistryRejected,
    EvidenceRegistryUnavailable,
    SyntheticEvidenceRegistry,
)
from app.main import create_app
from app.synthetic_evidence import EvidenceRejected, build_synthetic_evidence

EDGE_SECRET = "synthetic-registry-only-fake-edge-signing-key-000001"
CARE_TOKEN = "synthetic-registry-only-fake-independent-caregiver-key-0002"
GET_PREFIX = "/api/v1/caregiver/evidence/"


@pytest.fixture
def raw():
    candidates = edge_candidates_from_trace("fall")
    assert len(candidates) == 1
    return candidates[0]


def configuration(tmp_path, **overrides):
    fields = {
        "_env_file": None,
        "meta_provider": "mock",
        "meta_model_api_key": None,
        "meta_live_enabled": False,
        "demo_mode": False,
        "edge_candidate_ingest_enabled": True,
        "edge_candidate_source_id": SYNTHETIC_SOURCE,
        "edge_candidate_hmac_secret": SecretStr(EDGE_SECRET),
        "edge_candidate_ledger_path": str(tmp_path / "receipts.sqlite3"),
        "caregiver_inbox_enabled": True,
        "caregiver_inbox_token": SecretStr(CARE_TOKEN),
        "evidence_registry_enabled": True,
    }
    fields.update(overrides)
    return Settings(**fields)


def ingest(client, raw):
    stamp = str(int(time.time()))
    response = client.post(
        "/api/v1/edge/candidates",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-viil-source-id": SYNTHETIC_SOURCE,
            "x-viil-timestamp": stamp,
            "x-viil-signature": sign_candidate(
                EDGE_SECRET.encode(), source=SYNTHETIC_SOURCE, timestamp=stamp, body=raw,
            ),
        },
    )
    assert response.status_code == 201
    return response.json()


def get(client, event_id, token=CARE_TOKEN):
    return client.get(
        GET_PREFIX + str(event_id),
        headers={"Authorization": f"Bearer {token}"},
    )


def test_requires_committed_event_receipt_before_any_registry_write(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    registry = SyntheticEvidenceRegistry(path)
    with pytest.raises(EvidenceRegistryUnavailable):
        registry.register(raw_candidate=raw, evidence=build_synthetic_evidence(raw))
    assert not path.exists()


def test_real_signed_http_intake_registers_exact_metadata_and_reads_no_media(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        receipt = ingest(client, raw)
        registry = SyntheticEvidenceRegistry(path)
        evidence = build_synthetic_evidence(raw)
        record, duplicate = registry.register(raw_candidate=raw, evidence=evidence)
        assert duplicate is False
        assert str(record.event_id) == receipt["event_id"]
        assert record.candidate_sha256 == hashlib.sha256(raw).hexdigest()
        assert record.image_sha256 == hashlib.sha256(evidence.png).hexdigest()
        assert record.image_bytes_stored is False
        assert record.external_upload_authorized is False
        assert record.real_person_evidence_verified is False
        assert record.consent_state == "not_verified_for_real_media"
        assert record.meta_called is False
        assert record.fall_confirmed is False
        assert record.notification_sent is False
        assert record.registered_at_utc.tzinfo is not None
        response = get(client, record.event_id)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == set(record.model_dump(mode="json"))
        assert response.json()["event_id"] == receipt["event_id"]
        assert response.json()["simulated"] is True
        assert response.json()["image_bytes_stored"] is False
        assert "data:image" not in response.text
        assert "landmarks" not in response.text
        assert "image/png;base64" not in response.text
        assert "meta_called" in response.json()
        rows = client.get(
            "/api/v1/caregiver/inbox", headers={"Authorization": f"Bearer {CARE_TOKEN}"},
        )
        assert rows.status_code == 200
        assert rows.json()["advisories"][0]["meta_provenance"] == "none"
        assert rows.json()["advisories"][0]["fall_confirmed"] is False
    db_bytes = path.read_bytes()
    assert evidence.png not in db_bytes
    assert b"\x89PNG\r\n\x1a\n" not in db_bytes
    assert b"pose-landmarks" not in db_bytes
    assert b"data:image/png;base64" not in db_bytes


def test_duplicate_registration_is_idempotent_without_changed_receipt(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    registry = SyntheticEvidenceRegistry(path)
    evidence = build_synthetic_evidence(raw)
    first, duplicate = registry.register(raw_candidate=raw, evidence=evidence)
    second, duplicate_second = registry.register(raw_candidate=raw, evidence=evidence)
    assert duplicate is False
    assert duplicate_second is True
    assert first == second
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM synthetic_evidence_registry").fetchone()[0] == 1


def test_wrong_body_digest_rejected_even_with_correct_event_uuid(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    altered = json.dumps(json.loads(raw), separators=(", ", ": ")).encode("utf-8")
    assert altered != raw
    different_bundle = build_synthetic_evidence(altered)
    with pytest.raises(EvidenceRegistryRejected, match="matching signed"):
        SyntheticEvidenceRegistry(path).register(
            raw_candidate=altered, evidence=different_bundle,
        )
    assert SyntheticEvidenceRegistry(path).get(
        event_id=different_bundle.manifest.event_id, source_id=SYNTHETIC_SOURCE
    ) is None


def test_unseen_different_event_uuid_rejected_even_if_fixture_valid(tmp_path, raw):
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    candidate = json.loads(raw)
    candidate["event_id"] = str(uuid4())
    never_signed = json.dumps(candidate).encode("ascii")
    with pytest.raises(EvidenceRegistryRejected):
        SyntheticEvidenceRegistry(tmp_path / "receipts.sqlite3").register(
            raw_candidate=never_signed,
            evidence=build_synthetic_evidence(never_signed),
        )


def test_modified_image_or_fake_consent_is_rejected_before_sqlite_insert(tmp_path, raw):
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    bundle = build_synthetic_evidence(raw)
    corrupted = bytearray(bundle.png)
    corrupted[60] ^= 1
    registry = SyntheticEvidenceRegistry(tmp_path / "receipts.sqlite3")
    with pytest.raises(EvidenceRejected):
        registry.register(
            raw_candidate=raw, evidence=replace(bundle, png=bytes(corrupted)),
        )
    dishonest = bundle.manifest.model_copy(update={"external_upload_authorized": True})
    with pytest.raises(EvidenceRejected):
        registry.register(raw_candidate=raw, evidence=replace(bundle, manifest=dishonest))
    assert registry.get(event_id=bundle.manifest.event_id, source_id=SYNTHETIC_SOURCE) is None


def test_malformed_or_wrong_source_scope_is_rejected(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    registry = SyntheticEvidenceRegistry(path)
    with pytest.raises(EvidenceRegistryRejected):
        registry.get(event_id=uuid4(), source_id="synthetic-other-01")
    with pytest.raises(EvidenceRegistryRejected):
        registry.get(event_id=uuid4(), source_id="hikvision-camera")
    with pytest.raises(EvidenceRejected):
        registry.register(raw_candidate=b'{"real_person":true}', evidence=build_synthetic_evidence(raw))


def test_corrupt_registry_record_returns_503_fail_closed(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
        registry = SyntheticEvidenceRegistry(path)
        record, _ = registry.register(
            raw_candidate=raw, evidence=build_synthetic_evidence(raw),
        )
        with sqlite3.connect(path) as connection:
            obj = json.loads(connection.execute(
                "SELECT manifest_json FROM synthetic_evidence_registry"
            ).fetchone()[0])
            obj["external_upload_authorized"] = True
            connection.execute(
                "UPDATE synthetic_evidence_registry SET manifest_json=?",
                (json.dumps(obj),),
            )
        response = get(client, record.event_id)
        assert response.status_code == 503
        assert "true" not in response.text.lower()
        with pytest.raises(EvidenceRegistryRejected):
            registry.get(event_id=record.event_id, source_id=SYNTHETIC_SOURCE)


def test_missing_registry_is_404_not_database_created(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        event_id = str(uuid4())
        assert get(client, event_id).status_code == 404
        assert not path.exists()
        receipt = ingest(client, raw)
        assert get(client, receipt["event_id"]).status_code == 404
        with sqlite3.connect(path) as connection:
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE name='synthetic_evidence_registry'"
            ).fetchone() is None


def test_disabled_by_default_route_404_without_creating_db(tmp_path):
    settings = configuration(tmp_path, evidence_registry_enabled=False)
    with TestClient(create_app(settings)) as client:
        assert get(client, uuid4()).status_code == 404
    assert not (tmp_path / "receipts.sqlite3").exists()


@pytest.mark.parametrize("token", ["wrong-authorization-token-with-enough-chars", "a" * 200])
def test_caregiver_wrong_or_oversized_token_rejected(tmp_path, token):
    with TestClient(create_app(configuration(tmp_path))) as client:
        assert get(client, uuid4(), token=token).status_code == 401


def test_caregiver_missing_duplicate_and_remote_rejected(tmp_path):
    config = configuration(tmp_path)
    with TestClient(create_app(config)) as client:
        assert client.get(GET_PREFIX + str(uuid4())).status_code == 401
        duplicated = client.get(
            GET_PREFIX + str(uuid4()),
            headers=[
                ("Authorization", f"Bearer {CARE_TOKEN}"),
                ("Authorization", f"Bearer {CARE_TOKEN}"),
            ],
        )
        assert duplicated.status_code == 401
    with TestClient(create_app(config), client=("203.0.113.9", 9876)) as remote:
        event_id = str(uuid4())
        assert get(remote, event_id).status_code == 403
        assert remote.get(
            GET_PREFIX + event_id,
            headers={
                "Authorization": f"Bearer {CARE_TOKEN}",
                "X-Forwarded-For": "127.0.0.1",
                "Host": "localhost:5173",
            },
        ).status_code == 403


def test_weak_caregiver_key_and_reused_signer_disabled(tmp_path):
    for setting in (None, SecretStr("too-short"), SecretStr(EDGE_SECRET)):
        with TestClient(create_app(configuration(
            tmp_path, caregiver_inbox_token=setting,
        ))) as client:
            assert get(client, uuid4()).status_code == 503


def test_readonly_api_never_exposes_mutations(tmp_path):
    with TestClient(create_app(configuration(tmp_path))) as client:
        assert client.post(GET_PREFIX + str(uuid4()), json={}).status_code == 405
        assert client.put(GET_PREFIX + str(uuid4()), json={}).status_code == 405
        assert client.delete(GET_PREFIX + str(uuid4())).status_code == 405


def test_missing_or_corrupted_signed_receipt_is_not_usable(tmp_path, raw):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
        registry = SyntheticEvidenceRegistry(path)
        record, _ = registry.register(
            raw_candidate=raw, evidence=build_synthetic_evidence(raw),
        )
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE candidates SET digest=? WHERE event_id=?",
                ("0" * 64, str(record.event_id)),
            )
        # A well-formed but forged digest must never become a trusted receipt.
        # SQLite already rejects NULL digests at its schema layer.
        assert get(client, record.event_id).status_code == 503
        with pytest.raises(EvidenceRegistryRejected):
            registry.get(event_id=record.event_id, source_id=SYNTHETIC_SOURCE)


def test_registry_capacity_limit_does_not_write_rows(tmp_path, raw, monkeypatch):
    from app import evidence_registry as evidence_module

    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
    monkeypatch.setattr(evidence_module, "MAX_STORED_EVENTS", 0)
    registry = SyntheticEvidenceRegistry(path)
    with pytest.raises(evidence_module.EvidenceRegistryFull):
        registry.register(raw_candidate=raw, evidence=build_synthetic_evidence(raw))
    assert registry.get(
        event_id=build_synthetic_evidence(raw).manifest.event_id,
        source_id=SYNTHETIC_SOURCE,
    ) is None


def test_no_meta_billing_ledger_or_image_is_stored(tmp_path, raw):
    billing_path = tmp_path / "model_spend.sqlite3"
    with TestClient(create_app(configuration(tmp_path))) as client:
        ingest(client, raw)
        SyntheticEvidenceRegistry(tmp_path / "receipts.sqlite3").register(
            raw_candidate=raw, evidence=build_synthetic_evidence(raw),
        )
    assert not billing_path.exists()
    assert not (tmp_path / "evidence.png").exists()
