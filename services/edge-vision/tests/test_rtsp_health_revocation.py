"""RTSP health revocation simulations: no real camera, socket or credentials."""
import json
import sys
from types import ModuleType

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge import camera_health
from sentinel_edge.privacy_gate import PrivacyGateDenied


@pytest.fixture(autouse=True)
def fake_cv2_module(monkeypatch):
    """CI intentionally has no OpenCV extra: mock the module, never decode."""
    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))


class FakeCamera:
    def __init__(self, *, on_read=None, on_release=None, release_error=None):
        self.reads = 0
        self.released = False
        self.on_read = on_read
        self.on_release = on_release
        self.release_error = release_error

    def isOpened(self):
        return True

    def read(self):
        self.reads += 1
        if self.on_read is not None:
            self.on_read()
        return True, object()

    def release(self):
        self.released = True
        if self.on_release is not None:
            self.on_release()
        if self.release_error is not None:
            raise self.release_error


def test_recheck_before_and_after_every_decode_frame():
    camera = FakeCamera()
    checks = []

    def check():
        checks.append(camera.reads)

    report = camera_health.probe_capture(
        camera, sample_frames=3, privacy_check=check,
    )
    assert report == {
        "status": "readable", "frames_read": 3, "frames_requested": 3,
    }
    assert checks == [0, 0, 1, 1, 2, 2, 3]


@pytest.mark.parametrize(("fail_at", "reads"), [
    (1, 0),  # Before even checking whether the camera opened.
    (2, 0),  # Immediately before read.
    (3, 1),  # Immediately after native read; frame must not count.
])
def test_revoked_policy_raises_instead_of_reporting_partial_success(fail_at, reads):
    camera = FakeCamera()
    attempts = 0

    def check():
        nonlocal attempts
        attempts += 1
        if attempts == fail_at:
            raise PrivacyGateDenied("Approval revoked")

    with pytest.raises(PrivacyGateDenied):
        camera_health.probe_capture(
            camera, sample_frames=12, privacy_check=check,
        )
    assert camera.reads == reads


def _tamper(policy):
    body = json.loads(policy.read_text(encoding="utf-8"))
    body["notices_confirmed"] = False
    policy.write_text(json.dumps(body), encoding="utf-8")


def _args(tmp_path, monkeypatch, approval):
    # Fake RTSP URL exists only in an in-process test environment and is
    # never opened; do not use actual device credentials or addresses.
    monkeypatch.setenv(
        "VIIL_TEST_RTSP",
        "rtsp://fake_reader:synthetic_secret@192.168.88.10:554/Streaming/Channels/102",
    )
    return [
        "--rtsp-env", "VIIL_TEST_RTSP", "--source-id", "zone-a",
        "--privacy-approval", str(approval),
        "--frames", "12", "--confirm-authorized-camera",
    ]


def test_main_revoked_during_native_open_drops_all_output(
    tmp_path, monkeypatch, capsys,
):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    camera = FakeCamera()
    monkeypatch.setattr(
        camera_health, "open_rtsp_capture",
        lambda cv2, url: (_tamper(approval), camera)[-1],
    )
    with pytest.raises(SystemExit) as caught:
        camera_health.main(_args(tmp_path, monkeypatch, approval))
    assert caught.value.code == 2
    assert camera.released
    assert camera.reads == 0
    output = capsys.readouterr()
    assert output.out == ""
    assert "revoked during probe" in output.err
    assert "synthetic_secret" not in output.err


def test_main_revoked_during_decode_does_not_print_health_success(
    tmp_path, monkeypatch, capsys,
):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    camera = FakeCamera(on_read=lambda: _tamper(approval))
    monkeypatch.setattr(
        camera_health, "open_rtsp_capture", lambda cv2, url: camera,
    )
    with pytest.raises(SystemExit) as caught:
        camera_health.main(_args(tmp_path, monkeypatch, approval))
    assert caught.value.code == 2
    assert camera.reads == 1
    assert camera.released
    output = capsys.readouterr()
    assert output.out == ""
    assert "revoked during probe" in output.err
    assert "synthetic_secret" not in output.err


def test_revoked_during_native_close_never_claims_success(
    tmp_path, monkeypatch, capsys,
):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    camera = FakeCamera(on_release=lambda: _tamper(approval))
    monkeypatch.setattr(
        camera_health, "open_rtsp_capture", lambda cv2, url: camera,
    )
    with pytest.raises(SystemExit) as caught:
        camera_health.main(_args(tmp_path, monkeypatch, approval))
    assert caught.value.code == 2
    assert camera.reads == 12
    assert camera.released
    output = capsys.readouterr()
    assert output.out == ""
    assert "revoked during probe" in output.err
    assert "synthetic_secret" not in output.err


def test_native_release_exception_does_not_leak_rtsp_credentials(
    tmp_path, monkeypatch, capsys,
):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    camera = FakeCamera(release_error=RuntimeError("synthetic_secret"))
    monkeypatch.setattr(
        camera_health, "open_rtsp_capture", lambda cv2, url: camera,
    )
    result = camera_health.main(_args(tmp_path, monkeypatch, approval))
    assert result == 0
    assert camera.released
    output = capsys.readouterr()
    assert json.loads(output.out)["frames_read"] == 12
    assert "synthetic_secret" not in output.out + output.err
