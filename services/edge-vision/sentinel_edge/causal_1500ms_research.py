"""New 1.5-second TRAINED temporal research baseline, never a fall alarm.

Uses publisher staged action labels, NOT human-verified event onsets. All
original media SHA256/full-decode checked. No video/poses/model weights
exported, no camera API/incident hooks or legacy 8-second weight reuse.
A clip-end prediction is NOT onset latency or continuous live evaluation.
"""
from argparse import ArgumentParser
from collections import Counter
import json
from math import isfinite
from pathlib import Path
from typing import Callable

from sentinel_edge.temporal_training import TemporalLinearModel

from sentinel_edge.caucafall_curator import _sha256_file, _video_metadata
from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import train_and_evaluate
from sentinel_edge.video_benchmark import collect_video_frames
from sentinel_edge.window_export import NearestFrameSampler, _read_json

CONTEXT_MS = 1_500
MAX_CLIPS = 64
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_FRAMES = 6_000
MAX_TASK_BYTES = 60 * 1024 * 1024
SEGMENT_FIELDS = frozenset({
    "clip_id", "video", "start_ms", "end_ms", "expected_fall",
    "label_reviewed", "annotation_basis",
})


def _preflight(root: Path, pose_task: Path, groups: dict, proposals: dict,
               metadata_reader) -> list[tuple[dict, Path, int, int]]:
    """Validate every source before opening a model, allowing short abstentions."""
    root = root.resolve(strict=True)
    clip_root = (root / "clips").resolve(strict=True)
    if (pose_task.suffix.lower() != ".task" or not pose_task.is_file()
            or not 0 < pose_task.stat().st_size <= MAX_TASK_BYTES):
        raise ValueError("Local bounded official pose .task required")
    audit_subject_splits(groups)
    items = groups["clips"]
    if not 1 <= len(items) <= MAX_CLIPS:
        raise ValueError("Research pilot requires 1..64 fixed source clips")
    if (not isinstance(proposals, dict) or set(proposals) != {"version", "segments"}
            or type(proposals["version"]) is not int or proposals["version"] != 1
            or not isinstance(proposals["segments"], list)
            or len(proposals["segments"]) != len(items)):
        raise ValueError("Expected exact publisher proposal manifest")
    specs = {}
    for item in proposals["segments"]:
        if (not isinstance(item, dict) or set(item) != SEGMENT_FIELDS
                or not isinstance(item["clip_id"], str)
                or item["clip_id"] in specs
                or item["label_reviewed"] is not False
                or type(item["expected_fall"]) is not bool
                or type(item["start_ms"]) is not int
                or type(item["end_ms"]) is not int
                or item["start_ms"] < 0
                or item["end_ms"] <= item["start_ms"]
                or not isinstance(item["annotation_basis"], str)
                or len(item["annotation_basis"]) < 10):
            raise ValueError("Only bounded unreviewed publisher proposals permitted")
        specs[item["clip_id"]] = item
    plan = []
    for item in items:
        cid = item["clip_id"]
        spec = specs.get(cid)
        if spec is None or spec["expected_fall"] is not item["expected_fall"]:
            raise ValueError("Publisher label/source manifest mismatch")
        relative = spec["video"]
        if (not isinstance(relative, str) or not relative
                or ":" in relative or "\\" in relative
                or Path(relative).is_absolute() or ".." in Path(relative).parts):
            raise ValueError("Unsafe source video path")
        video = (root / relative).resolve(strict=True)
        if (not video.is_relative_to(clip_root)
                or video.suffix.lower() not in {".avi", ".mp4", ".mov"}
                or not video.is_file()
                or not 0 < video.stat().st_size <= MAX_VIDEO_BYTES):
            raise ValueError("Missing or unsafe publisher video")
        if _sha256_file(video) != item["media_sha256"]:
            raise ValueError("Publisher video SHA256 drifted")
        expected, fps = metadata_reader(video)
        if (type(expected) is not int or not 1 <= expected <= MAX_FRAMES
                or type(fps) not in (float, int) or not isfinite(fps)
                or not 1 <= fps <= 120):
            raise ValueError("Invalid source video count or FPS")
        duration_ms = round((expected - 1) * 1000 / fps)
        end_ms = spec["end_ms"]
        if end_ms > duration_ms + 100 or end_ms <= 0:
            raise ValueError("Publisher annotation exceeds original video")
        plan.append((item, video, expected, spec["start_ms"], end_ms))
    return plan


def train_causal_1500ms(root: Path, pose_task: Path, groups: dict,
                        proposals: dict, *, collector=collect_video_frames,
                        metadata_reader=_video_metadata,
                        model_sink: Callable[[TemporalLinearModel], None] | None = None) -> dict:
    """Train a separate in-memory 1.5s model with validation-only threshold.

    No test clip influences selection. Source clips shorter than 1.5s
    abstain and stay in the denominator, not imputed as correct ADL.
    """
    plan = _preflight(root, pose_task, groups, proposals, metadata_reader)
    eligible = set()
    windows = []
    rejected = Counter()
    selected = Counter()
    total_decoded = 0
    for item, video, expected, start_ms, end_ms in plan:
        split = item["split"]
        label = "fall" if item["expected_fall"] else "adl"
        selected[(split, label)] += 1
        if end_ms - start_ms < CONTEXT_MS:
            rejected[(split, label, "short")] += 1
            continue
        sampler = NearestFrameSampler(item["clip_id"], end_ms - CONTEXT_MS, end_ms)
        frames, stats = collector(
            video, clip_id=item["clip_id"], model=pose_task,
            max_frames=expected, frame_consumer=sampler.on_frame,
            event_consumer=lambda _: None,
        )
        if (frames or type(stats.get("frames_processed")) is not int
                or stats["frames_processed"] != expected
                or sampler.frames_processed != expected
                or type(stats.get("invalid_pose_frames")) is not int
                or not 0 <= stats["invalid_pose_frames"] <= expected):
            raise ValueError("Original source video full-decode parity violated")
        if _sha256_file(video) != item["media_sha256"]:
            raise ValueError("Source changed during offline inference")
        total_decoded += expected
        try:
            features = sampler.finish()
        except ValueError as exc:
            if "Too few valid poses" not in str(exc):
                raise
            rejected[(split, label, "pose")] += 1
            continue
        eligible.add(item["clip_id"])
        windows.append({"clip_id": item["clip_id"], "features": features})
    kept = dict(groups)
    kept["clips"] = [x for x in groups["clips"] if x["clip_id"] in eligible]
    # A discarded class or person is not a valid model-evaluation split.
    audit_subject_splits(kept)
    bundle = {
        "version": 1, "feature_set": "experimental_pose_motion_v1",
        "windows": windows,
    }
    # Separate NEW weights, trained only from these 1.5s descriptors.
    # Only an explicit private model_sink may serialize the 1500ms model;
    # frozen 8s artifacts must never be copied or silently reused.
    model, fit_report = train_and_evaluate(kept, bundle)
    if model_sink is not None:
        model_sink(model)
    coverage = {}
    for split in ("train", "val", "test"):
        coverage[split] = {}
        for label in ("fall", "adl"):
            n = selected[(split, label)]
            short = rejected[(split, label, "short")]
            pose = rejected[(split, label, "pose")]
            coverage[split][label] = {
                "selected": n, "too_short": short, "pose_abstained": pose,
                "scored": n - short - pose,
            }
    return {
        "stage": "publisher_label_causal_1500ms_offline_research_only",
        "trained_ai_classifier": True,
        "model_architecture": "independently_fitted_1500ms_30d_linear_logistic",
        "window_context_ms": CONTEXT_MS,
        "temporal_sample_slots": 30,
        "trailing_segment_end_only": True,
        "no_later_than_segment_end_frames_used": True,
        "not_trained_on_original_8s_feature_windows": True,
        "no_8s_artifact_reused": True,
        "all_source_sha256_verified": True,
        "full_decoded_source_frames": total_decoded,
        "input_original_clips": len(plan),
        "eligible_clips": len(eligible),
        "source_coverage": coverage,
        "split_audit": fit_report["split_audit"],
        "model_size_bytes_in_ram": model.model_bytes,
        "validation_threshold": fit_report["chosen_threshold"],
        "validation_publisher_clip_diagnostic": fit_report["validation"],
        "previously_exposed_test_publisher_clip_diagnostic": fit_report["heldout_test"],
        "test_data_excluded_from_training_and_threshold_selection": True,
        "publisher_clip_labels_not_fall_onset_truth": True,
        "human_event_onsets_independently_reviewed": False,
        "old_test_cohort_previously_exposed": True,
        "not_a_live_streaming_or_fall_detection_delay_test": True,
        "not_real_world_accuracy_false_alarms_or_recall": True,
        "retrained_weights_serialized": model_sink is not None,
        "alerts_modified_or_authorized": False,
        "raw_video_pose_vectors_and_subject_ids_exported": False,
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description="Research-only 1500ms in-memory model fit")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path, required=True)
    parser.add_argument("--private-model-output", type=Path,
                        help="Opt-in exclusive research-only 1500ms weights (data/private)")
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Acknowledge unreviewed labels and local pose privacy")
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    try:
        root = args.root.resolve(strict=True)
        groups_file = args.groups.resolve(strict=True)
        proposals_file = args.proposals.resolve(strict=True)
        if (not root.is_relative_to(private)
                or not groups_file.is_relative_to(root)
                or not proposals_file.is_relative_to(root)):
            raise ValueError("Only ignored private local sources accepted")
        from sentinel_edge.causal_1500ms_artifact import save_causal_artifact
        from sentinel_edge.window_export import _private_output_path
        destination = None
        if args.private_model_output is not None:
            destination = _private_output_path(args.private_model_output)
            if destination.exists():
                raise ValueError("Refusing to overwrite existing private model")
        groups = _read_json(groups_file)
        if (not isinstance(groups, dict)
                or not isinstance(groups.get("clips"), list)
                or not groups["clips"]):
            raise ValueError("Research group manifest has no clips")
        provenance = groups["clips"][0]["dataset_id"]
        saved = None

        def capture_model(model):
            nonlocal saved
            if destination is None:
                raise ValueError("Unrequested research model export")
            saved = save_causal_artifact(
                model, destination, groups_path=groups_file,
                proposals_path=proposals_file, dataset=provenance,
            )

        report = train_causal_1500ms(
            root, args.pose_task, groups, _read_json(proposals_file),
            model_sink=capture_model if destination is not None else None,
        )
        if saved is not None:
            report["private_short_model_export"] = saved
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        parser.error("1500ms research pilot refused: " + str(exc))
    print(json.dumps(report, allow_nan=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
