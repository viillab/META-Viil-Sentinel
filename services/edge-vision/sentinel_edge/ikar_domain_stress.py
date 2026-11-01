"""Source-frozen IKAR v1.0 Fall-only public video external stress research.

Official September 2026 RODBUK/AGH Dataverse CC BY 4.0 archive.
No participant IDs, real fall-onset times or ADL clips are available.
Prespecified two lowest indexed samples per category are diagnostic
only; all remaining source videos stay unscored. Never tune thresholds,
choose a model, retrain, or produce event recall from these observations.
"""
from argparse import ArgumentParser
from collections import Counter
from hashlib import md5, sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.request import Request, urlopen

from sentinel_edge.assist_external import _evaluate_one, private_root
from sentinel_edge.caucafall_curator import _video_metadata
from sentinel_edge.private_model_training import read_private_artifact
from sentinel_edge.temporal_training import _read_bounded_json
from sentinel_edge.window_export import _private_output_path

DATASET_DOI = "doi:10.58032/AGH/A1NZPE"
DATASET_VERSION = "1.0"
DATASET_LICENSE = "CC BY 4.0"
DATASET_FILE_ID = 16904
ARCHIVE_BYTES = 127_309_918
ARCHIVE_MD5 = "2667661c258610c0c0aa4bc58a7fc7c2"
ARCHIVE_SHA256 = "722ec563082373213fe43af94173b8ad1273a703b32acb262b6f3d21dd1f7809"
BASELINE_SHA256 = "2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab"
CATEGORIES = {"trips": 92, "slips": 64, "faintings": 65, "blackouts": 57}
SELECTED_IDS = (0, 1)
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_UNPACKED_BYTES = 350 * 1024 * 1024
MEMBER = re.compile(
    r"^IKAR_dataset/(trips|slips|faintings|blackouts)/(videos|labels)/"
    r"(trips|slips|faintings|blackouts)_([0-9]+)\.(mp4|json)$"
)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            digest.update(part)
    return digest.hexdigest()


def verify_archive(path: Path) -> str:
    path = path.resolve(strict=True)
    if path.name != "IKAR_dataset.tar.gz" or path.stat().st_size != ARCHIVE_BYTES:
        raise ValueError("IKAR official archive identity or size changed")
    # Publisher MD5 is a legacy archive identifier, never an auth hash.
    # The pinned SHA-256 above is the actual strong integrity check.
    digest, md5sum = sha256(), md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
            md5sum.update(block)
    if digest.hexdigest() != ARCHIVE_SHA256 or md5sum.hexdigest() != ARCHIVE_MD5:
        raise ValueError("IKAR publisher file SHA256/MD5 mismatch")
    return digest.hexdigest()


def validate_dataverse_api(payload: dict) -> None:
    """Fail closed on official pinned version, CC BY and exact source checksum."""
    try:
        latest = payload["data"]["latestVersion"]
        if (payload["status"] != "OK"
                or latest["versionNumber"] != 1
                or latest["versionMinorNumber"] != 0
                or latest["license"]["name"] != DATASET_LICENSE):
            raise ValueError("IKAR version/license mismatch")
        entries = [
            item for item in latest["files"]
            if item["dataFile"]["filename"] == "IKAR_dataset.tar.gz"
        ]
        if len(entries) != 1:
            raise ValueError("Official publisher archive not unique")
        item, file = entries[0], entries[0]["dataFile"]
        if (item.get("restricted") is not False
                or file["id"] != DATASET_FILE_ID
                or file["filesize"] != ARCHIVE_BYTES
                or file["checksum"] != {"type": "MD5", "value": ARCHIVE_MD5}):
            raise ValueError("Official publisher file checksum/rights changed")
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Invalid official Dataverse JSON response") from exc


def fetch_official_archive(root: Path, *, opener=urlopen) -> dict:
    """HTTPS-download at most 127MB; verify upstream metadata and two hashes.

    Binary media remains Git-ignored. An existing file is NEVER overwritten.
    The caller must create the private root under data/private beforehand.
    """
    root = _private_root(root)
    uri = "https://agh.rodbuk.pl"
    request = Request(
        uri + "/api/datasets/:persistentId/?persistentId=" + DATASET_DOI,
        headers={"User-Agent": "VIIL-Sentinel-public-research/1.0"},
    )
    with opener(request, timeout=45) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Oversized official metadata response")
    validate_dataverse_api(json.loads(raw))
    path = root / "IKAR_dataset.tar.gz"
    if path.exists():
        fingerprint = verify_archive(path)
        return {"already_downloaded_and_verified": True,
                "archive_sha256": fingerprint, "archive_bytes": ARCHIVE_BYTES}
    req = Request(
        uri + f"/api/access/datafile/{DATASET_FILE_ID}",
        headers={"User-Agent": "VIIL-Sentinel-public-research/1.0"},
    )
    # This is solely a public-binary download, not a text/config-file edit.
    created = False
    try:
        with opener(req, timeout=90) as response, path.open("xb") as out:
            created = True
            count = 0
            for chunk in iter(lambda: response.read(1 << 20), b""):
                count += len(chunk)
                if count > ARCHIVE_BYTES:
                    raise ValueError("Publisher download exceeds official size")
                out.write(chunk)
        if count != ARCHIVE_BYTES:
            raise ValueError("Incomplete official IKAR download")
        fingerprint = verify_archive(path)
    except Exception:
        if created:
            path.unlink(missing_ok=True)  # only our newly created partial binary
        raise
    return {"already_downloaded_and_verified": False,
            "archive_sha256": fingerprint, "archive_bytes": ARCHIVE_BYTES}


def inspect_archive(tar) -> dict:
    """Fail closed on traversal, duplicate names, missing video-label pairs."""
    found, totals = {}, Counter()
    unpacked = 0
    for member in tar.getmembers():
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts
                or len(path.parts) > 4):
            raise ValueError("Unsafe official TAR member path")
        if member.isdir():
            continue
        if not member.isfile() or not 0 < member.size <= MAX_MEMBER_BYTES:
            raise ValueError("Unexpected TAR entry type or size")
        unpacked += member.size
        if unpacked > MAX_UNPACKED_BYTES:
            raise ValueError("Official archive exceeds extraction budget")
        matched = MEMBER.fullmatch(member.name)
        if not matched:
            # The official archive contains a small top-level README.
            if member.name == "IKAR_dataset/README.md" and member.size < 100_000:
                continue
            raise ValueError("Unknown IKAR source file in official archive")
        category, folder, prefix, index, ext = matched.groups()
        if category != prefix or (folder == "videos") != (ext == "mp4"):
            raise ValueError("Publisher video and label namespace inconsistent")
        key = (category, int(index), folder)
        if key in found:
            raise ValueError("Duplicate source category/id/media entry")
        found[key] = member
        totals[(category, folder)] += 1
    for category, expected in CATEGORIES.items():
        if (totals[(category, "videos")] != expected
                or totals[(category, "labels")] != expected
                or {key[1] for key in found if key[0] == category and key[2] == "videos"}
                != {key[1] for key in found if key[0] == category and key[2] == "labels"}):
            raise ValueError("Incomplete official category/label pairing")
        if any((category, i, "videos") not in found for i in SELECTED_IDS):
            raise ValueError("Prespecified IKAR samples missing")
    return found


def _private_root(root: Path) -> Path:
    root = private_root(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("IKAR private root not a directory")
    return root


def extract_fixed_subset(root: Path, archive: Path) -> dict:
    """Only eight frozen category-balanced videos+annotations; no other unpack."""
    root = _private_root(root)
    archive = archive.resolve(strict=True)
    if not archive.is_relative_to(root):
        raise ValueError("IKAR archive must remain inside private root")
    fingerprint = verify_archive(archive)
    manifest_path = root / "ikar-8-source-frozen-manifest-v1.json"
    items = []
    with tarfile.open(archive, mode="r:gz") as tar:
        members = inspect_archive(tar)
        for category in CATEGORIES:
            for index in SELECTED_IDS:
                obj = {"category": category, "publisher_action_id": index}
                for folder, ext in (("videos", "mp4"), ("labels", "json")):
                    member = members[(category, index, folder)]
                    output = root / "selected" / category / folder / f"{category}_{index}.{ext}"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    src = tar.extractfile(member)
                    if src is None:
                        raise ValueError("Source TAR member not a regular file")
                    data = src.read(MAX_MEMBER_BYTES + 1)
                    if len(data) != member.size:
                        raise ValueError("Publisher entry decompressed size drift")
                    digest = sha256(data).hexdigest()
                    if output.exists():
                        if output.stat().st_size != len(data) or sha256_file(output) != digest:
                            raise ValueError("Extracted source file drift; never overwrite")
                    else:
                        with output.open("xb") as stream:
                            stream.write(data)
                    obj[folder + "_sha256"] = digest
                    obj[folder + "_bytes"] = len(data)
                items.append(obj)
    report = {
        "version": 1, "doi": DATASET_DOI,
        "official_version": DATASET_VERSION, "license": DATASET_LICENSE,
        "source_dataverse_file_id": DATASET_FILE_ID,
        "archive_sha256": fingerprint,
        "archive_size_bytes": ARCHIVE_BYTES,
        "total_publisher_fall_videos": sum(CATEGORIES.values()),
        "selected_before_scoring": True, "no_ADL_available": True,
        "fall_onsets_verified": False, "subject_identity_verified": False,
        "annotation_type": "publisher_spatial_bounding_boxes_not_event_onsets",
        "selection": items,
    }
    if manifest_path.exists():
        current = _read_bounded_json(manifest_path)
        if current != report:
            raise ValueError("Previous pinned IKAR manifest drifted")
    else:
        with manifest_path.open("x", encoding="utf8") as stream:
            json.dump(report, stream, indent=2)
    return report


def validate_subset(root: Path) -> dict:
    root = _private_root(root)
    manifest = _read_bounded_json(root / "ikar-8-source-frozen-manifest-v1.json")
    if (not isinstance(manifest, dict) or set(manifest) != {
        "version", "doi", "official_version", "license", "source_dataverse_file_id",
        "archive_sha256", "archive_size_bytes", "total_publisher_fall_videos",
        "selected_before_scoring", "no_ADL_available", "fall_onsets_verified",
        "subject_identity_verified", "annotation_type", "selection",
    } or manifest["version"] != 1 or manifest["doi"] != DATASET_DOI
            or manifest["official_version"] != DATASET_VERSION
            or manifest["license"] != DATASET_LICENSE
            or manifest["source_dataverse_file_id"] != DATASET_FILE_ID
            or manifest["archive_sha256"] != ARCHIVE_SHA256
            or manifest["archive_size_bytes"] != ARCHIVE_BYTES
            or manifest["total_publisher_fall_videos"] != sum(CATEGORIES.values())
            or manifest["selected_before_scoring"] is not True
            or manifest["no_ADL_available"] is not True
            or manifest["fall_onsets_verified"] is not False
            or manifest["subject_identity_verified"] is not False
            or manifest["annotation_type"] !=
            "publisher_spatial_bounding_boxes_not_event_onsets"
            or not isinstance(manifest["selection"], list)
            or len(manifest["selection"]) != len(CATEGORIES) * len(SELECTED_IDS)):
        raise ValueError("IKAR source manifest is unpinned or claims labels")
    observed = set()
    for row in manifest["selection"]:
        if not isinstance(row, dict) or set(row) != {
            "category", "publisher_action_id",
            "videos_sha256", "videos_bytes", "labels_sha256", "labels_bytes",
        }:
            raise ValueError("Unknown IKAR reference video contract")
        cat, index = row["category"], row["publisher_action_id"]
        if cat not in CATEGORIES or type(index) is not int or index not in SELECTED_IDS:
            raise ValueError("Not a fixed predeclared IKAR source sample")
        key = (cat, index)
        if key in observed:
            raise ValueError("Duplicated frozen public source")
        observed.add(key)
        for folder, ext in (("videos", "mp4"), ("labels", "json")):
            candidate = (root / "selected" / cat / folder / f"{cat}_{index}.{ext}").resolve(
                strict=True
            )
            if (not candidate.is_relative_to(root / "selected")
                    or sha256_file(candidate) != row[folder + "_sha256"]
                    or candidate.stat().st_size != row[folder + "_bytes"]):
                raise ValueError("IKAR source sample file checksum drift")
    if observed != {(category, n) for category in CATEGORIES for n in SELECTED_IDS}:
        raise ValueError("Missing expected IKAR categories/IDs")
    return manifest


def run_frozen_stress(root: Path, model_path: Path, pose_task: Path,
                      destination: Path, *, collector=None) -> dict:
    """Fall-only diagnostics; candidate video counts are NOT event recall."""
    root = _private_root(root)
    out = _private_output_path(destination)
    pinned = validate_subset(root)
    if sha256_file(model_path) != BASELINE_SHA256:
        raise ValueError("Frozen joint V1 model SHA256 mismatch")
    model = read_private_artifact(model_path)
    if abs(model.threshold - .53) > 1e-9:
        raise ValueError("Research model threshold altered")
    if pose_task.suffix != ".task" or not pose_task.is_file():
        raise ValueError("Local official MediaPipe task missing")
    summary = {}
    for category in CATEGORIES:
        aggregate = Counter()
        for index in SELECTED_IDS:
            path = root / "selected" / category / "videos" / f"{category}_{index}.mp4"
            count, fps = _video_metadata(path)
            duration = round(1000 * count / fps)
            result = _evaluate_one(
                path, "fall", f"{category}_{index}", duration,
                pose_task, model, collector=collector or __import__(
                    "sentinel_edge.video_benchmark", fromlist=["collect_video_frames"]
                ).collect_video_frames, diagnostics=True,
                detailed_reasons=True,
            )
            diag = result["failure_diagnostic"]
            aggregate["videos"] += 1
            aggregate["decoded_frames"] += diag["decoded_frames"]
            aggregate["accepted_torso_frames"] += diag["torso_adapter_available_frames"]
            aggregate["geometry_eligible_frames"] += diag["motion_geometry_eligible_frames"]
            aggregate["selected_windows"] += result["selected_windows"]
            aggregate["pose_eligible_windows"] += result["pose_eligible_windows"]
            aggregate["pose_abstentions"] += result["pose_abstentions"]
            aggregate["candidate_videos"] += result["any_window_fall_candidate"] is True
            aggregate["all_windows_abstain_videos"] += (
                result["any_window_fall_candidate"] is None
            )
            aggregate["legacy_heuristic_events"] += diag["legacy_heuristic_event_count"]
            for reason, value in result["pose_rejection_reasons"].items():
                aggregate["pose_reason_" + reason] += value
        if (aggregate["videos"] != len(SELECTED_IDS)
                or aggregate["selected_windows"] !=
                aggregate["pose_eligible_windows"] + aggregate["pose_abstentions"]
                or sum(aggregate["pose_reason_" + reason] for reason
                       in result["pose_rejection_reasons"]) != aggregate["decoded_frames"]):
            raise ValueError("Frozen IKAR stress diagnostics inconsistent")
        summary[category] = dict(aggregate)
    report = {
        "version": 1,
        "purpose": "fall_only_frozen_external_domain_stress_NOT_EVENT_ACCURACY",
        "doi": DATASET_DOI, "dataset_version": DATASET_VERSION,
        "publisher_archive_sha256": pinned["archive_sha256"],
        "frozen_research_model_sha256": BASELINE_SHA256,
        "threshold": .53,
        "sampled_total": len(CATEGORIES) * len(SELECTED_IDS),
        "sampled_before_prediction": True,
        "all_source_videos_source_hash_checked": True,
        "publisher_fall_actions_only": True,
        "no_independent_human_fall_onsets": True,
        "no_annotated_ADL_or_event_denominator": True,
        "participant_identity_unknown_per_clip": True,
        "never_used_for_model_training_or_selection": True,
        "not_emergency_fall_alert_ready": True,
        "no_promotion_metric_inferred": True,
        "categories": summary,
    }
    with out.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def main(argv=None):
    parser = ArgumentParser(description="Pinned IKAR 2026 Fall-only offline stress study")
    parser.add_argument("--mode", required=True,
                        choices=("download", "prepare", "evaluate"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--pose-task", type=Path)
    parser.add_argument("--frozen-model", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_publisher_labels or not args.acknowledge_pose_privacy:
        parser.error("Explicit publisher action and pose privacy acknowledgements required")
    try:
        if args.mode == "download":
            if any((args.archive, args.pose_task, args.frozen_model, args.report)):
                raise ValueError("download only accepts the private root")
            output = fetch_official_archive(args.root)
        elif args.mode == "prepare":
            if (args.archive is None or args.pose_task is not None
                    or args.frozen_model is not None or args.report is not None):
                raise ValueError("prepare only accepts archive and private root")
            results = extract_fixed_subset(args.root, args.archive)
            output = {"prepared_videos": len(results["selection"]),
                      "archive_sha256": results["archive_sha256"],
                      "publisher_fall_only": True, "pose_per_clip_saved": False}
        else:
            if not all((args.pose_task, args.frozen_model, args.report)):
                raise ValueError("evaluate requires pose task, frozen model and report")
            if args.archive is not None:
                raise ValueError("evaluate does not accept an archive")
            output = run_frozen_stress(
                args.root, args.frozen_model, args.pose_task, args.report
            )
    except (ValueError, OSError, tarfile.TarError, KeyError, TypeError) as exc:
        parser.error("IKAR stress refused: " + str(exc))
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
