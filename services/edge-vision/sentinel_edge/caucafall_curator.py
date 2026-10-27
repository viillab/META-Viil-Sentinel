"""Conservative CAUCAFall Omnifall *research* curation, not clinical training.

Reads the 258 official action-labeled MMAction rows, NOT all 516 AVI files.
Creates separate private proposal files with label_reviewed=False. Optional
experimental fitting uses publisher labels (never pretending an independent
human has reviewed events). No production alerts or third-party uploads.
"""
from argparse import ArgumentParser
from collections import Counter
import csv
from hashlib import sha256
from math import sqrt
import json
from pathlib import Path
import re

from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import _metrics, train_and_evaluate
from sentinel_edge.window_export import NearestFrameSampler, _private_output_path

CLASS_NAMES = {
    0: "walk", 1: "fall_motion", 2: "fallen", 3: "sit_down",
    4: "sitting", 5: "lie_down", 6: "lying", 7: "stand_up",
    8: "standing", 9: "other",
}
# Only unambiguous ADLs from the publisher's ADL *recordings*.
ADL_CLASSES = {0, 3, 4, 7, 8}
DATASET_ID = "caucafall-omnifall"
SUBJECT_SPLITS = {
    **{str(i): "train" for i in range(1, 7)},
    **{str(i): "val" for i in range(7, 9)},
    **{str(i): "test" for i in range(9, 11)},
}
ANNOTATION_NAME = "mmaction2_annotations.txt"
MAX_ROWS = 600
MAX_SOURCE_BYTES = 512 * 1024 * 1024


def _video_metadata(path: Path) -> tuple[int, float]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Local OpenCV video backend is required") from exc
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("Video could not be opened")
        count, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
        if not 1 <= count <= 6000 or not 1 <= fps <= 120:
            raise ValueError("Invalid video frame count or FPS")
        return count, fps
    finally:
        cap.release()


def read_publisher_annotations(root: Path) -> list[dict]:
    """Strictly validate publisher-listed annotated AVI clips, no guessing."""
    root = root.resolve(strict=True)
    label_file = root / ANNOTATION_NAME
    if not label_file.is_file() or label_file.stat().st_size > 200_000:
        raise ValueError("Missing or oversized publisher MMAction annotation")
    lines = label_file.read_text("utf-8-sig").splitlines()
    if not 1 <= len(lines) <= MAX_ROWS:
        raise ValueError("Unexpected annotation count")
    csv_file = root / "caucafall.csv"
    if not csv_file.is_file() or csv_file.stat().st_size > 200_000:
        raise ValueError("Missing original class and action CSV provenance")
    original = {}
    with csv_file.open("r", encoding="utf-8-sig", newline="") as stream:
        for source in csv.DictReader(stream):
            if set(source) != {"path", "label", "start", "end", "subject", "cam", "dataset"}:
                raise ValueError("Unexpected original CSV schema")
            if source["dataset"] != "caucafall" or source["cam"] != "1":
                raise ValueError("Unrecognized original dataset or camera")
            key = (source["subject"], int(source["label"]),
                   source["path"].split("/")[-1],
                   round(float(source["start"]) * 1000),
                   round(float(source["end"]) * 1000))
            if key in original:
                raise ValueError("Duplicate original CSV provenance")
            original[key] = source["path"].split("/")[0]
    found = set()
    records = []
    for line in lines:
        parts = line.rsplit(" ", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError("Invalid MMAction label row")
        raw, label = parts[0], int(parts[1])
        if label not in CLASS_NAMES or not re.fullmatch(
            r"Subject\.(?:10|[1-9])[/\\][A-Za-z0-9_.-]+\.avi", raw
        ):
            raise ValueError("Unexpected class or unsafe clip path")
        relative = raw.replace("\\", "/")
        if relative in found:
            raise ValueError("Duplicate publisher annotation")
        found.add(relative)
        subject = relative.split("/")[0].split(".")[1]
        fields = Path(relative).stem.rsplit("_", 6)
        if len(fields) != 7 or int(fields[1]) != label or fields[4] != subject:
            raise ValueError("Annotated crop disagrees with publisher label/subject")
        try:
            key = (subject, label, fields[0], round(float(fields[2]) * 1000),
                   round(float(fields[3]) * 1000))
            source_group = original[key]
        except (KeyError, ValueError) as exc:
            raise ValueError("Annotated crop has no matching original CSV interval") from exc
        video = (root / "clips" / relative).resolve()
        if not video.is_relative_to((root / "clips").resolve()) or not video.is_file():
            raise ValueError("Publisher annotation references missing/escaping file")
        if not 0 < video.stat().st_size <= MAX_SOURCE_BYTES:
            raise ValueError("Invalid publisher clip size")
        records.append({
            "relative": "clips/" + relative,
            "subject": subject,
            "class_id": label,
            "action": CLASS_NAMES[label],
            "source_group": source_group,
        })
    return records


def _origin_recording_id(relative: str) -> str:
    name = Path(relative).stem
    # Dataset crop pattern: TakeName_Class_Start_End_Subject_Camera_Dataset.
    fields = name.rsplit("_", 6)
    if len(fields) != 7 or not fields[1].isdigit():
        raise ValueError("Unable to recover original take identity")
    slug = re.sub(r"[^a-z0-9]+", "-", fields[0].lower()).strip("-")
    if not slug:
        raise ValueError("Missing source recording identity")
    return slug


def _sha256_file(path: Path) -> str:
    hash_obj = sha256()
    with path.open("rb") as fd:
        for block in iter(lambda: fd.read(1024 * 1024), b""):
            hash_obj.update(block)
    return hash_obj.hexdigest()


def curate(root: Path, *, per_class_per_subject: int = 2,
           metadata_reader=_video_metadata) -> tuple[dict, dict, dict]:
    """Select 2 fall motions + 2 clean ADLs per subject, no hidden relabeling.

    Each publisher annotation is a cropped clip; timestamps here are *clip
    local*, not original-long-video timestamps. The per-clip proposal still
    requires a real reviewer: label_reviewed is never automatically true.
    """
    if type(per_class_per_subject) is not int or not 1 <= per_class_per_subject <= 3:
        raise ValueError("per_class_per_subject must be between 1 and 3")
    root = root.resolve(strict=True)
    records = read_publisher_annotations(root)
    all_counts = Counter(r["class_id"] for r in records)
    groups = {"version": 2, "permission_basis":
              "CC BY 4.0 publisher-labeled CAUCAFall derivative, Zenodo 17170592; "
              "manual clip-label review outstanding", "clips": []}
    proposals = {"version": 1, "segments": []}
    selected_stats = Counter()
    selections = []
    for subject in range(1, 11):
        sid = str(subject)
        candidates = {"fall": [], "adl": []}
        for record in records:
            if record["subject"] != sid:
                continue
            label = record["class_id"]
            if label == 1 and record["source_group"] in {"side", "forward", "backwards"}:
                group = "fall"
            elif label in ADL_CLASSES and record["source_group"] == "adl":
                group = "adl"
            else:
                continue  # fallen/unknown and cropped pre/post fall take excluded
            video = root / record["relative"]
            frames, fps = metadata_reader(video)
            end_ms = int((frames - 1) / fps * 1000)
            if not 900 <= end_ms <= 8000:
                continue
            candidates[group].append((record, video, end_ms))
        # Diverse actions first, deterministic independent of target model scores.
        for group in ("fall", "adl"):
            preference = (["FallForward", "FallRight", "FallLeft",
                           "FallBackwards", "FallSitting"] if group == "fall"
                          else ["SitDown", "Walk", "Pickupobject", "Kneel"])
            def ranking(entry):
                name = Path(entry[0]["relative"]).name
                priority = next((i for i, p in enumerate(preference)
                                 if name.startswith(p)), len(preference))
                return (priority, name)
            choices = sorted(candidates[group], key=ranking)
            chosen = []
            seen_actions = set()
            for row in choices:
                action = _origin_recording_id(row[0]["relative"])
                if action not in seen_actions:
                    chosen.append(row)
                    seen_actions.add(action)
                if len(chosen) == per_class_per_subject:
                    break
            if len(chosen) < per_class_per_subject:
                raise ValueError("Not enough independent annotated action takes")
            for record, video, end_ms in chosen:
                action = _origin_recording_id(record["relative"])
                cid = f"cauca-s{subject:02d}-{action}"
                label = group == "fall"
                groups["clips"].append({
                    "clip_id": cid, "dataset_id": DATASET_ID,
                    "subject_id": f"cauca-subject-{subject:02d}",
                    "recording_id": f"cauca-s{subject:02d}-{action}",
                    "split": SUBJECT_SPLITS[sid],
                    "expected_fall": label,
                    "media_sha256": _sha256_file(video),
                })
                proposals["segments"].append({
                    "clip_id": cid, "video": record["relative"],
                    "start_ms": 0, "end_ms": end_ms, "expected_fall": label,
                    "label_reviewed": False,
                    "annotation_basis": (
                        f"Publisher MMAction2 class {record['class_id']} "
                        f"({record['action']}); manual interval review pending"
                    ),
                })
                selections.append(record)
                selected_stats[(SUBJECT_SPLITS[sid], group)] += 1
    audit = audit_subject_splits(groups)
    summary = {
        "source": "CAUCAFall OmniFall repack, Zenodo 17170592",
        "license": "CC BY 4.0 with attribution; participant review pending",
        "annotation_rows": len(records),
        "publisher_class_counts": {CLASS_NAMES[i]: all_counts[i] for i in sorted(CLASS_NAMES)},
        "selected": {
            split: {"fall": selected_stats[(split, "fall")],
                    "adl": selected_stats[(split, "adl")]}
            for split in ("train", "val", "test")
        },
        "split_audit": audit,
        "manual_label_review_completed": False,
        "ready_for_reviewed_window_export": False,
        "fall_label_definition": "publisher class 1 fall motion ONLY",
        "adl_label_definition": "publisher classes 0/3/4/7/8 under adl folder ONLY",
        "excluded_classes": [2, 5, 6, 9],
        "selection_never_uses_heldout_model_scores": True,
        "raw_media_committed": False,
        "selected_records": len(selections),
    }
    return groups, proposals, summary


def _wilson_95(hits: int, n: int) -> dict:
    """Descriptive Wilson score bounds for tiny research samples, NOT safety CI."""
    if type(hits) is not int or type(n) is not int or not 0 <= hits <= n:
        raise ValueError("Success count must be within 0..n")
    if n == 0:
        return {"hits": 0, "n": 0, "lower": None, "upper": None}
    z = 1.959963984540054
    rate = hits / n
    correction = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / correction
    half = (z / correction) * sqrt(rate * (1 - rate) / n + z * z / (4 * n * n))
    return {"hits": hits, "n": n,
            "lower": round(max(0.0, center - half), 4),
            "upper": round(min(1.0, center + half), 4)}


def publisher_label_pilot(root: Path, model: Path, groups: dict,
                          proposals: dict, *, collector=None, trainer=None,
                          dataset_origin="CAUCAFall OmniFall publisher action annotations") -> dict:
    """Opt-in REAL publisher-labeled, *unreviewed* pilot: no production claims.

    Unlike window_export, this uses publisher's action annotations as-is and
    truthfully says there was NO separate manual event review. No footage
    or pose features are saved. Only aggregate model metrics are returned.
    """
    from sentinel_edge.video_benchmark import collect_video_frames
    run_collector = collector or collect_video_frames
    root = root.resolve(strict=True)
    audit_subject_splits(groups)
    if len(groups["clips"]) != len(proposals["segments"]):
        raise ValueError("Proposal count mismatch")
    segments = {s["clip_id"]: s for s in proposals["segments"]}
    if len(segments) != len(proposals["segments"]):
        raise ValueError("Duplicate proposal IDs")
    if model.suffix != ".task" or not model.is_file():
        raise ValueError("Local official Pose task model missing")
    windows = {"version": 1, "feature_set": "experimental_pose_motion_v1",
               "windows": []}
    excluded = Counter()
    accepted = set()
    heuristic_detections = {}
    for item in groups["clips"]:
        cid = item["clip_id"]
        spec = segments.get(cid)
        if spec is None or spec["label_reviewed"] is not False or (
            spec["expected_fall"] != item["expected_fall"]
        ):
            raise ValueError("Expected unreviewed publisher label only; manual review must be separate")
        video = (root / spec["video"]).resolve(strict=True)
        if not video.is_relative_to(root / "clips"):
            raise ValueError("Source video outside curated root")
        if _sha256_file(video) != item["media_sha256"]:
            raise ValueError("Media changed after curation")
        sample = NearestFrameSampler(cid, spec["start_ms"], spec["end_ms"])
        observed_candidates = []
        frames, stats = run_collector(
            video, clip_id=cid, model=model, max_frames=6000,
            frame_consumer=sample.on_frame, event_consumer=observed_candidates.append,
        )
        if frames or stats["frames_processed"] != sample.frames_processed:
            raise ValueError("Streaming decoder inconsistency")
        try:
            derived = sample.finish()
        except ValueError as exc:
            if "Too few valid poses" not in str(exc):
                raise
            # Predefined label-independent pose-quality gate. Exclusions
            # are reported and are NOT evidence of real-world reliability.
            excluded[(item["split"], item["expected_fall"])] += 1
            continue
        accepted.add(cid)
        heuristic_detections[cid] = bool(observed_candidates)
        windows["windows"].append({"clip_id": cid, "features": derived})
    eligible_groups = dict(groups)
    eligible_groups["clips"] = [
        item for item in groups["clips"] if item["clip_id"] in accepted
    ]
    audit_subject_splits(eligible_groups)  # Fail if either label vanishes.
    _, result = (trainer or train_and_evaluate)(eligible_groups, windows)
    heldout = [item for item in eligible_groups["clips"] if item["split"] == "test"]
    result["original_heuristic_heldout_test_same_clips"] = _metrics(
        [item["expected_fall"] for item in heldout],
        [heuristic_detections[item["clip_id"]] for item in heldout],
    )
    result["comparison_notice"] = (
        "Original heuristic and research classifier evaluated on the same "
        "pose-eligible held-out subjects, not all recorded videos. Neither "
        "result establishes real-world fall-alarm reliability."
    )
    # Never hide pose-unreadable clips behind an eligible-only confusion matrix.
    # Aggregate by label/split, without exposing person IDs or motion windows.
    selected_counts = Counter(
        (item["split"], item["expected_fall"]) for item in groups["clips"]
    )
    coverage = {}
    for split in ("train", "val", "test"):
        coverage[split] = {}
        for label, fall in (("fall", True), ("adl", False)):
            selected = selected_counts[(split, fall)]
            abstained = excluded[(split, fall)]
            coverage[split][label] = {
                "selected": selected,
                "eligible": selected - abstained,
                "abstained": abstained,
                "coverage": round((selected - abstained) / selected, 5)
                if selected else None,
            }
    result["pose_quality_filter"] = {
        "coverage_by_split_and_label": coverage,
        "minimum_observed_of_30": 10,
        "input_clips": len(groups["clips"]),
        "eligible_clips": len(accepted),
        "rejected_for_low_pose_visibility": sum(excluded.values()),
        "excluded_by_split_and_label": {
            split: {"fall": excluded[(split, True)],
                    "adl": excluded[(split, False)]}
            for split in ("train", "val", "test")
        },
        "selection_bias_warning": (
            "Metrics are conditional on pose-readable clips and cannot "
            "estimate performance on all original recordings."
        ),
    }
    heldout_scores = result["heldout_test"]
    test_fall = coverage["test"]["fall"]
    test_adl = coverage["test"]["adl"]
    result["heldout_uncertainty"] = {
        "eligible_only": True,
        "selected_heldout_clips": test_fall["selected"] + test_adl["selected"],
        "scored_heldout_clips": test_fall["eligible"] + test_adl["eligible"],
        "unscored_heldout_clips": test_fall["abstained"] + test_adl["abstained"],
        "fall_recall_wilson_95": _wilson_95(
            heldout_scores["true_positive"], test_fall["eligible"],
        ),
        "adl_specificity_wilson_95": _wilson_95(
            heldout_scores["true_negative"], test_adl["eligible"],
        ),
        "interpretation": (
            "Approximate 95% Wilson intervals describe this fixed, tiny, "
            "pose-eligible publisher-labeled subset only; not population "
            "confidence bounds. Unscored videos are abstentions, not "
            "correct classifications. No clinical/safety reliability claim."
        ),
    }
    result["dataset_origin"] = dataset_origin
    result["publisher_labels_only"] = True
    result["independent_human_label_review"] = False
    result["prototype_research_only"] = True
    result["production_alerts_enabled"] = False
    result["reliability_proven"] = False
    result["raw_features_saved"] = False
    return result


def _private_new(path: Path) -> Path:
    return _private_output_path(path)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Private CAUCAFall publisher label curation")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--groups-out", type=Path, required=True)
    parser.add_argument("--segments-out", type=Path, required=True)
    parser.add_argument("--model", type=Path, help="For research-only in-memory pilot")
    parser.add_argument("--publisher-label-pilot", action="store_true",
                        help="Opt-in publisher-labeled unreviewed local model fit")
    args = parser.parse_args(argv)
    if args.publisher_label_pilot and args.model is None:
        parser.error("--model required for publisher-label pilot")
    try:
        for output in (args.groups_out, args.segments_out):
            _private_new(output)
        groups, proposals, summary = curate(args.root)
        if args.publisher_label_pilot:
            summary["experimental_training"] = publisher_label_pilot(
                args.root, args.model, groups, proposals
            )
        # Exclusive private output, no overwrite, no raw media.
        with args.groups_out.open("x", encoding="utf8") as stream:
            json.dump(groups, stream, indent=2)
        with args.segments_out.open("x", encoding="utf8") as stream:
            json.dump(proposals, stream, indent=2)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
