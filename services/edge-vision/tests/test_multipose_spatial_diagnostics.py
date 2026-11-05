"""Synthetic geometric multi-pose counters only; no human data/video."""
from types import SimpleNamespace as N

import pytest

from sentinel_edge.assist_external import (
    _evaluate_one, aggregate_multipose_spatial,
)
from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.multipose_spatial_diagnostics import (
    MULTIPOSE_CATEGORIES, multipose_spatial_category,
)
from sentinel_edge.pose_rejection_diagnostics import pose_adapter_reason


def pose(*, x=0.5, y=0.25, vis=.98):
    points = [N(x=x, y=y, visibility=vis, presence=.98) for _ in range(33)]
    for i in (23, 24):
        points[i] = N(x=x, y=y + .35, visibility=vis, presence=.98)
    return points


@pytest.mark.parametrize(("result", "expected"), [
    (N(pose_landmarks=[]), "not_multiple"),
    (N(pose_landmarks=[pose()]), "not_multiple"),
    (N(pose_landmarks=None), "not_multiple"),
    (N(pose_landmarks=[pose(), pose(x=.505, y=.253)]),
     "overlapping_torso_geometry"),
    (N(pose_landmarks=[pose(x=.25), pose(x=.75)]),
     "spatially_separated_geometry"),
    (N(pose_landmarks=[pose(x=.35), pose(x=.5)]),
     "ambiguous_geometry"),
    (N(pose_landmarks=[pose(), pose(vis=.1)]), "unusable_torso_geometry"),
    (N(pose_landmarks=[pose(), pose(x=1.3)]), "unusable_torso_geometry"),
    (N(pose_landmarks=[pose(), pose(), pose()]), "unsupported_pose_count"),
])
def test_spatial_taxonomy_cannot_override_multi_person_gate(result, expected):
    assert multipose_spatial_category(result) == expected
    assert expected in MULTIPOSE_CATEGORIES
    if expected != "not_multiple":
        assert pose_adapter_reason(result) == "multiple_people"


@pytest.mark.parametrize("invalid", [float("nan"), -1, 1.01])
def test_invalid_quality_rejected(invalid):
    with pytest.raises(ValueError, match="min_confidence"):
        multipose_spatial_category(N(pose_landmarks=[]), min_confidence=invalid)


class _FrozenResearchModel:
    threshold = .53

    def predict_probability(self, features):
        return .2


def _fictional_stream(path, *, clip_id, model, max_frames, frame_consumer,
                      event_consumer, pose_reason_consumer=None,
                      multipose_category_consumer=None, corrupt=False):
    assert path.name == "fake.mp4"
    assert model.name == "fake.task"
    for i in range(31):
        multiple = i % 3 == 0
        raw = N(pose_landmarks=[pose(), pose(x=.502)] if multiple else [pose()])
        geometry = multipose_spatial_category(raw)
        reason = pose_adapter_reason(raw)
        if multiple:
            points = {}
        else:
            points = {
                11: Landmark(.46, .25, .98), 12: Landmark(.54, .25, .98),
                23: Landmark(.46, .60, .98), 24: Landmark(.54, .60, .98),
            }
        if pose_reason_consumer:
            pose_reason_consumer(reason)
        if multipose_category_consumer:
            multipose_category_consumer(
                "ambiguous_geometry" if corrupt and multiple else geometry
            )
        frame_consumer(PoseFrame(timestamp_ms=i * 100, source_id=clip_id,
                                 landmarks=points))
    return [], {"frames_processed": 31, "invalid_pose_frames": 11,
                "candidate_events": 0}


def _one(tmp_path, collector=_fictional_stream, spatial_audit=True):
    return _evaluate_one(
        tmp_path / "fake.mp4", "fall", "fictional", 3000,
        tmp_path / "fake.task", _FrozenResearchModel(),
        collector=collector, diagnostics=True, detailed_reasons=True,
        spatial_audit=spatial_audit,
    )


def test_spatial_stream_is_bounded_and_matches_rejections(tmp_path):
    row = _one(tmp_path)
    assert row["pose_rejection_reasons"]["multiple_people"] == 11
    groups = row["multipose_spatial_categories"]
    assert groups["overlapping_torso_geometry"] == 11
    assert groups["not_multiple"] == 20
    agg = aggregate_multipose_spatial([row], "fall")
    assert agg["decoded_frames"] == 31
    assert agg["multi_pose_frames"] == 11
    assert agg["no_person_identity_or_duplicate_proven"]
    assert "landmarks" not in str(agg)
    assert "coordinates" not in str(agg)


def test_normal_mode_keeps_spatial_observer_off(tmp_path):
    row = _one(tmp_path, spatial_audit=False)
    assert "multipose_spatial_categories" not in row
    assert "pose_rejection_reasons" in row


def test_spatial_audit_requires_rejection_reason_audit(tmp_path):
    with pytest.raises(ValueError, match="requires detailed"):
        _evaluate_one(
            tmp_path / "fake.mp4", "fall", "fictional", 3000,
            tmp_path / "fake.task", _FrozenResearchModel(),
            collector=_fictional_stream, spatial_audit=True,
        )


def test_missing_spatial_categories_fail_closed(tmp_path):
    row = _one(tmp_path, spatial_audit=False)
    with pytest.raises(ValueError, match="Missing"):
        aggregate_multipose_spatial([row], "fall")


def test_spatial_category_inconsistency_fail_closed(tmp_path):
    row = _one(tmp_path)
    row["multipose_spatial_categories"]["overlapping_torso_geometry"] -= 1
    with pytest.raises(ValueError, match="inconsistent"):
        aggregate_multipose_spatial([row], "fall")
