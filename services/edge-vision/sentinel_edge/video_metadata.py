"""Strict video metadata checks for reproducible prototype clip evaluation.

Use declared video frame-count and nominal FPS only as a basic integrity
check. These checks cannot establish accurate timing for variable-frame-rate
video or prove that a container file is not corrupt.
"""
from math import isfinite


def expected_frame_count(capture, cv2, *, clip_id: str, max_frames: int) -> int:
    """Reject insufficient metadata and budget overflow *before* model inference."""
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not isfinite(fps) or not 1 <= fps < 240:
        raise ValueError(f"Clip {clip_id}: invalid FPS metadata; cannot evaluate event latency")

    value = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not isfinite(value) or value < 1 or value > 1_000_000:
        raise ValueError(f"Clip {clip_id}: missing or invalid declared frame count")
    expected = round(value)
    if abs(value - expected) > 0.1 or expected < 1:
        raise ValueError(f"Clip {clip_id}: non-integer declared frame count")
    if expected > max_frames:
        raise ValueError(
            f"Clip {clip_id}: declared {expected} frames exceeds maximum of {max_frames} "
            "frames; evaluation refused before inference"
        )
    return expected


def require_complete_decode(*, clip_id: str, expected: int, decoded: int) -> None:
    """Reject unexpectedly early EOF or an inconsistent frame count."""
    if decoded != expected:
        raise ValueError(
            f"Clip {clip_id}: declared {expected} frames but decoded {decoded}; "
            "clip is incomplete or metadata is inconsistent"
        )
