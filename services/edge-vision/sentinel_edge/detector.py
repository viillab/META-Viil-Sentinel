"""Temporal pose fall-candidate detector.

An explicitly heuristic non-clinical algorithm. A potential event requires
recent upright posture, downward hip motion, and sustained horizontal torso.
No inferred medical severity and no emergency dispatch.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite
from sentinel_edge.contracts import FallCandidateEvent, PoseFeatures, PoseFrame


@dataclass(frozen=True)
class DetectorConfig:
    upright_max_angle_deg: float = 32.0
    horizontal_min_angle_deg: float = 56.0
    min_hip_descent: float = 0.13
    upright_lookback_ms: int = 1600
    horizontal_hold_ms: int = 450
    cooldown_ms: int = 4000
    max_gap_ms: int = 700
    min_visibility: float = 0.55

    def __post_init__(self) -> None:
        if not 0 <= self.upright_max_angle_deg < self.horizontal_min_angle_deg <= 90:
            raise ValueError("invalid upright/horizontal angles")
        if not 0 < self.min_hip_descent < 1:
            raise ValueError("min_hip_descent must be between 0 and 1")
        if min(self.upright_lookback_ms, self.horizontal_hold_ms,
               self.cooldown_ms, self.max_gap_ms) <= 0:
            raise ValueError("temporal limits must be positive")
        if not isfinite(self.min_visibility) or not 0 <= self.min_visibility <= 1:
            raise ValueError("invalid min_visibility")


class TemporalFallDetector:
    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self._frames: deque[tuple[int, PoseFeatures]] = deque()
        self._source_id: str | None = None
        self._last_timestamp_ms = -1
        self._pending_since: int | None = None
        self._pending_descent = 0.0
        self._last_event_ms: int | None = None

    def reset(self) -> None:
        self._frames.clear()
        self._pending_since = None
        self._pending_descent = 0.0
        self._last_event_ms = None
        self._last_timestamp_ms = -1
        self._source_id = None

    def process(self, frame: PoseFrame) -> FallCandidateEvent | None:
        if self._source_id is not None and frame.source_id != self._source_id:
            self.reset()
        self._source_id = frame.source_id
        if frame.timestamp_ms <= self._last_timestamp_ms:
            raise ValueError("frame timestamps must strictly increase")
        if (self._last_timestamp_ms >= 0
                and frame.timestamp_ms - self._last_timestamp_ms > self.config.max_gap_ms):
            # Missing data or interrupted stream is not evidence of a fall.
            self._frames.clear()
            self._pending_since = None
            self._pending_descent = 0.0
        self._last_timestamp_ms = frame.timestamp_ms

        feature = PoseFeatures.from_frame(frame, self.config.min_visibility)
        if feature is None:
            self._pending_since = None
            self._pending_descent = 0.0
            return None

        cutoff = frame.timestamp_ms - self.config.upright_lookback_ms
        while self._frames and self._frames[0][0] < cutoff:
            self._frames.popleft()
        upright = [item.hip_y for ts, item in self._frames
                   if item.torso_angle_deg <= self.config.upright_max_angle_deg]
        self._frames.append((frame.timestamp_ms, feature))

        # Require a previously upright pose; bent/sitting motion is not a fall event.
        descent = feature.hip_y - min(upright) if upright else 0.0
        horizontal = feature.torso_angle_deg >= self.config.horizontal_min_angle_deg
        enough_drop = descent >= self.config.min_hip_descent
        cooled_down = (
            self._last_event_ms is None
            or frame.timestamp_ms - self._last_event_ms >= self.config.cooldown_ms
        )

        if not cooled_down or not horizontal or not enough_drop:
            self._pending_since = None
            self._pending_descent = 0.0
            return None

        if self._pending_since is None:
            self._pending_since = frame.timestamp_ms
            self._pending_descent = descent
            return None

        self._pending_descent = max(self._pending_descent, descent)
        if frame.timestamp_ms - self._pending_since < self.config.horizontal_hold_ms:
            return None

        self._pending_since = None
        self._last_event_ms = frame.timestamp_ms
        return FallCandidateEvent.from_features(
            frame, feature, drop=self._pending_descent
        )
