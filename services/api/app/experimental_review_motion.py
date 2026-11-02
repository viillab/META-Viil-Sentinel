"""Experimental REVIEW-ONLY fall-motion hypotheses for separate development clips.

This cannot diagnose a fall, trigger an alarm, or upgrade a synthetic source
to a verified real-person event. Never replace Member 1's detector with this
without independently labeled, subject-separated validation. No Meta calls.

The two hypotheses avoid the mandatory 'previously upright' requirement:
  rapid_descent_rotation: rapid normalized hip descent PLUS rotation in a
    short local time window and a semi-horizontal ending posture.
  horizontal_descent: rapid normalized hip descent while body is horizontal,
    potentially useful for bed-edge motion but confounded by ordinary ADL.

No inference about injury, emergency priority or physical safety is made.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from sentinel_edge.contracts import PoseFeatures, PoseFrame

ReviewHypothesis = Literal["rapid_descent_rotation", "horizontal_descent"]


@dataclass(frozen=True)
class ReviewMotionConfig:
    min_visibility: float = 0.55
    rapid_window_ms: int = 650
    max_history_ms: int = 1300
    min_rapid_hip_drop: float = 0.16
    min_angle_change_deg: float = 20.0
    min_final_angle_deg: float = 38.0
    horizontal_min_angle_deg: float = 60.0
    stable_hold_ms: int = 280
    max_event_window_ms: int = 1100
    cooldown_ms: int = 4000
    max_frame_gap_ms: int = 700

    def __post_init__(self) -> None:
        if not 0 <= self.min_visibility <= 1:
            raise ValueError("visibility must be 0-1")
        if not 0 < self.min_rapid_hip_drop <= 0.6:
            raise ValueError("drop must be normalized and positive")
        if not 0 < self.min_angle_change_deg <= 90:
            raise ValueError("rotation must be 0-90")
        if not 0 <= self.min_final_angle_deg <= self.horizontal_min_angle_deg <= 90:
            raise ValueError("invalid postures")
        values = (
            self.rapid_window_ms, self.max_history_ms, self.stable_hold_ms,
            self.max_event_window_ms, self.cooldown_ms, self.max_frame_gap_ms,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("temporal windows must be positive integers")
        if self.max_history_ms < self.rapid_window_ms:
            raise ValueError("history cannot be shorter than rapid motion window")
        if not all(isfinite(x) for x in (
            self.min_rapid_hip_drop, self.min_angle_change_deg,
            self.min_final_angle_deg, self.horizontal_min_angle_deg,
        )):
            raise ValueError("nonfinite experiment configuration")


@dataclass(frozen=True)
class ReviewMotionCandidate:
    timestamp_ms: int
    source_id: str
    hypothesis: ReviewHypothesis
    review_only: Literal[True] = True
    fall_confirmed: Literal[False] = False
    notification_authorized: Literal[False] = False
    meta_upload_authorized: Literal[False] = False
    probability_calibrated: Literal[False] = False


class ExperimentalReviewMotionDetector:
    """No I/O, no external services; stream in immutable PoseFrame records."""

    def __init__(self, config: ReviewMotionConfig | None = None):
        self.config = config or ReviewMotionConfig()
        self.reset()

    def reset(self) -> None:
        self._source: str | None = None
        self._last_ts = -1
        self._history: deque[tuple[int, PoseFeatures]] = deque()
        self._pending: tuple[int, ReviewHypothesis] | None = None
        self._last_event: int | None = None

    def _candidate_mode(self, timestamp: int, current: PoseFeatures
                        ) -> ReviewHypothesis | None:
        # Search *prior* frames in a bounded rapid-descent time window.
        # The current frame has not yet been enqueued.
        for earlier_ts, earlier in reversed(self._history):
            elapsed = timestamp - earlier_ts
            if elapsed > self.config.rapid_window_ms:
                break
            if elapsed <= 0:
                continue
            delta_hip = current.hip_y - earlier.hip_y
            if delta_hip < self.config.min_rapid_hip_drop:
                continue
            delta_angle = current.torso_angle_deg - earlier.torso_angle_deg
            if (
                delta_angle >= self.config.min_angle_change_deg
                and current.torso_angle_deg >= self.config.min_final_angle_deg
            ):
                return "rapid_descent_rotation"
            if (
                earlier.torso_angle_deg >= self.config.horizontal_min_angle_deg
                and current.torso_angle_deg >= self.config.horizontal_min_angle_deg
            ):
                return "horizontal_descent"
        return None

    def process(self, frame: PoseFrame) -> ReviewMotionCandidate | None:
        if self._source is not None and frame.source_id != self._source:
            self.reset()
        self._source = frame.source_id
        if frame.timestamp_ms <= self._last_ts:
            raise ValueError("Review motion timestamps must increase")
        if (
            self._last_ts >= 0
            and frame.timestamp_ms - self._last_ts > self.config.max_frame_gap_ms
        ):
            # No inference across discontinuous media or uncertain tracking.
            self._history.clear()
            self._pending = None
        self._last_ts = frame.timestamp_ms
        pose = PoseFeatures.from_frame(frame, self.config.min_visibility)
        if pose is None:
            self._pending = None
            self._history.clear()
            return None
        cutoff = frame.timestamp_ms - self.config.max_history_ms
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        if (
            self._last_event is not None
            and frame.timestamp_ms - self._last_event < self.config.cooldown_ms
        ):
            self._pending = None
            self._history.append((frame.timestamp_ms, pose))
            return None

        onset = self._candidate_mode(frame.timestamp_ms, pose)
        self._history.append((frame.timestamp_ms, pose))
        if onset is not None and self._pending is None:
            self._pending = (frame.timestamp_ms, onset)

        if self._pending is None:
            return None
        start, mode = self._pending
        required_angle = (
            self.config.min_final_angle_deg
            if mode == "rapid_descent_rotation" else self.config.horizontal_min_angle_deg
        )
        if (
            pose.torso_angle_deg < required_angle
            or frame.timestamp_ms - start > self.config.max_event_window_ms
        ):
            self._pending = None
            return None
        if frame.timestamp_ms - start < self.config.stable_hold_ms:
            return None
        self._pending = None
        self._last_event = frame.timestamp_ms
        return ReviewMotionCandidate(
            timestamp_ms=frame.timestamp_ms,
            source_id=frame.source_id,
            hypothesis=mode,
        )
