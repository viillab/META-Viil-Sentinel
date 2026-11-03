"""No-human-data CI tests for strict private actor-disjoint dataset admission.

All mock rights/subject IDs are invented. Passing does not prove a
permission, actor identity, clinical effect or scientific release.
"""
import copy
import json

import pytest

from app import actor_disjoint_admission as admission


def fiction():
    return admission._fictional_demo_manifest()


def inspect(doc, *, demo=False):
    return admission.inspect_manifest(doc, fictional_demo=demo)


def test_fictional_manifest_exercises_split_and_annotation_contract():
    result = inspect(fiction(), demo=True)
    assert result["status"] == "FICTIONAL_SCHEMA_EXERCISE"
    assert result["clips"] == 3
    assert result["frames"] == 12
    assert result["split_clip_counts"] == {
        "train": 1, "validation": 1, "test": 1,
    }
    assert result["test_multi_person_frames"] == 2
    assert result["test_occlusion_frames"] == 1
    assert result["test_single_visible_actor_handoffs"] == 1
    assert result["machine_checkable_leakage_not_observed"] is True
    assert result["self_reported_review_checklist_complete"] is True
    assert result["release_authorized"] is False
    assert result["automated_alert_authorized"] is False
    assert result["evaluation_cohort_ready_for_scientific_claim"] is False
    assert result["external_legal_privacy_and_identity_review_completed_by_this_tool"] is False
    assert result["live_meta_calls"] is False
    assert result["data_uploaded"] is False


def test_real_manifest_shape_not_equivalent_to_independent_rights_verification():
    report = inspect(fiction())
    assert report["status"] == "PRIVATE_MANIFEST_STRUCTURE_CHECKED"
    assert "actual_legal_rights_identity_and_consent_not_independently_audited" in (
        report["blocking_reasons"]
    )
    assert "actor_independence_cannot_be_verified_from_tokens" in (
        report["blocking_reasons"]
    )
    assert report["release_authorized"] is False
    assert report["evaluation_cohort_ready_for_scientific_claim"] is False


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="unknown"),
    lambda d: d.update(extra="unexpected"),
    lambda d: d.pop("rights"),
    lambda d: d["rights"].update(license_id="proprietary-unverified"),
    lambda d: d["rights"].update(rights_evidence_sha256="not-a-hash"),
    lambda d: d["rights"].update(unauthorized_field="yes"),
    lambda d: d["rights"]["declaration"].update(rights_reviewed_by_human=False),
    lambda d: d["rights"]["declaration"].update(permission_scope_recorded=None),
    lambda d: d["rights"]["declaration"].pop("identity_grouping_reviewed"),
    lambda d: d["rights"]["declaration"].update(extra=True),
])
def test_rights_or_schema_must_be_exact_and_explicit(mutation):
    doc = fiction()
    mutation(doc)
    with pytest.raises(ValueError):
        inspect(doc)


@pytest.mark.parametrize("mutation", [
    lambda d: d["clips"][2].update(actor_tokens=["A_a111", "A_d444"]),
    lambda d: d["clips"][2].update(session_token="S_trn"),
    lambda d: d["clips"][2].update(camera_token="CAM_val"),
    lambda d: d["clips"][2].update(source_sha256="5" * 64),
    lambda d: d["clips"][2].update(clip_token="C_trn"),
])
def test_prevent_cross_split_leakage_or_duplicate_video(mutation):
    doc = fiction()
    mutation(doc)
    with pytest.raises(ValueError):
        inspect(doc)


@pytest.mark.parametrize("mutation", [
    lambda d: d["clips"].pop(1),
    lambda d: d["clips"][0].update(split="unknown"),
    lambda d: d["clips"][0].update(split="test"),
    lambda d: d["clips"][0].update(clip_token="C_../secret"),
    lambda d: d["clips"][0].update(session_token="S_JohnDoe"),
    lambda d: d["clips"][0].update(actor_tokens=["A_a111", "A_a111"]),
    lambda d: d["clips"][0].update(actor_tokens=["A_a111", "john@example.com"]),
    lambda d: d["clips"][0].update(frame_count=True),
    lambda d: d["clips"][0].update(frame_count=500_000),
    lambda d: d["clips"][0].update(extra="not-allowed"),
])
def test_clip_and_pseudonymous_identity_schema_fail_closed(mutation):
    doc = fiction()
    mutation(doc)
    with pytest.raises(ValueError):
        inspect(doc)


@pytest.mark.parametrize("mutation", [
    lambda d: d["clips"][0]["frames"].pop(),
    lambda d: d["clips"][0]["frames"][1].update(frame_index=0),
    lambda d: d["clips"][0]["frames"][2].update(timestamp_ms=100),
    lambda d: d["clips"][0]["frames"][1].update(timestamp_ms=True),
    lambda d: d["clips"][0]["frames"][1].update(frame_index="1"),
    lambda d: d["clips"][0]["frames"][1].update(
        states=[{"actor_token": "A_a111", "state": "not_scored"}]
    ),
    lambda d: d["clips"][0]["frames"][1].update(
        states=[{"actor_token": "A_unknown", "state": "visible"}]
    ),
    lambda d: d["clips"][2]["frames"][1].update(
        states=[{"actor_token": "A_c333", "state": "visible"},
                {"actor_token": "A_c333", "state": "visible"}]
    ),
    lambda d: d["clips"][0]["frames"][1].update(unknown=7),
    lambda d: d["clips"][2]["frames"][1].update(states=[]),
])
def test_each_frame_requires_explicit_per_actor_identity_state(mutation):
    doc = fiction()
    mutation(doc)
    with pytest.raises(ValueError):
        inspect(doc)


def test_actor_must_actually_be_visible_in_a_clip():
    doc = fiction()
    for frame in doc["clips"][1]["frames"]:
        frame["states"][0]["state"] = "out_of_frame"
    with pytest.raises(ValueError, match="visible"):
        inspect(doc)


def test_negative_test_coverage_is_reported_as_blockers_not_pretend_validation():
    doc = fiction()
    # All frames are valid, but test no longer contains an identity handoff.
    doc["clips"][2]["frames"][2]["states"][0]["state"] = "visible"
    doc["clips"][2]["frames"][2]["states"][1]["state"] = "out_of_frame"
    report = inspect(doc, demo=True)
    assert report["test_single_visible_actor_handoffs"] == 0
    assert "test_split_lacks_single_visible_actor_handoff" in report["blocking_reasons"]
    assert report["release_authorized"] is False


def test_test_split_rejects_false_multi_person_coverage():
    doc = fiction()
    for sample in doc["clips"][2]["frames"]:
        sample["states"][1]["state"] = "out_of_frame"
    # D444 still needs an actual visible appearance, so this must reject.
    with pytest.raises(ValueError, match="visible"):
        inspect(doc)


def test_no_raw_identifiers_or_paths_in_aggregate_report():
    result = inspect(fiction())
    output = json.dumps(result, sort_keys=True)
    for sensitive in (
        "A_c333", "A_d444", "C_tst", "S_tst", "CAM_tst",
        "A_a111", "timestamp_ms", "frame_index",
        "actor_token", "source_sha256", "rights_evidence_sha256",
        "points", "landmarks", "x_coord",
    ):
        assert sensitive not in output
    assert result["raw_actor_identifiers_or_coordinates_exported"] is False


def test_private_manifest_reader_rejects_path_outside_private_root(tmp_path, monkeypatch):
    root = tmp_path / "private"
    root.mkdir()
    monkeypatch.setattr(admission, "PRIVATE_ROOT", root)
    outside = tmp_path / "external.json"
    outside.write_text(json.dumps(fiction()), encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        admission._read_private_manifest(outside)


def test_private_reader_allows_mock_file_only_inside_private_root(tmp_path, monkeypatch):
    folder = tmp_path / "data" / "private"
    folder.mkdir(parents=True)
    monkeypatch.setattr(admission, "PRIVATE_ROOT", folder)
    file = folder / "fiction.json"
    file.write_text(json.dumps(fiction()), encoding="utf-8")
    report = inspect(admission._read_private_manifest(file))
    assert report["clips"] == 3
    assert report["release_authorized"] is False


@pytest.mark.parametrize("jsontext", [
    '{"schema":"a","schema":"b"}',
    '{"rights":{"license_id":"x","license_id":"y"}}',
    '{"data":NaN}',
    '{"data":Infinity}',
    'not json at all',
])
def test_reject_duplicate_or_nonstandard_json_in_private_manifest(
    tmp_path, monkeypatch, jsontext,
):
    folder = tmp_path / "private"
    folder.mkdir()
    monkeypatch.setattr(admission, "PRIVATE_ROOT", folder)
    file = folder / "invalid.json"
    file.write_text(jsontext, encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        admission._read_private_manifest(file)


def test_reject_oversized_private_manifest_without_parsing(tmp_path, monkeypatch):
    folder = tmp_path / "private"
    folder.mkdir()
    monkeypatch.setattr(admission, "PRIVATE_ROOT", folder)
    file = folder / "oversized.json"
    file.write_bytes(b" " * (admission.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        admission._read_private_manifest(file)


def test_reject_symlink_that_points_inside_private_storage(tmp_path, monkeypatch):
    folder = tmp_path / "private"
    folder.mkdir()
    monkeypatch.setattr(admission, "PRIVATE_ROOT", folder)
    original = folder / "real.json"
    original.write_text(json.dumps(fiction()), encoding="utf-8")
    alias = folder / "alias.json"
    try:
        alias.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Windows user lacks symlink privileges")
    with pytest.raises(ValueError, match="symlink"):
        admission._read_private_manifest(alias)


def test_reject_symlinked_private_parent_even_when_target_is_inside(tmp_path, monkeypatch):
    folder = tmp_path / "private"
    folder.mkdir()
    monkeypatch.setattr(admission, "PRIVATE_ROOT", folder)
    target_dir = folder / "real"
    target_dir.mkdir()
    file = target_dir / "manifest.json"
    file.write_text(json.dumps(fiction()), encoding="utf-8")
    alias_dir = folder / "alias"
    try:
        alias_dir.symlink_to(target_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Windows user lacks directory symlink privileges")
    with pytest.raises(ValueError, match="symlink"):
        admission._read_private_manifest(alias_dir / "manifest.json")


def test_fictional_credential_or_person_details_cannot_be_used_as_labels():
    doc = fiction()
    doc["clips"][0]["actor_tokens"] = ["A_RealName"]
    with pytest.raises(ValueError):
        inspect(doc)
    doc = copy.deepcopy(fiction())
    doc["clips"][0]["clip_token"] = "C_0x../../user"
    with pytest.raises(ValueError):
        inspect(doc)
