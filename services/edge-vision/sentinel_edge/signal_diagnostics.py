"""Aggregate-only diagnostics for known false-negative fall clips.

These are *detector gate observations*, not event labels, diagnoses or
explanations of causality. Counts are over pose features held in RAM. No
raw images, names or landmark coordinates are included in output.
"""
from collections import deque
from dataclasses import asdict, dataclass

from sentinel_edge.contracts import PoseFeatures, PoseFrame
from sentinel_edge.detector import DetectorConfig


@dataclass(frozen=True)
class SignalDiagnostics:
    analyzed_frames: int
    valid_torso_frames: int
    upright_frames: int
    horizontal_frames: int
    horizontal_with_descent_frames: int
    max_observed_descent: float
    max_horizontal_descent_hold_ms: int
    configured_horizontal_hold_ms: int
    configured_min_hip_descent: float
    configured_horizontal_min_angle_deg: float


def diagnose_pose_signals(
    frames: list[PoseFrame], config: DetectorConfig | None = None,
) -> dict:
    """Report detector gate coverage; no frame-level or personal-data outputs."""
    c = config or DetectorConfig()
    history: deque[tuple[int, PoseFeatures]] = deque()
    valid = upright_n = horizontal_n = combo_n = 0
    max_drop = 0.0
    longest_run_ms = 0
    run_since: int | None = None
    previous_timestamp: int | None = None

    for frame in frames:
        ts = frame.timestamp_ms
        if previous_timestamp is not None and ts - previous_timestamp > c.max_gap_ms:
            history.clear()
            run_since = None
        previous_timestamp = ts
        feature = PoseFeatures.from_frame(frame, c.min_visibility)
        if feature is None:
            history.clear()
            run_since = None
            continue

        valid += 1
        horizontal = feature.torso_angle_deg >= c.horizontal_min_angle_deg
        upright = feature.torso_angle_deg <= c.upright_max_angle_deg
        horizontal_n += int(horizontal)
        upright_n += int(upright)
        while history and history[0][0] < ts - c.upright_lookback_ms:
            history.popleft()
        upright_baseline = [
            p.hip_y for _, p in history if p.torso_angle_deg <= c.upright_max_angle_deg
        ]
        drop = feature.hip_y - min(upright_baseline) if upright_baseline else 0.0
        max_drop = max(max_drop, drop)
        both = horizontal and drop >= c.min_hip_descent
        if both:
            combo_n += 1
            if run_since is None:
                run_since = ts
            longest_run_ms = max(longest_run_ms, ts - run_since)
        else:
            run_since = None
        history.append((ts, feature))

    return asdict(SignalDiagnostics(
        analyzed_frames=len(frames),
        valid_torso_frames=valid,
        upright_frames=upright_n,
        horizontal_frames=horizontal_n,
        horizontal_with_descent_frames=combo_n,
        max_observed_descent=round(max_drop, 4),
        max_horizontal_descent_hold_ms=longest_run_ms,
        configured_horizontal_hold_ms=c.horizontal_hold_ms,
        configured_min_hip_descent=c.min_hip_descent,
        configured_horizontal_min_angle_deg=c.horizontal_min_angle_deg,
    ))
