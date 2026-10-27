"""Static versioned JSON Schema and example agree with the emitter output."""
import json
from pathlib import Path
from uuid import UUID

from sentinel_edge.handoff import SCHEMA_VERSION
from sentinel_edge.handoff_cli import export_trace


def test_example_and_json_schema_match_real_output():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "docs/edge_candidate_v1.schema.json").read_text("utf-8"))
    example = json.loads((root / "examples/synthetic/candidate_v1.example.json").read_text("utf-8"))
    generated = export_trace(
        root / "examples/synthetic/fall.jsonl", source_id="synthetic-clip-01"
    )[0]
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert set(generated) == set(example) == set(schema["required"])
    assert str(UUID(generated["event_id"])) == generated["event_id"]
    assert example["confirmed_fall"] is False
    assert example["score_calibrated"] is False
    assert example["human_review_required"] is True
    assert example["model_sha256"] is None
    assert generated["event_type"] == "FALL_CANDIDATE"


def test_no_video_pixels_person_info_or_evidence_in_example():
    root = Path(__file__).resolve().parents[1]
    example = json.loads(
        (root / "examples/synthetic/candidate_v1.example.json").read_text("utf-8")
    )
    for forbidden in ("frame", "landmarks", "person_name", "raw_video", "severity",
                      "image", "medical_diagnosis", "api_key"):
        assert forbidden not in example
    assert example["evidence_refs"] == []
