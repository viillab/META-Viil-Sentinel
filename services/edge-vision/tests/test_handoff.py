"""Strict versioned payload contract checks without external API access."""
import json
from uuid import uuid4

import pytest

from sentinel_edge.contracts import FallCandidateEvent
from sentinel_edge.handoff import SCHEMA_VERSION, to_envelope


def candidate(**overrides):
    values = dict(id=str(uuid4()), timestamp_ms=850, source_id="staged01",
                  confidence=0.794, simulated=True,
                  evidence_notes=["sensitive free-form statement MUST NOT be exported"])
    values.update(overrides)
    return FallCandidateEvent(**values)


def test_synthetic_event_marks_its_status_uncertainty_and_privacy():
    original = candidate()
    payload = to_envelope(original, input_provenance="synthetic_pose_trace").to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["event_type"] == "FALL_CANDIDATE"
    assert payload["timestamp_basis"] == "relative_to_source_start"
    assert payload["source_timestamp_ms"] == 850
    assert payload["simulated"] is True
    assert payload["confirmed_fall"] is False
    assert payload["human_review_required"] is True
    assert payload["score_calibrated"] is False
    assert payload["medical_assessment_performed"] is False
    assert payload["detector_score_type"] == "uncalibrated_heuristic"
    assert payload["evidence_refs"] == []
    assert payload["delivery_mode"] == "local_stdout_only"
    assert payload["model_sha256"] is None
    assert "sensitive free-form statement" not in json.dumps(payload)
    assert "landmarks" not in json.dumps(payload)


def test_sha256_and_consented_event_are_labeled():
    payload = to_envelope(
        candidate(simulated=False), input_provenance="consented_staged_video",
        model_sha256="a" * 64
    ).to_dict()
    assert payload["model_sha256"] == "a" * 64
    assert payload["simulated"] is False


@pytest.mark.parametrize("bad_source", ["", "../private", "hello world", "x" * 81,
                                        "ผู้ป่วย01", "patient@example.com"])
def test_reject_invalid_source_id(bad_source):
    with pytest.raises(ValueError, match="source_id"):
        to_envelope(candidate(source_id=bad_source), input_provenance="synthetic_pose_trace")


@pytest.mark.parametrize("bad_score", [-1, 1.01, float("nan"), float("inf"), True])
def test_reject_out_of_range_or_nonfinite_score(bad_score):
    with pytest.raises(ValueError, match="score"):
        to_envelope(candidate(confidence=bad_score), input_provenance="synthetic_pose_trace")


def test_reject_evidence_refs_and_unknown_source_types():
    with pytest.raises(ValueError, match="evidence"):
        to_envelope(candidate(evidence_refs=["file:///private/face.jpg"]),
                    input_provenance="synthetic_pose_trace")
    with pytest.raises(ValueError, match="provenance"):
        to_envelope(candidate(), input_provenance="untrusted_remote")


def test_synthetic_flags_must_match_claimed_provenance():
    with pytest.raises(ValueError, match="simulated"):
        to_envelope(candidate(simulated=False), input_provenance="synthetic_pose_trace")
    with pytest.raises(ValueError, match="provenance"):
        to_envelope(candidate(), input_provenance="consented_staged_video")


def test_reject_invalid_identity_detector_timestamp_or_asset_sha():
    with pytest.raises(ValueError, match="UUID"):
        to_envelope(candidate(id="not-a-uuid"), input_provenance="synthetic_pose_trace")
    with pytest.raises(ValueError, match="detector"):
        to_envelope(candidate(detector="../models"), input_provenance="synthetic_pose_trace")
    with pytest.raises(ValueError, match="timestamp"):
        to_envelope(candidate(timestamp_ms=-1), input_provenance="synthetic_pose_trace")
    with pytest.raises(ValueError, match="model_sha256"):
        to_envelope(candidate(), input_provenance="synthetic_pose_trace",
                    model_sha256="BAD")
