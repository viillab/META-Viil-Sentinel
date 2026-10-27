"""Offline research-only persistent MediaPipe session across pinned video clips.

Uses one PoseLandmarker in VIDEO mode for eight complete public IKAR
segments. MediaPipe tracking persists across artificial video cuts, while a
NEW heuristic TemporalFallDetector is created per segment, preventing
cross-video fall evidence. This is NOT a live webcam benchmark and cannot
be used to authorize real emergency alerts, automatic human identification,
or production model/resize changes.
"""
from argparse import ArgumentParser
from collections import Counter
from contextlib import ExitStack
import json
from math import isfinite
from pathlib import Path
from time import perf_counter, process_time

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.edge_resource_profile import (
    MAX_EXPERIMENT_FRAMES, RSS_SAMPLE_EVERY, own_process_rss,
)
from sentinel_edge.ikar_domain_stress import (
    CATEGORIES, SELECTED_IDS, _private_root, sha256_file, validate_subset,
)
from sentinel_edge.pose_adapter import extract_torso_landmarks
from sentinel_edge.video_metadata import expected_frame_count, require_complete_decode
from sentinel_edge.window_export import _private_output_path

SESSION_SEGMENT_GAP_MS = 1_000
MAX_SOURCE_FPS = 120
POSE_MODEL_MAX_BYTES = 60 * 1024 * 1024


def session_timestamp_ms(*, last_ms: int, start_ms: int, frame: int,
                         fps: float) -> int:
    """Monotonic session timestamp from per-segment video FPS and gap."""
    if (type(last_ms) is not int or type(start_ms) is not int
            or type(frame) is not int or last_ms < -1 or start_ms < 0
            or frame < 0 or not isfinite(fps) or not 1 <= fps <= MAX_SOURCE_FPS):
        raise ValueError("Invalid session frame timestamp arguments")
    value = start_ms + int(frame * 1000 / fps)
    if value <= last_ms:
        raise ValueError("Non-monotonic persistent MediaPipe session timestamp")
    return value


def replay_persistent_session(
    clips: list[tuple[str, Path, int]], model: Path, *,
    cv2=None, mp=None, sample_rss=own_process_rss,
    wall_clock=perf_counter, cpu_clock=process_time,
) -> dict:
    """Measure REAL decode+pose+heuristic with one shared model per session.

    Caller verifies every source MP4 hash before entering this function.
    Frame/pixel/pose/event content is never retained across a callback.
    """
    if not clips or len(clips) > 8 or len({name for name, _, _ in clips}) != len(clips):
        raise ValueError("Expected up to eight unique staged video segments")
    if cv2 is None:
        import cv2
    if mp is None:
        import mediapipe as mp
    start_mem = sample_rss()
    if type(start_mem) is not int or start_mem <= 0:
        raise ValueError("Requires positive own-process RSS samples")
    peak_rss = start_mem
    total = Counter()
    category_totals = {name: Counter() for name in CATEGORIES}
    last_timestamp = -1
    frame_total = 0
    source_playback = 0.0
    before_cpu, before_wall = cpu_clock(), wall_clock()
    with ExitStack() as stack:
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model.resolve())),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=2,
        )
        landmarker = stack.enter_context(
            mp.tasks.vision.PoseLandmarker.create_from_options(options)
        )
        model_load_seconds = wall_clock() - before_wall
        if not isfinite(model_load_seconds) or model_load_seconds < 0:
            raise ValueError("Invalid model setup timing")
        peak_rss = max(peak_rss, sample_rss())
        for clip_id, video, category_frames in clips:
            if not isinstance(clip_id, str) or not clip_id:
                raise ValueError("Invalid private clip identifier")
            category = clip_id.rsplit("_", 1)[0]
            if category not in CATEGORIES:
                raise ValueError("Unexpected IKAR staged Fall category")
            if (type(category_frames) is not int
                    or not 1 <= category_frames <= MAX_EXPERIMENT_FRAMES):
                raise ValueError("Clip exceeds bounded segment replay")
            cap = cv2.VideoCapture(str(video))
            try:
                if not cap.isOpened():
                    raise ValueError("Cannot decode pinned staged video")
                declared = expected_frame_count(
                    cap, cv2, clip_id=clip_id, max_frames=MAX_EXPERIMENT_FRAMES
                )
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                if declared != category_frames or not 1 <= fps <= MAX_SOURCE_FPS:
                    raise ValueError("Source video metadata/frame preflight changed")
                source_playback += declared / fps
                # Deliberately isolate heuristic state at each video cut,
                # even though MediaPipe VIDEO tracking instance persists.
                heuristic = TemporalFallDetector()
                previous_segment_ts = last_timestamp
                segment_start_ms = last_timestamp + SESSION_SEGMENT_GAP_MS
                number = 0
                segment_events = 0
                segment_accepted = 0
                while number < declared + 1:
                    ok, bgr = cap.read()
                    if not ok:
                        break
                    if number >= declared:
                        raise ValueError("Extra video frame beyond declared count")
                    timestamp = session_timestamp_ms(
                        last_ms=last_timestamp, start_ms=segment_start_ms,
                        frame=number, fps=fps
                    )
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(image, timestamp)
                    landmarks = extract_torso_landmarks(result)
                    segment_accepted += bool(landmarks)
                    frame = PoseFrame(
                        timestamp_ms=timestamp, source_id=clip_id,
                        landmarks=landmarks,
                    )
                    event = heuristic.process(frame)
                    segment_events += event is not None
                    last_timestamp = timestamp
                    number += 1
                    frame_total += 1
                    if frame_total == 1 or frame_total % RSS_SAMPLE_EVERY == 0:
                        rss = sample_rss()
                        if type(rss) is not int or rss <= 0:
                            raise ValueError("Invalid sampled own-process RAM")
                        peak_rss = max(peak_rss, rss)
                require_complete_decode(
                    clip_id=clip_id, expected=declared, decoded=number
                )
                if previous_segment_ts >= segment_start_ms:
                    raise ValueError("Session video segment timestamp gap missing")
                category_totals[category]["segments"] += 1
                category_totals[category]["decoded_frames"] += number
                category_totals[category]["accepted_frames"] += segment_accepted
                category_totals[category]["candidate_events"] += segment_events
                total["segments"] += 1
                total["decoded_frames"] += number
                total["strict_accepted_frames"] += segment_accepted
                total["original_heuristic_candidate_events"] += segment_events
            finally:
                cap.release()
    wall_seconds, cpu_seconds = wall_clock() - before_wall, cpu_clock() - before_cpu
    peak_rss = max(peak_rss, sample_rss())
    if (total["segments"] != len(clips)
            or total["decoded_frames"] != sum(x[2] for x in clips)
            or total["decoded_frames"] != frame_total
            or not isfinite(wall_seconds) or wall_seconds <= 0
            or not isfinite(cpu_seconds) or cpu_seconds < 0
            or not isfinite(source_playback) or source_playback <= 0
            or type(peak_rss) is not int or peak_rss <= 0):
        raise ValueError("Persistent video session did not finish with valid totals")
    return {
        "videos": total["segments"],
        "fully_decoded_frames": total["decoded_frames"],
        "strict_accepted_torso_frames": total["strict_accepted_frames"],
        "candidate_events_original_heuristic": total[
            "original_heuristic_candidate_events"
        ],
        "wall_seconds_including_model_initialization": round(wall_seconds, 3),
        "model_load_wall_seconds": round(model_load_seconds, 3),
        "process_cpu_seconds": round(cpu_seconds, 3),
        "nominal_video_playback_seconds": round(source_playback, 3),
        "complete_replay_fps": round(frame_total / wall_seconds, 2),
        "realtime_replay_ratio": round(source_playback / wall_seconds, 3),
        "max_sampled_own_process_rss_mib": round(peak_rss / 1048576, 2),
        "category_counts": {c: dict(category_totals[c]) for c in CATEGORIES},
        "pose_landmarker_instances": 1,
        "temporal_heuristic_instances": len(clips),
        "artificial_cut_discontinuity_warning": True,
        "persisted_coordinates_frames_events_or_timestamps": False,
    }


def profile_ikar_session(
    root: Path, model: Path, output_path: Path, *, runner=replay_persistent_session
) -> dict:
    root = _private_root(root)
    output = _private_output_path(output_path)
    manifest = validate_subset(root)
    if (model.suffix.lower() != ".task" or not model.is_file()
            or not 1 <= model.stat().st_size <= POSE_MODEL_MAX_BYTES):
        raise ValueError("Original nonempty local pose task required")
    source = {
        (item["category"], item["publisher_action_id"]): item
        for item in manifest["selection"]
    }
    clips = []
    for category in CATEGORIES:
        for idx in SELECTED_IDS:
            row = source[(category, idx)]
            video = root / "selected" / category / "videos" / f"{category}_{idx}.mp4"
            if (sha256_file(video) != row["videos_sha256"]
                    or video.stat().st_size != row["videos_bytes"]):
                raise ValueError("Publisher video changed after manifest preflight")
            # FPS and frame budget are also re-verified within replay.
            from sentinel_edge.caucafall_curator import _video_metadata
            frames, _fps = _video_metadata(video)
            clips.append((f"{category}_{idx}", video, frames))
    result = runner(clips, model)
    if (result["videos"] != 8
            or result["fully_decoded_frames"] != sum(item[2] for item in clips)
            or result["pose_landmarker_instances"] != 1
            or result["temporal_heuristic_instances"] != 8):
        raise ValueError("Persistent model session invariants violated")
    report = {
        "version": 1,
        "source": "ikar_2026_8_source_verified_publisher_staged_fall_mp4",
        "publisher_archive_sha256": manifest["archive_sha256"],
        "official_pose_task_sha256": sha256_file(model),
        "benchmark_mode": "offline_persistent_pose_task_across_video_cuts",
        "original_strict_multi_person_abstention_unchanged": True,
        "new_fall_detector_at_each_video_boundary": True,
        "single_pose_landmarker_across_eight_video_cuts": True,
        "timestamps_monotonic_with_one_second_inter_segment_gap": True,
        "safety_event_accuracy_and_independent_onsets_unknown": True,
        "not_real_live_webcam_or_independent_safety_test": True,
        "no_PII_pose_video_event_timestamps_or_paths_persisted": True,
        "research_only": True,
        "measurements": result,
    }
    with output.open("x", encoding="utf8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
    return report


def main(argv=None) -> int:
    parser = ArgumentParser(description="Offline only persistent MediaPipe IKAR replay")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--pose-task", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--acknowledge-media-rights", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_media_rights and args.acknowledge_pose_privacy):
        parser.error("Local public media and temporary pose privacy acknowledgements required")
    try:
        report = profile_ikar_session(args.root, args.pose_task, args.report)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        parser.error("Persistent video replay refused: " + str(exc))
    print(json.dumps({
        "source": report["source"], "measurements": report["measurements"],
        "no_live_camera": True,
        "production_alert_changed": False,
    }, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
