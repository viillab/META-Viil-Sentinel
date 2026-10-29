"""Local-only, operator-supervised Hikvision live preview.

No HTTP server, remote streaming, image recording, persistence or AI claims.
Real cameras require the genuine signed privacy gate and an explicit GUI opt-in.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
from time import monotonic
from typing import Callable

from sentinel_edge.camera_health import (
    _valid_decoded_bgr_frame, open_rtsp_capture, validate_rtsp_env,
)
from sentinel_edge.privacy_gate import PrivacyGateDenied, verify_privacy_approval
from sentinel_edge.rtsp_failover import resolve_hikvision_stream_pair


WINDOW_TITLE = "VIIL Sentinel - AUTHORIZED LOCAL PREVIEW (not recorded)"
MAX_DISPLAY_SIDE = 960


class PreviewInterrupted(Exception):
    """Native stream or local GUI interruption (safe, credential-free message)."""


def _release_quietly(capture) -> None:
    if capture is not None:
        try:
            capture.release()
        except Exception:
            pass  # Native errors can contain the complete RTSP URL.


def _close_window_quietly(cv2, *, created: bool) -> None:
    if created:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except Exception:
            pass


def preview_authorized_stream(
    cv2, *,
    primary_url: str,
    alternate_url: str | None,
    privacy_check: Callable[[], None],
    max_frames: int = 450,
    duration_seconds: float = 30.0,
    open_capture: Callable | None = None,
    clock: Callable[[], float] = monotonic,
) -> dict:
    """Bounded on-screen frame display; never store/transmit frames.

    A malformed/missing frame causes a single same-camera fallback if provided.
    Signed approval is rechecked before native open, after open, before/after
    each read, before display, after input handling and after native cleanup.
    """
    if type(max_frames) is not int or not 1 <= max_frames <= 900:
        raise ValueError("Invalid preview frame budget")
    if type(duration_seconds) not in (float, int) or not 0 < duration_seconds <= 120:
        raise ValueError("Invalid preview duration")
    if not callable(privacy_check):
        raise ValueError("Signed privacy check required")
    if not primary_url or alternate_url == primary_url:
        raise ValueError("Invalid authorized stream selection")
    opener = open_capture or open_rtsp_capture
    start = clock()
    displayed = 0
    window_created = False
    used_fallback = False
    stopped_by_operator = False
    streams = (primary_url,) if alternate_url is None else (primary_url, alternate_url)
    try:
        for attempt, url in enumerate(streams):
            if displayed >= max_frames or clock() - start >= duration_seconds:
                break
            privacy_check()
            cap = None
            try:
                try:
                    cap = opener(cv2, url)
                except Exception:
                    raise PreviewInterrupted("Authorized stream open failed") from None
                privacy_check()
                try:
                    opened = cap is not None and cap.isOpened()
                except Exception:
                    raise PreviewInterrupted("Authorized stream unavailable") from None
                if not opened:
                    raise PreviewInterrupted("Authorized stream unavailable")
                while displayed < max_frames and clock() - start < duration_seconds:
                    privacy_check()
                    try:
                        ok, frame = cap.read()
                    except Exception:
                        raise PreviewInterrupted("Camera stream read interrupted") from None
                    privacy_check()
                    if not ok or not _valid_decoded_bgr_frame(frame):
                        raise PreviewInterrupted("Unusable decoded camera frame")
                    if clock() - start >= duration_seconds:
                        break
                    # Downsize only in volatile memory to bound GUI bandwidth.
                    height, width, _ = frame.shape
                    if max(height, width) > MAX_DISPLAY_SIDE:
                        scale = MAX_DISPLAY_SIDE / max(height, width)
                        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                        try:
                            frame = cv2.resize(
                                frame, new_size, interpolation=cv2.INTER_AREA,
                            )
                        except Exception:
                            raise PreviewInterrupted("Preview resize failed") from None
                    privacy_check()
                    try:
                        cv2.imshow(WINDOW_TITLE, frame)
                        window_created = True
                        key = cv2.waitKey(1) & 0xFF
                    except Exception:
                        raise PreviewInterrupted("Local graphical display unavailable") from None
                    privacy_check()
                    displayed += 1
                    if key in (ord("q"), 27):
                        stopped_by_operator = True
                        break
                if stopped_by_operator:
                    break
                # Hitting the explicit frame/time budget is a successful stop.
                if displayed >= max_frames or clock() - start >= duration_seconds:
                    break
            except PreviewInterrupted:
                if attempt + 1 == len(streams) or clock() - start >= duration_seconds:
                    raise
                used_fallback = True
                # No model or temporal state is retained across stream epochs.
            finally:
                _release_quietly(cap)
                privacy_check()
        privacy_check()
        if displayed == 0:
            raise PreviewInterrupted("No authorized frames displayed")
        return {
            "type": "viil.camera.local_preview.v1",
            "result": "operator_stopped" if stopped_by_operator else "bounded_preview_complete",
            "frames_displayed": displayed,
            "fallback_used": used_fallback,
            "video_saved": False,
            "remote_streamed": False,
            "ai_inference_run": False,
        }
    finally:
        _close_window_quietly(cv2, created=window_created)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Authorized local camera preview, no recording")
    parser.add_argument("--rtsp-env", required=True, help="Primary VIIL_ environment variable")
    parser.add_argument("--fallback-env", help="Same-camera alternative VIIL_ environment variable")
    parser.add_argument("--source-id", required=True, help="Approved pseudonymous camera ID")
    parser.add_argument("--privacy-approval", required=True, type=Path)
    parser.add_argument("--confirm-authorized-camera", action="store_true")
    parser.add_argument("--show-local-preview", action="store_true")
    parser.add_argument("--max-frames", type=int, default=450)
    parser.add_argument("--decoder", choices=("opencv", "pyav"), default="opencv",
                        help="In-memory RTSP video decoder backend")
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--rtsp-allow-port", type=int, default=None)
    args = parser.parse_args(argv)
    if not args.confirm_authorized_camera or not args.show_local_preview:
        parser.error("Explicit authorization and local display opt-in required")
    try:
        if args.fallback_env:
            pair = resolve_hikvision_stream_pair(
                args.rtsp_env, args.fallback_env, extra_port=args.rtsp_allow_port,
            )
            primary, alternate = pair.primary, pair.fallback
        else:
            primary = validate_rtsp_env(args.rtsp_env, extra_port=args.rtsp_allow_port)
            alternate = None
        if not 1 <= args.max_frames <= 900 or not 0 < args.duration_seconds <= 120:
            raise ValueError
    except (ValueError, TypeError):
        parser.error("Unsafe or missing camera configuration (details redacted)")
    def check() -> None:
        verify_privacy_approval(args.privacy_approval, camera_id=args.source_id)
    try:
        check()
    except PrivacyGateDenied:
        parser.error("Signed camera approval denied (details redacted)")
    try:
        import cv2
    except ImportError:
        parser.error("Local OpenCV GUI support is required")
    try:
        opener = None
        if args.decoder == "pyav":
            from sentinel_edge.pyav_capture import open_pyav_capture
            opener = open_pyav_capture
        report = preview_authorized_stream(
            cv2, primary_url=primary, alternate_url=alternate,
            privacy_check=check, max_frames=args.max_frames,
            duration_seconds=args.duration_seconds, open_capture=opener,
        )
    except PrivacyGateDenied:
        # Never declare a preview successful when approval was revoked.
        parser.error("Camera privacy approval revoked (details redacted)")
    except Exception:
        # No native error text: codecs may include the credentialed RTSP URL.
        parser.error("Local preview unavailable or interrupted (details redacted)")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
