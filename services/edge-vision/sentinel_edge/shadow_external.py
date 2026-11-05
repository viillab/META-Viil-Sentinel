"""Real previously-exposed public media Shadow+Heuristic research audit.

No tuning, training, calibration, subject claims, per-video identities,
event onset claims or alert path changes. Every 11 ASSIST MP4 source file
is pinned and rehashed before and during evaluation. Privacy-minimal
category aggregates are written only to ignored data/private.
"""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path

from sentinel_edge.caucafall_curator import _video_metadata
from sentinel_edge.ikar_domain_stress import sha256_file
from sentinel_edge.reviewed_event_benchmark import source_inventory
from sentinel_edge.shadow_inference import (
    SHADOW_WINDOW_MS, RollingModelShadow, load_verified_linear_shadow,
)
from sentinel_edge.video_benchmark import collect_video_frames
from sentinel_edge.window_export import _private_output_path


def audit_shadow_sources(
    root: Path, pose_task: Path, linear_model_path: Path, output: Path,
    *, collector=collect_video_frames,
) -> dict:
    destination = _private_output_path(output)
    inventory = source_inventory(root)
    if (pose_task.suffix.lower() != ".task" or not pose_task.is_file()
            or not 0 < pose_task.stat().st_size <= 60 * 1024 * 1024):
        raise ValueError("Missing/bad local MediaPipe pose task")
    linear = load_verified_linear_shadow(linear_model_path)
    totals = {"adl": Counter(), "fall": Counter()}
    for cid, item in inventory.items():
        if sha256_file(item["path"]) != item["media_sha256"]:
            raise ValueError("Publisher MP4 changed after initial preflight")
        category = item["publisher_class"]
        if category not in totals:
            raise ValueError("Unknown ASSIST publisher label")
        expected, fps = _video_metadata(item["path"])
        if not 1 <= expected <= 6000 or fps <= 0:
            raise ValueError("Invalid fixed public video source metadata")
        model_shadow = RollingModelShadow(linear)
        frames, stats = collector(
            item["path"], clip_id=cid, model=pose_task, max_frames=expected,
            frame_consumer=model_shadow.observe,
            event_consumer=lambda _: None,
        )
        counts = model_shadow.summary()
        if (frames or stats["frames_processed"] != expected
                or counts["incoming_frames"] != expected
                or stats["candidate_events"] < 0):
            raise ValueError("Unmatched original video, camera or shadow frame counts")
        target = totals[category]
        target["videos"] += 1
        target["frames"] += expected
        target["videos_nominally_shorter_than_8s"] += expected / fps < (
            SHADOW_WINDOW_MS / 1000
        )
        target["videos_with_scored_windows"] += counts["scored_windows"] > 0
        target["videos_any_shadow_candidate"] += counts["candidate_windows"] > 0
        target["shadow_scored_windows"] += counts["scored_windows"]
        target["shadow_candidate_windows"] += counts["candidate_windows"]
        target["shadow_below_threshold_windows"] += counts["below_threshold_windows"]
        target["shadow_pose_abstained_windows"] += counts["pose_abstained_windows"]
        target["original_heuristic_events"] += stats["candidate_events"]
        target["pose_unavailable_frames"] += stats["invalid_pose_frames"]
        target["temporal_gap_resets"] += counts["frame_time_gap_resets"]
    report = {
        "version": 1,
        "research_only": True,
        "source": "ASSIST_IoT_reference_mp4_exposed_diagnostic",
        "all_original_publisher_media_source_sha_verified": True,
        "publisher_labels_not_human_event_ground_truth": True,
        "source_actor_identities_unknown": True,
        "former_external_videos_already_exposed": True,
        "shadow_window_ms": SHADOW_WINDOW_MS,
        "shadow_hop_ms": 1000,
        "shadow_threshold": linear.threshold,
        "shadow_model_not_used_for_alerts_or_training": True,
        "original_heuristic_unchanged": True,
        "no_event_recall_false_alarm_hour_accuracy_or_alert_claim": True,
        "no_video_landmarks_individual_times_or_paths_exported": True,
        "categories": {key: dict(value) for key, value in totals.items()},
    }
    if sum(row["videos"] for row in report["categories"].values()) != len(inventory):
        raise ValueError("Incomplete source evaluation")
    with destination.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def main(argv=None) -> int:
    parser = ArgumentParser(description="Private source-verified real AI Shadow audit")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path, required=True)
    parser.add_argument("--linear-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Explicit research labels and pose-privacy acknowledgement required")
    try:
        report = audit_shadow_sources(
            args.root, args.pose_task, args.linear_model, args.report
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        parser.error("Source verified research shadow audit refused: " + str(exc))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
