"""Blind-development comparison: existing v1 heuristic vs optional review-only V2.

No Meta calls. Source video and pose traces are never uploaded or committed.
This experiment cannot produce a clinical or emergency classification.
"""
import argparse
import json
from pathlib import Path

from sentinel_edge.metrics import summarize_binary
from sentinel_edge.pose_traces import read_pose_trace

from app.dev_video_research import DEV, DEV_ROOT, HOLDOUT_IDS, SOURCE_TREE, baseline
from app.experimental_review_motion import ExperimentalReviewMotionDetector
from app.public_video_eval import (
    CLIPS as PREVIOUSLY_INSPECTED_CLIPS,
)
from app.public_video_eval import (
    DATA_ROOT as PREVIOUSLY_INSPECTED_ROOT,
)
from app.public_video_eval import summarize_existing


def compare_development_only(directory: Path = DEV_ROOT) -> dict[str, object]:
    original = baseline(directory)
    by_clip = {row["clip_id"]: row for row in original["baseline"]["clips"]}
    if set(by_clip) & HOLDOUT_IDS:
        raise ValueError("Holdout ID contamination detected in development set")
    if len(by_clip) != 5 or len({item[0] for item in DEV}) != 5:
        raise ValueError("Development set must contain exactly the frozen five clips")

    y_true = []
    y_original = []
    y_review = []
    y_union = []
    rows: list[dict[str, object]] = []
    for clip_id, category, _, _, _ in DEV:
        detector = ExperimentalReviewMotionDetector()
        events = []
        frames = 0
        for frame in read_pose_trace(
            directory / (clip_id + ".pose.jsonl"), source_id=clip_id,
        ):
            prediction = detector.process(frame)
            frames += 1
            if prediction is not None:
                events.append(prediction)
        was_fall = category != "adl_no_fall"
        old = by_clip[clip_id]
        if old["analyzed_frames"] != frames or old["expected_fall"] != was_fall:
            raise ValueError("Development reference baseline mismatch")
        original_detected = bool(old["predicted_fall"])
        review_detected = bool(events)
        y_true.append(was_fall)
        y_original.append(original_detected)
        y_review.append(review_detected)
        y_union.append(original_detected or review_detected)
        rows.append({
            "id": clip_id,
            "dataset_category": category,
            "dataset_expected_fall": was_fall,
            "analyzed_frames": frames,
            "original_v1_candidate": original_detected,
            "experimental_review_candidate": review_detected,
            "combined_human_review_candidate": original_detected or review_detected,
            "review_candidate_count": len(events),
            "experimental_reasons": sorted({ev.hypothesis for ev in events}),
            "fall_confirmed": False,
            "notification_sent": False,
            "meta_called": False,
        })
    return {
        "status": "DEVELOPMENT_REVIEW_ABLATION_COMPLETE",
        "dataset_tree": SOURCE_TREE,
        "development_clip_count": 5,
        "frozen_holdout_ids_excluded": True,
        "small_subject_independence_unverified": True,
        "purpose": "offline_hypothesis_generation_only",
        "v1_unchanged": True,
        "thresholds_chosen_using_original_holdout": False,
        "clinical_accuracy_claimed": False,
        "fall_confirmation_performed": False,
        "caregiver_notifications_sent": False,
        "meta_api_called": False,
        "original_v1_clip_metrics": vars(summarize_binary(y_true, y_original)),
        "experimental_review_only_clip_metrics": vars(summarize_binary(y_true, y_review)),
        "either_signal_review_clip_metrics": vars(summarize_binary(y_true, y_union)),
        "clips": rows,
    }


def compare_previously_inspected(
    directory: Path = PREVIOUSLY_INSPECTED_ROOT,
) -> dict[str, object]:
    """Regress on the *already seen* five clips, NEVER call this blind holdout.

    The previous 5 evaluation clips and their gate failures were already
    inspected before V2 design. Results are exploratory and leakage-prone.
    """
    old = summarize_existing(directory)
    by_clip = {row["clip_id"]: row for row in old["edge_evaluation"]["clips"]}
    if len(by_clip) != 5 or set(by_clip) != HOLDOUT_IDS:
        raise ValueError("Previously inspected regression set mismatch")
    y_true = []
    y_old = []
    y_review = []
    y_either = []
    results = []
    for entry in PREVIOUSLY_INSPECTED_CLIPS:
        clip_id = entry.clip_id
        frames = 0
        detector = ExperimentalReviewMotionDetector()
        events = []
        for frame in read_pose_trace(
            directory / (clip_id + ".pose.jsonl"), source_id=clip_id,
        ):
            frames += 1
            result = detector.process(frame)
            if result is not None:
                events.append(result)
        reference = by_clip[clip_id]
        if frames != reference["analyzed_frames"] or entry.label != reference["expected_fall"]:
            raise ValueError("Previously inspected clip metadata mismatch")
        old_hit = bool(reference["predicted_fall"])
        new_hit = bool(events)
        y_true.append(entry.label)
        y_old.append(old_hit)
        y_review.append(new_hit)
        y_either.append(old_hit or new_hit)
        results.append({
            "id": clip_id, "source_label_fall": entry.label,
            "v1_candidate": old_hit, "review_v2_candidate": new_hit,
            "review_v2_hypotheses": sorted({e.hypothesis for e in events}),
            "frames": frames, "fall_confirmed": False, "meta_called": False,
            "notification_sent": False,
        })
    return {
        "status": "INSPECTED_NONBLIND_REGRESSION_ONLY",
        "scientific_limit": (
            "These five clips were inspected BEFORE the experiment. "
            "This is NOT a blind or subject-independent holdout estimate."
        ),
        "thresholds_modified_after_development_run": False,
        "media_uploaded": False,
        "meta_called": False,
        "v1_metrics": vars(summarize_binary(y_true, y_old)),
        "review_v2_metrics": vars(summarize_binary(y_true, y_review)),
        "either_review_signal_metrics": vars(summarize_binary(y_true, y_either)),
        "clips": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline V1 vs V2 review-only research")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--compare-dev", action="store_true")
    choice.add_argument("--compare-inspected", action="store_true")
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license:
        parser.error("CC BY-NC noncommercial research use acknowledgment required")
    try:
        if args.compare_dev:
            result = compare_development_only()
            private = DEV_ROOT / "review-only-development-ablation.json"
        else:
            result = compare_previously_inspected()
            private = PREVIOUSLY_INSPECTED_ROOT / "previously-inspected-regression.json"
        if private.is_symlink():
            raise ValueError("Private report cannot be a symlink")
        private.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, ValueError):
        print(json.dumps({"status": "DEVELOPMENT_COMPARISON_REJECTED"}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
