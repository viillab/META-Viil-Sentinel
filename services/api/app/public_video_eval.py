"""Reproducible LOCAL, noncommercial five-video Edge evaluation.

Downloads only five preselected, size/Git-blob-hash-pinned CC BY-NC 4.0
research videos into ignored data/private/. No media, pose or image ever goes
to Meta or Git. Uses Member 1's unchanged actual OpenCV+MediaPipe runner.

This tiny, convenience-sampled evaluation is diagnostic, not evidence of
clinically reliable fall detection, or a subject-independent test set.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "data" / "private" / "public_fall_video_probe_v1"
MODEL = ROOT / "models" / "pose_landmarker_lite.task"
REPO = "samruddhi-2308/FallDetectionDataset"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
SOURCE_URL = f"https://github.com/{REPO}"
SOURCE_REVISION_TREE = "2ea3acbb74db88a4c2d584b3b5a631f180b490f6"
MAX_VIDEO_BYTES = 20_000_000
MAX_RECORDED_FRAMES = 12_000


@dataclass(frozen=True)
class PublicClip:
    clip_id: str
    original_path: str
    label: bool
    size: int
    git_blob_sha1: str
    sha256: str


CLIPS = (
    PublicClip(
        "FD0033", "data/standing_to_fall/video_20260216_152051.mp4",
        True, 3565031, "1f87d53a70f9f369800723f75797e163ae0c838d",
        "4a1f32db7c7133b7ed7248f31bd0429a399ceb1f6cd9e65fcb4ccc6779ab1353",
    ),
    PublicClip(
        "FD0012", "data/sitting_to_fall/video_20260216_152158.mp4",
        True, 5556922, "fb8e9fe3b77c6afd64a4420f3e65418df7e6e779",
        "fb644d44867a59abc05204867e1abb0df73394d6944092aa4610ec0919383421",
    ),
    PublicClip(
        "FD0032", "data/sleeping_to_fall/video_20260223_152328.mp4",
        True, 10369106, "3df0a58ac81c73d7d61dc7d85937974ac129a9df",
        "9cf4570ecb13c7e6fdab781a3403e1911a4c69fb03f46fa63eb47c1c50fe87db",
    ),
    PublicClip(
        "FD0002", "data/adl_no_fall/video_20260216_152523.mp4",
        False, 4130035, "49cec3073a1ba6d22110e011d3b2e03806e74aa7",
        "028a9e5c33939b2d13daafee1e26f763682edbf9fd33e2cff57e6ff1a3e8bbd1",
    ),
    PublicClip(
        "FD0003", "data/adl_no_fall/video_20260216_152939.mp4",
        False, 4448588, "6ad1d53f4d35b7e6073c6fec7ffda70368fadc70",
        "16bba229904cd3bb423199520ba46494106e088ea1b465350a20116fb8445edc",
    ),
)


def _private_root(path: Path) -> Path:
    private = (ROOT / "data" / "private").resolve(strict=True)
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(private):
        raise ValueError("Video probe must remain in ignored data/private")
    path.mkdir(parents=True, exist_ok=True)
    actual = path.resolve(strict=True)
    if not actual.is_relative_to(private):
        raise ValueError("Dataset directory changed outside ignored private storage")
    return actual


def _blob_and_sha256(path: Path, expected_size: int) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular, private video file")
    if path.stat().st_size != expected_size:
        raise ValueError("Video size does not match pinned public dataset")
    sha1 = hashlib.sha1(  # Git object ID, backed by SHA256 verification in results
        f"blob {expected_size}\0".encode("ascii")
    )
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            sha1.update(block)
            sha256.update(block)
    return sha1.hexdigest(), sha256.hexdigest()


def verify_video(path: Path, clip: PublicClip) -> str:
    digest, secure = _blob_and_sha256(path, clip.size)
    if digest != clip.git_blob_sha1 or secure != clip.sha256:
        raise ValueError(f"Dataset clip {clip.clip_id} changed from pinned upstream file")
    with path.open("rb") as handle:
        prefix = handle.read(12)
    if prefix[4:8] != b"ftyp":
        raise ValueError("Dataset file is not MP4 container media")
    return secure


def download_clips(directory: Path) -> list[dict[str, object]]:
    directory = _private_root(directory)
    results = []
    for clip in CLIPS:
        target = directory / (clip.clip_id + ".mp4")
        if target.is_symlink():
            raise ValueError("Dataset file must not be a symlink")
        if target.exists():
            sha = verify_video(target, clip)
        else:
            if clip.size > MAX_VIDEO_BYTES:
                raise ValueError("Configured public clip exceeds per-file limit")
            # GitHub raw file: source paths are committed constants,
            # and downloaded bytes MUST match the published Git blob SHA.
            uri = f"https://raw.githubusercontent.com/{REPO}/main/{clip.original_path}"
            pending = target.with_suffix(".partial")
            if pending.exists() or pending.is_symlink():
                raise ValueError("Refusing to overwrite an interrupted private download")
            try:
                with urlopen(Request(uri, headers={"User-Agent": "VIIL-Research-Eval/1.0"}),
                             timeout=60) as source, pending.open("xb") as dest:
                    if source.url.split("/")[2] not in {
                        "raw.githubusercontent.com", "github.com"
                    }:
                        raise ValueError("Unapproved dataset download origin")
                    copied = 0
                    while part := source.read(1024 * 1024):
                        copied += len(part)
                        if copied > min(MAX_VIDEO_BYTES, clip.size):
                            raise ValueError("Unexpected oversized public dataset video")
                        dest.write(part)
                    if copied != clip.size:
                        raise ValueError("Truncated dataset video")
                sha = verify_video(pending, clip)
                os.replace(pending, target)
            except Exception:
                pending.unlink(missing_ok=True)
                raise
        results.append({
            "clip_id": clip.clip_id, "label": "fall" if clip.label else "no_fall",
            "bytes": clip.size, "sha256": sha, "verified": True,
            "local_video": str(target),
        })
    return results


def _probe_video(path: Path) -> dict[str, object]:
    try:
        import cv2
    except ImportError as exc:
        raise ValueError("OpenCV video extra is not installed") from exc
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("Cannot decode authorized local dataset video")
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (
            not 1 <= frames <= MAX_RECORDED_FRAMES
            or not 1 <= fps <= 240
            or not 1 <= width <= 4096 or not 1 <= height <= 4096
        ):
            raise ValueError("Unusable/oversized video stream metadata")
        return {
            "frames_reported": frames, "fps": round(fps, 3),
            "duration_seconds": round(frames / fps, 3),
            "width": width, "height": height,
        }
    finally:
        cap.release()


def evaluate_clips(directory: Path, *, timeout_per_video: int = 180) -> dict[str, object]:
    from sentinel_edge.evaluation import evaluate_manifest

    directory = _private_root(directory)
    if not MODEL.is_file():
        raise ValueError("Local PoseLandmarker .task model missing; verify its license")
    try:
        import mediapipe  # noqa: F401
    except ImportError as exc:
        raise ValueError("MediaPipe video extra is not installed") from exc
    entries = []
    details = []
    for clip in CLIPS:
        video = directory / (clip.clip_id + ".mp4")
        checksum = verify_video(video, clip)
        metadata = _probe_video(video)
        trace = directory / (clip.clip_id + ".pose.jsonl")
        if trace.exists() or trace.is_symlink():
            raise ValueError(f"Refusing to overwrite private pose trace {clip.clip_id}")
        command = [
            sys.executable, "-m", "sentinel_edge",
            "--source", str(video), "--model", str(MODEL),
            "--source-id", clip.clip_id,
            "--trace-output", str(trace),
            "--acknowledge-pose-privacy",
        ]
        completed = subprocess.run(
            command, check=False, text=True, encoding="utf-8",
            capture_output=True, timeout=timeout_per_video,
            cwd=str(ROOT / "services" / "edge-vision"),
        )
        if completed.returncode != 0:
            # Do not leak original frames, absolute private paths or raw media.
            raise ValueError(f"Actual PoseLandmarker runner failed for {clip.clip_id}")
        entries.append({
            "id": clip.clip_id,
            "trace": trace.name,
            "expected_fall": clip.label,
        })
        details.append({
            "clip_id": clip.clip_id,
            "label": "fall" if clip.label else "no_fall",
            "original_path": clip.original_path,
            "sha256": checksum,
            "video": metadata,
            "runner_exit_code": completed.returncode,
        })
    manifest = {
        "version": 1,
        "permission_basis": (
            "Noncommercial local research evaluation, "
            f"{SOURCE_URL} under CC BY-NC 4.0 ({LICENSE_URL}); "
            "ground truth is dataset class labeling, not independently verified "
            "per-frame fall timing; never send media or pose data to Meta."
        ),
        "clips": entries,
    }
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() or manifest_path.is_symlink():
        raise ValueError("Refusing to overwrite private evaluation manifest")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    metrics = evaluate_manifest(manifest_path)
    if metrics["num_clips"] != len(CLIPS):
        raise ValueError("Partial pose evaluation is not a valid five-clip result")
    return {
        "evaluation_status": "EVALUATED_REAL_PUBLIC_STAGED_VIDEOS_LOCALLY",
        "research_only": True,
        "sample_selection": "smallest file in three fall classes + two ADL clips",
        "original_repository": SOURCE_URL,
        "upstream_tree_sha": SOURCE_REVISION_TREE,
        "license": "CC BY-NC 4.0",
        "media_transmitted_to_meta": False,
        "meta_api_called": False,
        "actual_pose_landmarker_used": True,
        "all_videos_decoded_and_frames_evaluated": True,
        "samples": details,
        "edge_evaluation": metrics,
        "private_manifest_path": str(manifest_path),
    }


def diagnose_trace(trace: Path, clip_id: str) -> dict[str, object]:
    """Report aggregated detector gate coverage WITHOUT any actual coordinates."""
    from sentinel_edge.contracts import PoseFeatures
    from sentinel_edge.detector import DetectorConfig
    from sentinel_edge.pose_traces import read_pose_trace

    cfg = DetectorConfig()
    frames = list(read_pose_trace(trace, source_id=clip_id))
    good = [
        (f.timestamp_ms, feature)
        for f in frames
        if (feature := PoseFeatures.from_frame(f, cfg.min_visibility)) is not None
    ]
    upright = [(ts, pose.hip_y) for ts, pose in good
               if pose.torso_angle_deg <= cfg.upright_max_angle_deg]
    horizontal = [(ts, pose) for ts, pose in good
                  if pose.torso_angle_deg >= cfg.horizontal_min_angle_deg]
    recent_upright_horizontal = []
    drops = []
    for timestamp, pose in good:
        baseline = [
            hip for old, hip in upright
            if old < timestamp and timestamp - old <= cfg.upright_lookback_ms
        ]
        if baseline:
            descent = pose.hip_y - min(baseline)
            drops.append(descent)
            if pose.torso_angle_deg >= cfg.horizontal_min_angle_deg:
                recent_upright_horizontal.append((timestamp, descent))
    return {
        "clip_id": clip_id,
        "frames": len(frames),
        "pose_valid_frames": len(good),
        "upright_frames": len(upright),
        "horizontal_frames": len(horizontal),
        "horizontal_frames_after_recent_upright": len(recent_upright_horizontal),
        "max_descent_after_upright_normalized": round(max(drops, default=0), 3),
        "max_descent_while_horizontal_normalized": round(
            max((drop for _, drop in recent_upright_horizontal), default=0), 3
        ),
        "max_torso_angle_deg": round(
            max((pose.torso_angle_deg for _, pose in good), default=0), 1
        ),
        "required_upright_angle_limit_deg": cfg.upright_max_angle_deg,
        "required_horizontal_angle_min_deg": cfg.horizontal_min_angle_deg,
        "required_min_hip_descent_normalized": cfg.min_hip_descent,
        "required_horizontal_hold_ms": cfg.horizontal_hold_ms,
        "source": "aggregated_local_pose_diagnostics_only",
        "raw_landmark_coordinates_exported": False,
    }


def summarize_existing(directory: Path) -> dict[str, object]:
    """Re-evaluate previously extracted traces offline without MediaPipe or network."""
    from sentinel_edge.evaluation import evaluate_manifest

    directory = _private_root(directory)
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Private five-clip pose manifest does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    permitted = [
        {"id": clip.clip_id, "trace": clip.clip_id + ".pose.jsonl",
         "expected_fall": clip.label}
        for clip in CLIPS
    ]
    if manifest.get("clips") != permitted:
        raise ValueError("Dataset trace manifest does not match pinned five videos")
    diagnostics = []
    for clip in CLIPS:
        video = directory / (clip.clip_id + ".mp4")
        verify_video(video, clip)
        video_info = _probe_video(video)
        trace = directory / (clip.clip_id + ".pose.jsonl")
        if trace.is_symlink() or not trace.is_file():
            raise ValueError("Private pose trace unavailable")
        diagnostic = diagnose_trace(trace, clip.clip_id)
        if diagnostic["frames"] != video_info["frames_reported"]:
            raise ValueError("Incomplete pose trace compared to original video")
        diagnostics.append(diagnostic)
    evaluated = evaluate_manifest(manifest_path)
    if evaluated["num_clips"] != len(CLIPS):
        raise ValueError("Incorrect number of evaluated videos")
    return {
        "status": "FIVE_PUBLIC_VIDEO_POSE_DIAGNOSTICS_COMPLETE",
        "evaluated_videos": 5,
        "upstream": SOURCE_URL,
        "source_tree": SOURCE_REVISION_TREE,
        "license": "CC BY-NC 4.0",
        "small_nonrandom_sample": True,
        "real_people_visible_in_source_videos": True,
        "meta_called": False,
        "real_media_uploaded": False,
        "thresholds_tuned_on_test_clips": False,
        "model_clinically_validated": False,
        "pose_diagnostics": diagnostics,
        "edge_evaluation": evaluated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local noncommercial fall dataset video test")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    parser.add_argument("--timeout-per-video", type=int, default=180)
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license:
        parser.error("Noncommercial research use and CC BY-NC attribution must be acknowledged")
    if not (args.download or args.evaluate or args.summarize_existing):
        parser.error("Select --download, --evaluate and/or --summarize-existing")
    if args.timeout_per_video < 10 or args.timeout_per_video > 1200:
        parser.error("timeout must be between 10 and 1200 seconds per clip")
    try:
        if args.download:
            downloaded = download_clips(DATA_ROOT)
            print(json.dumps({"downloaded": downloaded}, sort_keys=True), flush=True)
        if args.evaluate:
            result = evaluate_clips(DATA_ROOT, timeout_per_video=args.timeout_per_video)
            print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        if args.summarize_existing:
            result = summarize_existing(DATA_ROOT)
            # Store only aggregated counts and pseudonymous clip IDs; no
            # real video, raw pose coordinates, MediaPipe model, or API key.
            output = DATA_ROOT / "evaluation-summary.json"
            if output.is_symlink():
                raise ValueError("Private summary may not be a symlink")
            output.write_text(json.dumps(result, indent=2, sort_keys=True),
                              encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # Only controlled error messages; never include extracted frames.
        print(json.dumps({"status": "LOCAL_DATASET_TEST_FAILED",
                          "error_type": type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
