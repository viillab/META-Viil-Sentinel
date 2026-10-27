"""Experimental lightweight temporal model comparison, never a live fall alarm.

Deterministic candidate selection uses TRAIN subjects for fitting and VAL
subjects for choosing both a model and threshold. The TEST subjects are only
loaded *after* selection. No video, person identifiers, features or fitted
weights are printed or persisted.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.temporal_training import (
    _metrics, _numpy, _read_bounded_json, _validate_bundle,
    pool_temporal_window,
)

ARCHITECTURE = "masked_temporal_dynamics_v2_numpy_logistic"
THRESHOLDS = tuple(round(x / 100, 2) for x in range(95, 4, -1))
MIN_SELECTION_IMPROVEMENT = 0.01


def pooled_dynamics_v2(features):
    """30 old time-bin means + 5 signed motion deltas + 5 robust spreads.

    Each extra statistic is mask-aware and depends only on one clip; the
    existing 30x6 on-disk contract and original baseline remain unchanged.
    """
    np = _numpy()
    arr = np.asarray(features, dtype=np.float64)
    # Validate even if called without the strict bundle parser.
    if (arr.shape != (30, 6) or not np.isfinite(arr).all()
            or not np.isin(arr[:, -1], [0, 1]).all()
            or np.any((arr[:, -1] == 0)[:, None] & (arr[:, :-1] != 0))):
        raise ValueError("Expected finite, masked 30x6 motion features")
    mask = arr[:, -1] == 1
    if np.count_nonzero(mask) < 10:
        raise ValueError("At least ten observed poses are required")
    original = pool_temporal_window(features)
    # Difference between later and earlier observable torso/motion signals.
    def masked_mean(part):
        visible = part[part[:, -1] == 1, :-1]
        return visible.mean(axis=0) if len(visible) else np.zeros(5)
    delta = masked_mean(arr[20:]) - masked_mean(arr[:10])
    # Scaled within-clip variation; no additional learned normalization on
    # test people. Visibility/pose-mask still comes from the original bins.
    spread = np.std(arr[mask, :-1], axis=0)
    return np.concatenate((original, delta, spread))


def _fit_candidate(train_x, train_y, val_x, val_y):
    """Use class-balanced L2 NumPy fit with deterministic validation choice."""
    np = _numpy()
    mean = train_x.mean(axis=0)
    scale = np.where(train_x.std(axis=0) < 1e-6, 1.0, train_x.std(axis=0))
    x = np.clip((train_x - mean) / scale, -12, 12)
    weights = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    positives = np.count_nonzero(train_y)
    negatives = np.count_nonzero(train_y == 0)
    if not positives or not negatives:
        raise ValueError("Both Fall and ADL required to train")
    balance = np.where(train_y == 1, .5 / positives, .5 / negatives)
    for _ in range(600):
        logits = np.clip(x @ weights + bias, -45, 45)
        probs = 1 / (1 + np.exp(-logits))
        err = (probs - train_y) * balance
        grad = x.T @ err + .02 * weights
        weights -= .12 * grad
        bias -= .12 * err.sum()
    def predict(matrix):
        logits = np.clip(((matrix - mean) / scale) @ weights + bias, -45, 45)
        return 1 / (1 + np.exp(-logits))
    val_probs = predict(val_x)
    best_score = -1.0
    best_threshold = None
    # Higher thresholds win balanced-accuracy ties, like the v1 baseline.
    for threshold in THRESHOLDS:
        predictions = val_probs >= threshold
        recall = float(np.mean(predictions[val_y == 1]))
        specificity = float(np.mean(~predictions[val_y == 0]))
        score = (recall + specificity) / 2
        if score > best_score + 1e-10:
            best_score, best_threshold = score, threshold
    return predict, best_threshold, best_score, len(mean) * 8 * 3 + 16


def compare_models(manifest: dict, bundle: dict) -> tuple[None, dict]:
    """Compare fixed candidates; select on val, score final test once.

    The v1 baseline is independently fitted with its own validation threshold.
    v2 is a *research candidate*, not proven to improve generalization.
    """
    np = _numpy()
    audit, windows = _validate_bundle(manifest, bundle)
    clips = manifest["clips"]
    train_clips = [c for c in clips if c["split"] == "train"]
    val_clips = [c for c in clips if c["split"] == "val"]
    if not train_clips or not val_clips:
        raise ValueError("Both training and validation subjects are required")
    # TEST features and labels are not accessed until selection has finished.
    y_train = np.asarray([c["expected_fall"] for c in train_clips], dtype=np.int64)
    y_val = np.asarray([c["expected_fall"] for c in val_clips], dtype=np.int64)
    if not np.any(y_val) or np.all(y_val):
        raise ValueError("Both labels must appear among validation subjects")
    x_train_v1 = np.stack([pool_temporal_window(windows[c["clip_id"]])
                           for c in train_clips])
    x_val_v1 = np.stack([pool_temporal_window(windows[c["clip_id"]])
                         for c in val_clips])
    predict_v1, threshold_v1, score_v1, model_bytes_v1 = _fit_candidate(
        x_train_v1, y_train, x_val_v1, y_val
    )
    x_train_v2 = np.stack([pooled_dynamics_v2(windows[c["clip_id"]])
                           for c in train_clips])
    x_val_v2 = np.stack([pooled_dynamics_v2(windows[c["clip_id"]])
                         for c in val_clips])
    predict_v2, threshold_v2, score_v2, model_bytes_v2 = _fit_candidate(
        x_train_v2, y_train, x_val_v2, y_val
    )
    baseline_val = _metrics(y_val, predict_v1(x_val_v1) >= threshold_v1)
    val_v2 = _metrics(y_val, predict_v2(x_val_v2) >= threshold_v2)
    # Disallow added complexity unless a *strict* validation gain is observed.
    selected_v2 = score_v2 > score_v1 + MIN_SELECTION_IMPROVEMENT
    selected_name = (ARCHITECTURE if selected_v2
                     else "pooled_temporal_logistic_v1_NOT_TCN_OR_GRU")

    test_clips = [c for c in clips if c["split"] == "test"]
    y_test = np.asarray([c["expected_fall"] for c in test_clips], dtype=np.int64)
    x_test_v1 = np.stack([pool_temporal_window(windows[c["clip_id"]])
                          for c in test_clips])
    x_test_v2 = np.stack([pooled_dynamics_v2(windows[c["clip_id"]])
                          for c in test_clips])
    test_v1 = _metrics(y_test, predict_v1(x_test_v1) >= threshold_v1)
    test_v2 = _metrics(y_test, predict_v2(x_test_v2) >= threshold_v2)
    heldout = test_v2 if selected_v2 else test_v1
    val = val_v2 if selected_v2 else baseline_val
    return None, {
        "stage": "publisher_or_synthetic_research_candidate_selection",
        "selected_model": selected_name,
        "model_selected_on": "validation subjects only; held-out TEST excluded",
        "selection_rule": "prefer v1 unless v2 balanced accuracy improves by >0.01",
        "split_audit": audit,
        "chosen_threshold": threshold_v2 if selected_v2 else threshold_v1,
        "model_parameters_bytes_approx": model_bytes_v2 if selected_v2
                                         else model_bytes_v1,
        "validation": val,
        "heldout_test": heldout,
        "candidate_comparison": {
            "baseline_v1": {"validation": baseline_val,
                            "heldout_test": test_v1,
                            "threshold": threshold_v1,
                            "approx_model_bytes": model_bytes_v1},
            "dynamics_v2": {"validation": val_v2,
                            "heldout_test": test_v2,
                            "threshold": threshold_v2,
                            "approx_model_bytes": model_bytes_v2},
        },
        "model_deployed": False,
        "automated_fall_alerting_authorized": False,
        "real_world_accuracy_established": False,
        "model_artifact_saved": False,
        "selection_bias_warning": (
            "Only a few validation subjects; comparing candidates can overfit "
            "validation. Test metrics are small, pose-filtered, staged-activity "
            "clips and cannot predict real-world event safety."
        ),
    }


def main(argv=None):
    parser = ArgumentParser(description="Local research candidate comparison; no alerts")
    parser.add_argument("--synthetic-demo", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--groups", type=Path)
    parser.add_argument("--segments", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if args.synthetic_demo:
        if any((args.root, args.groups, args.segments, args.model)):
            parser.error("Synthetic demo may not be combined with local media")
        from sentinel_edge.temporal_training import synthetic_demo
        report = compare_models(*synthetic_demo())[1]
        report["synthetic_data_only"] = True
    else:
        if not all((args.root, args.groups, args.segments, args.model)):
            parser.error("Require --root, --groups, --segments and --model")
        if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
            parser.error("Explicit publisher-label and pose-privacy acknowledgement required")
        # Real media and derived information must stay under the ignored private
        # root. Symlink resolves cannot jump outside. No file is overwritten.
        private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
        try:
            root = args.root.resolve(strict=True)
            groups_file = args.groups.resolve(strict=True)
            segments_file = args.segments.resolve(strict=True)
            if (not root.is_relative_to(private)
                    or not groups_file.is_relative_to(root)
                    or not segments_file.is_relative_to(root)
                    or groups_file.suffix != ".json"
                    or segments_file.suffix != ".json"):
                raise ValueError("Research input must stay in private dataset root")
            from sentinel_edge.caucafall_curator import publisher_label_pilot
            report = publisher_label_pilot(
                root, args.model, _read_bounded_json(groups_file),
                _read_bounded_json(segments_file), trainer=compare_models
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
            parser.error("Private research input rejected: " + str(exc))
        report["synthetic_data_only"] = False
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
