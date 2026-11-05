"""Research-only reason taxonomy for the existing STRICT MediaPipe torso adapter.

Runs inside the authorized local video decoder only when a diagnostic
callback is supplied. Never exports an image, joint coordinates, per-frame
timestamp, confidence value or identifying subject features.
The categorical reason is only an observation at the adapter gate;
it does NOT establish a physical-world cause or justify loosened gates.
"""
from math import isfinite
from typing import Any

from sentinel_edge.contracts import REQUIRED_POINTS
from sentinel_edge.pose_adapter import MIN_CONFIDENCE

REASONS = (
    "accepted",
    "no_person",
    "multiple_people",
    "malformed_result",
    "malformed_torso",
    "missing_visibility",
    "invalid_numeric",
    "out_of_frame",
    "low_visibility",
    "low_presence",
)


def pose_adapter_reason(result: Any, *, min_confidence: float = MIN_CONFIDENCE) -> str:
    """Return exactly one bounded reason for the *original* adapter decision."""
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be within 0..1")
    poses = getattr(result, "pose_landmarks", None)
    if not isinstance(poses, (list, tuple)):
        return "malformed_result"
    if not poses:
        return "no_person"
    if len(poses) > 1:
        return "multiple_people"
    points = poses[0]
    if not isinstance(points, (list, tuple)) or len(points) <= max(REQUIRED_POINTS):
        return "malformed_torso"
    for idx in REQUIRED_POINTS:
        point = points[idx]
        try:
            x, y = float(point.x), float(point.y)
            raw_visibility = getattr(point, "visibility", None)
            raw_presence = getattr(point, "presence", None)
            if raw_visibility is None:
                return "missing_visibility"
            visible = float(raw_visibility)
            if not all(isfinite(v) for v in (x, y, visible)):
                return "invalid_numeric"
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return "out_of_frame"
            if visible < min_confidence:
                return "low_visibility"
            if visible > 1.0:
                return "invalid_numeric"
            if raw_presence is not None:
                presence = float(raw_presence)
                if not isfinite(presence):
                    return "invalid_numeric"
                if presence < min_confidence:
                    return "low_presence"
        except (AttributeError, TypeError, ValueError, OverflowError):
            return "invalid_numeric"
    return "accepted"
