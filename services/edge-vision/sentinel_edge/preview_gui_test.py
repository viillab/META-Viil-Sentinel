"""Bounded, explicitly SYNTHETIC Windows preview GUI diagnostic.

This module NEVER opens camera devices, reads RTSP or grants camera rights.
It shows a locally generated test pattern only, with unmistakable labels.
"""
from time import monotonic
from typing import Callable


TEST_TITLE = "VIIL Sentinel - SYNTHETIC GUI TEST (NOT CAMERA)"


class LocalGuiUnavailable(Exception):
    """No safe interactive display is accessible from this Windows session."""


def show_synthetic_gui(
    cv2, numpy, *,
    duration_seconds: float = 5.0,
    max_frames: int = 150,
    clock: Callable[[], float] = monotonic,
) -> dict:
    """Show a test pattern in memory; exit on Q/Esc/window close/time budget."""
    if (type(duration_seconds) not in (int, float)
            or not 0 < duration_seconds <= 8):
        raise ValueError("Synthetic GUI test duration must be 0..8 seconds")
    if type(max_frames) is not int or not 1 <= max_frames <= 240:
        raise ValueError("Synthetic GUI test frame budget must be 1..240")
    start = clock()
    frames = 0
    created = False
    stop_reason = "bounded_test_complete"
    try:
        while frames < max_frames and clock() - start < duration_seconds:
            # Distinct static header + frame counter so a frozen window is obvious.
            canvas = numpy.zeros((360, 640, 3), dtype=numpy.uint8)
            canvas[:, :] = (35, 32, 24)
            try:
                cv2.putText(
                    canvas, "VIIL SENTINEL - GUI SELF TEST", (28, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.82, (240, 240, 240), 2,
                )
                cv2.putText(
                    canvas, "SYNTHETIC / NOT CAMERA VIDEO", (28, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 220, 255), 2,
                )
                cv2.putText(
                    canvas, f"Frames shown: {frames + 1}", (28, 232),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 220), 2,
                )
                cv2.putText(
                    canvas, "Press Q or ESC to close", (28, 297),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 220, 220), 1,
                )
                cv2.imshow(TEST_TITLE, canvas)
                created = True
                key = cv2.waitKey(30) & 0xFF
                frames += 1
                if key in (ord("q"), ord("Q"), 27):
                    stop_reason = "operator_stopped"
                    break
                get_property = getattr(cv2, "getWindowProperty", None)
                visible_prop = getattr(cv2, "WND_PROP_VISIBLE", None)
                if callable(get_property) and visible_prop is not None:
                    if get_property(TEST_TITLE, visible_prop) < 1:
                        stop_reason = "window_closed"
                        break
            except Exception:
                # Native GUI failures can expose local runtime/config paths.
                raise LocalGuiUnavailable("Interactive local GUI is unavailable") from None
        return {
            "type": "viil.camera.synthetic_gui_test.v1",
            "result": stop_reason,
            "frames_displayed": frames,
            "synthetic_test_pattern": True,
            "camera_opened": False,
            "video_decoded": False,
            "video_saved": False,
            "remote_streamed": False,
        }
    finally:
        if created:
            try:
                cv2.destroyWindow(TEST_TITLE)
            except Exception:
                pass
