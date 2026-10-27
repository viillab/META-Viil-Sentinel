"""Model selection uses ONLY synthetic windows; no personal video fixtures."""
from copy import deepcopy
import json

import numpy as np
import pytest

from sentinel_edge.model_quality import (
    ARCHITECTURE, _fit_candidate, compare_models, main, pooled_dynamics_v2,
)
from sentinel_edge.temporal_training import synthetic_demo, train_and_evaluate


def test_v2_descriptor_has_motion_deltas_and_spread():
    _, bundle = synthetic_demo()
    features = bundle["windows"][1]["features"]
    descriptor = pooled_dynamics_v2(features)
    assert descriptor.shape == (40,)
    assert np.all(np.isfinite(descriptor))
    assert np.any(descriptor[30:35] != 0)
    assert np.any(descriptor[35:] > 0)


def test_v2_is_immune_to_masked_fake_poses():
    _, bundle = synthetic_demo()
    original = bundle["windows"][0]["features"]
    changed = deepcopy(original)
    changed[12] = [0, 0, 0, 0, 0, 0]
    assert np.all(np.isfinite(pooled_dynamics_v2(changed)))
    changed[12] = [123, 0, 0, 0, 0, 0]
    with pytest.raises(ValueError, match="masked 30x6"):
        pooled_dynamics_v2(changed)


def test_baseline_v1_is_unchanged_by_experiment():
    manifest, bundle = synthetic_demo()
    _, report_v1 = train_and_evaluate(manifest, bundle)
    _, comparison = compare_models(manifest, bundle)
    baseline = comparison["candidate_comparison"]["baseline_v1"]
    assert baseline["validation"] == report_v1["validation"]
    assert baseline["heldout_test"] == report_v1["heldout_test"]
    assert baseline["threshold"] == report_v1["chosen_threshold"]
    assert comparison["selected_model"] in {
        ARCHITECTURE, "pooled_temporal_logistic_v1_NOT_TCN_OR_GRU"
    }
    assert comparison["model_parameters_bytes_approx"] <= 1000
    assert comparison["automated_fall_alerting_authorized"] is False
    assert comparison["model_deployed"] is False
    assert "fictional-train" not in json.dumps(comparison)


def test_heldout_labels_do_not_choose_model_or_threshold():
    manifest, bundle = synthetic_demo()
    _, initial = compare_models(manifest, bundle)
    swapped = deepcopy(manifest)
    for item in swapped["clips"]:
        if item["split"] == "test":
            item["expected_fall"] = not item["expected_fall"]
    _, second = compare_models(swapped, bundle)
    assert initial["selected_model"] == second["selected_model"]
    assert initial["chosen_threshold"] == second["chosen_threshold"]
    assert initial["validation"] == second["validation"]
    assert initial["heldout_test"] != second["heldout_test"]


def test_test_features_do_not_select_model():
    manifest, bundle = synthetic_demo()
    _, original = compare_models(manifest, bundle)
    changed = deepcopy(bundle)
    heldout = {c["clip_id"] for c in manifest["clips"] if c["split"] == "test"}
    for item in changed["windows"]:
        if item["clip_id"] in heldout:
            for row in item["features"]:
                row[:5] = [3., 3., 3., 3., 1.]
    _, altered = compare_models(manifest, changed)
    assert original["selected_model"] == altered["selected_model"]
    assert original["chosen_threshold"] == altered["chosen_threshold"]
    for candidate in ("baseline_v1", "dynamics_v2"):
        assert (original["candidate_comparison"][candidate]["validation"]
                == altered["candidate_comparison"][candidate]["validation"])


def test_prevent_subject_overlap_before_model_fitting():
    manifest, bundle = synthetic_demo()
    manifest["clips"][0]["subject_id"] = manifest["clips"][-1]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        compare_models(manifest, bundle)


def test_class_imbalanced_training_is_refused():
    x = np.zeros((2, 30))
    with pytest.raises(ValueError, match="Both Fall and ADL"):
        _fit_candidate(x, np.array([1, 1]), x, np.array([0, 1]))


def test_deterministic_and_runnable_as_synthetic_cli(capsys):
    manifest, bundle = synthetic_demo()
    _, a = compare_models(manifest, bundle)
    _, b = compare_models(manifest, bundle)
    assert a == b
    assert main(["--synthetic-demo"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["synthetic_data_only"] is True
    assert payload["model_artifact_saved"] is False


def test_real_cli_requires_explicit_research_acknowledgements():
    with pytest.raises(SystemExit) as exc:
        main(["--root", "private", "--groups", "g.json",
              "--segments", "s.json", "--model", "pose.task"])
    assert exc.value.code == 2
