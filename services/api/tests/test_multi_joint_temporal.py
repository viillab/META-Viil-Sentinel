"""Synthetic-only tests for eight-joint temporal movement observability.

These cases contain original imaginary numeric joints, not actual human
video, so CI makes no media/network/provider calls.
"""
from dataclasses import asdict
from math import nan

import pytest

module = pytest.importorskip("app.multi_joint_temporal")
eight = pytest.importorskip("app.multi_joint_research")
report = pytest.importorskip("app.multi_joint_temporal_report")


def skeleton(hip_y=.42, ankle_y=.86, x_offset=0.0, confidence=.99):
    # A straight imaginary joint chain with normalized coordinates.
    return {
        11: (.43+x_offset, .20, confidence),
        12: (.57+x_offset, .20, confidence),
        23: (.44+x_offset, hip_y, confidence),
        24: (.56+x_offset, hip_y, confidence),
        25: (.44+x_offset, (hip_y+ankle_y)/2, confidence),
        26: (.56+x_offset, (hip_y+ankle_y)/2, confidence),
        27: (.44+x_offset, ankle_y, confidence),
        28: (.56+x_offset, ankle_y, confidence),
    }


def frames(n=40, *, every_ms=100):
    return [(i*every_ms, skeleton()) for i in range(n)]


def test_constant_fictional_pose_has_zero_motion_and_only_research_status():
    result = module.assess_temporal_observability(frames(), clip_id="fiction")
    assert result.frames == 40
    assert result.adjacent_intervals == 39
    assert result.eligible_temporal_pairs == 39
    assert result.all_joint_visible_frames == 40
    assert result.temporal_pair_fraction == 1
    assert result.all_joint_coverage == 1
    assert result.hip_center_speed_p95_normalized_per_second == 0
    assert result.ankle_center_speed_p95_normalized_per_second == 0
    assert result.knee_angle_rate_p95_deg_per_second == 0
    assert result.state == "exploratory_temporal_geometry_available"
    assert result.person_identity_verified is False
    assert result.calibrated_fall_probability is False
    assert result.confirms_fall is False
    assert result.confirms_no_fall is False
    assert result.alert_permitted is False
    assert result.meta_upload_permitted is False
    assert result.raw_pose_coordinates_exported is False
    for forbidden in ("points", "landmarks", "video", "person_id"):
        assert forbidden not in asdict(result)


def test_fixed_known_normalized_hip_velocity_not_physical_speed():
    data = [(i*100, skeleton(hip_y=.42+i*.01)) for i in range(40)]
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.hip_center_speed_p95_normalized_per_second == pytest.approx(.1)
    # Fixed ankles in image space, moving hip/knee; no cross-person inference.
    assert result.ankle_center_speed_p95_normalized_per_second == 0
    assert result.state == "exploratory_temporal_geometry_available"


def test_single_occlusion_discards_both_neighbor_pairs_and_speed_spike():
    data = frames()
    data[20] = (2000, {})
    data[21] = (2100, skeleton(x_offset=.4))
    data[22] = (2200, skeleton(x_offset=.4))
    # Big false jump occurs exactly across the missing frame.
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.all_joint_visible_frames == 39
    assert result.eligible_temporal_pairs == 37
    assert result.longest_unusable_run_frames == 1
    assert result.hip_center_speed_p95_normalized_per_second == 0
    assert result.ankle_center_speed_p95_normalized_per_second == 0
    assert "occluded_joint_intervals_excluded" in result.reason_codes


def test_40_frame_hole_forces_lower_body_abstention_and_keeps_replay_bounded():
    data = frames(100)
    for i in range(30, 70):
        data[i] = (i*100, {})
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.all_joint_visible_frames == 60
    assert result.longest_unusable_run_frames == 40
    assert result.eligible_temporal_pairs == 58
    assert result.state == "abstain_missing_lower_body"
    assert result.confirms_no_fall is False


def test_extended_occlusion_abstains_despite_good_overall_visibility():
    # 84% all-eight-point coverage is misleading if the middle 16 frames
    # are entirely untracked. This is not continuous person observation.
    data = frames(100)
    for i in range(40, 56):
        data[i] = (i*100, {})
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.all_joint_coverage == .84
    assert result.temporal_pair_fraction > .5
    assert result.longest_unusable_run_frames == 16
    assert result.state == "abstain_temporal_discontinuity"
    assert "extended_lower_body_occlusion" in result.reason_codes
    assert result.alert_permitted is False


def test_temporal_gap_avoids_unphysical_velocity_from_discontinuous_capture():
    data = frames()
    data = [
        (ts + (1000 if idx >= 20 else 0), joints)
        for idx, (ts, joints) in enumerate(data)
    ]
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.discontinuity_intervals == 1
    assert result.largest_timestamp_gap_ms == 1100
    assert result.eligible_temporal_pairs == 38
    assert result.hip_center_speed_p95_normalized_per_second == 0
    assert "gapped_frame_intervals_excluded" in result.reason_codes
    assert result.person_identity_verified is False


def test_insufficient_temporal_pair_count_is_separate_from_pose_coverage():
    config = module.TemporalObservabilityPolicy(min_temporal_pairs=40)
    result = module.assess_temporal_observability(
        frames(), clip_id="fiction", policy=config,
    )
    assert result.all_joint_coverage == 1
    assert result.state == "abstain_temporal_discontinuity"
    assert "insufficient_contiguous_joint_pairs" in result.reason_codes


def test_low_visibility_resets_velocity_chain():
    data = frames()
    low = skeleton(confidence=.3)
    data[20] = (2000, low)
    result = module.assess_temporal_observability(data, clip_id="fiction")
    assert result.all_joint_visible_frames == 39
    assert result.eligible_temporal_pairs == 37
    assert "occluded_joint_intervals_excluded" in result.reason_codes


@pytest.mark.parametrize("bad", [
    [(0, skeleton()), (0, skeleton())],
    [(100, skeleton()), (50, skeleton())],
    [(0, {999: (.1, .2, .99)})],
    [(0, {25: (.1, nan, .99)})],
    [(0, {25: (.1, .2, 1.1)})],
    [(0, {25: (True, .2, .99)})],
    [(0, {25: [.1, .2, .99]})],
    [(True, skeleton())],
    [(0, "not-landmarks")],
    ["not-a-pose-record"],
])
def test_corrupted_or_mixed_input_fails_closed(bad):
    with pytest.raises(ValueError):
        module.assess_temporal_observability(bad, clip_id="fiction")


def test_empty_or_oversize_poses_rejected_before_any_report():
    with pytest.raises(ValueError, match="Empty"):
        module.assess_temporal_observability([], clip_id="fiction")
    with pytest.raises(ValueError, match="bounded"):
        module.assess_temporal_observability(
            frames(6), clip_id="fiction",
            policy=module.TemporalObservabilityPolicy(max_input_frames=5),
        )


@pytest.mark.parametrize("values", [
    {"min_joint_visibility": 0},
    {"min_all_joint_coverage": nan},
    {"min_all_joint_coverage": 2},
    {"min_temporal_pair_coverage": True},
    {"min_temporal_pairs": -1},
    {"max_pair_gap_ms": 0},
    {"max_input_frames": 1.5},
])
def test_policy_rejects_unsafe_gates(values):
    with pytest.raises(ValueError):
        module.TemporalObservabilityPolicy(**values)
    with pytest.raises(ValueError, match="Unsupported"):
        module.assess_temporal_observability(
            frames(), clip_id="fiction", policy=object(),
        )


def test_p95_nearest_rank_frozen_index():
    assert module._p95([]) is None
    assert module._p95([3]) == 3
    assert module._p95(list(range(1, 21))) == 19
    assert module._p95(list(range(1, 101))) == 95


def test_research_report_is_independent_of_real_video_and_meta(tmp_path, monkeypatch):
    filenames = [cid for cid, _ in eight.SELECTION]
    path = tmp_path / "private"
    path.mkdir()
    points = skeleton()
    for clip_id in filenames:
        target = path / f"{clip_id}.eight.pose.jsonl"
        with target.open("x", encoding="utf-8") as handle:
            for i in range(40):
                handle.write(eight._fixed_record(i*100, points) + "\n")
    monkeypatch.setattr(report, "OUTPUT", path)
    monkeypatch.setattr(report, "_private_root", lambda p: p)
    monkeypatch.setattr(report, "_input_sources", lambda: tuple(
        eight.Source(cid, path / f"{cid}.mp4", "adl_no_fall", 40)
        for cid in filenames
    ))
    monkeypatch.setattr(report, "analyze_private", lambda _: {
        "clips": [
            {
                "clip_id": cid, "frames": 40,
                "all_8_joints_visible_frames": 40,
            } for cid in filenames
        ],
    })
    result = report.evaluate_frozen_five()
    assert result["status"] == "FROZEN_EIGHT_JOINT_TEMPORAL_OBSERVABILITY_COMPLETE"
    assert result["clip_count"] == 5
    assert result["total_frames"] == 200
    assert result["eligible_temporal_pairs"] == 195
    assert result["no_event_detection_or_diagnosis"] is True
    assert result["single_pose_per_frame_identity_tracking"] is False
    assert result["human_video_or_raw_joint_coordinates_uploaded"] is False
    assert result["meta_api_called"] is False
    assert result["states"] == {"exploratory_temporal_geometry_available": 5}
    assert all(row["confirms_fall"] is False for row in result["clips"])


def test_report_rejects_corrupted_or_incomplete_trace(tmp_path, monkeypatch):
    path = tmp_path / "private"
    path.mkdir()
    monkeypatch.setattr(report, "OUTPUT", path)
    monkeypatch.setattr(report, "_private_root", lambda p: p)
    monkeypatch.setattr(report, "_input_sources", lambda: tuple(
        eight.Source(cid, path / f"{cid}.mp4", "adl_no_fall", 40)
        for cid, _ in eight.SELECTION
    ))
    monkeypatch.setattr(report, "analyze_private", lambda _: {
        "clips": [
            {"clip_id": cid, "frames": 40, "all_8_joints_visible_frames": 40}
            for cid, _ in eight.SELECTION
        ],
    })
    # No human pose is fabricated if source is absent.
    with pytest.raises(ValueError, match="absent private"):
        report.evaluate_frozen_five()
