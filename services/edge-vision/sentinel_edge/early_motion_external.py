"""Private fixed-source research audit for causal motion-proposal counts.

The probe is deliberately NOT a learned AI model and does NOT emit
incident records, trigger alarms, or imply a validated accuracy value.
Publisher labels are exposed for prior experiments; no threshold tuning.
"""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path

from sentinel_edge.caucafall_curator import _video_metadata
from sentinel_edge.early_motion_probe import CausalMotionProbe, LOOKBACK_MS
from sentinel_edge.ikar_domain_stress import sha256_file
from sentinel_edge.reviewed_event_benchmark import source_inventory
from sentinel_edge.video_benchmark import collect_video_frames
from sentinel_edge.window_export import _private_output_path


def audit_early_motion(root: Path, pose_task: Path, output: Path, *,
                       collector=collect_video_frames) -> dict:
    destination = _private_output_path(output)
    inventory = source_inventory(root)
    if (pose_task.suffix.lower() != ".task" or not pose_task.is_file()
            or not 0 < pose_task.stat().st_size <= 60 * 1024 * 1024):
        raise ValueError("Official nonempty local pose task required")
    grouped = {"adl": Counter(), "fall": Counter()}
    total_videos = 0
    for cid, item in inventory.items():
        if sha256_file(item["path"]) != item["media_sha256"]:
            raise ValueError("Publisher source MP4 drifted after initial preflight")
        category = item["publisher_class"]
        if category not in grouped:
            raise ValueError("Unknown frozen publisher class")
        expected, fps = _video_metadata(item["path"])
        if not 1 <= expected <= 6000 or not 1 <= fps <= 120:
            raise ValueError("Invalid fixed source video FPS/count")
        probe = CausalMotionProbe()
        frames, stats = collector(
            item["path"], clip_id=cid, model=pose_task, max_frames=expected,
            frame_consumer=probe.observe, event_consumer=lambda _: None,
        )
        metrics = probe.summary()
        if (frames or type(stats.get("frames_processed")) is not int
                or stats["frames_processed"] != expected
                or metrics["frames"] != expected
                or type(stats.get("invalid_pose_frames")) is not int
                or not 0 <= stats["invalid_pose_frames"] <= metrics["pose_abstained_frames"]
                or metrics["provisional_motion_proposals"] < 0):
            raise ValueError("Real original pipeline/probe frame parity violated")
        result = grouped[category]
        result["videos"] += 1
        result["frames"] += expected
        result["nominal_video_duration_ms"] += round(expected * 1000 / fps)
        result["videos_2s_or_longer"] += expected * 1000 / fps >= LOOKBACK_MS
        result["videos_with_any_early_motion_proposal"] += bool(
            metrics["provisional_motion_proposals"]
        )
        for key in ("pose_accepted_frames", "pose_abstained_frames",
                    "samples_with_recent_upright_baseline",
                    "downward_cue_frames", "provisional_motion_proposals",
                    "cooldown_suppressed_frames", "source_resets",
                    "timestamp_gap_resets"):
            result[key] += metrics[key]
        result["strict_adapter_unavailable_frames"] += stats["invalid_pose_frames"]
        result["original_heuristic_events"] += stats["candidate_events"]
        total_videos += 1
    if total_videos != len(inventory):
        raise ValueError("Not all pinned video sources were evaluated")
    report = {
        "version": 1,
        "research_only": True,
        "dataset": "previously_exposed_ASSIST_IoT_11_original_public_clips",
        "source_publisher_hashes_verified": True,
        "not_trained_ai_model": True,
        "no_threshold_fitting_on_assist_iot": True,
        "not_a_recall_precision_fpr_or_detection_delay_evaluation": True,
        "no_human_event_onsets_or_subject_IDs_reviewed": True,
        "original_heuristic_unchanged_and_not_triggered_by_motion_probe": True,
        "strict_pose_multi_person_abstention_preserved": True,
        "short_motion_context_ms": LOOKBACK_MS,
        "no_raw_video_pose_per_event_timestamp_or_path_exported": True,
        "categories": {label: dict(grouped[label]) for label in grouped},
    }
    with destination.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def main(argv=None) -> int:
    parser = ArgumentParser(description="Research-only fixed-source 2s motion probe audit")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Both source-label limits and pose privacy must be acknowledged")
    try:
        result = audit_early_motion(args.root, args.pose_task, args.report)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        parser.error("Research-only causal probe refused: " + str(exc))
    print(json.dumps(result, sort_keys=True, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
