"""Bounded multi-camera launcher tests: no real camera or process is started."""
import json

import pytest

from sentinel_edge.camera_fleet import run_fleet


def test_multiple_camera_workers_use_distinct_env_secret_scopes(tmp_path, monkeypatch):
    registry = tmp_path / "fleet.json"
    registry.write_text(json.dumps({
        "schema_version": "viil.edge.camera_registry.v1",
        "cameras": [
            {"id": "cam-rtsp-a", "kind": "rtsp", "rtsp_env": "VIIL_CAM_A"},
            {"id": "cam-rtsp-b", "kind": "rtsp", "rtsp_env": "VIIL_CAM_B"},
            {"id": "cam-usb", "kind": "usb", "device_index": 2},
        ],
    }), encoding="utf-8")
    task = tmp_path / "test.task"
    task.write_bytes(b"synthetic")
    monkeypatch.setenv("VIIL_CAM_A", "rtsp://192.168.1.11/live")
    monkeypatch.setenv("VIIL_CAM_B", "rtsp://10.2.3.4:8554/stream")
    captured = []

    class Child:
        def wait(self, timeout=None):
            return 0

    def spawn(args, **options):
        captured.append((args, options))
        return Child()

    assert run_fleet(
        registry_path=registry,
        camera_ids=["cam-rtsp-a", "cam-rtsp-b", "cam-usb"],
        model=task, max_frames=300, launcher=spawn,
    ) == 0
    assert len(captured) == 3
    for args, options in captured:
        assert "--source" in args and "camera" in args
        assert options["shell"] is False
        assert options["stderr"] is not None
        assert "rtsp://" not in str(args)
        assert "--max-frames" in args
    assert "VIIL_CAM_B" not in captured[0][1]["env"]
    assert "VIIL_CAM_A" not in captured[1][1]["env"]
    assert "VIIL_CAM_A" not in captured[2][1]["env"]
    assert "VIIL_CAM_B" not in captured[2][1]["env"]
    assert "VIIL_CAM_A" in captured[0][1]["env"]
    assert "VIIL_CAM_B" in captured[1][1]["env"]


def test_invalid_fleet_fails_before_starting_any_process(tmp_path, monkeypatch):
    registry = tmp_path / "fleet.json"
    registry.write_text(json.dumps({
        "schema_version": "viil.edge.camera_registry.v1",
        "cameras": [
            {"id": "safe", "kind": "usb", "device_index": 0},
            {"id": "remote", "kind": "rtsp", "rtsp_env": "VIIL_REMOTE_CAM"},
        ],
    }), encoding="utf-8")
    task = tmp_path / "test.task"
    task.write_bytes(b"synthetic")
    monkeypatch.setenv("VIIL_REMOTE_CAM", "rtsp://8.8.8.8/live")
    spawned = []
    def spawn(*_a, **_kw):
        spawned.append(True)
        raise AssertionError("MUST NOT spawn")
    with pytest.raises(ValueError):
        run_fleet(registry_path=registry, camera_ids=["safe", "remote"],
                  model=task, max_frames=300, launcher=spawn)
    with pytest.raises(ValueError):
        run_fleet(registry_path=registry, camera_ids=["safe", "safe"],
                  model=task, max_frames=300, launcher=spawn)
    with pytest.raises(ValueError):
        run_fleet(registry_path=registry, camera_ids=["safe"], model=task,
                  max_frames=0, launcher=spawn)
    assert spawned == []


def test_fleet_returns_error_on_one_failed_worker(tmp_path):
    registry = tmp_path / "fleet.json"
    registry.write_text(json.dumps({
        "schema_version": "viil.edge.camera_registry.v1",
        "cameras": [
            {"id": "a", "kind": "usb", "device_index": 0},
            {"id": "b", "kind": "usb", "device_index": 1},
        ],
    }), encoding="utf-8")
    task = tmp_path / "test.task"
    task.write_bytes(b"synthetic")
    results = iter([0, 2])

    class Child:
        def __init__(self, rc):
            self.rc = rc
        def wait(self, timeout=None):
            return self.rc
    def spawn(*_a, **_kw):
        return Child(next(results))
    assert run_fleet(
        registry_path=registry, camera_ids=["a", "b"], model=task,
        max_frames=12, launcher=spawn,
    ) == 2
