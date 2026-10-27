"""Frame-budget controls are enforced before processing excess clips."""
import json

import pytest

from sentinel_edge.contracts import PoseFrame
import sentinel_edge.video_benchmark as benchmark


def fixture_manifest(tmp_path, clip_count=2):
    video = tmp_path / "blank.avi"
    video.write_bytes(b"synthetic-only")
    model = tmp_path / "placeholder.task"
    model.write_bytes(b"fake, not used by synthetic collector")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "permission_basis": "No real humans — fake collector",
        "clips": [
            {"id": f"synthetic-{i}", "video": "blank.avi", "expected_fall": False}
            for i in range(clip_count)
        ],
    }), encoding="utf-8")
    return manifest, model


def test_remaining_total_budget_applied_before_next_clip(tmp_path, monkeypatch):
    manifest, model = fixture_manifest(tmp_path, clip_count=2)
    monkeypatch.setattr(benchmark, "MAX_TOTAL_FRAMES", 5)
    requested = []

    def collect(video, *, clip_id, model, max_frames):
        requested.append(max_frames)
        if max_frames < 3:
            raise ValueError("declared frames exceeds maximum: refusing truncation")
        frames = [PoseFrame(timestamp_ms=t * 100, landmarks={}) for t in range(3)]
        return frames, {"frames_processed": 3, "invalid_pose_frames": 3,
                        "candidate_events": 0}

    with pytest.raises(ValueError, match="refusing truncation"):
        benchmark.evaluate_video_manifest(manifest, model, max_frames=4, collector=collect)
    assert requested == [4, 2]


@pytest.mark.parametrize("invalid", [
    {"frames_processed": 9, "invalid_pose_frames": 0},
    {"frames_processed": 3, "invalid_pose_frames": 4},
    {"frames_processed": -1, "invalid_pose_frames": 0},
    {"frames_processed": 3.0, "invalid_pose_frames": 0},
])
def test_collector_integrity_violation_cannot_produce_metrics(tmp_path, invalid):
    manifest, model = fixture_manifest(tmp_path)
    def collect(video, *, clip_id, model, max_frames):
        frames = [PoseFrame(timestamp_ms=t*100, landmarks={}) for t in range(3)]
        return frames, invalid

    with pytest.raises(ValueError, match="inconsistent collected-frame statistics"):
        benchmark.evaluate_video_manifest(manifest, model, collector=collect)
