"""Privacy-minimal actual Edge replay CPU/RAM/FPS profiling (RESEARCH ONLY).

Profiles the unchanged MediaPipe num_poses=2 video collector and unchanged
original fall-candidate heuristic. Strict source SHA pin and complete decode
required. Never retains or serializes frames, landmarks, events, or video paths
in the benchmark report. Offline, no camera and no production modifications.

Wall FPS includes model initialization, video decoding, pose conversion and
heuristic. RSS is *sampled* process memory, not a provable instantaneous peak.
Experimental 512px resizing may change pose availability or heuristic events:
no claim that it is deployment safe or an optimized setting.
"""
from argparse import ArgumentParser
from collections import Counter
import json
from math import isfinite
from pathlib import Path
from statistics import median
from time import perf_counter, process_time

from sentinel_edge.frame_resize import validate_max_side
from sentinel_edge.ikar_domain_stress import (
    CATEGORIES, SELECTED_IDS, _private_root, sha256_file, validate_subset,
)
from sentinel_edge.caucafall_curator import _video_metadata
from sentinel_edge.video_benchmark import collect_video_frames
from sentinel_edge.window_export import _private_output_path

RESOLUTIONS = (0, 512)
MAX_EXPERIMENT_FRAMES = 2_000
RSS_SAMPLE_EVERY = 16


def own_process_rss() -> int:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("psutil is required only for offline RAM profiling") from exc
    return int(psutil.Process().memory_info().rss)


def profile_clip(video: Path, pose_task: Path, *, clip_id: str,
                 expected_frames: int, source_fps: float,
                 max_side: int, collector=collect_video_frames,
                 wall_clock=perf_counter, cpu_clock=process_time,
                 sample_rss=own_process_rss) -> dict:
    """Actually consume each frame and event exactly once, retaining none."""
    validate_max_side(max_side)
    if (not 1 <= expected_frames <= MAX_EXPERIMENT_FRAMES
            or not 0 < source_fps <= 120):
        raise ValueError("Invalid source frame timing or budget")
    rss_before = sample_rss()
    if type(rss_before) is not int or rss_before <= 0:
        raise ValueError("RSS sampler must return positive bytes")
    peak = rss_before
    counters = Counter()
    def on_frame(frame):
        nonlocal peak
        counters["frames"] += 1
        counters["strict_pose_frames"] += bool(frame.landmarks)
        if counters["frames"] == 1 or counters["frames"] % RSS_SAMPLE_EVERY == 0:
            value = sample_rss()
            if type(value) is not int or value <= 0:
                raise ValueError("Invalid process RSS")
            peak = max(peak, value)
    def on_event(_event):
        counters["events"] += 1

    start_wall, start_cpu = wall_clock(), cpu_clock()
    frames, stats = collector(
        video, clip_id=clip_id, model=pose_task,
        max_frames=expected_frames,
        frame_consumer=on_frame, event_consumer=on_event,
        max_inference_side=max_side,
    )
    cpu_seconds = cpu_clock() - start_cpu
    wall_seconds = wall_clock() - start_wall
    peak = max(peak, sample_rss())
    if (frames or type(stats.get("frames_processed")) is not int
            or type(stats.get("invalid_pose_frames")) is not int
            or type(stats.get("candidate_events")) is not int
            or counters["frames"] != expected_frames
            or stats["frames_processed"] != expected_frames
            or stats["invalid_pose_frames"] !=
            expected_frames - counters["strict_pose_frames"]
            or stats["candidate_events"] != counters["events"]
            or not isfinite(wall_seconds) or not isfinite(cpu_seconds)
            or wall_seconds <= 0 or cpu_seconds < 0
            or peak <= 0):
        raise ValueError("Incomplete decode, timing, strict pose or event parity mismatch")
    playback_seconds = expected_frames / source_fps
    return {
        "frames": expected_frames,
        "strict_pose_frames": counters["strict_pose_frames"],
        "candidate_events": counters["events"],
        "wall_seconds": wall_seconds,
        "process_cpu_seconds": cpu_seconds,
        "source_playback_seconds": playback_seconds,
        "throughput_fps": expected_frames / wall_seconds,
        "replay_realtime_ratio": playback_seconds / wall_seconds,
        "rss_start_bytes": rss_before,
        "rss_peak_sampled_bytes": peak,
    }


def aggregate_profiles(clips: list[dict]) -> dict:
    if not clips:
        raise ValueError("No resource profiles")
    if any(
        type(item.get("frames")) is not int or item["frames"] <= 0
        or type(item.get("strict_pose_frames")) is not int
        or not 0 <= item["strict_pose_frames"] <= item["frames"]
        or type(item.get("candidate_events")) is not int
        or item["candidate_events"] < 0
        or any(type(item.get(key)) not in (float, int)
               or not isfinite(item[key]) or item[key] <= 0
               for key in ("wall_seconds", "source_playback_seconds", "throughput_fps"))
        or type(item.get("process_cpu_seconds")) not in (float, int)
        or not isfinite(item["process_cpu_seconds"])
        or item["process_cpu_seconds"] < 0
        or type(item.get("rss_peak_sampled_bytes")) is not int
        or item["rss_peak_sampled_bytes"] <= 0
        for item in clips
    ):
        raise ValueError("Resource stats violate timing/frame contracts")
    wall = sum(x["wall_seconds"] for x in clips)
    media = sum(x["source_playback_seconds"] for x in clips)
    decoded = sum(x["frames"] for x in clips)
    result = {
        "clips": len(clips),
        "frames": decoded,
        "strict_pose_frames": sum(x["strict_pose_frames"] for x in clips),
        "candidate_events": sum(x["candidate_events"] for x in clips),
        "total_wall_seconds": round(wall, 3),
        "total_process_cpu_seconds": round(
            sum(x["process_cpu_seconds"] for x in clips), 3
        ),
        "nominal_source_playback_seconds": round(media, 3),
        "actual_decode_pose_pipeline_fps": round(decoded / wall, 2),
        "replay_speed_multiple_of_video_realtime": round(media / wall, 3),
        "median_per_clip_throughput_fps": round(
            median(x["throughput_fps"] for x in clips), 2
        ),
        "max_sampled_own_process_rss_mib": round(
            max(x["rss_peak_sampled_bytes"] for x in clips) / (1024 ** 2), 2
        ),
        "rss_not_proven_instantaneous_peak": True,
    }
    return result


def profile_frozen_ikar(root: Path, pose_task: Path, report: Path, *,
                        collector=collect_video_frames,
                        wall_clock=perf_counter, cpu_clock=process_time,
                        sample_rss=own_process_rss) -> dict:
    """Replay only SOURCE-PINNED 8 MP4s; do not infer Fall quality."""
    root = _private_root(root)
    output = _private_output_path(report)
    pinned = validate_subset(root)
    if (not pose_task.is_file() or pose_task.suffix.lower() != ".task"
            or not 1 <= pose_task.stat().st_size <= 60 * 1024 * 1024):
        raise ValueError("Real local official MediaPipe Lite task required")
    pose_sha = sha256_file(pose_task)
    datasets = {}
    for max_side in RESOLUTIONS:
        by_category = {}
        for category in CATEGORIES:
            outcomes = []
            for index in SELECTED_IDS:
                path = (root / "selected" / category / "videos"
                        / f"{category}_{index}.mp4")
                expected, fps = _video_metadata(path)
                if expected > MAX_EXPERIMENT_FRAMES:
                    raise ValueError("IKAR clip exceeds bounded resource-test budget")
                results = profile_clip(
                    path, pose_task, clip_id=f"{category}_{index}",
                    expected_frames=expected, source_fps=fps,
                    max_side=max_side, collector=collector,
                    wall_clock=wall_clock, cpu_clock=cpu_clock,
                    sample_rss=sample_rss,
                )
                outcomes.append(results)
            by_category[category] = aggregate_profiles(outcomes)
        # Count ALL 8 clips for accurate weighting and end-to-end totals.
        total_frames = sum(x["frames"] for x in by_category.values())
        total_wall = sum(x["total_wall_seconds"] for x in by_category.values())
        total_cpu = sum(x["total_process_cpu_seconds"] for x in by_category.values())
        total_playback = sum(x["nominal_source_playback_seconds"]
                             for x in by_category.values())
        datasets[str(max_side)] = {
            "inference_max_side_px": max_side,
            "experimental_inference_resize": max_side != 0,
            "videos": sum(x["clips"] for x in by_category.values()),
            "frames": total_frames,
            "strict_pose_frames": sum(x["strict_pose_frames"]
                                       for x in by_category.values()),
            "candidate_events_original_heuristic": sum(
                x["candidate_events"] for x in by_category.values()
            ),
            "sum_pipeline_wall_seconds": round(total_wall, 3),
            "sum_process_cpu_seconds": round(total_cpu, 3),
            "nominal_video_playback_seconds": round(total_playback, 3),
            "aggregate_pipeline_throughput_fps": round(
                total_frames / total_wall, 2
            ),
            "aggregate_replay_realtime_ratio": round(
                total_playback / total_wall, 3
            ),
            "max_sampled_own_process_rss_mib": max(
                x["max_sampled_own_process_rss_mib"]
                for x in by_category.values()
            ),
            "by_publisher_staged_fall_type": by_category,
        }
        if datasets[str(max_side)]["videos"] != 8:
            raise ValueError("Frozen IKAR replay must include all 8 videos")
    report_data = {
        "version": 1,
        "source": "ikar_2026_source_frozen_8_public_staged_fall_only",
        "official_source_archive_sha256": pinned["archive_sha256"],
        "pose_task_sha256": pose_sha,
        "research_only": True,
        "no_frames_pose_or_timestamps_persisted": True,
        "source_subject_ids_not_reviewed": True,
        "no_ADL_negatives_or_human_reviewed_fall_onsets": True,
        "not_a_false_alarms_per_hour_experiment": True,
        "experimental_resize_not_production_setting": True,
        "memory_measures_own_process_rss_sampled_in_callbacks": True,
        "model_initialization_and_video_decode_included_in_wall_time": True,
        "results_in_execution_order_native_then_512": True,
        "not_real_camera_live_stream_benchmark": True,
        "variants": datasets,
    }
    with output.open("x", encoding="utf8") as out:
        json.dump(report_data, out, indent=2, allow_nan=False)
    return report_data


def main(argv=None) -> int:
    parser = ArgumentParser(description="Research-only real MediaPipe CPU/RAM replay profile")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--acknowledge-media-rights", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_media_rights or not args.acknowledge_pose_privacy:
        parser.error("Explicit media rights and sensitive pose processing consent required")
    try:
        result = profile_frozen_ikar(args.root, args.pose_task, args.report)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        parser.error("Offline resources profile refused: " + str(exc))
    print(json.dumps({
        "source": result["source"], "variants": result["variants"],
        "private_report": True, "production_alert_path_modified": False,
    }, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
