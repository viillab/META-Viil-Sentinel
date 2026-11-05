"""Pure smoke CLI/statistic validation; no downloads, cameras or model loading."""
from pathlib import Path

import pytest

from sentinel_edge.model_smoke import latency_summary, run_smoke, main


def test_percentiles_and_mean_are_deterministic():
    summary = latency_summary([10.0, 20.0, 30.0, 40.0])
    assert summary["mean_ms"] == 25.0
    assert summary["p50_ms"] == 20.0
    assert summary["p95_ms"] == 40.0
    assert summary["max_ms"] == 40.0


@pytest.mark.parametrize("invalid", [[], [-2], [float("nan")], [float("inf")]])
def test_latency_rejects_invalid_samples(invalid):
    with pytest.raises(ValueError):
        latency_summary(invalid)


def test_invalid_model_path_rejected_without_importing_mediapipe(tmp_path: Path):
    with pytest.raises(ValueError, match="local .task"):
        run_smoke(tmp_path / "missing.task")
    not_model = tmp_path / "fake.txt"
    not_model.write_text("not a model")
    with pytest.raises(ValueError, match="local .task"):
        run_smoke(not_model)


def test_invalid_frame_bounds_rejected_before_model_io(tmp_path: Path):
    for bad in (0, 301):
        with pytest.raises(ValueError, match="frames"):
            run_smoke(tmp_path / "missing.task", frames=bad)
    for bad in (20, 4096):
        with pytest.raises(ValueError, match="size"):
            run_smoke(tmp_path / "missing.task", size=bad)


def test_main_reports_missing_model(capsys):
    with pytest.raises(SystemExit) as err:
        main(["--model", "missing.task"])
    assert err.value.code == 2
    assert "local .task" in capsys.readouterr().err
