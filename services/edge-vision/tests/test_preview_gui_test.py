"""Synthetic GUI diagnostics: never access a real camera."""
import json
import sys
from types import ModuleType

import numpy as np
import pytest

from sentinel_edge import live_preview
from sentinel_edge import preview_gui_test as gui


class FakeGUI:
    FONT_HERSHEY_SIMPLEX = 0
    WND_PROP_VISIBLE = 4

    def __init__(self, *, keys=None, visibility=1, fails=False):
        self.keys = iter(keys or [])
        self.visibility = visibility
        self.fails = fails
        self.frames = []
        self.closed = []

    def putText(self, frame, text, pos, font, scale, color, thickness):
        assert frame.shape == (360, 640, 3)
        assert font == self.FONT_HERSHEY_SIMPLEX
        self.frames.append(text)

    def imshow(self, title, frame):
        assert title == gui.TEST_TITLE
        if self.fails:
            raise RuntimeError("SECRET_DISPLAY_PATH")
        assert isinstance(frame, np.ndarray)

    def waitKey(self, _ms):
        return next(self.keys, -1)

    def getWindowProperty(self, title, prop):
        assert title == gui.TEST_TITLE
        assert prop == self.WND_PROP_VISIBLE
        return self.visibility

    def destroyWindow(self, title):
        self.closed.append(title)


def test_synthetic_gui_has_unambiguous_labels_and_no_camera():
    cv2 = FakeGUI(keys=[ord("Q")])
    report = gui.show_synthetic_gui(
        cv2, np, max_frames=10, clock=lambda: 0,
    )
    assert report["result"] == "operator_stopped"
    assert report["frames_displayed"] == 1
    assert report["synthetic_test_pattern"] is True
    assert report["camera_opened"] is False
    assert report["video_decoded"] is False
    assert report["video_saved"] is False
    assert report["remote_streamed"] is False
    assert "SYNTHETIC / NOT CAMERA VIDEO" in cv2.frames
    assert cv2.closed == [gui.TEST_TITLE]


def test_synthetic_test_stops_when_window_closed():
    cv2 = FakeGUI(visibility=0)
    report = gui.show_synthetic_gui(
        cv2, np, max_frames=10, clock=lambda: 0,
    )
    assert report["result"] == "window_closed"
    assert report["frames_displayed"] == 1
    assert cv2.closed == [gui.TEST_TITLE]


def test_synthetic_bounds_do_not_allow_indefinite_session():
    cv2 = FakeGUI()
    report = gui.show_synthetic_gui(cv2, np, max_frames=3, clock=lambda: 0)
    assert report["frames_displayed"] == 3
    assert len(cv2.closed) == 1
    for kwargs in [
        {"max_frames": 0}, {"max_frames": 1000}, {"duration_seconds": -1},
        {"duration_seconds": 120},
    ]:
        with pytest.raises(ValueError):
            gui.show_synthetic_gui(FakeGUI(), np, **kwargs)


def test_synthetic_native_gui_error_is_redacted():
    with pytest.raises(gui.LocalGuiUnavailable) as caught:
        gui.show_synthetic_gui(FakeGUI(fails=True), np, max_frames=1)
    assert "SECRET_DISPLAY_PATH" not in str(caught.value)


def test_cli_gui_self_test_needs_no_rtsp_approval_or_camera(monkeypatch, capsys):
    mock_cv2 = ModuleType("cv2")
    fake = FakeGUI(keys=[27])
    for name in (
        "putText", "imshow", "waitKey", "getWindowProperty", "destroyWindow",
    ):
        setattr(mock_cv2, name, getattr(fake, name))
    mock_cv2.FONT_HERSHEY_SIMPLEX = 0
    mock_cv2.WND_PROP_VISIBLE = 4
    monkeypatch.setitem(sys.modules, "cv2", mock_cv2)
    assert live_preview.main(["--self-test-gui", "--duration-seconds", "1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["synthetic_test_pattern"] is True
    assert report["camera_opened"] is False
    assert report["frames_displayed"] == 1


@pytest.mark.parametrize("extra", [
    ["--rtsp-env", "VIIL_SUB"],
    ["--privacy-approval", "somefile.json"],
    ["--source-id", "a"],
    ["--show-local-preview"],
    ["--confirm-authorized-camera"],
    ["--fallback-env", "VIIL_BACKUP"],
])
def test_gui_self_test_refuses_mixed_camera_args(extra, capsys):
    with pytest.raises(SystemExit):
        live_preview.main(["--self-test-gui", *extra])
    assert "Synthetic GUI test cannot accept camera parameters" in capsys.readouterr().err


def test_camera_mode_still_requires_signed_approval_and_source(capsys):
    with pytest.raises(SystemExit):
        live_preview.main(["--show-local-preview", "--confirm-authorized-camera"])
    assert "Authorized camera parameters required" in capsys.readouterr().err
