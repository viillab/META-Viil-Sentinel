"""Offline HTTP MJPEG -> MediaPipe Edge runner wiring with signed policy gates.

Every test uses a fake capture. NO Hikvision, socket, real image or credentials.
"""
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge import runner
from sentinel_edge import http_mjpeg_capture as mjpeg
from sentinel_edge.privacy_gate import PrivacyGateDenied

URL = "http://192.168.10.204:80/ISAPI/Streaming/channels/102/httpPreview"


def sample_args(model, *, extra=()):
    return [
        "--source", "http-mjpeg",
        "--http-mjpeg-env", "VIIL_TEST_EDGE_MJPEG",
        "--model", str(model), "--source-id", "approved-test-camera",
        "--candidate-format", "v1", "--confirm-consent",
        "--max-frames", "10", *extra,
    ]


def test_http_mjpeg_cli_requires_explicit_bounded_authorized_source(tmp_path):
    model = tmp_path / "mock.task"
    model.write_bytes(b"synthetic")
    args = runner.parse_args(sample_args(model))
    assert args.source == "http-mjpeg"
    assert args.max_frames == 10
    assert args.http_mjpeg_env == "VIIL_TEST_EDGE_MJPEG"
    for extra in [
        ["--rtsp-env", "VIIL_TEST_RTSP"],
        ["--rtsp-retries", "1"],
        ["--rtsp-fallback-env", "VIIL_TEST_RTSP"],
        ["--rtsp-decoder", "pyav"],
        ["--rtsp-session-seconds", "60"],
        ["--profile-rtsp"],
        ["--display"],
        ["--rtsp-allow-port", "80"],
        ["--trace-output", str(tmp_path / "capture.pose.jsonl")],
    ]:
        with pytest.raises(SystemExit):
            runner.parse_args(sample_args(model, extra=extra))
    for n in [0, 121]:
        with pytest.raises(SystemExit):
            runner.parse_args(sample_args(model, extra=["--max-frames", str(n)]))
    with pytest.raises(SystemExit):
        runner.parse_args([
            "--source", "http-mjpeg", "--model", str(model),
            "--candidate-format", "v1", "--confirm-consent", "--max-frames", "1",
        ])


def test_http_mjpeg_signed_gate_denies_before_decoder_import(
    tmp_path, monkeypatch,
):
    model = tmp_path / "mock.task"
    model.write_bytes(b"synthetic")
    monkeypatch.setenv("VIIL_TEST_EDGE_MJPEG", URL)
    opened = []
    monkeypatch.setattr(mjpeg, "open_http_mjpeg_capture", lambda *_: opened.append(1))
    with pytest.raises(SystemExit, match="signed privacy approval"):
        runner.main(sample_args(model))
    assert opened == []


class FakeCapture:
    def __init__(self):
        self.closed = False
    def isOpened(self):
        return True
    def release(self):
        self.closed = True


def build_fake_mediapipe(created):
    class Pose:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            created.append("closed")
    module = ModuleType("mediapipe")
    module.tasks = NS(
        BaseOptions=lambda **kw: kw,
        vision=NS(
            PoseLandmarkerOptions=lambda **kw: kw,
            RunningMode=NS(VIDEO="video"),
            PoseLandmarker=NS(create_from_options=lambda _: Pose()),
        ),
    )
    return module


def test_authorized_http_mjpeg_runs_bounded_pose_pipeline_without_recording(
    tmp_path, monkeypatch, capsys,
):
    model = tmp_path / "mock.task"
    model.write_bytes(b"synthetic")
    approval = make_policy(
        tmp_path, monkeypatch, camera_ids=("approved-test-camera",),
    )
    monkeypatch.setenv("VIIL_TEST_EDGE_MJPEG", URL)
    cap = FakeCapture()
    opened = []
    monkeypatch.setattr(
        mjpeg, "open_http_mjpeg_capture",
        lambda _cv2, url: (opened.append(url), cap)[1],
    )
    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
    closed = []
    monkeypatch.setitem(sys.modules, "mediapipe", build_fake_mediapipe(closed))
    original = runner.LiveApprovalGuard
    checks = []
    class Guard(original):
        def check(self):
            checks.append(1)
            super().check()
    monkeypatch.setattr(runner, "LiveApprovalGuard", Guard)
    def capture_handler(_cap, **opts):
        assert _cap is cap
        assert opts["webcam"] is True
        assert opts["fail_on_loss"] is True
        assert opts["max_duration_seconds"] == 60
        assert opts["max_frames"] == 10
        assert opts["display"] is False
        assert opts["trace_file"] is None
        assert opts["event_encoder"] is not None
        opts["privacy_check"]()
        return runner.StreamStats(10, 1, 0)
    monkeypatch.setattr(runner, "process_capture", capture_handler)
    assert runner.main(sample_args(model, extra=[
        "--privacy-approval", str(approval),
    ])) == 0
    output = capsys.readouterr()
    assert "Processed 10 frames" in output.err
    assert URL not in output.out + output.err
    assert opened == [URL]
    assert cap.closed
    assert closed == ["closed"]
    assert len(checks) >= 5


def test_http_mjpeg_revoked_policy_closes_capture_and_stops_without_events(
    tmp_path, monkeypatch, capsys,
):
    model = tmp_path / "mock.task"
    model.write_bytes(b"synthetic")
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("approved-test-camera",))
    monkeypatch.setenv("VIIL_TEST_EDGE_MJPEG", URL)
    cap = FakeCapture()
    monkeypatch.setattr(mjpeg, "open_http_mjpeg_capture", lambda *_: cap)
    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
    monkeypatch.setitem(sys.modules, "mediapipe", build_fake_mediapipe([]))
    checks = 0
    class Guard:
        def __init__(self, *_, **__):
            pass
        def check(self):
            nonlocal checks
            checks += 1
            if checks >= 3:
                raise PrivacyGateDenied("policy revoked private-data")
    monkeypatch.setattr(runner, "LiveApprovalGuard", Guard)
    monkeypatch.setattr(
        runner, "process_capture",
        lambda *_a, **_kw: pytest.fail("No frames may be processed after revocation"),
    )
    assert runner.main(sample_args(model, extra=[
        "--privacy-approval", str(approval),
    ])) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "private-data" not in output.err
    assert cap.closed


def test_invalid_http_url_refused_before_network_access(tmp_path, monkeypatch):
    model = tmp_path / "mock.task"
    model.write_bytes(b"synthetic")
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("approved-test-camera",))
    monkeypatch.setenv("VIIL_TEST_EDGE_MJPEG", "http://8.8.8.8/ISAPI/Streaming/channels/102/httpPreview")
    opened = []
    monkeypatch.setattr(mjpeg, "open_http_mjpeg_capture", lambda *_: opened.append(1))
    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
    monkeypatch.setitem(sys.modules, "mediapipe", build_fake_mediapipe([]))
    with pytest.raises(SystemExit, match="Invalid or unsafe HTTP MJPEG"):
        runner.main(sample_args(model, extra=[
            "--privacy-approval", str(approval),
        ]))
    assert opened == []
