"""Opt-in bounded frame downscaling for OFFLINE inference experiments only.

The original pixels are never written, and display uses the unmodified
frame. This is deliberately not a production performance preset.
"""


def validate_max_side(max_side: int) -> None:
    """0=disabled; otherwise require an explicit reasonable pixel cap."""
    if type(max_side) is not int or (max_side != 0 and not 256 <= max_side <= 4096):
        raise ValueError("max_inference_side must be 0 or an integer within 256..4096")


def resize_for_inference(bgr, cv2, *, max_side: int):
    """Return a new downscaled frame only when at least one side exceeds cap.

    Aspect ratio is preserved to the nearest pixel, no upscaling/strides or
    frame dropping. MediaPipe source-relative timestamps remain unchanged.
    """
    validate_max_side(max_side)
    if max_side == 0:
        return bgr
    shape = getattr(bgr, "shape", None)
    if (shape is None or len(shape) != 3 or
            type(shape[0]) is not int or type(shape[1]) is not int or
            shape[0] < 1 or shape[1] < 1 or shape[2] != 3):
        raise ValueError("Expected non-empty HxWx3 decoded BGR frame")
    height, width = shape[:2]
    longest = max(width, height)
    if longest <= max_side:
        return bgr
    factor = max_side / longest
    new_width = max(1, round(width * factor))
    new_height = max(1, round(height * factor))
    return cv2.resize(bgr, (new_width, new_height), interpolation=cv2.INTER_AREA)
