"""Only invented numerical windows; avoid private clips, identifiers and weights."""
from copy import deepcopy
import json

import pytest

from sentinel_edge.dev_crossval import cross_validate_development
from sentinel_edge.model_quality import compare_models, main as model_main
from sentinel_edge.temporal_training import synthetic_demo


def test_cross_subject_four_outer_folds_are_disjoint_and_complete():
    groups, windows = synthetic_demo()
    report = cross_validate_development(groups, windows)
    assert report["protocol"] == "four_group_outer_holdout_inner_subject_validation_v1"
    assert report["outer_fold_count"] == 4
    assert report["development_subject_count"] == 11
    assert report["independent_final_test_subjects_used"] == 0
    assert report["development_clips_scored"] == 22
    assert report["no_model_saved"] is True
    assert report["reliability_proven"] is False
    for model in ("baseline_v1", "dynamics_v2", "inner_selected"):
        confusion = report["out_of_fold"][model]
        assert (confusion["true_positive"] + confusion["false_negative"] == 11)
        assert (confusion["true_negative"] + confusion["false_positive"] == 11)
    assert (report["folds_selected_v1"] + report["folds_selected_v2"] == 4)
    assert "fictional-" not in json.dumps(report)


def test_heldout_people_and_features_cannot_affect_dev_cv():
    groups, windows = synthetic_demo()
    baseline = cross_validate_development(groups, windows)
    changed_groups, changed_windows = deepcopy(groups), deepcopy(windows)
    final_test = {c["clip_id"] for c in changed_groups["clips"]
                  if c["split"] == "test"}
    for c in changed_groups["clips"]:
        if c["clip_id"] in final_test:
            c["expected_fall"] = not c["expected_fall"]
    for item in changed_windows["windows"]:
        if item["clip_id"] in final_test:
            item["features"] = [
                [3., 3., 3., 3., 1., 1.] for _ in range(30)
            ]
    assert cross_validate_development(changed_groups, changed_windows) == baseline


def test_dev_cv_order_invariance_and_reproducibility():
    groups, windows = synthetic_demo()
    report = cross_validate_development(groups, windows)
    rev_groups, rev_windows = deepcopy(groups), deepcopy(windows)
    rev_groups["clips"].reverse()
    rev_windows["windows"].reverse()
    assert cross_validate_development(rev_groups, rev_windows) == report
    assert cross_validate_development(groups, windows) == report


def test_cv_rejects_insufficient_development_subjects():
    groups, windows = synthetic_demo()
    keep = {c["clip_id"] for c in groups["clips"]
            if c["split"] == "test" or c["subject_id"] in {
                "fictional-train-00", "fictional-val-00"
            }}
    groups["clips"] = [c for c in groups["clips"] if c["clip_id"] in keep]
    windows["windows"] = [x for x in windows["windows"] if x["clip_id"] in keep]
    with pytest.raises(ValueError, match="at least 8"):
        cross_validate_development(groups, windows)


def test_cv_refuses_split_leakage():
    groups, windows = synthetic_demo()
    groups["clips"][0]["subject_id"] = groups["clips"][-1]["subject_id"]
    with pytest.raises(ValueError, match="subject leakage"):
        cross_validate_development(groups, windows)


def test_cv_is_opt_in_to_expensive_training():
    groups, windows = synthetic_demo()
    _, standard = compare_models(groups, windows)
    assert "development_crossvalidation" not in standard
    _, augmented = compare_models(groups, windows, dev_crossval=True)
    assert "development_crossvalidation" in augmented
    assert augmented["selected_model"] == standard["selected_model"]
    assert augmented["chosen_threshold"] == standard["chosen_threshold"]
    assert augmented["heldout_test"] == standard["heldout_test"]


def test_synthetic_cli_opt_in_reports_dev_cv(capsys):
    assert model_main(["--synthetic-demo", "--dev-crossval"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["synthetic_data_only"] is True
    assert report["development_crossvalidation"]["outer_fold_count"] == 4
