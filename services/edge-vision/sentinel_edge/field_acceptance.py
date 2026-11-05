"""Member 1 field acceptance gates: offline, metadata-only, fail closed.

Composes the existing synthetic candidate handoff check, strict dashboard
contracts and optional authorized camera configuration preflight. NO camera
is opened and no Meta/notification call is made. Not a production approval.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.camera_inputs import load_camera_registry, resolve_camera
from sentinel_edge.handoff_preflight import _json_file, preflight
from sentinel_edge.privacy_gate import verify_privacy_approval, PrivacyGateDenied

REPORT_VERSION = "viil.member1.field_acceptance.v1"
DEFAULT_ROOT = Path(__file__).resolve().parents[3]
UI_SCHEMAS = (
    ("handoff/team/integration_overview.v1.schema.json",
     "viil.backend.integration_overview.v1", 16, "cameras"),
    ("handoff/team/caregiver_inbox.v1.schema.json",
     "viil.backend.caregiver_inbox.v1", 30, "advisories"),
)
# No command-line flag can convert missing real-world evidence into a PASS.
LIVE_BLOCKERS = (
    "independent_human_reviewed_fall_recall_not_verified",
    "false_alarms_per_annotated_no_fall_hour_not_verified",
    "live_30min_camera_endurance_not_verified",
    "real_caregiver_accessibility_testing_not_verified",
    "jurisdiction_specific_legal_authorization_not_verified",
    "authenticated_member2_ingestion_not_connected",
    "real_meta_provider_and_evidence_gateway_not_connected",
    "verified_caregiver_delivery_not_connected",
)


def check_ui_contracts(root: Path) -> list[str]:
    """Assert Member 1 and Member 2 metadata interfaces have not drifted."""
    versions = []
    for relative, version, maximum, array_name in UI_SCHEMAS:
        schema = _json_file(root, relative)
        props = schema.get("properties")
        if (schema.get("type") != "object"
                or schema.get("additionalProperties") is not False
                or not isinstance(props, dict)
                or set(props) != set(schema.get("required", []))
                or props.get("schema_version", {}).get("const") != version):
            raise ValueError("Shared UI data contract drift (redacted)")
        arr = props.get(array_name, {})
        if (arr.get("type") != "array" or arr.get("maxItems") != maximum
                or not isinstance(arr.get("items"), dict)
                or arr["items"].get("additionalProperties") is not False):
            raise ValueError("Shared UI bounded array drift (redacted)")
        versions.append(version)
    return versions


def check_camera_config(
    registry_path: Path, approval_path: Path, camera_ids: list[str],
) -> dict:
    """Inspect private local config. Never log selected IDs or RTSP secrets."""
    if not 1 <= len(camera_ids) <= 4 or len(set(camera_ids)) != len(camera_ids):
        raise ValueError("Select 1..4 unique pseudonymous camera IDs")
    cameras = load_camera_registry(registry_path)
    kinds = []
    for camera_id in camera_ids:
        if camera_id not in cameras:
            raise ValueError("Unknown camera selection (redacted)")
        verify_privacy_approval(approval_path, camera_id=camera_id)
        # Validate port/private IP/required environment credential. Discard the
        # URL before formatting output, never print or serialize it.
        kind, _ = resolve_camera(cameras[camera_id])
        kinds.append(kind)
    return {
        "status": "passed_config_only_not_live_capture",
        "number_of_selected_cameras": len(camera_ids),
        "rtsp_count": kinds.count("rtsp"),
        "usb_count": kinds.count("usb"),
        "camera_opened": False,
        "network_requests_performed": False,
    }


def field_acceptance(
    root: Path, *,
    camera_registry: Path | None = None,
    camera_ids: list[str] | None = None,
    privacy_approval: Path | None = None,
    verify_local_models: bool = False,
) -> dict:
    """Return conservative aggregate claims; no personal or secret fields."""
    camera_ids = camera_ids or []
    if (camera_registry is not None or privacy_approval is not None or camera_ids):
        if camera_registry is None or privacy_approval is None or not camera_ids:
            raise ValueError("Camera check needs registry, signed approval and selected IDs")
    handoff = preflight(root, verify_models=verify_local_models)
    schemas = check_ui_contracts(root)
    camera = (
        check_camera_config(camera_registry, privacy_approval, camera_ids)
        if camera_registry is not None and privacy_approval is not None
        else {
            "status": "not_run_no_authorized_device_configuration",
            "camera_opened": False,
            "network_requests_performed": False,
        }
    )
    if handoff.get("status") != "ready_for_developer_handoff_only":
        raise ValueError("Synthetic candidate producer not ready")
    return {
        "schema_version": REPORT_VERSION,
        "scope": "member1_local_offline_acceptance_only",
        "synthetic_fall_candidate_count": handoff["candidate"]["synthetic_fall_events"],
        "synthetic_sitting_candidate_count": handoff["candidate"]["synthetic_non_fall_events"],
        "member2_ui_contract_versions": schemas,
        "private_model_integrity": handoff["private_model_integrity"],
        "camera_configuration": camera,
        "developer_contract_preflight_passed": True,
        "live_camera_validated": False,
        "fall_accuracy_proven": False,
        "real_meta_calls_performed": False,
        "real_notifications_sent": False,
        "legal_compliance_certified": False,
        "production_or_clinical_use_authorized": False,
        "network_requests_performed": False,
        "unresolved_field_blockers": list(LIVE_BLOCKERS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(
        description="Offline Member 1 readiness proof; not live deployment approval")
    parser.add_argument("--camera-registry", type=Path)
    parser.add_argument("--camera-id", action="append", default=[])
    parser.add_argument("--privacy-approval", type=Path)
    parser.add_argument("--verify-local-models", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = field_acceptance(
            DEFAULT_ROOT, camera_registry=args.camera_registry,
            camera_ids=args.camera_id, privacy_approval=args.privacy_approval,
            verify_local_models=args.verify_local_models,
        )
    except (OSError, KeyError, TypeError, ValueError, PrivacyGateDenied):
        parser.error("Member 1 offline field acceptance failed (redacted)")
    print(json.dumps(report, sort_keys=True, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
