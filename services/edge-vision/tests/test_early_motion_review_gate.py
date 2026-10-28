"""All fictional review/proposal timings; never assert human review happened."""
from copy import deepcopy
from hashlib import sha256

import pytest

from sentinel_edge import reviewed_event_benchmark as ev

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.early_motion_probe import CausalMotionProbe


def falling_frame(i, name):
    hip = .41 if i < 6 else .41 + min(i - 5, 7) * .03
    return PoseFrame(
        timestamp_ms=i * 100, source_id=name,
        landmarks={
            11: Landmark(.45, hip - .25, .98),
            12: Landmark(.55, hip - .25, .98),
            23: Landmark(.45, hip, .98),
            24: Landmark(.55, hip, .98),
        },
    )


def test_private_timestamp_callback_is_opt_in_and_not_in_summary():
    private_times = []
    probe = CausalMotionProbe(private_proposal_consumer=private_times.append)
    baseline = CausalMotionProbe()
    for i in range(18):
        frame = falling_frame(i, "fixture")
        assert probe.observe(frame) is baseline.observe(frame) is None
    assert len(private_times) >= 1
    assert len(private_times) == probe.summary()["provisional_motion_proposals"]
    assert baseline.summary() == probe.summary()
    assert all(isinstance(ms, int) for ms in private_times)
    assert "candidate_ms" not in str(probe.summary())
    assert "source_id" not in str(probe.summary())


def fixture_inventory(tmp_path):
    positives = tmp_path / "private-fall.avi"
    negatives = tmp_path / "private-normal.avi"
    positives.write_bytes(b"synthetic fake video")
    negatives.write_bytes(b"another synthetic fake video")
    return {
        "fall": {"path": positives, "media_sha256": sha256(positives.read_bytes()).hexdigest(),
                 "duration_ms": 2000},
        "adl": {"path": negatives, "media_sha256": sha256(negatives.read_bytes()).hexdigest(),
                "duration_ms": 2000},
    }


def inject_collector(video, *, clip_id, model, max_frames, frame_consumer,
                     event_consumer):
    assert max_frames == 18
    for i in range(18):
        if clip_id == "fall":
            frame_consumer(falling_frame(i, clip_id))
        else:
            original = falling_frame(i, clip_id)
            still = {idx: Landmark(p.x, p.y + (.41 - (.41 if i < 6 else .41 +
                    min(i - 5, 7) * .03)), p.visibility)
                     for idx, p in original.landmarks.items()}
            frame_consumer(PoseFrame(timestamp_ms=i * 100, source_id=clip_id,
                                     landmarks=still))
    return [], {"frames_processed": 18, "invalid_pose_frames": 0,
                "candidate_events": 0}


def test_capture_early_does_not_copy_publisher_fall_as_human_truth(tmp_path):
    inventory = fixture_inventory(tmp_path)
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic .task")
    evidence = ev.collect_early_motion_candidate_events(
        inventory, model, collector=inject_collector,
        metadata_reader=lambda video: (18, 10.0),
    )
    assert evidence["detector"] == ev.EARLY_MOTION_RESEARCH_TAG
    assert len(evidence["clips"]) == 2
    assert [len(row["candidate_ms"]) for row in evidence["clips"]] == [1, 0]
    assert all(row["analyzed_frames"] == row["valid_pose_frames"] == 18
               for row in evidence["clips"])
    assert "human_review" not in str(evidence)
    assert "landmarks" not in str(evidence)
    blank = ev.blank_review_template(inventory)
    with pytest.raises(ValueError, match="pseudonymous"):
        ev.evaluate_reviewed_events(inventory, blank, evidence)
    assert blank["decisions"][0]["fall_onsets_ms"] is None
    assert blank["decisions"][0]["independently_reviewed"] is False


def _synthetic_attested(inventory):
    reviews = ev.blank_review_template(inventory)
    for j, row in enumerate(reviews["decisions"]):
        label = row["clip_id"] == "fall"
        row.update(reviewer_id="synthetic-r1" if j % 2 == 0 else "synthetic-r2",
                   media_sha256=inventory[row["clip_id"]]["media_sha256"],
                   independently_reviewed=True, complete_video_reviewed=True,
                   uncertain=False, fall_onsets_ms=[800] if label else [],
                   review_note="Fictional example for code-only scoring tests.")
    return reviews


def test_scoring_of_fictional_two_reviewers_does_not_authorize_alert(tmp_path):
    inventory = fixture_inventory(tmp_path)
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic .task")
    evidence = ev.collect_early_motion_candidate_events(
        inventory, model, collector=inject_collector,
        metadata_reader=lambda video: (18, 10),
    )
    reviews = _synthetic_attested(inventory)
    result = ev.evaluate_reviewed_events(inventory, reviews, evidence)
    assert result["candidate_detector"] == ev.EARLY_MOTION_RESEARCH_TAG
    assert result["candidate_is_trained_ai"] is False
    assert result["automatic_alert_authorized"] is False
    assert result["reviewed_events"] == 1
    assert result["fully_reviewed_videos"] == 2
    modified = deepcopy(reviews)
    modified["decisions"][1]["fall_onsets_ms"] = []
    with pytest.raises(ValueError, match="disagree"):
        ev.evaluate_reviewed_events(inventory, modified, evidence)


@pytest.mark.parametrize("bad", ["unexpected_detector", "", None])
def test_unknown_candidate_detector_cannot_bypass_review_gate(tmp_path, bad):
    inventory = fixture_inventory(tmp_path)
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic .task")
    evidence = ev.collect_early_motion_candidate_events(
        inventory, model, collector=inject_collector,
        metadata_reader=lambda video: (18, 10),
    )
    evidence["detector"] = bad
    with pytest.raises(ValueError, match="candidate evidence"):
        ev.evaluate_reviewed_events(inventory, _synthetic_attested(inventory),
                                    evidence)


def test_source_tampering_and_incomplete_decode_fail_closed(tmp_path):
    inventory = fixture_inventory(tmp_path)
    model = tmp_path / "pose.task"
    model.write_bytes(b"synthetic .task")
    inventory["fall"]["path"].write_bytes(b"modified after hash")
    with pytest.raises(ValueError, match="mutated"):
        ev.collect_early_motion_candidate_events(
            inventory, model, collector=inject_collector,
            metadata_reader=lambda video: (18, 10),
        )
    inventory = fixture_inventory(tmp_path)

    def incomplete(video, *, clip_id, model, max_frames, frame_consumer,
                   event_consumer):
        for i in range(10):
            frame_consumer(falling_frame(i, clip_id))
        return [], {"frames_processed": 10, "invalid_pose_frames": 0,
                    "candidate_events": 0}
    with pytest.raises(ValueError, match="Incomplete"):
        ev.collect_early_motion_candidate_events(
            inventory, model, collector=incomplete,
            metadata_reader=lambda video: (18, 10),
        )
