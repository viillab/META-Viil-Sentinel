"""Synthetic-only source integrity tests for offline original-heuristic replay.

These cases do not claim real event truth or fall-detection accuracy.
"""
from hashlib import sha256

import pytest

from sentinel_edge import reviewed_event_benchmark as ev
from sentinel_edge.contracts import PoseFrame


def _fixtures(tmp_path):
    video = tmp_path / "invented-video.mp4"
    video.write_bytes(b"not a real video; injected collector only")
    task = tmp_path / "local-pose.task"
    task.write_bytes(b"fake local task bytes")
    inventory = {
        "synthetic": {
            "path": video,
            "duration_ms": 1500,
            "media_sha256": sha256(video.read_bytes()).hexdigest(),
        },
    }
    return inventory, task


def _collector(*, frame_count=6, reported_frames=None, reported_events=1,
               return_frames=False):
    def collect(video, *, clip_id, model, max_frames, frame_consumer,
                event_consumer):
        assert max_frames == 6
        for i in range(frame_count):
            frame_consumer(PoseFrame(
                timestamp_ms=i * 100, source_id=clip_id, landmarks={},
            ))

        class Candidate:
            timestamp_ms = 300

        event_consumer(Candidate())
        return ([1] if return_frames else []), {
            "frames_processed": (frame_count if reported_frames is None
                                 else reported_frames),
            "candidate_events": reported_events,
        }

    return collect


def test_original_collector_full_decode_requires_source_frame_count(tmp_path):
    inventory, task = _fixtures(tmp_path)
    evidence = ev.collect_original_heuristic_events(
        inventory, task, collector=_collector(),
        metadata_reader=lambda _: (6, 10.0),
    )
    row = evidence["clips"][0]
    assert row["analyzed_frames"] == 6
    assert row["valid_pose_frames"] == 0
    assert row["candidate_ms"] == [300]
    assert evidence["detector"] == "original_temporal_heuristic_v1"


def test_original_collector_rejects_truncated_decoder_with_matching_internal_counts(
    tmp_path,
):
    inventory, task = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="Incomplete video decode"):
        ev.collect_original_heuristic_events(
            inventory, task, collector=_collector(frame_count=4),
            metadata_reader=lambda _: (6, 10.0),
        )


@pytest.mark.parametrize("metadata", [
    (0, 10.0), (6001, 10.0), (True, 10.0),
    (6.0, 10.0), (6, 0), (6, 121), (6, float("nan")),
    (6, True), (6, "10"),
])
def test_original_collector_rejects_invalid_video_metadata(tmp_path, metadata):
    inventory, task = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="Invalid original video frame count or FPS"):
        ev.collect_original_heuristic_events(
            inventory, task, collector=_collector(),
            metadata_reader=lambda _: metadata,
        )


@pytest.mark.parametrize("collector", [
    _collector(reported_frames=True), _collector(reported_events=2),
    _collector(return_frames=True),
])
def test_original_collector_refuses_divergent_stream_statistics(tmp_path, collector):
    inventory, task = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="Incomplete video decode"):
        ev.collect_original_heuristic_events(
            inventory, task, collector=collector,
            metadata_reader=lambda _: (6, 10.0),
        )


@pytest.mark.parametrize("fps", [True, "10", float("nan")])
def test_early_motion_research_also_rejects_non_numeric_fps(tmp_path, fps):
    inventory, task = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="Invalid original video frame count or FPS"):
        ev.collect_early_motion_candidate_events(
            inventory, task, collector=_collector(),
            metadata_reader=lambda _: (6, fps),
        )


def test_original_collector_rejects_changed_media_before_decode(tmp_path):
    inventory, task = _fixtures(tmp_path)
    inventory["synthetic"]["path"].write_bytes(b"mutated after hashing")
    with pytest.raises(ValueError, match="mutated"):
        ev.collect_original_heuristic_events(
            inventory, task, collector=_collector(),
            metadata_reader=lambda _: (6, 10.0),
        )
