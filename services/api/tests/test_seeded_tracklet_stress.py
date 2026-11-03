"""Reproducible fictional association stress and fail-closed rejection tests.

No real human media. These tests MUST keep the warning that no single-pose
stream, however clean, proves identity across an unobserved subject swap.
"""
from dataclasses import asdict

import pytest

from app.anonymous_tracklet_research import (
    AnonymousTrackletResearch,
    ResearchDetections,
)
from app.seeded_tracklet_stress import (
    FAMILIES,
    OFFICIAL_SEEDS,
    generate_seeded_scenes,
    run_seeded_audit,
)
from app.synthetic_tracklet_benchmark import benchmark_one


def test_seeded_research_corpus_is_bounded_deterministic_and_original():
    assert OFFICIAL_SEEDS == 32
    assert len(FAMILIES) == len(set(FAMILIES)) == 8
    a = generate_seeded_scenes(7)
    b = generate_seeded_scenes(7)
    assert a == b
    assert a != generate_seeded_scenes(6)
    assert tuple(x.key for x in a) == FAMILIES
    assert all(len(x.frames) == 20 for x in a)
    assert all(x.frames[i].timestamp_ms > x.frames[i-1].timestamp_ms
               for x in a for i in range(1, len(x.frames)))
    assert all(len(f.labeled_poses) <= 3 for x in a for f in x.frames)


def test_default_safe_mode_still_misses_an_unobservable_one_actor_handoff():
    for seed in (0, 7, 31):
        case = next(
            c for c in generate_seeded_scenes(seed)
            if c.key == "invisible_single_pose_handoff"
        )
        conservative = benchmark_one(case, mode="abstain")
        assert conservative["incorrect_anonymous_adjacent_links"] == 1
        assert conservative["correct_anonymous_adjacent_links"] == 18
        assert conservative["reference_adjacent_actor_appearances"] == 18
        assert conservative["reference_appearances_not_linked"] == 0
        assert conservative["ground_truth_fictional_only"] is True
        assert conservative["real_person_identity_verified"] is False
        assert conservative["alert_permitted"] is False


def test_full_frozen_seeded_stress_exposes_both_known_ambiguity_types():
    result = run_seeded_audit()
    assert result["status"] == "FROZEN_SEEDED_SYNTHETIC_TRACKLET_STRESS_COMPLETE"
    assert result["seeds"] == 32
    assert result["families"] == 8
    assert result["fictional_cases"] == 256
    assert result["policy_replays"] == 512
    assert result["default_mode"] == "abstain"
    assert result["real_world_identity_accuracy_measured"] is False
    assert result["identity_ground_truth_only_mathematical"] is True
    assert result["production_identity_tracking_authorized"] is False
    assert result["no_raw_coordinates_or_actor_labels_in_output"] is True
    assert result["no_meta_api_call"] is True
    assert result["no_alert_dispatch"] is True
    a = result["by_mode"]["abstain"]
    g = result["by_mode"]["geometry_only"]
    assert a["fictional_reference_transitions"] == 7808
    assert g["fictional_reference_transitions"] == a["fictional_reference_transitions"]
    assert a["correct_links"] == 2240
    assert a["incorrect_links"] == 32  # solo-person switch not observable!
    assert a["unlinked_reference_appearances"] == 5568
    assert g["correct_links"] == 7328
    assert g["incorrect_links"] == 96
    assert g["unlinked_reference_appearances"] == 480
    assert result["by_family"]["invisible_single_pose_handoff"]["abstain"][
        "examples_with_incorrect_links"
    ] == 32
    assert result["by_family"]["two_people_full_position_swap"]["geometry_only"][
        "incorrect_links"
    ] == 64
    assert result["by_family"]["two_people_full_position_swap"]["abstain"][
        "incorrect_links"
    ] == 0
    assert result["by_family"]["three_people_shuffled"]["abstain"][
        "incorrect_links"
    ] == 0


@pytest.mark.parametrize("bad", [-1, True, 32, 10.5, "1"])
def test_reject_unapproved_fictional_seed(bad):
    with pytest.raises(ValueError):
        generate_seeded_scenes(bad)


@pytest.mark.parametrize("bad", [0, -2, True, 33, 1.5, "32"])
def test_reject_unbounded_stress_runs(bad):
    with pytest.raises(ValueError):
        run_seeded_audit(seeds=bad)


def test_short_seeded_replay_contains_no_actor_names_coordinates_or_images():
    result = run_seeded_audit(seeds=2)
    assert result["fictional_cases"] == 16
    assert result["policy_replays"] == 32
    assert result["by_mode"]["abstain"]["incorrect_links"] == 2
    assert result["by_mode"]["geometry_only"]["incorrect_links"] == 6
    rendered = str(result)
    assert "alpha" not in rendered
    assert "beta" not in rendered
    assert "gamma" not in rendered
    assert "labeled_poses" not in rendered
    assert "landmarks" not in rendered
    assert "person_id" not in result
    assert "model_confidence" not in result
    assert result["no_meta_api_call"] is True
    assert "camera_image" not in rendered


def _valid_pose(x=.3):
    return {
        11: (x-.05, .20, .99),
        12: (x+.05, .20, .99),
        23: (x-.05, .42, .99),
        24: (x+.05, .42, .99),
        25: (x-.05, .62, .99),
        26: (x+.05, .62, .99),
        27: (x-.05, .85, .99),
        28: (x+.05, .85, .99),
    }


def test_invalid_pose_revokes_previous_continuity_before_next_frame():
    model = AnonymousTrackletResearch()
    a = model.process(ResearchDetections("fiction", 0, (_valid_pose(),)))
    assert a.new_anonymous_tracklets == 1
    bad = _valid_pose()
    bad[25] = ("corrupt", .62, .99)
    with pytest.raises(ValueError):
        model.process(ResearchDetections("fiction", 100, (bad,)))
    assert model._last_pairs == ()
    step = model.process(ResearchDetections("fiction", 200, (_valid_pose(.32),)))
    assert step.new_anonymous_tracklets == 1
    assert step.linked_anonymous_pairs == 0
    assert model.aggregate()["adjacent_geometric_links"] == 0


@pytest.mark.parametrize("invalid", [
    ResearchDetections("other", 100, (_valid_pose(),)),
    ResearchDetections("fiction", 0, (_valid_pose(),)),
    ResearchDetections("fiction", 100, (_valid_pose(),) * 9),
])
def test_rejected_source_timestamp_or_capacity_revokes_old_state(invalid):
    model = AnonymousTrackletResearch()
    model.process(ResearchDetections("fiction", 0, (_valid_pose(),)))
    with pytest.raises(ValueError):
        model.process(invalid)
    assert model._last_pairs == ()
    step = model.process(ResearchDetections("fiction", 200, (_valid_pose(.31),)))
    assert step.new_anonymous_tracklets == 1
    assert step.linked_anonymous_pairs == 0


def test_first_untrusted_frame_does_not_latch_research_source():
    model = AnonymousTrackletResearch()
    bad = _valid_pose()
    bad[27] = (.27, .85, float("nan"))
    with pytest.raises(ValueError):
        model.process(ResearchDetections("damaged", 0, (bad,)))
    assert model._source is None
    valid = model.process(ResearchDetections("fiction", 100, (_valid_pose(),)))
    assert valid.new_anonymous_tracklets == 1
    assert model._source == "fiction"
    assert model.aggregate()["frames_observed"] == 1
    assert asdict(valid)["human_identity_verified"] is False
