"""Reproducible *clip-level* heuristic evaluation using authorized local pose traces.

No video/image/model network calls. Does not establish clinical performance.
Each manifest clip represents one ground-truth example, not one frame.
"""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from sentinel_edge.contracts import PoseFeatures
from sentinel_edge.detector import DetectorConfig, TemporalFallDetector
from sentinel_edge.metrics import summarize_binary
from sentinel_edge.pose_traces import read_pose_trace

CLIP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


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


def _load_manifest(path: Path) -> tuple[list[dict], str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Expected a version=1 evaluation manifest")
    permission = manifest.get("permission_basis")
    if not isinstance(permission, str) or not permission.strip():
        raise ValueError("Document the consent or license basis for every dataset")
    clips = manifest.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("Manifest must list at least one ground-truth clip")
    return clips, permission.strip()


def evaluate_manifest(
    manifest_path: Path, config: DetectorConfig | None = None
) -> dict:
    """Evaluate independent local traces, returning only aggregate and clip IDs."""
    manifest_path = manifest_path.resolve(strict=True)
    clips, permission = _load_manifest(manifest_path)
    root = manifest_path.parent
    outcomes: list[ClipOutcome] = []
    seen_ids: set[str] = set()
    false_candidates_in_negative_clips = 0
    false_candidates_before_onset = 0
    negative_observed_ms = 0

    for item in clips:
        if not isinstance(item, dict):
            raise ValueError("Each clip must be an object")
        if set(item) - {"id", "trace", "expected_fall", "onset_ms"}:
            raise ValueError("Unsupported clip manifest fields")
        clip_id, filename, label = (
            item.get("id"), item.get("trace"), item.get("expected_fall")
        )
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
        if not isinstance(filename, str) or not filename or Path(filename).is_absolute():
            raise ValueError("Each trace must be a relative JSONL file path")
        relative = Path(filename)
        if ".." in relative.parts or relative.suffix.lower() != ".jsonl":
            raise ValueError("Trace must be a relative .jsonl file within the manifest directory")
        resolved = (root / relative).resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("Trace must be a real file inside the dataset manifest directory")

        detector = TemporalFallDetector(config)
        first_time: int | None = None
        last_time: int | None = None
        events: list[int] = []
        frames = 0
        valid_pose_frames = 0
        for frame in read_pose_trace(resolved, source_id=clip_id):
            if first_time is None:
                first_time = frame.timestamp_ms
            last_time = frame.timestamp_ms
            event = detector.process(frame)
            frames += 1
            if PoseFeatures.from_frame(frame, detector.config.min_visibility) is not None:
                valid_pose_frames += 1
            if event is not None:
                events.append(event.timestamp_ms)

        if not label:
            false_candidates_in_negative_clips += len(events)
            if first_time is not None and last_time is not None:
                negative_observed_ms += max(0, last_time - first_time)

        # With onset annotations, events before onset cannot count as a match.
        if onset_ms is not None and (first_time is None or last_time is None or
                                     not first_time <= onset_ms <= last_time):
            raise ValueError(f"Clip {clip_id}: onset_ms outside the observed trace")
        pre_onset = sum(t < onset_ms for t in events) if onset_ms is not None else 0
        false_candidates_before_onset += pre_onset
        post_onset = next((t for t in events if onset_ms is not None and t >= onset_ms), None)
        outcomes.append(ClipOutcome(
            clip_id=clip_id,
            expected_fall=label,
            predicted_fall=(bool(events) if onset_ms is None else post_onset is not None),
            candidate_count=len(events),
            pre_onset_candidate_count=pre_onset,
            first_candidate_ms=events[0] if events else None,
            first_matching_candidate_ms=(post_onset if onset_ms is not None
                                         else (events[0] if events else None)),
            annotated_onset_ms=onset_ms,
            latency_ms=post_onset - onset_ms if post_onset is not None and onset_ms is not None else None,
            analyzed_frames=frames,
            observed_pose_frames=valid_pose_frames,
        ))

    metrics = summarize_binary(
        [result.expected_fall for result in outcomes],
        [result.predicted_fall for result in outcomes],
    )
    return {
        "evaluation_type": "clip-level-pose-heuristic",
        "source": "authorized local JSONL traces (no raw video uploaded)",
        "model_calibrated": False,
        "clinically_validated": False,
        "permission_basis_declared": bool(permission),
        "num_clips": len(outcomes),
        "metrics": asdict(metrics),
        "false_candidates_in_negative_clips": false_candidates_in_negative_clips,
        "false_candidates_before_onset": false_candidates_before_onset,
        "false_candidate_total_with_known_labels": (
            false_candidates_in_negative_clips + false_candidates_before_onset
        ),
        "negative_observed_hours": round(negative_observed_ms / 3_600_000, 6),
        "false_candidates_per_negative_hour": (
            round(false_candidates_in_negative_clips * 3_600_000 / negative_observed_ms, 4)
            if negative_observed_ms else None
        ),
        "clips": [asdict(outcome) for outcome in outcomes],
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="VIIL Sentinel offline clip-level evaluation")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Ground-truth manifest with local authorized JSONL traces")
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
