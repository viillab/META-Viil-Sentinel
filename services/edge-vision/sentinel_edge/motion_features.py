"""Experimental bounded temporal pose features for future trained classifiers.

NOT a fall classifier. Never feed these vectors to the production alert path
until a separately trained and held-out validated model is established.
Images, identity labels, raw keypoints and traces are not retained or written.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite

from sentinel_edge.contracts import PoseFeatures, PoseFrame

FEATURE_NAMES = (
    "torso_angle_normalized",
    "hip_y_normalized",
    "hip_vertical_speed_per_s_clipped",
    "torso_rotation_speed_per_s_clipped",
    "torso_visibility",
    "pose_observed_mask",
)
MAX_WINDOW = 256
MAX_GAP_MS = 700


@dataclass(frozen=True, slots=True)
class MotionWindow:
    """Chronologically ordered dense features; missing frames have mask=0."""
    features: tuple[tuple[float, ...], ...]
    feature_names: tuple[str, ...] = FEATURE_NAMES
    model_status: str = "FEATURES_ONLY_NOT_TRAINED"

    def __post_init__(self) -> None:
        if not self.features or len(self.features) > MAX_WINDOW:
            raise ValueError("window must contain 1..256 samples")
        if any(len(row) != len(FEATURE_NAMES) or
               not all(isfinite(value) for value in row) for row in self.features):
            raise ValueError("motion feature rows must have six finite channels")


class TemporalFeatureEncoder:
    """Lightweight bounded per-source rolling pose feature extraction.

    Velocity uses real dt, not frame index; visibility gaps invalidate
    derivatives, and timestamp gaps/source switches reset the window. Source
    IDs are never stored in exported MotionWindow or any output JSON.
    """
    def __init__(self, *, window_size: int = 30, min_visibility: float = 0.55,
                 max_gap_ms: int = MAX_GAP_MS):
        if type(window_size) is not int or not 2 <= window_size <= MAX_WINDOW:
            raise ValueError("window_size must be 2..256")
        if type(min_visibility) not in (float, int) or not (
            isfinite(min_visibility) and 0 <= min_visibility <= 1
        ):
            raise ValueError("min_visibility must be 0..1")
        if type(max_gap_ms) is not int or not 1 <= max_gap_ms <= 10_000:
            raise ValueError("max_gap_ms must be 1..10000")
        self.window_size = window_size
        self.min_visibility = min_visibility
        self.max_gap_ms = max_gap_ms
        self._values: deque[tuple[float, ...]] = deque(maxlen=window_size)
        self._source_id: str | None = None
        self._last_timestamp: int | None = None
        self._last_feature: PoseFeatures | None = None

    def reset(self) -> None:
        self._values.clear()
        self._source_id = None
        self._last_timestamp = None
        self._last_feature = None

    def process(self, frame: PoseFrame) -> MotionWindow:
        if self._source_id is not None and frame.source_id != self._source_id:
            self.reset()
        if self._last_timestamp is not None:
            dt = frame.timestamp_ms - self._last_timestamp
            if dt <= 0:
                raise ValueError("motion frames must have strictly increasing timestamps")
            if dt > self.max_gap_ms:
                self.reset()
        else:
            dt = 0
        self._source_id = frame.source_id
        feature = PoseFeatures.from_frame(frame, self.min_visibility)
        if feature is None:
            row = (0.0,) * len(FEATURE_NAMES)
            self._last_feature = None
        else:
            speed_y = rotation = 0.0
            if self._last_feature is not None and dt > 0:
                seconds = dt / 1000.0
                speed_y = (feature.hip_y - self._last_feature.hip_y) / seconds
                rotation = (feature.torso_angle_deg -
                            self._last_feature.torso_angle_deg) / seconds
            row = (
                feature.torso_angle_deg / 90.0,
                feature.hip_y,
                max(-4.0, min(4.0, speed_y)),
                max(-360.0, min(360.0, rotation)) / 360.0,
                feature.quality, 1.0,
            )
            self._last_feature = feature
        self._values.append(row)
        self._last_timestamp = frame.timestamp_ms
        return MotionWindow(tuple(self._values))

    def padded_window(self) -> MotionWindow:
        """Left pad with missing-mask rows to a stable tensor shape.

        Padding is NOT an observation and cannot be used as fall evidence.
        """
        missing = ((0.0,) * len(FEATURE_NAMES),) * (
            self.window_size - len(self._values)
        )
        return MotionWindow(missing + tuple(self._values))


def summarize_motion_signals(frames) -> dict:
    """Offline aggregate-only research signal summary, NOT a fall inference.

    Input PoseFrames stay in-memory; the returned dict contains *no* raw
    feature sequences, landmark positions, source IDs, image/video or people.
    """
    encoder = TemporalFeatureEncoder()
    analyzed = observed = 0
    max_hip_speed = max_rotation_speed = 0.0
    for frame in frames:
        window = encoder.process(frame)
        row = window.features[-1]
        analyzed += 1
        observed += int(row[5] == 1.0)
        max_hip_speed = max(max_hip_speed, abs(row[2]))
        max_rotation_speed = max(max_rotation_speed, abs(row[3]) * 360)
    if not analyzed:
        raise ValueError("Motion diagnostics require at least one frame")
    return {
        "feature_set": "experimental_pose_motion_v1",
        "trained_model": False,
        "analyzed_frames": analyzed,
        "pose_observed_frames": observed,
        "max_abs_hip_speed_per_s_clipped": round(max_hip_speed, 3),
        "max_abs_torso_rotation_deg_per_s_clipped": round(max_rotation_speed, 3),
        "raw_pose_saved": False,
        "not_a_fall_prediction": True,
    }
