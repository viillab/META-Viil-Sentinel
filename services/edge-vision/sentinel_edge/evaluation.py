"""Clip-level ground-truth evaluation for real or synthetic pose-frame streams.

Clip-level decision accounting remains identical for JSONL and direct-video
inputs. No raw video, image pixels, patient names or unapproved traces in
returned reports. This is non-clinical prototype scoring.
"""
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from sentinel_edge.contracts import PoseFeatures, PoseFrame
from sentinel_edge.detector import DetectorConfig, TemporalFallDetector
from sentinel_edge.metrics import summarize_binary
from sentinel_edge.pose_traces import read_pose_trace

CLIP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_CLIPS = 100


@dataclass(frozen=True)
class ClipOutcome:
    clip_id: str
    expected_fall: bool
    predicted_fall: bool
    candidate_count: int
    pre_onset_candidate_count: int
    first_candidate_ms: int | None
    first_matching_candidate_ms: int | None
    annotated_onset_ms: int | None
    latency_ms: int | None
    analyzed_frames: int
    observed_pose_frames: int
    first_frame_ms: int
    last_frame_ms: int


def load_manifest(path: Path) -> tuple[list[dict], str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Expected a version=1 evaluation manifest")
    permission = manifest.get("permission_basis")
    if not isinstance(permission, str) or not permission.strip():
        raise ValueError("Document the consent or license basis for every dataset")
    clips = manifest.get("clips")
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ValueError("Manifest must list 1..100 ground-truth clips")
    return clips, permission.strip()


def validate_clip(item: dict, seen_ids: set[str], *, path_key: str, suffixes: set[str]
                  ) -> tuple[str, str, bool, int | None]:
    if not isinstance(item, dict) or set(item) - {"id", path_key, "expected_fall", "onset_ms"}:
        raise ValueError("Unsupported clip manifest fields")
    clip_id, filename, label = item.get("id"), item.get(path_key), item.get("expected_fall")
    if not isinstance(clip_id, str) or CLIP_ID.fullmatch(clip_id) is None:
        raise ValueError("Clip ID must be a pseudonymous identifier (letters/digits/._-)")
    if clip_id in seen_ids:
        raise ValueError("Clip IDs must be unique")
    seen_ids.add(clip_id)
    if type(label) is not bool:
        raise ValueError("expected_fall must be an explicit boolean")
    onset_ms = item.get("onset_ms")
    if onset_ms is not None and (type(onset_ms) is not int or onset_ms < 0 or not label):
        raise ValueError("onset_ms requires a positive clip and a non-negative integer")
    if (not isinstance(filename, str) or not filename or ':' in filename
            or Path(filename).is_absolute() or any(ord(char) < 32 for char in filename)):
        raise ValueError("Each source must be a relative file path")
    relative = Path(filename)
    if ".." in relative.parts or relative.suffix.lower() not in suffixes:
        raise ValueError("Source must be a relative supported file within the manifest directory")
    return clip_id, filename, label, onset_ms


def local_source(root: Path, filename: str) -> Path:
    resolved = (root / filename).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Source must be a real file inside the manifest directory")
    return resolved


def clip_outcome_from_counts(
    *, clip_id: str, expected_fall: bool, onset_ms: int | None,
    times: list[int], analyzed: int, valid_pose_frames: int,
    first_time: int | None, last_time: int | None,
) -> ClipOutcome:
    """Common finalizer keeps incremental and trace scoring semantics identical."""
    if first_time is None or last_time is None:
        raise ValueError(f"Clip {clip_id}: trace has no frames")
    if onset_ms is not None and not first_time <= onset_ms <= last_time:
        raise ValueError(f"Clip {clip_id}: onset_ms outside the observed trace")
    before = sum(t < onset_ms for t in times) if onset_ms is not None else 0
    post = next((t for t in times if onset_ms is not None and t >= onset_ms), None)
    match = bool(times) if onset_ms is None else post is not None
    return ClipOutcome(
        clip_id=clip_id, expected_fall=expected_fall, predicted_fall=match,
        candidate_count=len(times), pre_onset_candidate_count=before,
        first_candidate_ms=times[0] if times else None,
        first_matching_candidate_ms=post if onset_ms is not None
        else (times[0] if times else None),
        annotated_onset_ms=onset_ms,
        latency_ms=post - onset_ms if post is not None and onset_ms is not None else None,
        analyzed_frames=analyzed, observed_pose_frames=valid_pose_frames,
        first_frame_ms=first_time, last_frame_ms=last_time,
    )


class StreamingClipAccumulator:
    """Constant-memory pose scoring using the SAME detector events from live inference.

    Holds only O(number_of_events) timestamps and scalar counts.
    Does not store poses, images, raw frame data or private file paths.
    """
    def __init__(self, *, config: DetectorConfig | None = None):
        self.config = config or DetectorConfig()
        self.first_time: int | None = None
        self.last_time: int | None = None
        self.analyzed = 0
        self.valid_pose_frames = 0
        self.times: list[int] = []

    def on_frame(self, frame: PoseFrame) -> None:
        if self.first_time is None:
            self.first_time = frame.timestamp_ms
        self.last_time = frame.timestamp_ms
        self.analyzed += 1
        if PoseFeatures.from_frame(frame, self.config.min_visibility) is not None:
            self.valid_pose_frames += 1

    def on_event(self, event) -> None:
        self.times.append(event.timestamp_ms)

    def finish(self, *, clip_id: str, expected_fall: bool,
               onset_ms: int | None = None) -> ClipOutcome:
        return clip_outcome_from_counts(
            clip_id=clip_id, expected_fall=expected_fall, onset_ms=onset_ms,
            times=self.times, analyzed=self.analyzed,
            valid_pose_frames=self.valid_pose_frames,
            first_time=self.first_time, last_time=self.last_time,
        )


def evaluate_clip_frames(
    frames: Iterable[PoseFrame], *, clip_id: str, expected_fall: bool,
    onset_ms: int | None = None, config: DetectorConfig | None = None
) -> ClipOutcome:
    """Process a single bounded pose-frame iterable against annotated fall onset."""
    detector = TemporalFallDetector(config)
    times: list[int] = []
    valid_pose_frames = 0
    first_time: int | None = None
    last_time: int | None = None
    analyzed = 0
    for frame in frames:
        if first_time is None:
            first_time = frame.timestamp_ms
        last_time = frame.timestamp_ms
        event = detector.process(frame)
        analyzed += 1
        if PoseFeatures.from_frame(frame, detector.config.min_visibility) is not None:
            valid_pose_frames += 1
        if event is not None:
            times.append(event.timestamp_ms)
    return clip_outcome_from_counts(
        clip_id=clip_id, expected_fall=expected_fall, onset_ms=onset_ms,
        times=times, analyzed=analyzed, valid_pose_frames=valid_pose_frames,
        first_time=first_time, last_time=last_time,
    )


def summarize_clips(
    outcomes: list[ClipOutcome], *, source: str, permission_basis_declared: bool
) -> dict:
    metrics = summarize_binary(
        [result.expected_fall for result in outcomes],
        [result.predicted_fall for result in outcomes],
    )
    negatives = [outcome for outcome in outcomes if not outcome.expected_fall]
    false_negative_clips = sum(item.candidate_count for item in negatives)
    false_before = sum(item.pre_onset_candidate_count for item in outcomes)
    observed_negative_ms = sum(
        max(0, item.last_frame_ms - item.first_frame_ms) for item in negatives
    )
    positive_count = sum(item.expected_fall for item in outcomes)
    negative_count = len(outcomes) - positive_count
    limitations = []
    if negative_count == 0:
        limitations.append(
            "Positive-only evaluation: cannot measure false-positive rate or "
            "specificity; reported precision/F1 do not demonstrate no-fall reliability."
        )
    if positive_count == 0:
        limitations.append(
            "Negative-only evaluation: cannot measure fall-detection sensitivity."
        )
    if not all(item.annotated_onset_ms is not None
               for item in outcomes if item.expected_fall):
        limitations.append(
            "Some positive clips lack onset_ms; detection latency is not evaluable for them."
        )
    return {
        "ground_truth_balance": {"fall_clips": positive_count, "no_fall_clips": negative_count},
        "metric_interpretation_limits": limitations,
        "evaluation_type": "clip-level-pose-heuristic",
        "source": source,
        "model_calibrated": False,
        "clinically_validated": False,
        "permission_basis_declared": permission_basis_declared,
        "num_clips": len(outcomes),
        "metrics": asdict(metrics),
        "false_candidates_in_negative_clips": false_negative_clips,
        "false_candidates_before_onset": false_before,
        "false_candidate_total_with_known_labels": false_negative_clips + false_before,
        "negative_observed_hours": round(observed_negative_ms / 3_600_000, 6),
        "false_candidates_per_negative_hour": (
            round(false_negative_clips * 3_600_000 / observed_negative_ms, 4)
            if observed_negative_ms else None
        ),
        "clips": [asdict(item) for item in outcomes],
    }


def evaluate_manifest(manifest_path: Path, config: DetectorConfig | None = None) -> dict:
    """Evaluate local JSONL traces. Trace files are never sent outside this process."""
    manifest_path = manifest_path.resolve(strict=True)
    clips, permission = load_manifest(manifest_path)
    root = manifest_path.parent
    seen_ids: set[str] = set()
    outcomes = []
    for item in clips:
        clip_id, filename, label, onset = validate_clip(
            item, seen_ids, path_key="trace", suffixes={".jsonl"}
        )
        resolved = local_source(root, filename)
        outcomes.append(evaluate_clip_frames(
            read_pose_trace(resolved, source_id=clip_id),
            clip_id=clip_id, expected_fall=label, onset_ms=onset, config=config,
        ))
    return summarize_clips(
        outcomes, source="authorized local JSONL traces (no raw video uploaded)",
        permission_basis_declared=bool(permission)
    )


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="VIIL Sentinel offline clip-level evaluation")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Ground-truth manifest with authorized local JSONL traces")
    parser.add_argument("--min-hip-descent", type=float, default=0.13)
    parser.add_argument("--horizontal-min-angle-deg", type=float, default=56)
    parser.add_argument("--horizontal-hold-ms", type=int, default=450)
    args = parser.parse_args(argv)
    try:
        config = DetectorConfig(
            min_hip_descent=args.min_hip_descent,
            horizontal_min_angle_deg=args.horizontal_min_angle_deg,
            horizontal_hold_ms=args.horizontal_hold_ms,
        )
        result = evaluate_manifest(args.manifest, config)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot evaluate manifest: {exc}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
