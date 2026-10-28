"""Synthetic 1.5-second research model tests, no real media or model weights."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.causal_1500ms_research import (
    CONTEXT_MS, _preflight, train_causal_1500ms,
)


def fixtures(tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir()
    groups = {
        "version": 2, "permission_basis": "Synthetic toy poses only, no person",
        "clips": [],
    }
    proposals = {"version": 1, "segments": []}
    poses = {}
    for split in ("train", "val", "test"):
        for label in ("fall", "adl"):
            cid = f"{split}-{label}"
            data = cid.encode("ascii") + b"-fake-avi"
            (clips / f"{cid}.avi").write_bytes(data)
            groups["clips"].append({
                "clip_id": cid, "dataset_id": "toy",
                "subject_id": f"{split}-person",
                "recording_id": cid, "split": split,
                "expected_fall": label == "fall",
                "media_sha256": sha256(data).hexdigest(),
            })
            proposals["segments"].append({
                "clip_id": cid, "video": f"clips/{cid}.avi",
                "start_ms": 0, "end_ms": 1500,
                "expected_fall": label == "fall",
                "label_reviewed": False,
                "annotation_basis": "publisher staged toy activity",
            })
            poses[cid] = label
    task = tmp_path / "pose.task"
    task.write_bytes(b"synthetic task")
    return groups, proposals, task, poses


def torso(timestamp, cid, *, fall=False, observed=True, future=False):
    if not observed:
        return PoseFrame(timestamp_ms=timestamp, source_id=cid, landmarks={})
    # Original normalized shoulder/hip contract; late-frame motion only.
    t = timestamp / 1000
    hip = (.44 + max(0, t - .5) * .28 if fall else .44)
    if future:
        hip = .7
    return PoseFrame(
        timestamp_ms=timestamp, source_id=cid,
        landmarks={
            11: Landmark(.45, hip - .20, .96),
            12: Landmark(.55, hip - .20, .96),
            23: Landmark(.45, hip, .96),
            24: Landmark(.55, hip, .96),
        },
    )


def collector_for(poses, *, mode="normal"):
    def collect(_video, *, clip_id, model, max_frames,
                frame_consumer, event_consumer):
        assert model.suffix == ".task"
        assert max_frames == 41
        count = 39 if mode == "truncate" else 41
        for i in range(count):
            stamp = i * 40
            visible = not (mode == "occlusion" and clip_id == "test-adl")
            frame_consumer(torso(
                stamp, clip_id, fall=poses[clip_id] == "fall",
                observed=visible, future=(mode == "different_future" and stamp > 1500),
            ))
        return [], {
            "frames_processed": count,
            "invalid_pose_frames": 0,
            "candidate_events": 0,
        }
    return collect


def run(root, params, **kwargs):
    groups, proposals, task, poses = params
    return train_causal_1500ms(
        root, task, groups, proposals, collector=collector_for(poses, **kwargs),
        metadata_reader=lambda _: (41, 25.0),
    )


def test_real_trained_but_research_only_1500ms_model(tmp_path):
    params = fixtures(tmp_path)
    result = run(tmp_path, params)
    assert result["trained_ai_classifier"] is True
    assert result["window_context_ms"] == CONTEXT_MS == 1500
    assert result["temporal_sample_slots"] == 30
    assert result["eligible_clips"] == result["input_original_clips"] == 6
    assert result["full_decoded_source_frames"] == 246
    assert result["no_8s_artifact_reused"] is True
    assert result["no_later_than_segment_end_frames_used"] is True
    assert result["test_data_excluded_from_training_and_threshold_selection"]
    assert result["retrained_weights_serialized"] is False
    assert result["alerts_modified_or_authorized"] is False
    assert result["not_real_world_accuracy_false_alarms_or_recall"]
    assert "train-person" not in json.dumps(result)
    assert "landmarks" not in json.dumps(result)
    assert "features" not in json.dumps(result)
    assert result["model_size_bytes_in_ram"] == 736


def test_true_future_frames_do_not_change_causal_trailing_predictions(tmp_path):
    params = fixtures(tmp_path)
    before = run(tmp_path, params)
    after = run(tmp_path, params, mode="different_future")
    assert before == after


def test_internal_matching_frame_counts_still_refuse_truncated_source(tmp_path):
    params = fixtures(tmp_path)
    with pytest.raises(ValueError, match="full-decode"):
        run(tmp_path, params, mode="truncate")


def test_pose_abstentions_not_misclassified_as_adl(tmp_path):
    params = fixtures(tmp_path)
    with pytest.raises(ValueError, match="BOTH fall and ADL"):
        run(tmp_path, params, mode="occlusion")


def test_short_video_is_not_padded_or_invented(tmp_path):
    params = fixtures(tmp_path)
    groups, proposals, _, _ = params
    proposals["segments"][0]["end_ms"] = 1100
    with pytest.raises(ValueError, match="BOTH fall and ADL"):
        run(tmp_path, params)


def test_annotation_shorter_than_context_cannot_read_pre_annotation_frames(tmp_path):
    params = fixtures(tmp_path)
    # The source itself has >=1500ms of frames, but the annotated interval
    # does not. Training must abstain instead of sampling earlier context.
    params[1]["segments"][0]["start_ms"] = 200
    with pytest.raises(ValueError, match="BOTH fall and ADL"):
        run(tmp_path, params)


def test_subject_leak_is_rejected_before_any_pose_collection(tmp_path):
    params = fixtures(tmp_path)
    groups, proposals, task, _ = params
    groups["clips"][0]["subject_id"] = groups["clips"][-1]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        train_causal_1500ms(
            tmp_path, task, groups, proposals,
            collector=lambda *a, **k: pytest.fail("must not start model"),
            metadata_reader=lambda _: (41, 25.0),
        )


@pytest.mark.parametrize("defect", ["sha", "reviewed", "label", "escape", "fps",
                                    "count", "late", "duplicate"])
def test_invalid_private_source_plan_refused_before_training(tmp_path, defect):
    params = fixtures(tmp_path)
    groups, proposals, task, _ = params
    if defect == "sha":
        groups["clips"][0]["media_sha256"] = "f" * 64
    elif defect == "reviewed":
        proposals["segments"][0]["label_reviewed"] = True
    elif defect == "label":
        proposals["segments"][0]["expected_fall"] = False
    elif defect == "escape":
        proposals["segments"][0]["video"] = "../outside.avi"
    elif defect == "late":
        proposals["segments"][0]["end_ms"] = 2500
    elif defect == "duplicate":
        proposals["segments"][0]["clip_id"] = proposals["segments"][1]["clip_id"]
    def reader(_):
        if defect == "fps":
            return 41, "25.0"
        if defect == "count":
            return True, 25.0
        return 41, 25.0
    with pytest.raises((ValueError, OSError)):
        _preflight(tmp_path, task, groups, proposals, reader)


def test_final_test_label_changes_do_not_change_train_or_selection(tmp_path):
    params = fixtures(tmp_path)
    original = run(tmp_path, params)
    changed = deepcopy(params[0])
    for clip in changed["clips"]:
        if clip["split"] == "test":
            clip["expected_fall"] = not clip["expected_fall"]
    modified_props = deepcopy(params[1])
    for spec in modified_props["segments"]:
        if spec["clip_id"].startswith("test-"):
            spec["expected_fall"] = not spec["expected_fall"]
    changed_result = train_causal_1500ms(
        tmp_path, params[2], changed, modified_props,
        collector=collector_for(params[3]),
        metadata_reader=lambda _: (41, 25.0),
    )
    assert original["validation_threshold"] == changed_result["validation_threshold"]
    assert original["validation_publisher_clip_diagnostic"] == (
        changed_result["validation_publisher_clip_diagnostic"]
    )
