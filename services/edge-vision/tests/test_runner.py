from pathlib import Path

import pytest

from sentinel_edge.runner import parse_args, timestamp_for_frame


def test_video_timestamp_is_strictly_monotonic():
    assert timestamp_for_frame(0, 30, -1) == 0
    assert timestamp_for_frame(1, 30, 0) == 33
    assert timestamp_for_frame(1, 30, 33) == 34


def test_requires_model_asset(tmp_path: Path):
    with pytest.raises(SystemExit):
        parse_args(["--source", "staged.mp4", "--model", str(tmp_path / "absent.task")])


def test_parser_accepts_existing_model_without_loading_it(tmp_path: Path):
    model = tmp_path / "model.task"
    model.write_bytes(b"placeholder for parser test only")
    args = parse_args(["--source", "0", "--model", str(model), "--max-frames", "12"])
    assert args.max_frames == 12
    assert args.source == "0"
