"""Adversarial, synthetic-only, offline Member1->Member2 handoff checks."""
import json
from pathlib import Path
from shutil import copyfile

import pytest

from sentinel_edge.handoff_preflight import main, preflight


@pytest.fixture
def miniature_repo(tmp_path):
    real = Path(__file__).resolve().parents[3]
    paths = [
        "handoff/member1/delivery_manifest.v1.json",
        "handoff/team/team_roster.v1.json",
        "services/edge-vision/docs/edge_candidate_v1.schema.json",
        "services/edge-vision/examples/synthetic/candidate_v1.example.json",
        "services/edge-vision/examples/synthetic/fall.jsonl",
        "services/edge-vision/examples/synthetic/sitting.jsonl",
        "apps/dashboard/package.json",
        "apps/dashboard/src/metaReview.ts",
        "apps/dashboard/tests/metaReview.test.mjs",
        "handoff/member1/FRONTEND_READINESS.md",
        "handoff/member1/ARCHITECTURE.md",
        "handoff/member2/START_HERE.md",
    ]
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(real / name, target)
    return tmp_path


def mutate(root, relative, f):
    path = root / relative
    data = json.loads(path.read_text("utf-8"))
    f(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_actual_checkout_handoff_valid_without_private_weights():
    repo = Path(__file__).resolve().parents[3]
    result = preflight(repo)
    assert result["status"] == "ready_for_developer_handoff_only"
    assert result["active_members"] == ["member1", "member2"]
    assert result["candidate"]["synthetic_fall_events"] == 1
    assert result["candidate"]["synthetic_non_fall_events"] == 0
    assert result["private_model_integrity"] == "not_checked"
    assert result["real_meta_provider_connected"] is False
    assert result["backend_ingestion_ready"] is False
    assert result["network_requests_performed"] is False
    assert "event_id" not in json.dumps(result)
    assert "weights" not in json.dumps(result)


def test_actual_cli_prints_only_bounded_aggregate(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1
    assert json.loads(output)["status"] == "ready_for_developer_handoff_only"
    assert "landmarks" not in output and "event_id" not in output


def test_offline_miniature_contract_baseline_passes(miniature_repo):
    assert preflight(miniature_repo)["private_model_integrity"] == "not_checked"


def test_wrong_roster_member_count_rejected(miniature_repo):
    mutate(miniature_repo, "handoff/team/team_roster.v1.json",
           lambda r: r.update(active_member_count=3))
    with pytest.raises(ValueError, match="two|two-member|Member 1"):
        preflight(miniature_repo)


def test_missing_frontend_handoff_file_rejected(miniature_repo):
    (miniature_repo / "apps/dashboard/src/metaReview.ts").unlink()
    with pytest.raises(ValueError, match="frontend handoff file missing"):
        preflight(miniature_repo)


def test_unchecked_future_frontend_version_rejected(miniature_repo):
    source = miniature_repo / "apps/dashboard/src/metaReview.ts"
    source.write_text("export const VERSION = 'v2';", encoding="utf-8")
    with pytest.raises(ValueError, match="DTO version drifted"):
        preflight(miniature_repo)


def test_fake_model_claims_blocked(miniature_repo):
    mutate(miniature_repo, "handoff/member1/delivery_manifest.v1.json",
           lambda m: m["causal_research_model"].update(auto_alert_authorized=True))
    with pytest.raises(ValueError, match="production gates"):
        preflight(miniature_repo)


def test_manifest_cannot_claim_real_world_accuracy(miniature_repo):
    mutate(miniature_repo, "handoff/member1/delivery_manifest.v1.json",
           lambda m: m["offline_preflight"].update(is_real_world_accuracy_test=True))
    with pytest.raises(ValueError, match="preflight command/claims drifted"):
        preflight(miniature_repo)


def test_backend_not_ready_must_remain_blocked(miniature_repo):
    mutate(miniature_repo, "handoff/member1/delivery_manifest.v1.json",
           lambda m: m["handoff_prerequisites"].update(real_meta_provider_connected=True))
    with pytest.raises(ValueError, match="production gates"):
        preflight(miniature_repo)


def test_synthetic_example_cannot_be_relabelled_real(miniature_repo):
    mutate(miniature_repo, "services/edge-vision/examples/synthetic/candidate_v1.example.json",
           lambda e: e.update(simulated=False))
    with pytest.raises(ValueError, match="unsafe or misleading"):
        preflight(miniature_repo)


@pytest.mark.parametrize(("field", "altered"), [
    ("confirmed_fall", {"type": "boolean"}),
    ("human_review_required", {"type": "boolean"}),
    ("medical_assessment_performed", {"const": True}),
    ("score_calibrated", {"const": True}),
    ("evidence_refs", {"type": "array", "maxItems": 1}),
    ("delivery_mode", {"type": "string"}),
    ("detector_score_type", {"type": "string"}),
    ("detector_score", {"type": "number", "minimum": 0, "maximum": 100}),
    ("event_id", {"type": "string"}),
    ("source_timestamp_ms", {"type": "integer", "minimum": -1}),
    ("timestamp_basis", {"type": "string"}),
    ("source_id", {"type": "string", "pattern": ".*"}),
    ("detector", {"type": "string"}),
    ("model_sha256", {"type": ["null", "string"]}),
    ("input_provenance", {"type": "string"}),
    ("simulated", {"type": "string"}),
])
def test_security_constraints_cannot_be_weakened_under_same_v1_schema(
    miniature_repo, field, altered,
):
    def weaken(schema):
        schema["properties"][field] = altered

    mutate(miniature_repo, "services/edge-vision/docs/edge_candidate_v1.schema.json", weaken)
    with pytest.raises(ValueError, match="schema drift"):
        preflight(miniature_repo)


@pytest.mark.parametrize(("field", "value"), [
    ("$schema", "https://json-schema.org/draft-04/schema#"),
    ("additionalProperties", True),
    ("type", "array"),
    ("required", ["schema_version", "event_type"]),
])
def test_candidate_root_schema_cannot_be_weakened(miniature_repo, field, value):
    mutate(miniature_repo, "services/edge-vision/docs/edge_candidate_v1.schema.json",
           lambda schema: schema.update({field: value}))
    with pytest.raises(ValueError, match="schema drift"):
        preflight(miniature_repo)


def test_duplicate_required_field_does_not_mask_missing_field(miniature_repo):
    def bad_required(schema):
        schema["required"][-1] = schema["required"][0]

    mutate(miniature_repo, "services/edge-vision/docs/edge_candidate_v1.schema.json",
           bad_required)
    with pytest.raises(ValueError, match="schema drift"):
        preflight(miniature_repo)


def test_schema_fields_must_match_producer(miniature_repo):
    mutate(miniature_repo, "services/edge-vision/docs/edge_candidate_v1.schema.json",
           lambda s: s["properties"].update(extra={"type": "string"}))
    with pytest.raises(ValueError, match="schema drift"):
        preflight(miniature_repo)


def test_synthetic_nonfall_cannot_turn_into_candidate(miniature_repo):
    fall = miniature_repo / "services/edge-vision/examples/synthetic/fall.jsonl"
    sitting = miniature_repo / "services/edge-vision/examples/synthetic/sitting.jsonl"
    sitting.write_bytes(fall.read_bytes())
    with pytest.raises(ValueError, match="one synthetic fall and zero sitting"):
        preflight(miniature_repo)


def test_path_traversal_blocked_by_pinned_manifest(miniature_repo):
    mutate(miniature_repo, "handoff/member1/delivery_manifest.v1.json",
           lambda m: m["edge_candidate_contract"].update(schema_path="../../secrets.json"))
    with pytest.raises(ValueError, match="version, path or boundaries"):
        preflight(miniature_repo)


def test_duplicate_keys_fail_closed(miniature_repo):
    source = miniature_repo / "handoff/team/team_roster.v1.json"
    source.write_text('{"schema_version":"x","schema_version":"y"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate keys"):
        preflight(miniature_repo)


def test_optional_private_model_verification_requires_real_files(miniature_repo):
    with pytest.raises(OSError):
        preflight(miniature_repo, verify_models=True)
