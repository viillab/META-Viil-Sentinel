"""Hikvision same-camera stream fallback; no network access or secret logging.

Only the operator-approved primary and alternate streams can be selected.
Windows routing (LAN/Tailscale) remains independent from the stream URL.
"""

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from sentinel_edge.camera_health import validate_rtsp_env

_CHANNEL = re.compile(r"^/Streaming/Channels/([1-9][0-9]*)(0[12])/?$", re.ASCII)


@dataclass(frozen=True, repr=False)
class ApprovedStreamPair:
    primary: str
    fallback: str

    def for_attempt(self, index: int) -> str:
        if type(index) is not int or index < 0:
            raise ValueError("Invalid bounded attempt index")
        return self.primary if index % 2 == 0 else self.fallback


def validate_same_camera_streams(primary: str, fallback: str) -> None:
    """The two RTSP URLs must identify the SAME private camera and channel.

    Both inputs must first pass validate_rtsp_env. Never include raw inputs
    in failures, repr, diagnostics or event metadata.
    """
    try:
        p = urlsplit(primary)
        f = urlsplit(fallback)
        pm = _CHANNEL.fullmatch(p.path)
        fm = _CHANNEL.fullmatch(f.path)
        accepted = (
            p.scheme == f.scheme == "rtsp"
            and p.netloc == f.netloc
            and p.query == f.query
            and not p.fragment and not f.fragment
            and pm is not None and fm is not None
            and pm.group(1) == fm.group(1)
            and pm.group(2) != fm.group(2)
        )
        if not accepted:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "Fallback must be the opposite Hikvision stream of the same camera (redacted)"
        ) from None


def resolve_hikvision_stream_pair(
    primary_env: str,
    fallback_env: str,
    *,
    extra_port: int | None = None,
    environment: dict[str, str] | None = None,
) -> ApprovedStreamPair:
    """Fail closed on different camera, credentials, RTSP port, or NVR channel."""
    if primary_env == fallback_env:
        raise ValueError("Primary and fallback variables must differ (redacted)")
    primary = validate_rtsp_env(primary_env, environment, extra_port=extra_port)
    fallback = validate_rtsp_env(fallback_env, environment, extra_port=extra_port)
    validate_same_camera_streams(primary, fallback)
    return ApprovedStreamPair(primary, fallback)
