"""Offline-only IKAR intake safety tests on invented tiny archives."""
from hashlib import sha256
import io
import json
from pathlib import Path
import tarfile

import pytest

from sentinel_edge import ikar_domain_stress as mod


def fictional_archive(root, *, sabotage=None):
    path = root / "IKAR_dataset.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for category, expected in mod.CATEGORIES.items():
            for num in range(expected):
                for folder, ext in (("videos", "mp4"), ("labels", "json")):
                    name = f"IKAR_dataset/{category}/{folder}/{category}_{num}.{ext}"
                    if sabotage == "missing" and category == "trips" and num == 2:
                        continue
                    if sabotage == "traversal" and category == "trips" and num == 0:
                        name = "IKAR_dataset/../escape.mp4"
                    if sabotage == "symlink" and category == "trips" and num == 0:
                        t = tarfile.TarInfo(name)
                        t.type = tarfile.SYMTYPE
                        t.linkname = "../../secret.txt"
                        tar.addfile(t)
                        continue
                    data = f"fictional-{category}-{num}-{folder}".encode()
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
    return path


def _fake_private(monkeypatch):
    monkeypatch.setattr(mod, "private_root", lambda p: Path(p))


def test_official_shape_requires_all_four_category_and_label_pairs(tmp_path):
    archive = fictional_archive(tmp_path)
    with tarfile.open(archive, "r:gz") as file:
        members = mod.inspect_archive(file)
    assert len(members) == 2 * sum(mod.CATEGORIES.values())
    assert all((category, number, "videos") in members for category in mod.CATEGORIES
               for number in mod.SELECTED_IDS)


@pytest.mark.parametrize("bad", ["missing", "traversal", "symlink"])
def test_archive_rejects_missing_source_or_archive_path_attack(tmp_path, bad):
    archive = fictional_archive(tmp_path, sabotage=bad)
    with tarfile.open(archive, "r:gz") as file:
        with pytest.raises(ValueError):
            mod.inspect_archive(file)


def test_source_private_predeclared_video_intake_repeat_and_drift(tmp_path, monkeypatch):
    _fake_private(monkeypatch)
    archive = fictional_archive(tmp_path)
    monkeypatch.setattr(mod, "verify_archive", lambda path: mod.ARCHIVE_SHA256)
    manifest = mod.extract_fixed_subset(tmp_path, archive)
    assert manifest["total_publisher_fall_videos"] == 278
    assert manifest["no_ADL_available"] is True
    assert manifest["fall_onsets_verified"] is False
    assert len(manifest["selection"]) == 8
    assert [r["publisher_action_id"] for r in manifest["selection"]] == [
        0, 1, 0, 1, 0, 1, 0, 1,
    ]
    validated = mod.validate_subset(tmp_path)
    assert validated == manifest
    assert mod.extract_fixed_subset(tmp_path, archive) == manifest
    damaged = tmp_path / "selected" / "trips" / "videos" / "trips_0.mp4"
    damaged.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="drift"):
        mod.validate_subset(tmp_path)
    with pytest.raises(ValueError, match="drift"):
        mod.extract_fixed_subset(tmp_path, archive)


def test_public_fall_only_research_report_is_not_event_recall(tmp_path, monkeypatch):
    _fake_private(monkeypatch)
    tarball = fictional_archive(tmp_path)
    monkeypatch.setattr(mod, "verify_archive", lambda path: mod.ARCHIVE_SHA256)
    mod.extract_fixed_subset(tmp_path, tarball)
    model = tmp_path / "fake-research.json"
    model.write_text("frozen", encoding="utf8")
    monkeypatch.setattr(mod, "BASELINE_SHA256", mod.sha256_file(model))
    monkeypatch.setattr(mod, "read_private_artifact",
                        lambda path: type("Model", (), {"threshold": .53})())
    monkeypatch.setattr(mod, "_private_output_path", lambda path: path)
    monkeypatch.setattr(mod, "_video_metadata", lambda path: (120, 30))
    def fake_evaluate(path, group, activity, duration, task, weights, **kwargs):
        assert group == "fall"
        assert duration == 4000
        assert kwargs["diagnostics"] is True
        assert kwargs["detailed_reasons"] is True
        return {
            "selected_windows": 1, "pose_eligible_windows": 1,
            "pose_abstentions": 0, "any_window_fall_candidate": False,
            "pose_rejection_reasons": {"accepted": 110, "no_person": 10},
            "failure_diagnostic": {
                "decoded_frames": 120,
                "torso_adapter_available_frames": 110,
                "motion_geometry_eligible_frames": 100,
                "legacy_heuristic_event_count": 0,
            },
        }
    monkeypatch.setattr(mod, "_evaluate_one", fake_evaluate)
    output = tmp_path / "fake-report.json"
    task = tmp_path / "pose.task"
    task.write_bytes(b"test")
    report = mod.run_frozen_stress(tmp_path, model, task, output)
    assert report["sampled_total"] == 8
    assert report["no_annotated_ADL_or_event_denominator"] is True
    assert report["no_promotion_metric_inferred"] is True
    assert all(x["videos"] == 2 and x["decoded_frames"] == 240
               for x in report["categories"].values())
    assert "recall" not in str(report).lower()
    assert output.is_file()
    assert json.loads(output.read_text()) == report
    with pytest.raises(FileExistsError):
        mod.run_frozen_stress(tmp_path, model, task, output)


def test_unrecognized_and_tampered_manifest_denied(tmp_path, monkeypatch):
    _fake_private(monkeypatch)
    archive = fictional_archive(tmp_path)
    monkeypatch.setattr(mod, "verify_archive", lambda path: mod.ARCHIVE_SHA256)
    manifest = mod.extract_fixed_subset(tmp_path, archive)
    manifest["fall_onsets_verified"] = True
    destination = tmp_path / "ikar-8-source-frozen-manifest-v1.json"
    destination.write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="unpinned or claims"):
        mod.validate_subset(tmp_path)



def dataverse_payload(*, license_name="CC BY 4.0", file_id=16904,
                      filesize=None, checksum=None):
    return {"status": "OK", "data": {"latestVersion": {
        "versionNumber": 1, "versionMinorNumber": 0,
        "license": {"name": license_name},
        "files": [{"restricted": False, "dataFile": {
            "id": file_id, "filename": "IKAR_dataset.tar.gz",
            "filesize": mod.ARCHIVE_BYTES if filesize is None else filesize,
            "checksum": {"type": "MD5", "value":
                         mod.ARCHIVE_MD5 if checksum is None else checksum},
        }}],
    }}}


@pytest.mark.parametrize("wrong", [
    {"license_name": "CC BY-NC 4.0"},
    {"file_id": 1},
    {"filesize": -1},
    {"checksum": "0" * 32},
])
def test_official_api_fails_on_wrong_licensing_archive_identity_or_hash(wrong):
    with pytest.raises(ValueError):
        mod.validate_dataverse_api(dataverse_payload(**wrong))


def test_official_download_binary_reused_and_checksum_bounded(tmp_path, monkeypatch):
    from hashlib import md5
    _fake_private(monkeypatch)
    dummy = b"Official-looking invented bytes only"
    monkeypatch.setattr(mod, "ARCHIVE_BYTES", len(dummy))
    monkeypatch.setattr(mod, "ARCHIVE_MD5", md5(dummy).hexdigest())
    monkeypatch.setattr(mod, "ARCHIVE_SHA256", sha256(dummy).hexdigest())
    calls = []
    def fake_open(request, *, timeout):
        calls.append(request.full_url)
        data = (json.dumps(dataverse_payload()).encode()
                if "/api/datasets/" in request.full_url else dummy)
        return io.BytesIO(data)
    first = mod.fetch_official_archive(tmp_path, opener=fake_open)
    assert first["archive_sha256"] == mod.ARCHIVE_SHA256
    assert first["already_downloaded_and_verified"] is False
    assert len(calls) == 2
    second = mod.fetch_official_archive(tmp_path, opener=fake_open)
    assert second["already_downloaded_and_verified"] is True
    assert len(calls) == 3  # source license is reverified but media is reused
    (tmp_path / "IKAR_dataset.tar.gz").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        mod.fetch_official_archive(tmp_path, opener=fake_open)

def test_no_public_archive_hash_overrides_allowed(tmp_path):
    file = tmp_path / "IKAR_dataset.tar.gz"
    file.write_bytes(b"not a real 127MB IKAR file")
    with pytest.raises(ValueError, match="identity or size"):
        mod.verify_archive(file)
