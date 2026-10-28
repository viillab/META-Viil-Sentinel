"""Camera health tests use fake video capture; never open real networks."""
import pytest

from sentinel_edge.camera_health import (
    RTSP_OPEN_TIMEOUT_MS, RTSP_READ_TIMEOUT_MS,
    open_rtsp_capture, probe_capture, validate_rtsp_env,
)


class FakeCapture:
    def __init__(self, count, opened=True):
        self.count = count
        self.opened = opened

    def isOpened(self):
        return self.opened

    def read(self):
        if self.count <= 0:
            return False, None
        self.count -= 1
        return True, object()


def test_rtsp_configuration_is_private_and_checked():
    secret = "private_test_password"
    url = f"rtsp://demo:{secret}@camera.local:554/Streaming/Channels/102"
    assert validate_rtsp_env("VIIL_CAMERA_RTSP", {"VIIL_CAMERA_RTSP": url}) == url
    for name, value in [
        ("CAMERA_RTSP", url),
        ("VIIL_CAMERA_RTSP", "https://camera.local"),
        ("VIIL_CAMERA_RTSP", "rtsp://camera.local:9554/live"),
        ("VIIL_CAMERA_RTSP", f"rtsp://demo:{secret}@camera.local/stream\nabc"),
    ]:
        with pytest.raises(ValueError) as caught:
            validate_rtsp_env(name, {name: value})
        assert secret not in str(caught.value)


@pytest.mark.parametrize(("readable", "opened", "status"), [
    (12, True, "readable"),
    (5, True, "interrupted"),
    (0, False, "offline"),
])
def test_probe_does_not_keep_frames(readable, opened, status):
    report = probe_capture(FakeCapture(readable, opened), sample_frames=12)
    assert report == {
        "status": status,
        "frames_read": readable if opened else 0,
        "frames_requested": 12,
    }
    assert all(isinstance(value, (str, int)) for value in report.values())


def test_bounded_probe_rejects_unbounded_requests():
    with pytest.raises(ValueError):
        probe_capture(FakeCapture(1000), sample_frames=0)
    with pytest.raises(ValueError):
        probe_capture(FakeCapture(1000), sample_frames=121)


def test_rtsp_capture_uses_ffmpeg_open_only_timeouts():
    class FakeCv2:
        CAP_FFMPEG = 1900
        CAP_PROP_OPEN_TIMEOUT_MSEC = 53
        CAP_PROP_READ_TIMEOUT_MSEC = 54

        @staticmethod
        def VideoCapture(url, backend, parameters):
            assert url == "rtsp://camera.local/Streaming/Channels/102"
            assert backend == FakeCv2.CAP_FFMPEG
            assert parameters == [
                FakeCv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT_MS,
                FakeCv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT_MS,
            ]
            return "fake capture"

    assert open_rtsp_capture(FakeCv2, "rtsp://camera.local/Streaming/Channels/102") == "fake capture"
