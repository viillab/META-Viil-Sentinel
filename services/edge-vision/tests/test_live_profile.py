"""Deterministic, metadata-only live RTSP cycle measurement tests."""
import math

import pytest

from sentinel_edge.live_profile import LiveCycleProfiler


def test_percentiles_are_recent_and_fps_uses_all_cycles():
    reads = iter([1024 * 1024, 2048 * 1024])
    profile = LiveCycleProfiler(rss_sample=lambda: next(reads), recent_limit=2)
    profile.observe(.01, True, False)
    profile.observe(.02, False, False)
    profile.observe(.03, True, True)
    report = profile.report(interrupted=False)
    assert report["schema_version"] == "viil.edge.rtsp_profile.v1"
    assert report["frames_processed"] == 3
    assert report["pose_unavailable_frames"] == 1
    assert report["candidate_events_unconfirmed"] == 1
    assert report["cycle_samples"] == 2
    assert report["cycle_p50_ms"] == 20
    assert report["cycle_p95_ms"] == 30
    assert report["cycle_mean_ms_all_frames"] == 20
    assert report["observed_cycle_throughput_fps"] == 50
    assert report["sampled_process_rss_max_mib"] == 2.0
    assert report["real_world_fall_accuracy_measured"] is False
    assert report["camera_acquisition_or_network_latency_measured"] is False
    assert report["no_camera_or_personal_identifiers"] is True
    assert not any(k in report for k in ("source_id", "camera_ip", "frames", "url"))


def test_zero_frame_disconnect_is_unavailable_not_success():
    profile = LiveCycleProfiler(rss_sample=lambda: None)
    result = profile.report(interrupted=True)
    assert result["stream_interrupted"] is True
    assert result["frames_processed"] == 0
    assert result["cycle_p95_ms"] is None
    assert result["observed_cycle_throughput_fps"] is None


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), math.inf, True])
def test_profile_rejects_bad_measurements(duration):
    profile = LiveCycleProfiler(rss_sample=lambda: None)
    with pytest.raises(ValueError):
        profile.observe(duration, True, False)


def test_profile_rejects_invalid_flags_and_unbounded_memory():
    with pytest.raises(ValueError):
        LiveCycleProfiler(recent_limit=2049)
    profile = LiveCycleProfiler(rss_sample=lambda: None)
    with pytest.raises(ValueError):
        profile.observe(0.2, 1, False)
    with pytest.raises(ValueError):
        profile.report(interrupted="yes")


def test_rss_sampled_every_32_frames_and_without_frame_storage():
    counter = iter([4096, 8192, 16384])
    profile = LiveCycleProfiler(rss_sample=lambda: next(counter))
    for _ in range(33):
        profile.observe(.005, True, False)
    report = profile.report(interrupted=False)
    assert report["frames_processed"] == 33
    assert report["sampled_process_rss_max_mib"] == round(16384 / 1048576, 2)
    assert report["rss_is_sampled_not_true_peak"] is True


def test_optional_memory_sampler_error_does_not_break_live_processing():
    def denied():
        raise PermissionError("RSS unavailable")
    profile = LiveCycleProfiler(rss_sample=denied)
    profile.observe(.01, True, False)
    report = profile.report(interrupted=False)
    assert report["frames_processed"] == 1
    assert report["sampled_process_rss_max_mib"] is None
