"""Credential-free, single-target RTSP OPTIONS diagnostic (no video capture).

RTSP OPTIONS is only an application-protocol handshake. It does NOT verify
camera credentials, signed privacy approval, video decoding or AI inference.
No other method (DESCRIBE/SETUP/PLAY) is issued. No network scanning.
"""
from argparse import ArgumentParser
from ipaddress import IPv4Address, ip_address
import json
import re
import socket

from sentinel_edge.camera_health import PRIVATE_CAMERA_NETWORKS


_STATUS_LINE = re.compile(rb"^RTSP/(?:1\.0|2\.0) ([1-5][0-9]{2})(?:[ \t]|$)")


def validate_target(camera_ip: str, port: int, timeout_seconds: float) -> str:
    """Permit one literal RFC1918 IPv4 and a bounded socket handshake."""
    try:
        ip = ip_address(camera_ip)
    except ValueError:
        raise ValueError("Camera IP must be an RFC1918 literal IPv4 address") from None
    if not isinstance(ip, IPv4Address) or not any(
        ip in network for network in PRIVATE_CAMERA_NETWORKS
        if network.version == 4
    ):
        raise ValueError("Camera IP must be an RFC1918 literal IPv4 address")
    if type(port) is not int or port not in (554, 8554):
        raise ValueError("Only approved RTSP ports 554 and 8554 are supported")
    if type(timeout_seconds) not in (float, int) or not 0.2 <= timeout_seconds <= 5.0:
        raise ValueError("Timeout must be in 0.2..5 seconds")
    return str(ip)


def probe_options(camera_ip: str, *, port: int = 554, timeout_seconds: float = 2.5) -> dict:
    """Send a single OPTIONS request, discard response except RTSP status code.

    The socket remains bounded in time and bytes. No credentials, image frames,
    filenames, raw headers, camera URL content or response body are returned.
    """
    ip = validate_target(camera_ip, port, timeout_seconds)
    result = {
        "type": "viil.camera.rtsp_options.v1",
        "result": "no_response",
        "rtsp_status_code": None,
        "authentication_challenge": False,
        "credentials_used": False,
        "video_decoded": False,
        "privacy_approval_verified": False,
    }
    # A standards-conformant OPTIONS request is deliberately sent without
    # Authorization, User-Agent identity, stream path or camera credentials.
    request = (
        f"OPTIONS rtsp://{ip}:{port}/ RTSP/1.0\r\n"
        "CSeq: 1\r\n\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((ip, port), timeout=timeout_seconds) as sock:
            sock.settimeout(timeout_seconds)
            sock.sendall(request)
            response = bytearray()
            while len(response) < 1024 and b"\n" not in response:
                part = sock.recv(min(256, 1024 - len(response)))
                if not part:
                    break
                response.extend(part)
    except (OSError, TimeoutError):
        result["result"] = "transport_or_protocol_timeout"
        return result
    first = bytes(response).split(b"\n", 1)[0].rstrip(b"\r")
    match = _STATUS_LINE.match(first)
    if not match:
        result["result"] = "non_rtsp_or_invalid_response"
        return result
    code = int(match.group(1))
    result["result"] = "rtsp_server_responded"
    result["rtsp_status_code"] = code
    result["authentication_challenge"] = code in (401, 407)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="One private-IP RTSP OPTIONS probe; no credentials or frames")
    parser.add_argument("--camera-ip", required=True, help="Authorized RFC1918 IPv4 camera")
    parser.add_argument("--port", type=int, default=554, choices=(554, 8554))
    parser.add_argument("--timeout-seconds", type=float, default=2.5)
    args = parser.parse_args(argv)
    try:
        report = probe_options(
            args.camera_ip, port=args.port, timeout_seconds=args.timeout_seconds,
        )
    except ValueError:
        parser.error("Unsafe RTSP probe parameters (details redacted)")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "rtsp_server_responded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
