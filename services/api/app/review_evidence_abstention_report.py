"""Offline quality+abstention audit of 12 previously seen licensed clips.

No real media is sent anywhere. The 12 clips and category labels have ALREADY
been inspected; this is retrospective diagnosis, NEVER a blind holdout.
Only aggregate data and public clip IDs are included in output; video and
person-derived poses remain Git-ignored.
"""
import argparse
import json
from collections import Counter
from dataclasses import asdict

from sentinel_edge.pose_traces import read_pose_trace

from app.adl_negative_challenge import CHALLENGE_ROOT
from app.adl_negative_challenge import CLIPS as ADL_CHALLENGE_CLIPS
from app.adl_negative_challenge import evaluate as evaluate_negative
from app.dev_video_research import DEV, DEV_ROOT, baseline
from app.public_video_eval import CLIPS as PREVIOUS_CLIPS
from app.public_video_eval import DATA_ROOT, SOURCE_URL, summarize_existing
from app.review_evidence_abstention import assess_pose_frames

TOTAL_EXPECTED = 12


def evaluate_known_cohorts() -> dict[str, object]:
    """Verify source MP4s, replay local pose traces, never score an unverified clip."""
    previous = summarize_existing(DATA_ROOT)["edge_evaluation"]["clips"]
    development = baseline(DEV_ROOT)["baseline"]["clips"]
    negatives = evaluate_negative(CHALLENGE_ROOT)["details"]

    prior_index = {entry["clip_id"]: entry for entry in previous}
    dev_index = {entry["clip_id"]: entry for entry in development}
    challenge_index = {entry["clip_id"]: entry for entry in negatives}
    tasks = []
    for entry in PREVIOUS_CLIPS:
        ref = prior_index[entry.clip_id]
        tasks.append((
            entry.clip_id, DATA_ROOT, entry.label,
            ref["analyzed_frames"], ref["candidate_count"], "previously_inspected",
        ))
    for clip_id, category, *_ in DEV:
        ref = dev_index[clip_id]
        tasks.append((
            clip_id, DEV_ROOT, category != "adl_no_fall",
            ref["analyzed_frames"], ref["candidate_count"], "development_seen",
        ))
    for entry in ADL_CHALLENGE_CLIPS:
        ref = challenge_index[entry.clip_id]
        tasks.append((
            entry.clip_id, CHALLENGE_ROOT, False, ref["frames"],
            ref["v1_candidate_count"], "adl_challenge_seen",
        ))
    if (
        len(tasks) != TOTAL_EXPECTED
        or len({task[0] for task in tasks}) != TOTAL_EXPECTED
        or sum(task[2] for task in tasks) != 6
    ):
        raise ValueError("Non-independent/repeated clip IDs in retrospective audit")

    results = []
    counters: Counter[str] = Counter()
    for clip_id, root, expected_fall, frames, v1_count, cohort in tasks:
        path = root / f"{clip_id}.pose.jsonl"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Untrusted or missing private source pose trace")
        assessed = assess_pose_frames(
            read_pose_trace(path, source_id=clip_id),
            source_id=clip_id,
        )
        if assessed.frames != frames or assessed.v1_candidate_count != v1_count:
            raise ValueError("Pose assessment differs from source-verified baseline")
        data = asdict(assessed)
        if data["raw_landmarks_exported"]:
            raise ValueError("Prohibited coordinate export")
        data.update({
            "cohort": cohort,
            "publisher_clip_label": "fall" if expected_fall else "adl_no_fall",
            "ground_truth_is_publisher_clip_level_only": True,
        })
        counters[assessed.status] += 1
        results.append(data)

    return {
        "status": "TWELVE_KNOWN_CLIPS_ABSTENTION_REPLAY_COMPLETE",
        "source": SOURCE_URL,
        "license": "CC BY-NC 4.0 noncommercial research only",
        "count": TOTAL_EXPECTED,
        "fall_labeled_clips": 6,
        "adl_labeled_clips": 6,
        "subjects_proven_disjoint": False,
        "known_data_only_not_blind": True,
        "no_threshold_selection_performed": True,
        "quality_thresholds_not_clinically_calibrated": True,
        "three_outcome_categories_not_diagnoses": True,
        "four_torso_landmarks_only": True,
        "any_negative_or_no_candidate_is_not_clearance": True,
        "meta_api_called": False,
        "real_media_uploaded": False,
        "notification_sent": False,
        "emergency_dispatch_enabled": False,
        "status_counts": dict(sorted(counters.items())),
        "clips": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Private 12-clip abstention research replay")
    parser.add_argument("--evaluate-known", action="store_true", required=True)
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license:
        parser.error("CC BY-NC 4.0 noncommercial research acknowledgment required")
    try:
        result = evaluate_known_cohorts()
        # Use same existing private location as the other local retrospective reports.
        filename = CHALLENGE_ROOT / "review-abstention-retrospective.json"
        if filename.is_symlink() or filename.parent.is_symlink():
            raise ValueError("Private JSON report symlink rejected")
        filename.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "RETROSPECTIVE_REVIEW_UNAVAILABLE"}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
