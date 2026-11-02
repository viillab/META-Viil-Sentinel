"""Deterministic non-person ADL stress probes for V1 and Review-only V2.

Four landmarks represent *fictional* geometry only. Scenarios deliberately
expose ambiguity: an upright-to-fast-sitting transition can be indistinguishable
from a staged fall using only shoulder/hip 2D normalized pose.

Synthetic outcomes are NOT a fall dataset, false alarms/hour estimate, or
proof of model performance on real people; no files/images, Meta or network.
"""
import json
from dataclasses import dataclass

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.detector import TemporalFallDetector

from app.experimental_review_motion import ExperimentalReviewMotionDetector


@dataclass(frozen=True)
class StressScenario:
    name: str
    description: str
    frames: tuple[PoseFrame, ...]
    source_label: str = "synthetic_nonfall_adl"


def _pose(
    timestamp: int, *, hip_y: float = .45, shoulder_y: float = .25,
    shoulder_x: float = .50, hip_x: float = .50, visibility: float = .99,
    source: str = "synthetic",
) -> PoseFrame:
    return PoseFrame(
        timestamp_ms=timestamp, source_id=source,
        landmarks={
            11: Landmark(shoulder_x - .04, shoulder_y, visibility),
            12: Landmark(shoulder_x + .04, shoulder_y, visibility),
            23: Landmark(hip_x - .05, hip_y, visibility),
            24: Landmark(hip_x + .05, hip_y, visibility),
        },
    )


def _lie(timestamp: int, hip_y: float = .70, source: str = "synthetic") -> PoseFrame:
    return _pose(
        timestamp, hip_y=hip_y, shoulder_y=hip_y,
        shoulder_x=.26, hip_x=.53, source=source,
    )


def scenario_catalog() -> tuple[StressScenario, ...]:
    """Freeze scenarios independently of outcome inspection."""
    return (
        StressScenario(
            "stationary_standing", "Standing, no descent or rotation",
            tuple(_pose(t) for t in range(0, 1500, 100)),
        ),
        StressScenario(
            "stationary_lying", "Lying still, no new incident",
            tuple(_lie(t) for t in range(0, 1500, 100)),
        ),
        StressScenario(
            "slow_voluntary_sitting", "Controlled gradual lowering without rapid motion",
            tuple(_pose(t, hip_y=.45 + .012 * idx,
                        shoulder_y=.25 + .012 * idx)
                  for idx, t in enumerate(range(0, 1500, 100))),
        ),
        StressScenario(
            "rapid_voluntary_sitting",
            "Known V2 false-candidate risk: fast intentional sitting",
            (
                _pose(0), _pose(100), _pose(200),
                _pose(340, hip_y=.66, shoulder_y=.52, shoulder_x=.76),
                _pose(500, hip_y=.67, shoulder_y=.53, shoulder_x=.78),
                _pose(650, hip_y=.67, shoulder_y=.53, shoulder_x=.78),
                _pose(800, hip_y=.67, shoulder_y=.53, shoulder_x=.78),
            ),
        ),
        StressScenario(
            "quick_bend_without_descent",
            "Bent torso but no downward hip motion",
            (
                _pose(0), _pose(100), _pose(200),
                _pose(320, shoulder_x=.81, shoulder_y=.32),
                _pose(470, shoulder_x=.81, shoulder_y=.32),
                _pose(630, shoulder_x=.81, shoulder_y=.32),
                _pose(800), _pose(1000),
            ),
        ),
        StressScenario(
            "rapid_voluntary_bed_shift",
            "Known V2 false-candidate risk: fast repositioning while horizontal",
            (
                _lie(0, .45), _lie(100, .45), _lie(200, .45),
                _lie(350, .67), _lie(500, .68),
                _lie(650, .68), _lie(790, .68),
            ),
        ),
        StressScenario(
            "low_visibility_gap",
            "Low-confidence tracking clears the pending motion sequence",
            (
                _pose(0), _pose(100), _pose(200),
                _pose(340, hip_y=.66, shoulder_y=.52, shoulder_x=.76),
                _pose(420, hip_y=.66, shoulder_y=.52, shoulder_x=.76,
                      visibility=.1),
                _pose(530, hip_y=.66, shoulder_y=.52, shoulder_x=.76),
                _pose(650, hip_y=.66, shoulder_y=.52, shoulder_x=.76),
                _pose(790, hip_y=.66, shoulder_y=.52, shoulder_x=.76),
            ),
        ),
        StressScenario(
            "source_identity_change",
            "Changing camera source must discard old person's motion context",
            (
                _pose(0), _pose(100), _pose(200),
                _pose(340, hip_y=.67, shoulder_y=.53,
                      shoulder_x=.77, source="different-camera"),
                _pose(500, hip_y=.68, shoulder_y=.53,
                      shoulder_x=.77, source="different-camera"),
                _pose(670, hip_y=.68, shoulder_y=.53,
                      shoulder_x=.77, source="different-camera"),
            ),
        ),
    )


def run_synthetic_stress() -> dict[str, object]:
    scenarios = scenario_catalog()
    if len(scenarios) != len({case.name for case in scenarios}):
        raise ValueError("Duplicate synthetic ADL stress scenario")
    entries = []
    total_v1 = 0
    total_v2 = 0
    for case in scenarios:
        old = TemporalFallDetector()
        review = ExperimentalReviewMotionDetector()
        v1 = []
        v2 = []
        for frame in case.frames:
            candidate = old.process(frame)
            flagged = review.process(frame)
            if candidate:
                v1.append(candidate)
            if flagged:
                v2.append(flagged)
                if (
                    not flagged.review_only or flagged.fall_confirmed
                    or flagged.notification_authorized or flagged.meta_upload_authorized
                ):
                    raise ValueError("Experimental candidate exceeds review-only scope")
        total_v1 += len(v1)
        total_v2 += len(v2)
        entries.append({
            "scenario": case.name,
            "description": case.description,
            "synthetic_nonfall_ground_truth": True,
            "frames": len(case.frames),
            "v1_candidate_count": len(v1),
            "v2_review_candidate_count": len(v2),
            "v2_hypothesis_types": sorted({x.hypothesis for x in v2}),
            "v2_review_only": True,
            "incident_confirmed": False,
            "notification_sent": False,
            "raw_pose_coordinates_exported": False,
        })
    return {
        "status": "SYNTHETIC_ADL_STRESS_COMPLETE",
        "cases": len(scenarios),
        "case_type": "fictional_four_landmark_geometry_not_real_people",
        "purpose": "reveal_known_false_review_flags_not_accuracy_estimation",
        "v1_candidate_count": total_v1,
        "v2_review_candidate_count": total_v2,
        "v2_scenarios_with_review_flags": sum(
            x["v2_review_candidate_count"] > 0 for x in entries
        ),
        "real_world_false_alert_rate_established": False,
        "automated_emergency_dispatch": False,
        "media_sent_to_meta": False,
        "meta_api_called": False,
        "scenarios": entries,
    }


def main() -> int:
    report = run_synthetic_stress()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
