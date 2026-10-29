"""PyAV decoder wiring for the signed, bounded RTSP Edge inference pipeline.

Pure synthetic cameras and policy checks; never open a device or RTSP socket.
"""
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from sentinel_edge import runner
from sentinel_edge import pyav_capture
from sentinel_edge.privacy_gate import PrivacyGateDenied


FAKE_SECRET = "UNREAL_TEST_PASSWORD_41"
SUB = f"rtsp://reader:{FAKE_SECRET}@192.168.88.14:554/Streaming/Channels/102"
MAIN = f"rtsp://reader:{FAKE_SECRET}@192.168.88.14:554/Streaming/Channels/101"


class FakeCap:
    def __init__(self):
        self.released = False
    def isOpened(self):
        return True
    def release(self):
        self.released = True


class FakePose:
    def __init__(self):
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.closed = True


def fake_mp(created):
    def pose_create(_options):
        pose = FakePose()
        created.append(pose)
        return pose
    return NS(tasks=NS(
        BaseOptions=lambda **kw: kw,
        vision=NS(
            PoseLandmarkerOptions=lambda **kw: kw,
            RunningMode=NS(VIDEO="video"),
            PoseLandmarker=NS(create_from_options=pose_create),
        ),
    ))


def make_args(tmp_path, *, extra=()):
    model = tmp_path / "fake.task"
    model.write_bytes(b"synthetic model for tests only")
    return runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_SYNTHETIC_SUB",
        "--model", str(model), "--source-id", "synthetic-zone",
        "--candidate-format", "v1", "--confirm-consent",
        "--rtsp-retries", "1", "--rtsp-fallback-env", "VIIL_SYNTHETIC_MAIN",
        "--rtsp-decoder", "pyav", "--max-frames", "2",
        "--rtsp-session-seconds", "30",
        "--rtsp-retry-delay-ms", "250", *extra,
    ])


def test_pyav_decoder_opt_in_restricted_to_rtsp(tmp_path):
    model = tmp_path / "fake.task"
    model.write_bytes(b"x")
    args = runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_SYNTHETIC_SUB",
        "--model", str(model), "--candidate-format", "v1",
        "--confirm-consent", "--rtsp-decoder", "pyav",
    ])
    assert args.rtsp_decoder == "pyav"
    with pytest.raises(SystemExit):
        runner.parse_args([
            "--source", "0", "--model", str(model),
            "--candidate-format", "v1", "--confirm-consent",
            "--rtsp-decoder", "pyav",
        ])
    assert runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_SYNTHETIC_SUB",
        "--model", str(model), "--candidate-format", "v1",
        "--confirm-consent",
    ]).rtsp_decoder == "opencv"


def test_pyav_retry_switches_same_camera_and_closes_both_resources(
    tmp_path, monkeypatch, capsys,
):
    args = make_args(tmp_path)
    opened = []
    captures = []
    poses = []
    policy_checks = []
    def policy():
        policy_checks.append("check")
    def pyav_open(_cv2, source):
        policy()
        opened.append(source)
        cap = FakeCap()
        captures.append(cap)
        return cap
    monkeypatch.setattr(pyav_capture, "open_pyav_capture", pyav_open)
    monkeypatch.setattr(
        runner, "open_rtsp_capture",
        lambda *_: pytest.fail("OpenCV must not be used in PyAV Edge mode"),
    )
    def process(_cap, **kwargs):
        assert kwargs["privacy_check"] is policy
        assert kwargs["fail_on_loss"] is True
        assert kwargs["webcam"] is True
        if len(opened) == 1:
            raise runner.CameraStreamInterrupted("synthetic codec outage")
        return runner.StreamStats(2, 2, 0)
    monkeypatch.setattr(runner, "process_capture", process)
    result = runner._run_rtsp_retry_mode(
        args, NS(), fake_mp(poses), SUB,
        fallback_source=MAIN, privacy_check=policy,
    )
    assert result == 0
    assert opened == [SUB, MAIN]
    assert len(policy_checks) >= 6
    assert all(cap.released for cap in captures)
    assert len(poses) == 2 and all(pose.closed for pose in poses)
    output = capsys.readouterr()
    assert FAKE_SECRET not in output.out + output.err
    assert "unconfirmed candidates" in output.err


def test_pyav_revoked_permission_never_opens_fallback(
    tmp_path, monkeypatch, capsys,
):
    args = make_args(tmp_path)
    opened = []
    captures = []
    checks = 0
    def policy():
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise PrivacyGateDenied("revoked " + FAKE_SECRET)
    def open_pyav(_cv2, source):
        opened.append(source)
        cap = FakeCap()
        captures.append(cap)
        return cap
    monkeypatch.setattr(pyav_capture, "open_pyav_capture", open_pyav)
    with pytest.raises(PrivacyGateDenied):
        runner._run_rtsp_retry_mode(
            args, NS(), fake_mp([]), SUB,
            fallback_source=MAIN, privacy_check=policy,
        )
    assert opened == [SUB]
    assert len(captures) == 1 and captures[0].released
    assert FAKE_SECRET not in capsys.readouterr().err


def test_pyav_native_error_redacted_and_no_replay_on_missing_approval(
    tmp_path, monkeypatch, capsys,
):
    args = make_args(tmp_path)
    opened = []
    def fail_open(_cv2, url):
        opened.append(url)
        raise RuntimeError("secret url " + FAKE_SECRET)
    monkeypatch.setattr(pyav_capture, "open_pyav_capture", fail_open)
    result = runner._run_rtsp_retry_mode(
        args, NS(), fake_mp([]), SUB,
        fallback_source=MAIN, privacy_check=lambda: None,
    )
    assert result == 2
    assert opened == [SUB, MAIN]
    assert FAKE_SECRET not in capsys.readouterr().out + capsys.readouterr().err

    model = tmp_path / "fake.task"
    with pytest.raises(SystemExit, match="signed privacy approval"):
        runner.main([
            "--source", "rtsp", "--rtsp-env", "VIIL_SYNTHETIC_SUB",
            "--model", str(model), "--candidate-format", "v1",
            "--confirm-consent", "--rtsp-decoder", "pyav",
        ])


def test_standard_nonretry_pyav_closes_cap_and_rechecks_approval(
    tmp_path, monkeypatch, capsys,
):
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic")
    monkeypatch.setenv("VIIL_TEST_EDGE_PYAV", SUB)
    state = NS(checks=0, pose_creations=0, process_calls=0)
    cap = FakeCap()
    poses = []
    class ApprovalGuard:
        def __init__(self, *_a, **_kw):
            pass
        def check(self):
            state.checks += 1
    class MP(ModuleType):
        pass
    mp = MP("mediapipe")
    mp.tasks = fake_mp(poses).tasks
    cv2 = ModuleType("cv2")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    monkeypatch.setattr(runner, "LiveApprovalGuard", ApprovalGuard)
    opened = []
    def opener(_cv2, url):
        opened.append(url)
        return cap
    monkeypatch.setattr(pyav_capture, "open_pyav_capture", opener)
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_: pytest.fail(
        "unexpected OpenCV decoder",
    ))
    def process(_cap, **kwargs):
        state.process_calls += 1
        assert kwargs["privacy_check"] is not None
        kwargs["privacy_check"]()
        return runner.StreamStats(2, 0, 0)
    monkeypatch.setattr(runner, "process_capture", process)
    result = runner.main([
        "--source", "rtsp", "--rtsp-env", "VIIL_TEST_EDGE_PYAV",
        "--model", str(model), "--privacy-approval", str(tmp_path / "fake.json"),
        "--candidate-format", "v1", "--confirm-consent",
        "--rtsp-decoder", "pyav", "--max-frames", "2",
    ])
    assert result == 0
    assert opened == [SUB]
    assert cap.released and all(p.closed for p in poses)
    assert state.checks >= 4
    assert state.process_calls == 1
    output = capsys.readouterr()
    assert FAKE_SECRET not in output.out + output.err
