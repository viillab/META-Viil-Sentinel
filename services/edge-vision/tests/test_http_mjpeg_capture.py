"""Authorized HTTP Digest/MJPEG tests: fake HTTP body, no sockets or camera."""
import io
import json
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge import http_mjpeg_capture as mjpeg
from sentinel_edge import live_preview, camera_health

URL = "http://192.168.10.204:80/ISAPI/Streaming/channels/102/httpPreview"
FAKE_PASSWORD = "SIMULATED_NO_NETWORK_SECRET"


class FakeHTTPResponse:
    def __init__(self, data, *, content_type="multipart/x-mixed-replace; boundary=frame"):
        self.headers = {"Content-Type": content_type}
        self.body = io.BytesIO(data)
        self.closed = False

    def read(self, size):
        return self.body.read(size)

    def close(self):
        self.closed = True


def jpeg_frame():
    data = np.zeros((24, 32, 3), dtype=np.uint8)
    data[:, :, 1] = 128
    ok, image = cv2.imencode(".jpg", data)
    assert ok
    return image.tobytes()


def http_frames(count):
    return b"".join(
        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_frame() + b"\r\n"
        for _ in range(count)
    )


@pytest.mark.parametrize("url", [
    "http://8.8.8.8/ISAPI/Streaming/channels/102/httpPreview",
    "http://127.0.0.1/ISAPI/Streaming/channels/102/httpPreview",
    "http://192.168.10.204.evil.example/ISAPI/Streaming/channels/102/httpPreview",
    "http://user:secret@192.168.10.204/ISAPI/Streaming/channels/102/httpPreview",
    "http://192.168.10.204/ISAPI/Streaming/channels/101/httpPreview",
    "http://192.168.10.204/ISAPI/Streaming/channels/102/httpPreview?redirect=evil",
    "https://192.168.10.204/ISAPI/Streaming/channels/102/httpPreview",
    "http://192.168.10.204:9876/ISAPI/Streaming/channels/102/httpPreview",
    "http://192.168.10.204:0/ISAPI/Streaming/channels/102/httpPreview",
])
def test_mjpeg_url_rejects_unsafe_remote_endpoints(url):
    with pytest.raises(ValueError) as error:
        mjpeg.validate_http_mjpeg_env("VIIL_CAM", {"VIIL_CAM": url})
    assert "secret" not in str(error.value)


def test_mjpeg_url_accepts_only_private_approved_channel_102():
    assert mjpeg.validate_http_mjpeg_env(
        "VIIL_CAM", {"VIIL_CAM": URL},
    ) == URL
    assert mjpeg.validate_http_mjpeg_env(
        "VIIL_CAM", {"VIIL_CAM": URL.replace("/ISAPI/", "/")},
    ).endswith("httpPreview")


def test_http_digest_decoder_reads_two_real_jpegs_without_recording():
    http = FakeHTTPResponse(http_frames(2))
    calls = []
    def opener_factory(*handlers):
        calls.append(handlers)
        return NS(open=lambda req, timeout: http)
    cap = mjpeg.HTTPMJPEGCapture(
        cv2, URL, username="reader", password=FAKE_PASSWORD,
        opener_factory=opener_factory,
    )
    assert cap.isOpened()
    assert len(calls[0]) == 3
    assert isinstance(calls[0][1], mjpeg._NoRedirect)
    assert cap.get(5) == 0
    for _ in range(2):
        ok, frame = cap.read()
        assert ok and frame.shape == (24, 32, 3)
        assert frame.dtype == np.uint8
    assert cap.read() == (False, None)
    cap.release()
    assert http.closed
    assert not cap.isOpened()
    assert cap.read() == (False, None)


def test_mjpeg_wrong_content_type_fails_closed_and_releases_response():
    http = FakeHTTPResponse(jpeg_frame(), content_type="text/html")
    with pytest.raises(RuntimeError, match="unavailable") as err:
        mjpeg.HTTPMJPEGCapture(
            cv2, URL, username="reader", password=FAKE_PASSWORD,
            opener_factory=lambda *handlers: NS(open=lambda req, timeout: http),
        )
    assert http.closed
    assert FAKE_PASSWORD not in str(err.value)


def test_mjpeg_corrupt_frame_and_oversized_frame_are_redacted():
    for blob in [b"\xff\xd8garbage\xff\xd9", b"\xff\xd8" + b"a" * (mjpeg.MAX_JPEG_BYTES + 1)]:
        http = FakeHTTPResponse(blob)
        cap = mjpeg.HTTPMJPEGCapture(
            cv2, URL, username="reader", password=FAKE_PASSWORD,
            opener_factory=lambda *handlers: NS(open=lambda req, timeout: http),
        )
        with pytest.raises(RuntimeError, match="interrupted") as err:
            cap.read()
        assert FAKE_PASSWORD not in str(err.value)
        cap.release()
        assert http.closed


def test_http_mjpeg_preview_denied_before_decoder_open(monkeypatch, tmp_path):
    monkeypatch.setenv("VIIL_TEST_HTTP_MJPEG", URL)
    monkeypatch.setenv("VIIL_HIK_HTTP_USER", "reader")
    monkeypatch.setenv("VIIL_HIK_HTTP_PASS", FAKE_PASSWORD)
    called = []
    def reject(*args, **kwargs):
        called.append(True)
        raise RuntimeError("must not open")
    monkeypatch.setattr(mjpeg, "open_http_mjpeg_capture", reject)
    with pytest.raises(SystemExit):
        live_preview.main([
            "--http-mjpeg-env", "VIIL_TEST_HTTP_MJPEG", "--decoder", "http-mjpeg",
            "--source-id", "zone-a", "--privacy-approval", str(tmp_path / "not-approved"),
            "--confirm-authorized-camera", "--show-local-preview",
            "--max-frames", "1",
        ])
    assert called == []


def test_http_mjpeg_health_with_signed_test_fixture(monkeypatch, tmp_path, capsys):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    monkeypatch.setenv("VIIL_TEST_HTTP_MJPEG", URL)
    frames = []
    class FakeCapture:
        def isOpened(self):
            return True
        def read(self):
            frames.append(True)
            return True, np.zeros((24, 32, 3), dtype=np.uint8)
        def release(self):
            pass
    monkeypatch.setattr(mjpeg, "open_http_mjpeg_capture", lambda *_: FakeCapture())
    assert camera_health.main([
        "--http-mjpeg-env", "VIIL_TEST_HTTP_MJPEG",
        "--decoder", "http-mjpeg", "--source-id", "zone-a",
        "--privacy-approval", str(signed),
        "--confirm-authorized-camera", "--frames", "2",
    ]) == 0
    assert len(frames) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["frames_read"] == 2
    assert result["status"] == "readable"
    assert "camera" not in result or not isinstance(result.get("camera"), dict)


def test_http_mjpeg_rejects_rtsp_fallback_or_unmatched_decoder(monkeypatch, tmp_path):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    monkeypatch.setenv("VIIL_TEST_HTTP_MJPEG", URL)
    for extra in [
        ["--decoder", "opencv"],
        ["--decoder", "http-mjpeg", "--fallback-env", "VIIL_RTSP_MAIN"],
        ["--decoder", "http-mjpeg", "--rtsp-env", "VIIL_RTSP_SUB"],
    ]:
        with pytest.raises(SystemExit):
            live_preview.main([
                "--http-mjpeg-env", "VIIL_TEST_HTTP_MJPEG",
                "--source-id", "zone-a", "--privacy-approval", str(signed),
                "--confirm-authorized-camera", "--show-local-preview",
                *extra,
            ])


def test_http_mjpeg_decoder_no_redirect():
    redirect = mjpeg._NoRedirect()
    assert redirect.redirect_request(
        None, None, 302, "Found", {}, "http://attacker.example/",
    ) is None
