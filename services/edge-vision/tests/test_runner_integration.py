"""End-to-end fake video/pose tests never touch a camera or model."""
from io import StringIO
import json
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.handoff import to_envelope
from sentinel_edge.runner import process_capture, timestamp_for_frame


class FakeCapture:
    def __init__(self, frames, *, fps=10.0):
        self.frames = list(frames)
        self.index = 0
        self.fps = fps

    def get(self, _):
        return self.fps

    def read(self):
        if self.index >= len(self.frames):
            return False, None
        self.index += 1
        return True, self.index


class FakeCv2:
    CAP_PROP_FPS = 5
    COLOR_BGR2RGB = 1

    @staticmethod
    def cvtColor(frame, _):
        return frame

    @staticmethod
    def imshow(*_):
        raise AssertionError("Display must remain off")

    @staticmethod
    def waitKey(*_):
        raise AssertionError("Display must remain off")


class FakeMp:
    ImageFormat = NS(SRGB="RGB")

    @staticmethod
    def Image(*, image_format, data):
        assert image_format == "RGB"
        return data


class FakeLandmarker:
    def __init__(self, *, corrupt_index=None):
        self.count = 0
        self.timestamps = []
        self.corrupt_index = corrupt_index

    def detect_for_video(self, image, timestamp):
        self.timestamps.append(timestamp)
        idx = self.count
        self.count += 1
        if idx == self.corrupt_index:
            return NS(pose_landmarks=[])
        horiz = idx >= 3
        sx, sy, hx, hy = (0.23, 0.78, 0.57, 0.78) if horiz else (0.5, 0.25, 0.5, 0.53)
        landmarks = [NS(x=0.5, y=0.5, visibility=0.98, presence=0.98)
                     for _ in range(33)]
        for i, x, y in (
            (11, sx - 0.045, sy), (12, sx + 0.045, sy),
            (23, hx - 0.05, hy), (24, hx + 0.05, hy),
        ):
            landmarks[i] = NS(x=x, y=y, visibility=0.98, presence=0.98)
        return NS(pose_landmarks=[landmarks])


def run_fake(*, frames=9, corrupt=None, max_frames=0):
    sink = StringIO()
    trace = StringIO()
    cap = FakeCapture(range(frames))
    model = FakeLandmarker(corrupt_index=corrupt)
    stats = process_capture(
        cap, cv2=FakeCv2, mp=FakeMp, landmarker=model,
        webcam=False, source_id="fake-test", output=sink,
        trace_file=trace, max_frames=max_frames,
    )
    return stats, sink.getvalue(), trace.getvalue(), model.timestamps


def test_fake_video_generates_metadata_event_without_image_export():
    stats, events, trace, stamps = run_fake()
    assert stats.frames_processed == 9
    assert stats.invalid_pose_frames == 0
    assert stats.candidate_events == 1
    payload = json.loads(events)
    assert payload["type"] == "FALL_CANDIDATE"
    assert payload["source_id"] == "fake-test"
    assert payload["simulated"] is False  # Fake input only in tests, not runner metadata
    assert payload["evidence_refs"] == []
    assert stamps == list(range(0, 900, 100))
    lines = [json.loads(line) for line in trace.splitlines()]
    assert len(lines) == 9
    assert set(lines[0]) == {"timestamp_ms", "landmarks"}
    assert set(lines[0]["landmarks"]) == {"11", "12", "23", "24"}
    assert "face" not in trace.lower()


def test_missing_pose_resets_candidate_and_does_not_fabricate_event():
    stats, events, trace, _ = run_fake(frames=8, corrupt=5)
    assert stats.invalid_pose_frames == 1
    assert stats.candidate_events == 0
    assert events == ""
    assert '"landmarks":{}' in trace


def test_frame_limit_is_enforced_without_inference_after_limit():
    stats, events, trace, stamps = run_fake(max_frames=4)
    assert stats.frames_processed == 4
    assert len(trace.splitlines()) == len(stamps) == 4
    assert events == ""


def test_invalid_source_parameters_rejected():
    cap = FakeCapture([1, 2])
    with pytest.raises(ValueError):
        process_capture(
            cap, cv2=FakeCv2, mp=FakeMp, landmarker=FakeLandmarker(),
            webcam=False, source_id="test", max_frames=-1,
        )


def test_timestamp_fps_validation():
    with pytest.raises(ValueError):
        timestamp_for_frame(3, float("nan"), 1)
    with pytest.raises(ValueError):
        timestamp_for_frame(3, float("inf"), 1)


def test_fake_local_video_can_emit_versioned_unverified_contract():
    sink = StringIO()
    stats = process_capture(
        FakeCapture(range(9)), cv2=FakeCv2, mp=FakeMp,
        landmarker=FakeLandmarker(), webcam=False,
        source_id="fake-test", output=sink,
        event_encoder=lambda event: to_envelope(
            event, input_provenance="consented_staged_video",
            model_sha256="a" * 64,
        ).to_dict(),
    )
    assert stats.candidate_events == 1
    envelope = json.loads(sink.getvalue())
    assert envelope["schema_version"] == "viil.edge.candidate.v1"
    assert envelope["source_timestamp_ms"] == 800
    assert envelope["source_id"] == "fake-test"
    assert envelope["model_sha256"] == "a" * 64
    assert envelope["simulated"] is False
    assert envelope["confirmed_fall"] is False
    assert envelope["human_review_required"] is True
    assert envelope["evidence_refs"] == []
    assert "evidence_notes" not in envelope
