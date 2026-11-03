"""Seeded, bounded fictional multi-pose stress corpus with oracle associations.

This intentionally falsifies a tempting but unsafe belief: a *single
detected pose* per frame is NOT independent proof of persistent identity.
A synthetic actor handoff at the same coordinates causes an incorrect
association even under the conservative multi-person-abstain default.

Pure Python synthetic coordinates only. No network, human data, image,
model weights, face recognition, Meta API or clinical prediction.
"""
import argparse
import json
from random import Random

from app.anonymous_tracklet_research import TrackletPolicy
from app.synthetic_tracklet_benchmark import FictionalCase, _case, benchmark_one

OFFICIAL_SEEDS = 32
FAMILIES = (
    "single_subject_jitter",
    "invisible_single_pose_handoff",
    "two_people_pose_order_shuffle",
    "two_people_full_position_swap",
    "two_people_near_crossing",
    "single_pose_occlusion",
    "camera_time_discontinuity",
    "three_people_shuffled",
)


def generate_seeded_scenes(seed: int) -> tuple[FictionalCase, ...]:
    """Generate eight fixed-format mathematical scenes for one integer seed.

    Seed affects only small nuisance variation in geometry and the order
    of fictional pose detections. It never imports source video frames.
    """
    if type(seed) is not int or not 0 <= seed < OFFICIAL_SEEDS:
        raise ValueError("Seed outside frozen deterministic stress corpus")
    rnd = Random(0x5A17_2026 + seed)
    def jitter() -> float:
        return rnd.uniform(-.0015, .0015)

    alone = _case(
        "single_subject_jitter",
        tuple(
            (100*i, (("alpha", .25+.004*i+jitter(), .99),))
            for i in range(20)
        ),
        "small-temporal-perturbations",
    )
    # No simultaneous crowd here. A new fake actor appears without a
    # blank frame, at precisely the former actor's plausible trajectory.
    # Geometry cannot detect this substitution from pose alone.
    handoff = _case(
        "invisible_single_pose_handoff",
        tuple(
            (100*i, ((
                "alpha" if i < 10 else "beta",
                .28+.003*i+jitter(), .99,
            ),))
            for i in range(20)
        ),
        "single-detection-identity-substitution-unobservable",
    )

    def reorder_pair(i: int):
        pair = (
            ("alpha", .17+.003*i+jitter(), .99),
            ("beta", .83-.003*i+jitter(), .99),
        )
        return tuple(reversed(pair)) if rnd.getrandbits(1) else pair

    shuffled = _case(
        "two_people_pose_order_shuffle",
        tuple((100*i, reorder_pair(i)) for i in range(20)),
        "arbitrary-pose-output-order",
    )
    swap = _case(
        "two_people_full_position_swap",
        tuple(
            (100*i, (
                ("alpha", (.38 if i < 10 else .62)+jitter(), .99),
                ("beta", (.62 if i < 10 else .38)+jitter(), .99),
            ))
            for i in range(20)
        ),
        "indistinguishable-person-swap-between-sampled-frames",
    )
    near_crossing = _case(
        "two_people_near_crossing",
        tuple(
            (100*i, (
                ("alpha", .19+.027*i+jitter(), .99),
                ("beta", .81-.027*i+jitter(), .99),
            ))
            for i in range(20)
        ),
        "overlapping-pelvis-region",
    )
    occlusion = _case(
        "single_pose_occlusion",
        tuple(
            (
                100*i,
                () if i == 14 else (
                    ("alpha", .32+.003*i+jitter(), .10 if i == 7 else .99),
                ),
            )
            for i in range(20)
        ),
        "unseen-frame-and-low-confidence-limbs",
    )
    timed = _case(
        "camera_time_discontinuity",
        tuple(
            (
                100*i+(700 if i >= 11 else 0),
                (("alpha", .30+.004*i+jitter(), .99),),
            )
            for i in range(20)
        ),
        "timestamp-gap-beyond-allowed-200ms",
    )
    def shuffle_triple(i: int):
        entries = [
            ("alpha", .12+.002*i+jitter(), .99),
            ("beta", .50+jitter(), .99),
            ("gamma", .88-.002*i+jitter(), .99),
        ]
        rnd.shuffle(entries)
        return tuple(entries)

    triple = _case(
        "three_people_shuffled",
        tuple((100*i, shuffle_triple(i)) for i in range(20)),
        "three-person-order-confusion",
    )
    return (alone, handoff, shuffled, swap, near_crossing, occlusion, timed, triple)


def run_seeded_audit(*, seeds: int = OFFICIAL_SEEDS) -> dict[str, object]:
    if type(seeds) is not int or not 1 <= seeds <= OFFICIAL_SEEDS:
        raise ValueError("Seed budget must be in frozen range 1..32")
    if TrackletPolicy().multi_person_mode != "abstain":
        raise ValueError("Unsafe default tracklet mode detected")
    modes = ("abstain", "geometry_only")
    stats = {
        family: {
            mode: {
                "fictional_reference_transitions": 0,
                "correct_links": 0,
                "incorrect_links": 0,
                "unlinked_reference_appearances": 0,
                "abstained_frames": 0,
                "examples_with_incorrect_links": 0,
            }
            for mode in modes
        }
        for family in FAMILIES
    }
    for seed in range(seeds):
        cases = generate_seeded_scenes(seed)
        if len(cases) != len(FAMILIES) or tuple(c.key for c in cases) != FAMILIES:
            raise ValueError("Frozen family corpus unexpectedly changed")
        for case in cases:
            for mode in modes:
                result = benchmark_one(case, mode=mode)
                dst = stats[case.key][mode]
                if (
                    result["correct_anonymous_adjacent_links"]
                    + result["reference_appearances_not_linked"]
                    != result["reference_adjacent_actor_appearances"]
                ):
                    raise ValueError("Ground-truth reference denominator inconsistent")
                dst["fictional_reference_transitions"] += (
                    result["reference_adjacent_actor_appearances"]
                )
                dst["correct_links"] += result["correct_anonymous_adjacent_links"]
                dst["incorrect_links"] += result["incorrect_anonymous_adjacent_links"]
                dst["unlinked_reference_appearances"] += (
                    result["reference_appearances_not_linked"]
                )
                dst["abstained_frames"] += result["conservative_frame_abstentions"]
                if result["incorrect_anonymous_adjacent_links"]:
                    dst["examples_with_incorrect_links"] += 1
    by_mode = {}
    for mode in modes:
        by_mode[mode] = {
            key: sum(stats[family][mode][key] for family in FAMILIES)
            for key in next(iter(stats.values()))[mode]
        }
    # These are **counterexamples**, not expected quality targets.
    # A silent actor substitution is undetectable from one-at-a-time
    # coordinates, even if the crowd mode is set to abstain.
    if not (
        stats["invisible_single_pose_handoff"]["abstain"]["incorrect_links"] > 0
        and stats["two_people_full_position_swap"]["geometry_only"]["incorrect_links"] > 0
        and sum(
            stats[family]["abstain"]["incorrect_links"]
            for family in FAMILIES if family != "invisible_single_pose_handoff"
        ) == 0
    ):
        raise ValueError("Required conservative identity-ambiguity regression changed")
    return {
        "status": "FROZEN_SEEDED_SYNTHETIC_TRACKLET_STRESS_COMPLETE",
        "seeds": seeds,
        "families": len(FAMILIES),
        "fictional_cases": seeds * len(FAMILIES),
        "policy_replays": seeds * len(FAMILIES) * len(modes),
        "fixed_public_seed_base": "0x5A172026",
        "default_mode": "abstain",
        "important_finding": (
            "Single detected pose per frame cannot establish that the "
            "same person is continuously present. Even conservative "
            "multi-person abstention may link two fictional actor IDs "
            "incorrectly after an unobservable handoff."
        ),
        "real_world_identity_accuracy_measured": False,
        "identity_ground_truth_only_mathematical": True,
        "trained_or_validated_fall_model": False,
        "production_identity_tracking_authorized": False,
        "no_raw_coordinates_or_actor_labels_in_output": True,
        "no_meta_api_call": True,
        "no_alert_dispatch": True,
        "by_mode": by_mode,
        "by_family": stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded deterministic fictional pose association stress audit",
    )
    parser.add_argument("--run", action="store_true", required=True)
    args = parser.parse_args()
    _ = args
    print(json.dumps(run_seeded_audit(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
