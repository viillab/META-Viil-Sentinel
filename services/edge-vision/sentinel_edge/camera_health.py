"""Vendor-neutral bounded RTSP camera health probe (no AI or frame storage).

Application messages never intentionally include URLs or credential values.
Native FFmpeg/OpenCV logs can still contain sensitive connection details.
"""
from argparse import ArgumentParser
from ipaddress import ip_address, ip_network
import json
from pathlib import Path
import os
from urllib.parse import unquote, urlsplit


RTSP_OPEN_TIMEOUT_MS = 8000
RTSP_READ_TIMEOUT_MS = 4000

# Literal private-address sources only by default: no public RTSP, localhost,
# link-local metadata-service ranges, multicast, DNS lookups or DNS rebinding.
PRIVATE_CAMERA_NETWORKS = (
    ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"), ip_network("fc00::/7"),
)
DEFAULT_RTSP_PORTS = frozenset({554, 8554})
MAX_RTSP_URL_LENGTH = 2048


def open_rtsp_capture(cv2, url: str):
    """Request FFmpeg RTSP open/read timeouts; backend support must be verified.

    OpenCV timeout properties are open-only and cannot be applied after opening.
    The caller must validate the URL and owns release of the returned capture.
    """
    return cv2.VideoCapture(
        url, cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT_MS,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_READ_TIMEOUT_MS,
        ],
    )


def validate_rtsp_env(
    name: str, environment: dict[str, str] | None = None, *,
    extra_port: int | None = None,
) -> str:
    """Return only a private-IP RTSP stream. Never print the source or exceptions.

    Supports any RTSP-compatible brand, standard 554/8554 and explicitly
    allowed custom ports. Literal private IPs deliberately avoid DNS rebinding.
    This is only a preflight filter; an egress firewall is still required.
    """
    if not name.isidentifier() or not name.startswith("VIIL_"):
        raise ValueError("Camera environment variable must be a VIIL_ identifier")
    if extra_port is not None and (type(extra_port) is not int or
                                   not 1 <= extra_port <= 65535):
        raise ValueError("Custom camera port must be in 1..65535")
    value = (os.environ if environment is None else environment).get(name, "")
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= MAX_RTSP_URL_LENGTH:
            raise ValueError
        parts = urlsplit(value)
        host = ip_address(parts.hostname or "")
        port = parts.port if parts.port is not None else 554
        decoded = unquote(value)
        valid = (
            parts.scheme == "rtsp"
            and any(host in network for network in PRIVATE_CAMERA_NETWORKS)
            and port in (DEFAULT_RTSP_PORTS | ({extra_port} if extra_port else set()))
            and not parts.fragment
            and not parts.netloc.count("@") > 1
            and not any(ord(char) < 32 or ord(char) == 127 for char in decoded)
            and not any(char in decoded for char in ("\\",))
            and "%" not in (parts.hostname or "")
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError("Missing or unsafe camera configuration (details redacted)")
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
    parser.add_argument("--rtsp-env", help="VIIL_ variable containing RTSP URL")
    parser.add_argument("--camera-registry", help="Local vendor-neutral camera JSON registry")
    parser.add_argument("--camera-id", help="RTSP camera ID in the registry")
    parser.add_argument("--source-id", default="staged-camera-01",
                        help="Pseudonymous camera scope for legacy --rtsp-env")
    parser.add_argument("--privacy-approval", type=Path, required=True,
                        help="Signed privacy authorization required for camera probe")
    parser.add_argument("--confirm-authorized-camera", action="store_true")
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--rtsp-allow-port", type=int, default=None,
                        help="Explicitly permit one vendor-specific RTSP port")
    args = parser.parse_args(argv)
    if not args.confirm_authorized_camera:
        parser.error("Real network capture needs --confirm-authorized-camera")
    try:
        if args.rtsp_env and (args.camera_registry or args.camera_id):
            raise ValueError
        if args.camera_registry:
            if not args.camera_id:
                raise ValueError
            from sentinel_edge.camera_inputs import load_camera_registry, resolve_camera
            registry = load_camera_registry(Path(args.camera_registry))
            camera = registry[args.camera_id]
            kind, url = resolve_camera(camera, extra_rtsp_port=args.rtsp_allow_port)
            if kind != "rtsp":
                raise ValueError
        elif args.rtsp_env and not args.camera_id:
            url = validate_rtsp_env(args.rtsp_env, extra_port=args.rtsp_allow_port)
        else:
            raise ValueError
        if not 1 <= args.frames <= 120:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        parser.error("Invalid camera selection or frame count (redacted)")
    from sentinel_edge.privacy_gate import verify_privacy_approval, PrivacyGateDenied
    try:
        verify_privacy_approval(
            args.privacy_approval, camera_id=args.camera_id or args.source_id,
        )
    except PrivacyGateDenied:
        parser.error("Camera privacy approval denied (redacted)")
    try:
        import cv2
    except ImportError:
        parser.error("OpenCV is required; install the edge video extra")
    cap = None
    try:
        cap = open_rtsp_capture(cv2, url)
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
