"""Offline comparison of authorized Hikvision live-RTSP *aggregate* measurements.

This accepts one profile and one pose-coverage summary for each camera
channel, not raw frames, video, RTSP URLs, or terminal logs. The provisional
technical screen is NOT a safety or fall-detection accuracy certification.
"""
from argparse import ArgumentParser
import json
from math import isfinite
from pathlib import Path


MAX_REPORT_BYTES = 16384
MIN_FRAMES = 300
MIN_CYCLE_SAMPLES = 30
MIN_FPS = 8.0
MAX_CYCLE_P95_MS = 250.0
MIN_POSE_RATIO = 0.60
MAX_SAMPLED_RSS_MIB = 1024.0

PROFILE_FIELDS = frozenset({
    "schema_version", "research_only", "stream_interrupted",
    "frames_processed", "pose_unavailable_frames", "candidate_events_unconfirmed",
    "cycle_time_includes_rtsp_blocking_read_and_local_inference",
    "camera_acquisition_or_network_latency_measured", "real_world_fall_accuracy_measured",
    "cycle_sample_window", "cycle_samples", "cycle_p50_ms", "cycle_p95_ms",
    "cycle_mean_ms_all_frames", "observed_cycle_throughput_fps",
    "sampled_process_rss_max_mib", "rss_is_sampled_not_true_peak",
    "no_camera_or_personal_identifiers",
})
COVERAGE_FIELDS = frozenset({
    "schema_version", "frames_observed", "pose_observed_frames",
    "longest_no_pose_streak_frames", "no_pose_streak_at_end_frames",
    "gap_threshold_frames", "gap_threshold_ms", "duration_gate_applied",
    "longest_no_pose_duration_ms", "condition", "operator_diagnostic_only",
    "person_absence_or_fall_inferred", "not_a_camera_health_or_safety_certification",
})


def _nonnegative_int(value) -> bool:
    return type(value) is int and value >= 0


def _positive_number(value) -> bool:
    return type(value) in (int, float) and isfinite(value) and value > 0


def _optional_positive_number(value) -> bool:
    return value is None or _positive_number(value)


def _safe_record(path: Path, expected_fields: frozenset[str]) -> dict:
    """Never echo path or untrusted JSON data on failed validation."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError("Invalid aggregate JSON record (content redacted)") from None
    if not isinstance(data, dict) or set(data) != expected_fields:
        raise ValueError("Aggregate report fields do not match approved schema")
    return data


def validate_pair(profile: dict, coverage: dict) -> dict:
    """Validate one reconnect epoch; never combine mismatched session totals."""
    if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
        raise ValueError("Invalid RTSP profile schema")
    if not isinstance(coverage, dict) or set(coverage) != COVERAGE_FIELDS:
        raise ValueError("Invalid RTSP coverage schema")
    if not (
        profile["schema_version"] == "viil.edge.rtsp_profile.v1"
        and profile["research_only"] is True
        and type(profile["stream_interrupted"]) is bool
        and profile["cycle_time_includes_rtsp_blocking_read_and_local_inference"] is True
        and profile["camera_acquisition_or_network_latency_measured"] is False
        and profile["real_world_fall_accuracy_measured"] is False
        and profile["cycle_sample_window"] == "most_recent_frames"
        and profile["rss_is_sampled_not_true_peak"] is True
        and profile["no_camera_or_personal_identifiers"] is True
        and coverage["schema_version"] == "viil.edge.pose_coverage.v1"
        and coverage["operator_diagnostic_only"] is True
        and coverage["person_absence_or_fall_inferred"] is False
        and coverage["not_a_camera_health_or_safety_certification"] is True
        and (coverage["duration_gate_applied"] is True or (
            coverage["duration_gate_applied"] is False
            and profile["frames_processed"] == 0
        ))
        and coverage["condition"] in ("unverified", "pose_seen", "pose_not_observed")
    ):
        raise ValueError("Profile/coverage provenance or scope does not match")
    frame_keys = (
        (profile, "frames_processed"),
        (profile, "pose_unavailable_frames"),
        (profile, "candidate_events_unconfirmed"),
        (profile, "cycle_samples"),
        (coverage, "frames_observed"),
        (coverage, "pose_observed_frames"),
        (coverage, "longest_no_pose_streak_frames"),
        (coverage, "no_pose_streak_at_end_frames"),
        (coverage, "gap_threshold_frames"),
        (coverage, "gap_threshold_ms"),
    )
    if any(not _nonnegative_int(item[key]) for item, key in frame_keys):
        raise ValueError("Invalid frame counters")
    frames = profile["frames_processed"]
    pose = coverage["pose_observed_frames"]
    if not (
        coverage["frames_observed"] == frames
        and pose == frames - profile["pose_unavailable_frames"]
        and profile["candidate_events_unconfirmed"] <= frames
        and 0 <= coverage["no_pose_streak_at_end_frames"] <=
        coverage["longest_no_pose_streak_frames"] <= frames
        and 1 <= coverage["gap_threshold_frames"] <= 300
        and 250 <= coverage["gap_threshold_ms"] <= 30000
        and 0 <= profile["cycle_samples"] <= min(frames, 2048)
    ):
        raise ValueError("Profile and coverage frame counts do not agree")
    duration = coverage["longest_no_pose_duration_ms"]
    if duration is not None and not _nonnegative_int(duration):
        raise ValueError("Invalid pose gap duration")
    if frames:
        if not (
            profile["cycle_samples"] > 0
            and all(_positive_number(profile[key]) for key in (
                "cycle_p50_ms", "cycle_p95_ms", "cycle_mean_ms_all_frames",
                "observed_cycle_throughput_fps",
            ))
            and profile["cycle_p50_ms"] <= profile["cycle_p95_ms"]
        ):
            raise ValueError("Missing or invalid cycle samples")
    elif any(profile[key] is not None for key in (
        "cycle_p50_ms", "cycle_p95_ms", "cycle_mean_ms_all_frames",
        "observed_cycle_throughput_fps",
    )) or profile["cycle_samples"]:
        raise ValueError("Zero-frame report cannot have cycle timing")
    if not _optional_positive_number(profile["sampled_process_rss_max_mib"]):
        raise ValueError("Invalid sampled RSS")

    ratio = pose / frames if frames else None
    passed = (
        not profile["stream_interrupted"]
        and frames >= MIN_FRAMES
        and profile["cycle_samples"] >= MIN_CYCLE_SAMPLES
        and ratio is not None and ratio >= MIN_POSE_RATIO
        and profile["observed_cycle_throughput_fps"] >= MIN_FPS
        and profile["cycle_p95_ms"] <= MAX_CYCLE_P95_MS
        and profile["sampled_process_rss_max_mib"] is not None
        and profile["sampled_process_rss_max_mib"] <= MAX_SAMPLED_RSS_MIB
    )
    return {
        "frames_processed": frames,
        "pose_coverage_percent": round(ratio * 100, 2) if ratio is not None else None,
        "cycle_p95_ms": profile["cycle_p95_ms"],
        "observed_cycle_throughput_fps": profile["observed_cycle_throughput_fps"],
        "sampled_process_rss_max_mib": profile["sampled_process_rss_max_mib"],
        "unconfirmed_candidate_count": profile["candidate_events_unconfirmed"],
        "longest_no_pose_streak_frames": coverage["longest_no_pose_streak_frames"],
        "longest_no_pose_duration_ms": duration,
        "stream_interrupted": profile["stream_interrupted"],
        "provisional_technical_screen_passed": passed,
        "provisional_screen_unmet": [
            name for name, ok in (
                ("uninterrupted_session", not profile["stream_interrupted"]),
                ("minimum_frames", frames >= MIN_FRAMES),
                ("minimum_recent_samples", profile["cycle_samples"] >= MIN_CYCLE_SAMPLES),
                ("minimum_pose_coverage", ratio is not None and ratio >= MIN_POSE_RATIO),
                ("minimum_throughput_fps", frames > 0
                 and profile["observed_cycle_throughput_fps"] >= MIN_FPS),
                ("maximum_cycle_p95_ms", frames > 0
                 and profile["cycle_p95_ms"] <= MAX_CYCLE_P95_MS),
                ("maximum_sampled_rss_mib", profile["sampled_process_rss_max_mib"] is not None
                 and profile["sampled_process_rss_max_mib"] <= MAX_SAMPLED_RSS_MIB),
            ) if not ok
        ],
    }


def compare_channels(main_profile: dict, main_coverage: dict,
                     sub_profile: dict, sub_coverage: dict) -> dict:
    """No auto-winner: scene/codec/lighting equivalence must be independently checked."""
    main = validate_pair(main_profile, main_coverage)
    sub = validate_pair(sub_profile, sub_coverage)

    def better(key: str, *, higher: bool) -> str:
        a, b = main[key], sub[key]
        if a is None or b is None:
            return "unavailable"
        if a == b:
            return "tie"
        return ("mainstream" if a > b else "substream") if higher else (
            "mainstream" if a < b else "substream"
        )

    return {
        "schema_version": "viil.edge.rtsp_pair_comparison.v1",
        "research_only": True,
        "self_reported_aggregate_inputs_not_hardware_verified": True,
        "same_scene_and_hardware_not_independently_verified": True,
        "thirty_minute_endurance_not_verified": True,
        "ground_truth_fall_accuracy_not_measured": True,
        "camera_to_caregiver_latency_not_measured": True,
        "eligible_for_real_world_safety_deployment": False,
        "provisional_technical_thresholds_not_validated": {
            "minimum_frames": MIN_FRAMES,
            "minimum_recent_cycle_samples": MIN_CYCLE_SAMPLES,
            "minimum_fps": MIN_FPS,
            "maximum_cycle_p95_ms": MAX_CYCLE_P95_MS,
            "minimum_pose_coverage_percent": MIN_POSE_RATIO * 100,
            "maximum_sampled_rss_mib": MAX_SAMPLED_RSS_MIB,
        },
        "mainstream": main,
        "substream": sub,
        "comparisons_not_a_recommendation": {
            "higher_pose_coverage": better("pose_coverage_percent", higher=True),
            "higher_observed_throughput": better("observed_cycle_throughput_fps", higher=True),
            "lower_cycle_p95": better("cycle_p95_ms", higher=False),
            "lower_sampled_rss": better("sampled_process_rss_max_mib", higher=False),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Compare two authorized local aggregate RTSP trials")
    for name in ("main-profile", "main-coverage", "sub-profile", "sub-coverage"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_channels(
            _safe_record(args.main_profile, PROFILE_FIELDS),
            _safe_record(args.main_coverage, COVERAGE_FIELDS),
            _safe_record(args.sub_profile, PROFILE_FIELDS),
            _safe_record(args.sub_coverage, COVERAGE_FIELDS),
        )
    except ValueError:
        parser.error("Comparison refused: invalid, inconsistent or incomplete input (redacted)")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
