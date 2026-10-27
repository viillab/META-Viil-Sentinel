"""Video metadata integrity tests without camera/model or personal footage."""
from types import SimpleNamespace

import pytest

from sentinel_edge.video_metadata import expected_frame_count, require_complete_decode


class FakeCapture:
    def __init__(self, *, fps=10.0, count=12.0):
        self.fps, self.count = fps, count

    def get(self, key):
        return self.fps if key == 1 else self.count


CV2 = SimpleNamespace(CAP_PROP_FPS=1, CAP_PROP_FRAME_COUNT=2)


def test_accepts_consentable_bounded_metadata():
    count = expected_frame_count(FakeCapture(fps=30, count=70), CV2,
                                 clip_id="synthetic", max_frames=100)
    assert count == 70
    require_complete_decode(clip_id="synthetic", expected=70, decoded=70)


@pytest.mark.parametrize("fps", [0, -1, 0.5, 240, float("nan"), float("inf")])
def test_rejects_missing_or_invalid_fps(fps):
    with pytest.raises(ValueError, match="FPS"):
        expected_frame_count(FakeCapture(fps=fps), CV2,
                             clip_id="synthetic", max_frames=100)


@pytest.mark.parametrize("count", [0, -1, float("nan"), float("inf"), 12.5])
def test_rejects_missing_or_invalid_frame_count(count):
    with pytest.raises(ValueError, match="frame count"):
        expected_frame_count(FakeCapture(count=count), CV2,
                             clip_id="synthetic", max_frames=100)


def test_rejects_overlong_declared_media_before_processing():
    with pytest.raises(ValueError, match="before inference"):
        expected_frame_count(FakeCapture(count=200), CV2,
                             clip_id="synthetic", max_frames=100)


@pytest.mark.parametrize("decoded", [0, 2, 4])
def test_rejects_incomplete_or_inconsistent_frame_decode(decoded):
    with pytest.raises(ValueError, match="incomplete or metadata is inconsistent"):
        require_complete_decode(clip_id="synthetic", expected=3, decoded=decoded)


def test_never_expose_identifiable_media_paths_in_error():
    with pytest.raises(ValueError) as exc:
        require_complete_decode(clip_id="pseudonymous-01", expected=10, decoded=4)
    assert "pseudonymous-01" in str(exc.value)
    assert "D:\\staged-private" not in str(exc.value)
