"""Supervised research-only training: no real media and no production alerts."""
from copy import deepcopy
import json

import numpy as np
import pytest

from sentinel_edge.temporal_training import (
    WINDOW_FRAMES, pool_temporal_window, synthetic_demo, train_and_evaluate,
)


def test_actual_numpy_training_predicts_on_unseen_fictional_subjects():
    manifest, bundle = synthetic_demo()
    model, report = train_and_evaluate(manifest, bundle)
    assert report["architecture"] == "pooled_temporal_logistic_v1_NOT_TCN_OR_GRU"
    assert report["trained_on"] == "declared train subjects only"
    assert report["threshold_selected_on"] == "declared validation subjects only"
    assert report["test_subjects_excluded_from_fitting"]
    assert not report["real_world_accuracy_established"]
    assert not report["model_deployed"]
    assert report["heldout_test"]["true_positive"] > 0
    assert report["heldout_test"]["true_negative"] > 0
    assert model.weights.shape == (30,)
    assert 0.05 <= model.threshold <= .95
    assert 0 < model.model_bytes < 1500
    assert "fictional-test" not in json.dumps(report)


def test_train_parameters_independent_of_val_and_test_data():
    metadata, features = synthetic_demo()
    original, _ = train_and_evaluate(metadata, features)
    changed = deepcopy(features)
    out_of_train = {
        item["clip_id"] for item in metadata["clips"] if item["split"] != "train"
    }
    for win in changed["windows"]:
        if win["clip_id"] in out_of_train:
            # Non-train features can wildly vary but cannot alter model weights.
            for row in win["features"]:
                row[:4] = [3.0, 3.0, 3.0, 1.0]
    altered, _ = train_and_evaluate(metadata, changed)
    np.testing.assert_allclose(original.weights, altered.weights)
    np.testing.assert_allclose(original.mean, altered.mean)
    np.testing.assert_allclose(original.scale, altered.scale)
    assert altered.bias == original.bias


def test_test_labels_never_choose_threshold():
    metadata, features = synthetic_demo()
    first, report1 = train_and_evaluate(metadata, features)
    flipped = deepcopy(metadata)
    for item in flipped["clips"]:
        if item["split"] == "test":
            item["expected_fall"] = not item["expected_fall"]
    second, report2 = train_and_evaluate(flipped, features)
    assert first.threshold == second.threshold
    assert report1["validation"] == report2["validation"]
    assert report1["heldout_test"] != report2["heldout_test"]


def test_splits_must_pass_before_any_training():
    metadata, features = synthetic_demo()
    metadata["clips"][2]["subject_id"] = metadata["clips"][-1]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        train_and_evaluate(metadata, features)


def test_fall_only_data_rejected():
    metadata, features = synthetic_demo()
    metadata["clips"] = [x for x in metadata["clips"] if x["expected_fall"]]
    features["windows"] = [
        x for x in features["windows"] if x["clip_id"].endswith("-fall")
    ]
    with pytest.raises(ValueError, match="BOTH fall and ADL"):
        train_and_evaluate(metadata, features)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "infinite", "nan", "badmask",
                                   "extra", "no_obs", "short"])
def test_corrupt_derived_windows_rejected(damage):
    metadata, data = synthetic_demo()
    data = deepcopy(data)
    if damage == "missing":
        data["windows"].pop()
    elif damage == "duplicate":
        data["windows"][0]["clip_id"] = data["windows"][1]["clip_id"]
    elif damage == "infinite":
        data["windows"][0]["features"][2][1] = float("inf")
    elif damage == "nan":
        data["windows"][0]["features"][2][1] = float("nan")
    elif damage == "badmask":
        data["windows"][0]["features"][2][5] = .25
    elif damage == "extra":
        data["windows"][0]["video_path"] = "C:/private"
    elif damage == "no_obs":
        for row in data["windows"][0]["features"]:
            row[:] = [0, 0, 0, 0, 0, 0]
    elif damage == "short":
        data["windows"][0]["features"].pop()
    with pytest.raises(ValueError):
        train_and_evaluate(metadata, data)


def test_pooling_keeps_temporal_order_and_ignores_missing():
    a = [[0., 0., 0., 0., 1., 1.] for _ in range(WINDOW_FRAMES)]
    b = deepcopy(a)
    for i in range(24, 30):
        a[i][0] = .7
    for i in range(0, 6):
        b[i][0] = .7
    va, vb = pool_temporal_window(a), pool_temporal_window(b)
    assert va.shape == (30,)
    assert va[0] == 0 and va[-6] == pytest.approx(.7)
    assert vb[0] == pytest.approx(.7) and vb[-6] == 0
    assert not np.array_equal(va, vb)
    a[24][:] = [0, 0, 0, 0, 0, 0]
    a[25][:] = [0, 0, 0, 0, 0, 0]
    assert pool_temporal_window(a)[-6] == pytest.approx(.7)


def test_demo_reproducible_with_seed():
    assert synthetic_demo() == synthetic_demo()
    assert synthetic_demo(seed=7) != synthetic_demo(seed=8)
