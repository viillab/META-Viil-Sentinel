"""ASSIST-IoT externally sourced hard-negative stress, no fitting or promotion.

Video references have no clip-level subject identities or independently
reviewed event onsets. This reports only diagnostic whole-clip predictions.
Raw frames/landmarks and model parameters never leave private local memory.
"""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from sentinel_edge.caucafall_curator import _video_metadata, _sha256_file
from sentinel_edge.contracts import PoseFeatures
from sentinel_edge.private_model_training import read_private_artifact
from sentinel_edge.pose_rejection_diagnostics import REASONS
from sentinel_edge.multipose_spatial_diagnostics import MULTIPOSE_CATEGORIES
from sentinel_edge.public_dataset_ingest import _github_blob_sha1
from sentinel_edge.temporal_training import pool_temporal_window
from sentinel_edge.video_benchmark import collect_video_frames
from sentinel_edge.window_export import NearestFrameSampler, _private_output_path

DATASET = "ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset"
PINNED_COMMIT = "7a11c96b9a3576cef92f0795a19b3786c69a3335"
SOURCE_URL = f"https://raw.githubusercontent.com/{DATASET}/{PINNED_COMMIT}"
SOURCE_LICENSE = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
DOI = "10.5281/zenodo.8340428"
# Frozen independent of external video predictions: previous jointly fitted
# CAUCAFall+GMDCSA-24 model, numeric parameters saved only to data/private.
EXPECTED_MODEL_SHA256 = "2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab"
MAX_TOTAL_BYTES = 42 * 1024 * 1024
MAX_CLIP_BYTES = 9 * 1024 * 1024
# group, exact public filename, exact bytes, Git tree blob SHA1.
# Selected by *activity description* BEFORE any frozen-model evaluation.
CATALOG = (
    ("adl", "09_low_chair_sitting_quickly.mp4", 1681435, "78cd01c91598710f5abac3e8ead5f856ba4b85f7"),
    ("adl", "10_collapsing_onto_chair.mp4", 2494982, "dddf82afb956a5f32d887e3dcb8d1aefc63a3d40"),
    ("adl", "12_sitting_laying_down_quickly.mp4", 2702255, "efee2b70a78eead75623b954b8ac8b7ac393fdee"),
    ("adl", "13_bending_at_knees.mp4", 1353104, "077030d73c39e27250706809983f6ce555e06245"),
    ("adl", "14_bending_wo_knees.mp4", 1774202, "2ed3b492327d88d9848a29237f75aa9c7f1dcb4e"),
    ("adl", "15_stumbling.mp4", 1286514, "2f70c1e223da1fdb9254c8ad802fe1ed47cc499e"),
    ("adl", "16_jumping_reaching.mp4", 803073, "6b95aeee3c624ecd519ed5fbbf7ee74f3e224d63"),
    ("adl", "17_crawling.mp4", 1866191, "4edd281e63ffc44360e28b0e7335f3063c6a256b"),
    ("fall", "01_forward_fall_walking.mp4", 4409845, "6001d9fc65d3ec08ef16cd051271b5c2c6d24775"),
    ("fall", "02_fall_backward.mp4", 5047305, "47f0571868cfea894222d5c37abe0a45517d946a"),
    ("fall", "05_vertical_fall_faint.mp4", 2164420, "971487fae13a885bda9bf9ada413ac39deb71add"),
)
assert sum(item[2] for item in CATALOG) < MAX_TOTAL_BYTES


def private_root(path: Path) -> Path:
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    target = path.resolve()
    if not target.is_relative_to(private):
        raise ValueError("All media/report files must stay in ignored data/private")
    return target


def source_url(group: str, name: str) -> str:
    if not any(g == group and n == name for g, n, _, _ in CATALOG):
        raise ValueError("Video source outside frozen allowlist")
    return f"{SOURCE_URL}/videos/{group}/{name}"


def _download(url: str, size: int) -> bytes:
    # _fetch_binary() in the earlier downloader is hard-pinned to GMDCSA;
    # fetch ASSIST only from the immutable SHA + fixed names above.
    from urllib.request import Request, urlopen
    if not url.startswith(SOURCE_URL + "/videos/"):
        raise ValueError("Non-pinned external source")
    with urlopen(Request(url, headers={"User-Agent": "VIIL-Sentinel-research/1.0"}),
                 timeout=45) as res:
        if res.status != 200:
            raise ValueError("Source HTTP response not successful")
        chunks, length = [], 0
        while True:
            chunk = res.read(min(65536, size + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            if length > size:
                raise ValueError("External video exceeds pinned length")
            chunks.append(chunk)
    return b"".join(chunks)


def verify_download(root: Path, *, fetcher=None, metadata_reader=_video_metadata) -> dict:
    """Idempotent private-only download, exact pinned SHA1 Git blob identity."""
    root = private_root(root)
    if root.exists() and not root.is_dir():
        raise ValueError("Dataset root cannot be a file")
    root.mkdir(parents=True, exist_ok=True)
    downloader = fetcher or _download
    reused = fetched = 0
    manifest = {"version": 1, "dataset": DATASET, "commit": PINNED_COMMIT,
                "license": SOURCE_LICENSE, "source_doi": DOI,
                "labels_independently_reviewed": False,
                "subject_identities_for_reference_videos": "unknown",
                "clips": []}
    for group, name, size, blob_sha in CATALOG:
        if size > MAX_CLIP_BYTES:
            raise ValueError("Source exceeds hard per-video byte limit")
        url = source_url(group, name)
        path = root / "clips" / group / name
        if not path.resolve().is_relative_to(root):
            raise ValueError("Media path escaped private root")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not path.is_file():
                raise ValueError("Invalid preexisting media")
            data = path.read_bytes()
            reused += 1
        else:
            data = downloader(url, size)
            if len(data) != size or _github_blob_sha1(data) != blob_sha:
                raise ValueError("Downloaded source fails expected Git blob digest")
            if not data.startswith(b"\x00\x00") or b"ftyp" not in data[:32]:
                raise ValueError("Unexpected MP4 format")
            with path.open("xb") as out:
                out.write(data)
            fetched += 1
        if len(data) != size or _github_blob_sha1(data) != blob_sha:
            raise ValueError("Source footage modified: refusing to use")
        frames, fps = metadata_reader(path)
        ms = int((frames - 1) * 1000 / fps)
        if not 900 <= ms <= 90000:
            raise ValueError("Reference clip is too short or too long")
        manifest["clips"].append({
            "activity": name.removesuffix(".mp4"),
            "class": group,
            "video": f"clips/{group}/{name}",
            "source_bytes": size,
            "media_sha256": sha256(data).hexdigest(),
            "duration_ms": ms,
        })
    target = root / "assist-frozen-video-manifest-v1.json"
    if target.exists():
        if json.loads(target.read_text("utf-8")) != manifest:
            raise ValueError("Existing private manifest drift")
    else:
        with target.open("x", encoding="utf8") as out:
            json.dump(manifest, out, indent=2)
    return {
        "selected": len(CATALOG), "adl": sum(a[0] == "adl" for a in CATALOG),
        "fall": sum(a[0] == "fall" for a in CATALOG),
        "total_bytes": sum(item[2] for item in CATALOG),
        "verified_reused": reused, "new_downloads": fetched,
        "subject_identity_verified": False, "manual_label_review": False,
        "source_git_commit": PINNED_COMMIT,
    }


def windows_of(duration_ms: int) -> list[tuple[int, int]]:
    """Predeclared non-overlap up to 8s; never infer fall-onset timestamps."""
    if not isinstance(duration_ms, int) or not 900 <= duration_ms <= 90000:
        raise ValueError("Invalid external reference duration")
    ends = []
    start = 0
    while duration_ms - start >= 900:
        end = min(start + 8000, duration_ms)
        ends.append((start, end))
        start = end
    if not ends or len(ends) > 12:
        raise ValueError("No bounded 30-frame temporal windows")
    return ends


def _evaluate_one(path: Path, group: str, activity: str, duration_ms: int,
                  pose_task: Path, model, *, collector=collect_video_frames,
                  spatial_audit=False,
                  detailed_reasons=False,
                  diagnostics=False) -> dict:
    windows = [NearestFrameSampler(activity, start, end)
               for start, end in windows_of(duration_ms)]
    if spatial_audit and not detailed_reasons:
        raise ValueError("Spatial analysis requires detailed pose reason audit")
    if detailed_reasons and not diagnostics:
        raise ValueError("Rejection reasons require failure diagnostics")
    reason_counts = Counter()
    spatial_counts = Counter()
    raw_torso_frames = geometric_valid_frames = 0
    def consume(frame):
        nonlocal raw_torso_frames, geometric_valid_frames
        if diagnostics:
            raw_torso_frames += bool(frame.landmarks)
            geometric_valid_frames += (PoseFeatures.from_frame(frame, .55) is not None)
        for sampler in windows:
            sampler.on_frame(frame)
    extra = {}
    if detailed_reasons:
        def consume_reason(reason):
            if reason not in REASONS:
                raise ValueError("Unexpected pose adapter reason")
            reason_counts.update((reason,))
        extra["pose_reason_consumer"] = consume_reason
    if spatial_audit:
        def consume_spatial(category):
            if category not in MULTIPOSE_CATEGORIES:
                raise ValueError("Invalid geometry category")
            spatial_counts.update((category,))
        extra["multipose_category_consumer"] = consume_spatial
    frames, stats = collector(
        path, clip_id=activity, model=pose_task, max_frames=6000,
        frame_consumer=consume, event_consumer=lambda _: None,
        **extra,
    )
    if frames or stats["frames_processed"] != windows[0].frames_processed:
        raise ValueError("Inconsistent pose stream frame counts")
    successes, abstentions = [], 0
    sampled_visible = 0
    margin_bands = {"clearly_below": 0, "near_below": 0, "candidate": 0}
    for sampler in windows:
        try:
            features = sampler.finish()
        except ValueError as exc:
            if "Too few valid poses" not in str(exc):
                raise
            abstentions += 1
            continue
        probability = float(model.predict_probability(pool_temporal_window(features)))
        if diagnostics:
            sampled_visible += sum(row[-1] == 1 for row in features)
            band = ("candidate" if probability >= model.threshold else
                    "near_below" if probability >= model.threshold - .2 else
                    "clearly_below")
            margin_bands[band] += 1
        successes.append(float(probability))
    result = {"activity": activity, "publisher_class": group,
            "selected_windows": len(windows),
            "pose_eligible_windows": len(successes),
            "pose_abstentions": abstentions,
            "any_window_fall_candidate": (
                any(p >= model.threshold for p in successes) if successes else None
            ),
            "fully_pose_covered": abstentions == 0}
    if detailed_reasons:
        if (sum(reason_counts.values()) != stats["frames_processed"]
                or reason_counts["accepted"] != raw_torso_frames):
            raise ValueError("Adapter rejection counters contradict frame stream")
        if spatial_audit:
            if (sum(spatial_counts.values()) != stats["frames_processed"]
                    or spatial_counts["not_multiple"] !=
                    stats["frames_processed"] - reason_counts["multiple_people"]):
                raise ValueError("Spatial categories contradict adapter frame counts")
            result["multipose_spatial_categories"] = {
                category: spatial_counts[category]
                for category in MULTIPOSE_CATEGORIES
            }
        result["pose_rejection_reasons"] = {
            reason: reason_counts[reason] for reason in REASONS
        }
    if diagnostics:
        if not (0 <= geometric_valid_frames <= raw_torso_frames <= stats["frames_processed"]):
            raise ValueError("Contradictory pose pipeline counters")
        if sum(margin_bands.values()) != len(successes):
            raise ValueError("Diagnostic score groups must match eligible windows")
        if not 0 <= stats["candidate_events"] <= stats["frames_processed"]:
            raise ValueError("Invalid legacy heuristic event count")
        result["failure_diagnostic"] = {
            "decoded_frames": stats["frames_processed"],
            "torso_adapter_available_frames": raw_torso_frames,
            "motion_geometry_eligible_frames": geometric_valid_frames,
            "unavailable_at_adapter_frames": stats["frames_processed"] - raw_torso_frames,
            "unavailable_at_geometry_after_adapter": raw_torso_frames - geometric_valid_frames,
            "eligible_window_sampled_visible_frames": sampled_visible,
            "legacy_heuristic_event_count": stats["candidate_events"],
            "frozen_score_bands": margin_bands,
            "pose_missing_windows_not_scored": abstentions,
        }
    return result


def summarize_class(rows: list[dict], group: str) -> dict:
    """Separate fully observed negative videos from partial-pose unknowns."""
    if group not in ("adl", "fall"):
        raise ValueError("Unexpected reference class")
    subset = [r for r in rows if r["publisher_class"] == group]
    eligible = [r for r in subset if r["any_window_fall_candidate"] is not None]
    flagged = sum(r["any_window_fall_candidate"] is True for r in eligible)
    return {
        "total_videos": len(subset),
        "video_pose_eligible": len(eligible),
        "video_pose_abstained": len(subset) - len(eligible),
        "windows_attempted": sum(r["selected_windows"] for r in subset),
        "windows_eligible": sum(r["pose_eligible_windows"] for r in subset),
        "windows_abstained": sum(r["pose_abstentions"] for r in subset),
        "any_window_fall_candidate_videos": flagged,
        "no_fall_candidate_videos": len(eligible) - flagged,
        "fully_pose_covered_videos": sum(r["fully_pose_covered"] for r in subset),
        "partly_pose_abstained_videos": sum(not r["fully_pose_covered"] for r in subset),
        "fully_covered_no_candidate_videos": sum(
            r["fully_pose_covered"] and r["any_window_fall_candidate"] is False
            for r in subset
        ),
    }


def summarize_failure_diagnostics(rows: list[dict], group: str) -> dict:
    """Aggregate counts only: never pose vectors or personal time traces.

    Adapter emptiness can have multiple causes (including ambiguous second
    person, low confidence, off-image pose). This cannot establish causality.
    """
    if group not in ("adl", "fall"):
        raise ValueError("Invalid diagnostic reference group")
    subset = [r for r in rows if r["publisher_class"] == group]
    if not subset or any("failure_diagnostic" not in r for r in subset):
        raise ValueError("All diagnostic activities must have complete counters")
    diag = [r["failure_diagnostic"] for r in subset]
    keys = ("decoded_frames", "torso_adapter_available_frames",
            "motion_geometry_eligible_frames", "unavailable_at_adapter_frames",
            "unavailable_at_geometry_after_adapter",
            "eligible_window_sampled_visible_frames", "legacy_heuristic_event_count")
    totals = {k: sum(x[k] for x in diag) for k in keys}
    bands = {
        name: sum(x["frozen_score_bands"][name] for x in diag)
        for name in ("clearly_below", "near_below", "candidate")
    }
    if (totals["motion_geometry_eligible_frames"] > totals["decoded_frames"]
            or totals["torso_adapter_available_frames"] > totals["decoded_frames"]
            or totals["unavailable_at_adapter_frames"] +
            totals["torso_adapter_available_frames"] != totals["decoded_frames"]
            or totals["unavailable_at_geometry_after_adapter"] +
            totals["motion_geometry_eligible_frames"] !=
            totals["torso_adapter_available_frames"]
            or sum(bands.values()) != sum(r["pose_eligible_windows"] for r in subset)):
        raise ValueError("Inconsistent diagnostic aggregate counts")
    return {
        "reference_videos": len(subset),
        **totals,
        "frozen_classifier_score_bands": bands,
        "videos_with_original_heuristic_candidates": sum(
            d["legacy_heuristic_event_count"] > 0 for d in diag
        ),
        "videos_with_frozen_classification_candidates": sum(
            r["any_window_fall_candidate"] is True for r in subset
        ),
        "videos_with_partial_pose_coverage": sum(
            not r["fully_pose_covered"] for r in subset
        ),
        "cause_not_identified_from_counts_alone": True,
        "original_heuristic_and_classification_not_same_event_contract": True,
    }


def aggregate_pose_rejection_reasons(rows: list[dict], group: str) -> dict:
    """Only source-level categorical integers, never raw MediaPipe outputs."""
    if group not in ("adl", "fall"):
        raise ValueError("Invalid pose-rejection group")
    subset = [r for r in rows if r["publisher_class"] == group]
    if not subset or any("pose_rejection_reasons" not in r for r in subset):
        raise ValueError("Missing opt-in pose-rejection diagnostic evidence")
    combined = Counter()
    for row in subset:
        counts = row["pose_rejection_reasons"]
        if (set(counts) != set(REASONS)
                or any(type(value) is not int or value < 0
                       for value in counts.values())
                or sum(counts.values()) != row["failure_diagnostic"]["decoded_frames"]
                or counts["accepted"] != row["failure_diagnostic"][
                    "torso_adapter_available_frames"
                ]):
            raise ValueError("Pose-rejection count contradicted stream")
        combined.update(counts)
    return {
        "videos": len(subset),
        "decoded_frames": sum(combined.values()),
        "accepted_frames": combined["accepted"],
        "rejected_frames": sum(combined.values()) - combined["accepted"],
        "reason_frame_counts": {reason: combined[reason] for reason in REASONS},
        "reason_counts_not_root_cause": True,
        "raw_pose_recorded": False,
    }


def aggregate_multipose_spatial(rows: list[dict], group: str) -> dict:
    """Only bounded categorical totals; no positions or individual tracking."""
    if group not in ("fall", "adl"):
        raise ValueError("Unexpected spatial audit class")
    subset = [r for r in rows if r["publisher_class"] == group]
    if not subset or any("multipose_spatial_categories" not in r for r in subset):
        raise ValueError("Missing opt-in spatial audit counters")
    totals = Counter()
    for item in subset:
        counts = item["multipose_spatial_categories"]
        reasons = item["pose_rejection_reasons"]
        if (set(counts) != set(MULTIPOSE_CATEGORIES)
                or any(type(v) is not int or v < 0 for v in counts.values())
                or sum(counts.values()) != item["failure_diagnostic"]["decoded_frames"]
                or sum(v for k, v in counts.items() if k != "not_multiple")
                != reasons["multiple_people"]):
            raise ValueError("Spatial audit frame categories inconsistent")
        totals.update(counts)
    return {
        "videos": len(subset),
        "decoded_frames": sum(totals.values()),
        "multi_pose_frames": sum(
            totals[c] for c in MULTIPOSE_CATEGORIES if c != "not_multiple"
        ),
        "spatial_categories": {c: totals[c] for c in MULTIPOSE_CATEGORIES},
        "no_person_identity_or_duplicate_proven": True,
        "research_only_multi_person_abstention_unchanged": True,
    }


def evaluate_external(root: Path, pose_task: Path, frozen_model_path: Path,
                      report_path: Path, *, collector=collect_video_frames,
                      detailed_reasons=False,
                      spatial_audit=False,
                      diagnostics=False) -> dict:
    """One-shot source-frozen external video stress; NEVER trains or tunes."""
    if spatial_audit and not (detailed_reasons and diagnostics):
        raise ValueError("Spatial audit requires both reason and frame diagnostics")
    root = private_root(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("No external research root")
    report_path = _private_output_path(report_path)
    frozen_model_path = private_root(frozen_model_path).resolve(strict=True)
    if _sha256_file(frozen_model_path) != EXPECTED_MODEL_SHA256:
        raise ValueError("Frozen model artifact SHA256 changed; refuse rescore")
    model = read_private_artifact(frozen_model_path)
    if abs(model.threshold - .53) > 1e-8:
        raise ValueError("Frozen validation-only threshold changed")
    manifest_path = root / "assist-frozen-video-manifest-v1.json"
    manifest = json.loads(manifest_path.read_text("utf8"))
    if set(manifest) != {
        "version", "dataset", "commit", "license", "source_doi",
        "labels_independently_reviewed", "subject_identities_for_reference_videos",
        "clips",
    } or manifest["commit"] != PINNED_COMMIT or manifest["dataset"] != DATASET or (
        manifest["license"] != SOURCE_LICENSE or manifest["source_doi"] != DOI
        or manifest["labels_independently_reviewed"] is not False
        or manifest["subject_identities_for_reference_videos"] != "unknown"
    ):
        raise ValueError("Unexpected dataset manifest schema or revision")
    expected = {(group, name): (size, blob) for group, name, size, blob in CATALOG}
    if len(manifest["clips"]) != len(expected):
        raise ValueError("External subset size has changed")
    plan = []
    # Preflight EVERY actual MP4 hash before starting any inference.
    for item in manifest["clips"]:
        group, activity = item["class"], item["activity"]
        name = activity + ".mp4"
        if (group, name) not in expected:
            raise ValueError("Unrecognized external activity")
        path = (root / "clips" / group / name).resolve(strict=True)
        if not path.is_relative_to(root / "clips") or path.stat().st_size != expected[(group, name)][0]:
            raise ValueError("External video path/size differs from pinned source")
        if (item["media_sha256"] != _sha256_file(path)
                or _github_blob_sha1(path.read_bytes()) != expected[(group, name)][1]):
            raise ValueError("External video content hash does not match manifest")
        duration = item["duration_ms"]
        if type(duration) is not int:
            raise ValueError("Invalid reference video duration")
        frames, fps = _video_metadata(path)
        if int((frames - 1) * 1000 / fps) != duration:
            raise ValueError("External video duration changed")
        plan.append((path, group, activity, duration))
    if len({activity for _, _, activity, _ in plan}) != len(expected):
        raise ValueError("Repeated reference video activity")
    rows = [
        _evaluate_one(path, group, activity, duration, pose_task,
                      model, collector=collector, diagnostics=diagnostics,
                      detailed_reasons=detailed_reasons,
                      spatial_audit=spatial_audit)
        for path, group, activity, duration in plan
    ]
    by_class = {
        group: summarize_class(rows, group) for group in ("adl", "fall")
    }
    report = {
        "mode": ("research_only_external_frozen_failure_diagnostics" if diagnostics
                 else "research_only_external_frozen_reference_video_stress"),
        "source": DATASET, "source_commit": PINNED_COMMIT, "license": SOURCE_LICENSE,
        "model_origin": "joint_cauca_gmdcsa_v1_prior_trained",
        "model_sha256": EXPECTED_MODEL_SHA256,
        "threshold_selection": "unchanged_prior_validation_only",
        "threshold": .53,
        "activity_window_seconds": "non-overlap up to 8",
        "labels_publisher_only": True,
        "reference_video_subjects_unknown": True,
        "no_training_or_threshold_tuning": True,
        "fall_event_onset_reviewed": False,
        "video_reference_only_not_independent_subject_holdout": True,
        "not_production_safety_evidence": True,
        "alerts_enabled": False,
        "adls_are_hard_negatives_not_monitored_hours": True,
        "metrics": by_class,
        # Public action labels only, no faces, pose windows or individual scores.
        "activity_outcomes": rows,
    }
    if diagnostics:
        report["failure_attribution"] = {
            group: summarize_failure_diagnostics(rows, group)
            for group in ("adl", "fall")
        }
        report["diagnostic_only_not_causal_proof"] = True
    if detailed_reasons:
        report["adapter_rejection_reason_counts"] = {
            group: aggregate_pose_rejection_reasons(rows, group)
            for group in ("adl", "fall")
        }
        report["pose_reasons_describe_adapter_gates_not_physical_cause"] = True
    if spatial_audit:
        report["multipose_spatial_summary"] = {
            group: aggregate_multipose_spatial(rows, group)
            for group in ("adl", "fall")
        }
        report["spatial_categories_are_not_real_person_counts"] = True
    with report_path.open("x", encoding="utf8") as out:
        json.dump(report, out, indent=2)
    return report


def main(argv=None) -> int:
    parser = ArgumentParser(description="Externally sourced frozen-video research only")
    parser.add_argument("--mode", choices=("download", "evaluate", "diagnose",
                                            "reason-audit", "spatial-audit"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--pose-task", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Require publisher-label and pose-privacy acknowledgement")
    try:
        if args.mode == "download":
            if args.model or args.pose_task or args.report:
                parser.error("download mode accepts --root only")
            result = verify_download(args.root)
        else:
            if not all((args.model, args.pose_task, args.report)):
                parser.error("evaluate requires --model, --pose-task and --report")
            result = evaluate_external(
                args.root, args.pose_task, args.model, args.report,
                diagnostics=(args.mode in ("diagnose", "reason-audit", "spatial-audit")),
                detailed_reasons=(args.mode in ("reason-audit", "spatial-audit")),
                spatial_audit=(args.mode == "spatial-audit"),
            )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.error("External frozen evaluation refused: " + str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
