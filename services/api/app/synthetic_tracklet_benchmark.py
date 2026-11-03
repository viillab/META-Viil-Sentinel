"""Ground-truth synthetic benchmark of anonymous pose association abstention.

No video, human identities, appearance embeddings, face data, network, or
Meta API. Actor labels are *fictional* and kept inside the benchmark
generator. Compare a legacy geometry-only research ablation to the safe
default, which refuses ALL multi-person associations.

A fully exchanged pair of silhouettes demonstrates an unavoidable
label-switch error for 2D geometric matching without identity cues.
The benchmark never calls this a real-world tracking accuracy estimate.
"""
import argparse
import json
from dataclasses import dataclass
from math import isfinite

from app.anonymous_tracklet_research import (
    AnonymousTrackletResearch,
    ResearchDetections,
    TrackletPolicy,
)


@dataclass(frozen=True, slots=True)
class FictionalFrame:
    timestamp_ms: int
    labeled_poses: tuple[tuple[str, dict[int, tuple[float, float, float]]], ...]


@dataclass(frozen=True, slots=True)
class FictionalCase:
    key: str
    frames: tuple[FictionalFrame, ...]
    stress_reason: str


def _skeleton(x: float, *, visibility: float = .99):
    """Eight fictitious normalized points, never derived from a human."""
    if not isfinite(x):
        raise ValueError("Fictional coordinate must be finite")
    return {
        11: (x-.07, .22, visibility),
        12: (x+.07, .22, visibility),
        23: (x-.06, .44, visibility),
        24: (x+.06, .44, visibility),
        25: (x-.06, .64, visibility),
        26: (x+.06, .64, visibility),
        27: (x-.06, .84, visibility),
        28: (x+.06, .84, visibility),
    }


def _case(
    name: str,
    frames: tuple[tuple[int, tuple[tuple[str, float, float], ...]], ...],
    reason: str,
) -> FictionalCase:
    return FictionalCase(
        name,
        tuple(
            FictionalFrame(
                timestamp, tuple(
                    (name, _skeleton(x, visibility=visible))
                    for name, x, visible in people
                ),
            )
            for timestamp, people in frames
        ),
        reason,
    )


def frozen_fictional_cases() -> tuple[FictionalCase, ...]:
    """Deterministic actor labels used solely as temporary synthetic oracle."""
    one = _case(
        "one_smooth_subject",
        tuple((100*i, (("alpha", .20+.009*i, .99),)) for i in range(20)),
        "single-body-consistency",
    )
    separated = _case(
        "two_separated_reordered",
        tuple(
            (
                100*i,
                tuple(reversed((
                    ("alpha", .15+.004*i, .99),
                    ("beta", .83-.004*i, .99),
                ))) if i % 2 else (
                    ("alpha", .15+.004*i, .99),
                    ("beta", .83-.004*i, .99),
                ),
            )
            for i in range(18)
        ),
        "pose-detector-output-order-permutation",
    )
    swapped = _case(
        "indistinguishable_spatial_swap",
        tuple(
            (
                100*i,
                (
                    ("alpha", .38 if i < 5 else .62, .99),
                    ("beta", .62 if i < 5 else .38, .99),
                ),
            )
            for i in range(12)
        ),
        "same-geometry-unobservable-subject-exchange",
    )
    approaching = _case(
        "approach_and_separate",
        tuple(
            (
                100*i,
                (
                    ("alpha", .20+.025*i, .99),
                    ("beta", .80-.025*i, .99),
                ),
            )
            for i in range(20)
        ),
        "near-crossing-ambiguity",
    )
    occlusion = _case(
        "brief_disappearance_reappearance",
        tuple(
            (100*i, () if i == 8 else (("alpha", .35+.004*i, .99),))
            for i in range(18)
        ),
        "no-reidentification-after-missing-pose",
    )
    low_visibility = _case(
        "lower_leg_occlusion",
        tuple(
            (
                100*i,
                (("alpha", .35+.004*i, .12 if i == 8 else .99),),
            )
            for i in range(18)
        ),
        "incomplete-joint-abstention",
    )
    clock = _case(
        "camera_timestamp_gap",
        tuple(
            (100*i + (900 if i >= 6 else 0),
             (("alpha", .35+.005*i, .99),))
            for i in range(12)
        ),
        "noninterpolated-discontinuous-time",
    )
    competing = _case(
        "one_previous_two_current",
        (
            (0, (("alpha", .5, .99),)),
            (100, (("alpha", .40, .99), ("beta", .60, .99))),
            (200, (("alpha", .30, .99), ("beta", .70, .99))),
            (300, (("alpha", .29, .99), ("beta", .71, .99))),
        ),
        "one-to-many-association-ambiguity",
    )
    return (one, separated, swapped, approaching, occlusion,
            low_visibility, clock, competing)


def benchmark_one(case: FictionalCase, *, mode: str) -> dict[str, object]:
    if mode not in ("abstain", "geometry_only"):
        raise ValueError("Unknown benchmark association policy")
    if not case.frames or len(case.frames) > 100:
        raise ValueError("Fictional benchmark case must be bounded")
    model = AnonymousTrackletResearch(TrackletPolicy(multi_person_mode=mode))
    previous: tuple[str, ...] = ()
    reference_transitions = 0
    correctly_linked = 0
    incorrectly_linked = 0
    abstained_frames = 0
    status_counts: dict[str, int] = {}
    for index, frame in enumerate(case.frames):
        identifiers = tuple(actor for actor, _ in frame.labeled_poses)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Duplicate fictional actor within one frame")
        if index > 0:
            reference_transitions += len(set(previous) & set(identifiers))
        result = model.process(ResearchDetections(
            source_id="fictional-scene",
            timestamp_ms=frame.timestamp_ms,
            poses=tuple(coords for _, coords in frame.labeled_poses),
        ))
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        if result.status.endswith("_abstain") or result.status == "temporal_gap_reset":
            abstained_frames += 1
        edges = model._last_pairs
        if len(edges) != result.linked_anonymous_pairs:
            raise ValueError("Inconsistent anonymous pair inspection")
        for old_idx, new_idx in edges:
            if old_idx >= len(previous) or new_idx >= len(identifiers):
                raise ValueError("Untrusted instantaneous benchmark edge")
            if previous[old_idx] == identifiers[new_idx]:
                correctly_linked += 1
            else:
                incorrectly_linked += 1
        previous = identifiers

    totals = model.aggregate()
    if (
        totals["adjacent_geometric_links"]
        != correctly_linked + incorrectly_linked
        or reference_transitions < correctly_linked
    ):
        raise ValueError("Benchmark ground-truth and model links disagree")
    # Each actor appearance in consecutive frames counts in the reference
    # even when a joint is low-visibility; missed links also measure deliberate
    # fail-closed abstention, NOT only tracking error.
    return {
        "case": case.key,
        "stress_reason": case.stress_reason,
        "mode": mode,
        "frames": len(case.frames),
        "reference_adjacent_actor_appearances": reference_transitions,
        "correct_anonymous_adjacent_links": correctly_linked,
        "incorrect_anonymous_adjacent_links": incorrectly_linked,
        "reference_appearances_not_linked": reference_transitions - correctly_linked,
        "conservative_frame_abstentions": abstained_frames,
        "synthetic_link_coverage": (
            round(correctly_linked / reference_transitions, 4)
            if reference_transitions else None
        ),
        "linked_pairs_with_incorrect_actor": (
            round(incorrectly_linked / totals["adjacent_geometric_links"], 4)
            if totals["adjacent_geometric_links"] else None
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "ephemeral_tracklets_started": totals["ephemeral_tracklets_started"],
        "ground_truth_fictional_only": True,
        "real_person_identity_verified": False,
        "trained_or_calibrated_model": False,
        "alert_permitted": False,
        "meta_api_called": False,
        "actor_names_or_pose_coordinates_exported": False,
    }


def benchmark_frozen_cases() -> dict[str, object]:
    cases = frozen_fictional_cases()
    if len(cases) != 8 or len({c.key for c in cases}) != 8:
        raise ValueError("Frozen fictional benchmark selection changed")
    results = [
        benchmark_one(case, mode=mode)
        for case in cases
        for mode in ("abstain", "geometry_only")
    ]
    total_by_mode = {}
    for mode in ("abstain", "geometry_only"):
        rows = [r for r in results if r["mode"] == mode]
        total_by_mode[mode] = {
            "correct_links": sum(r["correct_anonymous_adjacent_links"] for r in rows),
            "incorrect_links": sum(r["incorrect_anonymous_adjacent_links"] for r in rows),
            "unlinked_reference_appearances": sum(
                r["reference_appearances_not_linked"] for r in rows
            ),
            "abstained_frames": sum(r["conservative_frame_abstentions"] for r in rows),
            "reference_transitions": sum(
                r["reference_adjacent_actor_appearances"] for r in rows
            ),
        }
    return {
        "status": "FICTIONAL_ASSOCIATION_BENCHMARK_COMPLETE",
        "frozen_fictional_scenes": len(cases),
        "modes_compared": ("abstain", "geometry_only"),
        "real_multi_person_tracking_accuracy_measured": False,
        "synthetic_only_no_human_media": True,
        "default_mode": TrackletPolicy().multi_person_mode,
        "recommended_multi_person_release": "NO_GO",
        "reason": (
            "Eight-point geometry alone cannot distinguish two people "
            "exchanging spatial positions between sampled frames"
        ),
        "aggregate_by_mode": total_by_mode,
        "cases": results,
        "raw_pose_coordinates_exported": False,
        "identity_labels_exported": False,
        "meta_api_called": False,
        "automatic_alert_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fictional-only tracklet safety benchmark")
    parser.add_argument("--run", action="store_true", required=True)
    result = benchmark_frozen_cases()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
