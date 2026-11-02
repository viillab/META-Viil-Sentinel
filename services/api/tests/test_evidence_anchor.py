"""Offline, fail-closed tests for separate signed audit checkpoints."""
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidate_ingest import CandidateLedger, parse_candidate
from app.config import Settings
from app.edge_emitter_e2e import edge_candidates_from_trace
from app.evidence_anchor import (
    AnchorRejected,
    capture_checkpoint,
    verify_checkpoint,
)
from app.evidence_audit import _entry_hash, _payload, verify_audit_chain
from app.evidence_registry import EvidenceRegistryRejected, SyntheticEvidenceRegistry
from app.main import create_app
from app.synthetic_evidence import build_synthetic_evidence

KEY = b"fake-test-only-independent-audit-anchor-key-12345678901234567"
OTHER = b"other-test-only-independent-anchor-key-123456789012345678"
CARE = "fake-independent-caretaker-read-only-token-1234567890123"


def paths(tmp_path):
    db = tmp_path / "local-ledger" / "receipts.sqlite3"
    anchor = tmp_path / "separate-anchor" / "signed-head.json"
    anchor.parent.mkdir()
    return db, anchor


def new_event(db, raw=None):
    if raw is None:
        produced = edge_candidates_from_trace("fall")
        assert len(produced) == 1
        raw = produced[0]
    receipt = CandidateLedger(db).accept(parse_candidate(raw), raw=raw)
    record, duplicate = SyntheticEvidenceRegistry(db).register(
        raw_candidate=raw,
        evidence=build_synthetic_evidence(raw),
    )
    assert duplicate is False
    assert str(record.event_id) == str(receipt.event_id)
    return record


def test_checkpoint_is_independently_signed_and_idempotent(tmp_path):
    db, anchor = paths(tmp_path)
    record = new_event(db)
    signed = capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    assert signed.schema_version == "viil.synthetic.audit_anchor.v1"
    assert signed.record_count == 1
    assert signed.first_event_id == record.event_id
    assert signed.last_event_id == record.event_id
    assert signed.consent_state == "not_verified_for_real_media"
    assert signed.external_upload_authorized is False
    assert signed.meta_call_permitted is False
    assert len(signed.hmac_sha256) == 64
    assert verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY) == signed
    assert capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY) == signed
    content = anchor.read_text()
    assert "fake-test-only" not in content
    assert "LLM_" not in content
    assert "data:image" not in content
    assert "landmarks" not in content
    assert "real_media_verified" not in content


def test_invalid_keys_missing_file_wrong_location_and_no_data_fail_closed(tmp_path):
    db, anchor = paths(tmp_path)
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    record = new_event(db)
    for bad_key in (b"", b"short", OTHER):
        if len(bad_key) < 32:
            with pytest.raises(AnchorRejected):
                capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=bad_key)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=OTHER)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=OTHER)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(
            db_path=db, checkpoint_path=db.parent / "bad.json", secret=KEY,
        )
    assert record.event_id is not None


@pytest.mark.parametrize("mutate", ["mac", "flag", "duplicate", "truncate", "oversize"])
def test_tampered_checkpoint_is_rejected(tmp_path, mutate):
    db, anchor = paths(tmp_path)
    new_event(db)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    obj = json.loads(anchor.read_text())
    if mutate == "mac":
        obj["hmac_sha256"] = "f" * 64
        anchor.write_text(json.dumps(obj))
    elif mutate == "flag":
        obj["external_upload_authorized"] = True
        anchor.write_text(json.dumps(obj))
    elif mutate == "duplicate":
        raw = anchor.read_text()
        anchor.write_text(raw[:-1] + ', "record_count": 1}')
    elif mutate == "truncate":
        anchor.write_bytes(b"{")
    else:
        anchor.write_bytes(b"X" * 5000)
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)


def test_coordinated_sqlite_rewrite_is_detected_even_when_internal_hash_chain_passes(tmp_path):
    db, anchor = paths(tmp_path)
    record = new_event(db)
    captured = capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT sequence,event_id,source_id,occurred_at_utc,candidate_sha256,"
            "manifest_sha256,previous_hash FROM synthetic_evidence_audit"
        ).fetchone()
        sequence, event_id, source_id, old_stamp, candidate_hash, manifest_hash, prior = row
        new_stamp = "2026-01-01T00:00:00+00:00"
        assert old_stamp != new_stamp
        new_hash = _entry_hash(_payload(
            sequence=sequence, event_id=event_id, source_id=source_id,
            occurred_at_utc=new_stamp, candidate_sha256=candidate_hash,
            manifest_sha256=manifest_hash, previous_hash=prior,
        ))
        conn.execute(
            "UPDATE synthetic_evidence_audit SET occurred_at_utc=?,entry_hash=? "
            "WHERE event_id=?",
            (new_stamp, new_hash, event_id),
        )
        conn.execute(
            "UPDATE synthetic_evidence_registry SET registered_at_utc=? "
            "WHERE event_id=?", (new_stamp, event_id),
        )
    with sqlite3.connect(db) as conn:
        assert verify_audit_chain(conn)[0].entry_hash == new_hash
    assert new_hash != captured.last_entry_hash
    with pytest.raises(AnchorRejected, match="disagrees"):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    assert str(record.event_id) == event_id


def test_deleted_entire_chain_detected_by_anchor(tmp_path):
    db, anchor = paths(tmp_path)
    new_event(db)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM synthetic_evidence_audit")
        conn.execute("DELETE FROM synthetic_evidence_registry")
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)


def test_checkpoint_extension_is_explicit_and_prevents_rollback(tmp_path):
    db, anchor = paths(tmp_path)
    first = new_event(db)
    captured_first = capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    original = json.loads(edge_candidates_from_trace("fall")[0])
    original["event_id"] = str(uuid4())
    second_bytes = json.dumps(original, separators=(",", ":")).encode()
    second = new_event(db, raw=second_bytes)
    with pytest.raises(AnchorRejected, match="stale"):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    upgraded = capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    assert upgraded.record_count == 2
    assert upgraded.first_event_id == first.event_id
    assert upgraded.last_event_id == second.event_id
    assert upgraded.last_entry_hash != captured_first.last_entry_hash
    assert verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY) == upgraded
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM synthetic_evidence_registry WHERE event_id=?",
                     (str(second.event_id),))
        conn.execute("DELETE FROM synthetic_evidence_audit WHERE event_id=?",
                     (str(second.event_id),))
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)


def test_api_opt_in_requires_signed_anchor_and_preserves_caregiver_auth(tmp_path):
    db, anchor = paths(tmp_path)
    record = new_event(db)
    settings = Settings(
        _env_file=None, meta_provider="mock", meta_model_api_key=None,
        edge_candidate_ledger_path=str(db),
        evidence_registry_enabled=True,
        caregiver_inbox_token=SecretStr(CARE),
        evidence_audit_anchor_required=True,
        evidence_audit_anchor_path=str(anchor),
        evidence_audit_anchor_secret=SecretStr(KEY.decode()),
    )
    url = f"/api/v1/caregiver/evidence/{record.event_id}"
    token = {"Authorization": f"Bearer {CARE}"}
    with TestClient(create_app(settings)) as client:
        assert client.get(url, headers=token).status_code == 503
        assert client.get(url + "/audit", headers=token).status_code == 503
        capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
        good = client.get(url, headers=token)
        good_audit = client.get(url + "/audit", headers=token)
        assert good.status_code == 200
        assert good_audit.status_code == 200
        assert good.headers["cache-control"] == "no-store"
        assert good_audit.json()["chain_verified"] is True
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": "Bearer " + "x" * 45}).status_code == 401
        assert client.post(url + "/audit", headers=token, json={}).status_code == 405
        anchor.unlink()
        assert client.get(url, headers=token).status_code == 503
        assert client.get(url + "/audit", headers=token).status_code == 503
    anchored = SyntheticEvidenceRegistry(
        db, anchor_required=True, anchor_path=anchor, anchor_secret=KEY,
    )
    with pytest.raises(EvidenceRegistryRejected, match="read-only"):
        anchored.register(raw_candidate=b"{}", evidence=build_synthetic_evidence(
            edge_candidates_from_trace("fall")[0]
        ))


def test_api_fail_closed_for_partial_or_wrong_anchor_config(tmp_path):
    db, anchor = paths(tmp_path)
    record = new_event(db)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    for fields in (
        {"evidence_audit_anchor_secret": None},
        {"evidence_audit_anchor_path": None},
        {"evidence_audit_anchor_secret": SecretStr(OTHER.decode())},
    ):
        options = {
            "_env_file": None,
            "meta_provider": "mock",
            "edge_candidate_ledger_path": str(db),
            "evidence_registry_enabled": True,
            "caregiver_inbox_token": SecretStr(CARE),
            "evidence_audit_anchor_required": True,
            "evidence_audit_anchor_path": str(anchor),
            "evidence_audit_anchor_secret": SecretStr(KEY.decode()),
        }
        options.update(fields)
        settings = Settings(**options)
        with TestClient(create_app(settings)) as client:
            assert client.get(
                f"/api/v1/caregiver/evidence/{record.event_id}",
                headers={"Authorization": f"Bearer {CARE}"},
            ).status_code == 503


def test_valid_signed_anchor_from_other_ledger_cannot_be_replayed(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    db_one, anchor_one = paths(first_dir)
    db_two, anchor_two = paths(second_dir)
    one = new_event(db_one)
    two = new_event(db_two)
    assert one.event_id != two.event_id
    capture_checkpoint(db_path=db_one, checkpoint_path=anchor_one, secret=KEY)
    anchor_two.write_bytes(anchor_one.read_bytes())
    with pytest.raises(AnchorRejected, match="disagrees"):
        verify_checkpoint(db_path=db_two, checkpoint_path=anchor_two, secret=KEY)


def test_checkpoint_symlink_rejected_without_following_target(tmp_path):
    db, anchor = paths(tmp_path)
    new_event(db)
    capture_checkpoint(db_path=db, checkpoint_path=anchor, secret=KEY)
    alias = anchor.parent / "alias.json"
    try:
        alias.symlink_to(anchor)
    except (OSError, NotImplementedError):
        pytest.skip("This Windows profile does not allow creating symlinks")
    with pytest.raises(AnchorRejected):
        verify_checkpoint(db_path=db, checkpoint_path=alias, secret=KEY)
    with pytest.raises(AnchorRejected):
        capture_checkpoint(db_path=db, checkpoint_path=alias, secret=KEY)
