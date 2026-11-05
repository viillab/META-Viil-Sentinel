"""Bounded RTSP endurance tests: fake captures and synthetic clocks only."""
from pathlib import Path
from types import SimpleNamespace as NS
import math

import pytest

from sentinel_edge import runner


class FakeCapture:
    def __init__(self):
        self.reads = 0

    def get(self, _):
        return 15

    def read(self):
        self.reads += 1
        return True, self.reads


class FakeCv2:
    CAP_PROP_FPS = 5
    COLOR_BGR2RGB = 1

    @staticmethod
    def cvtColor(frame, _):
        return frame


class FakeMp:
    ImageFormat = NS(SRGB="rgb")

    @staticmethod
    def Image(*, image_format, data):
        return data


class NoPose:
    def __init__(self):
        self.timestamps = []

    def detect_for_video(self, frame, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        return NS(pose_landmarks=[])


class FakeClock:
    def __init__(self, ticks):
        self.it = iter(ticks)

    def __call__(self):
        return next(self.it)


def test_time_bound_stops_before_next_capture_read():
    capture, detector = FakeCapture(), NoPose()
    stats = runner.process_capture(
        capture, cv2=FakeCv2, mp=FakeMp, landmarker=detector,
        webcam=True, source_id="test", max_duration_seconds=1,
        clock=FakeClock([0, .1, .2, .3, .4, 1.1]),
    )
    assert stats.frames_processed == 1
    assert capture.reads == 1
    assert detector.timestamps == [300]


def test_blocking_read_crossing_deadline_is_not_sent_for_inference():
    capture, detector = FakeCapture(), NoPose()
    stats = runner.process_capture(
        capture, cv2=FakeCv2, mp=FakeMp, landmarker=detector,
        webcam=True, source_id="test", max_duration_seconds=1,
        clock=FakeClock([0, .1, 1.2]),
    )
    assert stats.frames_processed == 0
    assert capture.reads == 1
    assert detector.timestamps == []


@pytest.mark.parametrize("invalid", [True, None, -1, float("inf"), math.nan, 3601])
def test_invalid_duration_never_opens_capture(invalid):
    with pytest.raises(ValueError):
        runner.process_capture(
            FakeCapture(), cv2=FakeCv2, mp=FakeMp, landmarker=NoPose(),
            webcam=True, source_id="test", max_duration_seconds=invalid,
        )


@pytest.mark.parametrize("extras", [
    ["--rtsp-session-seconds", "-1"],
    ["--rtsp-session-seconds", "3601"],
    ["--rtsp-session-seconds", "1800"],
])
def test_session_seconds_invalid_without_valid_retry_mode(tmp_path: Path, extras):
    model = tmp_path / "test.task"
    model.write_bytes(b"synthetic")
    base = ["--source", "rtsp", "--rtsp-env", "VIIL_TEST_RTSP",
            "--model", str(model)]
    with pytest.raises(SystemExit):
        runner.parse_args(base + extras)


def test_duration_accepted_with_rtsp_retries_and_consent(tmp_path: Path):
    model = tmp_path / "test.task"
    model.write_bytes(b"synthetic")
    args = runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_TEST_RTSP",
        "--model", str(model), "--rtsp-retries", "1",
        "--candidate-format", "v1", "--confirm-consent",
        "--rtsp-session-seconds", "1800", "--profile-rtsp",
    ])
    assert args.rtsp_session_seconds == 1800


def test_zero_processed_frames_is_not_reported_as_healthy(monkeypatch, tmp_path: Path):
    model = tmp_path / "test.task"
    model.write_bytes(b"synthetic")
    args = runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_TEST_RTSP",
        "--model", str(model), "--rtsp-retries", "1",
        "--candidate-format", "v1", "--confirm-consent",
        "--rtsp-session-seconds", "1", "--profile-rtsp",
    ])

    captures = []
    class Cap:
        def __init__(self):
            self.released = False
            captures.append(self)

        def isOpened(self):
            return True

        def release(self):
            self.released = True

    class Pose:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class FakeVision:
        RunningMode = NS(VIDEO=1)
        PoseLandmarkerOptions = staticmethod(lambda **kw: kw)
        PoseLandmarker = NS(create_from_options=lambda _: Pose())

    fake_mp = NS(tasks=NS(BaseOptions=lambda **kw: kw, vision=FakeVision))
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_: Cap())
    monkeypatch.setattr(
        runner, "process_capture",
        lambda *_a, **_kw: runner.StreamStats(0, 0, 0),
    )
    # Two attempts at most; no successful frames must not yield success.
    assert runner._run_rtsp_retry_mode(args, NS(), fake_mp, "rtsp://fake.local") == 2
    assert len(captures) == 2
    assert all(x.released for x in captures)
