"""Offline-only Member2 integration snapshot tests; no network or camera."""
import json
from uuid import uuid4

import pytest

from sentinel_edge.contracts import FallCandidateEvent
from sentinel_edge.handoff import to_envelope
from sentinel_edge.member2_status import (
    collect_member2_status, inspect_backend_routes, static_fastapi_routes,
)

BASELINE = '''
from fastapi import FastAPI
def create_app():
    app = FastAPI()
    @app.get("/health")
    def health():
        pass
    @app.post("/api/v1/incidents/demo")
    def create_demo():
        pass
    return app
'''
FUTURE = BASELINE.replace(
    "    return app",
    """    @app.post("/api/v1/edge/candidates")
    def ingest_candidate():
        pass
    return app""",
)


def fake_git(*, main=BASELINE, refs="origin/member2/feature/initial", sha="a" * 40):
    calls = []

    def read(*args):
        calls.append(args)
        if args[0] == "for-each-ref":
            return refs
        if args[0] == "rev-parse":
            return sha
        if args[0] == "log":
            return "2026-10-28T17:50:16+07:00"
        if args[0] == "show":
            return main
        raise AssertionError("Unexpected git action")
    return read, calls


def test_baseline_backend_is_demo_only_not_authenticated_intake():
    review = inspect_backend_routes(BASELINE)
    assert review["demo_incident_post_detected"] is True
    assert review["candidate_ingestion_post_detected"] is False
    assert review["authenticated_ingestion_verified"] is False
    assert review["idempotent_ingestion_verified"] is False
    assert review["real_meta_provider_verified"] is False
    assert review["real_live_integration_verified"] is False
    assert review["literal_routes_seen"] == 2


def test_future_candidate_named_route_is_still_not_verified():
    review = inspect_backend_routes(FUTURE)
    assert review["candidate_ingestion_post_detected"] is True
    assert review["authenticated_ingestion_verified"] is False
    assert review["idempotent_ingestion_verified"] is False
    assert review["real_meta_provider_verified"] is False
    assert review["real_live_integration_verified"] is False
    assert review["candidate_ingestion_status"].endswith("require_security_review")


def test_dynamic_router_does_not_forge_static_verification():
    source = '''
from fastapi import APIRouter
router = APIRouter()
@router.post("/api/v1/edge/candidates")
def received():
    pass
'''
    assert static_fastapi_routes(source) == ()


def test_report_latest_member2_branch_sha_date_from_local_refs_only():
    git, calls = fake_git(
        refs="origin/member2/feature/initial\norigin/member2/feature/meta-intelligence",
    )
    report = collect_member2_status(git)
    assert report["member2_branch_found"] is True
    assert report["branch"] == "origin/member2/feature/initial"
    assert report["sha"] == "a" * 40
    assert report["commit_date"] == "2026-10-28T17:50:16+07:00"
    assert report["source"] == "local_git_refs_only_not_live_remote"
    assert report["backend_route_review"]["candidate_ingestion_post_detected"] is False
    assert report["manual_review_required"] is True
    assert [c[0] for c in calls] == [
        "for-each-ref", "rev-parse", "log", "show",
    ]


def test_no_member2_ref_fails_closed_without_git_show():
    git, calls = fake_git(refs="")
    result = collect_member2_status(git)
    assert result["member2_branch_found"] is False
    assert result["backend_route_review"] is None
    assert len(calls) == 1


def test_ref_injection_ignored_no_arbitrary_git_exec():
    git, calls = fake_git(refs="origin/member2/feature/a;rm -rf /\norigin/member2/feature/initial")
    report = collect_member2_status(git)
    assert report["branch"] == "origin/member2/feature/initial"
    assert len(calls) == 4


def test_malformed_rev_or_commit_date_redacted():
    git, _ = fake_git(sha="secret-rtsp")
    with pytest.raises(ValueError, match="Invalid local git revision"):
        collect_member2_status(git)


def test_candidate_contract_is_unconfirmed_local_stdout_not_demo_incident():
    event = FallCandidateEvent(
        id=str(uuid4()), source_id="staged-test", timestamp_ms=810,
        confidence=0.8, simulated=True,
    )
    payload = to_envelope(event, input_provenance="synthetic_pose_trace").to_dict()
    assert payload["schema_version"] == "viil.edge.candidate.v1"
    assert payload["event_type"] == "FALL_CANDIDATE"
    assert payload["simulated"] is True
    assert payload["confirmed_fall"] is False
    assert payload["human_review_required"] is True
    assert payload["delivery_mode"] == "local_stdout_only"
    assert payload["timestamp_basis"] == "relative_to_source_start"
    assert "rtsp://" not in json.dumps(payload)
