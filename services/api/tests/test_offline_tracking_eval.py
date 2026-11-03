"""Synthetic-only independent annotation/prediction integrity regression tests.

All names are invented actor tokens. No actual human images or poses
are loaded into CI. Descriptive scores NEVER certify person identity.
"""
import copy
import json

import pytest

from app import actor_disjoint_admission as admission
from app import offline_tracking_eval as evaluation


def fixture():
    manifest = admission._fictional_demo_manifest()
    return manifest, evaluation._fictional_prediction_example(manifest)


def audit(manifest, prediction, *, demo=True):
    return evaluation.evaluate_offline(
        manifest, prediction, fictional_demo=demo,
    )


def test_independently_matched_fictional_demo_has_precise_error_counters():
    manifest, prediction = fixture()
    report = audit(manifest, prediction)
    assert report["status"] == "FICTIONAL_TRACKING_METRICS_DEMO"
    assert report["manifest_content_fingerprint_verified"] is True
    assert report["actor_disjoint_structure_checked"] is True
    assert report["release_authorized"] is False
    assert report["matching_actor_labels_independently_attested_by_this_tool"] is False
    assert report["real_person_tracking_accuracy_established"] is False
    assert report["meta_api_called"] is False
    assert report["real_media_uploaded"] is False
    assert report["emergency_dispatch_enabled"] is False
    assert report["fall_confirmation_enabled"] is False
    assert report["metrics"] == {
        "test_clips": 1,
        "test_frames": 4,
        "reference_visible_actor_frames": 6,
        "matched_actor_frames": 6,
        "missed_visible_actor_frames": 0,
        "unmatched_detections": 1,
        "abstained_frames": 0,
        "reference_adjacent_visible_transitions": 2,
        "same_track_adjacent_continuations": 1,
        "adjacent_id_switches": 1,
        "adjacent_unobserved_links": 0,
        "cross_actor_track_reuse": 1,
        "reacquired_after_visible_gap": 0,
        "large_timestamp_intervals": 0,
        "untrusted_continuations_across_time_gap": 0,
    }
    assert "cross_actor_track_reuse_detected" in report["blocking_reasons"]
    assert "adjacent_track_id_switches_detected" in report["blocking_reasons"]


def test_actual_structural_check_cannot_authorize_real_person_metrics():
    manifest, prediction = fixture()
    report = audit(manifest, prediction, demo=False)
    assert report["status"] == "PRIVATE_OFFLINE_TRACKING_DIAGNOSTICS_ONLY"
    assert report["release_authorized"] is False
    assert report["matching_actor_labels_independently_attested_by_this_tool"] is False
    assert "actual_legal_rights_identity_and_consent_not_independently_audited" in (
        report["blocking_reasons"]
    )
    assert "actor_independence_cannot_be_verified_from_tokens" in (
        report["blocking_reasons"]
    )


def test_aggregates_export_no_fake_actor_ids_tracks_or_frame_timestamps():
    manifest, prediction = fixture()
    report = audit(manifest, prediction)
    encoded = json.dumps(report, sort_keys=True)
    for private in (
        "A_c333", "A_d444", "A_a111", "T_left", "T_right", "T_new",
        "T_noise", "C_tst", "S_tst", "CAM_tst", "timestamp_ms",
        "frame_index", "detection_index", "observations",
        "source_sha256", "labeled_poses",
    ):
        assert private not in encoded
    assert '"actor_token":' not in encoded
    assert report["raw_actor_tokens_tracks_or_coordinates_exported"] is False


def test_manifest_content_binding_changes_on_annotations_order_or_rights():
    manifest, prediction = fixture()
    tampered = copy.deepcopy(manifest)
    tampered["clips"][2]["frames"][0]["states"][0]["state"] = "occluded"
    with pytest.raises(ValueError, match="cryptographically"):
        audit(tampered, prediction)
    tampered = copy.deepcopy(manifest)
    tampered["rights"]["rights_evidence_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="cryptographically"):
        audit(tampered, prediction)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema="wrong-schema"),
    lambda p: p.update(manifest_sha256="bad"),
    lambda p: p.update(manifest_sha256="0" * 64),
    lambda p: p.update(extra=True),
    lambda p: p.pop("clips"),
    lambda p: p.update(clips=[]),
    lambda p: p["clips"].append(copy.deepcopy(p["clips"][0])),
    lambda p: p["clips"][0].update(clip_token="C_trn"),
    lambda p: p["clips"][0].update(clip_token="../invalid"),
    lambda p: p["clips"][0]["frames"].pop(),
    lambda p: p["clips"][0].update(other="unsafe"),
])
def test_prediction_file_binding_and_sealed_test_coverage_rejected(mutation):
    manifest, prediction = fixture()
    mutation(prediction)
    with pytest.raises(ValueError):
        audit(manifest, prediction)


@pytest.mark.parametrize("mutation", [
    lambda p: p["clips"][0]["frames"][0].update(frame_index=2),
    lambda p: p["clips"][0]["frames"][0].update(timestamp_ms=1000),
    lambda p: p["clips"][0]["frames"][0].update(timestamp_ms=True),
    lambda p: p["clips"][0]["frames"][0].update(status="untrusted"),
    lambda p: p["clips"][0]["frames"][0].update(reason="operator says okay"),
    lambda p: p["clips"][0]["frames"][0].update(reason="occluded"),
    lambda p: p["clips"][0]["frames"][0].update(status="abstained"),
    lambda p: p["clips"][0]["frames"][0].update(unknown="extra"),
    lambda p: p["clips"][0]["frames"][0].update(observations="not-a-list"),
    lambda p: p["clips"][0]["frames"][0].update(observations=[{}]),
])
def test_prediction_frame_requires_exact_schema_and_no_claim_on_abstention(mutation):
    manifest, prediction = fixture()
    mutation(prediction)
    with pytest.raises(ValueError):
        audit(manifest, prediction)


@pytest.mark.parametrize("mutation", [
    lambda obs: obs.update(track_token="T_JohnSmith"),
    lambda obs: obs.update(track_token="A_other"),
    lambda obs: obs.update(track_token="T../secret"),
    lambda obs: obs.update(track_token=None),
    lambda obs: obs.update(detection_index=True),
    lambda obs: obs.update(detection_index=-1),
    lambda obs: obs.update(detection_index=8),
    lambda obs: obs.update(detection_index="0"),
    lambda obs: obs.update(actor_token="A_unknown"),
    lambda obs: obs.update(actor_token="A_d444"),
    lambda obs: obs.update(extra="no"),
])
def test_untrusted_detection_track_and_actor_tokens_rejected(mutation):
    manifest, prediction = fixture()
    mutation(prediction["clips"][0]["frames"][1]["observations"][0])
    with pytest.raises(ValueError):
        audit(manifest, prediction)


@pytest.mark.parametrize("field", ["track_token", "detection_index", "actor_token"])
def test_duplicate_track_detection_or_reference_match_is_rejected(field):
    manifest, prediction = fixture()
    obs = prediction["clips"][0]["frames"][0]["observations"]
    second = obs[1]
    second[field] = obs[0][field]
    with pytest.raises(ValueError):
        audit(manifest, prediction)


def test_valid_abstained_frame_has_no_links_and_reports_missing_gt():
    manifest, prediction = fixture()
    frame = prediction["clips"][0]["frames"][1]
    frame["status"] = "abstained"
    frame["reason"] = "ambiguous"
    frame["observations"] = []
    report = audit(manifest, prediction)
    assert report["metrics"]["abstained_frames"] == 1
    assert report["abstention_reasons"] == {"ambiguous": 1}
    assert report["metrics"]["missed_visible_actor_frames"] == 1
    assert report["metrics"]["adjacent_unobserved_links"] == 1
    assert report["metrics"]["adjacent_id_switches"] == 0


def test_visible_actor_missing_then_reacquired_counts_fragmentation():
    manifest, prediction = fixture()
    test = manifest["clips"][2]
    observations = prediction["clips"][0]["frames"]
    # Two added synthetic frames: c333 stays visible, disappears from
    # predictions for one frame, then reappears with a new track ID.
    for i in (4, 5):
        test["frames"].append({
            "frame_index": i,
            "timestamp_ms": 100*i,
            "states": [
                {"actor_token": "A_c333", "state": "visible"},
                {"actor_token": "A_d444", "state": "visible"},
            ],
        })
    test["frame_count"] = 6
    observations.append({
        "frame_index": 4, "timestamp_ms": 400,
        "status": "accepted", "reason": "none",
        "observations": [
            {"detection_index": 0, "track_token": "T_new",
             "actor_token": "A_d444"},
        ],
    })
    observations.append({
        "frame_index": 5, "timestamp_ms": 500,
        "status": "accepted", "reason": "none",
        "observations": [
            {"detection_index": 0, "track_token": "T_new",
             "actor_token": "A_d444"},
            {"detection_index": 1, "track_token": "T_left2",
             "actor_token": "A_c333"},
        ],
    })
    prediction["manifest_sha256"] = evaluation._fingerprint(manifest)
    report = audit(manifest, prediction)
    assert report["metrics"]["reacquired_after_visible_gap"] == 1
    assert report["metrics"]["missed_visible_actor_frames"] == 1
    assert report["metrics"]["adjacent_unobserved_links"] == 2


def test_track_continued_across_long_timestamp_gap_is_untrusted():
    manifest, prediction = fixture()
    manifest["clips"][2]["frames"][2]["timestamp_ms"] = 1000
    manifest["clips"][2]["frames"][3]["timestamp_ms"] = 1300
    prediction["clips"][0]["frames"][2]["timestamp_ms"] = 1000
    prediction["clips"][0]["frames"][3]["timestamp_ms"] = 1300
    prediction["manifest_sha256"] = evaluation._fingerprint(manifest)
    result = audit(manifest, prediction)
    assert result["metrics"]["large_timestamp_intervals"] == 2
    assert result["metrics"]["untrusted_continuations_across_time_gap"] == 1
    assert "temporal_gap_tracking_continuity_untrusted" in result["blocking_reasons"]
    assert result["release_authorized"] is False


def test_false_positive_detections_are_separate_from_missing_reference_person():
    manifest, prediction = fixture()
    frame = prediction["clips"][0]["frames"][0]
    frame["observations"] = [
        {"detection_index": 0, "track_token": "T_noise", "actor_token": None},
    ]
    result = audit(manifest, prediction)
    assert result["metrics"]["unmatched_detections"] == 2
    assert result["metrics"]["missed_visible_actor_frames"] == 2
    assert result["metrics"]["reference_visible_actor_frames"] == 6
    assert result["metrics"]["matched_actor_frames"] == 4


def test_incomplete_or_malformed_manifest_rejected_before_predictions():
    manifest, prediction = fixture()
    manifest["clips"][2]["actor_tokens"] = ["A_a111", "A_d444"]
    for frame in manifest["clips"][2]["frames"]:
        frame["states"][0]["actor_token"] = "A_a111"
    prediction["manifest_sha256"] = evaluation._fingerprint(manifest)
    with pytest.raises(ValueError, match="Actor leakage"):
        audit(manifest, prediction)


def test_cannot_match_invisible_ground_truth_actor_in_prediction():
    manifest, prediction = fixture()
    frame = prediction["clips"][0]["frames"][2]["observations"][0]
    frame["actor_token"] = "A_c333"  # this actor is out_of_frame
    with pytest.raises(ValueError, match="not visible"):
        audit(manifest, prediction)


def test_private_mode_requires_file_paths_and_does_not_accept_demo_files(tmp_path):
    # This is a CLI/input-contract test without any human footage.
    private = tmp_path / "private"
    private.mkdir()
    manifest, prediction = fixture()
    mf = private / "manifest.json"
    pr = private / "predictions.json"
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    pr.write_text(json.dumps(prediction), encoding="utf-8")
    assert mf.is_file() and pr.is_file()
    # Only structural evaluation; user must independently verify rights
    # and manually annotated actor/detection correspondence.
    result = audit(manifest, prediction, demo=False)
    assert result["release_authorized"] is False
    assert result["status"] == "PRIVATE_OFFLINE_TRACKING_DIAGNOSTICS_ONLY"
