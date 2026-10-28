"""Security and multi-vendor camera adapter regression tests, no network devices."""
import json
import sys
from types import SimpleNamespace as NS

import pytest

from sentinel_edge.camera_health import validate_rtsp_env, main as health_main
from sentinel_edge.camera_inputs import (
    load_camera_registry, open_camera_capture, parse_usb_index, resolve_camera,
)
from sentinel_edge import runner


def save_registry(path, cameras):
    path.write_text(json.dumps({
        "schema_version": "viil.edge.camera_registry.v1", "cameras": cameras,
    }), encoding="utf-8")


def test_multi_vendor_rtsp_usb_registry_contains_no_credentials(tmp_path):
    catalog = tmp_path / "cameras.json"
    save_registry(catalog, [
        {"id": "reception-axis", "kind": "rtsp", "rtsp_env": "VIIL_AXIS_RTSP"},
        {"id": "entrance-onvif", "kind": "rtsp", "rtsp_env": "VIIL_GENERIC_RTSP"},
        {"id": "operator-usb", "kind": "usb", "device_index": 2},
    ])
    cameras = load_camera_registry(catalog)
    assert len(cameras) == 3
    assert resolve_camera(cameras["operator-usb"]) == ("usb", 2)
    env = {
        "VIIL_AXIS_RTSP": "rtsp://viewer:SECRET@192.168.10.11:8554/axis-media/media.amp",
        "VIIL_GENERIC_RTSP": "rtsp://10.2.3.4:554/live",
    }
    assert resolve_camera(cameras["reception-axis"], environment=env)[0] == "rtsp"
    assert resolve_camera(cameras["entrance-onvif"], environment=env)[0] == "rtsp"
    assert "SECRET" not in catalog.read_text(encoding="utf-8")


def test_compatible_vendor_custom_rtsp_port_requires_explicit_permission():
    env = {"VIIL_CAM_URL": "rtsp://172.20.1.19:10554/stream1"}
    with pytest.raises(ValueError):
        validate_rtsp_env("VIIL_CAM_URL", env)
    assert validate_rtsp_env("VIIL_CAM_URL", env, extra_port=10554) == env["VIIL_CAM_URL"]


@pytest.mark.parametrize("url", [
    "rtsp://8.8.8.8:554/live",
    "rtsp://127.0.0.1:554/live",
    "rtsp://169.254.169.254:554/metadata",
    "rtsp://0.0.0.0:554/live",
    "rtsp://224.0.0.1:554/live",
    "rtsp://camera.local/live",
    "rtsp://example.com/live",
    "rtsp://192.168.1.3:9999/live",
    "rtsps://192.168.1.3/live",
    "http://192.168.1.3/live",
    "rtsp://192.168.1.3/stream%0d%0aINJECT",
    "rtsp://192.168.1.3/stream%5csecret",
    "rtsp://192.168.1.3:554/live#fragment",
    "rtsp://user:pw@evil@192.168.1.3/live",
    "rtsp://[::1]/live",
    "rtsp://[fe80::1]/live",
    "rtsp://192.168.1.3:0/live",
])
def test_insecure_or_ambiguous_rtsp_destination_refused(url):
    with pytest.raises(ValueError, match="redacted"):
        validate_rtsp_env("VIIL_TEST_URL", {"VIIL_TEST_URL": url})


def test_ipv6_ula_supported_without_dns():
    env = {"VIIL_RTSP_URL": "rtsp://[fd00::1234]:8554/live"}
    assert validate_rtsp_env("VIIL_RTSP_URL", env) == env["VIIL_RTSP_URL"]


@pytest.mark.parametrize("bad", [0, -1, 65536, "554", True])
def test_invalid_custom_port_fails_closed(bad):
    with pytest.raises(ValueError):
        validate_rtsp_env("VIIL_RTSP_URL", {"VIIL_RTSP_URL": "rtsp://10.1.1.1/live"},
                          extra_port=bad)


@pytest.mark.parametrize("camera_rows", [
    [{"id": "same", "kind": "usb", "device_index": 1},
     {"id": "same", "kind": "usb", "device_index": 2}],
    [{"id": "invalid person", "kind": "usb", "device_index": 0}],
    [{"id": "cam1", "kind": "usb", "device_index": -1}],
    [{"id": "cam1", "kind": "usb", "device_index": True}],
    [{"id": "cam1", "kind": "rtsp", "rtsp_env": "SECRET_PASSWORD"}],
    [{"id": "cam1", "kind": "rtsp", "rtsp_env": "VIIL_X",
      "url": "rtsp://secret@10.1.1.2/live"}],
])
def test_registry_rejects_bad_or_secret_bearing_entries(tmp_path, camera_rows):
    registry = tmp_path / "cameras.json"
    save_registry(registry, camera_rows)
    with pytest.raises(ValueError):
        load_camera_registry(registry)


def test_oversized_catalog_rejected(tmp_path):
    registry = tmp_path / "secret.json"
    registry.write_text("x" * 20000, encoding="utf-8")
    with pytest.raises(ValueError, match="redacted"):
        load_camera_registry(registry)


@pytest.mark.parametrize("source, index", [
    ("0", 0), ("usb:0", 0), ("usb:3", 3), ("15", 15),
])
def test_usb_camera_aliases(source, index):
    assert parse_usb_index(source) == index


def test_usb_camera_not_rtsp_and_no_network():
    class Cv2:
        @staticmethod
        def VideoCapture(value):
            assert value == 3
            return "USB"
    assert open_camera_capture(Cv2, "usb", 3) == "USB"
    with pytest.raises(ValueError):
        open_camera_capture(Cv2, "rtmp", "rtmp://192.168.1.1/live")


def test_generic_camera_cli_preserves_source_isolation(tmp_path, monkeypatch):
    catalog = tmp_path / "cameras.json"
    save_registry(catalog, [
        {"id": "lab-usb", "kind": "usb", "device_index": 1},
        {"id": "lab-rtsp", "kind": "rtsp", "rtsp_env": "VIIL_LAB_RTSP"},
    ])
    model = tmp_path / "pose.task"
    model.write_bytes(b"model-placeholder")
    common = ["--source", "camera", "--camera-registry", str(catalog),
              "--model", str(model), "--candidate-format", "v1", "--confirm-consent"]
    usb = runner.parse_args(common + ["--camera-id", "lab-usb"])
    assert usb.selected_camera.kind == "usb"
    net = runner.parse_args(common + ["--camera-id", "lab-rtsp", "--rtsp-retries", "1"])
    assert net.selected_camera.kind == "rtsp"
    with pytest.raises(SystemExit):
        runner.parse_args(common + ["--camera-id", "lab-usb", "--rtsp-retries", "1"])
    with pytest.raises(SystemExit):
        runner.parse_args(common + ["--camera-id", "NOT_FOUND"])
    with pytest.raises(SystemExit):
        runner.parse_args(common + ["--camera-id", "lab-rtsp", "--rtsp-allow-port", "0"])

    # Patch runtime imports so the test never activates an actual camera.
    monkeypatch.setenv("VIIL_LAB_RTSP", "rtsp://10.3.2.1:8554/live")
    captured = {}
    def fake_rtsp(args, cv2, mp, source, *, source_id=None):
        captured.update(url=source, id=source_id)
        return 0
    monkeypatch.setattr(runner, "_run_rtsp_retry_mode", fake_rtsp)
    monkeypatch.setitem(sys.modules, "cv2", NS())
    monkeypatch.setitem(sys.modules, "mediapipe", NS())
    assert runner.main(common + ["--camera-id", "lab-rtsp", "--rtsp-retries", "1"]) == 0
    assert captured == {"url": "rtsp://10.3.2.1:8554/live", "id": "lab-rtsp"}


def test_health_probe_accepts_registry_and_rejects_usb(monkeypatch, tmp_path, capsys):
    from sentinel_edge import camera_health
    catalog = tmp_path / "cameras.json"
    save_registry(catalog, [
        {"id": "cam1", "kind": "rtsp", "rtsp_env": "VIIL_TEST_CAM"},
        {"id": "usb1", "kind": "usb", "device_index": 0},
    ])
    monkeypatch.setenv("VIIL_TEST_CAM", "rtsp://192.168.2.3/live")
    class Capture:
        def isOpened(self): return True
        def read(self): return True, object()
        def release(self): pass
    monkeypatch.setattr(camera_health, "open_rtsp_capture", lambda cv2, url: Capture())
    monkeypatch.setitem(sys.modules, "cv2", NS())
    base = ["--camera-registry", str(catalog), "--confirm-authorized-camera",
            "--frames", "2"]
    assert health_main(base + ["--camera-id", "cam1"]) == 0
    assert json.loads(capsys.readouterr().out)["frames_read"] == 2
    with pytest.raises(SystemExit):
        health_main(base + ["--camera-id", "usb1"])
    assert str(catalog) not in capsys.readouterr().err
