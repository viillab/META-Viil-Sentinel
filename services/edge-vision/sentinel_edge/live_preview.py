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


class PreviewDisplayUnavailable(PreviewInterrupted):
    """A GUI failure is not a camera outage; never retry on the alternate stream."""


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


def _overlay_live_status(
    cv2, frame, *, frame_number: int, display_fps: float | None,
):
    """Add a non-identifying HUD in memory. GUI text support is optional.

    Display FPS measures frames shown during this local session; it is not
    camera FPS, network latency, or the AI inference rate. Never show source
    IDs, IPs, RTSP URLs, credentials, timestamps or detection claims.
    """
    draw_text = getattr(cv2, "putText", None)
    if not callable(draw_text):
        return frame
    try:
        height, width, _ = frame.shape
        fps_label = "warming up" if display_fps is None else f"{display_fps:.1f} display fps"
        label = f"LOCAL ONLY | frame {frame_number} | {width}x{height} | {fps_label}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        antialias = cv2.LINE_AA
        # Shadow and lettering are drawn only on the transient preview frame.
        draw_text(frame, label, (10, 24), font, 0.48, (0, 0, 0), 3, antialias)
        draw_text(frame, label, (10, 24), font, 0.48, (255, 255, 255), 1, antialias)
    except Exception:
        # Overlay failure must not be mistaken for a camera disconnect, and
        # native exceptions can contain sensitive camera information.
        pass
    return frame


def preview_authorized_stream(
    cv2, *,
    primary_url: str,
    alternate_url: str | None,
    privacy_check: Callable[[], None],
    max_frames: int = 450,
    duration_seconds: float = 30.0,
    open_capture: Callable | None = None,
    pose_factory: Callable[[], object] | None = None,
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
    if pose_factory is not None and not callable(pose_factory):
        raise ValueError("Optional local pose session factory must be callable")
    if not primary_url or alternate_url == primary_url:
        raise ValueError("Invalid authorized stream selection")
    opener = open_capture or open_rtsp_capture
    start = clock()
    first_display_at = None
    displayed = 0
    pose_processed = 0
    pose_accepted = 0
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
            pose_session = None
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
                if pose_factory is not None:
                    privacy_check()
                    try:
                        pose_session = pose_factory()
                    except Exception:
                        raise PreviewDisplayUnavailable("Local pose overlay unavailable") from None
                    privacy_check()
                pose_epoch_started = clock()
                last_pose_timestamp = -1
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
                    if pose_session is not None:
                        # Strict VIDEO timestamps increase within a single epoch.
                        timestamp_ms = max(
                            last_pose_timestamp + 1,
                            int((clock() - pose_epoch_started) * 1000),
                        )
                        last_pose_timestamp = timestamp_ms
                        try:
                            accepted = pose_session.annotate(cv2, frame, timestamp_ms)
                        except Exception:
                            raise PreviewDisplayUnavailable(
                                "Local torso preview unavailable",
                            ) from None
                        privacy_check()  # discard result after native inference if revoked
                        pose_processed += 1
                        pose_accepted += bool(accepted)
                        try:
                            status = ("TORSO AVAILABLE" if accepted else "TORSO UNAVAILABLE")
                            cv2.putText(
                                frame, status + " | NO FALL DECISION",
                                (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                                (255, 255, 255), 1, cv2.LINE_AA,
                            )
                        except Exception:
                            pass
                        privacy_check()
                    display_now = clock()
                    if first_display_at is None:
                        first_display_at = display_now
                    elapsed = display_now - first_display_at
                    display_fps = displayed / elapsed if elapsed >= 0.5 else None
                    frame = _overlay_live_status(
                        cv2, frame, frame_number=displayed + 1,
                        display_fps=display_fps,
                    )
                    privacy_check()
                    try:
                        cv2.imshow(WINDOW_TITLE, frame)
                        window_created = True
                        key = cv2.waitKey(1) & 0xFF
                        window_visible = True
                        get_property = getattr(cv2, "getWindowProperty", None)
                        visible_property = getattr(cv2, "WND_PROP_VISIBLE", None)
                        if callable(get_property) and visible_property is not None:
                            window_visible = get_property(
                                WINDOW_TITLE, visible_property,
                            ) >= 1
                    except Exception:
                        raise PreviewDisplayUnavailable(
                            "Local graphical display unavailable",
                        ) from None
                    privacy_check()
                    displayed += 1
                    if key in (ord("q"), ord("Q"), 27) or not window_visible:
                        stopped_by_operator = True
                        break
                if stopped_by_operator:
                    break
                # Hitting the explicit frame/time budget is a successful stop.
                if displayed >= max_frames or clock() - start >= duration_seconds:
                    break
            except PreviewInterrupted as exc:
                if isinstance(exc, PreviewDisplayUnavailable):
                    raise
                if attempt + 1 == len(streams) or clock() - start >= duration_seconds:
                    raise
                used_fallback = True
                # No model or temporal state is retained across stream epochs.
            finally:
                if pose_session is not None:
                    try:
                        pose_session.close()
                    except Exception:
                        pass
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
            "ai_inference_run": pose_processed > 0,
            "torso_pose_inference_frames": pose_processed,
            "torso_pose_accepted_frames": pose_accepted,
            "fall_decision_run": False,
        }
    finally:
        _close_window_quietly(cv2, created=window_created)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Authorized local camera preview, no recording")
    parser.add_argument("--rtsp-env", help="Primary VIIL_ environment variable")
    parser.add_argument("--http-mjpeg-env", help="Private HTTP-MJPEG URL environment variable")
    parser.add_argument("--fallback-env", help="Same-camera alternative VIIL_ environment variable")
    parser.add_argument("--source-id", help="Approved pseudonymous camera ID")
    parser.add_argument("--privacy-approval", type=Path)
    parser.add_argument("--confirm-authorized-camera", action="store_true")
    parser.add_argument("--show-local-preview", action="store_true")
    parser.add_argument("--pose-model", type=Path,
                        help="Optional local torso-only MediaPipe overlay (not fall detection)")
    parser.add_argument("--self-test-gui", action="store_true",
                        help="SYNTHETIC local GUI test: NO CAMERA OR RTSP access")
    parser.add_argument("--max-frames", type=int, default=450)
    parser.add_argument("--decoder", choices=("opencv", "pyav", "http-mjpeg"), default="opencv",
                        help="In-memory RTSP video decoder backend")
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--rtsp-allow-port", type=int, default=None)
    args = parser.parse_args(argv)
    if args.self_test_gui:
        if (args.rtsp_env or args.http_mjpeg_env or args.fallback_env or args.source_id
                or args.privacy_approval or args.confirm_authorized_camera
                or args.show_local_preview or args.pose_model is not None):
            parser.error("Synthetic GUI test cannot accept camera parameters")
        try:
            import cv2
            import numpy as np
            from sentinel_edge.preview_gui_test import (
                LocalGuiUnavailable, show_synthetic_gui,
            )
            report = show_synthetic_gui(
                cv2, np, duration_seconds=min(args.duration_seconds, 8),
                max_frames=min(args.max_frames, 150),
            )
        except (ImportError, ValueError, LocalGuiUnavailable):
            parser.error("Synthetic local GUI unavailable (details redacted)")
        print(json.dumps(report, sort_keys=True))
        return 0
    if not (args.rtsp_env or args.http_mjpeg_env) or not args.source_id or args.privacy_approval is None:
        parser.error("Authorized camera parameters required")
    if not args.confirm_authorized_camera or not args.show_local_preview:
        parser.error("Explicit authorization and local display opt-in required")
    try:
        if args.http_mjpeg_env:
            if args.rtsp_env or args.fallback_env or args.decoder != "http-mjpeg":
                raise ValueError
            from sentinel_edge.http_mjpeg_capture import validate_http_mjpeg_env
            primary = validate_http_mjpeg_env(
                args.http_mjpeg_env, extra_port=args.rtsp_allow_port,
            )
            alternate = None
        elif args.decoder == "http-mjpeg":
            raise ValueError
        elif args.fallback_env:
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
    pose_factory = None
    if args.pose_model is not None:
        try:
            from sentinel_edge.pose_preview import (
                TorsoPoseOverlay, validate_local_pose_asset,
            )
            local_model = validate_local_pose_asset(args.pose_model)
        except (ValueError, ImportError):
            parser.error("Local torso pose asset missing or unsupported (redacted)")
        def pose_factory():
            return TorsoPoseOverlay(local_model)
    try:
        import cv2
    except ImportError:
        parser.error("Local OpenCV GUI support is required")
    try:
        opener = None
        if args.decoder == "pyav":
            from sentinel_edge.pyav_capture import open_pyav_capture
            opener = open_pyav_capture
        elif args.decoder == "http-mjpeg":
            from sentinel_edge.http_mjpeg_capture import open_http_mjpeg_capture
            opener = open_http_mjpeg_capture
        report = preview_authorized_stream(
            cv2, primary_url=primary, alternate_url=alternate,
            privacy_check=check, max_frames=args.max_frames,
            duration_seconds=args.duration_seconds, open_capture=opener,
            pose_factory=pose_factory,
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
