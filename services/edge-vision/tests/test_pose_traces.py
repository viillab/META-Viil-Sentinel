import json

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.pose_traces import (
    TraceFormatError,
    frame_to_trace_record,
    read_pose_trace,
)


def test_trace_round_trip_with_four_torso_landmarks(tmp_path):
    frame = PoseFrame(80, {
        11: Landmark(0.4, 0.2, 0.9),
        12: Landmark(0.6, 0.2, 0.9),
        23: Landmark(0.45, 0.55, 0.99),
        24: Landmark(0.55, 0.55, 0.99),
        0: Landmark(0.1, 0.1, 0.5),  # face points must never be retained
    })
    line = frame_to_trace_record(frame)
    assert set(json.loads(line)["landmarks"]) == {"11", "12", "23", "24"}
    file = tmp_path / "clip.jsonl"
    file.write_text(line + "\n", encoding="utf-8")
    loaded = list(read_pose_trace(file, source_id="anonymous-01"))
    assert loaded[0].source_id == "anonymous-01"
    assert loaded[0].timestamp_ms == 80
    assert loaded[0].landmarks == {key: frame.landmarks[key] for key in (11, 12, 23, 24)}


@pytest.mark.parametrize("data", [
    '{"timestamp_ms":true,"landmarks":{}}',
    '{"timestamp_ms":5,"landmarks":{"0":{"x":0,"y":0,"visibility":1}}}',
    '{"timestamp_ms":5,"landmarks":{"11":{"x":"bad","y":0,"visibility":1}}}',
    '{"timestamp_ms":5,"landmarks":{"11":{"x":NaN,"y":0,"visibility":1}}}',
    '{"timestamp_ms":5,"landmarks":{"11":{"x":0,"y":0}}}',
    '{"timestamp_ms":-1,"landmarks":{}}',
    '{}',
    '{bad-json}',
])
def test_reject_bad_trace_frames(tmp_path, data):
    file = tmp_path / "bad.jsonl"
    file.write_text(data + "\n", encoding="utf-8")
    with pytest.raises(TraceFormatError):
        list(read_pose_trace(file, source_id="test"))


def test_no_empty_trace_and_line_limit(tmp_path):
    file = tmp_path / "bad.jsonl"
    file.write_text(" \n", encoding="utf-8")
    with pytest.raises(TraceFormatError, match="empty"):
        list(read_pose_trace(file, source_id="test"))
    file.write_text("{" + "x" * 5000, encoding="utf-8")
    with pytest.raises(TraceFormatError, match="limit"):
        list(read_pose_trace(file, source_id="test"))
