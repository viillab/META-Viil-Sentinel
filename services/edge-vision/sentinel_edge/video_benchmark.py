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
from collections.abc import Callable
from sentinel_edge.contracts import FallCandidateEvent
from sentinel_edge.detector import DetectorConfig, TemporalFallDetector
from sentinel_edge.evaluation import (
    StreamingClipAccumulator, evaluate_clip_frames, load_manifest, local_source,
    summarize_clips, validate_clip,
)
from sentinel_edge.model_smoke import _file_sha256
from sentinel_edge.motion_features import summarize_motion_signals
from sentinel_edge.readiness import benchmark_readiness
from sentinel_edge.runner import process_capture
from sentinel_edge.frame_resize import validate_max_side
from sentinel_edge.signal_diagnostics import diagnose_pose_signals
from sentinel_edge.video_metadata import expected_frame_count, require_complete_decode

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
MAX_VIDEO_BYTES = 512 * 1024 * 1024  # No arbitrary multi-gigabyte uploads/processing.
MAX_FRAMES = 6000
MAX_TOTAL_FRAMES = 30_000


def collect_video_frames(
    video: Path, *, clip_id: str, model: Path, max_frames: int = MAX_FRAMES,
    cv2=None, mp=None,
    frame_consumer: Callable[[PoseFrame], None] | None = None,
    event_consumer: Callable[[FallCandidateEvent], None] | None = None,
    config: DetectorConfig | None = None,
    max_inference_side: int = 0,
    pose_reason_consumer: Callable[[str], None] | None = None,
) -> tuple[list[PoseFrame], dict]:
    """Process one file using an independent MediaPipe task instance.

    Test doubles for cv2/mp are permitted; production always loads the
    installed on-device runtime. Each clip resets pose tracking state.
    """
    if not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be 1..6000")
    validate_max_side(max_inference_side)
    if cv2 is None:
        import cv2
    if mp is None:
        import mediapipe as mp

    if (frame_consumer is None) != (event_consumer is None):
        raise ValueError("frame_consumer and event_consumer must be paired")
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
        diagnostic_options = (
            {"pose_reason_consumer": pose_reason_consumer}
            if pose_reason_consumer is not None else {}
        )
        stats = process_capture(
            capture, cv2=cv2, mp=mp, landmarker=landmark_model,
            webcam=False, source_id=clip_id, max_frames=max_frames + 1,
            display=False, output=StringIO(),
            on_frame=frame_consumer if frame_consumer is not None else frames.append,
            on_event=event_consumer,
            detector=TemporalFallDetector(config) if config is not None else None,
            **diagnostic_options,
            max_inference_side=max_inference_side,
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
    buffered_eval: bool = False, max_inference_side: int = 0,
    include_motion_study: bool = False,
) -> dict:
    if not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be 1..6000")
    validate_max_side(max_inference_side)
    if max_inference_side and collector is not collect_video_frames:
        raise ValueError("Resolution experiments require the real local video collector")
    resolved_clips, consent_declared = validate_video_manifest(manifest_path)
    if model.suffix.lower() != ".task" or not model.is_file() or model.stat().st_size == 0:
        raise ValueError("A non-empty, locally licensed .task model is required")

    outcomes = []
    total = 0
    no_pose = 0
    diagnostics = []
    motion_study = []
    for clip_id, video, label, onset in resolved_clips:
        remaining = MAX_TOTAL_FRAMES - total
        if remaining <= 0:
            raise ValueError("Evaluation exceeds total frame budget (30000)")
        # Each collector receives only the remaining budget. Oversized
        # clips are rejected instead of silently evaluating their start.
        limit = min(max_frames, remaining)
        # The production fast path consumes each PoseFrame and detector event
        # once in callbacks. It does not retain an entire clip in memory or
        # run the temporal detector a second time.
        streamed = (collector is collect_video_frames and not include_diagnostics
                    and not buffered_eval and not include_motion_study)
        if streamed:
            accumulator = StreamingClipAccumulator(config=config)
            frames, stats = collector(
                video, clip_id=clip_id, model=model, max_frames=limit,
                frame_consumer=accumulator.on_frame,
                event_consumer=accumulator.on_event, config=config,
                max_inference_side=max_inference_side,
            )
        else:
            # Injected collectors retain backwards-compatible test semantics.
            # Optional detailed diagnostics currently require the full pose list.
            if max_inference_side and collector is collect_video_frames:
                frames, stats = collector(
                    video, clip_id=clip_id, model=model, max_frames=limit,
                    max_inference_side=max_inference_side,
                )
            else:
                frames, stats = collector(
                    video, clip_id=clip_id, model=model, max_frames=limit
                )
        decoded = stats["frames_processed"]
        invalid = stats["invalid_pose_frames"]
        if (type(decoded) is not int or type(invalid) is not int
                or decoded < 1 or decoded > limit
                or invalid < 0 or invalid > decoded):
            raise ValueError(f"Clip {clip_id}: inconsistent collected-frame statistics")
        if streamed:
            if (frames or accumulator.analyzed != decoded
                    or len(accumulator.times) != stats["candidate_events"]):
                raise ValueError(f"Clip {clip_id}: inconsistent streamed frame/event counts")
            outcome = accumulator.finish(
                clip_id=clip_id, expected_fall=label, onset_ms=onset
            )
        else:
            if len(frames) != decoded:
                raise ValueError(f"Clip {clip_id}: inconsistent collected-frame statistics")
            outcome = evaluate_clip_frames(
                frames, clip_id=clip_id, expected_fall=label, onset_ms=onset, config=config
            )
            if include_diagnostics:
                diagnostics.append({
                    "clip_id": clip_id, **diagnose_pose_signals(frames, config),
                })
            if include_motion_study:
                motion_study.append({
                    "clip_id": clip_id, **summarize_motion_signals(frames),
                })
        total += decoded
        no_pose += invalid
        outcomes.append(outcome)
        del frames

    report = summarize_clips(
        outcomes,
        source="local consented video -> on-device MediaPipe -> in-memory pose -> clip scoring",
        permission_basis_declared=consent_declared,
    )
    report.update({
        "input_type": "video-files",
        "inference_max_side_px": max_inference_side,
        "experimental_resolution": max_inference_side != 0,
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
    if include_motion_study:
        report["experimental_motion_diagnostics"] = motion_study
        report["motion_study_notice"] = (
            "Untrained aggregate kinematic features only; NOT a new classifier "
            "or evidence of improved fall detection."
        )
    report["readiness_gate"] = benchmark_readiness(report)
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
    parser.add_argument("--profile-resource", action="store_true",
                        help="Opt-in own-process RAM/CPU sample; requires optional psutil")
    parser.add_argument("--max-inference-side", type=int, default=0,
                        help="EXPERIMENT ONLY: 0=original input, 256..4096 caps frame side")
    parser.add_argument("--buffered-eval", action="store_true",
                        help="Legacy buffered reference path for performance comparison")
    parser.add_argument("--motion-study", action="store_true",
                        help="RESEARCH ONLY: in-memory pose motion aggregate, no event changes")
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
            include_motion_study=args.motion_study,
            buffered_eval=args.buffered_eval,
            max_inference_side=args.max_inference_side,
            config=DetectorConfig(
                min_hip_descent=args.min_hip_descent,
                horizontal_min_angle_deg=args.horizontal_min_angle_deg,
                horizontal_hold_ms=args.horizontal_hold_ms,
            )
        )
    except (ValueError, OSError, ImportError, json.JSONDecodeError) as exc:
        parser.error(f"Evaluation failed: {exc}")
    if args.profile_resource:
        try:
            import psutil
        except ImportError:
            result["resource_profile"] = {"available": False,
                                          "reason": "optional psutil not installed"}
        else:
            process = psutil.Process()
            memory = process.memory_info()
            cpu = process.cpu_times()
            result["resource_profile"] = {
                "available": True,
                "peak_working_set_mb": round(getattr(memory, "peak_wset", memory.rss)
                                             / 1048576, 2),
                "cpu_seconds": round(cpu.user + cpu.system, 3),
                "measurement": "inside video benchmark process; native RAM included",
            }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
