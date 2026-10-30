"""Private, bounded *in-process* Edge MJPEG parts for a trusted media backend.

This module is NOT an HTTP server and never binds a network socket. The
Member 2 authenticated backend owns per-viewer session authorization/CSRF,
all HTTP headers and the final stream endpoint. No public/remote streaming.
Real-camera use additionally requires genuine, signed site/privacy approval,
a validated private RTSP source and an explicit trusted viewer-session check.

The generator returns transient multipart JPEG bytes to its trusted in-process
caller only, after 12/12 independently decoded camera health frames.
Do not call from a browser, from an unauthenticated route or a public service.
"""
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from time import monotonic, sleep

from sentinel_edge.camera_health import (
    _valid_decoded_bgr_frame, open_rtsp_capture, validate_rtsp_env,
)
from sentinel_edge.privacy_gate import CAMERA_PATTERN, verify_privacy_approval


class EdgeMediaDenied(ValueError):
    """Authorization rejected; deliberately contains no camera identifiers."""


class EdgeMediaUnavailable(RuntimeError):
    """No verified readable frames or bounded JPEG encoding unavailable."""


MAX_MJPEG_PART_BYTES = 256 * 1024
MAX_MJPEG_WIDTH = 768
MAX_MJPEG_HEIGHT = 432
PREFLIGHT_DECODE_FRAMES = 12
# First validated JPEG should be ready quickly enough for a human operator.
# This is an elapsed-time checkpoint, not a hard timeout for native codecs.
MAX_PREFLIGHT_SECONDS = 10.0
MJPEG_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame"


def iter_authorized_mjpeg_parts(
    cv2, *,
    source_env: str,
    source_id: str,
    privacy_approval: Path,
    viewer_check: Callable[[], bool],
    decoder: str = "pyav",
    max_frames: int = 120,
    duration_seconds: float = 25.0,
    fps: int = 5,
    jpeg_quality: int = 65,
    environment: Mapping[str, str] | None = None,
    open_capture: Callable | None = None,
    clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> Iterator[bytes]:
    """Yield local MJPEG parts, verifying BOTH approvals for every camera read.

    The viewer_check MUST be a trusted server-side callback that verifies the
    specific *current* operator, camera-scoped session, RBAC and expiry. Never
    pass a lambda that always returns True in real use. The signed Edge
    privacy checker is separate and cannot be bypassed by that callback.
    """
    if (not isinstance(source_id, str) or CAMERA_PATTERN.fullmatch(source_id) is None
            or not isinstance(privacy_approval, Path)
            or not callable(viewer_check) or not callable(clock)
            or not callable(sleeper)
            or decoder not in ("pyav", "opencv")
            or type(max_frames) is not int or not 1 <= max_frames <= 120
            or type(duration_seconds) not in (int, float)
            or not 0 < duration_seconds <= 30
            or type(fps) is not int or not 1 <= fps <= 10
            or type(jpeg_quality) is not int or not 40 <= jpeg_quality <= 80):
        raise ValueError("Invalid protected media session configuration")

    def authorized() -> None:
        try:
            verify_privacy_approval(
                privacy_approval, camera_id=source_id, environment=environment,
            )
            if viewer_check() is not True:
                raise EdgeMediaDenied("Protected media session not authorized")
        except Exception:
            # Do not expose file paths, camera IP, RTSP URLs or backend secrets.
            raise EdgeMediaDenied("Protected media session not authorized") from None

    started = clock()

    def require_first_frame_budget() -> None:
        # This rejects a delayed connection/read/encode *after* the native
        # operation returns. Native I/O timeouts are handled by the decoder.
        if clock() - started >= min(MAX_PREFLIGHT_SECONDS, duration_seconds):
            raise EdgeMediaUnavailable("Protected first-frame preflight timed out")

    authorized()  # no RTSP configuration or decoder is accessed before approval
    try:
        url = validate_rtsp_env(source_env, environment)
    except (ValueError, TypeError):
        raise ValueError("Invalid private RTSP configuration (redacted)") from None

    if open_capture is not None:
        opener = open_capture
    elif decoder == "pyav":
        from sentinel_edge.pyav_capture import open_pyav_capture
        opener = open_pyav_capture
    else:
        opener = open_rtsp_capture

    cap = None
    try:
        authorized()
        try:
            cap = opener(cv2, url)
            if cap is None or not cap.isOpened():
                raise EdgeMediaUnavailable("Protected source unavailable")
        except Exception:
            raise EdgeMediaUnavailable("Protected source unavailable") from None
        authorized()
        require_first_frame_budget()

        # A connection-only OPTIONS response or even one decoded frame is NOT
        # sufficient to declare the camera media ready for a browser client.
        for _ in range(PREFLIGHT_DECODE_FRAMES):
            require_first_frame_budget()
            authorized()
            try:
                ok, frame = cap.read()
            except Exception:
                raise EdgeMediaUnavailable("Protected source preflight failed") from None
            authorized()
            require_first_frame_budget()
            if not ok or not _valid_decoded_bgr_frame(frame):
                raise EdgeMediaUnavailable("Protected source preflight failed")

        require_first_frame_budget()
        last_emit = None
        for _ in range(max_frames):
            if clock() - started >= duration_seconds:
                break
            if last_emit is not None:
                pause = (1.0 / fps) - (clock() - last_emit)
                if pause > 0:
                    authorized()
                    try:
                        sleeper(pause)
                    except Exception:
                        raise EdgeMediaUnavailable("Protected frame pacing interrupted") from None
            if clock() - started >= duration_seconds:
                break
            if last_emit is None:
                require_first_frame_budget()
            authorized()
            try:
                ok, frame = cap.read()
            except Exception:
                raise EdgeMediaUnavailable("Protected frame decode interrupted") from None
            authorized()
            if last_emit is None:
                require_first_frame_budget()
            if not ok or not _valid_decoded_bgr_frame(frame):
                raise EdgeMediaUnavailable("Protected frame decode interrupted")
            height, width, _ = frame.shape
            if width > MAX_MJPEG_WIDTH or height > MAX_MJPEG_HEIGHT:
                scale = min(MAX_MJPEG_WIDTH / width, MAX_MJPEG_HEIGHT / height)
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                try:
                    frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
                except Exception:
                    raise EdgeMediaUnavailable("Protected frame resize failed") from None
                authorized()
                if not _valid_decoded_bgr_frame(frame):
                    raise EdgeMediaUnavailable("Protected frame resize invalid")
            try:
                ok_jpeg, encoded = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                )
                data = encoded.tobytes() if ok_jpeg else b""
            except Exception:
                raise EdgeMediaUnavailable("Protected frame JPEG encoding failed") from None
            if (not data or len(data) > MAX_MJPEG_PART_BYTES
                    or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9")):
                raise EdgeMediaUnavailable("Protected frame JPEG invalid or too large")
            if last_emit is None:
                require_first_frame_budget()
            if clock() - started >= duration_seconds:
                break
            authorized()  # no result leaves Edge if privacy/viewer access was revoked
            last_emit = clock()
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(data)).encode("ascii") + b"\r\n\r\n" + data + b"\r\n"
            )
        authorized()
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                # Native FFmpeg errors can embed the credentialed RTSP URL.
                pass
