"""Member 1 -> Member 2 offline, read-only, no-upload integration preflight.

This only validates VERSIONED handoff consistency using synthetic inputs,
and optionally checks private local model byte hashes. It does not test
accuracy, connect an API, grant consent, or produce caregiver alerts.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
from uuid import UUID

from sentinel_edge.handoff import SCHEMA_VERSION
from sentinel_edge.handoff_cli import export_trace
from sentinel_edge.handoff_verify import DEFAULT_CLASSIFIER

MANIFEST_PATH = "handoff/member1/delivery_manifest.v1.json"
ROSTER_PATH = "handoff/team/team_roster.v1.json"
SCHEMA_PATH = "services/edge-vision/docs/edge_candidate_v1.schema.json"
EXAMPLE_PATH = "services/edge-vision/examples/synthetic/candidate_v1.example.json"
FALL_TRACE = "services/edge-vision/examples/synthetic/fall.jsonl"
NON_FALL_TRACE = "services/edge-vision/examples/synthetic/sitting.jsonl"
FRONTEND_PATHS = (
    "apps/dashboard/src/metaReview.ts",
    "apps/dashboard/tests/metaReview.test.mjs",
    "handoff/member1/FRONTEND_READINESS.md",
    "handoff/member1/ARCHITECTURE.md",
    "handoff/member2/START_HERE.md",
)
FRONTEND_DTO_VERSION = "viil.backend.meta_review.v1"


def _no_duplicates(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("Handoff JSON has duplicate keys")
        output[key] = value
    return output


def _deny_constants(value):
    raise ValueError("Non-finite JSON handoff values forbidden")


def _json_file(root: Path, relative: str) -> dict:
    """Read only pinned canonical paths, with bounded file sizes."""
    path = (root / relative).resolve(strict=True)
    if (not path.is_relative_to(root.resolve(strict=True))
            or not path.is_file() or not 0 < path.stat().st_size <= 100_000):
        raise ValueError("Handoff JSON must be a bounded repository file")
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates,
        parse_constant=_deny_constants,
    )
    if not isinstance(value, dict):
        raise ValueError("Handoff JSON must be an object")
    return value


def check_team(roster: dict, manifest: dict) -> None:
    members = roster.get("members")
    if (roster.get("schema_version") != "viil.team.roster.v1"
            or type(roster.get("active_member_count")) is not int
            or roster["active_member_count"] != 2
            or not isinstance(members, list) or len(members) != 2
            or not all(isinstance(m, dict) for m in members)
            or [m.get("id") for m in members] != ["member1", "member2"]
            or roster.get("retired_member_id") != "member3"
            or roster.get("member3_branch_prefix_active") is not False
            or roster.get("integration_branch") != "member/feature/preprod"):
        raise ValueError("Current roster must contain Member 1 and Member 2 only")
    if (not {"edge_vision", "dashboard", "in_app_notifications"}
            <= set(members[0].get("owns", []))
            or not {"fastapi_backend", "meta_model_api_adapter"}
            <= set(members[1].get("owns", []))):
        raise ValueError("Two-member ownership boundaries disagree")
    ownership = manifest.get("team_ownership", {})
    if (manifest.get("schema_version") != "viil.member1.handoff.v1"
            or manifest.get("consumers") != ["member2_backend_meta"]
            or ownership.get("active_member_count") != 2
            or ownership.get("member3_active") is not False
            or ownership.get("team_roster_path") != ROSTER_PATH):
        raise ValueError("Handoff manifest and two-member roster disagree")


# Immutable v1 boundary: the schema must NOT silently relax safety flags
# while keeping the same field names. Any intentional v2 change requires a
# separately reviewed contract and new version, not a weakened v1 artifact.
_CANDIDATE_V1_PROPERTIES = {
    "schema_version": {"const": SCHEMA_VERSION},
    "event_type": {"const": "FALL_CANDIDATE"},
    "event_id": {"type": "string", "format": "uuid"},
    "source_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"},
    "source_timestamp_ms": {"type": "integer", "minimum": 0},
    "timestamp_basis": {"const": "relative_to_source_start"},
    "detector": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"},
    "model_sha256": {"oneOf": [
        {"type": "null"}, {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    ]},
    "input_provenance": {"enum": [
        "synthetic_pose_trace", "consented_staged_video", "authorized_local_camera",
    ]},
    "detector_score": {"type": "number", "minimum": 0, "maximum": 1},
    "detector_score_type": {"const": "uncalibrated_heuristic"},
    "score_calibrated": {"const": False},
    "confirmed_fall": {"const": False},
    "human_review_required": {"const": True},
    "medical_assessment_performed": {"const": False},
    "simulated": {"type": "boolean"},
    "evidence_refs": {"type": "array", "maxItems": 0},
    "delivery_mode": {"const": "local_stdout_only"},
}


def check_candidate_schema_invariants(schema: dict) -> set[str]:
    """Ensure canonical v1 meaning, not only field names, remains unchanged.

    This is a conservative static freeze of our producer/handoff version,
    not a general-purpose JSON Schema validator. A future Member2 backend
    must independently validate untrusted candidate payloads.
    """
    expected_fields = set(_CANDIDATE_V1_PROPERTIES)
    required = schema.get("required")
    if (schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or type(required) is not list
            or len(required) != len(expected_fields)
            or not all(type(field) is str for field in required)
            or set(required) != expected_fields
            or schema.get("properties") != _CANDIDATE_V1_PROPERTIES):
        raise ValueError("Strict canonical candidate JSON schema drift")
    return expected_fields


def check_candidate(root: Path, manifest: dict) -> dict:
    declared = manifest.get("edge_candidate_contract", {})
    if (declared.get("version") != SCHEMA_VERSION
            or declared.get("schema_path") != SCHEMA_PATH
            or declared.get("synthetic_example_path") != EXAMPLE_PATH
            or declared.get("transport") != "local_stdout_only"
            or declared.get("backend_ingestion_endpoint_exists") is not False
            or declared.get("evidence_refs_authorized") is not False):
        raise ValueError("Edge contract version, path or boundaries drifted")
    schema = _json_file(root, SCHEMA_PATH)
    example = _json_file(root, EXAMPLE_PATH)
    keys = check_candidate_schema_invariants(schema)
    fall = export_trace(root / FALL_TRACE, source_id="synthetic-clip-01")
    no_fall = export_trace(root / NON_FALL_TRACE, source_id="synthetic-clip-01")
    if len(fall) != 1 or no_fall:
        raise ValueError("Expected exactly one synthetic fall and zero sitting candidates")
    emitted = fall[0]
    if set(emitted) != keys or set(example) != keys:
        raise ValueError("Synthetic candidate fields do not match versioned schema")
    for candidate in (emitted, example):
        try:
            canonical = str(UUID(candidate["event_id"]))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Synthetic event UUID invalid") from exc
        if (canonical != candidate["event_id"]
                or candidate["schema_version"] != SCHEMA_VERSION
                or candidate["event_type"] != "FALL_CANDIDATE"
                or candidate["timestamp_basis"] != "relative_to_source_start"
                or type(candidate["source_timestamp_ms"]) is not int
                or candidate["source_timestamp_ms"] < 0
                or candidate["input_provenance"] != "synthetic_pose_trace"
                or candidate["detector_score_type"] != "uncalibrated_heuristic"
                or type(candidate["detector_score"]) not in (int, float)
                or not 0 <= candidate["detector_score"] <= 1
                or candidate["score_calibrated"] is not False
                or candidate["confirmed_fall"] is not False
                or candidate["human_review_required"] is not True
                or candidate["medical_assessment_performed"] is not False
                or candidate["simulated"] is not True
                or candidate["evidence_refs"] != []
                or candidate["model_sha256"] is not None
                or candidate["delivery_mode"] != "local_stdout_only"):
            raise ValueError("Synthetic candidate has unsafe or misleading values")
    # Freeze every field of the canonical example against the ACTUAL producer.
    # event_id is intentionally random per run; never pin it as execution proof.
    emitted_without_id = {key: value for key, value in emitted.items() if key != "event_id"}
    example_without_id = {key: value for key, value in example.items() if key != "event_id"}
    if emitted_without_id != example_without_id:
        raise ValueError("Canonical synthetic example drift from real Python Edge emitter")
    return {"contract": SCHEMA_VERSION, "synthetic_fall_events": 1,
            "synthetic_non_fall_events": 0, "transport": "local_stdout_only"}


def check_frontend(root: Path) -> dict:
    for relative in FRONTEND_PATHS:
        if not (root / relative).is_file():
            raise ValueError("Member 1 frontend handoff file missing: " + relative)
    package = _json_file(root, "apps/dashboard/package.json")
    scripts = package.get("scripts", {})
    if (not isinstance(scripts, dict)
            or "test:contract" not in scripts
            or "test:contract" not in scripts.get("build", "")
            or "tsc" not in scripts.get("build", "")
            or "vite build" not in scripts.get("build", "")):
        raise ValueError("Frontend build must run versioned contract tests")
    source = (root / FRONTEND_PATHS[0]).read_text(encoding="utf-8")
    if FRONTEND_DTO_VERSION not in source:
        raise ValueError("Frontend Meta read-only DTO version drifted")
    return {"meta_display_contract": FRONTEND_DTO_VERSION,
            "mode": "passive_ui_only_not_a_backend_authentication_gate"}


def preflight(root: Path, *, verify_models: bool = False) -> dict:
    """Ensure the exact repo handoff contract is coherent before integration."""
    manifest = _json_file(root, MANIFEST_PATH)
    check_team(_json_file(root, ROSTER_PATH), manifest)
    preflight_info = manifest.get("offline_preflight", {})
    if (preflight_info.get("command") != "python -m sentinel_edge.handoff_preflight"
            or preflight_info.get("optional_private_models_flag") != "--verify-local-models"
            or preflight_info.get("expected_synthetic_fall_events") != 1
            or preflight_info.get("expected_synthetic_non_fall_events") != 0
            or preflight_info.get("expected_network_requests") is not False
            or preflight_info.get("is_real_world_accuracy_test") is not False
            or preflight_info.get("readiness") != "developer_contract_only"
            or preflight_info.get("member2_start_guide") != "handoff/member2/START_HERE.md"):
        raise ValueError("Machine-readable offline preflight command/claims drifted")
    candidate = check_candidate(root, manifest)
    frontend = check_frontend(root)
    model = manifest.get("causal_research_model", {})
    prerequisites = manifest.get("handoff_prerequisites", {})
    security = manifest.get("security", {})
    if (model.get("format") != "viil.edge.causal_1500ms.linear_research.v1"
            or model.get("auto_alert_authorized") is not False
            or model.get("real_trained_weights_in_public_repository") is not False
            or model.get("temporal_context_ms") != 1500
            or model.get("numeric_model_bytes") != 736
            or not isinstance(prerequisites, dict)
            or not prerequisites
            or any(value is not False for value in prerequisites.values())
            or security.get("no_automated_emergency_dispatch") is not True):
        raise ValueError("Private research model or blocked production gates drifted")
    result = {
        "status": "ready_for_developer_handoff_only",
        "active_members": ["member1", "member2"],
        "candidate": candidate,
        "frontend": frontend,
        "private_model_integrity": "not_checked",
        "backend_ingestion_ready": False,
        "real_meta_provider_connected": False,
        "real_alerts_authorized": False,
        "emergency_dispatch_authorized": False,
        "network_requests_performed": False,
    }
    if verify_models:
        # Opt in only when the two private model artifacts are installed.
        from sentinel_edge.handoff_verify import (
            verify_handoff_bundle as verify_private,
        )

        private_result = verify_private(
            classifier=root / "data/private" / DEFAULT_CLASSIFIER,
            pose_task=root / "models/pose_landmarker_lite.task",
        )
        if private_result["validation"] != "passed_offline_sha256_and_model_contract":
            raise ValueError("Private bundle does not pass original hash checks")
        result["private_model_integrity"] = "verified_original_sha256"
        result["local_model_file_count"] = 2
    return result


def main(argv=None) -> int:
    parser = ArgumentParser(description="Offline, read-only Member 1 to 2 handoff preflight")
    parser.add_argument(
        "--verify-local-models", action="store_true",
        help="Also check SHA-256 of two ignored private models if installed",
    )
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[3]
    try:
        result = preflight(repo, verify_models=args.verify_local_models)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error("Member 1 handoff preflight failed: " + str(exc))
    print(json.dumps(result, sort_keys=True, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
