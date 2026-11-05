"""Typed normalized body landmarks and fall-candidate event contracts."""
from dataclasses import dataclass, field
from math import atan2, degrees, hypot, isfinite
from uuid import uuid4

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
REQUIRED_POINTS = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    visibility: float = 1.0

    def __post_init__(self) -> None:
        if not all(isfinite(x) for x in (self.x, self.y, self.visibility)):
            raise ValueError("landmark contains a non-finite coordinate")
        if not 0 <= self.visibility <= 1:
            raise ValueError("visibility must be between 0 and 1")


@dataclass(frozen=True)
class PoseFrame:
    timestamp_ms: int
    landmarks: dict[int, Landmark]
    source_id: str = "staged-camera-01"

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0:
            raise ValueError("timestamp_ms must be non-negative")
        if not self.source_id:
            raise ValueError("source_id must be non-empty")


@dataclass(frozen=True)
class PoseFeatures:
    torso_angle_deg: float
    hip_y: float
    quality: float

    @classmethod
    def from_frame(cls, frame: PoseFrame, min_visibility: float) -> "PoseFeatures | None":
        points = [frame.landmarks.get(idx) for idx in REQUIRED_POINTS]
        if any(p is None for p in points):
            return None
        assert all(p is not None for p in points)
        if min(p.visibility for p in points) < min_visibility:
            return None
        ls, rs, lh, rh = points
        sx = (ls.x + rs.x) / 2
        sy = (ls.y + rs.y) / 2
        hx = (lh.x + rh.x) / 2
        hy = (lh.y + rh.y) / 2
        dx, dy = sx - hx, sy - hy
        if hypot(dx, dy) < 0.04:
            return None  # Pose is collapsed or too small to measure reliably.
        return cls(
            torso_angle_deg=degrees(atan2(abs(dx), abs(dy))),
            hip_y=hy,
            quality=min(p.visibility for p in points),
        )


@dataclass(frozen=True)
class FallCandidateEvent:
    id: str
    timestamp_ms: int
    source_id: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    detector: str = "temporal-pose-heuristic-v0.1"
    simulated: bool = False
    evidence_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_features(
        cls, frame: PoseFrame, features: PoseFeatures, *, drop: float
    ) -> "FallCandidateEvent":
        # Heuristic score, not a calibrated probability or clinically valid confidence.
        score = max(0.0, min(0.95, 0.48 + 0.18 * min(drop / 0.25, 1.0)
                              + 0.18 * min(features.torso_angle_deg / 90, 1.0)
                              + 0.09 * features.quality))
        return cls(
            id=str(uuid4()),
            timestamp_ms=frame.timestamp_ms,
            source_id=frame.source_id,
            confidence=round(score, 3),
            evidence_notes=[
                "Sustained horizontal torso orientation after upright posture",
                "Rapid downward normalized hip motion relative to recent upright baseline",
                "Heuristic score is NOT calibrated; confirm visually with a human",
            ],
        )
