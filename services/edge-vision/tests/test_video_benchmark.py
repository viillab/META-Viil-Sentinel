"""Local benchmark tests; no actual human clips, camera activation or uploads."""
import json
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.video_benchmark import (
    evaluate_video_manifest, validate_video_manifest,
)


def write_manifest(tmp_path, *, clips=None):
    video = tmp_path / "empty.avi"
    video.write_bytes(b"placeholder binary, NOT an actual video")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "permission_basis": "Synthetic test video only; no human subjects",
        "clips": clips or [
            {"id": "blank-negative", "video": "empty.avi", "expected_fall": False}
        ],
    }), encoding="utf-8")
    return manifest, video


def make_pose(t, prone=False):
    if prone:
        sx, sy, hx, hy = 0.23, 0.78, 0.57, 0.78
    else:
        sx, sy, hx, hy = 0.5, 0.25, 0.5, 0.53
    return PoseFrame(
        timestamp_ms=t, source_id="fictional",
        landmarks={
            11: Landmark(sx - .045, sy, .98),
            12: Landmark(sx + .045, sy, .98),
            23: Landmark(hx - .05, hy, .98),
            24: Landmark(hx + .05, hy, .98),
        },
    )


def test_in_memory_manifest_evaluation_without_writing_pose_trace(tmp_path):
    manifest, _ = write_manifest(tmp_path, clips=[
        {"id": "demo-fall", "video": "empty.avi", "expected_fall": True, "onset_ms": 300},
        {"id": "demo-sit", "video": "empty.avi", "expected_fall": False},
    ])
    fake_model = tmp_path / "model.task"
    fake_model.write_bytes(b"only fake for injected synthetic collector")

    def fake_collect(video, *, clip_id, model, max_frames):
        assert video.is_file()
        assert model == fake_model and max_frames == 6000
        frames = [make_pose(t) for t in (0, 100, 200)]
        frames += [
            make_pose(t, prone=(clip_id == "demo-fall"))
            for t in (300, 500, 700, 850)
        ]
        return frames, {"frames_processed": len(frames),
                        "invalid_pose_frames": 0, "candidate_events": 1}

    report = evaluate_video_manifest(manifest, fake_model, collector=fake_collect)
    assert report["metrics"]["true_positive"] == 1
    assert report["metrics"]["true_negative"] == 1
    assert report["total_video_frames"] == 14
    assert report["pose_frame_availability_rate"] == 1
    assert report["raw_frames_written_to_disk"] is False
    assert report["pose_frames_written_to_disk"] is False
    assert report["remote_inference"] is False
    assert report["fall_accuracy_established"] is False
    assert not list(tmp_path.glob("*.pose.jsonl"))


def test_no_permission_or_path_traversal_allowed(tmp_path):
    manifest, _ = write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["permission_basis"] = ""
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="consent or license"):
        validate_video_manifest(manifest)
    payload["permission_basis"] = "synthetic"
    payload["clips"][0]["video"] = "../outside.avi"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="relative"):
        validate_video_manifest(manifest)


@pytest.mark.parametrize("video", [
    "0", "http://example.org/human.mp4", "secret.jsonl", "C:/private/human.avi",
])
def test_unsupported_video_sources_rejected(tmp_path, video):
    manifest, _ = write_manifest(tmp_path, clips=[
        {"id": "pseudonymous", "video": video, "expected_fall": False}
    ])
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_video_manifest(manifest)


def test_duplicate_ids_and_manifest_extra_fields_rejected(tmp_path):
    manifest, _ = write_manifest(tmp_path, clips=[
        {"id": "duplicate", "video": "empty.avi", "expected_fall": False},
        {"id": "duplicate", "video": "empty.avi", "expected_fall": False},
    ])
    with pytest.raises(ValueError, match="unique"):
        validate_video_manifest(manifest)
    payload = json.loads(manifest.read_text())
    payload["clips"] = [{"id": "okay", "video": "empty.avi",
                         "expected_fall": False, "notes": "potential real patient"}]
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="fields"):
        validate_video_manifest(manifest)


def test_total_and_per_clip_frame_limits(tmp_path):
    manifest, _ = write_manifest(tmp_path)
    fake_model = tmp_path / "model.task"
    fake_model.write_bytes(b"fake")
    with pytest.raises(ValueError, match="max_frames"):
        evaluate_video_manifest(manifest, fake_model, max_frames=7000)
    def too_long(*args, **kwargs):
        raise ValueError("Clip blank-negative: exceeds maximum of 3 frames")
    with pytest.raises(ValueError, match="maximum"):
        evaluate_video_manifest(manifest, fake_model, max_frames=3, collector=too_long)


def test_positive_onset_outside_trace_does_not_count(tmp_path):
    manifest, _ = write_manifest(tmp_path, clips=[
        {"id": "late-annotation", "video": "empty.avi",
         "expected_fall": True, "onset_ms": 10000}
    ])
    fake_model = tmp_path / "model.task"
    fake_model.write_bytes(b"fake")
    def short(*args, **kwargs):
        frames = [make_pose(t) for t in (0, 100, 200)]
        return frames, {"frames_processed": 3, "invalid_pose_frames": 0, "candidate_events": 0}
    with pytest.raises(ValueError, match="outside the observed trace"):
        evaluate_video_manifest(manifest, fake_model, collector=short)


def test_actual_mediapipe_decodes_a_generated_no_person_video(tmp_path):
    """Optional *real* video/MediaPipe runtime, runs when locally installed model exists."""
    model = Path(__file__).resolve().parents[3] / "models" / "pose_landmarker_lite.task"
    if not model.is_file():
        pytest.skip("Official local task model not present in CI")
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    pytest.importorskip("mediapipe")

    video = tmp_path / "empty.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 160))
    if not writer.isOpened():
        pytest.skip("Local OpenCV build lacks MJPG encoder")
    try:
        for _ in range(12):
            writer.write(np.zeros((160, 160, 3), dtype=np.uint8))
    finally:
        writer.release()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "permission_basis": "Generated empty pixels with no human subject",
        "clips": [{"id": "blank-negative", "video": "empty.avi", "expected_fall": False}],
    }), encoding="utf-8")
    report = evaluate_video_manifest(manifest, model, max_frames=20)
    assert report["total_video_frames"] == 12
    assert report["num_clips"] == 1
    assert report["metrics"]["true_negative"] == 1
    assert report["unavailable_pose_frames"] == 12
    buffered = evaluate_video_manifest(manifest, model, max_frames=20, buffered_eval=True)
    assert buffered == report  # Real model, exactly identical events/metrics.
    assert not list(tmp_path.glob("*.pose.jsonl"))
