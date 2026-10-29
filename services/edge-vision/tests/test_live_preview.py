"""Authorized local preview: isolated GUI fakes, no actual camera/network."""
import json
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge import live_preview as preview
from sentinel_edge.privacy_gate import PrivacyGateDenied


def frame(h=24, w=32, *, dtype="uint8", channels=3):
    return NS(shape=(h, w, channels), size=h * w * channels, dtype=dtype)


class FakeCapture:
    def __init__(self, frames, *, opened=True, release_error=False):
        self.frames = iter(frames)
        self.opened = opened
        self.release_error = release_error
        self.released = False
        self.reads = 0

    def isOpened(self):
        return self.opened

    def read(self):
        self.reads += 1
        return next(self.frames, (False, None))

    def release(self):
        self.released = True
        if self.release_error:
            raise RuntimeError("password_not_for_logs")


class FakeCV2:
    INTER_AREA = 3
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 16

    def __init__(self, keys=()):
        self.keys = iter(keys)
        self.shown = []
        self.closed = []
        self.resize_requests = []
        self.hud_labels = []

    def putText(self, img, label, *_args):
        self.hud_labels.append(label)
        return img

    def imshow(self, title, img):
        self.shown.append((title, img))

    def waitKey(self, _):
        return next(self.keys, -1)

    def destroyWindow(self, title):
        self.closed.append(title)

    def resize(self, img, size, interpolation):
        self.resize_requests.append((size, interpolation))
        return frame(size[1], size[0])


def test_preview_displays_frames_to_local_gui_only_no_recording():
    cv2 = FakeCV2()
    capture = FakeCapture([(True, frame())] * 3)
    checks = []
    def check():
        checks.append(capture.reads)
    result = preview.preview_authorized_stream(
        cv2, primary_url="fake_primary", alternate_url=None,
        privacy_check=check, open_capture=lambda *_: capture,
        max_frames=3, clock=lambda: 0.0,
    )
    assert result["frames_displayed"] == 3
    assert result["video_saved"] is False
    assert result["remote_streamed"] is False
    assert result["ai_inference_run"] is False
    assert not result["fallback_used"]
    assert len(cv2.shown) == 3
    assert cv2.hud_labels[::2] == [
        f"LOCAL ONLY | frame {n} | 32x24 | warming up" for n in (1, 2, 3)
    ]
    assert len(cv2.hud_labels) == 6  # dark outline + white lettering
    assert all("fake_primary" not in label for label in cv2.hud_labels)
    assert cv2.closed == [preview.WINDOW_TITLE]
    assert capture.released
    assert len(checks) >= 10


def test_local_only_status_hud_uses_display_rate_not_camera_claims():
    cv2 = FakeCV2()
    img = frame(432, 768)
    assert preview._overlay_live_status(
        cv2, img, frame_number=7, display_fps=12.345,
    ) is img
    assert cv2.hud_labels == [
        "LOCAL ONLY | frame 7 | 768x432 | 12.3 display fps",
    ] * 2
    assert "camera fps" not in cv2.hud_labels[0].lower()
    assert "rtsp" not in cv2.hud_labels[0].lower()


def test_unavailable_hud_never_blocks_authorized_preview_or_leaks_errors():
    cv2 = FakeCV2()
    def unsupported_overlay(*_a):
        raise RuntimeError("rtsp://private:password@camera-address")
    cv2.putText = unsupported_overlay
    cap = FakeCapture([(True, frame())])
    result = preview.preview_authorized_stream(
        cv2, primary_url="fake_primary", alternate_url=None,
        privacy_check=lambda: None, open_capture=lambda *_: cap,
        max_frames=1, clock=lambda: 0.0,
    )
    assert result["frames_displayed"] == 1
    assert cap.released and len(cv2.shown) == 1
    assert "password" not in str(result)


def test_corrupt_primary_falls_back_to_approved_alternate_without_stale_frame():
    cv2 = FakeCV2()
    primary = FakeCapture([(True, object())])
    fallback = FakeCapture([(True, frame())] * 2)
    opened = []
    def op(_cv2, url):
        opened.append(url)
        return primary if url == "fake_sub" else fallback
    result = preview.preview_authorized_stream(
        cv2, primary_url="fake_sub", alternate_url="fake_main",
        privacy_check=lambda: None, open_capture=op,
        max_frames=2, clock=lambda: 0,
    )
    assert opened == ["fake_sub", "fake_main"]
    assert result["fallback_used"] is True
    assert result["frames_displayed"] == 2
    assert len(cv2.shown) == 2
    assert primary.released and fallback.released


def test_open_failure_falls_back_and_still_closes_all_handles():
    cv2 = FakeCV2()
    caps = [FakeCapture([], opened=False), FakeCapture([(True, frame())])]
    opened = []
    def op(_cv2, url):
        opened.append(url)
        return caps[len(opened) - 1]
    result = preview.preview_authorized_stream(
        cv2, primary_url="first", alternate_url="backup",
        privacy_check=lambda: None, open_capture=op, max_frames=1,
        clock=lambda: 0,
    )
    assert result["frames_displayed"] == 1
    assert result["fallback_used"]
    assert all(cap.released for cap in caps)


def test_privacy_revocation_after_read_never_shows_frame_or_falls_back():
    cap = FakeCapture([(True, frame())] * 3)
    cv2 = FakeCV2()
    opened = []
    def check():
        if cap.reads:
            raise PrivacyGateDenied("secret_approval_revoked")
    with pytest.raises(PrivacyGateDenied):
        preview.preview_authorized_stream(
            cv2, primary_url="first", alternate_url="backup",
            privacy_check=check, max_frames=2,
            open_capture=lambda _cv, url: (opened.append(url), cap)[1],
            clock=lambda: 0,
        )
    assert opened == ["first"]
    assert cap.released
    assert cv2.shown == []


def test_preview_window_closed_even_when_approval_revoked_after_display():
    cv2 = FakeCV2()
    cap = FakeCapture([(True, frame())])
    def check():
        # Revoke specifically after actual display, independent of the
        # number of privacy checks added around future image operations.
        if cv2.shown:
            raise PrivacyGateDenied("revoked")
    with pytest.raises(PrivacyGateDenied):
        preview.preview_authorized_stream(
            cv2, primary_url="first", alternate_url=None,
            privacy_check=check, max_frames=1,
            open_capture=lambda *_: cap, clock=lambda: 0,
        )
    assert cap.released
    assert len(cv2.shown) == 1
    assert cv2.closed == [preview.WINDOW_TITLE]


def test_closing_gui_window_stops_camera_without_opening_backup():
    cv2 = FakeCV2()
    cv2.WND_PROP_VISIBLE = 4
    cv2.getWindowProperty = lambda *_args: 0
    camera = FakeCapture([(True, frame())] * 5)
    opened = []
    report = preview.preview_authorized_stream(
        cv2, primary_url="sub", alternate_url="main",
        privacy_check=lambda: None,
        open_capture=lambda _cv, url: (opened.append(url), camera)[1],
        max_frames=5, clock=lambda: 0,
    )
    assert report["result"] == "operator_stopped"
    assert opened == ["sub"]
    assert report["frames_displayed"] == 1
    assert camera.released
    assert cv2.closed == [preview.WINDOW_TITLE]


def test_gui_failure_is_not_treated_as_camera_fallback():
    cv2 = FakeCV2()
    def fail_gui(*_args):
        raise RuntimeError("credentialed-url-must-not-leak")
    cv2.imshow = fail_gui
    camera = FakeCapture([(True, frame())] * 5)
    opened = []
    with pytest.raises(preview.PreviewDisplayUnavailable) as caught:
        preview.preview_authorized_stream(
            cv2, primary_url="sub", alternate_url="main",
            privacy_check=lambda: None,
            open_capture=lambda _cv, url: (opened.append(url), camera)[1],
            max_frames=5, clock=lambda: 0,
        )
    assert opened == ["sub"]
    assert camera.released
    assert "credentialed-url" not in str(caught.value)


def test_operator_q_stops_preview_without_reconnect():
    cv2 = FakeCV2(keys=[ord("q")])
    cap = FakeCapture([(True, frame())] * 20)
    report = preview.preview_authorized_stream(
        cv2, primary_url="first", alternate_url="backup",
        privacy_check=lambda: None, max_frames=20,
        open_capture=lambda *_: cap, clock=lambda: 0,
    )
    assert report["result"] == "operator_stopped"
    assert report["frames_displayed"] == 1
    assert cap.released
    assert cv2.closed


def test_resize_bounds_preview_to_smaller_gui_frame():
    cv2 = FakeCV2()
    cap = FakeCapture([(True, frame(1080, 1920))])
    report = preview.preview_authorized_stream(
        cv2, primary_url="first", alternate_url=None,
        privacy_check=lambda: None, max_frames=1,
        open_capture=lambda *_: cap, clock=lambda: 0,
    )
    assert report["frames_displayed"] == 1
    assert cv2.resize_requests == [((960, 540), FakeCV2.INTER_AREA)]
    assert cv2.shown[0][1].shape == (540, 960, 3)


def test_budget_or_missing_privacy_check_fails_closed_without_socket():
    with pytest.raises(ValueError):
        preview.preview_authorized_stream(
            FakeCV2(), primary_url="a", alternate_url=None,
            privacy_check=None,
        )
    for frames, seconds in [(0, 30), (901, 30), (1, 0), (1, 121)]:
        with pytest.raises(ValueError):
            preview.preview_authorized_stream(
                FakeCV2(), primary_url="a", alternate_url=None,
                privacy_check=lambda: None,
                max_frames=frames, duration_seconds=seconds,
            )


def test_revoked_after_close_fails_closed_with_no_success_summary():
    cv2 = FakeCV2()
    cap = FakeCapture([(True, frame())], release_error=True)
    def check():
        if cap.released:
            raise PrivacyGateDenied("revoked_on_close")
    with pytest.raises(PrivacyGateDenied):
        preview.preview_authorized_stream(
            cv2, primary_url="first", alternate_url=None,
            privacy_check=check, max_frames=1,
            open_capture=lambda *_: cap, clock=lambda: 0,
        )
    assert cap.released
    assert cv2.closed == [preview.WINDOW_TITLE]


def test_main_rejects_missing_authorization_before_cv2_import(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VIIL_TEST_SUB", "rtsp://10.3.3.3:554/Streaming/Channels/102")
    monkeypatch.setenv("VIIL_TEST_MAIN", "rtsp://10.3.3.3:554/Streaming/Channels/101")
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    base = [
        "--rtsp-env", "VIIL_TEST_SUB", "--fallback-env", "VIIL_TEST_MAIN",
        "--source-id", "zone-a", "--privacy-approval", str(signed),
    ]
    with pytest.raises(SystemExit):
        preview.main(base + ["--show-local-preview"])
    with pytest.raises(SystemExit):
        preview.main(base + ["--confirm-authorized-camera"])
    assert "rtsp://10.3.3.3" not in capsys.readouterr().err


def test_main_safe_json_report_and_real_approval_with_mock_cv2(
    monkeypatch, tmp_path, capsys,
):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    monkeypatch.setenv("VIIL_TEST_SUB", "rtsp://reader:fake@192.168.50.2:554/Streaming/Channels/102")
    monkeypatch.setenv("VIIL_TEST_MAIN", "rtsp://reader:fake@192.168.50.2:554/Streaming/Channels/101")
    fake_cv2 = ModuleType("cv2")
    display = FakeCV2()
    fake_cv2.imshow = display.imshow
    fake_cv2.waitKey = display.waitKey
    fake_cv2.destroyWindow = display.destroyWindow
    fake_cv2.resize = display.resize
    fake_cv2.INTER_AREA = FakeCV2.INTER_AREA
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    def opened(_cv2, _url):
        return FakeCapture([(True, frame())])
    monkeypatch.setattr(preview, "open_rtsp_capture", opened)
    result = preview.main([
        "--rtsp-env", "VIIL_TEST_SUB", "--fallback-env", "VIIL_TEST_MAIN",
        "--source-id", "zone-a", "--privacy-approval", str(signed),
        "--confirm-authorized-camera", "--show-local-preview",
        "--max-frames", "1",
    ])
    assert result == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["frames_displayed"] == 1
    assert report["video_saved"] is False
    assert "fake@" not in out.out + out.err
    assert len(display.shown) == 1
