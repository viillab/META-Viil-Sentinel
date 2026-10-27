"""Consent-gated, bounded local video -> temporal training feature exporter.

NON-CLINICAL, RESEARCH-ONLY: curated 30-frame segments, never automatically
label whole fall clips. Pose-derived windows can identify people indirectly;
the output is *private* even without pictures, and must not enter Git.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.evaluation import local_source
from sentinel_edge.model_smoke import _file_sha256
from sentinel_edge.motion_features import TemporalFeatureEncoder, FEATURE_NAMES
from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import WINDOW_FRAMES, MAX_JSON_BYTES, _validate_bundle
from sentinel_edge.video_benchmark import (
    MAX_FRAMES, MAX_VIDEO_BYTES, VIDEO_SUFFIXES, collect_video_frames,
)

MAX_EXPORT_CLIPS = 64
MAX_EXPORT_FRAMES = 30_000
MAX_INPUT_JSON_BYTES = 5_000_000
MIN_SEGMENT_MS = 900
MAX_SEGMENT_MS = 8_000
MAX_TIME_TOLERANCE_MS = 90


class NearestFrameSampler:
    """Bounded (<=30 PoseFrames) nearest timestamp samples without raw images."""

    def __init__(self, source_id: str, start_ms: int, end_ms: int):
        if (type(start_ms) is not int or type(end_ms) is not int or
                start_ms < 0 or not MIN_SEGMENT_MS <= end_ms - start_ms <= MAX_SEGMENT_MS):
            raise ValueError("Reviewed segment must be 900..8000ms and non-negative")
        self.source_id = source_id
        self.start_ms = start_ms
        self.end_ms = end_ms
        step = (end_ms - start_ms) / WINDOW_FRAMES
        self.targets = tuple(round(start_ms + (i + .5) * step)
                             for i in range(WINDOW_FRAMES))
        if len(set(self.targets)) != WINDOW_FRAMES:
            raise ValueError("Temporal samples must have distinct timestamps")
        self.tolerance = min(MAX_TIME_TOLERANCE_MS, max(10, int(step * .51)))
        self.nearest: list[PoseFrame | None] = [None] * WINDOW_FRAMES
        self.distance = [self.tolerance + 1] * WINDOW_FRAMES
        self.frames_processed = 0
        self.last_timestamp = -1

    def on_frame(self, frame: PoseFrame) -> None:
        if frame.source_id != self.source_id:
            raise ValueError("Video source changed during window export")
        if frame.timestamp_ms <= self.last_timestamp:
            raise ValueError("Video timestamps must strictly increase")
        self.frames_processed += 1
        self.last_timestamp = frame.timestamp_ms
        if not self.start_ms - self.tolerance <= frame.timestamp_ms < (
            self.end_ms + self.tolerance
        ):
            return
        # A frame can never be reused as multiple independent samples.
        target_idx = min(range(WINDOW_FRAMES),
                         key=lambda i: abs(frame.timestamp_ms - self.targets[i]))
        dist = abs(frame.timestamp_ms - self.targets[target_idx])
        if dist <= self.tolerance and dist < self.distance[target_idx]:
            self.nearest[target_idx] = frame
            self.distance[target_idx] = dist

    def finish(self) -> list[list[float]]:
        if self.last_timestamp < self.end_ms - self.tolerance:
            raise ValueError("Annotated segment extends beyond decoded video")
        encoder = TemporalFeatureEncoder(window_size=WINDOW_FRAMES)
        result = []
        for ts, frame in zip(self.targets, self.nearest):
            # Reconstitute at uniform sample clock to avoid fabricated
            # variable-dt speed spikes. An unsampled slot is an occlusion.
            sampled = PoseFrame(
                timestamp_ms=ts, source_id=self.source_id,
                landmarks=frame.landmarks if frame is not None else {},
            )
            result.append(list(encoder.process(sampled).features[-1]))
        if sum(row[-1] == 1 for row in result) < WINDOW_FRAMES // 3:
            raise ValueError("Too few valid poses in reviewed segment")
        return result


def _read_json(path: Path):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT_JSON_BYTES:
        raise ValueError("Missing or oversized research manifest")
    return json.loads(path.read_text("utf-8"))


def validate_source_plan(group_manifest: dict, selection: dict, root: Path):
    """Fail closed on label provenance, unsafe paths, sizes and file hashes."""
    audit_subject_splits(group_manifest)
    groups = group_manifest["clips"]
    if len(groups) > MAX_EXPORT_CLIPS:
        raise ValueError("At most 64 reviewed clips per export")
    if (not isinstance(selection, dict) or set(selection) != {"version", "segments"}
            or type(selection["version"]) is not int or selection["version"] != 1
            or not isinstance(selection["segments"], list)
            or len(selection["segments"]) != len(groups)):
        raise ValueError("Expected exact version=1 reviewed segments for every group clip")
    specs = {}
    for s in selection["segments"]:
        if not isinstance(s, dict) or set(s) != {
            "clip_id", "video", "start_ms", "end_ms", "expected_fall",
            "label_reviewed", "annotation_basis",
        }:
            raise ValueError("Each segment requires exact curated annotation fields")
        clip_id = s["clip_id"]
        if not isinstance(clip_id, str) or clip_id in specs:
            raise ValueError("Duplicate or invalid segment clip ID")
        if s["label_reviewed"] is not True or type(s["expected_fall"]) is not bool:
            raise ValueError("Explicit reviewed segment label required")
        basis = s["annotation_basis"]
        if not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 200:
            raise ValueError("Document reviewed segment event/ADL annotation basis")
        # annotation text is local/private; never included in feature bundle.
        video = s["video"]
        if (not isinstance(video, str) or not video or ":" in video
                or Path(video).is_absolute() or ".." in Path(video).parts
                or any(ord(ch) < 32 for ch in video)
                or Path(video).suffix.lower() not in VIDEO_SUFFIXES):
            raise ValueError("Video paths must be supported relative local files")
        # Review time bounds before touching the source video.
        NearestFrameSampler(clip_id, s["start_ms"], s["end_ms"])
        specs[clip_id] = s

    plan = []
    for item in groups:
        cid = item["clip_id"]
        if cid not in specs:
            raise ValueError("Reviewed source segment missing for labeled clip")
        s = specs[cid]
        if s["expected_fall"] != item["expected_fall"]:
            raise ValueError("Reviewed segment label contradicts split manifest")
        if "media_sha256" not in item:
            raise ValueError("Each video needs a verified content digest before inference")
        video = local_source(root, s["video"])
        size = video.stat().st_size
        if not 0 < size <= MAX_VIDEO_BYTES:
            raise ValueError("Video file exceeds 512 MiB budget or is empty")
        if _file_sha256(video) != item["media_sha256"]:
            raise ValueError("Source video SHA-256 mismatch")
        plan.append((cid, video, s["start_ms"], s["end_ms"]))
    return plan


def extract_reviewed_windows(group_manifest: dict, selection: dict, *, root: Path,
                             model: Path, collector=collect_video_frames) -> dict:
    """Validate ALL sources before expensive inference; keep only 30 poses/clip."""
    root = root.resolve(strict=True)
    plan = validate_source_plan(group_manifest, selection, root)
    if model.suffix.lower() != ".task" or not model.is_file() or not model.stat().st_size:
        raise ValueError("Nonempty licensed local MediaPipe .task model is required")
    bundle = {"version": 1, "feature_set": "experimental_pose_motion_v1",
              "windows": []}
    total = 0
    for cid, video, start_ms, end_ms in plan:
        remaining = MAX_EXPORT_FRAMES - total
        if remaining <= 0:
            raise ValueError("Exceeds 30,000 total decoded-frame budget")
        sampler = NearestFrameSampler(cid, start_ms, end_ms)
        frames, stats = collector(
            video, clip_id=cid, model=model, max_frames=min(MAX_FRAMES, remaining),
            frame_consumer=sampler.on_frame, event_consumer=lambda event: None,
        )
        if (frames or type(stats.get("frames_processed")) is not int
                or stats["frames_processed"] != sampler.frames_processed
                or stats["frames_processed"] < 1):
            raise ValueError("Inconsistent streamed pose/frame counts")
        total += stats["frames_processed"]
        bundle["windows"].append({"clip_id": cid, "features": sampler.finish()})
    # The exact training contract must accept the derived features.
    _validate_bundle(group_manifest, bundle)
    return bundle


def _private_output_path(output: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    private_root = (repo_root / "data" / "private").resolve()
    candidate = output.resolve()
    if not candidate.is_relative_to(private_root) or output.suffix != ".json":
        raise ValueError("Derived human pose windows MUST remain in repo data/private/*.json")
    if not output.parent.is_dir() or output.exists():
        raise ValueError("Output parent must exist and output must not already exist")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Private reviewed MediaPipe pose window exporter")
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-consent", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_consent or not args.acknowledge_pose_privacy:
        parser.error("Require --confirm-consent AND --acknowledge-pose-privacy")
    try:
        destination = _private_output_path(args.output)
        group_manifest = _read_json(args.groups)
        selections = _read_json(args.segments)
        bundle = extract_reviewed_windows(
            group_manifest, selections, root=args.segments.parent, model=args.model,
        )
        payload = json.dumps(bundle, separators=(",", ":"), allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError("Generated feature bundle exceeds 15 MiB")
        # Exclusive creation. No fallback output path, no auto-overwrite.
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(f"Private window export refused: {exc}")
    print(json.dumps({
        "research_only": True, "trained_model": False,
        "clip_count": len(bundle["windows"]), "window_frames": WINDOW_FRAMES,
        "features_per_frame": len(FEATURE_NAMES), "private_file_created": True,
        "no_live_alerts": True, "no_media_uploaded": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
