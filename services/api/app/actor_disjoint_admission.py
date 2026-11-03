"""Fail-closed, OFFLINE research-dataset admission contract (not identity verification).

This checks only machine-readable *claims* and split/annotation structure.
Consent, subject identity and rights cannot be independently verified from
JSON flags; an outside human/legal review is always required. No real data
is bundled, downloaded, sent to Meta, or exposed to API/UI routes.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.multi_joint_research import ROOT

SCHEMA = "viil.research.actor_disjoint_manifest.v1"
PRIVATE_ROOT = ROOT / "data" / "private"
MAX_BYTES = 4_000_000
MAX_CLIPS = 40
MAX_FRAMES_TOTAL = 12_000
SPLITS = ("train", "validation", "test")
LICENSES = ("CC-BY-NC-4.0", "CC-BY-4.0", "CUSTOM_RESEARCH_CONSENT")
STATES = ("visible", "occluded", "out_of_frame")
REVIEW_FIELDS = (
    "rights_reviewed_by_human",
    "permission_scope_recorded",
    "privacy_impact_reviewed",
    "retention_and_deletion_reviewed",
    "independent_actor_annotation_reviewed",
    "identity_grouping_reviewed",
)
TOKEN = re.compile(r"^(?:C|S|CAM|A)_[a-z0-9]{3,24}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def _require_fields(obj: object, names: set[str], where: str) -> dict:
    if type(obj) is not dict or set(obj) != names:
        raise ValueError(f"{where}: unexpected or missing schema fields")
    return obj


def _token(value: object, prefix: str) -> str:
    if type(value) is not str or not TOKEN.fullmatch(value) or not value.startswith(prefix + "_"):
        raise ValueError("Invalid pseudonymous token; names and paths prohibited")
    return value


def _sha(value: object) -> str:
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError("Evidence digest must be a lowercase 64-character SHA-256")
    return value


def _int(value: object, *, at_least: int = 0, at_most: int = 2_147_483_647) -> int:
    if type(value) is not int or not at_least <= value <= at_most:
        raise ValueError("Invalid bounded integer in dataset annotation")
    return value


def _unique_tokens(values: object, prefix: str) -> tuple[str, ...]:
    if type(values) is not list or not 1 <= len(values) <= 8:
        raise ValueError("Invalid actor-token list")
    items = tuple(_token(v, prefix) for v in values)
    if len(items) != len(set(items)):
        raise ValueError("Duplicate pseudonymous actor in a clip")
    return items


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key in private research manifest")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError("Non-finite JSON constant in private manifest")


def inspect_manifest(doc: object, *, fictional_demo: bool = False) -> dict[str, object]:
    """Validate schema, splits, labels and review claims; output ONLY aggregates.

    A returned valid schema never authorizes real-world use. It does NOT
    independently establish actor identity, annotation truth or consent.
    """
    root = _require_fields(doc, {"schema", "rights", "clips"}, "manifest")
    if root["schema"] != SCHEMA:
        raise ValueError("Unsupported dataset admission manifest version")
    rights = _require_fields(root["rights"], {
        "license_id", "provenance_sha256", "rights_evidence_sha256",
        "annotation_review_sha256", "retention_plan_sha256", "declaration",
    }, "rights")
    if rights["license_id"] not in LICENSES:
        raise ValueError("Unsupported research license declaration")
    for key in ("provenance_sha256", "rights_evidence_sha256",
                "annotation_review_sha256", "retention_plan_sha256"):
        _sha(rights[key])
    declaration = _require_fields(rights["declaration"], set(REVIEW_FIELDS), "review")
    if any(declaration[x] is not True for x in REVIEW_FIELDS):
        raise ValueError("Rights, purpose, actor grouping or privacy review not declared")

    clips = root["clips"]
    if type(clips) is not list or not 3 <= len(clips) <= MAX_CLIPS:
        raise ValueError("Require bounded train/validation/test dataset clips")
    clip_ids: set[str] = set()
    source_hashes: set[str] = set()
    split_actors = {split: set() for split in SPLITS}
    split_sessions = {split: set() for split in SPLITS}
    split_cameras = {split: set() for split in SPLITS}
    splits: Counter[str] = Counter()
    total_frames = 0
    test_multi = 0
    test_occlusion = 0
    test_handoff = 0
    status_counts: Counter[str] = Counter()
    for clip in clips:
        row = _require_fields(clip, {
            "clip_token", "source_sha256", "split", "session_token",
            "camera_token", "actor_tokens", "frame_count", "frames",
        }, "clip")
        cid = _token(row["clip_token"], "C")
        digest = _sha(row["source_sha256"])
        if cid in clip_ids or digest in source_hashes:
            raise ValueError("Duplicate recording ID or exact source media content")
        clip_ids.add(cid)
        source_hashes.add(digest)
        split = row["split"]
        if type(split) is not str or split not in SPLITS:
            raise ValueError("Unknown frozen evaluation split")
        session = _token(row["session_token"], "S")
        camera = _token(row["camera_token"], "CAM")
        actors = _unique_tokens(row["actor_tokens"], "A")
        split_sessions[split].add(session)
        split_cameras[split].add(camera)
        split_actors[split].update(actors)
        declared_frames = _int(row["frame_count"], at_least=2, at_most=MAX_FRAMES_TOTAL)
        frames = row["frames"]
        if type(frames) is not list or len(frames) != declared_frames:
            raise ValueError("Incomplete or padded per-frame identity annotation")
        total_frames += declared_frames
        if total_frames > MAX_FRAMES_TOTAL:
            raise ValueError("Excessive per-frame private annotation data")
        splits[split] += 1
        last_ts = -1
        visible_once: set[str] = set()
        last_visible: set[str] | None = None
        for index, frame in enumerate(frames):
            sample = _require_fields(frame, {
                "frame_index", "timestamp_ms", "states",
            }, "frame")
            if _int(sample["frame_index"], at_most=MAX_FRAMES_TOTAL) != index:
                raise ValueError("Missing, repeated or out-of-order annotated frame")
            timestamp = _int(sample["timestamp_ms"], at_most=86_400_000)
            if timestamp <= last_ts:
                raise ValueError("Non-monotonic clip-local annotation timestamp")
            last_ts = timestamp
            states = sample["states"]
            if type(states) is not list or len(states) != len(actors):
                raise ValueError("Unlabeled/implicit actor visibility is forbidden")
            observed: set[str] = set()
            visible: set[str] = set()
            occluded_here = False
            for entry in states:
                item = _require_fields(entry, {"actor_token", "state"}, "actor-state")
                actor = _token(item["actor_token"], "A")
                if actor not in actors or actor in observed:
                    raise ValueError("Actor annotation missing, duplicated or out of scope")
                observed.add(actor)
                state = item["state"]
                if type(state) is not str or state not in STATES:
                    raise ValueError("Unrecognized explicit visibility state")
                status_counts[state] += 1
                if state == "visible":
                    visible.add(actor)
                    visible_once.add(actor)
                elif state == "occluded":
                    occluded_here = True
            if observed != set(actors):
                raise ValueError("Not every actor's status was explicitly annotated")
            if split == "test":
                if len(visible) >= 2:
                    test_multi += 1
                if occluded_here:
                    test_occlusion += 1
                if (
                    last_visible is not None
                    and len(last_visible) == len(visible) == 1
                    and last_visible.isdisjoint(visible)
                ):
                    test_handoff += 1
            last_visible = visible
        if visible_once != set(actors):
            raise ValueError("Every declared actor must be visible at least once")

    if set(splits) != set(SPLITS):
        raise ValueError("Train, validation and sealed test splits are all required")
    for i, name in enumerate(SPLITS):
        for other in SPLITS[i + 1:]:
            if split_actors[name] & split_actors[other]:
                raise ValueError("Actor leakage across research evaluation splits")
            if split_sessions[name] & split_sessions[other]:
                raise ValueError("Capture-session leakage across evaluation splits")
            if split_cameras[name] & split_cameras[other]:
                raise ValueError("Camera-domain leakage across evaluation splits")

    blockers = []
    if test_multi == 0:
        blockers.append("test_split_lacks_simultaneous_multi_person_ground_truth")
    if test_occlusion == 0:
        blockers.append("test_split_lacks_occlusion_ground_truth")
    if test_handoff == 0:
        blockers.append("test_split_lacks_single_visible_actor_handoff")
    if not fictional_demo:
        blockers.append("actual_legal_rights_identity_and_consent_not_independently_audited")
        blockers.append("actor_independence_cannot_be_verified_from_tokens")
    return {
        "status": "FICTIONAL_SCHEMA_EXERCISE" if fictional_demo else "PRIVATE_MANIFEST_STRUCTURE_CHECKED",
        "schema": SCHEMA,
        "license_claim": rights["license_id"],
        "clips": len(clips),
        "frames": total_frames,
        "split_clip_counts": {name: splits[name] for name in SPLITS},
        "explicit_state_counts": dict(sorted(status_counts.items())),
        "test_multi_person_frames": test_multi,
        "test_occlusion_frames": test_occlusion,
        "test_single_visible_actor_handoffs": test_handoff,
        "self_reported_review_checklist_complete": True,
        "machine_checkable_leakage_not_observed": True,
        "external_legal_privacy_and_identity_review_completed_by_this_tool": False,
        "evaluation_cohort_ready_for_scientific_claim": False,
        "release_authorized": False,
        "automated_alert_authorized": False,
        "live_meta_calls": False,
        "data_uploaded": False,
        "raw_actor_identifiers_or_coordinates_exported": False,
        "blocking_reasons": blockers,
    }


def _fictional_demo_manifest() -> dict:
    """Mathematical labels only: exercise schema without any human data."""
    rights = {
        "license_id": "CUSTOM_RESEARCH_CONSENT",
        "provenance_sha256": "1" * 64,
        "rights_evidence_sha256": "2" * 64,
        "annotation_review_sha256": "3" * 64,
        "retention_plan_sha256": "4" * 64,
        "declaration": {key: True for key in REVIEW_FIELDS},
    }
    specs = (
        ("train", "trn", ["a111"]),
        ("validation", "val", ["b222"]),
        ("test", "tst", ["c333", "d444"]),
    )
    clips = []
    for slot, (split, tag, actor_suffixes) in enumerate(specs):
        actors = ["A_" + x for x in actor_suffixes]
        # Test includes 2 people at same time, occlusion and an invisible
        # interframe person exchange with only 1 visible each side.
        if split == "test":
            rows = (
                ("visible", "visible"),
                ("visible", "occluded"),
                ("out_of_frame", "visible"),
                ("visible", "visible"),
            )
        else:
            rows = tuple(("visible",) for _ in range(4))
        clips.append({
            "clip_token": "C_" + tag,
            "source_sha256": str(slot+5) * 64,
            "split": split,
            "session_token": "S_" + tag,
            "camera_token": "CAM_" + tag,
            "actor_tokens": actors,
            "frame_count": 4,
            "frames": [
                {
                    "frame_index": i,
                    "timestamp_ms": i * 100,
                    "states": [
                        {"actor_token": actor, "state": rows[i][j]}
                        for j, actor in enumerate(actors)
                    ],
                } for i in range(4)
            ],
        })
    return {"schema": SCHEMA, "rights": rights, "clips": clips}


def _read_private_manifest(path: Path) -> dict:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise ValueError("Private manifest missing, invalid or symlinked")
    private = PRIVATE_ROOT.resolve()
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(private):
        raise ValueError("Private manifest cannot be read outside data/private")
    # Refuse symlinks in the full relative path, even when pointing inside.
    relative = path.absolute().relative_to(PRIVATE_ROOT.absolute())
    current = PRIVATE_ROOT
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError("Refusing symlinked private path component")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Private manifest exceeds byte limit")
    with path.open("r", encoding="utf-8") as stream:
        doc = json.load(
            stream, object_pairs_hook=_strict_pairs,
            parse_constant=_invalid_constant,
        )
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline structural readiness gate for actor-disjoint dataset"
    )
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--synthetic-demo", action="store_true")
    command.add_argument("--inspect-private", type=Path)
    parser.add_argument("--acknowledge-person-data-review", action="store_true")
    args = parser.parse_args()
    if args.inspect_private is not None and not args.acknowledge_person_data_review:
        parser.error("Explicit private person-derived annotation review acknowledgment needed")
    try:
        doc = (
            _fictional_demo_manifest()
            if args.synthetic_demo
            else _read_private_manifest(args.inspect_private)
        )
        result = inspect_manifest(doc, fictional_demo=args.synthetic_demo)
    except (ValueError, OSError, json.JSONDecodeError, UnicodeError):
        print(json.dumps({"status": "DATASET_ADMISSION_REFUSED", "release_authorized": False}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
