"""Offline safety and reproducibility checks: NEVER download real videos in CI."""
import hashlib
import json

import pytest

from app import public_video_eval as module


def clip_for_bytes(payload: bytes) -> module.PublicClip:
    sha = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
    return module.PublicClip(
        clip_id="TEST0001", original_path="data/adl_no_fall/fake.mp4",
        label=False, size=len(payload), git_blob_sha1=sha,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_five_real_pinned_public_samples_and_no_private_urls():
    assert len(module.CLIPS) == 5
    assert sum(c.label for c in module.CLIPS) == 3
    assert sum(not c.label for c in module.CLIPS) == 2
    assert len({c.clip_id for c in module.CLIPS}) == 5
    assert len({c.original_path for c in module.CLIPS}) == 5
    assert len({c.git_blob_sha1 for c in module.CLIPS}) == 5
    assert len({c.sha256 for c in module.CLIPS}) == 5
    assert all(c.original_path.startswith("data/") and c.original_path.endswith(".mp4")
               for c in module.CLIPS)
    assert all(0 < c.size <= module.MAX_VIDEO_BYTES for c in module.CLIPS)
    assert all(len(c.sha256) == 64 for c in module.CLIPS)
    assert module.LICENSE_URL == "https://creativecommons.org/licenses/by-nc/4.0/"
    assert module.DATA_ROOT.is_relative_to(module.ROOT / "data" / "private")


def test_video_bytes_require_both_git_blob_hash_and_sha256(tmp_path):
    payload = b"\x00\x00\x00\x18ftypisom" + b"test-only-fake-mp4-bytes"
    clip = clip_for_bytes(payload)
    file = tmp_path / "TEST0001.mp4"
    file.write_bytes(payload)
    assert module.verify_video(file, clip) == hashlib.sha256(payload).hexdigest()

    file.write_bytes(payload[:-1] + b"X")
    with pytest.raises(ValueError, match="pinned"):
        module.verify_video(file, clip)

    file.write_bytes(payload[:-1])
    with pytest.raises(ValueError, match="size"):
        module.verify_video(file, clip)


def test_non_mp4_magic_is_refused_even_when_hash_is_pinned(tmp_path):
    payload = b"not-allowed-video-content"
    clip = clip_for_bytes(payload)
    file = tmp_path / "TEST0001.mp4"
    file.write_bytes(payload)
    with pytest.raises(ValueError, match="MP4"):
        module.verify_video(file, clip)


def test_cached_private_dataset_does_not_reach_public_network(tmp_path, monkeypatch):
    project = tmp_path / "repo"
    (project / "data" / "private").mkdir(parents=True)
    payload = b"\x00\x00\x00\x18ftypisom" + b"synthetic-data-no-human"
    clip = clip_for_bytes(payload)
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(module, "CLIPS", (clip,))
    private = project / "data" / "private" / "test_cache"
    private.mkdir()
    (private / "TEST0001.mp4").write_bytes(payload)

    def banned_network(*_, **__):
        raise AssertionError("Cached dataset must not call network")

    monkeypatch.setattr(module, "urlopen", banned_network)
    receipts = module.download_clips(private)
    assert len(receipts) == 1
    assert receipts[0]["verified"] is True
    assert receipts[0]["label"] == "no_fall"
    assert receipts[0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipts[0]["bytes"] == len(payload)


def test_private_directory_validation_before_any_creation(tmp_path, monkeypatch):
    project = tmp_path / "repo"
    (project / "data" / "private").mkdir(parents=True)
    monkeypatch.setattr(module, "ROOT", project)
    allowed = project / "data" / "private" / "safe"
    assert module._private_root(allowed).is_dir()
    outside = project / "leak" / "export"
    with pytest.raises(ValueError, match="private"):
        module._private_root(outside)
    assert not outside.exists()


def test_private_symlink_rejected(tmp_path, monkeypatch):
    project = tmp_path / "repo"
    private = project / "data" / "private"
    private.mkdir(parents=True)
    outside = tmp_path / "other"
    outside.mkdir()
    alias = private / "alias"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is not allowed on this Windows host")
    monkeypatch.setattr(module, "ROOT", project)
    with pytest.raises(ValueError):
        module._private_root(alias)


def test_diagnostics_only_aggregates_synthetic_pose_not_coordinates():
    pytest.importorskip("sentinel_edge")
    synthetic = (
        module.ROOT / "services" / "edge-vision" / "examples"
        / "synthetic" / "fall.jsonl"
    )
    result = module.diagnose_trace(synthetic, "synthetic-test")
    assert result["frames"] >= 3
    assert result["pose_valid_frames"] > 0
    assert result["raw_landmark_coordinates_exported"] is False
    assert result["source"] == "aggregated_local_pose_diagnostics_only"
    assert "hip_y" not in result
    assert "landmarks" not in result
    assert "x" not in result and "y" not in result
    assert result["required_horizontal_angle_min_deg"] == 56.0


def test_existing_summary_refuses_unknown_extra_dataset_clip(tmp_path, monkeypatch):
    pytest.importorskip("sentinel_edge")
    project = tmp_path / "repo"
    private = project / "data" / "private"
    private.mkdir(parents=True)
    monkeypatch.setattr(module, "ROOT", project)
    folder = private / "eval"
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps({"version": 1, "permission_basis": "cc-by-nc-4.0",
                    "clips": [{"id": "untrusted-human", "trace": "steal.jsonl",
                               "expected_fall": True}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pinned five videos"):
        module.summarize_existing(folder)
