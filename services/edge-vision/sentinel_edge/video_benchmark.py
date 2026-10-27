"""Privacy-minimized, bounded offline evaluation of consented local video clips.

Each video is decoded only on this computer; Pose Landmarker runs locally;
derived pose frames live temporarily in RAM and are never written to disk.
Only pseudonymous clip-level metrics are printed. No webcam inputs accepted.
"""
from argparse import ArgumentParser
from contextlib import ExitStack
from io import StringIO
import json
from pathlib import Path

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.detector import DetectorConfig
from sentinel_edge.evaluation import (
    evaluate_clip_frames, load_manifest, local_source, summarize_clips, validate_clip,
)
from sentinel_edge.model_smoke import _file_sha256
from sentinel_edge.runner import process_capture
from sentinel_edge.signal_diagnostics import diagnose_pose_signals
from sentinel_edge.video_metadata import expected_frame_count, require_complete_decode

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
MAX_VIDEO_BYTES = 512 * 1024 * 1024  # No arbitrary multi-gigabyte uploads/processing.
MAX_FRAMES = 6000
MAX_TOTAL_FRAMES = 30_000


def collect_video_frames(
    video: Path, *, clip_id: str, model: Path, max_frames: int = MAX_FRAMES,
    cv2=None, mp=None,
) -> tuple[list[PoseFrame], dict]:
    """Process one file using an independent MediaPipe task instance.

    Test doubles for cv2/mp are permitted; production always loads the
    installed on-device runtime. Each clip resets pose tracking state.
    """
    if not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be 1..6000")
    if cv2 is None:
        import cv2
    if mp is None:
        import mediapipe as mp

    frames: list[PoseFrame] = []
    with ExitStack() as stack:
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Clip {clip_id}: cannot decode video")
        stack.callback(capture.release)
        # Fail closed on missing timing/count metadata or an excessive
        # declared clip length before loading a large inference model.
        declared_frames = expected_frame_count(
            capture, cv2, clip_id=clip_id, max_frames=max_frames
        )
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model.resolve())),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=2,
        )
        landmark_model = stack.enter_context(
            mp.tasks.vision.PoseLandmarker.create_from_options(options)
        )
        # Read one extra frame so we don't silently evaluate only the start
        # of an overlong video and present it as a complete clip.
        stats = process_capture(
            capture, cv2=cv2, mp=mp, landmarker=landmark_model,
            webcam=False, source_id=clip_id, max_frames=max_frames + 1,
            display=False, output=StringIO(), on_frame=frames.append,
        )
    require_complete_decode(
        clip_id=clip_id, expected=declared_frames, decoded=stats.frames_processed
    )
    if stats.frames_processed > max_frames:
        raise ValueError(f"Clip {clip_id}: exceeds maximum of {max_frames} frames")
    return frames, {
        "frames_processed": stats.frames_processed,
        "invalid_pose_frames": stats.invalid_pose_frames,
        "candidate_events": stats.candidate_events,
    }


def validate_video_manifest(manifest_path: Path) -> tuple[list[tuple], bool]:
    """Validate *every* clip and path before opening a model or a video."""
    manifest_path = manifest_path.resolve(strict=True)
    clips, permission = load_manifest(manifest_path)
    root = manifest_path.parent
    seen_ids: set[str] = set()
    resolved_clips: list[tuple] = []
    for item in clips:
        clip_id, filename, label, onset = validate_clip(
            item, seen_ids, path_key="video", suffixes=VIDEO_SUFFIXES
        )
        video = local_source(root, filename)
        if video.stat().st_size == 0 or video.stat().st_size > MAX_VIDEO_BYTES:
            raise ValueError(f"Clip {clip_id}: video must be between 1 byte and 512 MiB")
        resolved_clips.append((clip_id, video, label, onset))
    return resolved_clips, bool(permission)


def evaluate_video_manifest(
    manifest_path: Path, model: Path, *,
    max_frames: int = MAX_FRAMES, config: DetectorConfig | None = None,
    collector=collect_video_frames, include_diagnostics: bool = False,
) -> dict:
    if not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be 1..6000")
    resolved_clips, consent_declared = validate_video_manifest(manifest_path)
    if model.suffix.lower() != ".task" or not model.is_file() or model.stat().st_size == 0:
        raise ValueError("A non-empty, locally licensed .task model is required")

    outcomes = []
    total = 0
    no_pose = 0
    diagnostics = []
    for clip_id, video, label, onset in resolved_clips:
        remaining = MAX_TOTAL_FRAMES - total
        if remaining <= 0:
            raise ValueError("Evaluation exceeds total frame budget (30000)")
        # Each collector receives only the remaining budget. Oversized
        # clips are rejected instead of silently evaluating their start.
        limit = min(max_frames, remaining)
        frames, stats = collector(video, clip_id=clip_id, model=model, max_frames=limit)
        decoded = stats["frames_processed"]
        invalid = stats["invalid_pose_frames"]
        if (type(decoded) is not int or type(invalid) is not int
                or decoded < 1 or decoded > limit
                or invalid < 0 or invalid > decoded or len(frames) != decoded):
            raise ValueError(f"Clip {clip_id}: inconsistent collected-frame statistics")
        total += decoded
        no_pose += invalid
        outcomes.append(evaluate_clip_frames(
            frames, clip_id=clip_id, expected_fall=label, onset_ms=onset, config=config,
        ))
        if include_diagnostics:
            diagnostics.append({
                "clip_id": clip_id,
                **diagnose_pose_signals(frames, config),
            })
        # RAM containing derived landmark coordinates is released per clip.
        del frames

    report = summarize_clips(
        outcomes,
        source="local consented video -> on-device MediaPipe -> in-memory pose -> clip scoring",
        permission_basis_declared=consent_declared,
    )
    report.update({
        "input_type": "video-files",
        "pose_frames_written_to_disk": False,
        "raw_frames_written_to_disk": False,
        "remote_inference": False,
        "media_or_pose_uploaded": False,
        "model_sha256": _file_sha256(model),
        "total_video_frames": total,
        "unavailable_pose_frames": no_pose,
        "pose_frame_availability_rate": round((total - no_pose) / total, 4),
        "fall_accuracy_established": False,
        "notice": "Metrics describe this labeled video set only, not clinical or deployed performance.",
    })
    if include_diagnostics:
        report["aggregate_signal_diagnostics"] = diagnostics
        report["diagnostic_note"] = (
            "Gate counts are descriptive only, not ground-truth onset detection or "
            "proof of the cause of missed events."
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(
        description="On-device MediaPipe clip-level fall candidate evaluation (no uploads)"
    )
    parser.add_argument("--manifest", type=Path, required=True,
                        help="JSON manifest beside consented local videos; never a camera ID")
    parser.add_argument("--model", type=Path, required=True, help="Local Pose Landmarker .task")
    parser.add_argument("--confirm-consent", action="store_true",
                        help="Confirm authorization to analyze all video subjects and files")
    parser.add_argument("--max-frames", type=int, default=MAX_FRAMES)
    parser.add_argument("--signal-diagnostics", action="store_true",
                        help="Include aggregate-only per-clip detector gate counts")
    parser.add_argument("--min-hip-descent", type=float, default=0.13)
    parser.add_argument("--horizontal-min-angle-deg", type=float, default=56.0)
    parser.add_argument("--horizontal-hold-ms", type=int, default=450)
    args = parser.parse_args(argv)
    if not args.confirm_consent:
        parser.error("--confirm-consent is required for video evaluation")
    try:
        result = evaluate_video_manifest(
            args.manifest, args.model, max_frames=args.max_frames,
            include_diagnostics=args.signal_diagnostics,
            config=DetectorConfig(
                min_hip_descent=args.min_hip_descent,
                horizontal_min_angle_deg=args.horizontal_min_angle_deg,
                horizontal_hold_ms=args.horizontal_hold_ms,
            )
        )
    except (ValueError, OSError, ImportError, json.JSONDecodeError) as exc:
        parser.error(f"Evaluation failed: {exc}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
