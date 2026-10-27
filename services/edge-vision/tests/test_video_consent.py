"""Explicit CLI video consent gate."""
from sentinel_edge.video_benchmark import main
import pytest


def test_cli_requires_explicit_video_consent(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--manifest", "private.json", "--model", "pose.task"])
    assert exc.value.code == 2
    assert "--confirm-consent" in capsys.readouterr().err
