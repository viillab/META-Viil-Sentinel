"""Audited local replay of anonymous tracklet continuity, not real tracking.

The five existing research sources were extracted with MediaPipe num_poses=1.
Their *single-pose* traces cannot test multiple-person association or prove
identity. Multi-person ambiguity can only be tested on fictional geometry
until separately authorized, annotated multi-person video is available.
"""
import argparse
import json

from app.anonymous_tracklet_research import (
    AnonymousTrackletResearch,
    ResearchDetections,
)
from app.multi_joint_research import OUTPUT, SELECTION, _private_root, _read_private_trace
from app.multi_joint_temporal_report import evaluate_frozen_five


def evaluate_known_single_pose_continuity() -> dict[str, object]:
    original = evaluate_frozen_five()  # pinned source verification + complete traces
    prior = {c["clip_id"]: c for c in original["clips"]}
    if len(prior) != 5 or set(prior) != {c for c, _ in SELECTION}:
        raise ValueError("Frozen research source selection mismatched")
    folder = _private_root(OUTPUT)
    clips = []
    for cid, publisher_label in SELECTION:
        trace = folder / f"{cid}.eight.pose.jsonl"
        if trace.is_symlink() or not trace.is_file():
            raise ValueError("Missing or symlinked private research trace")
        tracker = AnonymousTrackletResearch()
        for ts, points in _read_private_trace(trace):
            # Existing single-pose MediaPipe results: 0 or 1 individual
            # detection per frame. Do not interpret as persistent identity.
            tracker.process(ResearchDetections(
                source_id=cid, timestamp_ms=ts,
                poses=(points,) if points else (),
            ))
        result = tracker.aggregate()
        if (
            result["frames_observed"] != prior[cid]["frames"]
            or result["adjacent_geometric_links"] > prior[cid]["adjacent_intervals"]
            or result["max_poses_seen_in_one_frame"] > 1
        ):
            raise ValueError("Observed tracklet counters conflict with source video")
        result["clip_id"] = cid
        result["publisher_label"] = publisher_label
        result["previously_inspected_nonblind"] = True
        clips.append(result)
    return {
        "status": "LOCAL_SINGLE_POSE_ANONYMOUS_CONTINUITY_AUDIT_COMPLETE",
        "source_pinned_and_trace_counts_verified": True,
        "original_five_known_clips_only": True,
        "clip_count": len(clips),
        "frames_observed": sum(c["frames_observed"] for c in clips),
        "adjacent_geometric_links": sum(c["adjacent_geometric_links"] for c in clips),
        "no_pose_frames_abstained": sum(c["no_pose_frames_abstained"] for c in clips),
        "incomplete_eight_joint_frames_abstained": sum(
            c["incomplete_eight_joint_frames_abstained"] for c in clips
        ),
        "actual_multi_person_source_frames_available": False,
        "person_tracking_accuracy_measured": False,
        "identity_recovery_after_occlusion": False,
        "raw_coordinates_or_media_uploaded": False,
        "real_meta_api_called": False,
        "emergency_notification_sent": False,
        "all_research_results_unverified_for_safety": True,
        "clips": clips,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline private single-pose continuity audit")
    parser.add_argument("--evaluate-known", action="store_true", required=True)
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args()
    if not (args.acknowledge_noncommercial_license and args.acknowledge_pose_privacy):
        parser.error("Both noncommercial license and private pose processing acknowledgment required")
    try:
        report = evaluate_known_single_pose_continuity()
        target = OUTPUT / "aggregate-anonymous-continuity.json"
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError("Private report is symlinked")
        target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "PRIVATE_ANONYMOUS_CONTINUITY_AUDIT_REJECTED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
