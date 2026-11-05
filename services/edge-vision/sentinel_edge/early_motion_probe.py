"""Experimental causal 2-second fall-motion *cue*, NOT a trained model.

A conservative kinematic proposal probe intended to diagnose why a
trained 8-second shadow model is too slow / rarely has enough pose context.
Only one fail-closed original torso pose is accepted. No identity selection,
incident generation, medically meaningful probability, or alert authority.

Fixed, a priori kinematic gates are explicitly NOT tuned on public Fall clips:
recent upright <=32 degrees, normalized hip descent >=.13, vertical
speed >=.20 units/second, sustained >=40ms in at least two observed frames.
No final horizontal-posture requirement, so ordinary sitting can trigger.
This diagnostic must never be promoted to safety alerts or described as AI.
"""
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from sentinel_edge.contracts import PoseFeatures, PoseFrame

LOOKBACK_MS = 2_000
UPRIGHT_LOOKBACK_MS = 1_500
MAX_GAP_MS = 700
COOLDOWN_MS = 2_500
MIN_OBSERVATION_MS = 200
MIN_SUSTAIN_MS = 40
MAX_STEP_MS = 250
MIN_UPRIGHT_ANGLE_DEG = 32.0
MIN_HIP_DESCENT = 0.13
MIN_DOWNWARD_SPEED_PER_S = 0.20
MAX_BUFFERED_POSES = 240


@dataclass(frozen=True)
class ProbeSnapshot:
    frames: int
    pose_accepted_frames: int
    pose_abstained_frames: int
    samples_with_recent_upright_baseline: int
    downward_cue_frames: int
    provisional_motion_proposals: int
    cooldown_suppressed_frames: int
    source_resets: int
    timestamp_gap_resets: int
    maximum_pose_history_frames: int


class CausalMotionProbe:
    """One-source 2s RAM-only *research probe* that returns no event objects."""

    def __init__(self, *, private_proposal_consumer: Callable[[int], None] | None = None):
        # Opt-in offline-only review evidence; normal camera summary stays private/minimal.
        self._private_proposal_consumer = private_proposal_consumer
        self._history = deque(maxlen=MAX_BUFFERED_POSES)
        self._last_timestamp = None
        self._last_valid = None
        self._source_id = None
        self._cue_since = None
        self._cue_samples = 0
        self._last_proposal = None
        self._frames = 0
        self._accepted = 0
        self._abstained = 0
        self._baseline = 0
        self._cues = 0
        self._proposals = 0
        self._cooled = 0
        self._sources = 0
        self._gaps = 0
        self._max_history = 0

    def _clear_evidence(self):
        self._history.clear()
        self._last_valid = None
        self._cue_since = None
        self._cue_samples = 0

    def observe(self, frame: PoseFrame) -> None:
        """Consumes strict original PoseFrames; NEVER emits a fall incident."""
        if self._source_id is not None and frame.source_id != self._source_id:
            self._sources += 1
            self._clear_evidence()
            self._last_timestamp = None
            self._last_proposal = None
        elif self._last_timestamp is not None:
            delta = frame.timestamp_ms - self._last_timestamp
            if delta <= 0:
                raise ValueError("Motion probe timestamps must strictly increase")
            if delta > MAX_GAP_MS:
                self._gaps += 1
                self._clear_evidence()
        self._source_id = frame.source_id
        self._last_timestamp = frame.timestamp_ms
        self._frames += 1
        feature = PoseFeatures.from_frame(frame, min_visibility=.55)
        if feature is None:
            self._abstained += 1
            self._clear_evidence()
            return
        self._accepted += 1
        cutoff = frame.timestamp_ms - LOOKBACK_MS
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        upright = [
            hip for ts, hip, angle in self._history
            if ts >= frame.timestamp_ms - UPRIGHT_LOOKBACK_MS
            and angle <= MIN_UPRIGHT_ANGLE_DEG
        ]
        previous = self._last_valid
        self._history.append((
            frame.timestamp_ms, feature.hip_y, feature.torso_angle_deg
        ))
        self._max_history = max(self._max_history, len(self._history))
        self._last_valid = (frame.timestamp_ms, feature.hip_y)
        if upright:
            self._baseline += 1
        if (not upright or previous is None
                or frame.timestamp_ms - self._history[0][0] < MIN_OBSERVATION_MS):
            self._cue_since = None
            self._cue_samples = 0
            return
        dt_ms = frame.timestamp_ms - previous[0]
        if not 0 < dt_ms <= MAX_STEP_MS:
            self._cue_since = None
            self._cue_samples = 0
            return
        speed = (feature.hip_y - previous[1]) * 1000 / dt_ms
        cue = (
            feature.hip_y - min(upright) >= MIN_HIP_DESCENT
            and speed >= MIN_DOWNWARD_SPEED_PER_S
        )
        if not cue:
            self._cue_since = None
            self._cue_samples = 0
            return
        self._cues += 1
        if self._cue_since is None:
            self._cue_since = frame.timestamp_ms
            self._cue_samples = 1
            return
        self._cue_samples += 1
        if (self._cue_samples < 2
                or frame.timestamp_ms - self._cue_since < MIN_SUSTAIN_MS):
            return
        if (self._last_proposal is not None
                and frame.timestamp_ms - self._last_proposal < COOLDOWN_MS):
            self._cooled += 1
            return
        self._proposals += 1
        self._last_proposal = frame.timestamp_ms
        if self._private_proposal_consumer is not None:
            self._private_proposal_consumer(frame.timestamp_ms)
        self._cue_since = None
        self._cue_samples = 0

    def summary(self) -> dict:
        data = ProbeSnapshot(
            frames=self._frames,
            pose_accepted_frames=self._accepted,
            pose_abstained_frames=self._abstained,
            samples_with_recent_upright_baseline=self._baseline,
            downward_cue_frames=self._cues,
            provisional_motion_proposals=self._proposals,
            cooldown_suppressed_frames=self._cooled,
            source_resets=self._sources,
            timestamp_gap_resets=self._gaps,
            maximum_pose_history_frames=self._max_history,
        )
        return {
            **data.__dict__,
            "lookback_ms": LOOKBACK_MS,
            "not_a_trained_classifier": True,
            "not_a_confirmed_fall_or_emergency_incident": True,
            "no_model_score_poses_frames_or_timestamps_exported": True,
            "not_calibrated_for_sitting_camera_motion_or_occlusion": True,
        }
