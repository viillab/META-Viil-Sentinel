"""Invented timestamps and bytes: never fake independent human approval."""
from copy import deepcopy
from hashlib import sha256

import pytest

from sentinel_edge import reviewed_event_benchmark as ev
from sentinel_edge.assist_external import DATASET, PINNED_COMMIT


def fixture():
    inventory = {
        "example-fall": {"duration_ms": 12000, "media_sha256": "a" * 64},
        "example-adl": {"duration_ms": 3600000, "media_sha256": "b" * 64},
    }
    blank = ev.blank_review_template(inventory)
    for decision in blank["decisions"]:
        fall = decision["clip_id"] == "example-fall"
        decision.update(
            reviewer_id="annotator-1" if blank["decisions"].index(decision) % 2 == 0
            else "annotator-2",
            media_sha256=inventory[decision["clip_id"]]["media_sha256"],
            independently_reviewed=True, complete_video_reviewed=True,
            uncertain=False, fall_onsets_ms=[2000, 7000] if fall else [],
            review_note="Observed fictional complete activity and event times.",
        )
    return inventory, blank


def candidate_evidence(inventory):
    return {"version": 1, "dataset": DATASET, "source_commit": PINNED_COMMIT,
            "detector": "original_temporal_heuristic_v1",
            "clips": [
                {"clip_id": cid, "media_sha256": item["media_sha256"],
                 "candidate_ms": ([2100, 2350, 9500] if cid == "example-fall"
                                  else [100000]),
                 "analyzed_frames": 250, "valid_pose_frames": 200}
                for cid, item in inventory.items()
            ]}


def test_blank_review_never_promotes_publisher_labels_to_truth():
    inventory, reviews = fixture()
    empty = ev.blank_review_template(inventory)
    assert all(decision["independently_reviewed"] is False
               and decision["fall_onsets_ms"] is None
               and decision["reviewer_id"] == "" for decision in empty["decisions"])
    with pytest.raises(ValueError, match="pseudonymous"):
        ev.verify_independent_onsets(inventory, empty)
    # Source publisher class, if present, cannot supply ground truth.
    assert set(ev.verify_independent_onsets(inventory, reviews)) == set(inventory)


def test_multi_event_one_to_one_duplicate_false_candidate_and_latency():
    x = ev.score_one([2000, 7000], [2100, 2350, 7001, 9500], 10000)
    assert (x["matched_fall_events"], x["missed_fall_events"]) == (2, 0)
    assert x["false_candidates"] == 2
    assert x["matching_delay_ms"] == [100, 1]


def test_event_match_early_window_boundaries_and_late_alerts():
    x = ev.score_one([3000, 7000], [2749, 4999, 9300], 12000)
    assert x["matched_fall_events"] == 1
    assert x["false_candidates"] == 2
    assert x["matching_delay_ms"] == [1999]
    y = ev.score_one([3000], [2750, 5000], 12000)
    assert y["matched_fall_events"] == 1
    assert y["matching_delay_ms"] == [-250]
    assert y["false_candidates"] == 1


def test_score_recall_and_false_alarm_hour_only_full_negative_videos():
    inventory, reviews = fixture()
    c = candidate_evidence(inventory)
    report = ev.evaluate_reviewed_events(inventory, reviews, c)
    assert report["reviewed_events"] == 2
    assert report["matched_events"] == 1
    assert report["missed_events"] == 1
    assert report["false_candidates"] == 3
    assert report["candidate_events"] == 4
    assert report["event_recall"] == .5
    assert report["matched_detection_delay_mean_ms"] == 100
    assert report["false_candidates_in_entire_reviewed_no_fall_videos"] == 1
    assert report["reviewed_no_fall_hours"] == 1
    assert report["false_candidates_per_full_no_fall_hour"] == 1
    assert report["publisher_labels_not_ground_truth"] is True
    assert report["not_an_independent_unseen_subject_test"] is True


@pytest.mark.parametrize(("mutation", "error"), [
    ("blank", "pseudonymous"),
    ("same_reviewer", "DISTINCT"),
    ("uncertain", "Unreviewed"),
    ("non_independent", "Unreviewed"),
    ("partial", "Unreviewed"),
    ("wrong_sha", "Unreviewed"),
    ("missing_event", "disagree"),
    ("onset_shift", "disagree"),
    ("unsorted", "Invalid fall onset"),
    ("outside_duration", "Invalid fall onset"),
    ("extra", "Unknown review"),
    ("same_entry", "DISTINCT"),
])
def test_two_reviewers_fail_closed_on_incomplete_or_conflicted_input(mutation, error):
    inventory, reviews = fixture()
    a, b = reviews["decisions"][:2]
    if mutation == "blank":
        a["reviewer_id"] = ""
    elif mutation == "same_reviewer":
        b["reviewer_id"] = a["reviewer_id"]
    elif mutation == "uncertain":
        a["uncertain"] = True
    elif mutation == "non_independent":
        a["independently_reviewed"] = False
    elif mutation == "partial":
        a["complete_video_reviewed"] = False
    elif mutation == "wrong_sha":
        a["media_sha256"] = "0" * 64
    elif mutation == "missing_event":
        b["fall_onsets_ms"] = [2000]
    elif mutation == "onset_shift":
        b["fall_onsets_ms"] = [2000, 7400]
    elif mutation == "unsorted":
        b["fall_onsets_ms"] = [7000, 2000]
    elif mutation == "outside_duration":
        b["fall_onsets_ms"] = [2000, 13000]
    elif mutation == "extra":
        a["email"] = "hidden.invalid"
    elif mutation == "same_entry":
        reviews["decisions"][1] = deepcopy(a)
    with pytest.raises(ValueError, match=error):
        ev.verify_independent_onsets(inventory, reviews)


@pytest.mark.parametrize("candidates", [
    [100, 100], [-1], [6000, 2000], [16000], [True], [100.0],
])
def test_out_of_order_duplicate_and_invalid_candidates_refused(candidates):
    with pytest.raises(ValueError, match="Invalid candidate"):
        ev.score_one([2000], candidates, 12000)


def test_empty_no_fall_video_has_no_events_or_denominator_confusion():
    x = ev.score_one([], [], 4000)
    assert x["matched_fall_events"] == x["false_candidates"] == 0
    assert x["matching_delay_ms"] == []


def test_candidate_media_tampering_is_rejected():
    inventory, reviews = fixture()
    evidence = candidate_evidence(inventory)
    evidence["clips"][0]["media_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA"):
        ev.evaluate_reviewed_events(inventory, reviews, evidence)


def test_capture_uses_only_event_timestamps_and_pose_counts(tmp_path):
    from sentinel_edge.contracts import Landmark, PoseFrame
    inventory = {
        "example": {
            "media_sha256": sha256(b"fake").hexdigest(),
            "duration_ms": 3000,
            "path": tmp_path / "fake.avi",
        },
    }
    inventory["example"]["path"].write_bytes(b"fake")
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake non-empty model")
    def mocked_collector(video, *, clip_id, model, max_frames, frame_consumer,
                         event_consumer):
        class E:
            timestamp_ms = 1200
        for i in range(4):
            frame_consumer(PoseFrame(
                timestamp_ms=i * 500, source_id=clip_id, landmarks={
                    11: Landmark(.4, .2, 1), 12: Landmark(.6, .2, 1),
                    23: Landmark(.4, .5, 1), 24: Landmark(.6, .5, 1),
                },
            ))
        event_consumer(E())
        return [], {"frames_processed": 4, "candidate_events": 1}
    manifest = ev.collect_original_heuristic_events(
        inventory, model, collector=mocked_collector
    )
    assert manifest["clips"][0]["candidate_ms"] == [1200]
    assert manifest["clips"][0]["valid_pose_frames"] == 4
    assert "landmarks" not in str(manifest)
    assert manifest["detector"] == "original_temporal_heuristic_v1"
