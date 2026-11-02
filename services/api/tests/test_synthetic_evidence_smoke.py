"""Verified local HTTP smoke must not spend Meta calls or write private media."""
import json

from app.synthetic_evidence_smoke import run_synthetic_event_bound_smoke


def test_full_offline_event_bound_http_and_mock_contract(monkeypatch):
    monkeypatch.setenv("META_MODEL_API_KEY", "fake-meta-key-that-must-never-be-used")
    monkeypatch.setenv("HIKVISION_PASSWORD", "never-use-real-camera-key")
    report = run_synthetic_event_bound_smoke()
    assert report["status"] == "SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS"
    assert report["edge_candidate_accepted_over_real_local_http"] is True
    assert report["candidate_event_id_matches_manifest"] is True
    assert report["image_dimensions"] == [336, 112]
    assert report["rendered_source_timestamps_ms"] == [0, 300, 850]
    assert report["evidence_origin"] == "pinned_mathematical_pose_trace"
    assert all(len(report[field]) == 64 for field in (
        "candidate_sha256", "trace_sha256", "image_sha256"
    ))
    assert report["offline_meta_request_prepared"] is True
    assert report["registry_same_signed_event_verified"] is True
    assert report["registry_read_via_local_http_verified"] is True
    assert report["registry_deduplicated"] is True
    assert report["registry_real_media_consent_verified"] is False
    assert report["registry_image_bytes_stored"] is False
    assert report["audit_read_via_local_http_verified"] is True
    assert report["audit_chain_verified"] is True
    assert report["independent_hmac_audit_anchor_verified"] is True
    assert report["read_without_anchor_rejected"] is True
    assert report["tampered_independent_anchor_rejected_over_http"] is True
    assert report["audit_idempotent_one_registration_entry"] is True
    assert report["consent_gate_real_media_upload_blocked"] is True
    assert report["audit_never_permits_meta_calls"] is True
    assert report["meta_copilot_offline_preview_verified_over_http"] is True
    assert report["meta_copilot_workplan_tasks"] == 3
    assert report["meta_copilot_no_anchor_rejected"] is True
    assert report["meta_copilot_corrupt_anchor_rejected"] is True
    assert report["meta_copilot_model_request_prepared_not_sent"] is True
    assert report["meta_copilot_mock_provider_contract_verified"] is True
    assert report["meta_copilot_mock_provider_rejected_after_anchor_corruption"] is True
    assert report["meta_copilot_mock_provider_calls"] == 1
    assert report["shadow_ledger_one_mock_call_per_event"] is True
    assert report["shadow_ledger_duplicate_cached"] is True
    assert report["shadow_ledger_readiness_denies_live_meta"] is True
    assert report["shadow_readiness_verified_over_local_http"] is True
    assert report["shadow_readiness_rejects_corrupt_anchor_over_http"] is True
    assert report["shadow_ledger_cache_invalidated_by_bad_anchor"] is True
    assert report["shadow_budget_ledger_unmodified"] is True
    assert report["meta_response_was_mocked"] is True
    assert report["real_meta_api_called"] is False
    assert report["meta_budget_modified"] is False
    assert report["inbox_remains_unconfirmed_and_synthetic"] is True
    assert report["real_camera_media_processed"] is False
    assert report["real_person_media_sent"] is False
    assert report["images_persisted"] is False
    assert report["temporary_local_http_stopped"] is True
    assert report["temporary_sqlite_deleted"] is True
    assert "fake-meta-key-that-must-never-be-used" not in json.dumps(report)
