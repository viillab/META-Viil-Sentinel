"""True Member1 Python Edge producer -> Member2 safe backend acceptance tests.

All subprocesses are local, isolated from secrets, and restricted to pinned
mathematical synthetic pose traces, not recordings, cameras or patient data.
"""
import json
import subprocess
from uuid import UUID

import pytest

from app import edge_emitter_e2e as bridge
from app.candidate_ingest import parse_candidate


def test_real_edge_cli_emits_frozen_synthetic_fall():
    events = bridge.edge_candidates_from_trace("fall")
    assert len(events) == 1
    candidate = parse_candidate(events[0])
    assert candidate.schema_version == "viil.edge.candidate.v1"
    assert candidate.event_id == UUID(str(candidate.event_id))
    assert candidate.source_id == "synthetic-clip-01"
    assert candidate.source_timestamp_ms == 850
    assert candidate.detector_score == pytest.approx(0.928)
    assert candidate.detector_score_type == "uncalibrated_heuristic"
    assert candidate.input_provenance == "synthetic_pose_trace"
    assert candidate.model_sha256 is None
    assert candidate.evidence_refs == []
    assert candidate.confirmed_fall is False
    assert candidate.simulated is True
    assert candidate.human_review_required is True


def test_real_edge_cli_emits_no_sitting_candidate():
    assert bridge.edge_candidates_from_trace("sitting") == []


@pytest.mark.parametrize("bad", [
    "real-video", "authorized_local_camera", "example", "../private",
    "", "FALL", "sitting.jsonl",
])
def test_only_pinned_synthetic_traces_are_permitted(bad):
    with pytest.raises(bridge.EdgeProducerSmokeError):
        bridge.edge_candidates_from_trace(bad)


def test_synthetic_trace_checksum_must_match_static_allowlist(monkeypatch):
    monkeypatch.setitem(bridge.EXPECTED_TRACE_HASHES, "fall", "0" * 64)
    with pytest.raises(bridge.EdgeProducerSmokeError, match="checksum mismatch"):
        bridge.edge_candidates_from_trace("fall")


def test_edge_child_process_does_not_inherit_meta_credentials(monkeypatch):
    sensitive = {
        "META_MODEL_API_KEY": "test-only-should-never-reach-child",
        "HIKVISION_PASSWORD": "test-only-never-forward",
        "EDGE_CANDIDATE_HMAC_SECRET": "test-only-never-forward",
        "CAREGIVER_INBOX_TOKEN": "test-only-never-forward",
        "AWS_SECRET_ACCESS_KEY": "test-only-never-forward",
    }
    for key, value in sensitive.items():
        monkeypatch.setenv(key, value)
    original_run = subprocess.run

    def observe_child(*args, **kwargs):
        child_env = kwargs["env"]
        assert all(key not in child_env for key in sensitive)
        assert kwargs["cwd"] == bridge.EDGE_ROOT
        assert kwargs["timeout"] <= 10
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        return original_run(*args, **kwargs)

    monkeypatch.setattr(bridge.subprocess, "run", observe_child)
    assert len(bridge.edge_candidates_from_trace("fall")) == 1


def test_child_process_timeout_is_safe_and_does_not_leak_data(monkeypatch):
    def fake_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["python"], timeout=3)

    monkeypatch.setattr(bridge.subprocess, "run", fake_timeout)
    with pytest.raises(bridge.EdgeProducerSmokeError, match="did not complete safely"):
        bridge.edge_candidates_from_trace("fall")


def test_child_process_failure_is_safe_and_does_not_echo_stderr(monkeypatch):
    class FakeResult:
        returncode = 1
        stderr = b"secret source data"
        stdout = b""

    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: FakeResult())
    with pytest.raises(bridge.EdgeProducerSmokeError) as caught:
        bridge.edge_candidates_from_trace("fall")
    assert "secret" not in str(caught.value)


def test_actual_python_edge_to_backend_to_caregiver_inbox(monkeypatch):
    # The explicitly disabled Meta settings must never activate a paid call.
    monkeypatch.setenv("META_MODEL_API_KEY", "fake-existing-meta-secret")
    summary = bridge.run_edge_emitter_e2e()
    assert summary["result"] == "REAL_EDGE_SYNTHETIC_TO_INBOX_PASS"
    assert summary["actual_python_detector"] is True
    assert summary["fall_candidate_count"] == 1
    assert summary["sitting_candidate_count"] == 0
    assert summary["fall_source_timestamp_ms"] == 850
    assert summary["uncalibrated_heuristic_score"] == pytest.approx(0.928)
    assert summary["signed_api_accepted"] is True
    assert summary["duplicate_event_rejected_without_new_advisory"] is True
    assert summary["forged_signature_rejected"] is True
    assert summary["real_camera_provenance_rejected"] is True
    assert summary["caregiver_metadata_inbox_verified"] is True
    assert summary["meta_api_called"] is False
    assert summary["notifications_sent"] is False
    assert summary["network_port_opened"] is False
    assert "fake-existing-meta-secret" not in json.dumps(summary)
