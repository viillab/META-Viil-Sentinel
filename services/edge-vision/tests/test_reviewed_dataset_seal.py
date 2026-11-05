"""Unsigned research freeze regression tests use invented NON-VIDEO bytes only."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from sentinel_edge.annotation_review import blank_independent_review_template
from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.reviewed_dataset_seal import (
    export_sealed_reviewed_windows, freeze_reviewed_dataset, main,
    verify_reviewed_dataset_seal,
)
from sentinel_edge.temporal_training import train_and_evaluate


def fake_manifest(tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    groups = {
        "version": 2,
        "permission_basis": "Invented synthetic NON-VIDEO bytes for unit tests",
        "clips": [],
    }
    proposals = {"version": 1, "segments": []}
    for split in ("train", "val", "test"):
        for fall in (True, False):
            cid = f"example-{split}-{'fall' if fall else 'adl'}"
            fake_bytes = ("not a video " + cid).encode("ascii")
            (folder / (cid + ".avi")).write_bytes(fake_bytes)
            groups["clips"].append({
                "clip_id": cid, "dataset_id": "synthetic",
                "subject_id": "subject-" + split,
                "recording_id": cid, "split": split,
                "expected_fall": fall,
                "media_sha256": sha256(fake_bytes).hexdigest(),
            })
            proposals["segments"].append({
                "clip_id": cid, "video": "clips/" + cid + ".avi",
                "start_ms": 0, "end_ms": 3000,
                "expected_fall": fall, "label_reviewed": False,
                "annotation_basis": "Invented synthetic activity placeholder only",
            })
    reviews = blank_independent_review_template(groups, proposals)
    for i, row in enumerate(reviews["decisions"]):
        clip = groups["clips"][i // 2]
        row.update({
            "reviewer_id": "fake-alpha" if i % 2 == 0 else "fake-beta",
            "expected_fall": clip["expected_fall"],
            "activity": "fall_motion" if clip["expected_fall"] else "walk",
            "start_ms": 0 if i % 2 == 0 else 50,
            "end_ms": 3000 if i % 2 == 0 else 2950,
            "media_sha256": clip["media_sha256"],
            "independently_reviewed": True,
            "uncertain": False,
            "review_note": "Fictional test-only reviewer decision, NOT a real human.",
        })
    return groups, proposals, reviews


def fake_collector(video, *, clip_id, model, max_frames, frame_consumer, event_consumer):
    assert model.is_file() and video.is_file() and max_frames <= 6000
    landmarks = {
        11: Landmark(.45, .25, .99), 12: Landmark(.55, .25, .99),
        23: Landmark(.45, .55, .99), 24: Landmark(.55, .55, .99),
    }
    for t in range(0, 3400, 100):
        frame_consumer(PoseFrame(timestamp_ms=t, source_id=clip_id,
                                 landmarks=landmarks))
    return [], {"frames_processed": 34}


def test_freeze_is_deterministic_and_contains_only_aggregate_information(tmp_path):
    groups, proposals, reviews = fake_manifest(tmp_path)
    seal, approved = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    repeated, again = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    assert (seal, approved) == (repeated, again)
    assert verify_reviewed_dataset_seal(
        groups, proposals, reviews, seal, root=tmp_path
    ) == approved
    assert len(approved["segments"]) == 6
    assert seal["split_summary"]["test"] == {
        "clips": 2, "subjects": 1, "fall": 1, "adl": 1,
    }
    assert all(len(seal[k]) == 64 for k in (
        "group_sha256", "publisher_proposals_sha256",
        "review_decisions_sha256", "reviewed_segments_sha256",
    ))
    dumped = json.dumps(seal)
    assert "fake-alpha" not in dumped
    assert "example-train" not in dumped
    assert "clips/" not in dumped
    assert seal["human_identity_verified"] is False
    assert seal["production_use_authorized"] is False


@pytest.mark.parametrize("damage,expected", [
    ("decision_text", "seal mismatch"),
    ("decision_order", "seal mismatch"),
    ("publisher_text", "seal mismatch"),
    ("group_order", "seal mismatch"),
    ("seal_digest", "seal mismatch"),
    ("extra_seal_field", "malformed"),
    ("wrong_version", "malformed"),
    ("wrong_reviewed_label", "disagrees"),
    ("missing_entry", "exactly two"),
])
def test_review_seal_fails_closed_on_any_manifest_drift(tmp_path, damage, expected):
    groups, proposals, reviews = fake_manifest(tmp_path)
    seal, _ = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    groups, proposals, reviews, seal = deepcopy(
        (groups, proposals, reviews, seal)
    )
    if damage == "decision_text":
        reviews["decisions"][0]["review_note"] = (
            "Fictional test-only revised note with altered substance."
        )
    elif damage == "decision_order":
        reviews["decisions"].reverse()
    elif damage == "publisher_text":
        proposals["segments"][0]["annotation_basis"] = (
            "Other invented synthetic source explanation."
        )
    elif damage == "group_order":
        groups["clips"].reverse()
    elif damage == "seal_digest":
        seal["reviewed_segments_sha256"] = "0" * 64
    elif damage == "extra_seal_field":
        seal["reviewer_email"] = "example@invalid.example"
    elif damage == "wrong_version":
        seal["version"] = 2
    elif damage == "wrong_reviewed_label":
        reviews["decisions"][0]["expected_fall"] = (
            not reviews["decisions"][0]["expected_fall"]
        )
    elif damage == "missing_entry":
        reviews["decisions"].pop()
    with pytest.raises(ValueError, match=expected):
        verify_reviewed_dataset_seal(groups, proposals, reviews, seal, root=tmp_path)


def test_unreviewed_template_must_never_get_unsigned_seal(tmp_path):
    groups, proposals, _ = fake_manifest(tmp_path)
    unreviewed = blank_independent_review_template(groups, proposals)
    with pytest.raises(ValueError):
        freeze_reviewed_dataset(groups, proposals, unreviewed, root=tmp_path)


def test_media_replaced_after_freeze_must_be_rejected(tmp_path):
    groups, proposals, reviews = fake_manifest(tmp_path)
    seal, _ = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    source = tmp_path / proposals["segments"][0]["video"]
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_reviewed_dataset_seal(groups, proposals, reviews, seal, root=tmp_path)


def test_export_seal_preflight_avoids_unapproved_decode(tmp_path):
    groups, proposals, reviews = fake_manifest(tmp_path)
    seal, _ = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    model = tmp_path / "fake.task"
    model.write_bytes(b"fictional model bytes")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Decoder must never run on changed review")

    reviews["decisions"][0]["review_note"] = "Updated fictional research decision."
    with pytest.raises(ValueError, match="seal mismatch"):
        export_sealed_reviewed_windows(
            groups, proposals, reviews, seal, root=tmp_path,
            model=model, collector=forbidden,
        )
    assert calls == []


def test_seal_gated_private_window_export_matches_training_contract(tmp_path):
    groups, proposals, reviews = fake_manifest(tmp_path)
    seal, _ = freeze_reviewed_dataset(groups, proposals, reviews, root=tmp_path)
    model = tmp_path / "fake.task"
    model.write_bytes(b"fake test-only model")
    bundle = export_sealed_reviewed_windows(
        groups, proposals, reviews, seal, root=tmp_path,
        model=model, collector=fake_collector,
    )
    assert len(bundle["windows"]) == 6
    assert all(len(window["features"]) == 30 for window in bundle["windows"])
    assert all(len(row) == 6 for w in bundle["windows"] for row in w["features"])
    trained, report = train_and_evaluate(groups, bundle)
    assert trained.model_bytes < 1500
    assert report["automated_fall_alerting_authorized"] is False
    assert not list(tmp_path.glob("*feature*"))


@pytest.mark.parametrize("args", [
    ["--mode", "freeze"],
    ["--mode", "export"],
    ["--mode", "verify"],
])
def test_cli_requires_rights_acknowledgement_and_all_inputs(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_cli_freeze_verify_export_happy_path_only_on_invented_data(
    tmp_path, monkeypatch, capsys
):
    import sentinel_edge.reviewed_dataset_seal as seal_cli

    groups, proposals, reviews = fake_manifest(tmp_path)
    # Only the testing fixture substitutes a fake private directory; the
    # production CLI's real _private_paths/_private_output_path remain strict.
    monkeypatch.setattr(seal_cli, "_private_paths", lambda args: (
        tmp_path, groups, proposals, reviews, tmp_path
    ))
    monkeypatch.setattr(seal_cli, "_private_output_path", lambda path: path)
    monkeypatch.setattr(seal_cli, "_private_input", lambda path, private: path)
    frozen = tmp_path / "freeze.json"
    common = [
        "--root", str(tmp_path), "--groups", "fixture-groups.json",
        "--proposals", "fixture-proposals.json",
        "--reviews", "fixture-reviews.json",
        "--seal", str(frozen),
        "--acknowledge-media-rights", "--acknowledge-review-privacy",
    ]
    assert main(["--mode", "freeze", *common, "--output", str(frozen)]) == 0
    assert frozen.exists()
    freeze_log = json.loads(capsys.readouterr().out)
    assert freeze_log["human_identity_verified"] is False
    assert "example-train" not in json.dumps(freeze_log)

    assert main(["--mode", "verify", *common]) == 0
    verify_log = json.loads(capsys.readouterr().out)
    assert verify_log["dataset_fingerprint_sha256"] == (
        freeze_log["dataset_fingerprint_sha256"]
    )
    model = tmp_path / "fictional.task"
    model.write_bytes(b"synthetic fixture no real weights")
    output = tmp_path / "private-windows.json"
    original_export = export_sealed_reviewed_windows
    monkeypatch.setattr(
        seal_cli, "export_sealed_reviewed_windows",
        lambda g, p, r, s, *, root, model: original_export(
            g, p, r, s, root=root, model=model, collector=fake_collector
        ),
    )
    assert main([
        "--mode", "export", *common, "--model", str(model),
        "--output", str(output), "--confirm-consent",
        "--acknowledge-pose-privacy",
    ]) == 0
    windows = json.loads(output.read_text("utf-8"))
    assert len(windows["windows"]) == 6
    logged = json.loads(capsys.readouterr().out)
    assert logged["pose_window_shape"] == [30, 6]

    # Tampering after the private freeze must stop all subsequent verification,
    # not recreate it or overwrite previously approved windows.
    reviews["decisions"][0]["review_note"] = (
        "This revised fictional reviewer statement changes the previous digest."
    )
    with pytest.raises(SystemExit) as denied:
        main(["--mode", "verify", *common])
    assert denied.value.code == 2


def test_real_cli_rejects_unapproved_outside_private_root(tmp_path):
    fake_seal = tmp_path / "seal.json"
    with pytest.raises(SystemExit) as denied:
        main([
            "--mode", "freeze", "--root", str(tmp_path),
            "--groups", str(tmp_path / "group.json"),
            "--proposals", str(tmp_path / "proposals.json"),
            "--reviews", str(tmp_path / "reviews.json"),
            "--seal", str(fake_seal), "--output", str(fake_seal),
            "--acknowledge-media-rights", "--acknowledge-review-privacy",
        ])
    assert denied.value.code == 2
    assert not fake_seal.exists()
