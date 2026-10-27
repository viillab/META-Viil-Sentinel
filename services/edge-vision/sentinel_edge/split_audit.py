"""Fail-closed, metadata-only train/validation/test grouping for fall research.

Prevents inadvertent use of the same volunteer, recording or media digest on
both sides of a model validation. This audits declarations, NOT identities
and cannot independently prove the metadata are truthful. No video is read.
"""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path
import re

TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$", re.ASCII)
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
SPLITS = ("train", "val", "test")
MAX_CLIPS = 100_000
CLIP_FIELDS = frozenset({
    "clip_id", "dataset_id", "subject_id", "recording_id",
    "split", "expected_fall", "media_sha256",
})


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError(f"{field} must be a pseudonymous lowercase ASCII slug")
    return value


def audit_subject_splits(manifest: dict) -> dict:
    """Return aggregate-only counts; fail on subject/media/view leakage.

    Neither this helper nor its output can authorize training on sensitive
    footage without separate license, consent and privacy review.
    """
    if (not isinstance(manifest, dict) or
            set(manifest) != {"version", "permission_basis", "clips"} or
            type(manifest["version"]) is not int or manifest["version"] != 2):
        raise ValueError("Expected exact version=2 research manifest keys")
    permission = manifest["permission_basis"]
    if not isinstance(permission, str) or not permission.strip() or len(permission) > 500:
        raise ValueError("A bounded dataset permission_basis is required")
    clips = manifest["clips"]
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ValueError("Expected 1..100000 clip metadata entries")

    seen_ids = set()
    owner_by_subject: dict[str, str] = {}
    owner_by_recording: dict[str, str] = {}
    owner_by_hash: dict[str, str] = {}
    labels_by_recording: dict[str, bool] = {}
    labels_by_hash: dict[str, bool] = {}
    counts = Counter()
    subjects = {s: set() for s in SPLITS}

    for item in clips:
        if not isinstance(item, dict) or not (set(item) == CLIP_FIELDS or
                                             set(item) == CLIP_FIELDS - {"media_sha256"}):
            raise ValueError("Clip metadata fields must match the research schema")
        clip_id = _token(item["clip_id"], "clip_id")
        if clip_id in seen_ids:
            raise ValueError("clip_id duplicated")
        seen_ids.add(clip_id)
        dataset = _token(item["dataset_id"], "dataset_id")
        subject = _token(item["subject_id"], "subject_id")
        recording = _token(item["recording_id"], "recording_id")
        split = item["split"]
        if split not in SPLITS:
            raise ValueError("split must be train, val or test")
        if type(item["expected_fall"]) is not bool:
            raise ValueError("expected_fall must be an explicit boolean")
        digest = item.get("media_sha256")
        if digest is not None and (
            not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None
        ):
            raise ValueError("media_sha256 must be a lowercase SHA-256 digest")

        # A stable volunteer identity must be consistent across datasets.
        # Different camera views of a single take share recording_id.
        for key, group, title in (
            (subject, owner_by_subject, "subject"),
            (f"{dataset}/{recording}", owner_by_recording, "recording"),
        ):
            previous = group.setdefault(key, split)
            if previous != split:
                raise ValueError(f"{title} leakage across splits")
        recording_key = f"{dataset}/{recording}"
        previous_label = labels_by_recording.setdefault(
            recording_key, item["expected_fall"]
        )
        if previous_label != item["expected_fall"]:
            raise ValueError("contradictory labels for the same recording")
        if digest is not None:
            previous_hash_label = labels_by_hash.setdefault(digest, item["expected_fall"])
            if previous_hash_label != item["expected_fall"]:
                raise ValueError("contradictory labels for the same media hash")
            previous = owner_by_hash.setdefault(digest, split)
            if previous != split:
                raise ValueError("media hash leakage across splits")
        subjects[split].add(subject)
        counts[(split, "fall" if item["expected_fall"] else "adl")] += 1

    missing_splits = [split for split in SPLITS if not subjects[split]]
    if missing_splits:
        raise ValueError("train/val/test each require independent subjects")
    for split in SPLITS:
        if counts[(split, "fall")] == 0 or counts[(split, "adl")] == 0:
            raise ValueError(f"{split} must contain BOTH fall and ADL clips")
    return {
        "protocol": "subject_disjoint_train_val_test_v1",
        "metadata_validation_only": True,
        "permission_claim_unverified": True,
        "subject_disjoint_by_declared_ids": True,
        "safe_to_deploy": False,
        "train": {
            "clips": counts[("train", "fall")] + counts[("train", "adl")],
            "subjects": len(subjects["train"]),
            "fall": counts[("train", "fall")], "adl": counts[("train", "adl")],
        },
        "val": {
            "clips": counts[("val", "fall")] + counts[("val", "adl")],
            "subjects": len(subjects["val"]),
            "fall": counts[("val", "fall")], "adl": counts[("val", "adl")],
        },
        "test": {
            "clips": counts[("test", "fall")] + counts[("test", "adl")],
            "subjects": len(subjects["test"]),
            "fall": counts[("test", "fall")], "adl": counts[("test", "adl")],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Metadata-only subject-split audit, not model training")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.manifest.is_file() or args.manifest.stat().st_size > 5_000_000:
            raise ValueError("Manifest missing or exceeds 5 MB")
        manifest = json.loads(args.manifest.read_text("utf-8"))
        result = audit_subject_splits(manifest)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Split integrity rejected: {exc}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
