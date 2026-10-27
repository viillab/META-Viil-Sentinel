"""Optional development-only subject-disjoint cross-validation.

No final held-out TEST clip is pooled, fitted, scored or used to select a model.
Four deterministic outer subject groups; the next group is the inner
validation cohort and the other two groups fit the two fixed architectures.
Research diagnostics only: no model export, automatic alert or threshold change.
"""
from collections import Counter

from sentinel_edge.model_quality import (
    MIN_SELECTION_IMPROVEMENT, _fit_candidate, pooled_dynamics_v2,
)
from sentinel_edge.temporal_training import (
    _metrics, _numpy, _validate_bundle, pool_temporal_window,
)

OUTER_FOLDS = 4
MIN_DEVELOPMENT_PEOPLE = 8
MAX_DEVELOPMENT_PEOPLE = 64


def _count_both(labels, *, role: str) -> None:
    if not any(labels) or all(labels):
        raise ValueError(f"{role} must contain both Fall and ADL labels")


def cross_validate_development(manifest: dict, bundle: dict) -> dict:
    """Return aggregate-only out-of-fold metrics on development subjects.

    All feature fitting, threshold tuning, and outer scoring are isolated
    by declared people per fold. The FINAL TEST partition is only checked
    for schema integrity, never used in numerical model development.
    """
    np = _numpy()
    _, windows = _validate_bundle(manifest, bundle)
    development = sorted(
        (item for item in manifest["clips"] if item["split"] in ("train", "val")),
        key=lambda item: item["clip_id"],
    )
    subjects = sorted({item["subject_id"] for item in development})
    if not MIN_DEVELOPMENT_PEOPLE <= len(subjects) <= MAX_DEVELOPMENT_PEOPLE:
        raise ValueError("Need at least 8 and at most 64 development subjects for CV")
    subject_fold = {subject: i % OUTER_FOLDS for i, subject in enumerate(subjects)}

    # Only development metadata/feature vectors enter these matrices.
    by_fold = [[] for _ in range(OUTER_FOLDS)]
    for item in development:
        by_fold[subject_fold[item["subject_id"]]].append(item)

    labels = []
    variants = {"baseline_v1": [], "dynamics_v2": [], "inner_selected": []}
    selections = Counter()
    for outer_idx in range(OUTER_FOLDS):
        inner_idx = (outer_idx + 1) % OUTER_FOLDS
        outer = by_fold[outer_idx]
        inner = by_fold[inner_idx]
        fitting = [
            item for idx, group in enumerate(by_fold)
            if idx not in (outer_idx, inner_idx) for item in group
        ]
        # Refuse degenerate folds instead of silently manufacturing scores.
        for role, subset in (("outer", outer), ("inner", inner), ("train", fitting)):
            if not subset:
                raise ValueError(f"Empty {role} group in development CV")
            _count_both([item["expected_fall"] for item in subset], role=role)
        fit_y = np.asarray([item["expected_fall"] for item in fitting], dtype=np.int64)
        inner_y = np.asarray([item["expected_fall"] for item in inner], dtype=np.int64)
        outer_y = np.asarray([item["expected_fall"] for item in outer], dtype=np.int64)

        def pool(items, extractor):
            return np.stack([extractor(windows[item["clip_id"]]) for item in items])

        fit_v1, inner_v1, outer_v1 = (
            pool(part, pool_temporal_window) for part in (fitting, inner, outer)
        )
        fit_v2, inner_v2, outer_v2 = (
            pool(part, pooled_dynamics_v2) for part in (fitting, inner, outer)
        )
        predict_v1, t1, score1, _ = _fit_candidate(
            fit_v1, fit_y, inner_v1, inner_y
        )
        predict_v2, t2, score2, _ = _fit_candidate(
            fit_v2, fit_y, inner_v2, inner_y
        )
        p1 = predict_v1(outer_v1) >= t1
        p2 = predict_v2(outer_v2) >= t2
        choose_v2 = score2 > score1 + MIN_SELECTION_IMPROVEMENT
        selections["v2" if choose_v2 else "v1"] += 1
        labels.extend(outer_y.tolist())
        variants["baseline_v1"].extend(p1.tolist())
        variants["dynamics_v2"].extend(p2.tolist())
        variants["inner_selected"].extend((p2 if choose_v2 else p1).tolist())

    return {
        "protocol": "four_group_outer_holdout_inner_subject_validation_v1",
        "development_subject_count": len(subjects),
        "development_clips_scored": len(development),
        "outer_fold_count": OUTER_FOLDS,
        "inner_validation_group_count_per_fold": 1,
        "independent_final_test_subjects_used": 0,
        "out_of_fold": {
            name: _metrics(labels, predictions) for name, predictions in variants.items()
        },
        "folds_selected_v1": selections["v1"],
        "folds_selected_v2": selections["v2"],
        "subject_disjoint_by_declared_metadata": True,
        "no_model_saved": True,
        "reliability_proven": False,
        "important": (
            "Non-overlapping outer subject folds, but all development people "
            "are reused for training in other folds. Fold-level results are "
            "correlated and publisher labels and identity groups are unverified. "
            "Final test is excluded; neither CV nor the small final test "
            "establishes real-world fall alert reliability."
        ),
    }
