"""Independent annotation-review trust and privacy regression tests (fake bytes)."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from sentinel_edge.annotation_review import (
    blank_independent_review_template, compile_independently_reviewed_segments,
    main,
)
from sentinel_edge.temporal_training import synthetic_demo
from sentinel_edge.window_export import validate_source_plan


def _fixture(tmp_path):
    groups, _ = synthetic_demo()
    directory = tmp_path / "clips"
    directory.mkdir()
    proposals = {"version": 1, "segments": []}
    for clip in groups["clips"]:
        cid = clip["clip_id"]
        data = ("FAKE SYNTHETIC NON-VIDEO FILE " + cid).encode()
        (directory / (cid + ".avi")).write_bytes(data)
        clip["media_sha256"] = sha256(data).hexdigest()
        proposals["segments"].append({
            "clip_id": cid,
            "video": "clips/" + cid + ".avi",
            "start_ms": 0, "end_ms": 3000,
            "expected_fall": clip["expected_fall"],
            "label_reviewed": False,
            "annotation_basis": "Synthetic publisher label, NOT manually reviewed",
        })
    return groups, proposals


def _complete_reviews(groups, proposals):
    reviews = blank_independent_review_template(groups, proposals)
    assert all(row["independently_reviewed"] is False
               and row["expected_fall"] is None and row["start_ms"] is None
               and row["media_sha256"] is None
               for row in reviews["decisions"])
    for i, row in enumerate(reviews["decisions"]):
        clip = groups["clips"][i // 2]
        row.update({
            "reviewer_id": "independent-alpha" if i % 2 == 0
                           else "independent-beta",
            "expected_fall": clip["expected_fall"],
            "activity": "fall_motion" if clip["expected_fall"] else "walk",
            "start_ms": 100 if i % 2 == 0 else 150,
            "end_ms": 2900 if i % 2 == 0 else 2850,
            "media_sha256": clip["media_sha256"],
            "independently_reviewed": True,
            "uncertain": False,
            "review_note": "Reviewed complete visual action in staged test footage.",
        })
    return reviews


def test_blank_template_cannot_be_compiled_or_claim_review(tmp_path):
    groups, proposals = _fixture(tmp_path)
    blank = blank_independent_review_template(groups, proposals)
    assert len(blank["decisions"]) == 2 * len(groups["clips"])
    assert all(row["reviewer_id"] == "" for row in blank["decisions"])
    # Even when a caller fills only a pseudonymous ID, a blank decision
    # must still be rejected because it has no explicit human observation.
    blank["decisions"][0]["reviewer_id"] = "independent-alpha"
    with pytest.raises(ValueError, match="explicit certain human review"):
        compile_independently_reviewed_segments(groups, proposals, blank, root=tmp_path)


def test_two_attested_reviewers_compile_exact_exporter_contract(tmp_path):
    groups, proposals = _fixture(tmp_path)
    reviews = _complete_reviews(groups, proposals)
    compiled = compile_independently_reviewed_segments(
        groups, proposals, reviews, root=tmp_path
    )
    assert len(compiled["segments"]) == len(groups["clips"])
    assert all(s["label_reviewed"] is True for s in compiled["segments"])
    assert compiled["segments"][0]["start_ms"] == 150
    assert compiled["segments"][0]["end_ms"] == 2850
    assert all("independent-alpha" not in json.dumps(s) for s in compiled["segments"])
    assert all("Reviewed complete visual" not in json.dumps(s)
               for s in compiled["segments"])
    assert len(validate_source_plan(groups, compiled, tmp_path)) == len(groups["clips"])


@pytest.mark.parametrize("damage,expected", [
    ("duplicate_reviewer", "DISTINCT"),
    ("missing_review", "exactly two"),
    ("uncertain", "explicit certain"),
    ("not_independent", "explicit certain"),
    ("wrong_label", "Manual label disagrees"),
    ("wrong_activity", "observed Fall/ADL"),
    ("wrong_hash", "SHA-256 mismatch"),
    ("wrong_note", "Review note"),
    ("bad_interval", "disagree on activity interval"),
    ("bad_bounds", "escapes publisher clip"),
    ("extra_field", "strict v1"),
    ("unknown_clip", "Unknown or repeated clip"),
    ("activity_conflict", "disagree on observed activity"),
])
def test_human_review_validation_fails_closed(tmp_path, damage, expected):
    groups, proposals = _fixture(tmp_path)
    reviews = _complete_reviews(groups, proposals)
    a, b = reviews["decisions"][:2]
    if damage == "duplicate_reviewer":
        b["reviewer_id"] = a["reviewer_id"]
    elif damage == "missing_review":
        reviews["decisions"].pop()
    elif damage == "uncertain":
        a["uncertain"] = True
    elif damage == "not_independent":
        a["independently_reviewed"] = False
    elif damage == "wrong_label":
        a["expected_fall"] = not a["expected_fall"]
    elif damage == "wrong_activity":
        a["activity"] = "sitting" if a["expected_fall"] else "fall_motion"
    elif damage == "wrong_hash":
        a["media_sha256"] = "0" * 64
    elif damage == "wrong_note":
        a["review_note"] = "no"
    elif damage == "bad_interval":
        b["start_ms"] = 600
    elif damage == "bad_bounds":
        a["start_ms"] = 50
        b["start_ms"] = 100
        a["end_ms"] = 3050
        b["end_ms"] = 3000
    elif damage == "extra_field":
        a["reviewer_email"] = "none@example.invalid"
    elif damage == "unknown_clip":
        a["clip_id"] = "unrecognized-clip"
    elif damage == "activity_conflict":
        clip = next(c for c in groups["clips"] if not c["expected_fall"])
        negative = reviews["decisions"][2 * groups["clips"].index(clip)]
        negative["activity"] = "sit_down"
    with pytest.raises(ValueError, match=expected):
        compile_independently_reviewed_segments(groups, proposals, reviews,
                                               root=tmp_path)


def test_original_label_review_flag_is_not_trusted(tmp_path):
    groups, proposals = _fixture(tmp_path)
    tampered = deepcopy(proposals)
    tampered["segments"][0]["label_reviewed"] = True
    with pytest.raises(ValueError, match="UNREVIEWED"):
        blank_independent_review_template(groups, tampered)


def test_media_is_hashed_again_at_final_approval(tmp_path):
    groups, proposals = _fixture(tmp_path)
    reviews = _complete_reviews(groups, proposals)
    src = tmp_path / proposals["segments"][0]["video"]
    src.write_bytes(src.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        compile_independently_reviewed_segments(groups, proposals, reviews,
                                               root=tmp_path)


def test_review_split_leakage_is_not_allowed(tmp_path):
    groups, proposals = _fixture(tmp_path)
    reviews = _complete_reviews(groups, proposals)
    groups["clips"][0]["subject_id"] = groups["clips"][-1]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        compile_independently_reviewed_segments(groups, proposals, reviews,
                                               root=tmp_path)


def test_reviewed_clip_path_traversal_rejected(tmp_path):
    groups, proposals = _fixture(tmp_path)
    reviews = _complete_reviews(groups, proposals)
    proposals["segments"][0]["video"] = "../escaped.avi"
    with pytest.raises(ValueError, match="Video paths"):
        compile_independently_reviewed_segments(groups, proposals, reviews,
                                               root=tmp_path)


def test_cli_cannot_auto_approve_without_explicit_rights_and_reviews():
    with pytest.raises(SystemExit) as exc:
        main(["--mode", "compile", "--root", "any", "--groups", "g.json",
              "--proposals", "p.json", "--output", "reviewed.json"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["--mode", "compile", "--root", "any", "--groups", "g.json",
              "--proposals", "p.json", "--output", "reviewed.json",
              "--acknowledge-media-rights", "--acknowledge-review-privacy"])
    assert exc.value.code == 2
