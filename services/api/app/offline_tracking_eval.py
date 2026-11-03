"""Strict, local-only identity-continuity metric calculator for research.

IMPORTANT: accepted actor-to-detection matches MUST be independently annotated
by a human; these tokens are not produced or validated by the current 8-joint
MediaPipe matcher. Metrics without trusted annotations are NOT tracking accuracy.

The manifest must pass the prior actor-disjoint structural gate. Only a sealed
test split may be read; prediction file must be in Git-ignored data/private.
No video, pose coordinates, faces, personal IDs, provider calls or alerts.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.actor_disjoint_admission import (
    _fictional_demo_manifest,
    _int,
    _read_private_manifest,
    _require_fields,
    _sha,
    _token,
    inspect_manifest,
)

PREDICTION_SCHEMA = "viil.research.offline_track_evaluation.v1"
TRACK = re.compile(r"^T_[a-z0-9]{3,24}$")
REASONS = ("none", "ambiguous", "occluded", "missing_pose", "time_gap", "human_review")
MAX_FRAME_GAP_MS = 200


def _fingerprint(manifest: dict) -> str:
    # Canonical binding covers the exact annotated content, not just filename.
    return hashlib.sha256(
        json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _prediction_frame(
    row: object, reference: dict,
) -> tuple[dict[str, str], dict[str, str], int, bool]:
    obj = _require_fields(
        row, {"frame_index", "timestamp_ms", "status", "reason", "observations"},
        "prediction frame",
    )
    if (
        _int(obj["frame_index"]) != reference["frame_index"]
        or _int(obj["timestamp_ms"]) != reference["timestamp_ms"]
    ):
        raise ValueError("Prediction frame/time does not match sealed annotation")
    status, reason = obj["status"], obj["reason"]
    if type(status) is not str or status not in ("accepted", "abstained"):
        raise ValueError("Invalid research prediction status")
    if type(reason) is not str or reason not in REASONS:
        raise ValueError("Invalid fixed abstention reason")
    if (status == "accepted" and reason != "none") or (
        status == "abstained" and reason == "none"
    ):
        raise ValueError("Prediction status/reason mismatch")
    observations = obj["observations"]
    if type(observations) is not list or len(observations) > 8:
        raise ValueError("Prediction observations exceed bounded capacity")
    if status == "abstained" and observations:
        raise ValueError("An abstained frame may not claim any association")

    visibility = {entry["actor_token"]: entry["state"]
                  for entry in reference["states"]}
    seen_tracks: set[str] = set()
    seen_detection: set[int] = set()
    matched: dict[str, str] = {}
    by_track: dict[str, str] = {}
    false_detections = 0
    for observation in observations:
        o = _require_fields(
            observation, {"detection_index", "track_token", "actor_token"},
            "prediction observation",
        )
        index = _int(o["detection_index"], at_most=7)
        track = o["track_token"]
        if type(track) is not str or not TRACK.fullmatch(track):
            raise ValueError("Bad local research track token")
        if index in seen_detection or track in seen_tracks:
            raise ValueError("Duplicated detection index/track within a frame")
        seen_detection.add(index)
        seen_tracks.add(track)
        actor = o["actor_token"]
        if actor is None:
            false_detections += 1
            continue
        actor = _token(actor, "A")
        if visibility.get(actor) != "visible":
            raise ValueError("Actor match is not visible in independent annotation")
        if actor in matched:
            raise ValueError("Multiple detections assigned to same reference actor")
        matched[actor] = track
        by_track[track] = actor
    return matched, by_track, false_detections, status == "abstained"


def evaluate_offline(
    manifest: object, predictions: object, *, fictional_demo: bool = False,
) -> dict[str, object]:
    """Compute descriptive tracking diagnostics, never certify rights or identity."""
    admission = inspect_manifest(manifest, fictional_demo=fictional_demo)
    doc = _require_fields(
        predictions, {"schema", "manifest_sha256", "clips"}, "predictions",
    )
    if doc["schema"] != PREDICTION_SCHEMA:
        raise ValueError("Unknown tracking-evaluation prediction schema")
    if _sha(doc["manifest_sha256"]) != _fingerprint(manifest):
        raise ValueError("Predictions not cryptographically bound to current annotations")
    test_clips = {clip["clip_token"]: clip
                  for clip in manifest["clips"] if clip["split"] == "test"}
    rows = doc["clips"]
    if type(rows) is not list or len(rows) != len(test_clips):
        raise ValueError("Predictions must cover precisely the sealed test clips")

    totals: Counter[str] = Counter()
    used_clips: set[str] = set()
    abstention_reasons: Counter[str] = Counter()
    for row in rows:
        clip = _require_fields(row, {"clip_token", "frames"}, "prediction clip")
        cid = _token(clip["clip_token"], "C")
        if cid not in test_clips or cid in used_clips:
            raise ValueError("Unknown/duplicated/non-test clip in prediction")
        used_clips.add(cid)
        reference_frames = test_clips[cid]["frames"]
        predicted_frames = clip["frames"]
        if type(predicted_frames) is not list or len(predicted_frames) != len(reference_frames):
            raise ValueError("Prediction frame coverage incomplete")
        totals["test_clips"] += 1
        previous_visible: set[str] = set()
        previous_matched: dict[str, str] = {}
        previous_tracks: dict[str, str] = {}
        previous_timestamp: int | None = None
        had_match_this_visible_run: set[str] = set()
        missed_since_match: set[str] = set()
        for ref, pred in zip(reference_frames, predicted_frames):
            matched, by_track, false_detections, abstained = _prediction_frame(pred, ref)
            visible = {e["actor_token"] for e in ref["states"] if e["state"] == "visible"}
            stamp = ref["timestamp_ms"]
            totals["test_frames"] += 1
            totals["reference_visible_actor_frames"] += len(visible)
            totals["matched_actor_frames"] += len(matched)
            totals["missed_visible_actor_frames"] += len(visible - matched.keys())
            totals["unmatched_detections"] += false_detections
            if abstained:
                totals["abstained_frames"] += 1
                abstention_reasons[pred["reason"]] += 1

            for actor in visible:
                if actor not in previous_visible:
                    had_match_this_visible_run.discard(actor)
                    missed_since_match.discard(actor)
                if actor in matched:
                    if actor in missed_since_match:
                        totals["reacquired_after_visible_gap"] += 1
                        missed_since_match.discard(actor)
                    had_match_this_visible_run.add(actor)
                elif actor in had_match_this_visible_run:
                    missed_since_match.add(actor)
            for actor in previous_visible - visible:
                had_match_this_visible_run.discard(actor)
                missed_since_match.discard(actor)

            if previous_timestamp is not None:
                gap = stamp - previous_timestamp
                shared_gt = previous_visible & visible
                totals["reference_adjacent_visible_transitions"] += len(shared_gt)
                for actor in shared_gt:
                    if actor in previous_matched and actor in matched:
                        if previous_matched[actor] == matched[actor]:
                            totals["same_track_adjacent_continuations"] += 1
                        else:
                            totals["adjacent_id_switches"] += 1
                    else:
                        totals["adjacent_unobserved_links"] += 1
                for track in previous_tracks.keys() & by_track.keys():
                    if previous_tracks[track] != by_track[track]:
                        totals["cross_actor_track_reuse"] += 1
                if gap > MAX_FRAME_GAP_MS:
                    totals["large_timestamp_intervals"] += 1
                    for actor in shared_gt:
                        if actor in previous_matched and (
                            previous_matched[actor] == matched.get(actor)
                        ):
                            totals["untrusted_continuations_across_time_gap"] += 1
            previous_visible = visible
            previous_matched = matched
            previous_tracks = by_track
            previous_timestamp = stamp
    if used_clips != set(test_clips):
        raise ValueError("Missing sealed test clip predictions")

    blockers = list(admission["blocking_reasons"])
    if totals["cross_actor_track_reuse"]:
        blockers.append("cross_actor_track_reuse_detected")
    if totals["adjacent_id_switches"]:
        blockers.append("adjacent_track_id_switches_detected")
    if totals["untrusted_continuations_across_time_gap"]:
        blockers.append("temporal_gap_tracking_continuity_untrusted")
    if totals["reference_visible_actor_frames"] == 0:
        raise ValueError("Empty visible actor reference")
    # Counts are NOT ground-truth accuracy unless human actor/detection
    # correspondences are independently annotated and reviewed.
    fields = (
        "test_clips", "test_frames", "reference_visible_actor_frames",
        "matched_actor_frames", "missed_visible_actor_frames",
        "unmatched_detections", "abstained_frames",
        "reference_adjacent_visible_transitions",
        "same_track_adjacent_continuations", "adjacent_id_switches",
        "adjacent_unobserved_links", "cross_actor_track_reuse",
        "reacquired_after_visible_gap", "large_timestamp_intervals",
        "untrusted_continuations_across_time_gap",
    )
    return {
        "status": "FICTIONAL_TRACKING_METRICS_DEMO"
        if fictional_demo else "PRIVATE_OFFLINE_TRACKING_DIAGNOSTICS_ONLY",
        "prediction_schema": PREDICTION_SCHEMA,
        "manifest_content_fingerprint_verified": True,
        "actor_disjoint_structure_checked": True,
        "structural_manifest_license_verified_by_external_reviewer": False,
        "matching_actor_labels_independently_attested_by_this_tool": False,
        "real_person_tracking_accuracy_established": False,
        "identity_metrics_are_research_diagnostics_only": True,
        "tracking_model_trained_by_this_tool": False,
        "release_authorized": False,
        "fall_confirmation_enabled": False,
        "emergency_dispatch_enabled": False,
        "raw_actor_tokens_tracks_or_coordinates_exported": False,
        "real_media_uploaded": False,
        "meta_api_called": False,
        "metrics": {name: totals[name] for name in fields},
        "abstention_reasons": dict(sorted(abstention_reasons.items())),
        "blocking_reasons": blockers,
    }


def _fictional_prediction_example(manifest: dict) -> dict:
    """Fake observations illustrate a track ID switch + cross-actor reuse."""
    test = next(c for c in manifest["clips"] if c["split"] == "test")
    states = (
        (("A_c333", "T_left"), ("A_d444", "T_right")),
        (("A_c333", "T_new"),),
        (("A_d444", "T_new"),),
        (("A_c333", "T_left"), ("A_d444", "T_new")),
    )
    rows = []
    for ref, pairs in zip(test["frames"], states):
        observations = [
            {"detection_index": i, "track_token": track, "actor_token": actor}
            for i, (actor, track) in enumerate(pairs)
        ]
        if ref["frame_index"] == 3:
            observations.append({
                "detection_index": 2, "track_token": "T_noise", "actor_token": None,
            })
        rows.append({
            "frame_index": ref["frame_index"],
            "timestamp_ms": ref["timestamp_ms"],
            "status": "accepted",
            "reason": "none",
            "observations": observations,
        })
    return {
        "schema": PREDICTION_SCHEMA,
        "manifest_sha256": _fingerprint(manifest),
        "clips": [{"clip_token": test["clip_token"], "frames": rows}],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate-only offline tracking metrics, no safety release"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic-demo", action="store_true")
    mode.add_argument("--inspect-private", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--acknowledge-person-data-review", action="store_true")
    args = parser.parse_args()
    if args.inspect_private is not None:
        if args.predictions is None or not args.acknowledge_person_data_review:
            parser.error("Private manifest, predictions and human-review acknowledgment required")
    elif args.predictions is not None:
        parser.error("Synthetic mode cannot load an external predictions file")
    try:
        if args.synthetic_demo:
            manifest = _fictional_demo_manifest()
            predictions = _fictional_prediction_example(manifest)
        else:
            manifest = _read_private_manifest(args.inspect_private)
            predictions = _read_private_manifest(args.predictions)
        report = evaluate_offline(
            manifest, predictions, fictional_demo=args.synthetic_demo,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, UnicodeError, TypeError):
        print(json.dumps({
            "status": "OFFLINE_TRACKING_EVALUATION_REFUSED",
            "release_authorized": False,
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
