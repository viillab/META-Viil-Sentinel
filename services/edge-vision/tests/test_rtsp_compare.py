"""Paired camera-mode comparison tests use synthetic aggregate samples only."""
import json
from pathlib import Path

import pytest

from sentinel_edge.live_profile import LiveCycleProfiler
from sentinel_edge.pose_coverage import PoseCoverageMonitor
from sentinel_edge.rtsp_compare import (
    COVERAGE_FIELDS, PROFILE_FIELDS, _safe_record, compare_channels, main,
    validate_pair,
)


def records(*, frames=300, pose_every=5, duration=.02, interrupted=False,
            rss_bytes=512 * 1024 * 1024):
    profiler = LiveCycleProfiler(rss_sample=lambda: rss_bytes)
    coverage = PoseCoverageMonitor()
    for i in range(frames):
        seen = i % pose_every != 0
        profiler.observe(duration, seen, False)
        coverage.observe(seen, timestamp_ms=i * 50)
    return profiler.report(interrupted=interrupted), coverage.summary()


def test_compare_two_aggregate_modes_with_no_deployment_certification():
    main_profile, main_coverage = records(duration=.025)
    sub_profile, sub_coverage = records(duration=.015)
    report = compare_channels(main_profile, main_coverage, sub_profile, sub_coverage)
    assert report["schema_version"] == "viil.edge.rtsp_pair_comparison.v1"
    assert report["mainstream"]["frames_processed"] == 300
    assert report["mainstream"]["pose_coverage_percent"] == 80
    assert report["substream"]["provisional_technical_screen_passed"] is True
    assert report["mainstream"]["provisional_technical_screen_passed"] is True
    assert report["comparisons_not_a_recommendation"]["lower_cycle_p95"] == "substream"
    assert report["ground_truth_fall_accuracy_not_measured"] is True
    assert report["eligible_for_real_world_safety_deployment"] is False
    assert report["thirty_minute_endurance_not_verified"] is True
    assert "source_id" not in json.dumps(report)


def test_interrupted_profile_does_not_pass_provisional_screen():
    prof, coverage = records(interrupted=True)
    result = validate_pair(prof, coverage)
    assert result["provisional_technical_screen_passed"] is False
    assert "uninterrupted_session" in result["provisional_screen_unmet"]


def test_short_and_no_pose_sessions_are_not_promoted():
    prof, coverage = records(frames=20, pose_every=1)
    result = validate_pair(prof, coverage)
    assert result["pose_coverage_percent"] == 0
    assert "minimum_frames" in result["provisional_screen_unmet"]
    assert "minimum_recent_samples" in result["provisional_screen_unmet"]
    assert "minimum_pose_coverage" in result["provisional_screen_unmet"]


def test_missing_rss_remains_unverified_not_assumed_safe():
    prof, coverage = records(rss_bytes=None)
    result = validate_pair(prof, coverage)
    assert result["sampled_process_rss_max_mib"] is None
    assert result["provisional_technical_screen_passed"] is False
    assert "maximum_sampled_rss_mib" in result["provisional_screen_unmet"]


@pytest.mark.parametrize("mutation", [
    lambda p, c: p.update(frames_processed=299),
    lambda p, c: c.update(pose_observed_frames=299),
    lambda p, c: p.update(cycle_p95_ms=float("nan")),
    lambda p, c: p.update(cycle_samples=3000),
    lambda p, c: p.update(research_only=False),
    lambda p, c: p.update(source_id="private-camera-id"),
    lambda p, c: c.update(duration_gate_applied=False),
    lambda p, c: c.update(longest_no_pose_streak_frames=1000),
    lambda p, c: c.update(gap_threshold_ms=True),
])
def test_mismatched_malicious_or_impossible_records_refused(mutation):
    prof, coverage = records()
    mutation(prof, coverage)
    with pytest.raises(ValueError):
        validate_pair(prof, coverage)


def test_empty_decode_is_not_false_success():
    prof, coverage = records(frames=0)
    result = validate_pair(prof, coverage)
    assert result["frames_processed"] == 0
    assert result["pose_coverage_percent"] is None
    assert result["provisional_technical_screen_passed"] is False


def test_cli_never_echoes_private_file_paths_or_raw_json(tmp_path: Path, capsys):
    main_profile, main_coverage = records()
    sub_profile, sub_coverage = records(duration=.01)
    values = {
        "main-profile": main_profile, "main-coverage": main_coverage,
        "sub-profile": sub_profile, "sub-coverage": sub_coverage,
    }
    arguments = []
    for kind, data in values.items():
        path = tmp_path / (kind + ".json")
        path.write_text(json.dumps(data), encoding="utf-8")
        arguments.extend(["--" + kind, str(path)])
    assert main(arguments) == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["mainstream"]["frames_processed"] == 300
    assert str(tmp_path) not in output
    assert "rtsp://" not in output

    secret_path = tmp_path / "SECRET-CAMERA-ADDRESS.json"
    secret_path.write_text('{"camera_secret":"very_sensitive"}', encoding="utf-8")
    arguments[1] = str(secret_path)
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2
    error_text = capsys.readouterr().err
    assert "SECRET-CAMERA-ADDRESS" not in error_text
    assert "very_sensitive" not in error_text


def test_oversized_input_rejected_without_returning_contents(tmp_path: Path):
    path = tmp_path / "secret.json"
    path.write_text("s" * 20000, encoding="utf-8")
    with pytest.raises(ValueError, match="redacted"):
        _safe_record(path, PROFILE_FIELDS)


def test_strict_reports_are_exactly_the_known_public_fields():
    profile, coverage = records()
    assert set(profile) == PROFILE_FIELDS
    assert set(coverage) == COVERAGE_FIELDS
