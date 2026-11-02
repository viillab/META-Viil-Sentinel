"""Five *development-only* public videos, completely separate from earlier holdout.

These are noncommercial CC BY-NC 4.0 research recordings showing people.
Never commit media/poses, send them to Meta, use them for notifications, or
claim this tiny convenience split offers subject-independent generalization.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from sentinel_edge.evaluation import evaluate_manifest

from app.public_video_eval import MODEL, ROOT, SOURCE_URL, _private_root, _probe_video

DEV_ROOT = ROOT / "data" / "private" / "public_fall_devset_v1"
SOURCE_COMMIT = "main"  # fixed blob digests fail closed on upstream edits
SOURCE_TREE = "2ea3acbb74db88a4c2d584b3b5a631f180b490f6"
# id, category, public path, exact bytes, original upstream Git blob object ID
DEV = (
    ("FD0034", "standing_to_fall", "data/standing_to_fall/video_20260216_152309.mp4",
     4882604, "e902ad3f8b55f95c9fa4de03c74f79600dbf20c4"),
    ("FD0011", "sitting_to_fall", "data/sitting_to_fall/video_20260216_151931.mp4",
     8462495, "df7edca2133161028a3775ee114f033db793fec9"),
    ("FD0024", "sleeping_to_fall", "data/sleeping_to_fall/video_20260223_150715.mp4",
     12742080, "4e390b81af5cffeecfe434ef118ad77f09b227af"),
    ("FD0004", "adl_no_fall", "data/adl_no_fall/video_20260216_154339.mp4",
     6181032, "108e231d134df3692ab7252980c1a95efd7e85bb"),
    ("FD0006", "adl_no_fall", "data/adl_no_fall/video_20260223_151533.mp4",
     9960480, "17b6174951aa8f5f466219e8e3536885c5356782"),
)
HOLDOUT_IDS = frozenset({"FD0033", "FD0012", "FD0032", "FD0002", "FD0003"})
# SHA-256 recorded from the first checked download; protects even against
# structural collisions in upstream Git blob SHA-1 identifiers.
EXPECTED_SHA256 = {
    "e902ad3f8b55f95c9fa4de03c74f79600dbf20c4":
        "9dcaad933728016af70deb9d6673fdd347e1c78ec6710cf1871051b71ac7a295",
    "df7edca2133161028a3775ee114f033db793fec9":
        "58324d0e01b0a705733744cbff055220723baafde2986f1ef874c1e8bbb787af",
    "4e390b81af5cffeecfe434ef118ad77f09b227af":
        "6af452b9809489ca2d45f925577c4ec4e4e6ee3d3fb92cc9efafa28762a65a02",
    "108e231d134df3692ab7252980c1a95efd7e85bb":
        "1e039d51dcd1552899ead38392135146f9861802db61212675abb76e8adf5ca0",
    "17b6174951aa8f5f466219e8e3536885c5356782":
        "1efcd5827d94805ff9d35d711c76017f37a6ff959f5eb5a21e6d5be5fc450664",
}
MAX_BYTES = 15_000_000


def _validate(path: Path, expected_size: int, expected_git_blob: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing private development video")
    if path.stat().st_size != expected_size or expected_size > MAX_BYTES:
        raise ValueError("Mismatch with pinned development video size")
    git_hash = hashlib.sha1(f"blob {expected_size}\0".encode("ascii"))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        first = stream.read(12)
        if len(first) < 12 or first[4:8] != b"ftyp":
            raise ValueError("Expected MP4 video container")
        git_hash.update(first)
        digest.update(first)
        while chunk := stream.read(1024 * 1024):
            git_hash.update(chunk)
            digest.update(chunk)
    if (
        git_hash.hexdigest() != expected_git_blob
        or digest.hexdigest() != EXPECTED_SHA256.get(expected_git_blob)
    ):
        raise ValueError("Video does not match pinned SHA-256 and upstream Git blob")
    return digest.hexdigest()


def download(directory: Path = DEV_ROOT) -> list[dict[str, object]]:
    private = _private_root(directory)
    results = []
    for clip_id, category, rel, length, git_sha in DEV:
        target = private / f"{clip_id}.mp4"
        if target.is_symlink():
            raise ValueError("Private video cannot be a symlink")
        if not target.exists():
            partial = target.with_suffix(".partial")
            if partial.exists() or partial.is_symlink():
                raise ValueError("Refusing to overwrite incomplete private video")
            url = ("https://raw.githubusercontent.com/samruddhi-2308/"
                   f"FallDetectionDataset/{SOURCE_COMMIT}/{rel}")
            try:
                with urlopen(Request(url, headers={"User-Agent": "VIIL-Noncommercial-Research"}),
                             timeout=80) as response, partial.open("xb") as handle:
                    if response.url.split("/")[2] not in {
                        "raw.githubusercontent.com", "github.com"
                    }:
                        raise ValueError("Unexpected dataset source host")
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > min(length, MAX_BYTES):
                            raise ValueError("Oversized public video rejected")
                        handle.write(chunk)
                    if total != length:
                        raise ValueError("Truncated download")
                sha256 = _validate(partial, length, git_sha)
                os.replace(partial, target)
            except Exception:
                partial.unlink(missing_ok=True)
                raise
        else:
            sha256 = _validate(target, length, git_sha)
        results.append({
            "id": clip_id, "category": category, "size": length,
            "sha256": sha256, "verified_upstream_git_blob": True,
        })
    return results


def extract(directory: Path = DEV_ROOT, *, timeout: int = 480) -> dict[str, object]:
    root = _private_root(directory)
    if not MODEL.is_file():
        raise ValueError("PoseLandmarker .task model is missing")
    if timeout < 10 or timeout > 1200:
        raise ValueError("Invalid per-video timeout")
    manifest = {"version": 1, "permission_basis": (
        f"Noncommercial local research under CC BY-NC 4.0: {SOURCE_URL}; "
        "derived pose traces private, no remote Meta inference"
    ), "clips": []}
    details = []
    for clip_id, category, _, size, git_sha in DEV:
        video = root / f"{clip_id}.mp4"
        sha256 = _validate(video, size, git_sha)
        info = _probe_video(video)
        trace = root / f"{clip_id}.pose.jsonl"
        if trace.exists() or trace.is_symlink():
            raise ValueError("Refusing to overwrite existing person-derived pose trace")
        command = [
            sys.executable, "-m", "sentinel_edge", "--source", str(video),
            "--model", str(MODEL), "--source-id", clip_id,
            "--trace-output", str(trace), "--acknowledge-pose-privacy",
        ]
        execution = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout,
            cwd=str(ROOT / "services" / "edge-vision"),
        )
        if execution.returncode:
            raise ValueError("Real local pose extraction failed for " + clip_id)
        manifest["clips"].append({
            "id": clip_id, "trace": trace.name,
            "expected_fall": category != "adl_no_fall",
        })
        details.append({
            "id": clip_id, "category": category, "video_sha256": sha256,
            "decoded_video": info, "pose_extraction_exit_code": 0,
        })
    out = root / "manifest.json"
    if out.exists() or out.is_symlink():
        raise ValueError("Refusing to overwrite development manifest")
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    results = evaluate_manifest(out)
    return {
        "status": "DEV_POSE_EXTRACTION_SUCCESS", "clips": details,
        "baseline": results, "media_uploaded_to_meta": False,
    }


def baseline(directory: Path = DEV_ROOT) -> dict[str, object]:
    private = _private_root(directory)
    path = private / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Development manifest not yet available")
    expected = [
        {"id": cid, "trace": cid + ".pose.jsonl",
         "expected_fall": category != "adl_no_fall"}
        for cid, category, _, _, _ in DEV
    ]
    stored = json.loads(path.read_text(encoding="utf-8"))
    if stored.get("clips") != expected:
        raise ValueError("Development manifest differs from frozen clip selection")
    for clip_id, _, _, size, git_sha in DEV:
        _validate(private / f"{clip_id}.mp4", size, git_sha)
        trace = private / f"{clip_id}.pose.jsonl"
        if trace.is_symlink() or not trace.is_file():
            raise ValueError("Missing private development pose trace")
    results = evaluate_manifest(path)
    if results["num_clips"] != 5:
        raise ValueError("Partial development-set evaluation is not permitted")
    return {
        "status": "DEV_BASELINE_ONLY", "source": SOURCE_URL,
        "source_tree": SOURCE_TREE, "license": "CC BY-NC 4.0",
        "holdout_not_used_for_tuning": True,
        "dev_clip_ids": [entry[0] for entry in DEV],
        "meta_called": False, "real_media_uploaded": False,
        "baseline": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local noncommercial 5-clip development set")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--download", action="store_true")
    selector.add_argument("--extract", action="store_true")
    selector.add_argument("--baseline", action="store_true")
    parser.add_argument("--acknowledge-noncommercial-license", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_noncommercial_license:
        parser.error("CC BY-NC 4.0 license acknowledgment required")
    try:
        if args.download:
            result = {"downloaded": download()}
        elif args.extract:
            result = extract()
        else:
            result = baseline()
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "DEV_EVALUATION_FAILED"}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
