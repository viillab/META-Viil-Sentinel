"""Cross-dataset tests use invented numerical windows, not copied footage."""
from copy import deepcopy
import json

import numpy as np
import pytest

from sentinel_edge.joint_dataset_training import (
    SOURCE_NAMES, _digest_sources, merge_eligible_sources, main,
)
from sentinel_edge.temporal_training import (
    _validate_bundle, synthetic_demo, train_and_evaluate,
)


def two_sources():
    parts = []
    for dataset, seed in zip(SOURCE_NAMES, (7, 29)):
        manifest, bundle = synthetic_demo(seed=seed)
        names = {}
        for item in manifest["clips"]:
            old = item["clip_id"]
            new = dataset + "-" + old
            names[old] = new
            item["clip_id"] = new
            item["dataset_id"] = dataset
            item["subject_id"] = dataset + "-" + item["subject_id"]
            item["recording_id"] = new
        for row in bundle["windows"]:
            row["clip_id"] = names[row["clip_id"]]
        parts.append((manifest, bundle))
    return parts


def test_joint_audit_and_fit_includes_development_subjects_across_domains():
    groups, data = merge_eligible_sources(two_sources())
    audit, windows = _validate_bundle(groups, data)
    assert len(windows) == 56
    assert audit["train"]["subjects"] == 16
    assert audit["val"]["subjects"] == 6
    assert audit["test"]["subjects"] == 6
    assert audit["train"]["fall"] == audit["train"]["adl"] == 16
    model, report = train_and_evaluate(groups, data)
    assert model.model_bytes == 736
    assert report["test_subjects_excluded_from_fitting"] is True


def test_cross_domain_subject_leakage_refused():
    parts = two_sources()
    first_train = next(c for c in parts[0][0]["clips"] if c["split"] == "train")
    second_test = next(c for c in parts[1][0]["clips"] if c["split"] == "test")
    second_test["subject_id"] = first_train["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        merge_eligible_sources(parts)


def test_cross_domain_sha256_duplicate_refused():
    parts = two_sources()
    first_train = next(c for c in parts[0][0]["clips"] if c["split"] == "train")
    second_test = next(c for c in parts[1][0]["clips"] if c["split"] == "test")
    first_train["media_sha256"] = "a" * 64
    second_test["media_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="media hash leakage"):
        merge_eligible_sources(parts)


def test_cross_domain_clip_id_duplicate_refused():
    parts = two_sources()
    parts[1][0]["clips"][0]["clip_id"] = parts[0][0]["clips"][0]["clip_id"]
    with pytest.raises(ValueError, match="Duplicate clip ID"):
        merge_eligible_sources(parts)


def test_wrong_dataset_identity_refused():
    parts = two_sources()
    parts[1][0]["clips"][0]["dataset_id"] = "caucafall-omnifall"
    with pytest.raises(ValueError, match="Dataset identity"):
        merge_eligible_sources(parts)


def test_missing_source_fail_closed():
    with pytest.raises(ValueError, match="Exactly two"):
        merge_eligible_sources(two_sources()[:1])


def test_test_labels_and_motion_never_change_joint_fit_or_validation_threshold():
    groups, bundle = merge_eligible_sources(two_sources())
    original, _ = train_and_evaluate(groups, bundle)
    altered_groups, altered_bundle = deepcopy(groups), deepcopy(bundle)
    ids = {c["clip_id"] for c in groups["clips"] if c["split"] == "test"}
    for c in altered_groups["clips"]:
        if c["clip_id"] in ids:
            c["expected_fall"] = not c["expected_fall"]
    for row in altered_bundle["windows"]:
        if row["clip_id"] in ids:
            row["features"] = [[0.1, 0.2, 0.3, 0.4, 0.5, 1] for _ in range(30)]
    modified, _ = train_and_evaluate(altered_groups, altered_bundle)
    for attr in ("mean", "scale", "weights"):
        np.testing.assert_array_equal(getattr(original, attr), getattr(modified, attr))
    assert original.bias == modified.bias
    assert original.threshold == modified.threshold


def test_source_digest_is_bounded_and_order_sensitive():
    a = [{"dataset": "alpha", "sha256": "a" * 64},
         {"dataset": "beta", "sha256": "b" * 64}]
    b = deepcopy(a)
    assert _digest_sources(a) == _digest_sources(b)
    assert len(_digest_sources(a)) == 64
    assert _digest_sources(a) != _digest_sources(list(reversed(b)))
    assert _digest_sources(a) != _digest_sources([a[0], a[0]])
    assert "clips" not in json.dumps(a)


def test_cli_refuses_unacknowledged_public_labels_and_pose():
    with pytest.raises(SystemExit) as exc:
        main(["--cauca-root", "a", "--gmdcsa-root", "b",
              "--pose-model", "m", "--output", "o"])
    assert exc.value.code == 2
