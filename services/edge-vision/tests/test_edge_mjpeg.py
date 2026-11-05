"""Offline Edge MJPEG tests: signed synthetic policy and fake video only."""
from types import SimpleNamespace as NS

import pytest

from privacy_approval_fixture import make_policy, TEST_KEY
from sentinel_edge.edge_mjpeg import (
    EdgeMediaDenied, EdgeMediaUnavailable, MAX_MJPEG_PART_BYTES,
    PREFLIGHT_DECODE_FRAMES, iter_authorized_mjpeg_parts,
)
from sentinel_edge.privacy_gate import KEY_ENV


PRIVATE_URL = "rtsp://local-viewer:SYNTHETIC-TEST-NOT-A-REAL-PASSWORD@192.168.70.6:554/Streaming/Channels/102"
ENV = "VIIL_TEST_MEDIA_CAMERA"
FRAME = NS(shape=(432, 768, 3), size=432 * 768 * 3, dtype="uint8")


class FakeCapture:
    def __init__(self, frames=30, invalid_at=None):
        self.frames = frames
        self.invalid_at = invalid_at
        self.calls = 0
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        self.calls += 1
        if self.invalid_at == self.calls:
            return False, None
        if self.calls > self.frames:
            return False, None
        return True, FRAME

    def release(self):
        self.released = True


class FakeCV2:
    IMWRITE_JPEG_QUALITY = 1
    INTER_AREA = 2

    def __init__(self, jpeg=b"\xff\xd8synthetic\xff\xd9"):
        self.jpeg = jpeg
        self.encoded = 0
        self.resized = []

    def imencode(self, extension, frame, options):
        assert extension == ".jpg"
        assert options == [self.IMWRITE_JPEG_QUALITY, 65]
        self.encoded += 1
        return True, NS(tobytes=lambda: self.jpeg)

    def resize(self, frame, shape, interpolation=None):
        self.resized.append(shape)
        assert interpolation == self.INTER_AREA
        return NS(shape=(shape[1], shape[0], 3),
                  size=shape[0] * shape[1] * 3, dtype="uint8")


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def now(self):
        return self.value

    def sleep(self, interval):
        self.sleeps.append(interval)
        self.value += interval


def inputs(tmp_path, monkeypatch, *, cap=None, gate=None, camera_ids=None, cv2=None,
           clock=None, **overrides):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=camera_ids
                           or ("staged-camera-01",))
    instance = cap or FakeCapture()
    log = []
    def open_capture(_cv2, url):
        log.append(url)
        return instance
    timer = clock or FakeClock()
    values = {
        "source_env": ENV,
        "source_id": "staged-camera-01",
        "privacy_approval": approval,
        "environment": {KEY_ENV: TEST_KEY, ENV: PRIVATE_URL},
        "viewer_check": gate or (lambda: True),
        "open_capture": open_capture,
        "clock": timer.now,
        "sleeper": timer.sleep,
        "max_frames": 2,
    }
    values.update(overrides)
    return cv2 or FakeCV2(), values, instance, log, timer


def test_no_captured_frame_before_twelve_decoder_preflight(tmp_path, monkeypatch):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch)
    items = list(iter_authorized_mjpeg_parts(cv2, **values))
    assert len(items) == 2
    assert cap.calls == PREFLIGHT_DECODE_FRAMES + 2
    assert cap.released and opened == [PRIVATE_URL]
    assert cv2.encoded == 2
    assert items[0].startswith(
        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 13\r\n\r\n"
    )
    assert items[0].endswith(b"\xff\xd9\r\n")
    assert b"RTSP" not in b"".join(items)
    assert b"SYNTHETIC-TEST-NOT-A-REAL-PASSWORD" not in b"".join(items)


def test_no_camera_open_without_signed_approval(tmp_path, monkeypatch):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch)
    values["privacy_approval"] = tmp_path / "missing-policy.json"
    with pytest.raises(EdgeMediaDenied) as e:
        next(iter_authorized_mjpeg_parts(cv2, **values))
    assert not opened and cap.calls == 0
    assert PRIVATE_URL not in str(e.value)


def test_wrong_source_scope_fails_before_native_camera(tmp_path, monkeypatch):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch,
                                            camera_ids=("different-camera",))
    with pytest.raises(EdgeMediaDenied):
        next(iter_authorized_mjpeg_parts(cv2, **values))
    assert not opened and cap.calls == 0


@pytest.mark.parametrize("allowed", [False, None, 1, "true"])
def test_backend_viewer_denied_before_native_camera(tmp_path, monkeypatch, allowed):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch,
                                            gate=lambda: allowed)
    with pytest.raises(EdgeMediaDenied):
        next(iter_authorized_mjpeg_parts(cv2, **values))
    assert not opened and cap.calls == 0


def test_revoked_viewer_stops_during_preflight_no_output(tmp_path, monkeypatch):
    checks = [0]
    def gate():
        checks[0] += 1
        return checks[0] < 8
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch, gate=gate)
    with pytest.raises(EdgeMediaDenied):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert opened == [PRIVATE_URL]
    assert cap.released
    assert cap.calls < PREFLIGHT_DECODE_FRAMES
    assert cv2.encoded == 0


def test_policy_revoked_after_first_frame_closes_decoder(tmp_path, monkeypatch):
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch)
    iterator = iter_authorized_mjpeg_parts(cv2, **values)
    assert next(iterator).startswith(b"--frame")
    values["privacy_approval"].unlink()
    with pytest.raises(EdgeMediaDenied):
        next(iterator)
    assert cap.released and cv2.encoded == 1


def test_manual_stream_close_releases_native_decoder(tmp_path, monkeypatch):
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch)
    iterator = iter_authorized_mjpeg_parts(cv2, **values)
    next(iterator)
    iterator.close()
    assert cap.released


def test_slow_native_open_rejected_before_any_decode(tmp_path, monkeypatch):
    from sentinel_edge.edge_mjpeg import MAX_PREFLIGHT_SECONDS

    clock = FakeClock()
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch, clock=clock)

    def slow_open(_cv2, _url):
        clock.value += MAX_PREFLIGHT_SECONDS + 0.5
        return cap

    values["open_capture"] = slow_open
    with pytest.raises(EdgeMediaUnavailable, match="first-frame preflight"):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released and cap.calls == 0 and cv2.encoded == 0


def test_slow_twelve_frame_preflight_rejects_and_releases(tmp_path, monkeypatch):
    clock = FakeClock()
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch, clock=clock)
    original = cap.read

    def slow_read():
        clock.value += 1.5
        return original()

    cap.read = slow_read
    with pytest.raises(EdgeMediaUnavailable, match="first-frame preflight"):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released and cap.calls < PREFLIGHT_DECODE_FRAMES
    assert cv2.encoded == 0


def test_slow_thirteenth_frame_does_not_emit_stale_first_jpeg(tmp_path, monkeypatch):
    clock = FakeClock()
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch, clock=clock)
    original = cap.read

    def slow_first_jpeg_frame():
        clock.value += 8.0 if cap.calls == PREFLIGHT_DECODE_FRAMES else 0.3
        return original()

    cap.read = slow_first_jpeg_frame
    with pytest.raises(EdgeMediaUnavailable, match="first-frame preflight"):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released and cap.calls == PREFLIGHT_DECODE_FRAMES + 1
    assert cv2.encoded == 0


def test_slow_jpeg_encoder_does_not_emit_expired_frame(tmp_path, monkeypatch):
    clock = FakeClock()
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch, clock=clock)
    old = cv2.imencode

    def slow_encoding(*args, **kwargs):
        clock.value += 10.5
        return old(*args, **kwargs)

    cv2.imencode = slow_encoding
    with pytest.raises(EdgeMediaUnavailable, match="first-frame preflight"):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released and cap.calls == PREFLIGHT_DECODE_FRAMES + 1
    assert cv2.encoded == 1  # encoded locally, but never yielded to browser


def test_timely_twelve_frame_preflight_and_first_jpeg_still_work(tmp_path, monkeypatch):
    clock = FakeClock()
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch, clock=clock)
    original = cap.read

    def timely_read():
        clock.value += 0.25
        return original()

    cap.read = timely_read
    parts = list(iter_authorized_mjpeg_parts(cv2, **values))
    assert len(parts) == 2 and all(b"synthetic" in part for part in parts)
    assert cap.released


def test_decode_preflight_cannot_promote_only_eleven_frames(tmp_path, monkeypatch):
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch,
                                      cap=FakeCapture(invalid_at=12))
    with pytest.raises(EdgeMediaUnavailable):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released and cv2.encoded == 0


def test_failure_to_encode_oversized_frame_never_yields_image(tmp_path, monkeypatch):
    frame = b"\xff\xd8" + b"x" * MAX_MJPEG_PART_BYTES + b"\xff\xd9"
    cv2, values, cap, _, _ = inputs(tmp_path, monkeypatch,
                                      cv2=FakeCV2(jpeg=frame))
    with pytest.raises(EdgeMediaUnavailable):
        list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cap.released


def test_prohibited_public_url_rejected_before_open(tmp_path, monkeypatch):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch)
    values["environment"][ENV] = "rtsp://example.com:554/live"
    with pytest.raises(ValueError, match="Invalid private RTSP configuration"):
        next(iter_authorized_mjpeg_parts(cv2, **values))
    assert not opened and cap.calls == 0


def test_bounded_resolution_and_pacing(tmp_path, monkeypatch):
    cv2, values, cap, _, clock = inputs(tmp_path, monkeypatch)
    large_frame = NS(shape=(1440, 2560, 3), size=1440 * 2560 * 3, dtype="uint8")
    cap.read = lambda: (True, large_frame)
    list(iter_authorized_mjpeg_parts(cv2, **values))
    assert cv2.resized == [(768, 432), (768, 432)]
    assert len(clock.sleeps) == 1 and clock.sleeps[0] == pytest.approx(0.2)
    assert cap.released


@pytest.mark.parametrize("changes", [
    {"max_frames": 0}, {"max_frames": 121}, {"duration_seconds": 35},
    {"duration_seconds": float("nan")}, {"fps": 0}, {"fps": 11},
    {"jpeg_quality": 90}, {"jpeg_quality": True},
    {"source_id": "../foreign-camera"}, {"viewer_check": None},
])
def test_invalid_budgets_never_open_camera(tmp_path, monkeypatch, changes):
    cv2, values, cap, opened, _ = inputs(tmp_path, monkeypatch, **changes)
    with pytest.raises(ValueError):
        next(iter_authorized_mjpeg_parts(cv2, **values))
    assert not opened and cap.calls == 0
