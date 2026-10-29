"""Authorized Hikvision HTTP Digest MJPEG capture; in-memory JPEG -> BGR.

HTTP-MJPEG is model/firmware dependent. No camera configuration is changed.
The calling camera health/preview must verify genuine signed privacy consent
before opening and before/after every read. Never expose native URLs/secrets.
"""
from ipaddress import ip_address
import os
import re
from typing import Any
from urllib.parse import urlsplit
from urllib.request import (
    HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm,
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

from sentinel_edge.camera_health import PRIVATE_CAMERA_NETWORKS


MAX_JPEG_BYTES = 2 * 1024 * 1024
MAX_BUFFER_BYTES = MAX_JPEG_BYTES + 8192
READ_CHUNK_BYTES = 4096
_HTTP_PATH = re.compile(
    r"^/(?:ISAPI/)?Streaming/channels/102/httpPreview$", re.IGNORECASE,
)


def validate_http_mjpeg_env(
    name: str, environment: dict[str, str] | None = None, *,
    extra_port: int | None = None,
) -> str:
    """Only allow one exact MJPEG endpoint on a literal RFC1918 IPv4 camera."""
    env = os.environ if environment is None else environment
    if not isinstance(name, str) or not name.isidentifier() or not name.startswith("VIIL_"):
        raise ValueError("Invalid private camera environment variable")
    value = env.get(name)
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 512:
            raise ValueError
        parts = urlsplit(value)
        host = ip_address(parts.hostname or "")
        port = parts.port if parts.port is not None else 80
        if not (
            parts.scheme == "http"
            and host.version == 4
            and any(host in network for network in PRIVATE_CAMERA_NETWORKS)
            and port in ({80, 8080} | ({extra_port} if extra_port else set()))
            and _HTTP_PATH.fullmatch(parts.path)
            and not parts.username and not parts.password
            and not parts.query and not parts.fragment
            and all(32 <= ord(c) < 127 for c in value)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Missing or unsafe HTTP MJPEG source (redacted)") from None
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Digest credentials or data to another host.
        return None


class HTTPMJPEGCapture:
    """Open authorized HTTP Digest video, use bounded volatile JPEG buffering."""

    def __init__(
        self, cv2: Any, url: str, *,
        username: str,
        password: str,
        opener_factory=build_opener,
        timeout_seconds: float = 4.0,
    ):
        if not username or not password or len(username) > 128 or len(password) > 256:
            raise RuntimeError("Camera HTTP credentials are unavailable")
        # Defense in depth even if this adapter is called without the CLI.
        try:
            validate_http_mjpeg_env("VIIL_INTERNAL_HTTP", {"VIIL_INTERNAL_HTTP": url})
        except ValueError:
            raise RuntimeError("Unsafe HTTP camera endpoint (redacted)") from None
        self._response = None
        self._buffer = bytearray()
        self._cv2 = cv2
        self._opened = False
        try:
            manager = HTTPPasswordMgrWithDefaultRealm()
            manager.add_password(None, url, username, password)
            opener = opener_factory(
                HTTPDigestAuthHandler(manager), _NoRedirect(), ProxyHandler({}),
            )
            response = opener.open(
                Request(url, headers={"Accept": "multipart/x-mixed-replace"}),
                timeout=timeout_seconds,
            )
            self._response = response
            content_type = response.headers.get("Content-Type", "").lower()
            if not content_type.startswith("multipart/x-mixed-replace"):
                raise ValueError
            self._opened = True
        except Exception:
            self.release()
            # Native HTTP errors might include user-supplied secrets or URLs.
            raise RuntimeError("Authorized HTTP MJPEG stream unavailable") from None

    def isOpened(self) -> bool:
        return self._opened

    def get(self, _property: Any) -> float:
        return 0.0  # HTTP multipart does not advertise a reliable frame rate.

    def read(self):
        if not self._opened:
            return False, None
        try:
            import numpy as np
            while True:
                start = self._buffer.find(b"\xff\xd8")
                if start >= 0:
                    if start:
                        del self._buffer[:start]
                    end = self._buffer.find(b"\xff\xd9", 2)
                    if end >= 0:
                        jpeg = bytes(self._buffer[:end + 2])
                        del self._buffer[:end + 2]
                        if len(jpeg) > MAX_JPEG_BYTES:
                            raise ValueError
                        frame = self._cv2.imdecode(
                            np.frombuffer(jpeg, dtype=np.uint8), self._cv2.IMREAD_COLOR,
                        )
                        if frame is None:
                            raise ValueError
                        return True, frame
                    if len(self._buffer) > MAX_JPEG_BYTES:
                        raise ValueError
                elif len(self._buffer) > 2:
                    # Keep only potential first byte of JPEG marker.
                    self._buffer[:] = self._buffer[-1:]
                chunk = self._response.read(READ_CHUNK_BYTES)
                if not chunk:
                    return False, None
                self._buffer.extend(chunk)
                if len(self._buffer) > MAX_BUFFER_BYTES:
                    raise ValueError
        except Exception:
            raise RuntimeError("HTTP MJPEG frame decode interrupted") from None

    def release(self) -> None:
        response, self._response = self._response, None
        self._opened = False
        self._buffer.clear()
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def open_http_mjpeg_capture(
    cv2: Any, url: str, *,
    environment: dict[str, str] | None = None,
) -> HTTPMJPEGCapture:
    """Credentials are inherited from private env only, never from CLI URLs."""
    env = os.environ if environment is None else environment
    return HTTPMJPEGCapture(
        cv2, url, username=env.get("VIIL_HIK_HTTP_USER", ""),
        password=env.get("VIIL_HIK_HTTP_PASS", ""),
    )
