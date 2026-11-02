"""Offline-only evidence quality envelope regression tests (fictional poses)."""
from dataclasses import asdict
from math import nan

import pytest

contracts = pytest.importorskip("sentinel_edge.contracts")
quality = pytest.importorskip("app.review_evidence_abstention")
stress = pytest.importorskip("app.synthetic_adl_stress")

assess = quality.assess_pose_frames
Policy = quality.ReviewQualityPolicy
PoseFrame = contracts.PoseFrame


def frames_stationary(source="fictional"):
    return [
        stress._pose(i * 100, source=source)
        for i in range(30)
    ]


def padded_fast_sit(source="fictional"):
    # A *voluntary* ADL can satisfy BOTH shared-torso-heuristic triggers.
    # Long, high-quality history must not make the model claim a real fall.
    return [
        *(stress._pose(i * 100, source=source) for i in range(16)),
        stress._pose(1700, source=source),
        stress._pose(1800, source=source),
        stress._pose(1900, source=source),
        stress._pose(
            2040, hip_y=.66, shoulder_y=.52, shoulder_x=.76, source=source,
        ),
        stress._pose(
            2200, hip_y=.67, shoulder_y=.53, shoulder_x=.78, source=source,
        ),
        stress._pose(
            2350, hip_y=.67, shoulder_y=.53, shoulder_x=.78, source=source,
        ),
        stress._pose(
            2500, hip_y=.67, shoulder_y=.53, shoulder_x=.78, source=source,
        ),
    ]


def padded_horizontal_bed_shift(source="fictional"):
    return [
        *(stress._lie(i * 100, .45, source=source) for i in range(16)),
        stress._lie(1700, .45, source=source),
        stress._lie(1800, .45, source=source),
        stress._lie(1900, .45, source=source),
        stress._lie(2040, .67, source=source),
        stress._lie(2200, .68, source=source),
        stress._lie(2350, .68, source=source),
        stress._lie(2500, .68, source=source),
    ]


def test_stationary_pose_never_becomes_a_confirmed_safe_decision():
    result = assess(frames_stationary(), source_id="fictional")
    assert result.status == "no_candidate_not_clearance"
    assert result.frames == 30
    assert result.valid_pose_frames == 30
    assert result.valid_pose_fraction == 1
    assert result.abstained_due_to_quality is False
    assert result.human_review_proposed is False
    assert result.v1_candidate_count == 0
    assert result.v2_review_candidate_count == 0
    assert result.no_fall_confirmed is False
    assert result.fall_confirmed is False
    assert result.provider_called is False
    assert result.meta_upload_permitted is False


@pytest.mark.parametrize("samples", [
    padded_fast_sit,
    padded_horizontal_bed_shift,
])
def test_adequate_quality_still_cannot_distinguish_normal_motion(samples):
    result = assess(samples(), source_id="fictional")
    assert result.abstained_due_to_quality is False
    assert result.human_review_proposed is True
    assert result.v2_review_candidate_count >= 1
    assert result.status in (
        "dual_heuristic_review_only", "single_heuristic_review_only",
    )
    assert "activity_intent_unobservable" in result.reason_codes
    assert "detectors_share_correlated_evidence" in result.reason_codes
    assert result.raw_landmarks_exported is False
    assert result.automatic_notification_permitted is False
    assert result.emergency_dispatch_permitted is False
    assert result.fall_confirmed is False
    assert result.no_fall_confirmed is False
    assert result.calibrated_fall_probability_available is False
    rendered = asdict(result)
    assert "landmarks" not in rendered
    assert "hip_y" not in rendered


def test_short_candidate_is_withheld_by_quality_not_passed_to_ui():
    source = "fictional"
    original = stress.scenario_catalog()
    quick = next(item for item in original if item.name == "rapid_voluntary_sitting")
    short = [
        PoseFrame(
            timestamp_ms=frame.timestamp_ms,
            source_id=source,
            landmarks=frame.landmarks,
        )
        for frame in quick.frames
    ]
    result = assess(short, source_id=source)
    assert result.v2_review_candidate_count == 1
    assert result.status == "abstain_insufficient_pose"
    assert result.abstained_due_to_quality
    assert result.human_review_proposed is False
    assert "too_few_frames" in result.reason_codes
    assert result.automatic_notification_permitted is False


def test_invalid_pose_fraction_and_occlusion_causes_abstention():
    frames = frames_stationary()
    frames = [
        PoseFrame(
            timestamp_ms=f.timestamp_ms,
            source_id=f.source_id,
            landmarks={} if 5 <= i < 24 else f.landmarks,
        )
        for i, f in enumerate(frames)
    ]
    result = assess(frames, source_id="fictional")
    assert result.status == "abstain_insufficient_pose"
    assert "low_pose_coverage" in result.reason_codes
    assert "extended_pose_occlusion" in result.reason_codes
    assert result.valid_pose_frames == 11
    assert result.longest_unusable_run_frames == 19
    assert result.no_fall_confirmed is False


def test_time_gap_forces_abstention_even_with_many_good_frames():
    data = frames_stationary()
    gap = [
        PoseFrame(
            timestamp_ms=f.timestamp_ms + (1000 if i >= 20 else 0),
            source_id=f.source_id, landmarks=f.landmarks,
        )
        for i, f in enumerate(data)
    ]
    result = assess(gap, source_id="fictional")
    assert "timestamp_discontinuity" in result.reason_codes
    assert result.largest_timestamp_gap_ms == 1100
    assert result.status == "abstain_insufficient_pose"


def test_mixed_source_missing_source_duplicate_timestamps_and_empty_rejected():
    with pytest.raises(ValueError, match="Empty"):
        assess([], source_id="fictional")
    with pytest.raises(ValueError, match="source"):
        assess(frames_stationary(), source_id="another")
    data = frames_stationary()
    data[5] = PoseFrame(
        timestamp_ms=data[4].timestamp_ms,
        source_id="fictional",
        landmarks=data[5].landmarks,
    )
    with pytest.raises(ValueError, match="Timestamp"):
        assess(data, source_id="fictional")
    with pytest.raises(ValueError, match="source identifier"):
        assess(frames_stationary(), source_id="")
    with pytest.raises(ValueError, match="source identifier"):
        assess(frames_stationary(), source_id="x" * 81)


def test_policy_fails_closed_on_bad_values_and_prohibited_subclasses():
    for values in (
        {"min_frames": 0},
        {"min_frames": True},
        {"min_valid_pose_fraction": 2},
        {"min_valid_pose_fraction": nan},
        {"min_torso_visibility": 0},
        {"max_gap_ms": -3},
        {"event_pair_window_ms": "200"},
    ):
        with pytest.raises(ValueError):
            Policy(**values)
    with pytest.raises(ValueError, match="policy"):
        assess(frames_stationary(), source_id="fictional", policy=object())


def test_regression_report_uses_only_12_pseudonymous_licensed_ids(tmp_path, monkeypatch):
    from sentinel_edge.pose_traces import frame_to_trace_record

    from app import review_evidence_abstention_report as report

    roots = {
        "prior": tmp_path / "previous",
        "dev": tmp_path / "development",
        "challenge": tmp_path / "challenge",
    }
    for root in roots.values():
        root.mkdir()

    monkeypatch.setattr(report, "DATA_ROOT", roots["prior"])
    monkeypatch.setattr(report, "DEV_ROOT", roots["dev"])
    monkeypatch.setattr(report, "CHALLENGE_ROOT", roots["challenge"])
    frames = [
        stress._pose(i * 100)
        for i in range(30)
    ]
    def store(root, clip_id):
        with (root / (clip_id + ".pose.jsonl")).open("w", encoding="utf-8") as stream:
            for f in frames:
                stream.write(frame_to_trace_record(f) + "\n")
    for item in report.PREVIOUS_CLIPS:
        store(roots["prior"], item.clip_id)
    for clip_id, *_ in report.DEV:
        store(roots["dev"], clip_id)
    for item in report.ADL_CHALLENGE_CLIPS:
        store(roots["challenge"], item.clip_id)

    monkeypatch.setattr(report, "summarize_existing", lambda _: {
        "edge_evaluation": {
            "clips": [
                {"clip_id": x.clip_id, "analyzed_frames": 30, "candidate_count": 0}
                for x in report.PREVIOUS_CLIPS
            ],
        },
    })
    monkeypatch.setattr(report, "baseline", lambda _: {
        "baseline": {
            "clips": [
                {"clip_id": clip_id, "analyzed_frames": 30, "candidate_count": 0}
                for clip_id, *_ in report.DEV
            ],
        },
    })
    monkeypatch.setattr(report, "evaluate_negative", lambda _: {
        "details": [
            {"clip_id": x.clip_id, "frames": 30, "v1_candidate_count": 0}
            for x in report.ADL_CHALLENGE_CLIPS
        ],
    })
    result = report.evaluate_known_cohorts()
    assert result["status"] == "TWELVE_KNOWN_CLIPS_ABSTENTION_REPLAY_COMPLETE"
    assert result["count"] == 12
    assert result["fall_labeled_clips"] == 6
    assert result["adl_labeled_clips"] == 6
    assert result["known_data_only_not_blind"] is True
    assert result["subjects_proven_disjoint"] is False
    assert result["meta_api_called"] is False
    assert result["status_counts"] == {"no_candidate_not_clearance": 12}
    assert all(row["fall_confirmed"] is False for row in result["clips"])
    assert all(row["source_id"][:2] == "FD" for row in result["clips"])


def test_report_rejects_source_baseline_candidate_inconsistency(tmp_path, monkeypatch):
    from app import review_evidence_abstention_report as report

    monkeypatch.setattr(report, "summarize_existing", lambda _: {
        "edge_evaluation": {
            "clips": [
                {"clip_id": item.clip_id, "analyzed_frames": 30, "candidate_count": 0}
                for item in report.PREVIOUS_CLIPS
            ]
        }
    })
    monkeypatch.setattr(report, "baseline", lambda _: {
        "baseline": {"clips": [
            {"clip_id": c, "analyzed_frames": 30, "candidate_count": 0}
            for c, *_ in report.DEV
        ]}
    })
    monkeypatch.setattr(report, "evaluate_negative", lambda _: {
        "details": [
            {"clip_id": x.clip_id, "frames": 30, "v1_candidate_count": 0}
            for x in report.ADL_CHALLENGE_CLIPS
        ]
    })
    # The report must not silently fabricate missing source traces.
    monkeypatch.setattr(report, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(report, "DEV_ROOT", tmp_path)
    monkeypatch.setattr(report, "CHALLENGE_ROOT", tmp_path)
    with pytest.raises(ValueError, match="source pose trace"):
        report.evaluate_known_cohorts()
