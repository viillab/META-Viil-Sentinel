"""Private, fail-closed TWO-reviewer annotation gate for research datasets.

A publisher action label is NOT independent ground truth. Never turn an
unreviewed proposal into a training window by copying its bool flag.
Reviewers must view the actual media and independently enter every decision.
The program can verify agreement and file digests but cannot verify that the
people, consent, or the observations are genuine. No media is uploaded.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.split_audit import HEX_SHA256, _token, audit_subject_splits
from sentinel_edge.window_export import (
    MAX_EXPORT_CLIPS, NearestFrameSampler, _private_output_path, _read_json,
    validate_source_plan,
)

ACTIVITIES_ADL = frozenset({
    "walk", "sit_down", "sitting", "stand_up", "standing", "kneel",
    "bend", "pickup", "lie_down", "lying", "other_adl",
})
REVIEW_FIELDS = frozenset({
    "clip_id", "reviewer_id", "expected_fall", "activity", "start_ms",
    "end_ms", "media_sha256", "independently_reviewed", "uncertain",
    "review_note",
})
REVIEW_TOLERANCE_MS = 200


def _publisher_inputs(groups: dict, proposals: dict) -> dict:
    """Audit proposal structure before preparing a template or approving it."""
    audit_subject_splits(groups)
    clips = groups["clips"]
    if len(clips) > MAX_EXPORT_CLIPS:
        raise ValueError("At most 64 source clips per review batch")
    if (not isinstance(proposals, dict) or set(proposals) != {"version", "segments"}
            or type(proposals["version"]) is not int or proposals["version"] != 1
            or not isinstance(proposals["segments"], list)
            or len(proposals["segments"]) != len(clips)):
        raise ValueError("Expected exact v1 proposal manifest with one entry per clip")

    mapped = {}
    for spec in proposals["segments"]:
        if (not isinstance(spec, dict) or set(spec) != {
            "clip_id", "video", "start_ms", "end_ms", "expected_fall",
            "label_reviewed", "annotation_basis",
        }):
            raise ValueError("Unexpected publisher proposal schema")
        cid = _token(spec["clip_id"], "clip_id")
        if cid in mapped or spec["label_reviewed"] is not False:
            raise ValueError("Only unique UNREVIEWED publisher proposals accepted")
        NearestFrameSampler(cid, spec["start_ms"], spec["end_ms"])
        mapped[cid] = spec

    for clip in clips:
        cid = clip["clip_id"]
        if (cid not in mapped or
                type(mapped[cid]["expected_fall"]) is not bool or
                mapped[cid]["expected_fall"] != clip["expected_fall"]):
            raise ValueError("Publisher proposal label/clip mismatch")
        digest = clip.get("media_sha256")
        if not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
            raise ValueError("SHA-256 source media identity required per clip")
    return mapped


def blank_independent_review_template(groups: dict, proposals: dict) -> dict:
    """Blank human-entry fields; NEVER copy publisher label into an approval."""
    _publisher_inputs(groups, proposals)
    decisions = []
    for clip in groups["clips"]:
        for _ in range(2):
            decisions.append({
                "clip_id": clip["clip_id"],
                "reviewer_id": "",
                "expected_fall": None,
                "activity": None,
                "start_ms": None,
                "end_ms": None,
                "media_sha256": None,
                "independently_reviewed": False,
                "uncertain": True,
                "review_note": "",
            })
    return {"version": 1, "decisions": decisions}


def compile_independently_reviewed_segments(groups: dict, proposals: dict,
                                            reviews: dict, *, root: Path) -> dict:
    """Require two separate attested reviewers for EVERY original clip.

    No silent drop of disagreements, uncertain decisions, unreadable videos
    or original test clips. Result uses window_export's reviewed segment v1.
    """
    sources = _publisher_inputs(groups, proposals)
    if (not isinstance(reviews, dict) or set(reviews) != {"version", "decisions"}
            or type(reviews["version"]) is not int or reviews["version"] != 1
            or not isinstance(reviews["decisions"], list)
            or len(reviews["decisions"]) != 2 * len(groups["clips"])):
        raise ValueError("Expected exactly two independent decisions for every clip")

    by_clip = {clip["clip_id"]: [] for clip in groups["clips"]}
    clips = {clip["clip_id"]: clip for clip in groups["clips"]}
    for decision in reviews["decisions"]:
        if not isinstance(decision, dict) or set(decision) != REVIEW_FIELDS:
            raise ValueError("Review fields must match the strict v1 decision schema")
        cid = _token(decision["clip_id"], "clip_id")
        if cid not in by_clip or len(by_clip[cid]) >= 2:
            raise ValueError("Unknown or repeated clip review")
        person = _token(decision["reviewer_id"], "reviewer_id")
        if any(prior["reviewer_id"] == person for prior in by_clip[cid]):
            raise ValueError("Two DISTINCT reviewer identities required per clip")
        if decision["independently_reviewed"] is not True or (
            decision["uncertain"] is not False
        ):
            raise ValueError("All clips require an explicit certain human review")
        label = decision["expected_fall"]
        if type(label) is not bool or label != clips[cid]["expected_fall"]:
            raise ValueError("Manual label disagrees with publisher/group manifest")
        activity = decision["activity"]
        if (not isinstance(activity, str) or
                (activity != "fall_motion" if label else activity not in ACTIVITIES_ADL)):
            raise ValueError("Explicit matching observed Fall/ADL activity required")
        digest = decision["media_sha256"]
        if digest != clips[cid]["media_sha256"]:
            raise ValueError("Reviewer-attested media SHA-256 mismatch")
        note = decision["review_note"]
        if (not isinstance(note, str) or
                not 15 <= len(note.strip()) <= 200 or
                any(ord(ch) < 32 for ch in note)):
            raise ValueError("Review note must be 15-200 printable characters")
        start, end = decision["start_ms"], decision["end_ms"]
        proposal = sources[cid]
        NearestFrameSampler(cid, start, end)
        if start < proposal["start_ms"] or end > proposal["end_ms"]:
            raise ValueError("Reviewed event interval escapes publisher clip")
        by_clip[cid].append(decision)

    approved = []
    for item in groups["clips"]:
        cid = item["clip_id"]
        pair = by_clip[cid]
        if len(pair) != 2:
            raise ValueError("Exactly two completed human entries per clip required")
        if pair[0]["activity"] != pair[1]["activity"]:
            raise ValueError("Reviewers disagree on observed activity")
        if (abs(pair[0]["start_ms"] - pair[1]["start_ms"]) > REVIEW_TOLERANCE_MS or
                abs(pair[0]["end_ms"] - pair[1]["end_ms"]) > REVIEW_TOLERANCE_MS):
            raise ValueError("Reviewers disagree on activity interval; adjudicate")
        start = max(row["start_ms"] for row in pair)
        end = min(row["end_ms"] for row in pair)
        NearestFrameSampler(cid, start, end)
        proposal = sources[cid]
        approved.append({
            "clip_id": cid,
            "video": proposal["video"],
            "start_ms": start,
            "end_ms": end,
            "expected_fall": item["expected_fall"],
            "label_reviewed": True,
            "annotation_basis": (
                "Two independently attested reviewer entries agree on "
                + pair[0]["activity"] + " and bounded activity interval"
            ),
        })

    reviewed = {"version": 1, "segments": approved}
    # Reuse the actual reviewed exporter for strict relative paths, media
    # SHA-256, file size, split integrity and exact final output contract.
    validate_source_plan(groups, reviewed, root.resolve(strict=True))
    return reviewed


def _private_input(path: Path, private: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(private):
        raise ValueError("Research manifest must be an existing private file")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Private human-label review; NEVER auto-approve")
    parser.add_argument("--mode", choices=("prepare", "compile"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-media-rights", action="store_true")
    parser.add_argument("--acknowledge-review-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_media_rights or not args.acknowledge_review_privacy:
        parser.error("Require explicit local research rights/privacy acknowledgements")
    if (args.mode == "compile") != (args.reviews is not None):
        parser.error("--reviews is mandatory for compile, forbidden for prepare")
    try:
        private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
        root = args.root.resolve(strict=True)
        if not root.is_dir() or not root.is_relative_to(private):
            raise ValueError("Media root must be within Git-ignored data/private")
        groups_file = _private_input(args.groups, private)
        proposals_file = _private_input(args.proposals, private)
        if not groups_file.is_relative_to(root) or not proposals_file.is_relative_to(root):
            raise ValueError("Media-group and proposal manifest must be under media root")
        output = _private_output_path(args.output)
        groups, proposals = _read_json(groups_file), _read_json(proposals_file)
        if args.mode == "prepare":
            payload = blank_independent_review_template(groups, proposals)
        else:
            decision_file = _private_input(args.reviews, private)
            payload = compile_independently_reviewed_segments(
                groups, proposals, _read_json(decision_file), root=root
            )
        data = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
        if len(data.encode("utf-8")) > 5_000_000:
            raise ValueError("Review payload exceeds 5 MB")
        # Fail-closed on overwrites; no processed media, keypoints or model export.
        with output.open("x", encoding="utf-8") as handle:
            handle.write(data)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(f"Private annotation review refused: {exc}")
    print(json.dumps({
        "research_only": True,
        "mode": args.mode,
        "clips": len(groups["clips"]),
        "entries": len(payload["decisions"] if args.mode == "prepare"
                       else payload["segments"]),
        "review_statements_structurally_consistent": args.mode == "compile",
        "verified_human_identity": False,
        "raw_media_or_pose_exported": False,
        "clinical_use_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
