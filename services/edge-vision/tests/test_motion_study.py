"""Experimental motion study produces only aggregates and preserves decisions."""
import json
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.motion_features import summarize_motion_signals
from sentinel_edge.video_benchmark import evaluate_video_manifest


def pose(ts, sy=0.2, hy=0.5):
    return PoseFrame(timestamp_ms=ts, source_id="synthetic", landmarks={
        11: Landmark(0.45, sy), 12: Landmark(0.55, sy),
        23: Landmark(0.45, hy), 24: Landmark(0.55, hy),
    })


def test_aggregate_does_not_expose_raw_keypoints_source_or_person():
    frames = [pose(0), pose(100, 0.35, 0.62), pose(200, 0.4, 0.8)]
    report = summarize_motion_signals(frames)
    assert report["analyzed_frames"] == 3
    assert report["pose_observed_frames"] == 3
    assert report["max_abs_hip_speed_per_s_clipped"] > 0
    assert report["not_a_fall_prediction"] is True
    assert report["trained_model"] is False
    for forbidden in ("source_id", "landmark", "image", "frames_raw", "patient"):
        assert forbidden not in json.dumps(report)


def test_empty_motion_stream_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        summarize_motion_signals([])


def test_motion_study_does_not_change_candidate_counts(tmp_path):
    sample = tmp_path / "synthetic.avi"
    sample.write_bytes(b"not video; injected frames only")
    task = tmp_path / "fake.task"
    task.write_bytes(b"fake")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1, "permission_basis": "Synthetic numerical data",
        "clips": [{"id": "synthetic", "video": "synthetic.avi",
                   "expected_fall": False}],
    }), encoding="utf-8")

    def collector(video: Path, *, clip_id, model, max_frames):
        del video, clip_id, model, max_frames
        frames = [pose(0), pose(100, 0.3, 0.6), pose(200, 0.4, 0.7)]
        return frames, {"frames_processed": len(frames),
                        "invalid_pose_frames": 0, "candidate_events": 0}

    control = evaluate_video_manifest(manifest, task, collector=collector)
    experimental = evaluate_video_manifest(
        manifest, task, collector=collector, include_motion_study=True
    )
    assert control["clips"] == experimental["clips"]
    assert control["metrics"] == experimental["metrics"]
    assert control["readiness_gate"] == experimental["readiness_gate"]
    assert "experimental_motion_diagnostics" not in control
    assert experimental["experimental_motion_diagnostics"][0]["analyzed_frames"] == 3
    assert not list(tmp_path.glob("*.pose.jsonl"))
