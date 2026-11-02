"""Local eight-joint temporal *observability* research, NEVER fall detection.

Consumes only already-extracted, privacy-scoped research traces. A single-pose
MediaPipe stream has NO person association: apparently continuous coordinates
can belong to different people, or change with camera position. Outputs are
aggregate diagnostics, not a person trace, intent estimate or safety clearance.

No Meta, network, FastAPI route, database/incident mutation or notifications.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal

from app.multi_joint_research import (
    MIN_LOWER_BODY_COVERAGE,
    POINTS,
    VISIBILITY_FLOOR,
    _knee_angle,
)

Point = tuple[float, float, float]
FramePoints = tuple[int, dict[int, Point]]
MotionState = Literal[
    "abstain_missing_lower_body",
    "abstain_temporal_discontinuity",
    "exploratory_temporal_geometry_available",
]


@dataclass(frozen=True, slots=True)
class TemporalObservabilityPolicy:
    """Predeclared engineering gates, uncalibrated for real fall safety."""

    min_joint_visibility: float = VISIBILITY_FLOOR
    min_all_joint_coverage: float = MIN_LOWER_BODY_COVERAGE
    min_temporal_pair_coverage: float = 0.50
    min_temporal_pairs: int = 20
    max_pair_gap_ms: int = 200
    # Inherited from the prior research evidence-quality abstention policy.
    max_consecutive_unusable: int = 12
    max_input_frames: int = 12_000

    def __post_init__(self) -> None:
        fields = (
            self.min_joint_visibility,
            self.min_all_joint_coverage,
            self.min_temporal_pair_coverage,
        )
        if any(type(v) not in (int, float) or not isfinite(v) or not 0 < v <= 1
               for v in fields):
            raise ValueError("Observability percentages must be finite and in (0, 1]")
        counts = (
            self.min_temporal_pairs, self.max_pair_gap_ms,
            self.max_consecutive_unusable, self.max_input_frames,
        )
        if any(type(v) is not int or v < 1 for v in counts):
            raise ValueError("Temporal windows and sample limits must be positive ints")


@dataclass(frozen=True, slots=True)
class TemporalAggregate:
    clip_id: str
    frames: int
    adjacent_intervals: int
    eligible_temporal_pairs: int
    all_joint_visible_frames: int
    temporal_pair_fraction: float
    all_joint_coverage: float
    longest_unusable_run_frames: int
    largest_timestamp_gap_ms: int
    discontinuity_intervals: int
    hip_center_speed_p95_normalized_per_second: float | None
    ankle_center_speed_p95_normalized_per_second: float | None
    knee_angle_rate_p95_deg_per_second: float | None
    state: MotionState
    reason_codes: tuple[str, ...]
    person_identity_verified: Literal[False] = False
    calibrated_fall_probability: Literal[False] = False
    confirms_fall: Literal[False] = False
    confirms_no_fall: Literal[False] = False
    alert_permitted: Literal[False] = False
    meta_upload_permitted: Literal[False] = False
    raw_pose_coordinates_exported: Literal[False] = False


def _p95(numbers: list[float]) -> float | None:
    if not numbers:
        return None
    ordered = sorted(numbers)
    # Explicit nearest-rank index; only group statistics are exported.
    index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return round(ordered[index], 3)


def _center(points: dict[int, Point], a: int, b: int) -> tuple[float, float]:
    return (
        (points[a][0] + points[b][0]) / 2,
        (points[a][1] + points[b][1]) / 2,
    )


def assess_temporal_observability(
    frames: Iterable[FramePoints], *,
    clip_id: str,
    policy: TemporalObservabilityPolicy | None = None,
) -> TemporalAggregate:
    """Compute motion observability from *adjacent, complete* eight-joint frames.

    A missing/occluded pose, even for one frame, breaks the velocity chain.
    Speed measures are 2D normalized-camera-plane magnitudes, NOT physical
    m/s; pan/zoom, motion blur and single-person ID switches can bias them.
    """
    if not isinstance(clip_id, str) or not 1 <= len(clip_id) <= 80:
        raise ValueError("Expected a bounded explicit clip identifier")
    config = policy or TemporalObservabilityPolicy()
    if type(config) is not TemporalObservabilityPolicy:
        raise ValueError("Unsupported observability policy")

    count = 0
    valid_count = 0
    eligible = 0
    longest_missing = 0
    missing_run = 0
    max_gap = 0
    discontinuities = 0
    previous_timestamp: int | None = None
    previous_valid: FramePoints | None = None
    hip_speeds: list[float] = []
    ankle_speeds: list[float] = []
    knee_rates: list[float] = []

    for record in frames:
        if type(record) is not tuple or len(record) != 2:
            raise ValueError("Invalid restricted time/landmark frame")
        timestamp, points = record
        if type(timestamp) is not int or timestamp < 0 or type(points) is not dict:
            raise ValueError("Invalid time or point schema")
        count += 1
        if count > config.max_input_frames:
            raise ValueError("Input clip exceeds bounded research frame count")
        if previous_timestamp is not None:
            if timestamp <= previous_timestamp:
                raise ValueError("Timestamp replay/reordering in research trace")
            gap = timestamp - previous_timestamp
            max_gap = max(max_gap, gap)
            if gap > config.max_pair_gap_ms:
                discontinuities += 1
        previous_timestamp = timestamp

        if set(points) - set(POINTS):
            raise ValueError("Unapproved joint index")
        for value in points.values():
            if (
                type(value) is not tuple or len(value) != 3
                or any(type(v) not in (int, float) or not isfinite(v) for v in value)
                or not 0 <= value[2] <= 1
            ):
                raise ValueError("Bad research landmark value")
        complete = all(
            i in points and points[i][2] >= config.min_joint_visibility
            for i in POINTS
        )
        if not complete:
            missing_run += 1
            longest_missing = max(longest_missing, missing_run)
            previous_valid = None
            continue
        missing_run = 0
        valid_count += 1
        if previous_valid is not None:
            old_timestamp, old_points = previous_valid
            dt_ms = timestamp - old_timestamp
            if dt_ms <= config.max_pair_gap_ms:
                prev_knees = [
                    _knee_angle(old_points, side=side)
                    for side in ("left", "right")
                ]
                now_knees = [
                    _knee_angle(points, side=side)
                    for side in ("left", "right")
                ]
                # _knee_angle uses the frozen 0.55 MediaPipe confidence gate.
                if all(x is not None for x in (*prev_knees, *now_knees)):
                    seconds = dt_ms / 1000
                    hip0, hip1 = _center(old_points, 23, 24), _center(points, 23, 24)
                    ankle0, ankle1 = _center(old_points, 27, 28), _center(points, 27, 28)
                    hip_speeds.append(
                        hypot(hip1[0] - hip0[0], hip1[1] - hip0[1]) / seconds
                    )
                    ankle_speeds.append(
                        hypot(ankle1[0] - ankle0[0], ankle1[1] - ankle0[1])
                        / seconds
                    )
                    knee_rates.append(
                        max(abs(a-b) for a, b in zip(prev_knees, now_knees))
                        / seconds
                    )
                    eligible += 1
        previous_valid = (timestamp, points)

    if not count:
        raise ValueError("Empty research motion trace")
    intervals = max(count - 1, 0)
    pair_fraction = eligible / intervals if intervals else 0.0
    all_coverage = valid_count / count
    reasons = [
        "single_pose_no_person_identity_association",
        "camera_motion_and_perspective_uncompensated",
        "not_a_fall_classifier",
    ]
    if all_coverage < config.min_all_joint_coverage:
        state: MotionState = "abstain_missing_lower_body"
        reasons.append("all_joint_visibility_below_gate")
    elif (
        eligible < config.min_temporal_pairs
        or pair_fraction < config.min_temporal_pair_coverage
        or longest_missing > config.max_consecutive_unusable
    ):
        state = "abstain_temporal_discontinuity"
        if longest_missing > config.max_consecutive_unusable:
            reasons.append("extended_lower_body_occlusion")
        if (
            eligible < config.min_temporal_pairs
            or pair_fraction < config.min_temporal_pair_coverage
        ):
            reasons.append("insufficient_contiguous_joint_pairs")
    else:
        state = "exploratory_temporal_geometry_available"
    if discontinuities:
        reasons.append("gapped_frame_intervals_excluded")
    if longest_missing:
        reasons.append("occluded_joint_intervals_excluded")
    return TemporalAggregate(
        clip_id=clip_id,
        frames=count,
        adjacent_intervals=intervals,
        eligible_temporal_pairs=eligible,
        all_joint_visible_frames=valid_count,
        temporal_pair_fraction=round(pair_fraction, 4),
        all_joint_coverage=round(all_coverage, 4),
        longest_unusable_run_frames=longest_missing,
        largest_timestamp_gap_ms=max_gap,
        discontinuity_intervals=discontinuities,
        hip_center_speed_p95_normalized_per_second=_p95(hip_speeds),
        ankle_center_speed_p95_normalized_per_second=_p95(ankle_speeds),
        knee_angle_rate_p95_deg_per_second=_p95(knee_rates),
        state=state,
        reason_codes=tuple(reasons),
    )
