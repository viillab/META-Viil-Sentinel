import json
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.evaluation import evaluate_manifest, main
from sentinel_edge.pose_traces import frame_to_trace_record


def record(t, *, horizontal=False, sitting=False):
    if horizontal:
        shoulder_x, shoulder_y, hip_x, hip_y = 0.23, 0.78, 0.57, 0.78
    elif sitting:
        shoulder_x, shoulder_y, hip_x, hip_y = 0.5, 0.48, 0.5, 0.78
    else:
        shoulder_x, shoulder_y, hip_x, hip_y = 0.5, 0.25, 0.5, 0.53
    return frame_to_trace_record(PoseFrame(
        timestamp_ms=t,
        landmarks={
            11: Landmark(shoulder_x - 0.045, shoulder_y, 0.98),
            12: Landmark(shoulder_x + 0.045, shoulder_y, 0.98),
            23: Landmark(hip_x - 0.05, hip_y, 0.98),
            24: Landmark(hip_x + 0.05, hip_y, 0.98),
        },
    ))


def manifest_data(tmp_path: Path, *, rights="Team-staged and explicitly authorized"):
    fall = [record(t) for t in (0, 100, 200)]
    fall += [record(t, horizontal=True) for t in (300, 500, 700, 850)]
    sit = [record(t) for t in (0, 100, 200)]
    sit += [record(t, sitting=True) for t in (300, 500, 700, 850)]
    (tmp_path / "fall.pose.jsonl").write_text("\n".join(fall) + "\n", encoding="utf-8")
    (tmp_path / "sit.pose.jsonl").write_text("\n".join(sit) + "\n", encoding="utf-8")
    payload = {
        "version": 1,
        "permission_basis": rights,
        "clips": [
            {"id": "f1", "trace": "fall.pose.jsonl",
             "expected_fall": True, "onset_ms": 300},
            {"id": "s1", "trace": "sit.pose.jsonl", "expected_fall": False},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def test_clip_level_precision_recall_latency_and_false_alerts(tmp_path):
    path, _ = manifest_data(tmp_path)
    result = evaluate_manifest(path)
    assert result["evaluation_type"] == "clip-level-pose-heuristic"
    assert result["num_clips"] == 2
    assert result["model_calibrated"] is False
    assert result["clinically_validated"] is False
    assert result["metrics"]["f1"] == 1.0  # Synthetic fixtures ONLY
    assert result["clips"][0]["predicted_fall"] is True
    assert result["clips"][0]["latency_ms"] == 550
    assert result["clips"][1]["predicted_fall"] is False
    assert result["false_candidates_in_negative_clips"] == 0
    assert result["false_candidates_per_negative_hour"] == 0.0
    assert "Team-staged" not in json.dumps(result)  # Never repeat permission contents


def test_cli_json_output(tmp_path, capsys):
    path, _ = manifest_data(tmp_path)
    assert main(["--manifest", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["metrics"]["true_positive"] == 1


def test_reject_missing_consent_and_duplicate_ids(tmp_path):
    path, data = manifest_data(tmp_path, rights="")
    with pytest.raises(ValueError, match="consent or license"):
        evaluate_manifest(path)
    data["permission_basis"] = "staged"
    data["clips"][1]["id"] = "f1"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        evaluate_manifest(path)


def test_reject_path_traversal_and_absolute_paths(tmp_path):
    path, data = manifest_data(tmp_path)
    data["clips"][0]["trace"] = "../outside.jsonl"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="relative"):
        evaluate_manifest(path)
    data["clips"][0]["trace"] = str((tmp_path / "fall.pose.jsonl").resolve())
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="relative"):
        evaluate_manifest(path)


def test_reject_missing_label_and_bad_onset(tmp_path):
    path, data = manifest_data(tmp_path)
    data["clips"][0]["expected_fall"] = "yes"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="boolean"):
        evaluate_manifest(path)
    data["clips"][0]["expected_fall"] = True
    data["clips"][0]["onset_ms"] = -5
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="onset"):
        evaluate_manifest(path)


def test_empty_negative_duration_produces_null_rate(tmp_path):
    path, data = manifest_data(tmp_path)
    data["clips"] = data["clips"][:1]
    path.write_text(json.dumps(data), encoding="utf-8")
    report = evaluate_manifest(path)
    assert report["false_candidates_per_negative_hour"] is None
