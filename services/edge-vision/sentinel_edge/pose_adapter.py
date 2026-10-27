"""Convert MediaPipe task results into a minimal, fail-closed torso contract.

No raw images, face landmarks, identity or inferential health information
leave this adapter. Empty landmarks represent unknown/occluded state.
"""
from math import isfinite
from typing import Any

from sentinel_edge.contracts import Landmark, REQUIRED_POINTS

MIN_CONFIDENCE = 0.55


def extract_torso_landmarks(result: Any, *, min_confidence: float = MIN_CONFIDENCE) -> dict[int, Landmark]:
    """Use exactly one unambiguous detected person; otherwise return no pose.

    MediaPipe may return None for a landmark's visibility/presence. These are
    treated as unavailable measurements, not proof of high confidence.
    """
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be within 0..1")

    poses = getattr(result, "pose_landmarks", None)
    if not isinstance(poses, (list, tuple)) or len(poses) != 1:
        return {}
    points = poses[0]
    if not isinstance(points, (list, tuple)) or len(points) <= max(REQUIRED_POINTS):
        return {}

    converted: dict[int, Landmark] = {}
    for idx in REQUIRED_POINTS:
        point = points[idx]
        try:
            x, y = float(point.x), float(point.y)
            visibility = getattr(point, "visibility", None)
            presence = getattr(point, "presence", None)
            if visibility is None:
                return {}
            visible = float(visibility)
            if not all(isfinite(n) for n in (x, y, visible)):
                return {}
            # Coordinates outside the image make the torso geometry ambiguous.
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return {}
            if visible < min_confidence or visible > 1.0:
                return {}
            if presence is not None:
                presence_score = float(presence)
                if not isfinite(presence_score) or presence_score < min_confidence:
                    return {}
            converted[idx] = Landmark(x=x, y=y, visibility=visible)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return {}
    return converted
