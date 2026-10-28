"""Prevent accidental Member 3 reintroduction into active team contracts."""
import json
from pathlib import Path

from sentinel_edge.handoff_verify import CLASSIFIER_FILE_BYTES


def test_current_team_exactly_two_and_member1_owns_dashboard():
    root = Path(__file__).resolve().parents[3]
    roster = json.loads((root / "handoff/team/team_roster.v1.json").read_text("utf-8"))
    assert roster["active_member_count"] == 2
    members = roster["members"]
    assert [m["id"] for m in members] == ["member1", "member2"]
    assert "dashboard" in members[0]["owns"]
    assert "in_app_notifications" in members[0]["owns"]
    assert "edge_vision" in members[0]["owns"]
    assert "meta_model_api_adapter" in members[1]["owns"]
    assert "fastapi_backend" in members[1]["owns"]
    assert roster["retired_member_id"] == "member3"
    assert roster["member3_branch_prefix_active"] is False
    assert all(not m["branch_prefix"].startswith("member3/") for m in members)
    assert roster["integration_branch"] == "member/feature/preprod"
    assert set(roster["protected_branches"]) == {"main", "preprod"}


def test_research_model_cannot_be_promoted_by_team_reassignment():
    root = Path(__file__).resolve().parents[3]
    roster = json.loads((root / "handoff/team/team_roster.v1.json").read_text("utf-8"))
    manifest = json.loads(
        (root / "handoff/member1/delivery_manifest.v1.json").read_text("utf-8")
    )
    assert manifest["team_ownership"]["active_member_count"] == 2
    assert manifest["team_ownership"]["member3_active"] is False
    assert "dashboard" in manifest["team_ownership"]["member1"]
    assert manifest["consumers"] == ["member2_backend_meta"]
    assert manifest["causal_research_model"]["auto_alert_authorized"] is False
    assert manifest["causal_research_model"]["numeric_model_bytes"] == 736
    assert CLASSIFIER_FILE_BYTES == 2654
    assert roster["policy"]["real_meta_provider_currently_connected"] is False
    assert roster["policy"]["emergency_dispatch_authorized"] is False
    assert roster["policy"]["research_model_authorized_for_real_alerts"] is False
    assert (root / "handoff/team/TEAM_ROLES_AND_META_FIRST.md").is_file()
