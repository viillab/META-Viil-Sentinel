"""AFDCare-inspired *research-only* shadow inference for local VIIL video/camera.

AFDCare uses an actual YOLO-Pose + 120x93 GRU/ONNX temporal classifier and
separates immediate candidate from confirmed incident. VIIL's 30D pooled
linear research model has a DIFFERENT input contract and is NOT approved to
send incidents. This class evaluates only independently of the unchanged
heuristic; its output is aggregate counts, not alarm events.

Match the original model training: 30 uniformly spaced pose samples over
EXACTLY an 8s trailing interval (NearestFrameSampler), with sample-time
missing masks and the existing 30D pooled descriptor. Never interpret 30
adjacent camera frames as equivalent to the temporal training window.
"""
from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.private_model_training import read_private_artifact
from sentinel_edge.temporal_training import pool_temporal_window
from sentinel_edge.window_export import NearestFrameSampler

FROZEN_LINEAR_SHA256 = (
    "2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab"
)
FROZEN_THRESHOLD = .53
SHADOW_WINDOW_MS = 8_000
SHADOW_HOP_MS = 1_000
SHADOW_MAX_GAP_MS = 700
MAX_BUFFERED_FRAMES = 1_000


def load_verified_linear_shadow(path: Path):
    """Trusted, exact pinned TRAIN-only artifact; never auto-pick another file."""
    path = path.resolve(strict=True)
    digest = sha256()
    if not path.is_file() or path.stat().st_size > 10_000:
        raise ValueError("Shadow research artifact missing or oversized")
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            digest.update(part)
    if digest.hexdigest() != FROZEN_LINEAR_SHA256:
        raise ValueError("Shadow research model SHA256 differs from validated V1")
    model = read_private_artifact(path)
    if not isfinite(model.threshold) or abs(model.threshold-FROZEN_THRESHOLD) > 1e-9:
        raise ValueError("Shadow model changed threshold")
    return model


@dataclass(frozen=True)
class ShadowCounters:
    incoming_frames: int
    scored_windows: int
    candidate_windows: int
    below_threshold_windows: int
    pose_abstained_windows: int
    frame_time_gap_resets: int
    source_resets: int
    buffer_overflow_resets: int


class RollingModelShadow:
    """RAM-only windowed predictor; NONE of these candidates becomes an event.

    State is single-source, max 8s and max 1000 PoseFrames, never persisted.
    Any frame/source gap >700ms invalidates pre-gap motion context. Exactly one
    prediction each 1s of trailing 8s coverage. The first model prediction
    is intentionally impossible until 8s of observed source clock elapsed.
    """

    def __init__(self, model):
        if abs(float(model.threshold) - FROZEN_THRESHOLD) > 1e-9:
            raise ValueError("Unexpected frozen model threshold")
        self._model = model
        self._buffer = deque(maxlen=MAX_BUFFERED_FRAMES)
        self._first_timestamp = None
        self._last_timestamp = None
        self._last_scored_timestamp = None
        self._source_id = None
        self._frames = 0
        self._scored = 0
        self._positive = 0
        self._negative = 0
        self._abstain = 0
        self._gaps = 0
        self._sources = 0
        self._overflows = 0

    def _clear_window(self):
        self._buffer.clear()
        self._first_timestamp = None
        self._last_timestamp = None
        self._last_scored_timestamp = None

    def observe(self, frame: PoseFrame) -> None:
        """Process one accepted or abstained PoseFrame without emitting an event."""
        if self._source_id is not None and frame.source_id != self._source_id:
            self._sources += 1
            self._clear_window()
        elif self._last_timestamp is not None:
            delta = frame.timestamp_ms - self._last_timestamp
            if delta <= 0:
                raise ValueError("Shadow source timestamp must strictly increase")
            if delta > SHADOW_MAX_GAP_MS:
                self._gaps += 1
                self._clear_window()
        self._source_id = frame.source_id
        self._frames += 1
        if len(self._buffer) == MAX_BUFFERED_FRAMES:
            self._overflows += 1
            self._clear_window()
        if self._first_timestamp is None:
            self._first_timestamp = frame.timestamp_ms
        self._last_timestamp = frame.timestamp_ms
        self._buffer.append(frame)
        while (self._buffer and self._buffer[0].timestamp_ms
               < frame.timestamp_ms - SHADOW_WINDOW_MS - 90):
            self._buffer.popleft()
        if frame.timestamp_ms - self._first_timestamp < SHADOW_WINDOW_MS:
            return
        if (self._last_scored_timestamp is not None
                and frame.timestamp_ms - self._last_scored_timestamp < SHADOW_HOP_MS):
            return
        self._last_scored_timestamp = frame.timestamp_ms
        sampler = NearestFrameSampler(
            frame.source_id, frame.timestamp_ms - SHADOW_WINDOW_MS,
            frame.timestamp_ms
        )
        for existing in self._buffer:
            sampler.on_frame(existing)
        try:
            features = sampler.finish()
        except ValueError as exc:
            if "Too few valid poses" not in str(exc):
                raise
            self._abstain += 1
            return
        probability = float(self._model.predict_probability(
            pool_temporal_window(features)
        ))
        if not isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Nonfinite/out of range shadow model probability")
        self._scored += 1
        if probability >= FROZEN_THRESHOLD:
            self._positive += 1
        else:
            self._negative += 1

    def summary(self) -> dict:
        counts = ShadowCounters(
            incoming_frames=self._frames,
            scored_windows=self._scored,
            candidate_windows=self._positive,
            below_threshold_windows=self._negative,
            pose_abstained_windows=self._abstain,
            frame_time_gap_resets=self._gaps,
            source_resets=self._sources,
            buffer_overflow_resets=self._overflows,
        )
        return {
            **counts.__dict__,
            "training_matched_context_ms": SHADOW_WINDOW_MS,
            "shadow_hop_ms": SHADOW_HOP_MS,
            "frozen_model_sha256": FROZEN_LINEAR_SHA256,
            "frozen_threshold": FROZEN_THRESHOLD,
            "shadow_model_executed": True,
            "shadow_never_emits_incidents_or_modifies_heuristic": True,
            "no_coordinates_frames_probabilities_or_timestamps_persisted": True,
            "not_a_precision_recall_or_latency_measurement": True,
        }
