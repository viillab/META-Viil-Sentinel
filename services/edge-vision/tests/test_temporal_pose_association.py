"""Strict RAM-only association potential: synthetic shapes, no real people."""
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.assist_external import (
    _evaluate_one, aggregate_temporal_association,
)
from sentinel_edge.contracts import PoseFrame
from sentinel_edge.multipose_spatial_diagnostics import multipose_spatial_category
from sentinel_edge.pose_adapter import extract_torso_landmarks
from sentinel_edge.pose_rejection_diagnostics import pose_adapter_reason
from sentinel_edge.temporal_pose_association import (
    ASSOCIATION_CATEGORIES, MAX_ANCHOR_GAP_FRAMES, OfflineAssociationObserver,
)


def torso_pose(x=.50, y=.25, visibility=.95, height=.3):
    points = [NS(x=x, y=y, visibility=visibility, presence=.95)
              for _ in range(33)]
    for i in (23, 24):
        points[i] = NS(x=x, y=y + height, visibility=visibility, presence=.95)
    return points


def result(*poses):
    return NS(pose_landmarks=list(poses))


def test_temporal_candidate_requires_unique_strict_single_frame_anchor():
    ob = OfflineAssociationObserver()
    frame = result(torso_pose(.5), torso_pose(.9))
    assert ob.observe(frame) == "multiple_anchor_stale_or_missing"
    assert ob.observe(result(torso_pose(.50))) == "single_anchor"
    assert ob.observe(result(torso_pose(.515), torso_pose(.90))) == (
        "multiple_short_anchor_unique_candidate"
    )
    # Does not assert same real person, and strict production adapter abstains.
    assert extract_torso_landmarks(frame) == {}
    assert pose_adapter_reason(frame) == "multiple_people"


def test_multiple_candidates_never_reanchor_or_extend_lifetime():
    ob = OfflineAssociationObserver()
    assert ob.observe(result(torso_pose(.5))) == "single_anchor"
    outcomes = [
        ob.observe(result(torso_pose(.5), torso_pose(.9)))
        for _ in range(MAX_ANCHOR_GAP_FRAMES + 2)
    ]
    assert outcomes[:MAX_ANCHOR_GAP_FRAMES] == [
        "multiple_short_anchor_unique_candidate"
    ] * MAX_ANCHOR_GAP_FRAMES
    assert outcomes[-2:] == ["multiple_anchor_stale_or_missing"] * 2


def test_unclear_and_unusable_shapes_fail_closed():
    ob = OfflineAssociationObserver()
    assert ob.observe(result(torso_pose(.5))) == "single_anchor"
    # two candidates equally near.
    assert ob.observe(result(torso_pose(.505), torso_pose(.515))) == (
        "multiple_short_anchor_ambiguous"
    )
    assert ob.observe(result(torso_pose(.9), torso_pose(.7))) == (
        "multiple_short_anchor_no_match"
    )
    assert ob.observe(result(torso_pose(.51), torso_pose(.9, visibility=.1))) == (
        "multiple_unusable_geometry"
    )
    assert ob.observe(result(torso_pose(.5), torso_pose(.7), torso_pose(.9))) == (
        "multiple_unsupported_count"
    )


def test_no_person_does_not_seed_or_invalidate_short_existing_anchor():
    ob = OfflineAssociationObserver()
    assert ob.observe(result(torso_pose(.5))) == "single_anchor"
    assert ob.observe(result()) == "no_single_pose"
    assert ob.observe(result(torso_pose(.51), torso_pose(.85))) == (
        "multiple_short_anchor_unique_candidate"
    )
    assert ob.observe(result(torso_pose(.5, visibility=.1))) == "single_unusable"
    assert ob.observe(result(torso_pose(.5), torso_pose(.85))) == (
        "multiple_anchor_stale_or_missing"
    )


def test_adaptor_accepted_but_geometry_too_short_stays_unanchored():
    ob = OfflineAssociationObserver()
    p = torso_pose(.5, height=.01)
    assert pose_adapter_reason(result(p)) == "accepted"
    assert ob.observe(result(p)) == "single_accepted_geometry_unusable"
    assert ob.observe(result(torso_pose(.5), torso_pose(.9))) == (
        "multiple_anchor_stale_or_missing"
    )


@pytest.mark.parametrize("bad", [-1, 1.01, float("nan")])
def test_bad_quality_gate_is_refused(bad):
    with pytest.raises(ValueError, match="Invalid"):
        OfflineAssociationObserver(min_confidence=bad)


def _fictional_stream(path, *, clip_id, model, max_frames, frame_consumer,
                      event_consumer, pose_reason_consumer=None,
                      multipose_category_consumer=None,
                      association_category_consumer=None):
    observer = OfflineAssociationObserver()
    for i in range(31):
        poses = ((torso_pose(.5),) if i % 5 == 0 else
                 (torso_pose(.51), torso_pose(.9)))
        mp_result = result(*poses)
        if pose_reason_consumer:
            pose_reason_consumer(pose_adapter_reason(mp_result))
        if multipose_category_consumer:
            multipose_category_consumer(multipose_spatial_category(mp_result))
        if association_category_consumer:
            association_category_consumer(observer.observe(mp_result))
        landmarks = extract_torso_landmarks(mp_result)
        frame_consumer(PoseFrame(
            timestamp_ms=i * 100, source_id=clip_id, landmarks=landmarks
        ))
    return [], {"frames_processed": 31, "invalid_pose_frames": 24,
                "candidate_events": 0}


class _FixedModel:
    threshold = .53

    def predict_probability(self, features):
        return .12


def _one(tmp_path, *, temporal=True, collector=_fictional_stream):
    return _evaluate_one(
        tmp_path / "fiction.mp4", "fall", "mock", 3000,
        tmp_path / "pose.task", _FixedModel(),
        collector=collector, diagnostics=True, detailed_reasons=True,
        spatial_audit=True, temporal_association_audit=temporal,
    )


def test_aggregate_reconciles_all_original_strict_adapter_counts(tmp_path):
    row = _one(tmp_path)
    by_cat = row["temporal_association_categories"]
    assert set(by_cat) == set(ASSOCIATION_CATEGORIES)
    assert sum(by_cat.values()) == 31
    report = aggregate_temporal_association([row], "fall")
    assert report["returned_multi_pose_frames"] == 24
    assert report["strict_accepted_single_frames"] == 7
    assert report["pose_selection_or_alert_change"] is False
    assert report["track_coordinates_persisted"] is False
    assert "landmarks" not in str(report)


def test_invalid_counter_parity_is_rejected(tmp_path):
    row = _one(tmp_path)
    row["temporal_association_categories"][
        "multiple_short_anchor_unique_candidate"
    ] += 1
    with pytest.raises(ValueError, match="inconsistent"):
        aggregate_temporal_association([row], "fall")


def test_normal_spatial_audit_unchanged_and_still_has_no_track_data(tmp_path):
    row = _one(tmp_path, temporal=False)
    assert "temporal_association_categories" not in row
    assert row["pose_rejection_reasons"]["multiple_people"] == 24


def test_temporal_audit_rejects_non_spatial_mode(tmp_path):
    with pytest.raises(ValueError, match="requires full spatial"):
        _evaluate_one(
            tmp_path / "fiction.mp4", "fall", "mock", 3000,
            tmp_path / "pose.task", _FixedModel(), collector=_fictional_stream,
            diagnostics=True, temporal_association_audit=True,
        )
