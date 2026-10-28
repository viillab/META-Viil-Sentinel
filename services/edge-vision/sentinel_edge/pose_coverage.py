"""Privacy-minimal pose coverage observer for authorized local RTSP research.

A decoded frame without usable torso landmarks can mean an empty room, a
different pose, occlusion, darkness, multiple people, or model failure.
It MUST NOT be labeled camera disconnection or absence of a fall.
No images, landmarks, timestamps, identifiers or external requests are retained.
"""


class PoseCoverageMonitor:
    """Track pose-observation gaps within ONE capture + model session."""

    def __init__(self, *, gap_threshold_frames: int = 45,
                 gap_threshold_ms: int = 3000) -> None:
        if type(gap_threshold_frames) is not int or not 1 <= gap_threshold_frames <= 300:
            raise ValueError("gap_threshold_frames must be an integer in 1..300")
        if type(gap_threshold_ms) is not int or not 250 <= gap_threshold_ms <= 30000:
            raise ValueError("gap_threshold_ms must be an integer in 250..30000")
        self.gap_threshold_frames = gap_threshold_frames
        self.gap_threshold_ms = gap_threshold_ms
        self._timestamp_mode: bool | None = None
        self._last_timestamp_ms: int | None = None
        self._no_pose_started_ms: int | None = None
        self._longest_no_pose_duration_ms: int | None = None
        self.frames = 0
        self.pose_observed_frames = 0
        self.consecutive_no_pose = 0
        self.longest_no_pose_streak = 0
        self._indeterminate = False

    def observe(self, pose_observed: bool, *, timestamp_ms: int | None = None) -> dict | None:
        """Track pose gaps by frames AND elapsed time if timestamps are available.

        Source-relative milliseconds are used for duration only and are never
        serialized or mixed across RTSP reconnection epochs.
        """
        if type(pose_observed) is not bool:
            raise ValueError("pose_observed must be boolean")
        if timestamp_ms is not None and (
            type(timestamp_ms) is not int or timestamp_ms < 0
            or (self._last_timestamp_ms is not None
                and timestamp_ms <= self._last_timestamp_ms)
        ):
            raise ValueError("timestamp_ms must be strictly increasing nonnegative int")
        uses_timestamps = timestamp_ms is not None
        if self._timestamp_mode is not None and uses_timestamps != self._timestamp_mode:
            raise ValueError("Do not mix frame-only and timestamp-aware observations")
        self._timestamp_mode = uses_timestamps
        if uses_timestamps:
            self._last_timestamp_ms = timestamp_ms
        self.frames += 1
        if pose_observed:
            self.pose_observed_frames += 1
            self.consecutive_no_pose = 0
            self._no_pose_started_ms = None
            if self._indeterminate:
                self._indeterminate = False
                return self._event("pose_observed_again")
            return None
        self.consecutive_no_pose += 1
        if self.consecutive_no_pose == 1:
            self._no_pose_started_ms = timestamp_ms
        if timestamp_ms is not None and self._no_pose_started_ms is not None:
            duration = timestamp_ms - self._no_pose_started_ms
            self._longest_no_pose_duration_ms = max(
                self._longest_no_pose_duration_ms or 0, duration
            )
        self.longest_no_pose_streak = max(
            self.longest_no_pose_streak, self.consecutive_no_pose
        )
        enough_frames = self.consecutive_no_pose >= self.gap_threshold_frames
        enough_time = (
            timestamp_ms is None
            or (self._no_pose_started_ms is not None
                and timestamp_ms - self._no_pose_started_ms >= self.gap_threshold_ms)
        )
        if not self._indeterminate and enough_frames and enough_time:
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
            "gap_threshold_ms": self.gap_threshold_ms,
            "duration_gate_applied": self._timestamp_mode is True,
            "longest_no_pose_duration_ms": self._longest_no_pose_duration_ms,
            "condition": (
                "pose_not_observed" if self._indeterminate
                else "pose_seen" if self.pose_observed_frames
                else "unverified"
            ),
            "operator_diagnostic_only": True,
            "person_absence_or_fall_inferred": False,
            "not_a_camera_health_or_safety_certification": True,
        }
