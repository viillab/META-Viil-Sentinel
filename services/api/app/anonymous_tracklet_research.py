"""Conservative anonymous pose-tracklet association research (NO identity tracking).

Creates ephemeral in-process geometric tracklets from a bounded set of
synthetic or licensed LOCAL eight-point detections. Rejects ambiguous crowds,
missing limbs, crossings and occlusion rather than guessing a person identity
or interpolating human motion. Tracklet handles are NEVER exported.

This is not face/body identification, calibrated person tracking, a fall
classifier, caregiver authorization, emergency dispatch, or Meta integration.
All results remain nonbinding research diagnostics.
"""
from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal

from app.multi_joint_research import POINTS, VISIBILITY_FLOOR

Point = tuple[float, float, float]
Pose = dict[int, Point]
FrameStatus = Literal[
    "new_anonymous_tracklets",
    "anonymous_geometry_linked",
    "no_pose_abstain",
    "low_visibility_abstain",
    "ambiguous_people_abstain",
    "temporal_gap_reset",
]


@dataclass(frozen=True, slots=True)
class TrackletPolicy:
    """Fixed, uncalibrated normalized-image-space geometry thresholds."""

    max_poses_per_frame: int = 4
    max_frames: int = 12_000
    # Conservative default prevents silent person swaps in close/crossing
    # multi-person clips. "geometry_only" is explicit research ablation.
    multi_person_mode: Literal["abstain", "geometry_only"] = "abstain"
    min_visibility: float = VISIBILITY_FLOOR
    max_center_displacement: float = 0.14
    # Prevent a large apparent jump being linked over an implausibly
    # short interval. Image-plane units, not physically calibrated.
    max_center_speed_normalized_per_second: float = 2.0
    ambiguity_proximity: float = 0.13
    max_frame_gap_ms: int = 200
    min_torso_length: float = 0.035
    max_torso_length_ratio: float = 1.8

    def __post_init__(self) -> None:
        if self.multi_person_mode not in ("abstain", "geometry_only"):
            raise ValueError("Unsupported multi-person research policy")
        integer_fields = (
            self.max_poses_per_frame, self.max_frames, self.max_frame_gap_ms,
        )
        if any(type(x) is not int or x <= 0 for x in integer_fields):
            raise ValueError("Tracklet capacities/time windows must be positive integers")
        if self.max_poses_per_frame > 8 or self.max_frames > 20_000:
            raise ValueError("Unbounded research association configuration")
        for x in (
            self.min_visibility, self.max_center_displacement,
            self.max_center_speed_normalized_per_second,
            self.ambiguity_proximity, self.min_torso_length,
            self.max_torso_length_ratio,
        ):
            if type(x) not in (int, float) or not isfinite(x):
                raise ValueError("Non-finite tracklet geometry")
        if not 0 < self.min_visibility <= 1:
            raise ValueError("Visibility must be in (0,1]")
        if not 0 < self.max_center_displacement <= 1:
            raise ValueError("Displacement must be bounded")
        if not 0 < self.max_center_speed_normalized_per_second <= 10:
            raise ValueError("Image-plane speed must be bounded")
        if not 0 < self.ambiguity_proximity <= 1:
            raise ValueError("Ambiguity distance must be bounded")
        if not 0 < self.min_torso_length < 1:
            raise ValueError("Torso length gate invalid")
        if not 1 <= self.max_torso_length_ratio <= 3:
            raise ValueError("Unrealistic torso scale ratio")


@dataclass(frozen=True, slots=True)
class ResearchDetections:
    source_id: str
    timestamp_ms: int
    poses: tuple[Pose, ...]


@dataclass(frozen=True, slots=True)
class TrackletStep:
    status: FrameStatus
    poses_observed: int
    linked_anonymous_pairs: int
    new_anonymous_tracklets: int
    active_anonymous_tracklets: int
    human_identity_verified: Literal[False] = False
    occlusion_interpolated: Literal[False] = False
    confirmed_fall: Literal[False] = False
    confirmed_no_fall: Literal[False] = False
    alert_permitted: Literal[False] = False
    meta_upload_permitted: Literal[False] = False
    raw_coordinates_exported: Literal[False] = False


@dataclass(slots=True)
class _LocalTracklet:
    center: tuple[float, float]
    torso_length: float
    consecutive_frames: int


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _geometry(pose: Pose, policy: TrackletPolicy):
    if type(pose) is not dict or set(pose) - set(POINTS):
        raise ValueError("Untrusted or unapproved research landmark fields")
    for p in pose.values():
        if (
            type(p) is not tuple or len(p) != 3
            or any(type(v) not in (int, float) or not isfinite(v) for v in p)
            or not -2 <= p[0] <= 3 or not -2 <= p[1] <= 3
            or not 0 <= p[2] <= 1
        ):
            raise ValueError("Invalid raw eight-point research geometry")
    if any(i not in pose or pose[i][2] < policy.min_visibility for i in POINTS):
        return None
    # Only geometry, no image, clothing, identity vector or descriptor.
    shoulders = ((pose[11][0] + pose[12][0]) / 2,
                 (pose[11][1] + pose[12][1]) / 2)
    hips = ((pose[23][0] + pose[24][0]) / 2,
            (pose[23][1] + pose[24][1]) / 2)
    length = _dist(shoulders, hips)
    if length < policy.min_torso_length:
        return None
    return hips, length


class AnonymousTrackletResearch:
    """Simple bounded geometric matching, *not verified person tracking*.

    Any lost frame, occlusion, ambiguous multi-person association, timestamp
    gap or short torso tracklet breaks identity continuity immediately.
    Reappearance starts a NEW anonymous tracklet; NEVER reidentify.
    """

    def __init__(self, policy: TrackletPolicy | None = None):
        self.policy = policy or TrackletPolicy()
        if type(self.policy) is not TrackletPolicy:
            raise ValueError("Unsupported research tracklet policy")
        self._source: str | None = None
        self._last_time: int | None = None
        self._active: list[_LocalTracklet] = []
        self.frames = 0
        self.links = 0
        self.started = 0
        self.longest_consecutive_frames = 0
        self.abstained_empty = 0
        self.abstained_low_visibility = 0
        self.abstained_ambiguous = 0
        self.gap_resets = 0
        self.max_seen_poses = 0
        # Instantaneous detection-index edges for *fictional benchmark only*.
        # NOT persistent track IDs; cleared every frame and NEVER serialized.
        self._last_pairs: tuple[tuple[int, int], ...] = ()

    def _step(self, status: FrameStatus, detected: int, linked: int = 0,
              new: int = 0) -> TrackletStep:
        self.links += linked
        self.started += new
        if self._active:
            self.longest_consecutive_frames = max(
                self.longest_consecutive_frames,
                *(t.consecutive_frames for t in self._active),
            )
        return TrackletStep(
            status=status, poses_observed=detected,
            linked_anonymous_pairs=linked, new_anonymous_tracklets=new,
            active_anonymous_tracklets=len(self._active),
        )

    def process(self, frame: ResearchDetections) -> TrackletStep:
        # Failed inputs invalidate continuity. No matching is allowed
        # across an untrusted frame, including bad timestamp or source.
        self._last_pairs = ()
        try:
            if type(frame) is not ResearchDetections:
                raise ValueError("Unsupported multi-pose frame structure")
            if (
                type(frame.source_id) is not str or not 1 <= len(frame.source_id) <= 80
                or type(frame.timestamp_ms) is not int or frame.timestamp_ms < 0
                or type(frame.poses) is not tuple
                or len(frame.poses) > self.policy.max_poses_per_frame
            ):
                raise ValueError("Invalid bounded multi-pose frame/source/time")
            if self._source is not None and frame.source_id != self._source:
                raise ValueError("Cross-camera/source motion association rejected")
            if self._last_time is not None and frame.timestamp_ms <= self._last_time:
                raise ValueError("Duplicate/reordered timestamp rejected")
            if self.frames >= self.policy.max_frames:
                raise ValueError("Unbounded association trace rejected")
            geometries = [_geometry(pose, self.policy) for pose in frame.poses]
        except (ValueError, TypeError):
            self._active.clear()
            raise
        # Commit state only after every restricted pose has passed validation.
        if self._source is None:
            self._source = frame.source_id
        self.frames += 1
        gap = (frame.timestamp_ms - self._last_time
               if self._last_time is not None else 0)
        self._last_time = frame.timestamp_ms
        self.max_seen_poses = max(self.max_seen_poses, len(frame.poses))
        if any(g is None for g in geometries):
            self._active.clear()
            self.abstained_low_visibility += 1
            return self._step("low_visibility_abstain", len(frame.poses))
        if not geometries:
            self._active.clear()
            self.abstained_empty += 1
            return self._step("no_pose_abstain", 0)

        # A crowded pair with nearly coincident pelvis centers is inherently
        # ambiguous from 8 points; do not force association through crossing.
        if any(
            _dist(ga[0], gb[0]) <= self.policy.ambiguity_proximity
            for i, ga in enumerate(geometries)
            for gb in geometries[i + 1:]
        ):
            self._active.clear()
            self.abstained_ambiguous += 1
            return self._step("ambiguous_people_abstain", len(frame.poses))

        if (
            self.policy.multi_person_mode == "abstain"
            and (len(geometries) > 1 or len(self._active) > 1)
        ):
            # Eight skeletal landmarks cannot prove person identity after a
            # full position swap between sampled frames. No geometric
            # association is authorized when 2+ people are involved.
            self._active.clear()
            self.abstained_ambiguous += 1
            return self._step("ambiguous_people_abstain", len(frame.poses))

        if gap > self.policy.max_frame_gap_ms:
            self._active.clear()
            self.gap_resets += 1
            self._active = [_LocalTracklet(center, scale, 1)
                            for center, scale in geometries]
            return self._step("temporal_gap_reset", len(frame.poses),
                              new=len(geometries))

        # Only one-to-one unambiguous matches, no global assignment forcing
        # and no extrapolation across occlusions. Proximity alternatives
        # invalidate the *whole* scene rather than guessing a track.
        associations: list[tuple[int, int]] = []
        for t_idx, tracklet in enumerate(self._active):
            for p_idx, (center, scale) in enumerate(geometries):
                if (
                    _dist(tracklet.center, center)
                    <= min(
                        self.policy.max_center_displacement,
                        self.policy.max_center_speed_normalized_per_second * gap / 1000,
                    )
                    and max(scale / tracklet.torso_length,
                            tracklet.torso_length / scale)
                    <= self.policy.max_torso_length_ratio
                ):
                    associations.append((t_idx, p_idx))
        if (
            len({t for t, _ in associations}) < len(associations)
            or len({p for _, p in associations}) < len(associations)
        ):
            self._active.clear()
            self.abstained_ambiguous += 1
            return self._step("ambiguous_people_abstain", len(frame.poses))

        pair_by_new = {p: t for t, p in associations}
        updated = []
        for idx, (center, scale) in enumerate(geometries):
            t_idx = pair_by_new.get(idx)
            consecutive = (
                self._active[t_idx].consecutive_frames + 1
                if t_idx is not None else 1
            )
            updated.append(_LocalTracklet(center, scale, consecutive))
        self._active = updated
        self._last_pairs = tuple(associations)
        return self._step(
            "anonymous_geometry_linked" if associations else "new_anonymous_tracklets",
            len(frame.poses), linked=len(associations),
            new=len(geometries) - len(associations),
        )

    def aggregate(self) -> dict[str, object]:
        if self.frames == 0:
            raise ValueError("Cannot publish empty tracklet experiment")
        return {
            "status": "ANONYMOUS_TRACKLET_RESEARCH_COMPLETE",
            "frames_observed": self.frames,
            "adjacent_geometric_links": self.links,
            "ephemeral_tracklets_started": self.started,
            "longest_contiguous_tracklet_frames": self.longest_consecutive_frames,
            "no_pose_frames_abstained": self.abstained_empty,
            "incomplete_eight_joint_frames_abstained": self.abstained_low_visibility,
            "multi_person_ambiguous_frames_abstained": self.abstained_ambiguous,
            "timestamp_discontinuity_resets": self.gap_resets,
            "max_poses_seen_in_one_frame": self.max_seen_poses,
            "real_person_identity_verified": False,
            "reidentified_across_occlusion": False,
            "interpolated_missing_person_coordinates": False,
            "automatic_fall_detection": False,
            "automated_alert_permitted": False,
            "real_media_uploaded": False,
            "meta_api_called": False,
            "raw_person_coordinates_exported": False,
        }
