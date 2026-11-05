"""Human-review-gated, event-level offline benchmark for ASSIST-IoT videos.

No fall event labels are inferred from publisher video names or model output.
Two distinct independently attested human reviewers must manually specify
EVERY event onset (including a deliberate empty set) for ALL 11 clips.
Without complete agreement this module refuses ALL accuracy numbers.
Publisher labels, unknown subject identities, and consent remain caveats.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.assist_external import (
    CATALOG, DATASET, PINNED_COMMIT, SOURCE_LICENSE, private_root,
)
from sentinel_edge.temporal_training import _read_bounded_json
from sentinel_edge.window_export import _private_output_path

MAX_REVIEWED_ONSETS = 32
ONSET_TOLERANCE_MS = 200
EARLY_TOLERANCE_MS = 250
MATCH_AFTER_MS = 2_000
MAX_CANDIDATES = 1000
MAX_VIDEO_MS = 90_000
EARLY_MOTION_RESEARCH_TAG = "causal_early_motion_probe_v1_untrained"
REVIEWABLE_DETECTORS = frozenset({
    "original_temporal_heuristic_v1", EARLY_MOTION_RESEARCH_TAG,
})


def source_inventory(root: Path) -> dict:
    """Validate original fixed source manifests + every original video digest."""
    from sentinel_edge.caucafall_curator import _sha256_file
    from sentinel_edge.public_dataset_ingest import _github_blob_sha1
    root = private_root(root).resolve(strict=True)
    manifest = _read_bounded_json(root / "assist-frozen-video-manifest-v1.json")
    if (not isinstance(manifest, dict)
            or set(manifest) != {
                "version", "dataset", "commit", "license", "source_doi",
                "labels_independently_reviewed", "subject_identities_for_reference_videos",
                "clips",
            }
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or manifest["dataset"] != DATASET
            or manifest["commit"] != PINNED_COMMIT
            or manifest["license"] != SOURCE_LICENSE
            or manifest["labels_independently_reviewed"] is not False
            or manifest["subject_identities_for_reference_videos"] != "unknown"):
        raise ValueError("Publisher source manifest is not pinned/strict")
    expected = {(group, name[:-4]): (size, blob)
                for group, name, size, blob in CATALOG}
    if not isinstance(manifest["clips"], list) or len(manifest["clips"]) != len(expected):
        raise ValueError("Pinned reference clip count differs")
    inventory = {}
    for clip in manifest["clips"]:
        if not isinstance(clip, dict) or set(clip) != {
            "activity", "class", "video", "source_bytes", "media_sha256", "duration_ms",
        }:
            raise ValueError("Unexpected source-video manifest clip fields")
        cid, group = clip["activity"], clip["class"]
        if (type(cid) is not str or (group, cid) not in expected
                or cid in inventory):
            raise ValueError("Unrecognized/duplicate publisher activity")
        size, blob = expected[(group, cid)]
        if (clip["video"] != f"clips/{group}/{cid}.mp4"
                or clip["source_bytes"] != size
                or type(clip["duration_ms"]) is not int
                or not 900 <= clip["duration_ms"] <= MAX_VIDEO_MS):
            raise ValueError("Pinned media metadata changed")
        candidate = (root / clip["video"]).resolve(strict=True)
        if (not candidate.is_relative_to(root / "clips")
                or candidate.stat().st_size != size
                or _sha256_file(candidate) != clip["media_sha256"]
                or _github_blob_sha1(candidate.read_bytes()) != blob):
            raise ValueError("Publisher source file hash drift")
        inventory[cid] = {
            "duration_ms": clip["duration_ms"],
            "media_sha256": clip["media_sha256"],
            "publisher_class": group,
            "path": candidate,
        }
    return inventory


def blank_review_template(inventory: dict) -> dict:
    """Two *empty* decisions per video, no publisher-label auto-population."""
    if not inventory:
        raise ValueError("Source inventory empty")
    decisions = []
    for cid in inventory:
        for _ in range(2):
            decisions.append({
                "clip_id": cid,
                "reviewer_id": "",
                "media_sha256": None,
                "independently_reviewed": False,
                "complete_video_reviewed": False,
                "uncertain": True,
                "fall_onsets_ms": None,
                "review_note": "",
            })
    return {
        "version": 1, "dataset": DATASET, "source_commit": PINNED_COMMIT,
        "decisions": decisions,
    }


def _timestamps(values, duration: int, *, name: str, max_count: int,
                separation: int = 1) -> list[int]:
    if (not isinstance(values, list) or len(values) > max_count
            or any(type(t) is not int or not 0 <= t <= duration for t in values)
            or any(b - a < separation for a, b in zip(values, values[1:]))):
        raise ValueError(f"Invalid {name}; require ordered bounded integer millisecond times")
    return values


def verify_independent_onsets(inventory: dict, reviews: dict) -> dict:
    """Fail closed on both reviewers for every video; never trust clip label."""
    if (not isinstance(reviews, dict)
            or set(reviews) != {"version", "dataset", "source_commit", "decisions"}
            or type(reviews["version"]) is not int or reviews["version"] != 1
            or reviews["dataset"] != DATASET
            or reviews["source_commit"] != PINNED_COMMIT
            or not isinstance(reviews["decisions"], list)
            or len(reviews["decisions"]) != 2 * len(inventory)):
        raise ValueError("Review protocol and number of decisions are invalid")
    grouped = {cid: [] for cid in inventory}
    for decision in reviews["decisions"]:
        if (not isinstance(decision, dict) or set(decision) != {
                "clip_id", "reviewer_id", "media_sha256", "independently_reviewed",
                "complete_video_reviewed", "uncertain", "fall_onsets_ms", "review_note",
        } or decision["clip_id"] not in grouped):
            raise ValueError("Unknown review clip or schema")
        cid = decision["clip_id"]
        if len(grouped[cid]) >= 2:
            raise ValueError("Repeated reviewer entries")
        if not isinstance(decision["reviewer_id"], str) or not (
            3 <= len(decision["reviewer_id"]) <= 60
        ) or any(not (ch.isalnum() or ch in "-_") for ch in decision["reviewer_id"]):
            raise ValueError("Require pseudonymous distinct reviewer ID")
        if any(d["reviewer_id"] == decision["reviewer_id"] for d in grouped[cid]):
            raise ValueError("Two DISTINCT reviewers required per clip")
        if (decision["media_sha256"] != inventory[cid]["media_sha256"]
                or decision["independently_reviewed"] is not True
                or decision["complete_video_reviewed"] is not True
                or decision["uncertain"] is not False):
            raise ValueError("Unreviewed/uncertain/partly reviewed or source hash mismatch")
        note = decision["review_note"]
        if (not isinstance(note, str) or not 15 <= len(note.strip()) <= 200
                or any(ord(ch) < 32 for ch in note)):
            raise ValueError("Real reviewer observation note required")
        _timestamps(decision["fall_onsets_ms"], inventory[cid]["duration_ms"],
                    name="fall onset", max_count=MAX_REVIEWED_ONSETS,
                    separation=ONSET_TOLERANCE_MS + 1)
        grouped[cid].append(decision)
    approved = {}
    for cid, rows in grouped.items():
        if len(rows) != 2:
            raise ValueError("Two decisions required for every reference clip")
        a, b = rows[0]["fall_onsets_ms"], rows[1]["fall_onsets_ms"]
        if len(a) != len(b) or any(abs(x - y) > ONSET_TOLERANCE_MS
                                   for x, y in zip(a, b)):
            raise ValueError("Reviewers disagree on event count or onset timings")
        approved[cid] = [(x + y) // 2 for x, y in zip(a, b)]
    return approved


def score_one(onsets: list[int], candidates: list[int], duration_ms: int) -> dict:
    """Chronological one-to-one event matching, fixed {-250,+2000}ms window.

    Earliest candidate in a label's permitted interval can match only one
    event; other candidates are false candidates, not duplicate true hits.
    """
    _timestamps(onsets, duration_ms, name="reviewed onset",
                max_count=MAX_REVIEWED_ONSETS, separation=ONSET_TOLERANCE_MS + 1)
    _timestamps(candidates, duration_ms, name="candidate",
                max_count=MAX_CANDIDATES)
    matched = 0
    delays = []
    used = set()
    for onset in onsets:
        for i, candidate in enumerate(candidates):
            if i not in used and onset - EARLY_TOLERANCE_MS <= candidate <= (
                onset + MATCH_AFTER_MS
            ):
                used.add(i)
                matched += 1
                delays.append(candidate - onset)
                break
    return {
        "reviewed_fall_events": len(onsets),
        "matched_fall_events": matched,
        "missed_fall_events": len(onsets) - matched,
        "false_candidates": len(candidates) - matched,
        "candidate_count": len(candidates),
        "matching_delay_ms": delays,  # only aggregated summaries exported
    }


def evaluate_reviewed_events(inventory: dict, reviews: dict,
                             candidate_manifest: dict) -> dict:
    """Aggregate metrics only; zero without full two-reviewer verification."""
    onsets_by_clip = verify_independent_onsets(inventory, reviews)
    if (not isinstance(candidate_manifest, dict)
            or set(candidate_manifest) != {
                "version", "dataset", "source_commit", "detector", "clips",
            } or type(candidate_manifest["version"]) is not int
            or candidate_manifest["version"] != 1
            or candidate_manifest["dataset"] != DATASET
            or candidate_manifest["source_commit"] != PINNED_COMMIT
            or candidate_manifest["detector"] not in REVIEWABLE_DETECTORS
            or not isinstance(candidate_manifest["clips"], list)
            or len(candidate_manifest["clips"]) != len(inventory)):
        raise ValueError("Expected original detector candidate evidence for every clip")
    observed = set()
    counts = dict(reviewed_events=0, matched_events=0, missed_events=0,
                  false_candidates=0, candidate_events=0, fully_reviewed_videos=0)
    latencies = []
    negative_ms = 0
    negative_false_candidates = 0
    positives = 0
    for row in candidate_manifest["clips"]:
        if not isinstance(row, dict) or set(row) != {
            "clip_id", "media_sha256", "candidate_ms", "analyzed_frames",
            "valid_pose_frames",
        }:
            raise ValueError("Unexpected candidate-evidence schema")
        cid = row["clip_id"]
        if cid not in inventory or cid in observed:
            raise ValueError("Missing/duplicate candidate evidence")
        observed.add(cid)
        if row["media_sha256"] != inventory[cid]["media_sha256"]:
            raise ValueError("Candidate media SHA mismatch")
        n, v = row["analyzed_frames"], row["valid_pose_frames"]
        if (type(n) is not int or type(v) is not int or not 0 <= v <= n <= 6000
                or n == 0):
            raise ValueError("Invalid pose coverage in candidate evidence")
        candidates = _timestamps(
            row["candidate_ms"], inventory[cid]["duration_ms"],
            name="candidate", max_count=MAX_CANDIDATES,
        )
        starts = onsets_by_clip[cid]
        scored = score_one(starts, candidates, inventory[cid]["duration_ms"])
        counts["reviewed_events"] += scored["reviewed_fall_events"]
        counts["matched_events"] += scored["matched_fall_events"]
        counts["missed_events"] += scored["missed_fall_events"]
        counts["false_candidates"] += scored["false_candidates"]
        counts["candidate_events"] += scored["candidate_count"]
        counts["fully_reviewed_videos"] += 1
        latencies.extend(scored["matching_delay_ms"])
        if starts:
            positives += 1
        else:
            negative_ms += inventory[cid]["duration_ms"]
            negative_false_candidates += scored["false_candidates"]
    if observed != set(inventory):
        raise ValueError("Candidate evidence misses video")
    totals = {
        **counts,
        "reviewed_fall_videos": positives,
        "reviewed_no_fall_videos": len(inventory) - positives,
        "reviewed_no_fall_hours": round(negative_ms / 3_600_000, 6),
        "event_recall": (round(counts["matched_events"] / counts["reviewed_events"], 5)
                         if counts["reviewed_events"] else None),
        "matched_detection_delay_mean_ms": (
            round(sum(latencies) / len(latencies), 1) if latencies else None
        ),
        "false_candidates_in_entire_reviewed_no_fall_videos": negative_false_candidates,
        "false_candidates_per_full_no_fall_hour": (
            round(negative_false_candidates * 3_600_000 / negative_ms, 4)
            if negative_ms else None
        ),
        "no_false_alarm_hour_claim": True,
        "two_pseudonymous_attestations_per_video_required": True,
        "reviewer_identity_and_consent_not_software_verified": True,
        "publisher_labels_not_ground_truth": True,
        "not_an_independent_unseen_subject_test": True,
        "not_clinically_validated": True,
        "model_wiring_changed": False,
        "candidate_detector": candidate_manifest["detector"],
        "candidate_is_trained_ai": False,
        "automatic_alert_authorized": False,
    }
    return totals


def collect_original_heuristic_events(
    inventory: dict, pose_task: Path, *, collector=None, metadata_reader=None,
) -> dict:
    """Actually decode all source clips using unchanged production heuristic.

    Keeps only event times and counts. Does NOT create human truth labels.
    """
    from sentinel_edge.contracts import PoseFeatures
    from sentinel_edge.video_benchmark import collect_video_frames
    from sentinel_edge.caucafall_curator import _sha256_file, _video_metadata
    if (pose_task.suffix.lower() != ".task" or not pose_task.is_file()
            or not 0 < pose_task.stat().st_size <= 60 * 1024 * 1024):
        raise ValueError("Official local nonempty pose task required")
    extractor = collector or collect_video_frames
    reader = metadata_reader or _video_metadata
    results = []
    for cid, item in inventory.items():
        if _sha256_file(item["path"]) != item["media_sha256"]:
            raise ValueError("Media mutated since preflight")
        expected, fps = reader(item["path"])
        if (type(expected) is not int or not 1 <= expected <= 6000
                or type(fps) not in (int, float) or not 1 <= fps <= 120):
            raise ValueError("Invalid original video frame count or FPS")
        event_times = []
        counts = {"frames": 0, "poses": 0}
        def on_frame(frame):
            counts["frames"] += 1
            counts["poses"] += PoseFeatures.from_frame(frame, .55) is not None
        def on_event(event):
            if type(event.timestamp_ms) is not int:
                raise ValueError("Invalid candidate timestamp")
            event_times.append(event.timestamp_ms)
        frames, stats = extractor(
            item["path"], clip_id=cid, model=pose_task, max_frames=expected,
            frame_consumer=on_frame, event_consumer=on_event,
        )
        if (frames or type(stats.get("frames_processed")) is not int
                or type(stats.get("candidate_events")) is not int
                or counts["frames"] != expected
                or stats["frames_processed"] != expected
                or stats["candidate_events"] != len(event_times)):
            raise ValueError("Incomplete video decode or original heuristic counts diverged")
        _timestamps(event_times, item["duration_ms"], name="original candidate",
                    max_count=MAX_CANDIDATES)
        results.append({
            "clip_id": cid, "media_sha256": item["media_sha256"],
            "candidate_ms": event_times,
            "analyzed_frames": counts["frames"],
            "valid_pose_frames": counts["poses"],
        })
    return {
        "version": 1, "dataset": DATASET, "source_commit": PINNED_COMMIT,
        "detector": "original_temporal_heuristic_v1", "clips": results,
    }


def collect_early_motion_candidate_events(
    inventory: dict, pose_task: Path, *, collector=None, metadata_reader=None,
) -> dict:
    """Capture untrained 2s cues in PRIVATE event-time evidence, NOT alerts.

    Uses exact original video decoding/pose adapter/heuristic. Never invent
    labels. Caller writes only into Git-ignored data/private by exclusive create.
    Source-hash checks are repeated for each video; missing frames abort.
    """
    from sentinel_edge.caucafall_curator import _sha256_file, _video_metadata
    from sentinel_edge.contracts import PoseFeatures
    from sentinel_edge.early_motion_probe import CausalMotionProbe
    from sentinel_edge.video_benchmark import collect_video_frames

    if (pose_task.suffix.lower() != ".task" or not pose_task.is_file()
            or not 0 < pose_task.stat().st_size <= 60 * 1024 * 1024):
        raise ValueError("Official nonempty private local PoseLandmarker task required")
    extractor = collector or collect_video_frames
    reader = metadata_reader or _video_metadata
    results = []
    for cid, item in inventory.items():
        if _sha256_file(item["path"]) != item["media_sha256"]:
            raise ValueError("Media mutated since source preflight")
        expected, fps = reader(item["path"])
        if (type(expected) is not int or not 1 <= expected <= 6000
                or type(fps) not in (int, float) or not 1 <= fps <= 120):
            raise ValueError("Invalid original video frame count or FPS")
        private_times: list[int] = []
        cue = CausalMotionProbe(private_proposal_consumer=private_times.append)
        observed = 0
        pose_eligible = 0

        def on_frame(frame):
            nonlocal observed, pose_eligible
            observed += 1
            pose_eligible += PoseFeatures.from_frame(frame, .55) is not None
            cue.observe(frame)

        frames, stats = extractor(
            item["path"], clip_id=cid, model=pose_task, max_frames=expected,
            frame_consumer=on_frame, event_consumer=lambda _: None,
        )
        if (frames or type(stats.get("frames_processed")) is not int
                or stats["frames_processed"] != expected or observed != expected
                or cue.summary()["frames"] != expected
                or cue.summary()["pose_accepted_frames"] != pose_eligible
                or len(private_times) != cue.summary()["provisional_motion_proposals"]):
            raise ValueError("Incomplete video decode or research cue count mismatch")
        _timestamps(private_times, item["duration_ms"],
                    name="private research motion candidate",
                    max_count=MAX_CANDIDATES)
        results.append({
            "clip_id": cid, "media_sha256": item["media_sha256"],
            "candidate_ms": private_times,
            "analyzed_frames": observed, "valid_pose_frames": pose_eligible,
        })
    return {
        "version": 1, "dataset": DATASET, "source_commit": PINNED_COMMIT,
        "detector": EARLY_MOTION_RESEARCH_TAG, "clips": results,
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description="Private, two-reviewer fall-onset event protocol")
    parser.add_argument("--mode", choices=("prepare", "capture", "capture-early", "score"),
                        required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--acknowledge-review-privacy", action="store_true")
    parser.add_argument("--acknowledge-media-rights", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_review_privacy or not args.acknowledge_media_rights:
        parser.error("Explicit privacy and media-rights acknowledgement required")
    if args.mode == "score" and not (args.reviews and args.candidates):
        parser.error("score requires both --reviews and --candidates")
    if args.mode != "score" and (args.reviews or args.candidates):
        parser.error("only score accepts --reviews and --candidates")
    if (args.mode in ("capture", "capture-early")) != (args.pose_task is not None):
        parser.error("capture and capture-early require --pose-task; prepare/score forbid it")
    try:
        destination = _private_output_path(args.output)
        root = private_root(args.root).resolve(strict=True)
        inventory = source_inventory(root)
        if args.mode == "prepare":
            payload = blank_review_template(inventory)
        elif args.mode == "capture":
            payload = collect_original_heuristic_events(inventory, args.pose_task)
        elif args.mode == "capture-early":
            payload = collect_early_motion_candidate_events(inventory, args.pose_task)
        else:
            def bounded(path):
                target = private_root(path).resolve(strict=True)
                if not target.is_relative_to(root):
                    raise ValueError("All source/reviewer data must remain under private root")
                return _read_bounded_json(target)
            payload = evaluate_reviewed_events(
                inventory, bounded(args.reviews), bounded(args.candidates),
            )
        serialized = json.dumps(payload, allow_nan=False, indent=2)
        if len(serialized.encode("utf8")) > 2_000_000:
            raise ValueError("Private event-evaluation JSON output too large")
        with destination.open("x", encoding="utf8") as f:
            f.write(serialized)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error("Event scoring refused: " + str(exc))
    print(json.dumps({
        "mode": args.mode, "videos": len(inventory),
        "reviewed_ground_truth_automatically_generated": False,
        "score_available": args.mode == "score",
        "candidate_evidence_without_ground_truth": args.mode in ("capture", "capture-early"),
        "production_alarm_authorized": False,
        "private_output": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
