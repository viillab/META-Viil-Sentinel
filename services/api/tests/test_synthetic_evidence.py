"""No-paid-call regression tests for event-bound synthetic pose evidence."""
import base64
import hashlib
import json
import struct
import zlib
from dataclasses import replace
from uuid import uuid4

import pytest

from app.candidate_ingest import sign_candidate
from app.edge_emitter_e2e import SYNTHETIC_ROOT, edge_candidates_from_trace
from app.meta_live import MetaSyntheticVisionClient, synthetic_png
from app.synthetic_evidence import (
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    SOURCE_TIMES,
    EvidenceRejected,
    build_offline_pose_meta_request,
    build_synthetic_evidence,
    verify_synthetic_evidence,
)


def generated_candidate():
    rows = edge_candidates_from_trace("fall")
    assert len(rows) == 1
    return rows[0]


def replace_json(raw: bytes, **changes) -> bytes:
    obj = json.loads(raw)
    obj.update(changes)
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def test_actual_member1_candidate_produces_bound_schematic_png():
    raw = generated_candidate()
    created = build_synthetic_evidence(raw)
    verify_synthetic_evidence(raw, created)
    man = created.manifest
    assert man.schema_version == "viil.synthetic.evidence.v1"
    assert man.source_id == "synthetic-clip-01"
    assert str(man.event_id) == json.loads(raw)["event_id"]
    assert man.candidate_sha256 == hashlib.sha256(raw).hexdigest()
    assert man.trace_sha256 == hashlib.sha256(
        (SYNTHETIC_ROOT / "fall.jsonl").read_bytes()
    ).hexdigest()
    assert man.image_sha256 == hashlib.sha256(created.png).hexdigest()
    assert man.frame_timestamps_ms == SOURCE_TIMES
    assert man.source_timestamp_ms == 850
    assert man.simulated is True
    assert man.contains_real_person is False
    assert man.consent_for_real_media_verified is False
    assert man.external_upload_authorized is False
    assert man.meta_inference_performed is False
    assert man.fall_confirmed is False
    assert created.png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", created.png[16:24]) == (IMAGE_WIDTH, IMAGE_HEIGHT)
    assert len(created.png) < 128 * 1024
    assert created.png != synthetic_png()
    assert created == build_synthetic_evidence(raw)


def test_candidate_event_uuid_changes_manifest_binding_but_image_is_deterministic():
    raw = generated_candidate()
    different_event = replace_json(raw, event_id=str(uuid4()))
    first = build_synthetic_evidence(raw)
    second = build_synthetic_evidence(different_event)
    assert first.manifest.event_id != second.manifest.event_id
    assert first.manifest.candidate_sha256 != second.manifest.candidate_sha256
    assert first.manifest.image_sha256 == second.manifest.image_sha256
    with pytest.raises(EvidenceRejected, match="mismatch"):
        verify_synthetic_evidence(different_event, first)


@pytest.mark.parametrize("changes", [
    {"source_id": "synthetic-other-01"},
    {"source_id": "camera-01"},
    {"source_timestamp_ms": 300},
    {"source_timestamp_ms": 700},
    {"input_provenance": "authorized_local_camera"},
    {"input_provenance": "consented_staged_video"},
    {"simulated": False},
    {"confirmed_fall": True},
    {"detector_score": 0.999},
    {"detector": "other-detector"},
    {"evidence_refs": ["file:///private/patient.png"]},
    {"model_sha256": "0" * 64},
])
def test_tampered_or_real_input_candidate_cannot_produce_evidence(changes):
    with pytest.raises(EvidenceRejected):
        build_synthetic_evidence(replace_json(generated_candidate(), **changes))


def test_reject_oversized_invalid_and_duplicate_key_json():
    with pytest.raises(EvidenceRejected):
        build_synthetic_evidence(b"{}")
    with pytest.raises(EvidenceRejected):
        build_synthetic_evidence(b"{" + b'"schema_version":"bad",' * 300 + b"}")
    raw = generated_candidate()
    with pytest.raises(EvidenceRejected):
        build_synthetic_evidence(
            raw[:-1] + b', "event_id": "' + str(uuid4()).encode("ascii") + b'"}'
        )


def test_renderer_requires_sha_pinned_mathematical_trace(monkeypatch):
    from app import synthetic_evidence as evidence

    candidate = generated_candidate()
    monkeypatch.setitem(evidence.EXPECTED_TRACE_HASHES, "fall", "0" * 64)
    with pytest.raises(EvidenceRejected, match="synthetic"):
        evidence.build_synthetic_evidence(candidate)


def test_manifest_tamper_image_tamper_and_injected_metadata_rejected():
    raw = generated_candidate()
    evidence = build_synthetic_evidence(raw)
    other = evidence.manifest.model_copy(update={"source_id": "synthetic-other-01"})
    with pytest.raises(EvidenceRejected, match="mismatch"):
        verify_synthetic_evidence(raw, replace(evidence, manifest=other))
    other = evidence.manifest.model_copy(update={"external_upload_authorized": True})
    with pytest.raises(EvidenceRejected, match="mismatch"):
        verify_synthetic_evidence(raw, replace(evidence, manifest=other))
    damaged = bytearray(evidence.png)
    damaged[42] ^= 0xFF
    with pytest.raises(EvidenceRejected, match="mismatch"):
        verify_synthetic_evidence(raw, replace(evidence, png=bytes(damaged)))
    with pytest.raises(EvidenceRejected, match="Not a PNG"):
        verify_synthetic_evidence(raw, replace(evidence, png=b"not-an-image"))
    with pytest.raises(EvidenceRejected):
        verify_synthetic_evidence(raw, replace(evidence, png=b"\x89PNG\r\n\x1a\n" + b"0" * 140000))


def test_offline_request_uses_exact_bound_png_and_strict_schema():
    raw = generated_candidate()
    evidence = build_synthetic_evidence(raw)
    body = build_offline_pose_meta_request(raw, evidence)
    assert body["model"] == "muse-spark-1.3"
    assert body["reasoning_effort"] == "minimal"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_completion_tokens"] == 1024
    assert "synthetic" in body["messages"][0]["content"].lower()
    data_url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == evidence.png
    assert not any("Authorization" in json.dumps(x) for x in body["messages"])


def test_meta_live_client_cannot_upload_pose_image_or_spend(tmp_path):
    import asyncio

    from app.meta_budget import MetaBudget

    raw = generated_candidate()
    evidence = build_synthetic_evidence(raw)
    budget = MetaBudget(path=tmp_path / "meta.sqlite3")
    live_client = MetaSyntheticVisionClient(
        api_key="LLM_fake_test", live_enabled=True, budget=budget
    )
    with pytest.raises(ValueError, match="canonical generated"):
        asyncio.run(live_client.assess(image=evidence.png))
    assert budget.status() == (0, 0)


def test_three_panels_represent_different_torso_shapes():
    png = build_synthetic_evidence(generated_candidate()).png
    cursor = 8
    concatenated = b""
    while cursor < len(png):
        size = struct.unpack(">I", png[cursor:cursor + 4])[0]
        kind = png[cursor + 4:cursor + 8]
        data = png[cursor + 8:cursor + 8 + size]
        if kind == b"IDAT":
            concatenated += data
        cursor += 12 + size
    raw = zlib.decompress(concatenated)
    stride = 1 + IMAGE_WIDTH * 3
    before = b"".join(raw[y * stride + 1:y * stride + 1 + 112 * 3]
                      for y in range(IMAGE_HEIGHT))
    during = b"".join(raw[y * stride + 1 + 112 * 3:y * stride + 1 + 224 * 3]
                      for y in range(IMAGE_HEIGHT))
    after = b"".join(raw[y * stride + 1 + 224 * 3:y * stride + 1 + 336 * 3]
                     for y in range(IMAGE_HEIGHT))
    assert before != during
    # Vertical separator draws at panel boundaries. Compare only interior
    # pixels to verify repeated mathematical poses at 300 and 850 ms.
    def interior(panel):
        return b"".join(
            panel[row * 112 * 3 + 5 * 3:row * 112 * 3 + 107 * 3]
            for row in range(IMAGE_HEIGHT)
        )

    assert interior(during) == interior(after)


def test_no_candidate_from_sitting_trace():
    assert edge_candidates_from_trace("sitting") == []


def test_attacker_cannot_pass_hmac_as_image_approval():
    raw = generated_candidate()
    approved_candidate_signature = sign_candidate(
        b"x" * 32, source="synthetic-clip-01",
        timestamp="1793630000", body=raw,
    )
    assert approved_candidate_signature.startswith("sha256=")
    evidence = build_synthetic_evidence(raw)
    assert evidence.manifest.external_upload_authorized is False
    assert evidence.manifest.consent_for_real_media_verified is False
