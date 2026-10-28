"""Synthetic safety regression: authorization may change while inference blocks.

Uses no real image, person, camera, cloud provider or model weights.
"""
from io import StringIO
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.privacy_gate import PrivacyGateDenied
from sentinel_edge.runner import process_capture


class Capture:
    def __init__(self):
        self.reads = 0

    def get(self, _):
        return 15

    def read(self):
        self.reads += 1
        return True, object()


class FakeCv:
    CAP_PROP_FPS = 5
    COLOR_BGR2RGB = 1

    @staticmethod
    def cvtColor(frame, _):
        return frame


class FakeMp:
    ImageFormat = NS(SRGB=1)

    @staticmethod
    def Image(*, image_format, data):
        return data


class EmptyLandmarker:
    def detect_for_video(self, *_):
        return NS(pose_landmarks=[])


class ForbiddenDetector:
    def process(self, _):
        raise AssertionError("Revoked or expired inference may not reach temporal detector")


def test_revoke_during_inference_never_calls_callbacks_or_writes_pose():
    output = StringIO()
    trace = StringIO()
    capture = Capture()
    received = []
    checked = 0

    def check():
        nonlocal checked
        checked += 1
        # Checks before and after video read pass. During MediaPipe inference,
        # approval becomes invalid; its next check must refuse every consumer.
        if checked == 3:
            raise PrivacyGateDenied("synthetic revocation")

    with pytest.raises(PrivacyGateDenied):
        process_capture(
            capture, cv2=FakeCv, mp=FakeMp, landmarker=EmptyLandmarker(),
            webcam=True, source_id="staged-camera-01", detector=ForbiddenDetector(),
            output=output, trace_file=trace, on_frame=received.append,
            privacy_check=check,
        )
    assert checked == 3
    assert capture.reads == 1
    assert received == []
    assert trace.getvalue() == ""
    assert output.getvalue() == ""


def test_inference_ending_after_session_budget_discards_frame():
    output = StringIO()
    capture = Capture()
    now = [0.0]
    received = []

    class SlowLandmarker:
        def detect_for_video(self, *_):
            now[0] = 1.25
            return NS(pose_landmarks=[])

    result = process_capture(
        capture, cv2=FakeCv, mp=FakeMp, landmarker=SlowLandmarker(),
        webcam=True, source_id="staged-camera-01",
        detector=ForbiddenDetector(), output=output,
        clock=lambda: now[0], max_duration_seconds=1.0,
        on_frame=received.append,
    )
    assert result.frames_processed == 0
    assert capture.reads == 1
    assert received == []
    assert output.getvalue() == ""
