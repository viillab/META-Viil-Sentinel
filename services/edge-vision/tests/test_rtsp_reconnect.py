"""Offline reconnect tests — no RTSP connections, cameras, images or secrets."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import runner
from sentinel_edge.rtsp_reconnect import (
    CameraStreamInterrupted,
    run_bounded_sessions,
    session_source_id,
)


def test_each_attempt_has_a_distinct_bounded_clock_namespace():
    base = "camera-" + "a" * 70
    first = session_source_id(base, "abcdef12", 1)
    second = session_source_id(base, "abcdef12", 2)
    assert first != second
    assert len(first) <= 80 and len(second) <= 80
    assert first.endswith("-s1-abcdef12")
    assert second.endswith("-s2-abcdef12")


def test_reconnect_resets_epoch_and_obeys_retry_bound():
    attempted = []
    delays = []
    messages = []

    def session(source):
        attempted.append(source)
        if len(attempted) == 1:
            raise CameraStreamInterrupted("rtsp://user:TEST_SECRET@camera")

    outcome = run_bounded_sessions(
        session, source_id="camera-one", retries=2, delay_seconds=0.25,
        pause=delays.append, status=messages.append, token="12345678",
    )
    assert outcome.completed is True
    assert outcome.attempts == 2
    assert attempted == ["camera-one-s1-12345678", "camera-one-s2-12345678"]
    assert delays == [0.25]
    assert "TEST_SECRET" not in str(messages)
    assert "no monitoring" in messages[0]


def test_retry_exhaustion_is_failure_without_unbounded_loop():
    attempts = []
    outcome = run_bounded_sessions(
        lambda s: (attempts.append(s), (_ for _ in ()).throw(CameraStreamInterrupted())),
        source_id="camera-one", retries=3, delay_seconds=0.25,
        pause=lambda _: None, token="abcdef12",
    )
    assert outcome.completed is False
    assert len(attempts) == 4


def test_non_capture_failure_is_never_retried():
    attempts = []
    def broken(source):
        attempts.append(source)
        raise ValueError("Model corrupted")
    with pytest.raises(ValueError, match="Model corrupted"):
        run_bounded_sessions(broken, source_id="camera", retries=3, token="abcdef12")
    assert len(attempts) == 1


@pytest.mark.parametrize("extra", [
    ["--rtsp-retries", "4"], ["--rtsp-retries", "-1"],
    ["--rtsp-retry-delay-ms", "1"], ["--rtsp-retry-delay-ms", "6000"],
    ["--rtsp-retries", "1", "--candidate-format", "legacy"],
    ["--rtsp-retries", "1", "--display"],
    ["--rtsp-retries", "1", "--early-motion-probe"],
    ["--profile-rtsp"],
])
def test_retry_flags_fail_closed(tmp_path: Path, extra):
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic")
    with pytest.raises(SystemExit):
        runner.parse_args([
            "--source", "rtsp", "--rtsp-env", "VIIL_TEST_RTSP",
            "--model", str(model), "--confirm-consent", *extra,
        ])


def test_retry_flags_rejected_for_local_webcam(tmp_path: Path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic")
    with pytest.raises(SystemExit):
        runner.parse_args([
            "--source", "0", "--model", str(model), "--rtsp-retries", "1",
        ])


def test_retry_mode_creates_fresh_native_tasks_releases_capture_and_renames_source(
    tmp_path: Path, monkeypatch, capsys,
):
    class FakeCap:
        def __init__(self, frames):
            self.remaining = frames
            self.released = False
        def isOpened(self):
            return True
        def get(self, _property):
            return 15.0
        def read(self):
            if self.remaining == 0:
                return False, None
            self.remaining -= 1
            return True, object()
        def release(self):
            self.released = True

    class Cv2:
        CAP_PROP_FPS = 5
        COLOR_BGR2RGB = 1
        @staticmethod
        def cvtColor(frame, _code):
            return frame

    tasks_created = []
    class FakePose:
        def __init__(self):
            self.timestamps = []
            self.closed = False
            tasks_created.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.closed = True
        def detect_for_video(self, _img, ts):
            self.timestamps.append(ts)
            return NS(pose_landmarks=[])

    class Mp:
        ImageFormat = NS(SRGB="rgb")
        tasks = NS(
            BaseOptions=lambda **k: k,
            vision=NS(
                PoseLandmarkerOptions=lambda **k: k,
                RunningMode=NS(VIDEO="video"),
                PoseLandmarker=NS(create_from_options=lambda _: FakePose()),
            ),
        )
        @staticmethod
        def Image(**kwargs):
            return kwargs

    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic")
    args = runner.parse_args([
        "--source", "rtsp", "--rtsp-env", "VIIL_TEST_RTSP",
        "--model", str(model), "--source-id", "camera-test",
        "--candidate-format", "v1", "--confirm-consent",
        "--rtsp-retries", "1", "--rtsp-retry-delay-ms", "250",
        "--max-frames", "3", "--profile-rtsp",
    ])
    caps = [FakeCap(2), FakeCap(3)]
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_: caps.pop(0))
    all_caps = []  # captured independently because the list is consumed
    original_process = runner.process_capture
    source_names = []
    def observed_process(cap, **kwargs):
        all_caps.append(cap)
        source_names.append(kwargs["source_id"])
        return original_process(cap, **kwargs)
    monkeypatch.setattr(runner, "process_capture", observed_process)
    assert runner._run_rtsp_retry_mode(args, Cv2, Mp, "rtsp://fake.local") == 0
    assert len(all_caps) == 2 and all(x.released for x in all_caps)
    assert len(tasks_created) == 2 and all(x.closed for x in tasks_created)
    assert source_names[0] != source_names[1]
    assert all(s.startswith("camera-test-s") for s in source_names)
    assert tasks_created[0].timestamps[0] == 0
    assert tasks_created[1].timestamps[0] == 0
    stderr = capsys.readouterr().err
    profile_lines = [line.removeprefix("RESEARCH_RTSP_PROFILE ")
                     for line in stderr.splitlines()
                     if line.startswith("RESEARCH_RTSP_PROFILE ")]
    profiles = [json.loads(line) for line in profile_lines]
    assert len(profiles) == 2
    assert profiles[0]["stream_interrupted"] is True
    assert profiles[0]["frames_processed"] == 2
    assert profiles[1]["stream_interrupted"] is False
    assert profiles[1]["frames_processed"] == 3
    assert all("camera-test" not in line and "fake.local" not in line
               for line in profile_lines)
    health_lines = [line.removeprefix("EDGE_POSE_COVERAGE_SUMMARY ")
                    for line in stderr.splitlines()
                    if line.startswith("EDGE_POSE_COVERAGE_SUMMARY ")]
    summaries = [json.loads(line) for line in health_lines]
    assert len(summaries) == 2
    assert [x["frames_observed"] for x in summaries] == [2, 3]
    assert [x["longest_no_pose_streak_frames"] for x in summaries] == [2, 3]
    assert all(x["condition"] == "unverified" for x in summaries)
    assert all("camera-test" not in line and "fake.local" not in line
               for line in health_lines)
