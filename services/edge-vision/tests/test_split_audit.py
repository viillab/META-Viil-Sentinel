"""Prevent subject/recording/view/data leakage before *any* model training."""
from copy import deepcopy

import pytest

from sentinel_edge.split_audit import audit_subject_splits


def manifest():
    clips = []
    for s in ("train", "val", "test"):
        for label in (True, False):
            clips.append({
                "clip_id": f"{s}-{'fall' if label else 'adl'}-01",
                "dataset_id": "licensed-demo",
                "subject_id": f"pseudonym-{s}",
                "recording_id": f"{s}-{'fall' if label else 'adl'}",
                "split": s, "expected_fall": label,
            })
    return {"version": 2, "permission_basis": "synthetic metadata only; no real people",
            "clips": clips}


def test_all_three_splits_have_both_classes_without_exposing_ids():
    result = audit_subject_splits(manifest())
    assert result["train"] == {"clips": 2, "subjects": 1, "fall": 1, "adl": 1}
    assert result["test"]["subjects"] == 1
    assert result["safe_to_deploy"] is False
    assert result["permission_claim_unverified"] is True
    assert "pseudonym-train" not in str(result)


def test_reject_subject_overlap():
    m = manifest()
    m["clips"][2]["subject_id"] = m["clips"][0]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        audit_subject_splits(m)


def test_reject_camera_view_recording_overlap():
    m = manifest()
    m["clips"][2]["recording_id"] = m["clips"][0]["recording_id"]
    with pytest.raises(ValueError, match="recording leakage"):
        audit_subject_splits(m)


def test_reject_same_media_digest_in_two_splits():
    m = manifest()
    for i in (0, 2):
        m["clips"][i]["media_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="hash leakage"):
        audit_subject_splits(m)


def test_reject_class_imbalance_even_if_split_metadata_present():
    m = manifest()
    m["clips"] = [c for c in m["clips"] if c["clip_id"] != "test-adl-01"]
    with pytest.raises(ValueError, match="BOTH fall and ADL"):
        audit_subject_splits(m)


def test_reject_unlabeled_or_malformed_privacy_sensitive_metadata():
    m = manifest()
    m["clips"][0]["expected_fall"] = 1
    with pytest.raises(ValueError, match="explicit boolean"):
        audit_subject_splits(m)
    m = manifest()
    m["clips"][0]["subject_id"] = "Alice Private Name"
    with pytest.raises(ValueError, match="pseudonymous"):
        audit_subject_splits(m)
    m = manifest()
    m["clips"][0]["path"] = "C:\\Users\\private\\video.mp4"
    with pytest.raises(ValueError, match="fields"):
        audit_subject_splits(m)


def test_reject_duplicate_clips_unknown_split_and_unverified_permission():
    m = manifest()
    m["clips"][1]["clip_id"] = m["clips"][0]["clip_id"]
    with pytest.raises(ValueError, match="duplicated"):
        audit_subject_splits(m)
    m = manifest()
    m["clips"][1]["split"] = "deployment"
    with pytest.raises(ValueError, match="train, val or test"):
        audit_subject_splits(m)
    m = manifest()
    m["permission_basis"] = ""
    with pytest.raises(ValueError, match="permission_basis"):
        audit_subject_splits(m)


def test_private_names_never_appear_in_aggregate_result():
    m = deepcopy(manifest())
    result = audit_subject_splits(m)
    serialized = str(result)
    for c in m["clips"]:
        assert c["subject_id"] not in serialized
        assert c["recording_id"] not in serialized


def test_same_recording_conflicting_labels_rejected_even_within_one_split():
    m = manifest()
    m["clips"][1]["recording_id"] = m["clips"][0]["recording_id"]
    with pytest.raises(ValueError, match="contradictory labels"):
        audit_subject_splits(m)


def test_same_media_digest_with_conflicting_label_rejected():
    m = manifest()
    m["clips"][0]["media_sha256"] = "b" * 64
    m["clips"][1]["media_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="contradictory labels"):
        audit_subject_splits(m)


def test_multiple_views_same_recording_with_same_label_same_split_accepted():
    m = manifest()
    camera_b = deepcopy(m["clips"][0])
    camera_b["clip_id"] = "train-fall-camera-b"
    camera_b["recording_id"] = m["clips"][0]["recording_id"]
    m["clips"].append(camera_b)
    outcome = audit_subject_splits(m)
    assert outcome["train"]["clips"] == 3
    assert outcome["train"]["subjects"] == 1
