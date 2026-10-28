"""RTSP source safety checks (offline; no camera/network required)."""
from pathlib import Path

import pytest

from sentinel_edge.runner import parse_args


def test_rtsp_requires_env_and_consent(tmp_path: Path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"placeholder")
    base = ["--source", "rtsp", "--model", str(model)]
    with pytest.raises(SystemExit):
        parse_args(base)
    with pytest.raises(SystemExit):
        parse_args(base + ["--rtsp-env", "CAMERA_URL"])
    with pytest.raises(SystemExit):
        parse_args(base + ["--rtsp-env", "VIIL_CAMERA_URL", "--candidate-format", "v1"])
    args = parse_args(base + ["--rtsp-env", "VIIL_CAMERA_URL",
                              "--candidate-format", "v1", "--confirm-consent"])
    assert args.rtsp_env == "VIIL_CAMERA_URL"


def test_network_credentials_never_accepted_as_cli_source(tmp_path: Path, capsys):
    model = tmp_path / "pose.task"
    model.write_bytes(b"placeholder")
    secret = "UNSAFE_TEST_PASSWORD"
    with pytest.raises(SystemExit):
        parse_args(["--source", "rtsp://camera:" + secret + "@127.0.0.1/Streaming/Channels/102",
                    "--model", str(model)])
    assert secret not in capsys.readouterr().err
