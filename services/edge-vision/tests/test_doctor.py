"""Readiness checks never load a model or access the webcam."""
from pathlib import Path

from sentinel_edge.doctor import _parse_version, probe, main


def test_version_check():
    assert _parse_version("0.10.20") == (0, 10, 20)
    assert _parse_version("0.10.33.dev") == (0, 10, 33)
    assert _parse_version("invalid") is None


def test_probe_does_not_treat_missing_model_as_ready(tmp_path):
    result = probe(model=tmp_path / "missing.task")
    assert result["checks"]["pose_model"]["ready"] is False
    assert result["ready_for_video_smoke_test"] is False
    assert result["tests_only_mode_available"] is True


def test_existing_nonempty_task_file_is_only_basic_asset_check(tmp_path: Path):
    model = tmp_path / "test.task"
    model.write_bytes(b"not a real model")
    result = probe(model=model)
    assert result["checks"]["pose_model"]["ready"] is True
    assert "inference" in result["checks"]["pose_model"]["asset_check"]


def test_cli_missing_model_reports_diagnostic(capsys):
    assert main([]) == 2
    assert '"ready_for_video_smoke_test": false' in capsys.readouterr().out
