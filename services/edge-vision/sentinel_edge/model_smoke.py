"""Offline MediaPipe Pose Landmarker smoke test on generated *no-person* frames.

This validates the real model bundle/API runtime, NOT detection accuracy.
Never accesses cameras, recordings, private images or external APIs.
"""
from argparse import ArgumentParser
import hashlib
import json
from math import ceil, isfinite
from pathlib import Path
from statistics import mean
from time import perf_counter

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.pose_adapter import extract_torso_landmarks


def latency_summary(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms or not all(isfinite(value) and value >= 0 for value in samples_ms):
        raise ValueError("latencies must be non-empty finite non-negative values")
    values = sorted(samples_ms)
    def percentile(p: float) -> float:
        # Nearest-rank empirical quantile: easy to reproduce across systems.
        return values[max(0, ceil(len(values) * p) - 1)]
    return {
        "mean_ms": round(mean(values), 3),
        "p50_ms": round(percentile(0.50), 3),
        "p95_ms": round(percentile(0.95), 3),
        "max_ms": round(values[-1], 3),
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_smoke(model: Path, *, frames: int = 30, size: int = 256) -> dict:
    """Load a *real* on-device MediaPipe model and process deterministic blank frames."""
    if not 1 <= frames <= 300:
        raise ValueError("frames must be in range 1..300")
    if not 128 <= size <= 1024:
        raise ValueError("size must be in range 128..1024")
    if model.suffix.lower() != ".task" or not model.is_file() or model.stat().st_size == 0:
        raise ValueError("A non-empty, licensed local .task asset is required")

    # Imported on demand so pure unit tests need no third-party runtime.
    import mediapipe as mp
    import numpy as np

    blank = np.zeros((size, size, 3), dtype=np.uint8)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=blank)
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model.resolve())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=2,
    )
    detector = TemporalFallDetector()
    latencies_ms: list[float] = []
    valid_pose_frames = 0
    event_count = 0
    start = perf_counter()
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        for i in range(frames):
            timestamp_ms = i * 100
            clock_start = perf_counter()
            result = landmarker.detect_for_video(image, timestamp_ms)
            latencies_ms.append((perf_counter() - clock_start) * 1000)
            landmarks = extract_torso_landmarks(result)
            if landmarks:
                valid_pose_frames += 1
            candidate = detector.process(
                PoseFrame(timestamp_ms=timestamp_ms, landmarks=landmarks, source_id="synthetic-blank")
            )
            if candidate:
                event_count += 1
    elapsed_sec = max(perf_counter() - start, 1e-9)
    return {
        "test_type": "synthetic-no-person-negative-control",
        "real_mediapipe_inference": True,
        "fall_accuracy_measured": False,
        "clinical_use": False,
        "model_file_sha256": _file_sha256(model),
        "frames": frames,
        "frame_size": size,
        "valid_pose_frames_on_blank_control": valid_pose_frames,
        "candidate_events_on_blank_control": event_count,
        "negative_control_passed": valid_pose_frames == 0 and event_count == 0,
        "inference_latency_ms": latency_summary(latencies_ms),
        "overall_throughput_fps": round(frames / elapsed_sec, 2),
        "note": "Synthetic blank-frame smoke test only; no humans, no webcam, no diagnosis.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Offline real-model smoke test using blank RGB frames")
    parser.add_argument("--model", type=Path, required=True, help="Local licensed .task model")
    parser.add_argument("--frames", type=int, default=30, help="1..300 generated empty frames")
    parser.add_argument("--size", type=int, default=256, help="Blank frame side, 128..1024")
    args = parser.parse_args(argv)
    try:
        result = run_smoke(args.model, frames=args.frames, size=args.size)
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0 if result["negative_control_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
