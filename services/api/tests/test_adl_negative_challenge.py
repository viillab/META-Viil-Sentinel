"""Private-data-safe ADL negative challenge and synthetic counterexamples."""
import hashlib
from dataclasses import asdict

import pytest

challenge = pytest.importorskip("app.adl_negative_challenge")
stress = pytest.importorskip("app.synthetic_adl_stress")


def fictional_mp4():
    return b"\x00\x00\x00\x18ftypisom" + b"fictional-fixture-only-not-real-video"


def test_two_remaining_adl_clips_are_unseen_by_previous_cohorts():
    assert len(challenge.CLIPS) == 2
    assert {c.clip_id for c in challenge.CLIPS} == {"FD0001", "FD0005"}
    assert {c.clip_id for c in challenge.CLIPS}.isdisjoint(challenge.ALREADY_USED)
    assert all(c.upstream_relative_path.startswith("data/adl_no_fall/")
               for c in challenge.CLIPS)
    assert all(c.upstream_relative_path.endswith(".mp4") for c in challenge.CLIPS)
    assert all(0 < c.size_bytes <= challenge.MAX_FILE_BYTES for c in challenge.CLIPS)
    assert all(len(c.git_blob_sha1) == 40 and len(c.sha256) == 64
               for c in challenge.CLIPS)
    assert all("PIN" not in c.sha256 for c in challenge.CLIPS)
    assert challenge.CHALLENGE_ROOT.is_relative_to(
        challenge.ROOT / "data" / "private",
    )
    assert asdict(challenge.FIXED_V2_CONFIG)["min_rapid_hip_drop"] == .16
    assert asdict(challenge.FIXED_V2_CONFIG)["horizontal_min_angle_deg"] == 60


def test_verifier_requires_git_object_sha256_file_size_and_mp4(tmp_path):
    payload = fictional_mp4()
    git = hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload,
    ).hexdigest()
    sha = hashlib.sha256(payload).hexdigest()
    clip = challenge.ChallengeClip(
        "FICT", "data/adl_no_fall/fictional.mp4", len(payload), git, sha,
    )
    file = tmp_path / "FICT.mp4"
    file.write_bytes(payload)
    assert challenge._verify(file, clip) == sha
    with pytest.raises(ValueError, match="independent SHA-256"):
        challenge._verify(file, challenge.ChallengeClip(
            "FICT", "data/adl_no_fall/fictional.mp4",
            len(payload), git, "0" * 64,
        ))
    file.write_bytes(payload[:-1] + b"X")
    with pytest.raises(ValueError, match="exact pinned"):
        challenge._verify(file, clip)
    file.write_bytes(payload[:-1])
    with pytest.raises(ValueError, match="size"):
        challenge._verify(file, clip)
    file.write_bytes(b"x" * len(payload))
    with pytest.raises(ValueError, match="MP4"):
        challenge._verify(file, clip)


def test_cached_fictional_clip_does_not_use_network(tmp_path, monkeypatch):
    payload = fictional_mp4()
    git = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    clip = challenge.ChallengeClip(
        "FICT", "data/adl_no_fall/fake.mp4",
        len(payload), git, hashlib.sha256(payload).hexdigest(),
    )
    (tmp_path / "FICT.mp4").write_bytes(payload)
    monkeypatch.setattr(challenge, "CLIPS", (clip,))
    monkeypatch.setattr(challenge, "_private_root", lambda d: d)

    def forbidden(*args, **kwargs):
        raise AssertionError("Network must not be touched for verified cached media")

    monkeypatch.setattr(challenge, "urlopen", forbidden)
    receipts = challenge.download(tmp_path)
    assert len(receipts) == 1
    assert receipts[0]["sha256"] == clip.sha256
    assert receipts[0]["upstream_git_blob_verified"] is True
    assert not (tmp_path / ".FICT.partial").exists()


def test_challenge_refuses_missing_private_pose_without_model_or_network(
    tmp_path, monkeypatch,
):
    payload = fictional_mp4()
    git = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    sha = hashlib.sha256(payload).hexdigest()
    clips = tuple(
        challenge.ChallengeClip(
            cid, "data/adl_no_fall/fake.mp4", len(payload), git, sha,
        ) for cid in ("FICT1", "FICT2")
    )
    for clip in clips:
        (tmp_path / f"{clip.clip_id}.mp4").write_bytes(payload)
    monkeypatch.setattr(challenge, "CLIPS", clips)
    monkeypatch.setattr(challenge, "_private_root", lambda d: d)
    monkeypatch.setattr(challenge, "_probe_video", lambda path: {
        "frames_reported": 10, "duration_seconds": 1.0,
    })
    with pytest.raises(ValueError, match="private pose trace"):
        challenge.evaluate(tmp_path)


def test_synthetic_safety_stress_explicitly_exposes_two_false_review_risks():
    report = stress.run_synthetic_stress()
    assert report["status"] == "SYNTHETIC_ADL_STRESS_COMPLETE"
    assert report["cases"] == 8
    assert report["v1_candidate_count"] == 1
    assert report["v2_review_candidate_count"] == 2
    assert report["v2_scenarios_with_review_flags"] == 2
    assert report["quality_abstained_scenarios"] == 8
    assert all(x["quality_abstained"] is True for x in report["scenarios"])
    assert all(x["automated_alert_permitted"] is False for x in report["scenarios"])
    assert report["real_world_false_alert_rate_established"] is False
    assert report["meta_api_called"] is False
    assert report["automated_emergency_dispatch"] is False
    observed = {
        entry["scenario"]: entry["v2_review_candidate_count"]
        for entry in report["scenarios"]
    }
    assert {name for name, count in observed.items() if count} == {
        "rapid_voluntary_sitting", "rapid_voluntary_bed_shift",
    }
    assert all(entry["synthetic_nonfall_ground_truth"] for entry in report["scenarios"])
    assert all(entry["v2_review_only"] for entry in report["scenarios"])
    assert all(entry["notification_sent"] is False for entry in report["scenarios"])
    assert all(entry["raw_pose_coordinates_exported"] is False
               for entry in report["scenarios"])
    assert "landmarks" not in str(report)
    assert "hip_y" not in str(report)


def test_six_clip_replay_rejects_duplicate_ids_without_private_file_access(monkeypatch):
    from app import review_dev_comparison

    fake_old = {"clips": [
        {"id": "FD0001", "source_label_fall": False, "frames": 4,
         "v1_candidate": False, "review_v2_candidate": False},
    ]}
    fake_dev = {"clips": [
        {"id": "FD0001", "dataset_expected_fall": False,
         "analyzed_frames": 4, "original_v1_candidate": False,
         "experimental_review_candidate": False},
    ]}
    fake_new = {"details": [
        {"clip_id": "FD0005", "frames": 4, "v1_candidate_count": 0,
         "v2_review_candidate_count": 0},
    ]}
    monkeypatch.setattr(review_dev_comparison, "compare_previously_inspected",
                        lambda *args: fake_old)
    monkeypatch.setattr(review_dev_comparison, "compare_development_only",
                        lambda *args: fake_dev)
    monkeypatch.setattr(challenge, "evaluate", lambda *args: fake_new)
    with pytest.raises(ValueError, match="six distinct"):
        challenge.summarize_all_six_adl()
