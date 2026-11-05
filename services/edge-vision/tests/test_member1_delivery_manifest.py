"""Two-member handoff manifest remains pinned to the tested Edge source."""
import json
from pathlib import Path

from sentinel_edge.causal_1500ms_artifact import (
    ARTIFACT_FORMAT, CONTEXT_MS, HOP_MS, SAMPLE_SLOTS,
)
from sentinel_edge.handoff import SCHEMA_VERSION


def test_cross_team_manifest_points_to_canonical_versioned_contract():
    repo = Path(__file__).resolve().parents[3]
    root = repo / "handoff" / "member1"
    info = json.loads((root / "delivery_manifest.v1.json").read_text("utf8"))
    assert info["schema_version"] == "viil.member1.handoff.v1"
    candidate = info["edge_candidate_contract"]
    assert candidate["version"] == SCHEMA_VERSION
    schema = json.loads((repo / candidate["schema_path"]).read_text("utf8"))
    example = json.loads(
        (repo / candidate["synthetic_example_path"]).read_text("utf8")
    )
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert set(example) == set(schema["properties"]) == set(schema["required"])
    assert schema["additionalProperties"] is False
    assert example["simulated"] is True
    assert example["confirmed_fall"] is False
    assert example["human_review_required"] is True
    assert example["delivery_mode"] == "local_stdout_only"
    assert candidate["backend_ingestion_endpoint_exists"] is False
    assert candidate["evidence_refs_authorized"] is False


def test_model_manifest_cannot_implicitly_promote_eight_second_model():
    repo = Path(__file__).resolve().parents[3]
    info = json.loads((repo / "handoff/member1/delivery_manifest.v1.json").read_text())
    model = info["causal_research_model"]
    assert model["format"] == ARTIFACT_FORMAT
    assert model["temporal_context_ms"] == CONTEXT_MS == 1500
    assert model["sample_slots"] == SAMPLE_SLOTS == 30
    assert model["shadow_hop_ms"] == HOP_MS == 250
    assert model["sample_features_per_slot"] == 6
    assert model["descriptor_dimensions"] == 30
    assert model["numeric_model_bytes"] == 736
    assert model["num_float64_model_parameters"] == 92
    assert model["real_trained_weights_in_public_repository"] is False
    assert model["artifact_private_only"] is True
    assert model["auto_alert_authorized"] is False
    assert model["human_event_onset_review_completed"] is False
    assert model["accuracy_on_independent_real_world_actors_proven"] is False


def test_all_handoff_docs_exist_and_no_private_data_in_metadata():
    repo = Path(__file__).resolve().parents[3]
    root = repo / "handoff/member1"
    for name in ("README.md", "ARCHITECTURE.md", "PERFORMANCE.md",
                 "delivery_manifest.v1.json"):
        assert (root / name).is_file()
    manifest = json.loads((root / "delivery_manifest.v1.json").read_text())
    assert manifest["security"]["never_commit_private_weights"]
    assert manifest["security"]["never_commit_video_or_derived_pose"]
    assert manifest["security"]["no_automated_emergency_dispatch"]
    assert not any("data/private/" in name for name in manifest.keys())
    assert all(value is False for value in
               manifest["handoff_prerequisites"].values())
