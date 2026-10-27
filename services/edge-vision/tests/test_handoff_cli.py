"""CLI handoff tests use only invented numerical torso landmarks."""
import json

import pytest

from sentinel_edge.handoff_cli import export_trace, main


def test_synthetic_trace_can_export_unverified_candidate_without_upload(capsys):
    assert main([
        "--trace", "examples/synthetic/fall.jsonl", "--source-id", "fictional-01"
    ]) == 0
    output = capsys.readouterr().out.splitlines()
    assert len(output) == 1
    event = json.loads(output[0])
    assert event["source_id"] == "fictional-01"
    assert event["simulated"] is True
    assert event["confirmed_fall"] is False
    assert event["human_review_required"] is True
    assert event["delivery_mode"] == "local_stdout_only"


def test_nonfall_trace_outputs_no_events(capsys):
    assert main(["--trace", "examples/synthetic/sitting.jsonl"]) == 0
    assert capsys.readouterr().out == ""


def test_real_trace_requires_explicit_authorization(tmp_path):
    trace = tmp_path / "staged.pose.jsonl"
    trace.write_text('{"timestamp_ms":0,"landmarks":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="authorization"):
        export_trace(trace, source_id="test", provenance="consented_staged_video")


def test_malformed_trace_cannot_produce_partial_export(tmp_path, capsys):
    synthetic = (tmp_path / "bad.pose.jsonl")
    source = __import__("pathlib").Path("examples/synthetic/fall.jsonl")
    synthetic.write_text(source.read_text(encoding="utf-8") + "{ invalid json \n",
                         encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["--trace", str(synthetic)])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


def test_provenance_mismatch_is_rejected(tmp_path):
    trace = tmp_path / "staged.pose.jsonl"
    trace.write_text('{"timestamp_ms":0,"landmarks":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic"):
        export_trace(trace, source_id="test", authorized=True)
