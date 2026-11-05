"""Independent causal 1.5s model SHADOW: never emits an alert.

This module is an opt-in, in-memory research primitive. The caller
supplies a separately trained 1500ms 30D predictor; it NEVER loads the
frozen incompatible 8s model, retains raw images, sends events to the
backend, or exposes model probabilities or event timestamps.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite
from numbers import Real

from sentinel_edge.contracts import PoseFrame
from sentinel_edge.temporal_training import pool_temporal_window
from sentinel_edge.window_export import NearestFrameSampler

CONTEXT_MS = 1_500
HOP_MS = 250
MAX_GAP_MS = 700
MAX_BUFFERED_FRAMES = 256
SAMPLE_TOLERANCE_MS = 90


@dataclass(frozen=True)
class CausalShadowTotals:
    incoming_frames: int
    scored_windows: int
    positive_windows: int
    negative_windows: int
    pose_abstained_windows: int
    source_resets: int
    timestamp_gap_resets: int
    buffer_overflow_resets: int
    max_buffered_frames_seen: int


class Causal1500msModelShadow:
    """Consumes past PoseFrames; only returns aggregate offline research totals.

    At each 250ms hop, exactly 30 timestamps are sampled from the past
    1500ms and pooled using the SAME 30D features as training. Strict
    source change/large-gap resets; no score before 1500ms of source time.
    """

    def __init__(self, model):
        # Explicit model-input contract prevents accidental 8s V1 binding.
        # A tag alone is not provenance; this stays research-only.
        if (type(getattr(model, "temporal_context_ms", None)) is not int
                or model.temporal_context_ms != CONTEXT_MS
                or type(getattr(model, "input_dimensions", None)) is not int
                or model.input_dimensions != 30):
            raise ValueError("Research predictor must identify 1500ms 30D training")
        threshold = getattr(model, "threshold", None)
        if (type(threshold) not in (int, float)
                or not isfinite(threshold) or not 0 < threshold < 1
                or not callable(getattr(model, "predict_probability", None))):
            raise ValueError("1500ms research shadow requires valid fitted model")
        self._model = model
        self._threshold = float(threshold)
        self._buffer: deque[PoseFrame] = deque()
        self._source = None
        self._first_timestamp = None
        self._last_timestamp = None
        self._last_scored_timestamp = None
        self._incoming = 0
        self._scored = 0
        self._positive = 0
        self._negative = 0
        self._abstained = 0
        self._source_resets = 0
        self._time_resets = 0
        self._overflow_resets = 0
        self._max_buffer = 0

    def _reset_evidence(self):
        self._buffer.clear()
        self._first_timestamp = None
        self._last_timestamp = None
        self._last_scored_timestamp = None

    def observe(self, frame: PoseFrame) -> None:
        """Never returns candidates, probabilities, event IDs or any incidents."""
        if (not isinstance(frame, PoseFrame)
                or type(frame.timestamp_ms) is not int
                or frame.timestamp_ms < 0
                or not isinstance(frame.source_id, str)
                or not frame.source_id):
            raise ValueError("Expected validated PoseFrame for causal shadow")
        if self._source is not None and frame.source_id != self._source:
            self._source_resets += 1
            self._reset_evidence()
        elif self._last_timestamp is not None:
            delta = frame.timestamp_ms - self._last_timestamp
            if delta <= 0:
                raise ValueError("1500ms shadow requires increasing timestamps")
            if delta > MAX_GAP_MS:
                self._time_resets += 1
                self._reset_evidence()
        self._source = frame.source_id
        self._incoming += 1
        if len(self._buffer) >= MAX_BUFFERED_FRAMES:
            self._overflow_resets += 1
            self._reset_evidence()
        if self._first_timestamp is None:
            self._first_timestamp = frame.timestamp_ms
        self._last_timestamp = frame.timestamp_ms
        self._buffer.append(frame)
        cutoff = frame.timestamp_ms - CONTEXT_MS - SAMPLE_TOLERANCE_MS
        while self._buffer and self._buffer[0].timestamp_ms < cutoff:
            self._buffer.popleft()
        self._max_buffer = max(self._max_buffer, len(self._buffer))

        if frame.timestamp_ms - self._first_timestamp < CONTEXT_MS:
            return
        if (self._last_scored_timestamp is not None
                and frame.timestamp_ms - self._last_scored_timestamp < HOP_MS):
            return
        self._last_scored_timestamp = frame.timestamp_ms
        sampler = NearestFrameSampler(
            frame.source_id, frame.timestamp_ms - CONTEXT_MS,
            frame.timestamp_ms,
        )
        for past in self._buffer:
            if past.timestamp_ms > frame.timestamp_ms:
                raise ValueError("Future frame found inside causal window")
            sampler.on_frame(past)
        try:
            features = sampler.finish()
        except ValueError as exc:
            if "Too few valid poses" not in str(exc):
                raise
            self._abstained += 1
            return
        score = self._model.predict_probability(pool_temporal_window(features))
        # Research-only model scores are never retained or exported.
        if (not isinstance(score, Real) or isinstance(score, bool)
                or not isfinite(score) or not 0 <= score <= 1):
            raise ValueError("Invalid bounded causal model probability")
        self._scored += 1
        if score >= self._threshold:
            self._positive += 1
        else:
            self._negative += 1

    def summary(self) -> dict:
        totals = CausalShadowTotals(
            incoming_frames=self._incoming,
            scored_windows=self._scored,
            positive_windows=self._positive,
            negative_windows=self._negative,
            pose_abstained_windows=self._abstained,
            source_resets=self._source_resets,
            timestamp_gap_resets=self._time_resets,
            buffer_overflow_resets=self._overflow_resets,
            max_buffered_frames_seen=self._max_buffer,
        )
        return {
            **totals.__dict__,
            "context_ms": CONTEXT_MS,
            "hop_ms": HOP_MS,
            "window_slots": 30,
            "model_input_feature_dimensions": 30,
            "only_historical_pose_frames_used": True,
            "shadow_research_only_no_incident_or_dispatch": True,
            "no_source_ids_raw_landmarks_model_probabilities_or_timestamps_exported": True,
            "not_a_real_world_recall_or_fall_onset_delay_measure": True,
        }
