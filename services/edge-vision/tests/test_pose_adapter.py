"""Fail-closed conversion of MediaPipe-like pose results (no webcam access)."""
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.pose_adapter import extract_torso_landmarks

TORSO = (11, 12, 23, 24)


def make_pose(*, visibility=0.99, presence=0.99, x=0.5, y=0.3):
    landmarks = [NS(x=x, y=y, visibility=visibility, presence=presence)
                 for _ in range(33)]
    return NS(pose_landmarks=[landmarks])


def test_returns_only_four_visible_torso_landmarks():
    result = extract_torso_landmarks(make_pose())
    assert set(result) == set(TORSO)
    assert all(p.visibility == 0.99 for p in result.values())


@pytest.mark.parametrize("result", [
    NS(pose_landmarks=[]),
    NS(pose_landmarks=None),
    NS(pose_landmarks=[[], []]),
    NS(pose_landmarks=[[NS(x=0, y=0, visibility=1)] * 10]),
    NS(pose_landmarks="invalid"),
    object(),
])
def test_unknown_or_ambiguous_person_fails_closed(result):
    assert extract_torso_landmarks(result) == {}


@pytest.mark.parametrize("kwargs", [
    {"visibility": None},
    {"visibility": 0.20},
    {"visibility": float("nan")},
    {"presence": 0.1},
    {"presence": float("nan")},
    {"x": float("inf")},
    {"x": -0.1},
    {"y": 1.1},
    {"x": None},
])
def test_low_quality_unavailable_or_out_of_frame_fails_closed(kwargs):
    assert extract_torso_landmarks(make_pose(**kwargs)) == {}


def test_one_missing_torso_point_invalidates_frame():
    result = make_pose()
    result.pose_landmarks[0][11] = NS(x=None, y=0.2, visibility=0.9)
    assert extract_torso_landmarks(result) == {}


def test_presence_unavailable_is_allowed_when_visibility_is_high():
    assert set(extract_torso_landmarks(make_pose(presence=None))) == set(TORSO)


def test_invalid_minimum_quality_rejected():
    with pytest.raises(ValueError):
        extract_torso_landmarks(make_pose(), min_confidence=float("nan"))
