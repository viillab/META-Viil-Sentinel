"""Live output handoff is opt-in and requires a pseudonymous source ID."""
import pytest

from sentinel_edge.runner import parse_args


def test_real_runner_requires_consent_for_handoff(tmp_path, capsys):
    model = tmp_path / "pose.task"
    model.write_bytes(b"parser-only synthetic placeholder")
    base = ["--source", "0", "--model", str(model), "--candidate-format", "v1"]

    with pytest.raises(SystemExit) as exc:
        parse_args(base)
    assert exc.value.code == 2
    assert "confirm-consent" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        parse_args(base + ["--confirm-consent", "--source-id", "../private-person"])

    args = parse_args(base + ["--confirm-consent", "--source-id", "staged-camera-01"])
    assert args.candidate_format == "v1"
    assert args.confirm_consent is True


def test_legacy_runner_does_not_require_new_flag(tmp_path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"parser only")
    args = parse_args(["--source", "0", "--model", str(model)])
    assert args.candidate_format == "legacy"
