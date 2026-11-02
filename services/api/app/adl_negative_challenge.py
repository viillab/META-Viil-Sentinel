"""Offline, two remaining *previously unused* ADL videos: false-alarm challenge.

CC BY-NC 4.0 staged human clips are downloaded under Git-ignored
data/private. Never send video or pose landmarks to Meta, any live service,
or a Git remote. Review-only V2 parameters are frozen before this challenge.
This is a small same-source convenience sample, NOT blinded/actor-disjoint
evaluation or evidence of a safe clinical false-alarm rate.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.pose_traces import read_pose_trace

from app.dev_video_research import DEV, HOLDOUT_IDS, SOURCE_TREE
from app.experimental_review_motion import (
    ExperimentalReviewMotionDetector,
    ReviewMotionConfig,
)
from app.public_video_eval import MODEL, ROOT, SOURCE_URL, _private_root, _probe_video

CHALLENGE_ROOT = ROOT / "data" / "private" / "adl_negative_challenge_v1"
MAX_FILE_BYTES = 20_000_000
RESEARCH_LICENSE = "CC BY-NC 4.0"
FIXED_V2_CONFIG = ReviewMotionConfig()  # do not tune after examining this cohort


@dataclass(frozen=True)
class ChallengeClip:
    clip_id: str
    upstream_relative_path: str
    size_bytes: int
    git_blob_sha1: str
    sha256: str


CLIPS = (
    ChallengeClip(
        "FD0001", "data/adl_no_fall/video_20260216_151903.mp4",
        12172376, "dc8c27a2cba1dbdddb3d37454b7c352bd32642f7",
        "737ce8f78042fe166fff8d64de7372fb2d8c44ef19945f27f40046e499746000",
    ),
    ChallengeClip(
        "FD0005", "data/adl_no_fall/video_20260223_151242.mp4",
        16832519, "0031a5d675ac02f280f52f0b9aec04e98b38484b",
        "eaacb0bc568de95547d302b711ad7f4d69115b7beb11084d5c1748d8221174a8",
    ),
)
ALREADY_USED = HOLDOUT_IDS | {item[0] for item in DEV}


def _verify(path: Path, clip: ChallengeClip) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing/linked licensed local research video")
    if path.stat().st_size != clip.size_bytes or clip.size_bytes > MAX_FILE_BYTES:
        raise ValueError("Clip size differs from pinned upstream dataset")
    git_hash = hashlib.sha1(f"blob {clip.size_bytes}\0".encode("ascii"))
    secure = hashlib.sha256()
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[4:8] != b"ftyp":
            raise ValueError("Expected MP4 media container")
        git_hash.update(header)
        secure.update(header)
        while chunk := handle.read(1024 * 1024):
            git_hash.update(chunk)
            secure.update(chunk)
    if git_hash.hexdigest() != clip.git_blob_sha1:
        raise ValueError("Clip does not match exact pinned Git object")
    digest = secure.hexdigest()
    if digest != clip.sha256:
        raise ValueError("Clip does not match independent SHA-256 pin")
    return digest


def download(directory: Path = CHALLENGE_ROOT) -> list[dict[str, object]]:
    private = _private_root(directory)
    receipts = []
    for clip in CLIPS:
        target = private / f"{clip.clip_id}.mp4"
        if target.is_symlink():
            raise ValueError("Symlinked private media rejected")
        if target.exists():
            sha256 = _verify(target, clip)
        else:
            partial = private / f".{clip.clip_id}.partial"
            if partial.exists() or partial.is_symlink():
                raise ValueError("Refusing to clobber incomplete private media")
            url = (
                "https://raw.githubusercontent.com/samruddhi-2308/"
                "FallDetectionDataset/main/" + clip.upstream_relative_path
            )
            try:
                with urlopen(
                    Request(url, headers={"User-Agent": "VIIL-Noncommercial-Local-ADL"}),
                    timeout=80,
                ) as response, partial.open("xb") as handle:
                    if response.url.split("/")[2] not in {
                        "raw.githubusercontent.com", "github.com",
                    }:
                        raise ValueError("Unexpected media source")
                    count = 0
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > min(MAX_FILE_BYTES, clip.size_bytes):
                            raise ValueError("Oversized licensed public media")
                        handle.write(chunk)
                    if count != clip.size_bytes:
                        raise ValueError("Incomplete public media download")
                sha256 = _verify(partial, clip)
                os.replace(partial, target)
            except Exception:
                partial.unlink(missing_ok=True)
                raise
        receipts.append({
            "clip_id": clip.clip_id, "source_label": "ADL_NO_FALL",
            "bytes": clip.size_bytes, "sha256": sha256,
            "upstream_git_blob_verified": True,
        })
    return receipts


def extract(directory: Path = CHALLENGE_ROOT, *, timeout: int = 480) -> list[dict[str, object]]:
    private = _private_root(directory)
    if not MODEL.is_file() or MODEL.is_symlink():
        raise ValueError("Local MediaPipe Pose asset unavailable")
    if not 10 <= timeout <= 1200:
        raise ValueError("Invalid local-only extraction timeout")
    results = []
    for clip in CLIPS:
        video = private / f"{clip.clip_id}.mp4"
        _verify(video, clip)
        info = _probe_video(video)
        pose_path = private / f"{clip.clip_id}.pose.jsonl"
        if pose_path.exists() or pose_path.is_symlink():
            raise ValueError("Refusing to overwrite private person-derived pose trace")
        argv = [
            sys.executable, "-m", "sentinel_edge",
            "--source", str(video), "--model", str(MODEL),
            "--source-id", clip.clip_id, "--trace-output", str(pose_path),
            "--acknowledge-pose-privacy",
        ]
        completed = subprocess.run(
            argv, cwd=str(ROOT / "services" / "edge-vision"),
            capture_output=True, text=True, check=False, timeout=timeout,
        )
        if completed.returncode:
            raise ValueError("Local PoseLandmarker extraction failed")
        results.append({
            "id": clip.clip_id, "source_label": "ADL_NO_FALL",
            "video_sha256_verified": True, "video": info,
            "media_sent_to_meta": False, "pose_exported_to_git": False,
        })
    return results


def evaluate(directory: Path = CHALLENGE_ROOT) -> dict[str, object]:
    private = _private_root(directory)
    if not CLIPS or len(CLIPS) != 2 or {x.clip_id for x in CLIPS} & ALREADY_USED:
        raise ValueError("Challenge clip IDs overlap previously inspected data")
    original_count = 0
    v2_count = 0
    reviewed_frames = 0
    negative_observed_ms = 0
    reports = []
    for clip in CLIPS:
        video = private / f"{clip.clip_id}.mp4"
        source_sha = _verify(video, clip)
        meta = _probe_video(video)
        trace = private / f"{clip.clip_id}.pose.jsonl"
        if trace.is_symlink() or not trace.is_file():
            raise ValueError("Missing, unsafe private pose trace")
        v1 = TemporalFallDetector()
        v2 = ExperimentalReviewMotionDetector(FIXED_V2_CONFIG)
        original = []
        review = []
        count = 0
        start = end = None
        for frame in read_pose_trace(trace, source_id=clip.clip_id):
            count += 1
            start = frame.timestamp_ms if start is None else start
            end = frame.timestamp_ms
            result_v1 = v1.process(frame)
            result_v2 = v2.process(frame)
            if result_v1:
                original.append(result_v1)
            if result_v2:
                review.append(result_v2)
        if count != meta["frames_reported"] or start is None or end is None:
            raise ValueError("Private pose trace incomplete relative to source video")
        reviewed_frames += count
        negative_observed_ms += max(end - start, 0)
        original_count += len(original)
        v2_count += len(review)
        reports.append({
            "clip_id": clip.clip_id, "source_label": "adl_no_fall",
            "source_video_sha256": source_sha,
            "frames": count, "duration_seconds": meta["duration_seconds"],
            "v1_candidate_count": len(original),
            "v2_review_candidate_count": len(review),
            "v2_review_hypotheses": sorted({x.hypothesis for x in review}),
            "v2_human_review_only": True,
            "fall_confirmed": False,
            "notification_sent": False,
        })
    hours = negative_observed_ms / 3_600_000
    return {
        "status": "ADL_NEGATIVE_CHALLENGE_EVALUATED",
        "source": SOURCE_URL,
        "upstream_tree": SOURCE_TREE,
        "license": RESEARCH_LICENSE,
        "only_previously_unused_clip_ids": True,
        "source_actor_disjointness_unverified": True,
        "video_count": len(reports),
        "analyzed_frames": reviewed_frames,
        "negative_observed_hours": round(hours, 6),
        "v1_candidate_count": original_count,
        "v2_review_candidate_count": v2_count,
        "v1_negative_clips_flagged": sum(x["v1_candidate_count"] > 0 for x in reports),
        "v2_negative_clips_flagged": sum(x["v2_review_candidate_count"] > 0 for x in reports),
        "v2_review_candidates_per_negative_hour": (
            round(v2_count / hours, 4) if hours else None
        ),
        "v2_config_frozen": asdict(FIXED_V2_CONFIG),
        "v2_review_only": True,
        "automated_emergency_dispatch": False,
        "model_clinically_validated": False,
        "meta_api_called": False,
        "data_sent_to_meta": False,
        "details": reports,
    }


def summarize_all_six_adl() -> dict[str, object]:
    """Read-only, hash-checked replay of every known ADL clip from this dataset.

    Four clips were previously inspected; two are the new negative challenge.
    This is NOT subject-separated or representative validation.
    """
    from app.dev_video_research import DEV_ROOT
    from app.public_video_eval import DATA_ROOT
    from app.review_dev_comparison import (
        compare_development_only,
        compare_previously_inspected,
    )

    previous = compare_previously_inspected(DATA_ROOT)
    development = compare_development_only(DEV_ROOT)
    fresh = evaluate(CHALLENGE_ROOT)
    entries = []
    for row in previous["clips"]:
        if row["source_label_fall"]:
            continue
        entries.append((
            row["id"], DATA_ROOT, row["frames"],
            bool(row["v1_candidate"]), bool(row["review_v2_candidate"]),
            "previously_inspected",
        ))
    for row in development["clips"]:
        if row["dataset_expected_fall"]:
            continue
        entries.append((
            row["id"], DEV_ROOT, row["analyzed_frames"],
            bool(row["original_v1_candidate"]),
            bool(row["experimental_review_candidate"]),
            "previous_development",
        ))
    for row in fresh["details"]:
        entries.append((
            row["clip_id"], CHALLENGE_ROOT, row["frames"],
            row["v1_candidate_count"] > 0, row["v2_review_candidate_count"] > 0,
            "new_negative_challenge",
        ))
    if len(entries) != 6 or len({item[0] for item in entries}) != 6:
        raise ValueError("Expected all six distinct licensed ADL clips exactly once")

    total_frames = 0
    observed_ms = 0
    summary = []
    for clip_id, root, expected_frames, original_hit, review_hit, cohort in entries:
        timestamps = [
            frame.timestamp_ms
            for frame in read_pose_trace(
                root / f"{clip_id}.pose.jsonl", source_id=clip_id,
            )
        ]
        if len(timestamps) != expected_frames or not timestamps:
            raise ValueError("ADL clip trace was incomplete or changed")
        span = max(0, timestamps[-1] - timestamps[0])
        total_frames += len(timestamps)
        observed_ms += span
        summary.append({
            "clip_id": clip_id, "cohort": cohort,
            "source_label": "adl_no_fall",
            "frames": len(timestamps), "negative_observed_seconds": round(span / 1000, 3),
            "v1_flagged": original_hit, "v2_review_flagged": review_hit,
        })
    return {
        "status": "ALL_SIX_ADL_REPLAYED_LOCALLY",
        "source": SOURCE_URL, "license": RESEARCH_LICENSE,
        "original_clips_previously_inspected": True,
        "shared_dataset_actors_may_overlap": True,
        "v2_config_frozen": asdict(FIXED_V2_CONFIG),
        "adl_clips_evaluated": len(summary),
        "total_frames": total_frames,
        "negative_observed_seconds": round(observed_ms / 1000, 3),
        "v1_negative_clips_flagged": sum(x["v1_flagged"] for x in summary),
        "v2_negative_clips_flagged": sum(x["v2_review_flagged"] for x in summary),
        "actual_clinical_false_alert_rate_established": False,
        "meta_api_called": False, "media_uploaded_to_meta": False,
        "automatic_notifications_authorized": False,
        "clips": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline noncommercial ADL negative challenge")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true")
    group.add_argument("--extract", action="store_true")
    group.add_argument("--evaluate", action="store_true")
    group.add_argument("--summarize-six", action="store_true")
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license:
        parser.error("Explicit noncommercial research/license acknowledgment required")
    try:
        if args.download:
            report = {"status": "VERIFIED_ADL_DOWNLOAD", "data": download()}
        elif args.extract:
            report = {"status": "LOCAL_POSE_EXTRACTED", "data": extract()}
        else:
            report = summarize_all_six_adl() if args.summarize_six else evaluate()
            output = CHALLENGE_ROOT / (
                "all-six-adl-summary.json" if args.summarize_six
                else "negative-challenge-report.json"
            )
            if output.is_symlink():
                raise ValueError("Private report may not be a symlink")
            output.write_text(
                json.dumps(report, indent=2, sort_keys=True), encoding="utf-8",
            )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "ADL_CHALLENGE_FAILED"}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
