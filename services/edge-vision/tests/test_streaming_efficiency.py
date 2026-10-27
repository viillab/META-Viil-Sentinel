"""Streaming evaluation decisions must match the original buffered path."""
from io import StringIO
from dataclasses import asdict

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.evaluation import StreamingClipAccumulator, evaluate_clip_frames
from sentinel_edge.runner import process_capture
from test_runner_integration import FakeCapture, FakeCv2, FakeLandmarker, FakeMp


def pose(t, prone=False):
    sx, sy, hx, hy = (0.23, .78, .57, .78) if prone else (.5, .25, .5, .53)
    return PoseFrame(timestamp_ms=t, source_id="test", landmarks={
        11: Landmark(sx-.045, sy, .98), 12: Landmark(sx+.045, sy, .98),
        23: Landmark(hx-.05, hy, .98), 24: Landmark(hx+.05, hy, .98),
    })


def test_matching_post_onset_event():
    seq = [pose(t, prone=i >= 3) for i, t in
           enumerate((0, 100, 200, 300, 500, 700, 850))]
    expected = evaluate_clip_frames(seq, clip_id="test", expected_fall=True, onset_ms=300)
    accumulator, detector = StreamingClipAccumulator(), TemporalFallDetector()
    for frame in seq:
        accumulator.on_frame(frame)
        if (event := detector.process(frame)) is not None:
            accumulator.on_event(event)
    assert asdict(accumulator.finish(clip_id="test", expected_fall=True, onset_ms=300)) == asdict(
        expected
    )
    assert len(accumulator.times) == 1


def test_runner_callbacks_use_existing_detector_events():
    accumulator = StreamingClipAccumulator()
    stats = process_capture(
        FakeCapture(range(9)), cv2=FakeCv2, mp=FakeMp,
        landmarker=FakeLandmarker(), webcam=False, source_id="fake-test",
        output=StringIO(), on_frame=accumulator.on_frame,
        on_event=accumulator.on_event, detector=TemporalFallDetector(),
    )
    outcome = accumulator.finish(clip_id="fake-test", expected_fall=True)
    assert stats.frames_processed == outcome.analyzed_frames == 9
    assert stats.candidate_events == outcome.candidate_count == 1
    assert outcome.first_candidate_ms == 800
    assert outcome.observed_pose_frames == 9


def test_storage_is_not_proportional_to_frames():
    accumulator = StreamingClipAccumulator()
    for i in range(4000):
        accumulator.on_frame(PoseFrame(
            timestamp_ms=i*100, source_id="negative", landmarks={}
        ))
    result = accumulator.finish(clip_id="negative", expected_fall=False)
    assert result.analyzed_frames == 4000
    assert result.predicted_fall is False
    assert accumulator.times == []


def test_missing_pose_keeps_same_false_negative_result():
    seq = [pose(t, prone=i >= 3) for i, t in
           enumerate((0, 100, 200, 300, 500, 700, 850))]
    seq[4] = PoseFrame(timestamp_ms=500, source_id="test", landmarks={})
    expected = evaluate_clip_frames(seq, clip_id="gap", expected_fall=True, onset_ms=300)
    accumulator, detector = StreamingClipAccumulator(), TemporalFallDetector()
    for frame in seq:
        accumulator.on_frame(frame)
        if (event := detector.process(frame)) is not None:
            accumulator.on_event(event)
    assert asdict(accumulator.finish(clip_id="gap", expected_fall=True, onset_ms=300)) == asdict(
        expected
    )
