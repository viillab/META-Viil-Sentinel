"""Opt-in geometric classification of 2 MediaPipe poses for offline research.

No identity or person count conclusions. Only a categorical summary is
returned; normalized coordinates and confidence values must NOT be logged.
A spatial overlap does not prove duplicate detection or the same person.
"""
from math import hypot, isfinite
from typing import Any

from sentinel_edge.contracts import REQUIRED_POINTS
from sentinel_edge.pose_adapter import MIN_CONFIDENCE

MULTIPOSE_CATEGORIES = (
    "not_multiple",
    "overlapping_torso_geometry",
    "spatially_separated_geometry",
    "ambiguous_geometry",
    "unusable_torso_geometry",
    "unsupported_pose_count",
)


def _torso(points, threshold):
    if not isinstance(points, (tuple, list)) or len(points) <= max(REQUIRED_POINTS):
        return None
    output = []
    for index in REQUIRED_POINTS:
        p = points[index]
        try:
            x, y = float(p.x), float(p.y)
            visibility = getattr(p, "visibility", None)
            if visibility is None:
                return None
            visibility = float(visibility)
            presence = getattr(p, "presence", None)
            presence = float(presence) if presence is not None else None
        except (TypeError, ValueError, AttributeError, OverflowError):
            return None
        if (not all(isfinite(v) for v in (x, y, visibility))
                or presence is not None and not isfinite(presence)
                or not 0 <= x <= 1 or not 0 <= y <= 1
                or not threshold <= visibility <= 1
                or presence is not None and presence < threshold):
            return None
        output.append((x, y))
    shoulder = ((output[0][0] + output[1][0]) / 2,
                (output[0][1] + output[1][1]) / 2)
    hip = ((output[2][0] + output[3][0]) / 2,
           (output[2][1] + output[3][1]) / 2)
    length = hypot(shoulder[0] - hip[0], shoulder[1] - hip[1])
    if length < .04:
        return None
    midpoint = ((shoulder[0] + hip[0]) / 2, (shoulder[1] + hip[1]) / 2)
    return output, midpoint, length


def multipose_spatial_category(result: Any, *,
                                min_confidence: float = MIN_CONFIDENCE) -> str:
    """Predeclared scale-aware geometrical buckets, no pose selection.

    Bins are exploratory and intentionally strict; a safety decision must
    abstain for *every* input in these multi-pose classes.
    """
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be within 0..1")
    poses = getattr(result, "pose_landmarks", None)
    if not isinstance(poses, (tuple, list)) or len(poses) < 2:
        return "not_multiple"
    if len(poses) != 2:
        return "unsupported_pose_count"
    first, second = (_torso(p, min_confidence) for p in poses)
    if first is None or second is None:
        return "unusable_torso_geometry"
    keypoints_a, centre_a, length_a = first
    keypoints_b, centre_b, length_b = second
    centre_dist = hypot(centre_a[0] - centre_b[0],
                        centre_a[1] - centre_b[1])
    max_keypoint_dist = max(
        hypot(a[0] - b[0], a[1] - b[1])
        for a, b in zip(keypoints_a, keypoints_b)
    )
    smaller = min(length_a, length_b)
    larger = max(length_a, length_b)
    # Fixed BEFORE examination of the 11 external reference predictions.
    if (centre_dist <= max(.03, .20 * smaller)
            and max_keypoint_dist <= max(.04, .30 * smaller)):
        return "overlapping_torso_geometry"
    if centre_dist >= max(.24, .75 * larger):
        return "spatially_separated_geometry"
    return "ambiguous_geometry"
