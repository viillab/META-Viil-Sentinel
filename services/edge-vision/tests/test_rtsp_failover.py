"""Offline Hikvision same-camera stream failover tests; no RTSP or real model."""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import runner
from sentinel_edge.privacy_gate import PrivacyGateDenied
from sentinel_edge.rtsp_failover import (
    ApprovedStreamPair,
    resolve_hikvision_stream_pair,
    validate_same_camera_streams,
)


SECRET = "invented_TEST_credential"
SUB = f"rtsp://readonly:{SECRET}@192.168.10.204:554/Streaming/Channels/102"
MAIN = f"rtsp://readonly:{SECRET}@192.168.10.204:554/Streaming/Channels/101"


def test_valid_same_camera_pair_alternates_with_bounded_attempts():
    pair = resolve_hikvision_stream_pair(
        "VIIL_LAN_SUB", "VIIL_LAN_MAIN",
        environment={"VIIL_LAN_SUB": SUB, "VIIL_LAN_MAIN": MAIN},
    )
    assert isinstance(pair, ApprovedStreamPair)
    assert SECRET not in repr(pair)
    assert [pair.for_attempt(i) for i in range(4)] == [SUB, MAIN, SUB, MAIN]


@pytest.mark.parametrize("first,second", [
    (SUB, SUB),
    (SUB, MAIN.replace("192.168.10.204", "192.168.10.205")),
    (SUB, MAIN.replace("Channels/101", "Channels/201")),
    (SUB, MAIN.replace("readonly", "admin")),
    (SUB, MAIN.replace(SECRET, "different_pass")),
    (SUB, MAIN.replace("554", "8554")),
    (SUB, MAIN + "?altered=1"),
    (SUB, MAIN.replace("Channels/101", "Other/101")),
    (SUB, "rtsp://test.example.com/Streaming/Channels/101"),
    (SUB, "rtsp://127.0.0.1:554/Streaming/Channels/101"),
])
def test_rejects_mixed_or_unsafe_fallback_redacted(first, second):
    with pytest.raises(ValueError) as exc:
        resolve_hikvision_stream_pair(
            "VIIL_PRIMARY", "VIIL_SECONDARY",
            environment={"VIIL_PRIMARY": first, "VIIL_SECONDARY": second},
        )
    assert SECRET not in str(exc.value)
    assert "192.168" not in str(exc.value)


@pytest.mark.parametrize("index", [-1, 1.5, "1", True, None])
def test_rejects_invalid_attempt_index(index):
    with pytest.raises(ValueError):
        ApprovedStreamPair(SUB, MAIN).for_attempt(index)


def test_rejects_duplicate_or_missing_env():
    with pytest.raises(ValueError):
        resolve_hikvision_stream_pair("VIIL_A", "VIIL_A", environment={"VIIL_A": SUB})
    with pytest.raises(ValueError):
        resolve_hikvision_stream_pair("VIIL_A", "VIIL_B", environment={"VIIL_A": SUB})


def test_pure_pair_validation_does_not_open_network():
    assert validate_same_camera_streams(SUB, MAIN) is None


def test_non_default_port_requires_explicit_allowlist():
    sub, main = SUB.replace("554", "9554"), MAIN.replace("554", "9554")
    env = {"VIIL_A": sub, "VIIL_B": main}
    with pytest.raises(ValueError):
        resolve_hikvision_stream_pair("VIIL_A", "VIIL_B", environment=env)
    assert resolve_hikvision_stream_pair(
        "VIIL_A", "VIIL_B", environment=env, extra_port=9554,
    ).fallback == main


def args(tmp_path: Path, *, retries: int = 1):
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic-fake-model")
    return NS(
        model=model, profile_rtsp=False, max_frames=1,
        rtsp_session_seconds=0, rtsp_retries=retries,
        rtsp_retry_delay_ms=250, source_id="test-camera",
    )


class Capture:
    def __init__(self):
        self.released = False

    def isOpened(self):
        return True

    def release(self):
        self.released = True


class FakePose:
    def __init__(self, created):
        self.closed = False
        created.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def detect_for_video(self, image, timestamp):
        # Legitimate synthetic pose-missing response, not a fall candidate.
        return NS(pose_landmarks=[])


def fake_mp(created):
    return NS(tasks=NS(
        BaseOptions=lambda **kw: kw,
        vision=NS(
            PoseLandmarkerOptions=lambda **kw: kw,
            RunningMode=NS(VIDEO="video"),
            PoseLandmarker=NS(
                create_from_options=lambda _: FakePose(created),
            ),
        ),
    ))


def test_runtime_first_stream_fails_then_fallback_succeeds(
    tmp_path, monkeypatch, capsys,
):
    opened = []
    caps = []
    poses = []

    def open_capture(_cv2, source):
        opened.append(source)
        cap = Capture()
        caps.append(cap)
        return cap

    def decode(cap, **kw):
        assert kw["privacy_check"] is not None
        if len(opened) == 1:
            raise runner.CameraStreamInterrupted("unavailable")
        return runner.StreamStats(1, 1, 0)

    monkeypatch.setattr(runner, "open_rtsp_capture", open_capture)
    monkeypatch.setattr(runner, "process_capture", decode)
    result = runner._run_rtsp_retry_mode(
        args(tmp_path), NS(), fake_mp(poses), SUB,
        fallback_source=MAIN, privacy_check=lambda: None,
    )
    assert result == 0
    assert opened == [SUB, MAIN]
    assert all(cap.released for cap in caps)
    assert len(poses) == 2 and all(pose.closed for pose in poses)
    logs = capsys.readouterr()
    assert SECRET not in logs.err + logs.out
    assert "no monitoring" in logs.err


def test_native_corrupt_rtsp_frame_retries_with_real_processor_and_fresh_resources(
    tmp_path, monkeypatch, capsys,
):
    """Do not mock process_capture: malformed RTSP frame must trigger fallback."""
    opened = []
    captures = []
    poses = []

    class FrameCapture(Capture):
        def get(self, _key):
            return 10.0

        def read(self):
            if len(opened) == 1:
                # FFmpeg/OpenCV may report ok=True yet return invalid bytes.
                return True, object()
            return True, NS(shape=(24, 32, 3), size=24 * 32 * 3, dtype="uint8")

    def fake_open(_cv2, source):
        opened.append(source)
        cap = FrameCapture()
        captures.append(cap)
        return cap

    cv2 = NS(CAP_PROP_FPS=5, COLOR_BGR2RGB=1, cvtColor=lambda frame, _: frame)
    pose_mp = fake_mp(poses)
    mp = NS(
        tasks=pose_mp.tasks,
        ImageFormat=NS(SRGB="RGB"),
        Image=lambda **kwargs: kwargs["data"],
    )
    monkeypatch.setattr(runner, "open_rtsp_capture", fake_open)

    outcome = runner._run_rtsp_retry_mode(
        args(tmp_path), cv2, mp, SUB,
        fallback_source=MAIN, privacy_check=lambda: None,
    )
    assert outcome == 0
    assert opened == [SUB, MAIN]
    assert len(captures) == 2 and all(cap.released for cap in captures)
    assert len(poses) == 2 and all(pose.closed for pose in poses)
    logs = capsys.readouterr()
    assert logs.out == ""
    assert "no monitoring" in logs.err
    assert SECRET not in logs.err


def test_exhausted_fallback_exits_nonzero_with_no_events(
    tmp_path, monkeypatch, capsys,
):
    opened = []
    caps = []
    def open_capture(_cv2, source):
        opened.append(source)
        cap = Capture()
        caps.append(cap)
        return cap
    monkeypatch.setattr(runner, "open_rtsp_capture", open_capture)
    monkeypatch.setattr(runner, "process_capture", lambda *_a, **_kw: (
        (_ for _ in ()).throw(runner.CameraStreamInterrupted("interrupted"))
    ))
    result = runner._run_rtsp_retry_mode(
        args(tmp_path, retries=3), NS(), fake_mp([]), SUB,
        fallback_source=MAIN, privacy_check=lambda: None,
    )
    assert result == 2
    assert opened == [SUB, MAIN, SUB, MAIN]
    assert all(cap.released for cap in caps)
    logs = capsys.readouterr()
    assert logs.out == ""
    assert SECRET not in logs.err
    assert "no monitoring" in logs.err


def test_privacy_revocation_prevents_fallback(
    tmp_path, monkeypatch, capsys,
):
    opened = []
    def open_capture(_cv2, source):
        opened.append(source)
        return Capture()
    monkeypatch.setattr(runner, "open_rtsp_capture", open_capture)
    def deny():
        raise PrivacyGateDenied("signed consent revoked: " + SECRET)
    with pytest.raises(PrivacyGateDenied):
        runner._run_rtsp_retry_mode(
            args(tmp_path, retries=3), NS(), fake_mp([]), SUB,
            fallback_source=MAIN, privacy_check=deny,
        )
    assert not opened
    assert SECRET not in capsys.readouterr().err


@pytest.mark.parametrize("extra", [
    ["--rtsp-fallback-env", "VIIL_ALT"],
    ["--rtsp-retries", "1", "--rtsp-fallback-env", "VIIL_PRIMARY"],
    ["--rtsp-retries", "1", "--rtsp-fallback-env", "UNSAFE_ALT"],
    ["--rtsp-retries", "1", "--rtsp-fallback-env", "VIIL-ALT"],
])
def test_cli_requires_safe_and_retrying_fallback(tmp_path, extra):
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    with pytest.raises(SystemExit):
        runner.parse_args([
            "--source", "rtsp", "--rtsp-env", "VIIL_PRIMARY",
            "--model", str(model), "--confirm-consent", "--candidate-format", "v1",
            *extra,
        ])


def test_cli_accepts_valid_fallback_name(tmp_path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    result = runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_PRIMARY",
        "--model", str(model), "--confirm-consent", "--candidate-format", "v1",
        "--rtsp-retries", "1", "--rtsp-fallback-env", "VIIL_ALT",
    ])
    assert result.rtsp_fallback_env == "VIIL_ALT"
