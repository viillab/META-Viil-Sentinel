"""Ephemeral, opt-in research-only multi-pose association potential.

No output coordinates, persistent IDs, association tracks or selected poses.
A 'unique_candidate' is NOT a verified same person and is NEVER sent
to the real-time incident detector. Anchor comes ONLY from a strict
single-person frame, never from a multi-pose candidate. The short horizon
prevents indefinite drift and forces abstention on ambiguous geometry.
"""
from math import hypot
from typing import Any

from sentinel_edge.multipose_spatial_diagnostics import _torso
from sentinel_edge.pose_adapter import MIN_CONFIDENCE
from sentinel_edge.pose_rejection_diagnostics import pose_adapter_reason

ASSOCIATION_CATEGORIES = (
    "single_anchor",
    "single_unusable",
    "single_accepted_geometry_unusable",
    "no_single_pose",
    "multiple_short_anchor_unique_candidate",
    "multiple_short_anchor_ambiguous",
    "multiple_short_anchor_no_match",
    "multiple_anchor_stale_or_missing",
    "multiple_unusable_geometry",
    "multiple_unsupported_count",
)

MULTIPLE_CATEGORIES = tuple(
    name for name in ASSOCIATION_CATEGORIES if name.startswith("multiple_")
)
MAX_ANCHOR_GAP_FRAMES = 6


class OfflineAssociationObserver:
    """RAM-only strict single-torso anchor; every multi-person pose abstains.

    Values are predeclared engineering heuristics, NOT fitted or optimized on
    previously inspected ASSIST-IoT reference clips.
    """

    def __init__(self, *, min_confidence: float = MIN_CONFIDENCE):
        if not 0 <= min_confidence <= 1:
            raise ValueError("Invalid association confidence gate")
        self._threshold = min_confidence
        self._index = 0
        self._anchor = None
        self._last_anchor_frame = -1

    def observe(self, result: Any) -> str:
        index = self._index
        self._index += 1
        poses = getattr(result, "pose_landmarks", None)
        if not isinstance(poses, (tuple, list)) or len(poses) == 0:
            return "no_single_pose"
        if len(poses) == 1:
            if pose_adapter_reason(result, min_confidence=self._threshold) != "accepted":
                self._anchor = None
                return "single_unusable"
            torso = _torso(poses[0], self._threshold)
            if torso is None:
                self._anchor = None
                return "single_accepted_geometry_unusable"
            self._anchor = torso
            self._last_anchor_frame = index
            return "single_anchor"
        # All multi-pose frames remain REJECTED by the production adapter.
        if len(poses) != 2:
            return "multiple_unsupported_count"
        if self._anchor is None or index - self._last_anchor_frame > MAX_ANCHOR_GAP_FRAMES:
            return "multiple_anchor_stale_or_missing"
        first, second = (_torso(p, self._threshold) for p in poses)
        if first is None or second is None:
            return "multiple_unusable_geometry"
        _, centre, length = self._anchor
        distances = [
            hypot(p[1][0] - centre[0], p[1][1] - centre[1])
            for p in (first, second)
        ]
        # The tighter bound and a required far alternate make identity
        # association deliberately *more* cautious than pose selection.
        max_match_distance = max(.04, .25 * length)
        near = [d <= max_match_distance for d in distances]
        if not any(near):
            return "multiple_short_anchor_no_match"
        # If BOTH match the anchor there is no unique candidate. Even if
        # only one matches, a second pose must be well separated.
        far_other = max(.22, .70 * length)
        if sum(near) == 1 and max(distances) >= far_other:
            return "multiple_short_anchor_unique_candidate"
        return "multiple_short_anchor_ambiguous"
