import pytest

from sentinel_edge.runner import parse_args


def test_opt_in_pose_trace_export_required(tmp_path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"not an actual model")
    trace = tmp_path / "local.pose.jsonl"
    base = ["--source", "consented-offline.mp4", "--model", str(model)]
    with pytest.raises(SystemExit):
        parse_args(base + ["--trace-output", str(trace)])
    with pytest.raises(SystemExit):
        parse_args(base + ["--trace-output", str(tmp_path / "other.jsonl"),
                           "--acknowledge-pose-privacy"])
    valid = parse_args(base + ["--trace-output", str(trace), "--acknowledge-pose-privacy"])
    assert valid.trace_output == trace
    trace.write_text("already exists", encoding="utf-8")
    with pytest.raises(SystemExit):
        parse_args(base + ["--trace-output", str(trace), "--acknowledge-pose-privacy"])
