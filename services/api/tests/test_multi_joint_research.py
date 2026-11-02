"""Research-only 8-joint privacy, geometry, and fail-closed trace tests.

Every fixture is fictional numerical geometry; no real videos are loaded
from Git or from the private licensed dataset by this test module.
"""
import json
from math import nan

import pytest

probe = pytest.importorskip("app.multi_joint_research")


def fictional_points():
    # 8 joint landmarks; in 2D, a straight knee is near 180 degrees.
    return {
        11: (0.43, 0.20, .99),
        12: (0.57, 0.20, .99),
        23: (0.44, 0.42, .99),
        24: (0.56, 0.42, .99),
        25: (0.44, 0.64, .99),
        26: (0.56, 0.64, .99),
        27: (0.44, 0.86, .99),
        28: (0.56, 0.86, .99),
    }


def write_private_fixture(path, n=3, fn=None):
    with path.open("x", encoding="utf-8") as stream:
        for i in range(n):
            points = fictional_points() if fn is None else fn(i)
            stream.write(probe._fixed_record(i * 100, points) + "\n")


def test_strict_auditable_five_source_selection_and_eight_landmarks():
    assert len(probe.SELECTION) == 5
    assert len({cid for cid, _ in probe.SELECTION}) == 5
    assert sum(cat == "adl_no_fall" for _, cat in probe.SELECTION) == 2
    assert set(probe.POINTS) == {11, 12, 23, 24, 25, 26, 27, 28}
    assert probe.OUTPUT.is_relative_to(probe.ROOT / "data" / "private")
    assert not hasattr(probe, "meta_client")
    assert probe.SCHEMA == "viil.research.eight_joint_pose.v1"


def test_knee_angles_are_geometric_not_diagnostic():
    straight = fictional_points()
    for side in ("left", "right"):
        assert probe._knee_angle(straight, side=side) == pytest.approx(180)
    flexed = fictional_points()
    flexed[27] = (.66, .64, .99)
    assert probe._knee_angle(flexed, side="left") == pytest.approx(90)
    assert probe._knee_angle(flexed, side="right") == pytest.approx(180)


def test_low_visibility_or_missing_ankle_abstains_from_knee_geometry():
    points = fictional_points()
    points[27] = (.44, .86, .3)
    assert probe._knee_angle(points, side="left") is None
    assert probe._knee_angle(points, side="right") is not None
    del points[28]
    assert probe._knee_angle(points, side="right") is None


def test_exact_frame_count_rejects_incomplete_derived_pose(tmp_path):
    path = tmp_path / "FICT.eight.pose.jsonl"
    write_private_fixture(path, 3)
    report = probe.aggregate_trace(path, clip_id="FD0012", expected_frames=3)
    assert report["frames"] == 3
    assert report["all_8_joints_visible_frames"] == 3
    assert report["both_knees_geometry_valid_frames"] == 3
    assert report["all_8_joint_coverage"] == 1
    assert report["lower_body_evidence_state"] == "exploratory_joint_geometry_available"
    assert report["knee_angle_min_deg"] == 180
    assert report["knee_angle_max_deg"] == 180
    assert report["fall_confirmed"] is False
    assert report["alert_permitted"] is False
    assert report["raw_pose_coordinates_exported"] is False
    assert "points" not in report
    with pytest.raises(ValueError, match="missing or extra"):
        probe.aggregate_trace(path, clip_id="FD0012", expected_frames=4)


def test_absent_lower_limbs_produce_coverage_not_incident(tmp_path):
    path = tmp_path / "FICT.eight.pose.jsonl"
    write_private_fixture(path, 6, fn=lambda _: {
        k: v for k, v in fictional_points().items() if k in (11, 12, 23, 24)
    })
    report = probe.aggregate_trace(path, clip_id="FD0032", expected_frames=6)
    assert report["torso_4point_visible_frames"] == 6
    assert report["all_8_joints_visible_frames"] == 0
    assert report["both_knees_geometry_valid_frames"] == 0
    assert report["both_knees_geometry_coverage"] == 0
    assert report["lower_body_evidence_state"] == "abstain_incomplete_lower_body_visibility"
    assert report["knee_angle_min_deg"] is None
    assert report["knee_angle_max_deg"] is None


@pytest.mark.parametrize("points", [
    {999: (.5, .5, .99)},
    {25: (.4, .6, nan)},
    {25: (.4, .6, -0.1)},
    {25: (.4, .6, 2.0)},
    {25: ("NaN", .6, .7)},
    {25: (.4, .6, True)},
])
def test_unapproved_joint_or_nonfinite_point_does_not_serialize(points):
    with pytest.raises(ValueError):
        probe._fixed_record(0, points)


@pytest.mark.parametrize("content", [
    '{"schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{"999":{}}}\n',
    '{"schema":"wrong","timestamp_ms":0,"points":{}}\n',
    '{"schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{},"bonus":true}\n',
    '{"schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{"25":{"x":NaN,"y":1,"visibility":1}}}\n',
    '{"schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{"25":{"x":0.4,"y":1,"visibility":2}}}\n',
    'not-json\n',
    '{"schema":"viil.research.eight_joint_pose.v1","schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{}}\n',
    '{"schema":"viil.research.eight_joint_pose.v1","timestamp_ms":0,"points":{"25":{"x":0.2,"x":0.3,"y":0.2,"visibility":1}}}\n',
])
def test_reader_rejects_invalid_or_unbounded_raw_pose(content, tmp_path):
    path = tmp_path / "fake.eight.pose.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        list(probe._read_private_trace(path))


def test_replayed_timestamp_and_incomplete_stream_denied(tmp_path):
    path = tmp_path / "fake.eight.pose.jsonl"
    raw = probe._fixed_record(0, fictional_points())
    path.write_text(raw + "\n" + raw + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timestamps"):
        list(probe._read_private_trace(path))
    with pytest.raises(ValueError, match="Unknown"):
        probe.aggregate_trace(path, clip_id="untrusted", expected_frames=2)
    with pytest.raises(ValueError, match="Unknown"):
        probe.aggregate_trace(path, clip_id="FD0012", expected_frames=0)


def test_no_video_or_secret_persisted_in_aggregate(tmp_path):
    path = tmp_path / "FICT.eight.pose.jsonl"
    write_private_fixture(path, 3)
    report = probe.aggregate_trace(path, clip_id="FD0011", expected_frames=3)
    serialized = json.dumps(report)
    assert "landmarks" not in serialized
    assert "pose.jsonl" not in serialized
    assert "authorization" not in serialized
    assert "token" not in serialized
    assert "x" not in report and "y" not in report


def test_private_trace_symlink_is_refused(tmp_path):
    real = tmp_path / "target.eight.pose.jsonl"
    write_private_fixture(real)
    alias = tmp_path / "alias.eight.pose.jsonl"
    try:
        alias.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not permitted on this Windows setup")
    with pytest.raises(ValueError, match="symlinked"):
        list(probe._read_private_trace(alias))
