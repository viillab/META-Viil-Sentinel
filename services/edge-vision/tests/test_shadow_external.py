"""Invented-only checks of private-source AI shadow audit output."""
import json


import pytest

from sentinel_edge import shadow_external as audit
from sentinel_edge.contracts import Landmark, PoseFrame


class ResearchModel:
    threshold = .53

    def predict_probability(self, _matrix):
        return .8


def synthetic_frame(index, source):
    return PoseFrame(timestamp_ms=index * 1000 // 30,
                     source_id=source, landmarks={
                         11: Landmark(.42,.2,.99), 12: Landmark(.58,.2,.99),
                         23: Landmark(.42,.5,.99), 24: Landmark(.58,.5,.99),
                     })


def test_private_aggregate_real_runner_contract_with_synthetic_video(tmp_path, monkeypatch):
    clip_a = tmp_path / "video_a.mp4"
    clip_b = tmp_path / "video_b.mp4"
    clip_a.write_bytes(b"fake publisher adl")
    clip_b.write_bytes(b"fake publisher fall")
    inventory = {
        "adl": {"path": clip_a, "publisher_class": "adl",
                "media_sha256": audit.sha256_file(clip_a)},
        "fall": {"path": clip_b, "publisher_class": "fall",
                 "media_sha256": audit.sha256_file(clip_b)},
    }
    monkeypatch.setattr(audit, "source_inventory", lambda root: inventory)
    monkeypatch.setattr(audit, "load_verified_linear_shadow",
                        lambda path: ResearchModel())
    monkeypatch.setattr(audit, "_private_output_path", lambda path: path)
    monkeypatch.setattr(audit, "_video_metadata",
                        lambda path: (271,30) if path == clip_a else (91,30))

    def collector(video, *, clip_id, model, max_frames, frame_consumer,
                  event_consumer):
        assert max_frames in (91,271)
        for i in range(max_frames):
            frame_consumer(synthetic_frame(i, clip_id))
        return [], {"frames_processed":max_frames,"candidate_events":0,
                    "invalid_pose_frames":0}
    task = tmp_path / "pose.task"
    task.write_bytes(b"fake")
    out = tmp_path / "private.json"
    report = audit.audit_shadow_sources(tmp_path, task, tmp_path / "frozen",
                                        out, collector=collector)
    assert report["categories"]["adl"]["videos_with_scored_windows"] == 1
    assert report["categories"]["adl"]["videos_any_shadow_candidate"] == 1
    assert report["categories"]["fall"]["videos_with_scored_windows"] == 0
    assert report["categories"]["fall"]["videos_nominally_shorter_than_8s"] == 1
    assert report["no_event_recall_false_alarm_hour_accuracy_or_alert_claim"] is True
    assert "fall_recalls" not in report
    assert str(clip_a) not in out.read_text()
    assert "pose_landmarks" not in out.read_text()
    assert json.loads(out.read_text()) == report
    with pytest.raises(FileExistsError):
        audit.audit_shadow_sources(tmp_path, task, tmp_path / "frozen",
                                  out, collector=collector)


def test_source_hash_modified_after_preflight_refused(tmp_path, monkeypatch):
    clip = tmp_path / "fake.mp4"
    clip.write_bytes(b"before")
    original_hash = audit.sha256_file(clip)
    monkeypatch.setattr(audit, "source_inventory", lambda root: {
        "c": {"path": clip, "publisher_class": "fall",
              "media_sha256": original_hash},
    })
    clip.write_bytes(b"after")
    monkeypatch.setattr(audit, "_private_output_path", lambda path: path)
    monkeypatch.setattr(audit, "load_verified_linear_shadow",
                        lambda path: ResearchModel())
    pose_task = tmp_path / "pose.task"
    pose_task.write_bytes(b"fake")
    with pytest.raises(ValueError, match="changed after"):
        audit.audit_shadow_sources(tmp_path, pose_task,
                                   tmp_path / "artifact", tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()
