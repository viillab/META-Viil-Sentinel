"""No network, no MediaPipe and no human media: development split guards."""
import hashlib
import json

import pytest

dev = pytest.importorskip("app.dev_video_research")
comparison = pytest.importorskip("app.review_dev_comparison")
contracts = pytest.importorskip("sentinel_edge.contracts")
traces = pytest.importorskip("sentinel_edge.pose_traces")


def test_dev_selection_disjoint_from_previous_five_and_pinned():
    ids = [row[0] for row in dev.DEV]
    assert len(ids) == len(set(ids)) == 5
    assert not set(ids) & dev.HOLDOUT_IDS
    assert sum(cat != "adl_no_fall" for _, cat, *_ in dev.DEV) == 3
    assert sum(cat == "adl_no_fall" for _, cat, *_ in dev.DEV) == 2
    for _, _, path, size, git_sha in dev.DEV:
        assert path.startswith("data/") and path.endswith(".mp4")
        assert 0 < size <= dev.MAX_BYTES
        assert len(git_sha) == 40
        assert len(dev.EXPECTED_SHA256[git_sha]) == 64
    assert dev.DEV_ROOT.is_relative_to(dev.ROOT / "data" / "private")


def test_git_and_sha256_pins_reject_modified_dev_video(tmp_path, monkeypatch):
    payload = b"\x00\x00\x00\x18ftypisom" + b"fictional-bytes-only"
    obj_id = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    monkeypatch.setitem(dev.EXPECTED_SHA256, obj_id, hashlib.sha256(payload).hexdigest())
    video = tmp_path / "synthetic.mp4"
    video.write_bytes(payload)
    assert dev._validate(video, len(payload), obj_id) == hashlib.sha256(payload).hexdigest()
    video.write_bytes(payload[:-1] + b"x")
    with pytest.raises(ValueError, match="pinned"):
        dev._validate(video, len(payload), obj_id)
    video.write_bytes(payload[:-1])
    with pytest.raises(ValueError, match="size"):
        dev._validate(video, len(payload), obj_id)


def test_dev_manifest_modified_or_cross_split_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "_validate", lambda *_: "f" * 64)
    for clip_id, _, _, _, _ in dev.DEV:
        (tmp_path / f"{clip_id}.pose.jsonl").write_text(
            '{"timestamp_ms":0,"landmarks":{}}\n', encoding="utf-8",
        )
    from app import public_video_eval
    monkeypatch.setattr(public_video_eval, "ROOT", tmp_path.parent)
    # Fake dev root inside allowed private folder.
    root = tmp_path.parent / "data" / "private" / "dev"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "version": 1, "permission_basis": "research",
        "clips": [{"id": "FD0033", "trace": "FD0033.pose.jsonl",
                   "expected_fall": True}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        dev.baseline(root)


def test_pure_dev_comparison_uses_real_trace_parser_but_no_media_or_meta(tmp_path, monkeypatch):
    for clip_id, category, _, _, _ in dev.DEV:
        # Basic neutral synthetic motion, not real person pose.
        frames = [
            contracts.PoseFrame(timestamp_ms=t, source_id=clip_id, landmarks={
                11: contracts.Landmark(.46, .25),
                12: contracts.Landmark(.54, .25),
                23: contracts.Landmark(.45, .53),
                24: contracts.Landmark(.55, .53),
            }) for t in (0, 100, 200, 300)
        ]
        (tmp_path / f"{clip_id}.pose.jsonl").write_text(
            "\n".join(traces.frame_to_trace_record(frame) for frame in frames) + "\n",
            encoding="utf-8",
        )
    truth = [
        {"clip_id": clip_id, "expected_fall": cat != "adl_no_fall",
         "predicted_fall": False, "analyzed_frames": 4}
        for clip_id, cat, *_ in dev.DEV
    ]
    monkeypatch.setattr(comparison, "baseline", lambda _: {
        "baseline": {"clips": truth},
    })
    result = comparison.compare_development_only(tmp_path)
    assert result["development_clip_count"] == 5
    assert result["v1_unchanged"] is True
    assert result["meta_api_called"] is False
    assert result["fall_confirmation_performed"] is False
    assert all(row["review_candidate_count"] == 0 for row in result["clips"])
    assert result["experimental_review_only_clip_metrics"]["false_positive"] == 0
    assert result["experimental_review_only_clip_metrics"]["false_negative"] == 3
