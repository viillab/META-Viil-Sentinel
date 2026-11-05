"""Offline lifecycle checks for the standard (non-reconnecting) RTSP runner.

All devices, native modules and permission state are simulated. These tests
never connect to a camera, load a real model, or use an actual password.
"""
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from sentinel_edge import runner
from sentinel_edge.privacy_gate import PrivacyGateDenied


FAKE_SECRET = "invented-nonretry-password"
FAKE_URL = f"rtsp://reader:{FAKE_SECRET}@192.168.88.14:554/Streaming/Channels/102"


class FakeCapture:
    def __init__(self, state):
        self.state = state
        self.released = False
        self.is_open_calls = 0
        self.on_is_open = None
        self.on_release = None

    def isOpened(self):
        self.is_open_calls += 1
        if self.on_is_open is not None:
            self.on_is_open()
        return True

    def release(self):
        self.released = True
        if self.on_release is not None:
            self.on_release()
        # Native decoder failures must never be echoed to terminal output.
        raise RuntimeError("synthetic native close failed: " + FAKE_URL)


class FakePose:
    def __init__(self, state):
        self.state = state
        self.entered = False
        self.closed = False
        self.on_enter = None

    def __enter__(self):
        self.entered = True
        if self.on_enter is not None:
            self.on_enter()
        return self

    def __exit__(self, *_args):
        self.closed = True


@pytest.fixture
def rig(tmp_path, monkeypatch):
    state = NS(revoked=False, checks=0, inference_calls=0, opens=0)
    capture = FakeCapture(state)
    pose = FakePose(state)

    model = tmp_path / "synthetic.task"
    model.write_bytes(b"test-only path, never loaded as a real pose model")
    approval = tmp_path / "signed-test-fixture.json"
    monkeypatch.setenv("VIIL_TEST_NONRETRY_RTSP", FAKE_URL)

    class FakeApprovalGuard:
        def __init__(self, *_args, **_kwargs):
            pass

        def check(self):
            state.checks += 1
            if state.revoked:
                raise PrivacyGateDenied("synthetic revoked approval: " + FAKE_URL)

    cv2 = ModuleType("cv2")
    mp = ModuleType("mediapipe")

    def create_pose(*_args, **_kwargs):
        state.opens += 1
        return pose

    mp.tasks = NS(
        BaseOptions=lambda **kwargs: kwargs,
        vision=NS(
            RunningMode=NS(VIDEO="VIDEO"),
            PoseLandmarkerOptions=lambda **kwargs: kwargs,
            PoseLandmarker=NS(create_from_options=create_pose),
        ),
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    monkeypatch.setattr(runner, "LiveApprovalGuard", FakeApprovalGuard)
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_args: capture)

    def process(*_args, **_kwargs):
        state.inference_calls += 1
        return runner.StreamStats(1, 0, 0)

    monkeypatch.setattr(runner, "process_capture", process)
    argv = [
        "--source", "rtsp", "--rtsp-env", "VIIL_TEST_NONRETRY_RTSP",
        "--model", str(model), "--privacy-approval", str(approval),
        "--candidate-format", "v1", "--confirm-consent",
        "--source-id", "synthetic-zone-a", "--max-frames", "1",
    ]
    return NS(
        state=state, capture=capture, pose=pose, argv=argv,
        monkeypatch=monkeypatch,
    )


@pytest.mark.parametrize(("stage", "opened_calls", "model_creations", "inference_calls"), [
    ("after_native_open", 0, 0, 0),
    ("during_is_open", 1, 0, 0),
    ("during_model_enter", 1, 1, 0),
    ("during_native_close", 1, 1, 1),
])
def test_standard_rtsp_revocation_fails_closed_and_releases_every_resource(
    rig, capsys, stage, opened_calls, model_creations, inference_calls,
):
    if stage == "after_native_open":
        def open_revoking(*_args):
            rig.state.revoked = True
            return rig.capture
        rig.monkeypatch.setattr(runner, "open_rtsp_capture", open_revoking)
    elif stage == "during_is_open":
        rig.capture.on_is_open = lambda: setattr(rig.state, "revoked", True)
    elif stage == "during_model_enter":
        rig.pose.on_enter = lambda: setattr(rig.state, "revoked", True)
    else:
        rig.capture.on_release = lambda: setattr(rig.state, "revoked", True)

    assert runner.main(rig.argv) == 2
    assert rig.capture.released
    assert rig.capture.is_open_calls == opened_calls
    assert rig.state.opens == model_creations
    assert rig.state.inference_calls == inference_calls
    assert rig.pose.closed == (model_creations == 1)
    output = capsys.readouterr()
    assert output.out == ""
    assert "approval revoked/invalid" in output.err
    assert FAKE_URL not in output.err and FAKE_SECRET not in output.err
    assert rig.state.checks >= 1


def test_standard_rtsp_native_open_check_exception_redacted_and_capture_closed(
    rig, capsys,
):
    def explode():
        raise RuntimeError("synthetic isOpened exception " + FAKE_URL)

    rig.capture.on_is_open = explode
    with pytest.raises(SystemExit) as caught:
        runner.main(rig.argv)
    assert "details redacted" in str(caught.value)
    assert rig.capture.released
    assert rig.state.opens == 0
    output = capsys.readouterr()
    assert FAKE_URL not in output.out + output.err


def test_standard_rtsp_success_closes_native_handles_before_final_summary(
    rig, capsys,
):
    assert runner.main(rig.argv) == 0
    assert rig.capture.released
    assert rig.pose.closed
    assert rig.state.inference_calls == 1
    assert rig.state.checks >= 3
    output = capsys.readouterr()
    assert "Processed 1 frames" in output.err
    assert FAKE_URL not in output.out + output.err
