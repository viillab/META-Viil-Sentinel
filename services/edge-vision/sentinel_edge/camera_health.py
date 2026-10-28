"""Offline-testable bounded RTSP camera health probe (no AI, no frames persisted).

This module never logs URLs, credentials, network addresses or frame content.
Real device probing is explicitly opt-in and restricted to an authorized LAN.
"""
from argparse import ArgumentParser
import json
import os
from urllib.parse import urlsplit


def validate_rtsp_env(name: str, environment: dict[str, str] | None = None) -> str:
    """Return an RTSP URL only to the local capture backend; never print it."""
    if not name.isidentifier() or not name.startswith("VIIL_"):
        raise ValueError("Camera environment variable must be a VIIL_ identifier")
    value = (os.environ if environment is None else environment).get(name, "")
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme.lower() == "rtsp"
            and parts.hostname is not None
            and parts.port in (None, 554)
            and not parts.fragment
            and not any(char in value for char in ("\r", "\n", "\x00"))
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Missing or invalid camera configuration (details redacted)")
    return value


def probe_capture(capture, *, sample_frames: int = 12) -> dict:
    """Measure a bounded decode smoke test, not real camera uptime or safety."""
    if not 1 <= sample_frames <= 120:
        raise ValueError("sample_frames must be 1..120")
    if not capture.isOpened():
        return {"status": "offline", "frames_read": 0, "frames_requested": sample_frames}
    frames_read = 0
    for _ in range(sample_frames):
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        frames_read += 1
    return {
        "status": "readable" if frames_read == sample_frames else "interrupted",
        "frames_read": frames_read,
        "frames_requested": sample_frames,
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Local-only authorized RTSP decode health check")
    parser.add_argument("--rtsp-env", required=True, help="VIIL_ variable containing RTSP URL")
    parser.add_argument("--confirm-authorized-camera", action="store_true")
    parser.add_argument("--frames", type=int, default=12)
    args = parser.parse_args(argv)
    if not args.confirm_authorized_camera:
        parser.error("Real network capture needs --confirm-authorized-camera")
    try:
        url = validate_rtsp_env(args.rtsp_env)
        if not 1 <= args.frames <= 120:
            raise ValueError("frames must be between 1 and 120")
    except ValueError as exc:
        parser.error(str(exc))
    try:
        import cv2
    except ImportError:
        parser.error("OpenCV is required; install the edge video extra")
    cap = None
    try:
        cap = cv2.VideoCapture(url)
        report = probe_capture(cap, sample_frames=args.frames)
    except Exception:
        # Never stringify native library exceptions that could contain credentials.
        report = {"status": "error", "frames_read": 0, "frames_requested": args.frames}
    finally:
        if cap is not None:
            cap.release()
    # Print only bounded, non-identifying output. No URL/frame/model output.
    print(json.dumps({"type": "viil.camera.health.v1", **report}, sort_keys=True))
    return 0 if report["status"] == "readable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
