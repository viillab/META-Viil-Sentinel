"""Small VERIFIED public GMDCSA-24 Fall+ADL video subset, research-only.

16 selected publisher-labeled clips from FOUR separate declared subjects.
Pins GitHub commit and per-file git blob hash. Downloads binary videos to
ignored data/private only. No weights/videos/pose traces go into source control.
Publisher labels are not human-reviewed event boundaries.
"""
from argparse import ArgumentParser
from hashlib import sha1, sha256
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from sentinel_edge.caucafall_curator import _video_metadata, publisher_label_pilot
from sentinel_edge.model_quality import compare_models

OWNER_REPO = "ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos"
PINNED_COMMIT = "5abac7693229900cf80f722e878fbb119211fc1c"
LICENSE = "MIT (Ekram Alam 2024); original source attribution required"
SOURCE_URL = "https://raw.githubusercontent.com/" + OWNER_REPO + "/" + PINNED_COMMIT
MAX_CLIP_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 95 * 1024 * 1024
# subject, publisher-folder class, clip, exact file byte length, git blob SHA1.
# Selected BEFORE running any models; no test-result-based cherry picking.
CATALOG = (
    [1,"ADL","01",8013673,"04e48b5b6e6b59f3bd1eb35abfd3025d6f689c83"],
    [1,"ADL","13",6219096,"47068d10cf263c6a6c5f9954a7d46fc90bd999ef"],
    [1,"Fall","02",6422328,"f0d333d834ca13fd0c0a920e7a7826e830bd9b38"],
    [1,"Fall","08",4343049,"e9ca3b2c85f0e3d92358d56ff645cd31d0ecf2e8"],
    [2,"ADL","13",5042870,"e9661d6f2fe026138a9a6f6e0a39bdad7ce6ddc1"],
    [2,"ADL","16",6180584,"b71643610739371a728d25294ed171ce7c2a696e"],
    [2,"Fall","01",6472725,"6f308a3873d5768ea81b932d45a521e520368592"],
    [2,"Fall","08",6240049,"8cd7c5c12beed12c7e06aac04a45fd7e554af288"],
    [3,"ADL","08",5172948,"a38dca4aed2a27d930354beeb7d36911a7b8dd55"],
    [3,"ADL","13",4930771,"1501187cf894db4e575a459d2a2af5bf4c20def5"],
    [3,"Fall","01",4135599,"63849f8c776ba8197a5df16f9e900bd97e9214be"],
    [3,"Fall","13",4490977,"d25639c966de928befc72ebfe7c02d8fea071b4b"],
    [4,"ADL","13",5741194,"3816f83a422ce780d5572a32734a30ed612dab43"],
    [4,"ADL","16",7385513,"230970de9b41962a4000cc914e61dbfedc15b130"],
    [4,"Fall","01",1714708,"8765c6ffe2c26e5cabcaf828e0a3d58e972a7fb3"],
    [4,"Fall","13",5212102,"098f7ec72f666a79dfcd426505fcc714e3138d30"],
)
assert sum(row[3] for row in CATALOG) < MAX_TOTAL_BYTES


def _source_url(subject: int, category: str, clip: str) -> str:
    return (SOURCE_URL + "/Subject%20" + str(subject) + "/" +
            quote(category, safe="") + "/" + clip + ".mp4")


def _local_path(root: Path, subject: int, category: str, clip: str) -> Path:
    return root / "clips" / ("subject-" + str(subject)) / (category + "-" + clip + ".mp4")


def _github_blob_sha1(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _fetch_binary(url: str, limit: int) -> bytes:
    """Only our generated URL on a pinned GitHub commit is fetched."""
    if not url.startswith(SOURCE_URL + "/Subject%20"):
        raise ValueError("Remote must be pinned to audited dataset source")
    with urlopen(Request(url, headers={"User-Agent": "VIIL-Sentinel-research/1.0"}),
                 timeout=45) as response:
        if response.status != 200:
            raise ValueError("HTTP download failed")
        chunks = []
        length = 0
        while True:
            chunk = response.read(min(65536, limit + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            if length > limit:
                raise ValueError("Video exceeds expected byte budget")
            chunks.append(chunk)
    return b"".join(chunks)


def download_subset(root: Path, *, fetcher=_fetch_binary) -> dict:
    """Download/resume only 16 approved public binary clips into private root.

    A corrupt existing file is NEVER overwritten. Temp creation is exclusive.
    Files are checked with both Git blob SHA1 and length; per-video SHA256
    identifies inputs for cross-split audit. No data is uploaded.
    """
    root = root.resolve()
    if root.exists() and any(p.is_symlink() for p in root.parents):
        raise ValueError("Symlinked research roots are not supported")
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 2, "permission_basis": (
        "GMDCSA-24 publisher MIT repo at " + PINNED_COMMIT + "; "
        "research-only staged clips, no independent action-label review"
    ), "clips": []}
    proposals = {"version": 1, "segments": []}
    reused = downloaded = 0
    for subject, category, clip, size, git_sha in CATALOG:
        if size > MAX_CLIP_BYTES:
            raise ValueError("Source exceeds per-clip bound")
        path = _local_path(root, subject, category, clip)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            data = path.read_bytes()
            reused += 1
        else:
            data = fetcher(_source_url(subject, category, clip), size)
            if len(data) != size or _github_blob_sha1(data) != git_sha:
                raise ValueError("Source data fails pinned integrity check")
            # Validate downloaded container before persistent commit.
            if not data.startswith(b"\x00\x00") or b"ftyp" not in data[:32]:
                raise ValueError("Unexpected video file header")
            with path.open("xb") as stream:
                stream.write(data)
            downloaded += 1
        if len(data) != size or _github_blob_sha1(data) != git_sha:
            raise ValueError("Existing media modified; refusing reuse")
        n_frames, fps = _video_metadata(path)
        end_ms = min(8000, int((n_frames - 1) * 1000 / fps))
        if not 900 <= end_ms <= 8000:
            raise ValueError("Clip duration incompatible with 30-frame sampler")
        cid = f"gmdcsa-s{subject:02d}-" + category.lower() + "-" + clip
        manifest["clips"].append({
            "clip_id": cid, "dataset_id": "gmdcsa24",
            "subject_id": f"gmdcsa-subject-{subject:02d}",
            "recording_id": cid,
            "split": "train" if subject <= 2 else "val" if subject == 3 else "test",
            "expected_fall": category == "Fall",
            "media_sha256": sha256(data).hexdigest(),
        })
        proposals["segments"].append({
            "clip_id": cid,
            "video": path.relative_to(root).as_posix(),
            "start_ms": 0, "end_ms": end_ms,
            "expected_fall": category == "Fall",
            "label_reviewed": False,
            "annotation_basis": (
                "GMDCSA-24 official Subject " + str(subject) + " / " +
                category + "/" + clip + ".mp4 publisher class + CSV. "
                "Full cropped clip, temporal action review pending"
            ),
        })
    # The same subject and media SHA256 may never appear across splits.
    from sentinel_edge.split_audit import audit_subject_splits
    audit = audit_subject_splits(manifest)
    for filename, payload in (
        ("gmdcsa-research-groups-v2.json", manifest),
        ("gmdcsa-publisher-proposals-v1.json", proposals),
    ):
        path = root / filename
        if path.exists():
            if json.loads(path.read_text("utf-8")) != payload:
                raise ValueError("Private manifest already exists and differs")
        else:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
    return {
        "dataset": "GMDCSA-24", "license": LICENSE, "source_commit": PINNED_COMMIT,
        "clip_count": len(manifest["clips"]), "subjects": 4,
        "fall_clips": sum(c["expected_fall"] for c in manifest["clips"]),
        "adl_clips": sum(not c["expected_fall"] for c in manifest["clips"]),
        "new_downloads": downloaded, "verified_reused": reused,
        "source_bytes": sum(r[3] for r in CATALOG),
        "split_counts": {k: audit[k] for k in ("train", "val", "test")},
        "label_reviewed": False, "media_committed": False,
    }


def research_pilot(root: Path, model: Path) -> dict:
    """4-subject research experiment, NOT a real-world clinical accuracy test."""
    root = root.resolve(strict=True)
    groups = json.loads((root / "gmdcsa-research-groups-v2.json").read_text("utf-8"))
    proposals = json.loads((root / "gmdcsa-publisher-proposals-v1.json").read_text("utf-8"))
    report = publisher_label_pilot(
        root, model, groups, proposals,
        trainer=compare_models,
        dataset_origin=(
            "GMDCSA-24 publisher MIT repo " + PINNED_COMMIT +
            "; publisher video class + CSV, no independent human review"
        ),
    )
    report["cross_dataset_generalization_validated"] = False
    report["dataset_subject_count"] = 4
    report["sample_selection_predeclared"] = True
    report["source_license"] = LICENSE
    return report


def _verified_private_root(root: Path) -> Path:
    """Restrict uncommitted footage to repo-local ignored data/private."""
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    requested = root.resolve()
    if not requested.is_relative_to(private):
        raise ValueError("Source media MUST be in ignored data/private")
    return requested


def main(argv=None) -> int:
    parser = ArgumentParser(description="Research-only bounded public GMDCSA videos")
    parser.add_argument("--mode", required=True, choices=("download", "pilot"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_publisher_labels:
        parser.error("Publisher labels are unreviewed; explicit acknowledgement required")
    try:
        root = _verified_private_root(args.root)
        if args.mode == "download":
            if args.model is not None:
                parser.error("--model only allowed for --mode pilot")
            summary = download_subset(root)
        else:
            if args.model is None:
                parser.error("--model is required for real pose pilot")
            summary = research_pilot(root, args.model)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
