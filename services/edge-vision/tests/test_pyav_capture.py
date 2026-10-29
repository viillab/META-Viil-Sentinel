"""Offline PyAV adapter checks. No network, credentials, camera, or native codec."""
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from sentinel_edge.pyav_capture import PyAVCapture, open_pyav_capture


class FakeVideoFrame:
    def __init__(self):
        self.formats = []

    def to_ndarray(self, *, format):
        self.formats.append(format)
        return NS(shape=(24, 32, 3), size=24 * 32 * 3, dtype="uint8")


class FakeContainer:
    def __init__(self, *, video=True, decode_error=False):
        self.streams = [NS(type="video", average_rate=15)] if video else [NS(type="audio")]
        self.closed = False
        self.decode_error = decode_error
        self.sample = FakeVideoFrame()

    def decode(self, *, video):
        assert video == 0
        if self.decode_error:
            def fail():
                raise RuntimeError("rtsp://secret:password@192.168.10.204")
                yield None
            return fail()
        return iter([self.sample])

    def close(self):
        self.closed = True


def install_fake_av(monkeypatch, container, opened):
    av = ModuleType("av")

    def open_fake(url, **kwargs):
        opened.append((url, kwargs))
        return container

    av.open = open_fake
    monkeypatch.setitem(sys.modules, "av", av)


def test_pyav_capture_reads_bgr24_without_file_output(monkeypatch):
    created = []
    container = FakeContainer()
    install_fake_av(monkeypatch, container, created)
    cap = open_pyav_capture(None, "rtsp://example-hidden")
    assert created[0][1] == {
        "mode": "r", "format": "rtsp",
        "options": {"rtsp_transport": "tcp", "rw_timeout": "4000000"},
        "timeout": (8.0, 4.0),
    }
    assert cap.isOpened() and cap.get(5) == 15.0
    ok, first = cap.read()
    assert ok and first.shape == (24, 32, 3)
    assert container.sample.formats == ["bgr24"]
    assert cap.read() == (False, None)
    cap.release()
    assert container.closed and not cap.isOpened()
    assert cap.read() == (False, None)
    cap.release()


def test_empty_video_track_closes_container_without_leaking_url(monkeypatch):
    container = FakeContainer(video=False)
    install_fake_av(monkeypatch, container, [])
    with pytest.raises(RuntimeError, match="could not open") as err:
        PyAVCapture("rtsp://reader:PRIVATE@host")
    assert container.closed
    assert "PRIVATE" not in str(err.value)


def test_native_decode_error_redacted_and_release_works(monkeypatch):
    container = FakeContainer(decode_error=True)
    install_fake_av(monkeypatch, container, [])
    cap = PyAVCapture("rtsp://reader:PRIVATE@host")
    with pytest.raises(RuntimeError, match="interrupted") as err:
        cap.read()
    assert "PRIVATE" not in str(err.value)
    assert "password" not in str(err.value)
    cap.release()
    assert container.closed



def test_health_pyav_selection_requires_real_policy_and_checks_every_read(
    monkeypatch, tmp_path, capsys,
):
    from privacy_approval_fixture import make_policy
    from sentinel_edge import camera_health

    policy = make_policy(tmp_path, monkeypatch, camera_ids=("cam1",))
    monkeypatch.setenv("VIIL_TEST_PYAV_HEALTH", "rtsp://192.168.10.204:554/Streaming/Channels/102")
    cv2 = ModuleType("cv2")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    container = FakeContainer()
    opened = []
    install_fake_av(monkeypatch, container, opened)
    assert camera_health.main([
        "--rtsp-env", "VIIL_TEST_PYAV_HEALTH",
        "--privacy-approval", str(policy),
        "--source-id", "cam1",
        "--confirm-authorized-camera", "--frames", "1",
        "--decoder", "pyav",
    ]) == 0
    out = capsys.readouterr()
    assert '"frames_read": 1' in out.out
    assert container.closed and opened
    assert "192.168.10.204" not in out.out


def test_pyav_preview_and_health_absent_signed_approval_do_not_open(
    monkeypatch, tmp_path,
):
    from sentinel_edge import live_preview, camera_health

    monkeypatch.setenv("VIIL_TEST_PYAV_HEALTH", "rtsp://192.168.10.204:554/Streaming/Channels/102")
    monkeypatch.setenv("VIIL_TEST_PYAV_SUB", "rtsp://192.168.10.204:554/Streaming/Channels/102")
    missing = str(tmp_path / "missing-approval.json")
    with pytest.raises(SystemExit):
        camera_health.main([
            "--rtsp-env", "VIIL_TEST_PYAV_HEALTH",
            "--privacy-approval", missing, "--source-id", "cam1",
            "--confirm-authorized-camera", "--decoder", "pyav",
        ])
    with pytest.raises(SystemExit):
        live_preview.main([
            "--rtsp-env", "VIIL_TEST_PYAV_SUB",
            "--privacy-approval", missing, "--source-id", "cam1",
            "--confirm-authorized-camera", "--show-local-preview", "--decoder", "pyav",
        ])

def test_native_open_error_redacted(monkeypatch):
    av = ModuleType("av")
    def fail_open(*_a, **_kw):
        raise RuntimeError("rtsp://reader:PRIVATE@192.168.10.204")
    av.open = fail_open
    monkeypatch.setitem(sys.modules, "av", av)
    with pytest.raises(RuntimeError, match="could not open") as err:
        PyAVCapture("rtsp://reader:PRIVATE@192.168.10.204")
    assert "PRIVATE" not in str(err.value)


def test_preview_pyav_selection_uses_guarded_opener(monkeypatch, tmp_path, capsys):
    from privacy_approval_fixture import make_policy
    from sentinel_edge import live_preview

    policy = make_policy(tmp_path, monkeypatch, camera_ids=("cam1",))
    monkeypatch.setenv(
        "VIIL_TEST_PYAV_SUB",
        "rtsp://reader:PRIVATE@192.168.10.204:554/Streaming/Channels/102",
    )
    created = []
    cont = FakeContainer()
    install_fake_av(monkeypatch, cont, created)

    class FakeCV2:
        def __init__(self):
            self.shown = 0
            self.closed = 0
        def imshow(self, _title, img):
            assert img.shape == (24, 32, 3)
            self.shown += 1
        def waitKey(self, _delay):
            return -1
        def destroyWindow(self, _title):
            self.closed += 1
    cv2 = ModuleType("cv2")
    gui = FakeCV2()
    cv2.imshow, cv2.waitKey, cv2.destroyWindow = (
        gui.imshow, gui.waitKey, gui.destroyWindow,
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    assert live_preview.main([
        "--rtsp-env", "VIIL_TEST_PYAV_SUB",
        "--privacy-approval", str(policy),
        "--source-id", "cam1",
        "--confirm-authorized-camera", "--show-local-preview",
        "--decoder", "pyav", "--max-frames", "1",
    ]) == 0
    out = capsys.readouterr()
    assert "PRIVATE" not in out.out + out.err
    assert gui.shown == 1 and gui.closed == 1
    assert cont.closed and created
