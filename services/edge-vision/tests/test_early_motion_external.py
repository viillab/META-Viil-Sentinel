"""Fictional source-only tests of early motion aggregate audit and tamper failure."""
import json

import pytest

from sentinel_edge import early_motion_external as audit
from sentinel_edge.contracts import Landmark, PoseFrame


def pose(time_ms, source, delta=0):
    hip = .40 + delta
    return PoseFrame(timestamp_ms=time_ms, source_id=source, landmarks={
        11: Landmark(.45, hip-.22, .99),
        12: Landmark(.55, hip-.22, .99),
        23: Landmark(.45, hip, .99),
        24: Landmark(.55, hip, .99),
    })


def test_audit_never_exports_clips_frames_identities_or_event_times(tmp_path, monkeypatch):
    adl = tmp_path / "private_adl.mp4"
    falling = tmp_path / "private_fall.mp4"
    for path, value in ((adl,b"adl"),(falling,b"fall")):
        path.write_bytes(value)
    inventory = {
        "a": {"path": adl, "publisher_class": "adl",
              "media_sha256": audit.sha256_file(adl)},
        "f": {"path": falling, "publisher_class": "fall",
              "media_sha256": audit.sha256_file(falling)},
    }
    monkeypatch.setattr(audit,"source_inventory",lambda root: inventory)
    monkeypatch.setattr(audit,"_private_output_path",lambda path: path)
    monkeypatch.setattr(audit,"_video_metadata",lambda path: (18,10.))
    task = tmp_path/"pose.task"
    task.write_bytes(b"model")
    def collector(path, *, clip_id, model, max_frames,
                  frame_consumer, event_consumer):
        assert max_frames == 18
        assert model == task
        for i in range(18):
            delta = .027 * max(i-5,0) if clip_id == "f" else 0
            frame_consumer(pose(100*i, clip_id, delta))
        return [],{"frames_processed":18,"invalid_pose_frames":0,
                  "candidate_events":0}
    report_path=tmp_path/"report.json"
    report=audit.audit_early_motion(tmp_path,task,report_path,collector=collector)
    assert report["categories"]["adl"]["provisional_motion_proposals"] == 0
    assert report["categories"]["fall"]["provisional_motion_proposals"] >= 1
    assert report["not_trained_ai_model"]
    assert report["no_human_event_onsets_or_subject_IDs_reviewed"]
    assert report["original_heuristic_unchanged_and_not_triggered_by_motion_probe"]
    serialized=report_path.read_text(encoding="utf8")
    assert str(adl) not in serialized
    assert "private_fall" not in serialized
    assert "source_id" not in serialized
    assert "timestamp_ms" not in serialized
    assert json.loads(serialized)==report
    with pytest.raises(FileExistsError):
        audit.audit_early_motion(tmp_path,task,report_path,collector=collector)


def test_rehash_detects_tampered_video_before_processing(tmp_path,monkeypatch):
    path=tmp_path/"fake.mp4"
    path.write_bytes(b"before")
    digest=audit.sha256_file(path)
    monkeypatch.setattr(audit,"source_inventory",lambda root: {
        "a":{"path":path,"publisher_class":"adl","media_sha256":digest},
    })
    monkeypatch.setattr(audit,"_private_output_path",lambda path:path)
    path.write_bytes(b"after")
    task=tmp_path/"pose.task"
    task.write_bytes(b"model")
    with pytest.raises(ValueError, match="drifted"):
        audit.audit_early_motion(tmp_path,task,tmp_path/"out.json",
                                 collector=lambda *args,**kwargs:None)
    assert not (tmp_path/"out.json").exists()
