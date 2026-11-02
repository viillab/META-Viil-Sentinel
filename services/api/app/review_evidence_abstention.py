"""Fail-closed quality / abstention envelope for local V1 + experimental V2.

The existing video trace contains *only four torso landmarks*. It cannot
distinguish a deliberate sit/bed shift from a fall, identify a person,
verify camera perspective, or establish clinical safety. Even agreement
between V1 and V2 is correlated: both consume the same four points.

This module is a SEPARATE research-only, local, read-only decision layer.
It produces no incident, emergency dispatch, consent grants, Meta calls or
automatic reassurance. It has no dependency on the FastAPI incident routes.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from sentinel_edge.contracts import PoseFeatures, PoseFrame
from sentinel_edge.detector import TemporalFallDetector

from app.experimental_review_motion import ExperimentalReviewMotionDetector

ReviewState = Literal[
    "abstain_insufficient_pose",
    "no_candidate_not_clearance",
    "single_heuristic_review_only",
    "dual_heuristic_review_only",
]


@dataclass(frozen=True, slots=True)
class ReviewQualityPolicy:
    """Conservative diagnostics, NOT independently calibrated thresholds."""

    min_frames: int = 20
    min_observed_ms: int = 700
    min_valid_pose_fraction: float = 0.75
    max_gap_ms: int = 700
    max_consecutive_unusable: int = 12
    min_torso_visibility: float = 0.55
    event_pair_window_ms: int = 1_200

    def __post_init__(self) -> None:
        integer_fields = (
            self.min_frames,
            self.min_observed_ms,
            self.max_gap_ms,
            self.max_consecutive_unusable,
            self.event_pair_window_ms,
        )
        if any(type(x) is not int or x <= 0 for x in integer_fields):
            raise ValueError("Quality policy requires positive integer windows")
        floats = (self.min_valid_pose_fraction, self.min_torso_visibility)
        if any(
            type(x) not in (float, int)
            or not isfinite(x)
            or not 0 < x <= 1
            for x in floats
        ):
            raise ValueError("Quality fractions must be finite in (0, 1]")


@dataclass(frozen=True, slots=True)
class ReviewEvidenceDecision:
    """Only aggregate counts and bounded fixed reason codes, no coordinates."""

    source_id: str
    status: ReviewState
    reason_codes: tuple[str, ...]
    frames: int
    valid_pose_frames: int
    valid_pose_fraction: float
    longest_unusable_run_frames: int
    largest_timestamp_gap_ms: int
    observed_span_ms: int
    v1_candidate_count: int
    v2_review_candidate_count: int
    event_aligned_dual_heuristic: bool
    human_review_proposed: bool
    abstained_due_to_quality: bool
    raw_landmarks_exported: Literal[False] = False
    fall_confirmed: Literal[False] = False
    no_fall_confirmed: Literal[False] = False
    automatic_notification_permitted: Literal[False] = False
    emergency_dispatch_permitted: Literal[False] = False
    meta_upload_permitted: Literal[False] = False
    provider_called: Literal[False] = False
    calibrated_fall_probability_available: Literal[False] = False


def assess_pose_frames(
    frames: Iterable[PoseFrame],
    *,
    source_id: str,
    policy: ReviewQualityPolicy | None = None,
) -> ReviewEvidenceDecision:
    """Validate monotonic, same-source frames and apply fixed advisory gates.

    This function never returns an autonomous 'safe' state. A missing
    candidate is *not* evidence that a fall did not happen.
    """
    if not isinstance(source_id, str) or not source_id or len(source_id) > 80:
        raise ValueError("Expected one explicit bounded source identifier")
    config = policy or ReviewQualityPolicy()
    if type(config) is not ReviewQualityPolicy:
        raise ValueError("Unsupported quality policy instance")
    v1 = TemporalFallDetector()
    v2 = ExperimentalReviewMotionDetector()
    first_ts: int | None = None
    previous_ts: int | None = None
    total = 0
    valid = 0
    max_gap = 0
    run_invalid = 0
    max_invalid = 0
    v1_times: list[int] = []
    v2_times: list[int] = []

    for frame in frames:
        if type(frame) is not PoseFrame or frame.source_id != source_id:
            raise ValueError("Mixed/non-PoseFrame source was rejected")
        if previous_ts is not None:
            if frame.timestamp_ms <= previous_ts:
                raise ValueError("Timestamp replay or frame reordering")
            max_gap = max(max_gap, frame.timestamp_ms - previous_ts)
        else:
            first_ts = frame.timestamp_ms
        previous_ts = frame.timestamp_ms
        total += 1
        if total > 100_000:
            raise ValueError("Unbounded pose trace rejected")
        feature = PoseFeatures.from_frame(frame, config.min_torso_visibility)
        if feature is not None:
            valid += 1
            run_invalid = 0
        else:
            run_invalid += 1
            max_invalid = max(max_invalid, run_invalid)

        old_event = v1.process(frame)
        review_event = v2.process(frame)
        if old_event is not None:
            v1_times.append(old_event.timestamp_ms)
        if review_event is not None:
            if not review_event.review_only or review_event.notification_authorized:
                raise ValueError("Unexpected effectful experimental signal")
            v2_times.append(review_event.timestamp_ms)

    if not total or first_ts is None or previous_ts is None:
        raise ValueError("Empty pose stream")
    observed = previous_ts - first_ts
    fraction = valid / total
    quality_codes = []
    if total < config.min_frames:
        quality_codes.append("too_few_frames")
    if observed < config.min_observed_ms:
        quality_codes.append("short_observation_window")
    if fraction < config.min_valid_pose_fraction:
        quality_codes.append("low_pose_coverage")
    if max_invalid > config.max_consecutive_unusable:
        quality_codes.append("extended_pose_occlusion")
    if max_gap > config.max_gap_ms:
        quality_codes.append("timestamp_discontinuity")

    aligned = any(
        abs(a - b) <= config.event_pair_window_ms
        for a in v1_times for b in v2_times
    )
    has_signal = bool(v1_times or v2_times)
    # Even aligned agreement is not independent corroboration: both
    # detectors depend on the same four torso landmarks.
    if quality_codes:
        state: ReviewState = "abstain_insufficient_pose"
    elif aligned:
        state = "dual_heuristic_review_only"
    elif has_signal:
        state = "single_heuristic_review_only"
    else:
        state = "no_candidate_not_clearance"

    return ReviewEvidenceDecision(
        source_id=source_id,
        status=state,
        reason_codes=(
            *quality_codes,
            "torso_four_points_only",
            "activity_intent_unobservable",
            "detectors_share_correlated_evidence",
            "no_clinical_approval",
        ),
        frames=total,
        valid_pose_frames=valid,
        valid_pose_fraction=round(fraction, 4),
        longest_unusable_run_frames=max_invalid,
        largest_timestamp_gap_ms=max_gap,
        observed_span_ms=observed,
        v1_candidate_count=len(v1_times),
        v2_review_candidate_count=len(v2_times),
        event_aligned_dual_heuristic=aligned,
        human_review_proposed=has_signal and not quality_codes,
        abstained_due_to_quality=bool(quality_codes),
    )
