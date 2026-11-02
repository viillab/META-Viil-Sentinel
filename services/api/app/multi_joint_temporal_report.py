"""Reproducible offline 5-clip eight-joint temporal availability audit.

Original human videos and derived pose coordinates remain in ignored private
storage. This does NOT infer falls, identify a person, or change Member 1's
four-torso-joint production runtime. All five clips were previously inspected:
their performance cannot be treated as blind holdout validation.
"""
import argparse
import json
from collections import Counter
from dataclasses import asdict

from app.multi_joint_research import (
    OUTPUT,
    SELECTION,
    _input_sources,
    _private_root,
    _read_private_trace,
    analyze_private,
)
from app.multi_joint_temporal import assess_temporal_observability


def evaluate_frozen_five() -> dict[str, object]:
    # Original MP4 bytes are SHA-256+Git-blob checked by _input_sources()
    # and the prior coverage aggregator enforces complete extracted traces.
    sources = _input_sources()
    original = analyze_private(OUTPUT)
    old_by_clip = {c["clip_id"]: c for c in original["clips"]}
    if (
        len(sources) != 5 or len(old_by_clip) != 5
        or set(old_by_clip) != {cid for cid, _ in SELECTION}
    ):
        raise ValueError("Frozen five-clip research cohort mismatch")
    folder = _private_root(OUTPUT)
    details = []
    states: Counter[str] = Counter()
    for source in sources:
        path = folder / f"{source.clip_id}.eight.pose.jsonl"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Untrusted or absent private eight-joint trace")
        sample = assess_temporal_observability(
            _read_private_trace(path), clip_id=source.clip_id,
        )
        baseline = old_by_clip[source.clip_id]
        if (
            sample.frames != source.expected_frames
            or sample.frames != baseline["frames"]
            or sample.all_joint_visible_frames
            != baseline["all_8_joints_visible_frames"]
        ):
            raise ValueError("Temporal features disagree with independently checked source")
        # Keep only aggregate numeric diagnostics; no actual landmarks.
        result = asdict(sample)
        result["publisher_label"] = source.label
        result["already_inspected_nonblind"] = True
        details.append(result)
        states[sample.state] += 1
    return {
        "status": "FROZEN_EIGHT_JOINT_TEMPORAL_OBSERVABILITY_COMPLETE",
        "clip_count": len(details),
        "total_frames": sum(item["frames"] for item in details),
        "eligible_temporal_pairs": sum(item["eligible_temporal_pairs"] for item in details),
        "publisher_labels_not_independent": True,
        "single_pose_per_frame_identity_tracking": False,
        "camera_motion_compensated": False,
        "preselected_known_clips_not_blind": True,
        "no_new_model_trained": True,
        "no_event_detection_or_diagnosis": True,
        "human_video_or_raw_joint_coordinates_uploaded": False,
        "meta_api_called": False,
        "emergency_alert_enabled": False,
        "states": dict(sorted(states.items())),
        "clips": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local-only five-clip temporal joint feasibility research",
    )
    parser.add_argument("--evaluate-known", action="store_true", required=True)
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license or not args.acknowledge_pose_privacy:
        parser.error("Both noncommercial research and pose privacy acknowledgment required")
    try:
        report = evaluate_frozen_five()
        target = OUTPUT / "aggregate-temporal-observability.json"
        if target.is_symlink():
            raise ValueError("Refusing symlinked private report")
        target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "EIGHT_JOINT_TEMPORAL_AUDIT_REJECTED"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
