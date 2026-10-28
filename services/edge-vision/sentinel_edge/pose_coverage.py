"""Privacy-minimal pose coverage observer for authorized local RTSP research.

A decoded frame without usable torso landmarks can mean an empty room, a
different pose, occlusion, darkness, multiple people, or model failure.
It MUST NOT be labeled camera disconnection or absence of a fall.
No images, landmarks, timestamps, identifiers or external requests are retained.
"""


class PoseCoverageMonitor:
    """Track pose-observation gaps within ONE capture + model session."""

    def __init__(self, *, gap_threshold_frames: int = 45) -> None:
        if type(gap_threshold_frames) is not int or not 1 <= gap_threshold_frames <= 300:
            raise ValueError("gap_threshold_frames must be an integer in 1..300")
        self.gap_threshold_frames = gap_threshold_frames
        self.frames = 0
        self.pose_observed_frames = 0
        self.consecutive_no_pose = 0
        self.longest_no_pose_streak = 0
        self._indeterminate = False

    def observe(self, pose_observed: bool) -> dict | None:
        """Return transitions for operator diagnostics, never caregiver alarms."""
        if type(pose_observed) is not bool:
            raise ValueError("pose_observed must be boolean")
        self.frames += 1
        if pose_observed:
            self.pose_observed_frames += 1
            self.consecutive_no_pose = 0
            if self._indeterminate:
                self._indeterminate = False
                return self._event("pose_observed_again")
            return None
        self.consecutive_no_pose += 1
        self.longest_no_pose_streak = max(
            self.longest_no_pose_streak, self.consecutive_no_pose
        )
        if not self._indeterminate and self.consecutive_no_pose >= self.gap_threshold_frames:
            self._indeterminate = True
            return self._event("pose_not_observed")
        return None

    @staticmethod
    def _event(condition: str) -> dict:
        return {
            "schema_version": "viil.edge.pose_coverage.v1",
            "condition": condition,
            "operator_diagnostic_only": True,
            "camera_stream_disconnection_inferred": False,
            "person_absence_or_fall_inferred": False,
        }

    def summary(self) -> dict:
        return {
            "schema_version": "viil.edge.pose_coverage.v1",
            "frames_observed": self.frames,
            "pose_observed_frames": self.pose_observed_frames,
            "longest_no_pose_streak_frames": self.longest_no_pose_streak,
            "no_pose_streak_at_end_frames": self.consecutive_no_pose,
            "gap_threshold_frames": self.gap_threshold_frames,
            "condition": (
                "pose_not_observed" if self._indeterminate
                else "pose_seen" if self.pose_observed_frames
                else "unverified"
            ),
            "operator_diagnostic_only": True,
            "person_absence_or_fall_inferred": False,
            "not_a_camera_health_or_safety_certification": True,
        }
