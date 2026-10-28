"""Offline Hikvision over Tailscale *subnet-route* contract checks.

No sockets, Tailscale client, camera, privacy grant or real password required.
"""
import json
from pathlib import Path

import pytest

from sentinel_edge.camera_inputs import load_camera_registry, resolve_camera


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "examples" / "camera_registry.tailscale.example.json"
ENV = "VIIL_HIK_TAILSCALE_RTSP"


def test_tailscale_registry_contains_only_a_pseudonymous_id_and_env_reference():
    original = REGISTRY.read_text(encoding="utf-8")
    parsed = json.loads(original)
    assert set(parsed) == {"schema_version", "cameras"}
    assert parsed["cameras"] == [{
        "id": "hik-tailnet-demo", "kind": "rtsp", "rtsp_env": ENV,
    }]
    assert "rtsp://" not in original
    assert "192.168." not in original
    assert "password" not in original.lower()
    camera = load_camera_registry(REGISTRY)["hik-tailnet-demo"]
    assert camera.kind == "rtsp"
    assert camera.rtsp_env == ENV


@pytest.mark.parametrize("channel", ["101", "102"])
def test_private_site_lan_hikvision_rtsp_over_tailnet_route_is_supported(channel):
    """Private site LAN IP, NOT the CGNAT IP assigned to Tailscale gateways."""
    fake_user_and_password = "sample_reader:sample%40test"
    url = (
        f"rtsp://{fake_user_and_password}@192.168.88.10:554"
        f"/Streaming/Channels/{channel}"
    )
    selected = load_camera_registry(REGISTRY)["hik-tailnet-demo"]
    assert resolve_camera(selected, environment={ENV: url}) == ("rtsp", url)


@pytest.mark.parametrize("unsafe", [
    "rtsp://100.101.102.103:554/Streaming/Channels/102",
    "rtsp://198.51.100.10:554/Streaming/Channels/102",
    "rtsp://site-camera.internal:554/Streaming/Channels/102",
    "rtsp://192.168.88.10:554/Streaming/Channels/102%0d%0aINJECT",
    "https://192.168.88.10:554/Streaming/Channels/102",
])
def test_overlay_cgnat_public_dns_and_injection_are_not_trusted_rtsp_sources(unsafe):
    selected = load_camera_registry(REGISTRY)["hik-tailnet-demo"]
    with pytest.raises(ValueError, match="redacted") as error:
        resolve_camera(selected, environment={ENV: unsafe})
    assert unsafe not in str(error.value)


def test_nonstandard_vendor_port_remains_explicit_opt_in():
    selected = load_camera_registry(REGISTRY)["hik-tailnet-demo"]
    value = "rtsp://192.168.88.10:10554/Streaming/Channels/102"
    with pytest.raises(ValueError, match="redacted"):
        resolve_camera(selected, environment={ENV: value})
    assert resolve_camera(
        selected, environment={ENV: value}, extra_rtsp_port=10554,
    ) == ("rtsp", value)


def test_no_env_secret_fails_without_logging_or_network():
    selected = load_camera_registry(REGISTRY)["hik-tailnet-demo"]
    with pytest.raises(ValueError, match="redacted"):
        resolve_camera(selected, environment={})
