"""No camera, external video or personal pixels used by resolution tests."""
from io import StringIO

import pytest

from sentinel_edge.frame_resize import resize_for_inference, validate_max_side
from sentinel_edge.runner import process_capture
from test_runner_integration import FakeLandmarker, FakeMp


class FakeFrame:
    def __init__(self, height: int, width: int):
        self.shape = (height, width, 3)


class FakeCV:
    CAP_PROP_FPS = 5
    COLOR_BGR2RGB = 1
    INTER_AREA = 3
    sizes = []

    @classmethod
    def resize(cls, image, size, interpolation=None):
        assert interpolation == cls.INTER_AREA
        cls.sizes.append(size)
        return FakeFrame(size[1], size[0])

    @staticmethod
    def cvtColor(frame, code):
        assert code == FakeCV.COLOR_BGR2RGB
        return frame


class FakeCapture:
    def __init__(self, count=9):
        self.count = count
        self.index = 0

    def get(self, key):
        assert key == FakeCV.CAP_PROP_FPS
        return 10.0

    def read(self):
        if self.index >= self.count:
            return False, None
        self.index += 1
        return True, FakeFrame(720, 1280)


@pytest.mark.parametrize("cap", [-1, 1, 255, 4097, 1.5, True, None])
def test_bad_experimental_caps_rejected(cap):
    with pytest.raises(ValueError, match="max_inference_side"):
        validate_max_side(cap)


def test_no_opt_in_returns_same_source_object_without_accessing_shape():
    original = object()
    assert resize_for_inference(original, FakeCV, max_side=0) is original


def test_resize_preserves_aspect_and_never_upscales():
    FakeCV.sizes.clear()
    source = FakeFrame(720, 1280)
    scaled = resize_for_inference(source, FakeCV, max_side=640)
    assert scaled.shape == (360, 640, 3)
    assert FakeCV.sizes == [(640, 360)]
    assert resize_for_inference(scaled, FakeCV, max_side=640) is scaled
    assert len(FakeCV.sizes) == 1


@pytest.mark.parametrize("shape", [(0, 1280, 3), (720, 1280, 1),
                                  (720, 0, 3), (1280,)])
def test_invalid_shape_fails_closed(shape):
    image = FakeFrame(720, 1280)
    image.shape = shape
    with pytest.raises(ValueError, match="HxWx3"):
        resize_for_inference(image, FakeCV, max_side=640)


def test_opt_in_resizes_before_model_without_dropping_frames_or_changing_timestamps():
    FakeCV.sizes.clear()
    captured_shapes = []

    class ShapeCheckingLandmarker(FakeLandmarker):
        def detect_for_video(self, image, timestamp):
            captured_shapes.append((image.shape, timestamp))
            return super().detect_for_video(image, timestamp)

    model = ShapeCheckingLandmarker()
    stats = process_capture(
        FakeCapture(), cv2=FakeCV, mp=FakeMp, landmarker=model,
        webcam=False, source_id="synthetic-01", output=StringIO(),
        max_inference_side=640,
    )
    assert stats.frames_processed == 9
    assert stats.candidate_events == 1
    assert FakeCV.sizes == [(640, 360)] * 9
    assert captured_shapes == [((360, 640, 3), i * 100) for i in range(9)]
