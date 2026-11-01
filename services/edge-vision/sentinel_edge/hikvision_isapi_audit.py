"""Read-only, privacy-minimal Hikvision ISAPI stream configuration audit.

Reads ONLY /ISAPI/Streaming/channels/{101,102} using HTTP Digest. Never
requests PLAY, recordings, PTZ, device edits, or camera images. Requires
operator-provided process-only credentials; emits strictly allowlisted stream
metadata, never URLs, credentials, serials, XML, or camera addresses.
"""
from argparse import ArgumentParser
from ipaddress import IPv4Address, ip_address, ip_network
import json
import math
import os
import re
from urllib.request import (
    HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm,
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring as safe_xml_fromstring
from defusedxml.common import DefusedXmlException

MAX_XML_BYTES = 64 * 1024
_PRIVATE = (ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"))
_CHANNELS = ("101", "102")
_CODEC = {"H.264": "H.264", "H264": "H.264",
          "H.265": "H.265", "H265": "H.265",
          "MJPEG": "MJPEG", "M-JPEG": "MJPEG"}
_PROFILE = {"BASELINE", "MAIN", "HIGH"}
_BITRATE = {"CBR", "VBR"}


class CameraAuditUnavailable(Exception):
    """The camera metadata is unavailable or unsafe; never expose native errors."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _url(camera_ip: str, port: int, channel: str) -> str:
    try:
        ip = ip_address(camera_ip)
        if (not isinstance(ip, IPv4Address) or
                not any(ip in network for network in _PRIVATE) or
                type(port) is not int or port not in (80, 8080) or
                channel not in _CHANNELS):
            raise ValueError
    except ValueError:
        raise CameraAuditUnavailable("Unsafe private camera target") from None
    return f"http://{ip}:{port}/ISAPI/Streaming/channels/{channel}"


def _field(root: ElementTree.Element, *names: str) -> str | None:
    aliases = {n.lower() for n in names}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() in aliases:
            value = (element.text or "").strip()
            if value:
                return value
    return None


def _numeric(value: str | None, *, maximum: int) -> int | None:
    if value is None or not re.fullmatch(r"[0-9]{1,10}", value):
        return None
    n = int(value)
    return n if 0 < n <= maximum else None


def parse_stream_xml(payload: bytes, expected_channel: str) -> dict:
    """Extract only bounded non-personal codec parameters; do not retain XML."""
    if (expected_channel not in _CHANNELS or
            not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_XML_BYTES or
            b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper()):
        raise CameraAuditUnavailable("Invalid Hikvision channel metadata")
    try:
        # Reject DTD/entities in the parser itself, not only by checking bytes.
        # Only short, allowlisted, read-only codec metadata is inspected.
        root = safe_xml_fromstring(
            payload, forbid_dtd=True, forbid_entities=True, forbid_external=True,
        )
        if root.tag.rsplit("}", 1)[-1] != "StreamingChannel":
            raise ValueError
        actual_id = _field(root, "id")
        if actual_id is not None and actual_id != expected_channel:
            raise ValueError
        video = next(
            (e for e in root.iter() if e.tag.rsplit("}", 1)[-1].lower() == "video"),
            None,
        )
        if video is None:
            raise ValueError
        raw = (_field(video, "videoCodecType", "videoEncoding") or "").upper()
        codec = _CODEC.get(raw)
        if codec is None:
            raise ValueError
        width = _numeric(_field(video, "videoResolutionWidth", "width"),
                         maximum=8192)
        height = _numeric(_field(video, "videoResolutionHeight", "height"),
                          maximum=8192)
        frame_rate_x100 = _numeric(_field(video, "maxFrameRate"),
                                   maximum=24000)
        bitrate = _numeric(_field(video, "vbrUpperCap", "constantBitRate",
                                  "maxBitrate", "bitRate"), maximum=1000000)
        profile = (_field(video, "h264Profile", "videoProfile") or "").upper()
        rate_control = (_field(video, "videoQualityControlType",
                               "bitrateType") or "").upper()
        return {
            "channel": expected_channel,
            "codec": codec,
            "width": width,
            "height": height,
            "configured_fps": round(frame_rate_x100 / 100, 2) if frame_rate_x100 else None,
            "bitrate_kbps": bitrate,
            "h264_profile": profile if codec == "H.264" and profile in _PROFILE else None,
            "bitrate_control": rate_control if rate_control in _BITRATE else None,
        }
    except (ElementTree.ParseError, DefusedXmlException,
            ValueError, StopIteration, TypeError):
        raise CameraAuditUnavailable("Invalid Hikvision channel metadata") from None


def audit_camera(
    camera_ip: str, *,
    port: int = 80, username: str, password: str,
    timeout_seconds: float = 3.0, opener_factory=build_opener,
) -> dict:
    """Fetch two read-only endpoints; Digest challenge may retry each GET."""
    _url(camera_ip, port, "101")
    if (not isinstance(username, str) or not 1 <= len(username) <= 128 or
            not isinstance(password, str) or not 1 <= len(password) <= 256 or
            type(timeout_seconds) not in (float, int) or
            not math.isfinite(timeout_seconds) or
            not 0.5 <= timeout_seconds <= 5):
        raise CameraAuditUnavailable("Camera operator configuration unavailable")
    manager = HTTPPasswordMgrWithDefaultRealm()
    # Authenticate both sibling paths (101 and 102) under one camera root.
    manager.add_password(None, f"http://{camera_ip}:{port}/", username, password)
    try:
        opener = opener_factory(HTTPDigestAuthHandler(manager), _NoRedirect(),
                                ProxyHandler({}))
        channels = []
        for channel in _CHANNELS:
            url = _url(camera_ip, port, channel)
            response = opener.open(
                Request(url, headers={"Accept": "application/xml"}, method="GET"),
                timeout=timeout_seconds,
            )
            try:
                content_type = response.headers.get("Content-Type", "").lower()
                if ("xml" not in content_type or
                        not content_type.startswith(("application/", "text/"))):
                    raise CameraAuditUnavailable("Unexpected camera metadata type")
                data = response.read(MAX_XML_BYTES + 1)
            finally:
                response.close()
            channels.append(parse_stream_xml(data, channel))
    except CameraAuditUnavailable:
        raise
    except Exception:
        # HTTP Digest, socket, XML errors may contain device identifiers/secrets.
        raise CameraAuditUnavailable("Hikvision ISAPI read-only audit unavailable") from None
    sub = channels[1]
    main = channels[0]
    preferred = (
        "102" if sub["codec"] in ("H.264", "H.265")
        else "101" if main["codec"] in ("H.264", "H.265")
        else None
    )
    return {
        "type": "viil.camera.hikvision_stream_audit.v1",
        "result": "read_only_metadata",
        "channels": channels,
        "recommended_edge_channel": preferred,
        "http_mjpeg_substream_configured": sub["codec"] == "MJPEG",
        "mjpeg_frames_verified": False,
        "rtsp_frames_decoded": False,
        "edge_inference_run": False,
        "camera_settings_modified": False,
        "authorization_for_video_granted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Read-only Hikvision ISAPI stream audit; NO VIDEO")
    parser.add_argument("--camera-ip", required=True, help="RFC1918 IPv4 camera")
    parser.add_argument("--http-port", type=int, default=80, choices=(80, 8080))
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    args = parser.parse_args(argv)
    username = os.environ.get("VIIL_HIK_HTTP_USER", "")
    password = os.environ.get("VIIL_HIK_HTTP_PASS", "")
    try:
        report = audit_camera(
            args.camera_ip, port=args.http_port, username=username,
            password=password, timeout_seconds=args.timeout_seconds,
        )
    except CameraAuditUnavailable:
        print(json.dumps({"type": "viil.camera.hikvision_stream_audit.v1",
                          "result": "unavailable", "video_decoded": False,
                          "camera_settings_modified": False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
