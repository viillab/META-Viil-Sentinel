"""Synthetic memory/timing tests; no human frames or identification."""
from itertools import count
from pathlib import Path
import json
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import edge_resource_profile as mod


class FixedTimer:
    def __init__(self, step=1.0):
        self._count = count()
        self.step = step

    def __call__(self):
        return next(self._count) * self.step


def fake_collector(path, *, clip_id, model, max_frames,
                   frame_consumer, event_consumer, max_inference_side):
    assert model.suffix == ".task"
    assert max_frames == 3
    assert max_inference_side in (0, 512)
    for index in range(3):
        frame_consumer(NS(landmarks={11: NS()} if index != 1 else {}))
    event_consumer(NS(timestamp_ms=100))
    return [], {"frames_processed": 3, "invalid_pose_frames": 1,
                "candidate_events": 1}


def test_real_collector_contract_not_buffered_and_realtime_denominator(tmp_path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    rss = iter((1000, 1100, 1200))
    report = mod.profile_clip(
        tmp_path / "fiction.mp4", model,
        clip_id="fiction", expected_frames=3, source_fps=30,
        max_side=512, collector=fake_collector,
        wall_clock=FixedTimer(), cpu_clock=FixedTimer(.2),
        sample_rss=lambda: next(rss),
    )
    assert report["frames"] == 3
    assert report["strict_pose_frames"] == 2
    assert report["candidate_events"] == 1
    assert report["source_playback_seconds"] == pytest.approx(.1)
    assert report["replay_realtime_ratio"] == pytest.approx(.1)
    assert report["throughput_fps"] == pytest.approx(3)
    assert report["rss_peak_sampled_bytes"] == 1200
    assert report["process_cpu_seconds"] == pytest.approx(.2)
    assert "landmarks" not in str(report)
    assert "timestamp" not in str(report)


def test_aggregate_rates_are_frame_weighted_not_mean_clip_rates():
    rows = [
        {"frames": 30, "strict_pose_frames": 20, "candidate_events": 0,
         "wall_seconds": 1.0, "process_cpu_seconds": 1.,
         "source_playback_seconds": 1.0, "throughput_fps": 30.,
         "rss_peak_sampled_bytes": 2 ** 20},
        {"frames": 120, "strict_pose_frames": 118, "candidate_events": 1,
         "wall_seconds": 8.0, "process_cpu_seconds": 7.,
         "source_playback_seconds": 4.0, "throughput_fps": 15.,
         "rss_peak_sampled_bytes": 2 * 2 ** 20},
    ]
    v = mod.aggregate_profiles(rows)
    assert v["actual_decode_pose_pipeline_fps"] == pytest.approx(16.67)
    assert v["replay_speed_multiple_of_video_realtime"] == pytest.approx(.556)
    assert v["frames"] == 150
    assert v["strict_pose_frames"] == 138
    assert v["candidate_events"] == 1
    assert v["max_sampled_own_process_rss_mib"] == 2.0


@pytest.mark.parametrize("broken", [
    {"frames": 0},
    {"strict_pose_frames": 100},
    {"candidate_events": -1},
    {"wall_seconds": 0},
    {"wall_seconds": float("nan")},
    {"process_cpu_seconds": -1},
    {"source_playback_seconds": 0},
    {"rss_peak_sampled_bytes": 0},
])
def test_invalid_source_resource_metrics_fail_closed(broken):
    good = {
        "frames": 3, "strict_pose_frames": 3, "candidate_events": 0,
        "wall_seconds": 1., "process_cpu_seconds": .3,
        "source_playback_seconds": .1, "throughput_fps": 3.,
        "rss_peak_sampled_bytes": 1024,
    }
    good.update(broken)
    with pytest.raises(ValueError):
        mod.aggregate_profiles([good])


def test_failed_incomplete_decode_produces_no_valid_stats(tmp_path):
    task = tmp_path / "pose.task"
    task.write_bytes(b"fake")
    def cut_short(video, *, clip_id, model, max_frames,
                  frame_consumer, event_consumer, max_inference_side):
        frame_consumer(NS(landmarks={}))
        return [], {"frames_processed": 1, "invalid_pose_frames": 1,
                    "candidate_events": 0}
    with pytest.raises(ValueError, match="Incomplete decode"):
        mod.profile_clip(
            tmp_path / "fiction.mp4", task,
            clip_id="fiction", expected_frames=3, source_fps=30,
            max_side=0, collector=cut_short,
            wall_clock=FixedTimer(), cpu_clock=FixedTimer(.3),
            sample_rss=lambda: 1000,
        )


def test_video_report_has_aggregate_only_and_does_not_overwrite(tmp_path, monkeypatch):
    model = tmp_path / "pose.task"
    model.write_bytes(b"mock task")
    monkeypatch.setattr(mod, "_private_root", lambda path: Path(path))
    monkeypatch.setattr(mod, "_private_output_path", lambda path: Path(path))
    monkeypatch.setattr(
        mod, "validate_subset",
        lambda root: {"archive_sha256": "a" * 64},
    )
    monkeypatch.setattr(mod, "_video_metadata", lambda path: (3, 30.))
    target = tmp_path / "result.json"
    result = mod.profile_frozen_ikar(
        tmp_path, model, target, collector=fake_collector,
        wall_clock=FixedTimer(), cpu_clock=FixedTimer(.3),
        sample_rss=lambda: 1024 ** 2,
    )
    assert set(result["variants"]) == {"0", "512"}
    for output in result["variants"].values():
        assert output["frames"] == 24
        assert output["videos"] == 8
        assert output["strict_pose_frames"] == 16
        assert output["candidate_events_original_heuristic"] == 8
        assert output["aggregate_pipeline_throughput_fps"] == 3
    assert result["no_frames_pose_or_timestamps_persisted"] is True
    assert result["not_real_camera_live_stream_benchmark"] is True
    assert json.loads(target.read_text(encoding="utf8")) == result
    assert str(tmp_path) not in target.read_text(encoding="utf8")
    with pytest.raises(FileExistsError):
        mod.profile_frozen_ikar(
            tmp_path, model, target, collector=fake_collector,
            wall_clock=FixedTimer(), cpu_clock=FixedTimer(.3),
            sample_rss=lambda: 1024 ** 2,
        )


@pytest.mark.parametrize("max_side", [-1, 33, 7_000])
def test_frame_resize_experiment_limits(max_side, tmp_path):
    task = tmp_path / "pose.task"
    task.write_bytes(b"fake")
    with pytest.raises(ValueError):
        mod.profile_clip(
            tmp_path / "fake.mp4", task, clip_id="fiction",
            expected_frames=3, source_fps=30, max_side=max_side,
            collector=fake_collector,
            wall_clock=FixedTimer(), cpu_clock=FixedTimer(.3),
            sample_rss=lambda: 1000,
        )
