"""Synthetic-only, deterministic identity-switch falsification tests.

All actor names are invented and benchmark-local; this module never
downloads videos, handles face imagery, writes person pose traces,
or accesses the Meta provider.
"""
from dataclasses import asdict

import pytest

from app.anonymous_tracklet_research import (
    AnonymousTrackletResearch,
    ResearchDetections,
    TrackletPolicy,
)
from app.synthetic_tracklet_benchmark import (
    FictionalCase,
    FictionalFrame,
    _skeleton,
    benchmark_frozen_cases,
    benchmark_one,
    frozen_fictional_cases,
)


def _one(key):
    return next(case for case in frozen_fictional_cases() if case.key == key)


def test_frozen_eight_scenarios_include_actual_identity_swap_counterexample():
    cases = frozen_fictional_cases()
    assert len(cases) == len({case.key for case in cases}) == 8
    assert len(_one("indistinguishable_spatial_swap").frames) == 12
    assert TrackletPolicy().multi_person_mode == "abstain"
    assert all(len(case.frames) >= 4 for case in cases)


def test_default_safe_mode_never_emits_multi_person_identity_like_links():
    policy = TrackletPolicy()
    assert policy.multi_person_mode == "abstain"
    tracker = AnonymousTrackletResearch()
    poses = (_skeleton(.38), _skeleton(.62))
    assert tracker.process(ResearchDetections("fiction", 0, poses)).status == (
        "ambiguous_people_abstain"
    )
    assert tracker.process(ResearchDetections("fiction", 100, poses)).status == (
        "ambiguous_people_abstain"
    )
    assert tracker._last_pairs == ()
    assert tracker.aggregate()["adjacent_geometric_links"] == 0
    assert tracker.aggregate()["real_person_identity_verified"] is False


def test_legacy_geometry_mode_can_silently_swap_two_fictional_actors():
    case = _one("indistinguishable_spatial_swap")
    unsafe = benchmark_one(case, mode="geometry_only")
    safe = benchmark_one(case, mode="abstain")
    assert unsafe["incorrect_anonymous_adjacent_links"] == 2
    assert unsafe["correct_anonymous_adjacent_links"] == 20
    assert unsafe["conservative_frame_abstentions"] == 0
    assert safe["incorrect_anonymous_adjacent_links"] == 0
    assert safe["correct_anonymous_adjacent_links"] == 0
    assert safe["conservative_frame_abstentions"] == 12


def test_default_safe_mode_keeps_unambiguous_single_person_local_geometry():
    case = _one("one_smooth_subject")
    safe = benchmark_one(case, mode="abstain")
    legacy = benchmark_one(case, mode="geometry_only")
    assert safe["correct_anonymous_adjacent_links"] == 19
    assert safe["incorrect_anonymous_adjacent_links"] == 0
    assert safe["reference_appearances_not_linked"] == 0
    assert safe["correct_anonymous_adjacent_links"] == (
        legacy["correct_anonymous_adjacent_links"]
    )


def test_two_people_detector_output_order_changes_are_not_actor_ids():
    case = _one("two_separated_reordered")
    legacy = benchmark_one(case, mode="geometry_only")
    safe = benchmark_one(case, mode="abstain")
    assert legacy["correct_anonymous_adjacent_links"] == 34
    assert legacy["incorrect_anonymous_adjacent_links"] == 0
    assert safe["correct_anonymous_adjacent_links"] == 0
    assert safe["reference_appearances_not_linked"] == 34
    assert safe["conservative_frame_abstentions"] == 18


def test_real_person_tracking_accuracy_is_explicitly_not_measured():
    report = benchmark_frozen_cases()
    assert report["status"] == "FICTIONAL_ASSOCIATION_BENCHMARK_COMPLETE"
    assert report["default_mode"] == "abstain"
    assert report["frozen_fictional_scenes"] == 8
    assert len(report["cases"]) == 16
    assert report["synthetic_only_no_human_media"] is True
    assert report["real_multi_person_tracking_accuracy_measured"] is False
    assert report["recommended_multi_person_release"] == "NO_GO"
    assert report["raw_pose_coordinates_exported"] is False
    assert report["identity_labels_exported"] is False
    assert report["meta_api_called"] is False
    assert report["automatic_alert_enabled"] is False
    assert report["aggregate_by_mode"]["abstain"]["incorrect_links"] == 0
    assert report["aggregate_by_mode"]["geometry_only"]["incorrect_links"] == 2
    assert report["aggregate_by_mode"]["abstain"]["correct_links"] == 59
    assert report["aggregate_by_mode"]["geometry_only"]["correct_links"] == 141
    assert report["aggregate_by_mode"]["abstain"]["reference_transitions"] == 161
    assert report["aggregate_by_mode"]["geometry_only"]["reference_transitions"] == 161
    assert all(row["ground_truth_fictional_only"] for row in report["cases"])
    assert all(row["real_person_identity_verified"] is False for row in report["cases"])
    assert all(row["trained_or_calibrated_model"] is False for row in report["cases"])
    assert all(row["alert_permitted"] is False for row in report["cases"])


def test_fictional_ground_truth_reference_denominator_includes_abstained_frames():
    case = _one("lower_leg_occlusion")
    report = benchmark_one(case, mode="abstain")
    assert report["reference_adjacent_actor_appearances"] == 17
    assert report["correct_anonymous_adjacent_links"] == 15
    assert report["reference_appearances_not_linked"] == 2
    assert report["conservative_frame_abstentions"] == 1
    assert report["incorrect_anonymous_adjacent_links"] == 0


def test_missing_person_and_camera_gap_never_get_reidentified():
    absent = benchmark_one(
        _one("brief_disappearance_reappearance"), mode="abstain",
    )
    gap = benchmark_one(_one("camera_timestamp_gap"), mode="abstain")
    assert absent["correct_anonymous_adjacent_links"] == 15
    assert absent["incorrect_anonymous_adjacent_links"] == 0
    assert absent["conservative_frame_abstentions"] == 1
    assert gap["reference_appearances_not_linked"] == 1
    assert gap["conservative_frame_abstentions"] == 1


def test_reject_duplicate_fictional_actor_identifiers_in_one_frame():
    case = FictionalCase(
        "dup",
        (FictionalFrame(0, (
            ("fiction", _skeleton(.2)),
            ("fiction", _skeleton(.8)),
        )),),
        "duplicate",
    )
    with pytest.raises(ValueError, match="Duplicate fictional actor"):
        benchmark_one(case, mode="abstain")


def test_forbidden_policy_and_empty_benchmark_are_rejected():
    with pytest.raises(ValueError, match="Unknown benchmark"):
        benchmark_one(_one("one_smooth_subject"), mode="unsafe_fiction")
    with pytest.raises(ValueError, match="bounded"):
        benchmark_one(FictionalCase("empty", (), "empty"), mode="abstain")


def test_aggregate_does_not_contain_raw_geometry_or_fictional_names():
    output = benchmark_frozen_cases()
    # Allowed metadata only, never actor IDs used for reference matching.
    assert "labeled_poses" not in str(output)
    assert "alpha" not in str(output)
    assert "beta" not in str(output)
    assert "hip_center" not in str(output)
    assert "points" not in output
    assert "person_id" not in output
    for row in output["cases"]:
        assert "labeled_poses" not in str(row)
        assert "actor_names_or_pose_coordinates_exported" in row
        assert row["actor_names_or_pose_coordinates_exported"] is False


def test_tracklet_step_has_no_persistent_track_identifiers():
    tracker = AnonymousTrackletResearch()
    a = _skeleton(.4)
    step_a = tracker.process(ResearchDetections("scene", 0, (a,)))
    step_b = tracker.process(ResearchDetections("scene", 100, (a,)))
    assert step_b.linked_anonymous_pairs == 1
    assert tracker._last_pairs == ((0, 0),)
    record = asdict(step_a)
    assert "track_id" not in record
    assert "person_id" not in record
    assert "coordinates" not in record
    assert record["human_identity_verified"] is False
