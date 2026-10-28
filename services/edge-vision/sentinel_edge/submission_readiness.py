"""Read-only Member 1 hackathon artifact acceptance check.

Never performs capture, Meta inference, third-party calls, file writes,
notification dispatch, uploads or model training. This verifies source
contracts and the synthetic handoff, NOT real-world fall performance.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.handoff_preflight import preflight

APP_FILES = (
    "apps/dashboard/src/JudgeDemoView.tsx",
    "apps/dashboard/src/judgeDemo.ts",
    "apps/dashboard/src/EdgeTestLab.tsx",
    "apps/dashboard/src/CaregiverInboxView.tsx",
    "apps/dashboard/src/IntegrationCenter.tsx",
    "apps/dashboard/src/judge.css",
    "apps/dashboard/src/caregiver.css",
    "apps/dashboard/tests/judgeDemo.test.mjs",
    "apps/dashboard/tests/caregiverInbox.test.mjs",
    "docs/integrations/MEMBER1_ACCESSIBLE_CAREGIVER_INBOX.md",
    "docs/submission/MEMBER1_JUDGE_DEMO_RUNBOOK.md",
)
SHARED_SCHEMAS = {
    "handoff/team/caregiver_inbox.v1.schema.json": "viil.backend.caregiver_inbox.v1",
    "handoff/team/integration_overview.v1.schema.json":
        "viil.backend.integration_overview.v1",
}
BLOCKERS = (
    "independent_human_labeled_fall_and_adl_metrics_not_verified",
    "30_minute_real_camera_soak_and_reconnect_not_verified",
    "production_backend_authentication_and_tenant_rbac_not_verified",
    "real_authorized_meta_multimodal_inference_not_verified",
    "real_caregiver_delivery_receipt_and_accessibility_testing_not_verified",
    "jurisdictional_legal_privacy_and_security_signoff_not_verified",
)


def _json_object(path: Path) -> dict:
    if not path.is_file() or not 0 < path.stat().st_size <= 100_000:
        raise ValueError("Missing or oversized required handoff JSON")
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate handoff JSON key")
            value[key] = item
        return value
    def reject_nonfinite(_):
        raise ValueError("Nonfinite handoff JSON value")
    parsed = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates, parse_constant=reject_nonfinite,
    )
    if type(parsed) is not dict:
        raise ValueError("Expected a JSON object")
    return parsed


def verify_member1_submission(root: Path) -> dict:
    """Fail on missing/drifted code contracts; never mark external gates green."""
    root = root.resolve(strict=True)
    handoff = preflight(root)
    for relative in APP_FILES:
        candidate = (root / relative).resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError("Member 1 demo asset missing")
    for relative, version in SHARED_SCHEMAS.items():
        schema = _json_object(root / relative)
        props = schema.get("properties")
        if (schema.get("type") != "object"
                or schema.get("additionalProperties") is not False
                or not isinstance(props, dict)
                or set(schema.get("required", [])) != set(props)
                or props.get("schema_version", {}).get("const") != version):
            raise ValueError("Member 2 JSON contract drifted")
        if relative.endswith("caregiver_inbox.v1.schema.json"):
            advisories = props.get("advisories", {})
            items = advisories.get("items", {})
            if (advisories.get("maxItems") != 30
                    or items.get("additionalProperties") is not False
                    or not {"fall_confirmed", "emergency_dispatch_authorized",
                            "human_follow_up_required"} <= set(items.get("required", []))
                    or items.get("properties", {}).get(
                        "fall_confirmed", {}).get("const") is not False
                    or items.get("properties", {}).get(
                        "emergency_dispatch_authorized", {}).get("const") is not False):
                raise ValueError("Caregiver safety contract drifted")
        else:
            cameras = props.get("cameras", {})
            if (cameras.get("maxItems") != 16
                    or cameras.get("items", {}).get("additionalProperties") is not False):
                raise ValueError("Camera metadata contract drifted")
    if handoff.get("network_requests_performed") is not False:
        raise ValueError("Offline handoff unexpectedly used network")
    if handoff.get("candidate", {}).get("synthetic_fall_events") != 1:
        raise ValueError("Synthetic Edge candidate parity failed")
    if handoff.get("candidate", {}).get("synthetic_non_fall_events") != 0:
        raise ValueError("Synthetic nonfall fixture changed")
    return {
        "status": "member1_offline_artifact_gate_passed",
        "scope": "demo_source_and_contracts_only",
        "synthetic_edge_candidate_count": 1,
        "synthetic_sitting_candidate_count": 0,
        "offline_demo_scenarios": 5,
        "shared_backend_schemas_verified": len(SHARED_SCHEMAS),
        "external_network_calls": 0,
        "actual_meta_calls": 0,
        "actual_caregiver_alerts": 0,
        "real_fall_accuracy_verified": False,
        "production_ready": False,
        "blocked_on_evidence_or_member2": list(BLOCKERS),
        "note": "Run npm build, backend/edge tests and GitHub CI separately.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(
        description="Member 1 offline hackathon release artifacts, no external actions",
    )
    parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[3]
    try:
        report = verify_member1_submission(repo)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error("Member 1 offline artifact acceptance failed: " + str(exc))
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
