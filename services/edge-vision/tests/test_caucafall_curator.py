"""Curator tests use only fictional AVI bytes and invented annotations."""
from collections import Counter
from pathlib import Path

import pytest

from sentinel_edge.caucafall_curator import (
    CLASS_NAMES, curate, publisher_label_pilot, read_publisher_annotations,
)


def fake_root(tmp_path: Path, *, skip_adl=False):
    lines = ["path,label,start,end,subject,cam,dataset"]
    labels = []
    for subject in range(1, 11):
        examples = [
            ("forward", f"FallForwardS{subject}", 1),
            ("side", f"FallRightS{subject}", 1),
            ("adl", f"SitDownS{subject}", 3),
            ("adl", f"WalkS{subject}", 0),
            ("forward", f"FallForwardOtherS{subject}", 2),
            ("side", f"FallUnknownS{subject}", 9),
            ("forward", f"FallForwardBeforeS{subject}", 0),
        ]
        for folder, name, label in examples:
            if skip_adl and folder == "adl" and subject == 10:
                continue
            relative = f"Subject.{subject}/{name}_{label}_0.000_3.000_{subject}_1_caucafall.avi"
            video = tmp_path / "clips" / f"Subject.{subject}" / Path(relative).name
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(f"FICTIONAL-{relative}".encode())
            labels.append(f"{relative.replace('/', chr(92))} {label}")
            lines.append(f"{folder}/{name},{label},0,3,{subject},1,caucafall")
    (tmp_path / "mmaction2_annotations.txt").write_text(
        "\n".join(labels) + "\n", encoding="utf-8"
    )
    (tmp_path / "caucafall.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return tmp_path


def mock_video_info(path):
    assert path.is_file()
    return 60, 20.0


def test_curation_real_protocol_subject_groups_and_separate_publisher_review(tmp_path):
    root = fake_root(tmp_path)
    groups, proposals, summary = curate(root, metadata_reader=mock_video_info)
    assert len(groups["clips"]) == 40
    assert len(proposals["segments"]) == 40
    assert summary["selected"] == {
        "train": {"fall": 12, "adl": 12},
        "val": {"fall": 4, "adl": 4},
        "test": {"fall": 4, "adl": 4},
    }
    assert summary["manual_label_review_completed"] is False
    assert summary["ready_for_reviewed_window_export"] is False
    assert all(s["label_reviewed"] is False for s in proposals["segments"])
    assert {x["split"] for x in groups["clips"]} == {"train", "val", "test"}
    assert {x["expected_fall"] for x in groups["clips"]} == {False, True}
    assert all(len(x["media_sha256"]) == 64 for x in groups["clips"])
    assert summary["publisher_class_counts"] == {
        CLASS_NAMES[i]: {0: 20, 1: 20, 2: 10, 3: 10, 9: 10}.get(i, 0)
        for i in sorted(CLASS_NAMES)
    }


def test_filename_fall_context_but_not_fall_motion_excluded(tmp_path):
    groups, proposals, _ = curate(fake_root(tmp_path), metadata_reader=mock_video_info)
    assert all("before" not in g["clip_id"] for g in groups["clips"])
    assert all("fallen" not in p["annotation_basis"] for p in proposals["segments"])
    assert Counter(g["expected_fall"] for g in groups["clips"]) == {True: 20, False: 20}


def test_missing_adl_subject_blocks_complete_split(tmp_path):
    root = fake_root(tmp_path, skip_adl=True)
    with pytest.raises(ValueError, match="Not enough independent"):
        curate(root, metadata_reader=mock_video_info)


def test_tampered_publisher_annotation_detected(tmp_path):
    root = fake_root(tmp_path)
    ann = root / "mmaction2_annotations.txt"
    text = ann.read_text("utf-8")
    ann.write_text(text.replace("_1_0.000_3.000", "_9_0.000_3.000", 1), "utf-8")
    with pytest.raises(ValueError, match="no matching original CSV|disagrees"):
        read_publisher_annotations(root)


def test_bad_source_filename_or_missing_video_rejected(tmp_path):
    root = fake_root(tmp_path)
    ann = root / "mmaction2_annotations.txt"
    text = ann.read_text("utf-8")
    ann.write_text("../secret.avi 1\n" + text, "utf-8")
    with pytest.raises(ValueError, match="unsafe clip path"):
        read_publisher_annotations(root)


def test_too_short_video_is_not_eligible(tmp_path):
    root = fake_root(tmp_path)
    def short_info(path):
        if "WalkS10" in str(path):
            return 10, 20.0
        return mock_video_info(path)
    with pytest.raises(ValueError, match="Not enough independent"):
        curate(root, metadata_reader=short_info)


def test_not_allowed_to_fake_manual_review_in_publisher_pilot(tmp_path):
    root = fake_root(tmp_path)
    groups, proposals, _ = curate(root, metadata_reader=mock_video_info)
    proposals["segments"][0]["label_reviewed"] = True
    model = tmp_path / "test.task"
    model.write_bytes(b"FAKE")
    with pytest.raises(ValueError, match="unreviewed publisher"):
        publisher_label_pilot(root, model, groups, proposals,
                              collector=lambda **kwargs: None)


def test_bad_cap_refused(tmp_path):
    with pytest.raises(ValueError, match="between 1 and 3"):
        curate(fake_root(tmp_path), per_class_per_subject=4,
               metadata_reader=mock_video_info)
