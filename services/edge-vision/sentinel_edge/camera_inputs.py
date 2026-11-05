"""Vendor-neutral, local-only camera registry.

RTSP works with compatible IP cameras/NVRs regardless of brand; UVC indexes
work with local USB cameras. Registry files contain NO passwords, stream URLs,
IP addresses, personal data or frame content. One camera is selected per
runner process; run separate authorized processes for multiple simultaneous
cameras. This is not network-wide discovery or an ONVIF controller.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from sentinel_edge.camera_health import validate_rtsp_env
from sentinel_edge.handoff import SOURCE_ID_PATTERN


MAX_CAMERA_REGISTRY_BYTES = 16_384
MAX_CAMERAS = 16
CAMERA_ENV_PATTERN = re.compile(r"^VIIL_[A-Z0-9_]{1,100}$", re.ASCII)
USB_SOURCE_PATTERN = re.compile(r"^usb:([0-9]{1,2})$", re.ASCII)


@dataclass(frozen=True)
class CameraInput:
    camera_id: str
    kind: str
    rtsp_env: str | None = None
    device_index: int | None = None


def parse_usb_index(source: str) -> int | None:
    """Numeric legacy webcam input or usb:<index>; bounded local device indexes."""
    match = USB_SOURCE_PATTERN.fullmatch(source)
    if match:
        index = int(match.group(1))
    elif source.isascii() and source.isdecimal():
        index = int(source)
    else:
        return None
    if not 0 <= index <= 15:
        raise ValueError("USB/UVC camera index must be 0..15")
    return index


def load_camera_registry(path: Path) -> dict[str, CameraInput]:
    """Read a small strict local JSON catalog. Never echo the file or contents."""
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_CAMERA_REGISTRY_BYTES:
            raise ValueError("Invalid camera registry size")
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        raise ValueError("Camera registry is missing or invalid (redacted)") from None
    if (not isinstance(doc, dict)
            or set(doc) != {"schema_version", "cameras"}
            or doc["schema_version"] != "viil.edge.camera_registry.v1"
            or not isinstance(doc["cameras"], list)
            or not 1 <= len(doc["cameras"]) <= MAX_CAMERAS):
        raise ValueError("Camera registry schema is invalid")
    cameras: dict[str, CameraInput] = {}
    for row in doc["cameras"]:
        if not isinstance(row, dict) or row.get("kind") not in ("rtsp", "usb"):
            raise ValueError("Camera registry entry kind is invalid")
        kind = row["kind"]
        expected = {"id", "kind", "rtsp_env" if kind == "rtsp" else "device_index"}
        if set(row) != expected:
            raise ValueError("Camera registry entry fields are invalid")
        camera_id = row["id"]
        if (not isinstance(camera_id, str)
                or SOURCE_ID_PATTERN.fullmatch(camera_id) is None
                or camera_id in cameras):
            raise ValueError("Camera registry IDs must be unique pseudonymous slugs")
        if kind == "rtsp":
            env = row["rtsp_env"]
            if not isinstance(env, str) or CAMERA_ENV_PATTERN.fullmatch(env) is None:
                raise ValueError("Camera secret must be referenced by VIIL_ environment name")
            cameras[camera_id] = CameraInput(camera_id, kind, rtsp_env=env)
        else:
            index = row["device_index"]
            if type(index) is not int or not 0 <= index <= 15:
                raise ValueError("USB device index must be integer 0..15")
            cameras[camera_id] = CameraInput(camera_id, kind, device_index=index)
    return cameras


def resolve_camera(
    camera: CameraInput, *,
    environment: dict[str, str] | None = None,
    extra_rtsp_port: int | None = None,
) -> tuple[str, str | int]:
    """Return capture kind and input. Never stringify returned secret in logs."""
    if camera.kind == "usb":
        return "usb", camera.device_index
    if camera.kind == "rtsp" and camera.rtsp_env:
        return "rtsp", validate_rtsp_env(
            camera.rtsp_env, environment, extra_port=extra_rtsp_port,
        )
    raise ValueError("Unsupported camera definition")


def open_camera_capture(cv2, kind: str, source: str | int):
    """One interface for USB and any vendor's RTSP device."""
    if kind == "rtsp":
        from sentinel_edge.camera_health import open_rtsp_capture
        return open_rtsp_capture(cv2, source)
    if kind == "usb":
        if type(source) is not int or not 0 <= source <= 15:
            raise ValueError("Invalid USB camera index")
        return cv2.VideoCapture(source)
    raise ValueError("Unsupported live camera kind")
