"""Offline pose traces: strict, bounded, local-only JSONL reader.

Landmark traces can be identifying. Do not commit real traces or patient data.
Only a minimal set of torso landmarks is needed for this heuristic.
"""
import json
from collections.abc import Iterator
from pathlib import Path

from sentinel_edge.contracts import REQUIRED_POINTS, Landmark, PoseFrame

MAX_FRAMES_PER_CLIP = 100_000
MAX_LINE_CHARS = 4096


class TraceFormatError(ValueError):
    """A local trace contains invalid or excessive data."""


def read_pose_trace(path: Path, *, source_id: str) -> Iterator[PoseFrame]:
    """Read timestamped normalized torso landmarks; reject malformed lines.

    JSONL schema: {"timestamp_ms": 100, "landmarks":
                   {"11":{"x":0.45,"y":0.25,"visibility":0.95},...}}
    Missing landmarks are allowed to represent occlusions.
    """
    with path.open("r", encoding="utf-8") as stream:
        seen = 0
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if len(line) > MAX_LINE_CHARS:
                raise TraceFormatError(f"Line {line_number}: exceeds limit")
            seen += 1
            if seen > MAX_FRAMES_PER_CLIP:
                raise TraceFormatError("Trace exceeds allowed frame count")
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict) or set(obj) != {"timestamp_ms", "landmarks"}:
                    raise ValueError("invalid trace frame keys")
                ts, raw = obj["timestamp_ms"], obj["landmarks"]
                if type(ts) is not int or ts < 0 or not isinstance(raw, dict):
                    raise ValueError("invalid timestamp_ms or landmarks")
                if any(str(k) not in {str(idx) for idx in REQUIRED_POINTS} for k in raw):
                    raise ValueError("only four required torso landmark IDs may be stored")
                landmarks = {}
                for raw_index, point in raw.items():
                    if not isinstance(point, dict) or set(point) != {"x", "y", "visibility"}:
                        raise ValueError("invalid landmark keys")
                    if any(type(point[k]) not in (float, int) for k in point):
                        raise ValueError("landmark values must be numbers")
                    landmarks[int(raw_index)] = Landmark(**point)
                yield PoseFrame(timestamp_ms=ts, source_id=source_id, landmarks=landmarks)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise TraceFormatError(f"Line {line_number}: invalid pose trace data") from exc
        if seen == 0:
            raise TraceFormatError("Pose trace is empty")


def frame_to_trace_record(frame: PoseFrame) -> str:
    """Serialize only the 4 torso points; no raw video, names, or frame images."""
    landmarks = {
        str(idx): {
            "x": frame.landmarks[idx].x,
            "y": frame.landmarks[idx].y,
            "visibility": frame.landmarks[idx].visibility,
        }
        for idx in REQUIRED_POINTS if idx in frame.landmarks
    }
    return json.dumps({"timestamp_ms": frame.timestamp_ms, "landmarks": landmarks},
                      separators=(",", ":"), allow_nan=False)
