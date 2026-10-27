"""Research-only dataset freeze, drift check and seal-gated private pose export.

Hash commitments detect accidental changes to a reviewed dataset. They are
NOT signatures, proof of human review/consent, or authority to deploy a model.
The release file and all training windows are private and Git-ignored.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

from sentinel_edge.annotation_review import (
    _private_input, compile_independently_reviewed_segments,
)
from sentinel_edge.motion_features import FEATURE_NAMES
from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import MAX_JSON_BYTES, WINDOW_FRAMES
from sentinel_edge.window_export import (
    _private_output_path, _read_json, extract_reviewed_windows,
)

SEAL_VERSION = 1
SEAL_KEYS = frozenset({
    "version", "protocol", "group_sha256", "publisher_proposals_sha256",
    "review_decisions_sha256", "reviewed_segments_sha256", "split_summary",
    "source_hashes_reverified", "human_identity_verified",
    "consent_verified_by_software", "production_use_authorized",
})
MAX_PRIVATE_JSON_BYTES = 5_000_000


def _digest_object(payload: object) -> str:
    """Canonical UTF-8 JSON commitment; order of clip lists remains material."""
    data = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return sha256(data).hexdigest()


def freeze_reviewed_dataset(groups: dict, proposals: dict, reviews: dict,
                            *, root: Path) -> tuple[dict, dict]:
    """Revalidate *all* consent-gated review claims and media file content.

    This verifies structural consistency only. Anyone able to rewrite all
    inputs and the unsigned seal can manufacture another matching seal.
    """
    reviewed = compile_independently_reviewed_segments(
        groups, proposals, reviews, root=root
    )
    audit = audit_subject_splits(groups)
    summary = {split: audit[split] for split in ("train", "val", "test")}
    seal = {
        "version": SEAL_VERSION,
        "protocol": "unsigned_private_reviewed_dataset_fingerprint_v1",
        "group_sha256": _digest_object(groups),
        "publisher_proposals_sha256": _digest_object(proposals),
        "review_decisions_sha256": _digest_object(reviews),
        "reviewed_segments_sha256": _digest_object(reviewed),
        "split_summary": summary,
        "source_hashes_reverified": True,
        "human_identity_verified": False,
        "consent_verified_by_software": False,
        "production_use_authorized": False,
    }
    return seal, reviewed


def verify_reviewed_dataset_seal(groups: dict, proposals: dict, reviews: dict,
                                 seal: dict, *, root: Path) -> dict:
    """Reject an altered review, clip list, group split, decision, or media."""
    if (not isinstance(seal, dict) or set(seal) != SEAL_KEYS or
            type(seal["version"]) is not int or seal["version"] != SEAL_VERSION):
        raise ValueError("Unknown or malformed reviewed dataset seal")
    current, reviewed = freeze_reviewed_dataset(
        groups, proposals, reviews, root=root
    )
    if current != seal:
        raise ValueError("Reviewed dataset seal mismatch; freeze new revision only after audit")
    return reviewed


def export_sealed_reviewed_windows(groups: dict, proposals: dict, reviews: dict,
                                   seal: dict, *, root: Path, model: Path,
                                   collector=None) -> dict:
    """No video decode before verified review, digest and split preflight.

    The exporter's existing strict SHA-256 source validation is repeated
    immediately before MediaPipe decoding. No persistent bytes are written
    by this function; CLI handles exclusive private destination.
    """
    reviewed = verify_reviewed_dataset_seal(
        groups, proposals, reviews, seal, root=root
    )
    if collector is None:
        return extract_reviewed_windows(
            groups, reviewed, root=root, model=model
        )
    return extract_reviewed_windows(
        groups, reviewed, root=root, model=model, collector=collector
    )


def _private_paths(args) -> tuple[Path, dict, dict, dict, Path]:
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    root = args.root.resolve(strict=True)
    if not root.is_dir() or not root.is_relative_to(private):
        raise ValueError("Root must be under Git-ignored data/private")
    paths = (args.groups, args.proposals, args.reviews)
    sources = []
    for path in paths:
        source = _private_input(path, private)
        if not source.is_relative_to(root):
            raise ValueError("All reviewed inputs must be below the private dataset root")
        sources.append(source)
    if args.mode != "freeze":
        seal_file = _private_input(args.seal, private)
        if not seal_file.is_relative_to(root):
            raise ValueError("Seal must be in the private dataset root")
    return root, *(_read_json(source) for source in sources), private


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Unsigned PRIVATE reviewed dataset freeze/gate")
    parser.add_argument("--mode", choices=("freeze", "verify", "export"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        help="Exclusive private research JSON output (freeze/export only)")
    parser.add_argument("--model", type=Path, help="Local .task for sealed pose export only")
    parser.add_argument("--acknowledge-media-rights", action="store_true")
    parser.add_argument("--acknowledge-review-privacy", action="store_true")
    parser.add_argument("--confirm-consent", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_media_rights and args.acknowledge_review_privacy):
        parser.error("Explicit media rights and review privacy acknowledgement required")
    if (args.mode == "freeze" and
            (args.output is None or args.model is not None)):
        parser.error("freeze requires --output and forbids --model")
    if args.mode == "verify" and (args.output is not None or args.model is not None):
        parser.error("verify forbids --output and --model")
    if (args.mode == "export" and
            (args.output is None or args.model is None or
             not args.confirm_consent or not args.acknowledge_pose_privacy)):
        parser.error("export requires --output, --model, explicit consent and pose privacy")
    try:
        root, groups, proposals, reviews, private = _private_paths(args)
        if args.mode == "freeze":
            if args.seal.resolve() != args.output.resolve():
                raise ValueError("For freeze, --seal and --output must be the SAME destination")
            destination = _private_output_path(args.output)
            if not destination.is_relative_to(root):
                raise ValueError("Seal output must be under the private dataset root")
            seal, _ = freeze_reviewed_dataset(groups, proposals, reviews, root=root)
            payload = seal
        else:
            if args.seal.stat().st_size > MAX_PRIVATE_JSON_BYTES:
                raise ValueError("Seal exceeds allowed private size")
            seal = _read_json(_private_input(args.seal, private))
            if args.mode == "verify":
                verify_reviewed_dataset_seal(
                    groups, proposals, reviews, seal, root=root
                )
                payload = None
            else:
                destination = _private_output_path(args.output)
                if not destination.is_relative_to(root):
                    raise ValueError("Pose windows must stay within their private dataset root")
                payload = export_sealed_reviewed_windows(
                    groups, proposals, reviews, seal, root=root, model=args.model
                )
        if payload is not None:
            data = json.dumps(payload, allow_nan=False, separators=(",", ":"))
            if len(data.encode("utf-8")) > MAX_JSON_BYTES:
                raise ValueError("Private reviewed dataset output exceeds 15 MiB")
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(data)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(f"Private dataset freeze rejected: {exc}")
    split_audit = audit_subject_splits(groups)
    print(json.dumps({
        "mode": args.mode,
        "research_only": True,
        "train_clips": split_audit["train"]["clips"],
        "validation_clips": split_audit["val"]["clips"],
        "test_clips": split_audit["test"]["clips"],
        "dataset_fingerprint_sha256": _digest_object(seal),
        "all_media_hashes_rechecked": True,
        "review_claims_structurally_consistent": True,
        "human_identity_verified": False,
        "consent_verified_by_software": False,
        "production_alerting_authorized": False,
        "output_is_private": payload is not None,
        "pose_window_shape": ([WINDOW_FRAMES, len(FEATURE_NAMES)]
                              if args.mode == "export" else None),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
