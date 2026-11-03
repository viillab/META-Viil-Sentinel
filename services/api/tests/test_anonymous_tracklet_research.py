"""Synthetic-only research tests: anonymous association, not person IDs.

No actual human media, face descriptors, embeddings, real identities, Meta,
camera access, notifications, or private pose traces are used in CI.
"""
from dataclasses import asdict
from math import nan

import pytest

from app import anonymous_tracklet_research as associate


def person(x=.5, y=.48, *, visible=.99, xscale=1.0):
    """Original synthetic eight-joint silhouette anchored at pelvis x,y."""
    return {
        11: (x-.07*xscale, y-.22, visible),
        12: (x+.07*xscale, y-.22, visible),
        23: (x-.06*xscale, y, visible),
        24: (x+.06*xscale, y, visible),
        25: (x-.06*xscale, y+.22, visible),
        26: (x+.06*xscale, y+.22, visible),
        27: (x-.06*xscale, y+.42, visible),
        28: (x+.06*xscale, y+.42, visible),
    }


def frame(ts, *poses, source="fiction"):
    return associate.ResearchDetections(source, ts, tuple(poses))


def run(*records, policy=None):
    model = associate.AnonymousTrackletResearch(policy)
    values = [model.process(record) for record in records]
    return values, model.aggregate()


def test_stable_single_person_tracklet_never_becomes_a_verified_identity():
    values, result = run(
        *[frame(i*100, person(x=.3+i*.01)) for i in range(30)]
    )
    assert values[0].status == "new_anonymous_tracklets"
    assert all(x.status == "anonymous_geometry_linked" for x in values[1:])
    assert result["frames_observed"] == 30
    assert result["adjacent_geometric_links"] == 29
    assert result["ephemeral_tracklets_started"] == 1
    assert result["longest_contiguous_tracklet_frames"] == 30
    assert result["real_person_identity_verified"] is False
    assert result["reidentified_across_occlusion"] is False
    assert result["automatic_fall_detection"] is False
    assert result["automated_alert_permitted"] is False
    assert result["meta_api_called"] is False
    assert all(x.human_identity_verified is False for x in values)
    assert all(x.occlusion_interpolated is False for x in values)
    assert "track_id" not in result and "landmarks" not in str(result)


def test_two_people_well_separated_use_unique_local_geometry_not_reidentification():
    inputs = [frame(i*100, person(x=.19+i*.01), person(x=.81-i*.01))
              for i in range(12)]
    results, summary = run(
        *inputs,
        policy=associate.TrackletPolicy(multi_person_mode="geometry_only"),
    )
    assert results[0].new_anonymous_tracklets == 2
    assert all(x.linked_anonymous_pairs == 2 for x in results[1:])
    assert summary["max_poses_seen_in_one_frame"] == 2
    assert summary["adjacent_geometric_links"] == 22
    assert summary["ephemeral_tracklets_started"] == 2
    assert summary["multi_person_ambiguous_frames_abstained"] == 0


def test_crossing_close_people_forces_abstention_then_new_tracklets():
    values, summary = run(
        frame(0, person(.35), person(.65)),
        frame(100, person(.47), person(.53)),  # overlap: no trusted pairing
        frame(200, person(.28), person(.72)),
        frame(300, person(.27), person(.73)),
        policy=associate.TrackletPolicy(multi_person_mode="geometry_only"),
    )
    assert [v.status for v in values] == [
        "new_anonymous_tracklets", "ambiguous_people_abstain",
        "new_anonymous_tracklets", "anonymous_geometry_linked",
    ]
    assert values[1].active_anonymous_tracklets == 0
    assert summary["multi_person_ambiguous_frames_abstained"] == 1
    assert summary["ephemeral_tracklets_started"] == 4
    assert summary["adjacent_geometric_links"] == 2
    assert summary["reidentified_across_occlusion"] is False


def test_one_old_center_compatible_with_two_new_centers_is_ambiguous():
    values, summary = run(
        frame(0, person(.5)),
        frame(100, person(.40), person(.60)),  # separated but both near old
        frame(200, person(.25), person(.75)),
        policy=associate.TrackletPolicy(multi_person_mode="geometry_only"),
    )
    assert values[1].status == "ambiguous_people_abstain"
    assert summary["multi_person_ambiguous_frames_abstained"] == 1
    assert summary["adjacent_geometric_links"] == 0


def test_missed_frame_reappearance_is_new_tracklet_not_recovered_identity():
    values, report = run(
        frame(0, person(.5)),
        frame(100, person(.52)),
        frame(200),  # no person / occlusion
        frame(300, person(.53)),
        frame(400, person(.55)),
    )
    assert [x.linked_anonymous_pairs for x in values] == [0, 1, 0, 0, 1]
    assert report["no_pose_frames_abstained"] == 1
    assert report["ephemeral_tracklets_started"] == 2
    assert report["longest_contiguous_tracklet_frames"] == 2
    assert report["reidentified_across_occlusion"] is False


def test_one_partial_pose_abstains_entire_crowded_scene():
    damaged = person(.75)
    damaged[28] = (.75, .9, .12)
    values, summary = run(
        frame(0, person(.25), person(.75)),
        frame(100, person(.25), damaged),
        frame(200, person(.25), person(.75)),
        policy=associate.TrackletPolicy(multi_person_mode="geometry_only"),
    )
    assert values[1].status == "low_visibility_abstain"
    assert values[1].active_anonymous_tracklets == 0
    assert values[2].new_anonymous_tracklets == 2
    assert summary["incomplete_eight_joint_frames_abstained"] == 1
    assert summary["adjacent_geometric_links"] == 0


def test_long_timestamp_discontinuity_resets_but_does_not_relink():
    values, summary = run(
        frame(0, person()),
        frame(100, person(.52)),
        frame(1200, person(.52)),
        frame(1300, person(.53)),
    )
    assert values[2].status == "temporal_gap_reset"
    assert values[2].linked_anonymous_pairs == 0
    assert values[2].new_anonymous_tracklets == 1
    assert summary["timestamp_discontinuity_resets"] == 1
    assert summary["adjacent_geometric_links"] == 2


def test_one_millisecond_jump_is_not_paired_despite_small_displacement():
    values, stats = run(
        frame(0, person(.3)),
        frame(1, person(.34)),  # .04 in 1 ms => 40 image-units/s
        frame(101, person(.35)),
    )
    assert [x.linked_anonymous_pairs for x in values] == [0, 0, 1]
    assert stats["ephemeral_tracklets_started"] == 2


def test_far_person_jump_creates_new_anonymous_tracklet():
    values, report = run(
        frame(0, person(.15)),
        frame(100, person(.75)),
        frame(200, person(.76)),
    )
    assert [x.linked_anonymous_pairs for x in values] == [0, 0, 1]
    assert report["ephemeral_tracklets_started"] == 2


@pytest.mark.parametrize("records", [
    (frame(0, person()), frame(0, person())),
    (frame(100, person()), frame(99, person())),
    (frame(0, person(), source="alpha"), frame(100, person(), source="beta")),
])
def test_replayed_time_or_cross_camera_association_rejected(records):
    tracker = associate.AnonymousTrackletResearch()
    tracker.process(records[0])
    with pytest.raises(ValueError):
        tracker.process(records[1])


@pytest.mark.parametrize("bad", [
    frame(0, {999: (.1, .2, .99)}),
    frame(0, {23: (.5, nan, .99)}),
    frame(0, {23: (.5, .5, 2)}),
    frame(0, {23: (True, .5, .99)}),
    frame(0, {23: [.5, .5, .99]}),
    frame(0, {23: (9999, .5, .99)}),
    associate.ResearchDetections("fiction", 0, [person()]),
    associate.ResearchDetections("", 0, (person(),)),
    associate.ResearchDetections("fiction", True, (person(),)),
    associate.ResearchDetections("fiction", 0, tuple(person() for _ in range(9))),
])
def test_invalid_pose_source_or_capacity_is_rejected(bad):
    with pytest.raises(ValueError):
        associate.AnonymousTrackletResearch().process(bad)


@pytest.mark.parametrize("options", [
    {"max_poses_per_frame": 0},
    {"multi_person_mode": "wrong"},
    {"max_poses_per_frame": True},
    {"max_poses_per_frame": 9},
    {"max_frames": 30_000},
    {"min_visibility": nan},
    {"min_visibility": 2},
    {"max_center_displacement": -1},
    {"max_center_speed_normalized_per_second": 0},
    {"max_center_speed_normalized_per_second": float("inf")},
    {"ambiguity_proximity": 0},
    {"max_frame_gap_ms": 0},
    {"min_torso_length": -1},
    {"max_torso_length_ratio": 0},
])
def test_tracklet_policy_invalid_settings_fail_closed(options):
    with pytest.raises(ValueError):
        associate.TrackletPolicy(**options)


def test_bounds_fail_closed_and_empty_aggregate_is_unavailable():
    tracker = associate.AnonymousTrackletResearch(
        associate.TrackletPolicy(max_frames=2),
    )
    with pytest.raises(ValueError, match="empty"):
        tracker.aggregate()
    tracker.process(frame(0, person()))
    tracker.process(frame(100, person()))
    with pytest.raises(ValueError, match="Unbounded"):
        tracker.process(frame(200, person()))


def test_anonymous_output_omits_person_pose_and_identity_keys():
    vals, data = run(frame(0, person()), frame(100, person()))
    for sample in [data, asdict(vals[1])]:
        serialized = str(sample).lower()
        assert "raw_" not in serialized or "raw_coordinates_exported" in serialized or "raw_person_coordinates_exported" in serialized
        assert "landmarks" not in serialized
        assert "pose_landmarks" not in serialized
        assert "person_id" not in sample
        assert "identity_verified': true" not in serialized
    assert vals[1].confirmed_fall is False
    assert vals[1].confirmed_no_fall is False
    assert vals[1].alert_permitted is False
    assert vals[1].meta_upload_permitted is False


def test_single_pose_replay_fail_closed_on_missing_private_trace(tmp_path, monkeypatch):
    from app import anonymous_tracklet_report as runner
    from app.multi_joint_research import SELECTION

    monkeypatch.setattr(runner, "OUTPUT", tmp_path)
    monkeypatch.setattr(runner, "_private_root", lambda x: x)
    monkeypatch.setattr(runner, "evaluate_frozen_five", lambda: {
        "clips": [{"clip_id": c, "frames": 40, "adjacent_intervals": 39}
                  for c, _ in SELECTION],
    })
    monkeypatch.setattr(runner, "_read_private_trace",
                        lambda _: iter([]))  # must not be called
    with pytest.raises(ValueError, match="private research trace"):
        runner.evaluate_known_single_pose_continuity()
