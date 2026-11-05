"""Private research pose-window export contracts: invented files and keypoints."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.temporal_training import train_and_evaluate
from sentinel_edge.window_export import (
    NearestFrameSampler, _private_output_path, extract_reviewed_windows,
    validate_source_plan,
)


def payload(tmp_path):
    groups = {"version": 2, "permission_basis": "Fictional videos, no human subjects",
              "clips": []}
    segments = {"version": 1, "segments": []}
    for split in ("train", "val", "test"):
        for falls in (True, False):
            cid = f"{split}-{'fall' if falls else 'adl'}"
            video = tmp_path / f"{cid}.avi"
            data = f"fake-{cid}".encode()
            video.write_bytes(data)
            groups["clips"].append({
                "clip_id": cid, "dataset_id": "fictional", "subject_id": f"p-{split}",
                "recording_id": cid, "split": split, "expected_fall": falls,
                "media_sha256": hashlib.sha256(data).hexdigest(),
            })
            segments["segments"].append({
                "clip_id": cid, "video": video.name, "start_ms": 100,
                "end_ms": 3100, "expected_fall": falls,
                "label_reviewed": True,
                "annotation_basis": "Synthetic fixture's invented 3-second segment",
            })
    return groups, segments


def pose(cid, ts, *, valid=True):
    return PoseFrame(timestamp_ms=ts, source_id=cid, landmarks={
        11: Landmark(.45, .25, .99), 12: Landmark(.55, .25, .99),
        23: Landmark(.45, .55, .99), 24: Landmark(.55, .55, .99),
    } if valid else {})


def fake_collector(video: Path, *, clip_id, model, max_frames, frame_consumer,
                   event_consumer):
    assert video.is_file() and model.is_file()
    assert max_frames <= 6000
    for t in range(0, 4000, 100):
        frame_consumer(pose(clip_id, t))
    return [], {"frames_processed": 40, "invalid_pose_frames": 0, "candidate_events": 0}


def test_extraction_matches_trainer_contract_without_saving_person_data(tmp_path):
    groups, segments = payload(tmp_path)
    model = tmp_path / "fake.task"
    model.write_bytes(b"imaginary model")
    bundle = extract_reviewed_windows(
        groups, segments, root=tmp_path, model=model, collector=fake_collector,
    )
    assert len(bundle["windows"]) == 6
    assert len(bundle["windows"][0]["features"]) == 30
    assert len(bundle["windows"][0]["features"][0]) == 6
    assert all(row[-1] == 1 for row in bundle["windows"][0]["features"])
    model, report = train_and_evaluate(groups, bundle)
    assert report["model_deployed"] is False
    assert model.model_bytes < 1500
    assert not list(tmp_path.glob("*.pose.jsonl"))


def test_sampler_missing_pose_has_mask_without_fabricated_keypoints():
    sampler = NearestFrameSampler("fiction", 0, 3000)
    for t in range(0, 3200, 100):
        sampler.on_frame(pose("fiction", t, valid=(t > 500)))
    window = sampler.finish()
    assert len(window) == 30
    assert window[0] == [0] * 6
    assert sum(row[-1] for row in window) >= 20
    assert sampler.frames_processed == 32
    assert len(sampler.nearest) == 30


def test_sampler_does_not_fill_unobserved_gap_with_same_old_pose():
    sampler = NearestFrameSampler("fiction", 0, 3000)
    for t in (0, 100, 200, 2700, 2800, 2900, 3000):
        sampler.on_frame(pose("fiction", t))
    with pytest.raises(ValueError, match="Too few valid"):
        sampler.finish()


@pytest.mark.parametrize("start,end", [
    (0, 899), (300, 9000), (-1, 1400), (0.0, 3000), (1000, 1000)
])
def test_segment_bounds_fail_closed(start, end):
    with pytest.raises(ValueError):
        NearestFrameSampler("f", start, end)


def test_bad_subject_metadata_checked_before_inference(tmp_path):
    groups, segments = payload(tmp_path)
    groups["clips"][2]["subject_id"] = groups["clips"][0]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        validate_source_plan(groups, segments, tmp_path)


def test_bad_annotation_review_rejected(tmp_path):
    groups, segments = payload(tmp_path)
    segments["segments"][0]["label_reviewed"] = False
    with pytest.raises(ValueError, match="reviewed segment"):
        validate_source_plan(groups, segments, tmp_path)


def test_bad_label_and_unmatched_metadata_rejected(tmp_path):
    groups, segments = payload(tmp_path)
    segments["segments"][0]["expected_fall"] = False
    with pytest.raises(ValueError, match="contradicts"):
        validate_source_plan(groups, segments, tmp_path)
    groups, segments = payload(tmp_path)
    segments["segments"].pop()
    with pytest.raises(ValueError, match="every group clip"):
        validate_source_plan(groups, segments, tmp_path)


def test_bad_media_hash_rejected_before_inference(tmp_path):
    groups, segments = payload(tmp_path)
    groups["clips"][0]["media_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_source_plan(groups, segments, tmp_path)


def test_no_media_hash_is_rejected(tmp_path):
    groups, segments = payload(tmp_path)
    groups["clips"][0].pop("media_sha256")
    with pytest.raises(ValueError, match="verified content digest"):
        validate_source_plan(groups, segments, tmp_path)


@pytest.mark.parametrize("filename", ["../secret.avi", "C:/outside.avi",
                                      "https://evil.tld/a.mp4", "movie.exe"])
def test_path_escape_rejected(tmp_path, filename):
    groups, segments = payload(tmp_path)
    segments["segments"][0]["video"] = filename
    with pytest.raises(ValueError, match="relative local"):
        validate_source_plan(groups, segments, tmp_path)


def test_cannot_export_to_temp_or_git_directory(tmp_path):
    with pytest.raises(ValueError, match="data/private"):
        _private_output_path(tmp_path / "windows.json")


def test_sampler_rejects_timestamp_source_switch():
    sampler = NearestFrameSampler("fiction", 0, 3000)
    sampler.on_frame(pose("fiction", 0))
    with pytest.raises(ValueError, match="source changed"):
        sampler.on_frame(pose("other", 100))
    with pytest.raises(ValueError, match="strictly increase"):
        sampler.on_frame(pose("fiction", 0))


def test_inference_not_called_when_missing_data(tmp_path):
    groups, selections = payload(tmp_path)
    groups["clips"] = deepcopy(groups["clips"])[:1]
    selections["segments"] = deepcopy(selections["segments"])[:1]
    model = tmp_path / "local.task"
    model.write_bytes(b"fiction")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Should not process unsplittable data")

    with pytest.raises(ValueError, match="train/val/test"):
        extract_reviewed_windows(
            groups, selections, root=tmp_path, model=model, collector=forbidden,
        )
    assert calls == []
