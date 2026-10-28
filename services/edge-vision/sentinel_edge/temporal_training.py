"""Offline *research* supervised temporal logistic baseline (NumPy only).

No TCN/GRU is claimed. Train-only feature normalization, val-only decision
threshold and held-out declared-subject test. Does not wire to alerts, persist
the model, use a webcam, or make outbound requests.
"""
from argparse import ArgumentParser
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path

from sentinel_edge.motion_features import FEATURE_NAMES
from sentinel_edge.split_audit import audit_subject_splits

WINDOW_FRAMES = 30
TIME_BINS = 5
MAX_SAMPLES = 10000
MAX_JSON_BYTES = 15 * 1024 * 1024


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Install optional 'numpy' / .[training] for offline research") from exc
    return np


def _validate_bundle(manifest: dict, bundle: dict) -> tuple[dict, dict]:
    audit = audit_subject_splits(manifest)
    if not isinstance(bundle, dict) or set(bundle) != {"version", "feature_set", "windows"}:
        raise ValueError("Expected exact version=1 temporal feature bundle keys")
    if type(bundle["version"]) is not int or bundle["version"] != 1:
        raise ValueError("Temporal feature bundle version must be 1")
    if bundle["feature_set"] != "experimental_pose_motion_v1":
        raise ValueError("Unexpected feature_set; cannot silently change model inputs")
    windows = bundle["windows"]
    if not isinstance(windows, list) or not 1 <= len(windows) <= MAX_SAMPLES:
        raise ValueError("Must supply bounded feature windows")
    clips = manifest["clips"]
    if len(windows) != len(clips):
        raise ValueError("Every labeled clip requires exactly one feature window")
    expected = {item["clip_id"] for item in clips}
    found = {}
    for item in windows:
        if not isinstance(item, dict) or set(item) != {"clip_id", "features"}:
            raise ValueError("Feature entry must contain only clip_id and features")
        clip_id, features = item["clip_id"], item["features"]
        if clip_id not in expected or clip_id in found:
            raise ValueError("Feature IDs must be unique and match labeled clip IDs")
        if not isinstance(features, list) or len(features) != WINDOW_FRAMES:
            raise ValueError("Each clip must have exactly 30 temporal frames")
        count_valid = 0
        for row in features:
            if not isinstance(row, list) or len(row) != len(FEATURE_NAMES):
                raise ValueError("Each frame must contain six motion features")
            if any(type(v) not in (float, int) or not isfinite(v) for v in row):
                raise ValueError("Frame features must be finite real numbers")
            mask = row[-1]
            if mask not in (0, 1):
                raise ValueError("Observed-mask must be binary")
            if mask == 0 and any(v != 0 for v in row[:-1]):
                raise ValueError("Unobserved frames must have all-zero features")
            count_valid += bool(mask)
        if count_valid < WINDOW_FRAMES // 3:
            raise ValueError("Feature window has insufficient valid poses")
        found[clip_id] = features
    if set(found) != expected:
        raise ValueError("Feature and labeled clip ID sets differ")
    return audit, found


def pool_temporal_window(features: list[list[float]]):
    """Masked contiguous time-bin means; retains coarse temporal ordering."""
    np = _numpy()
    a = np.asarray(features, dtype=np.float64)
    if a.shape != (WINDOW_FRAMES, len(FEATURE_NAMES)):
        raise ValueError("Expected exactly 30 frames x 6 channels")
    if not np.isfinite(a).all() or not np.isin(a[:, -1], [0, 1]).all():
        raise ValueError("Only finite, binary-mask temporal features are accepted")
    rows = []
    for block in np.array_split(a, TIME_BINS):
        mask = block[:, -1]
        observed = np.maximum(mask.sum(), 1.0)
        # Missing frames contribute no false signal; valid fraction remains
        # a separate input dimension that models can learn to discount.
        rows.extend((block[:, :-1] * mask[:, None]).sum(axis=0) / observed)
        rows.append(mask.mean())
    return np.asarray(rows, dtype=np.float64)


def _normalize_for_fit_and_inference(matrix, mean, scale):
    """Train-only z-score with identical bounded inference for V1/V2.

    Accept one descriptor or a nonempty batch. Fail closed on nonfinite
    features/parameters so they never become a model score.
    """
    np = _numpy()
    x = np.asarray(matrix, dtype=np.float64)
    center = np.asarray(mean, dtype=np.float64)
    spread = np.asarray(scale, dtype=np.float64)
    if (center.ndim != 1 or center.size == 0
            or spread.shape != center.shape
            or not np.isfinite(center).all()
            or not np.isfinite(spread).all() or np.any(spread <= 0)):
        raise ValueError("Invalid model normalization parameters")
    if (x.ndim not in (1, 2) or x.size == 0
            or x.shape[-1] != center.size):
        raise ValueError("Invalid temporal feature shape")
    if not np.isfinite(x).all():
        raise ValueError("Temporal features must be finite")
    with np.errstate(over="ignore", invalid="ignore"):
        z = (x - center) / spread
    if not np.isfinite(z).all():
        raise ValueError("Normalized temporal features must be finite")
    return np.clip(z, -12, 12)


@dataclass
class TemporalLinearModel:
    """Small trained model only in memory; no automatic persistence."""
    mean: object
    scale: object
    weights: object
    bias: float
    threshold: float

    def predict_probability(self, matrix):
        np = _numpy()
        x = _normalize_for_fit_and_inference(matrix, self.mean, self.scale)
        z = x @ self.weights + self.bias
        return 1 / (1 + np.exp(-np.clip(z, -45, 45)))

    @property
    def model_bytes(self):
        return self.mean.nbytes + self.scale.nbytes + self.weights.nbytes + 16


def _matrix_and_labels(clips: list[dict], features: dict, split: str):
    np = _numpy()
    group = [c for c in clips if c["split"] == split]
    data = np.stack([pool_temporal_window(features[c["clip_id"]]) for c in group])
    labels = np.asarray([c["expected_fall"] for c in group], dtype=np.int64)
    if not labels.any() or labels.all():
        raise ValueError("Fall AND ADL required in every data split")
    return data, labels


def _metrics(labels, predictions) -> dict:
    np = _numpy()
    truth = np.asarray(labels, dtype=bool)
    pred = np.asarray(predictions, dtype=bool)
    tp = int(np.sum(truth & pred))
    fn = int(np.sum(truth & ~pred))
    fp = int(np.sum(~truth & pred))
    tn = int(np.sum(~truth & ~pred))
    return {
        "true_positive": tp, "false_negative": fn,
        "false_positive": fp, "true_negative": tn,
        "recall": round(tp / (tp + fn), 5) if tp + fn else None,
        "precision": round(tp / (tp + fp), 5) if tp + fp else None,
        "specificity": round(tn / (tn + fp), 5) if tn + fp else None,
        "false_positive_rate": round(fp / (tn + fp), 5) if tn + fp else None,
    }


def train_and_evaluate(manifest: dict, bundle: dict) -> tuple[TemporalLinearModel, dict]:
    """Preflight metadata, train, tune on val ONLY, evaluate untouched test."""
    np = _numpy()
    split_audit, windows = _validate_bundle(manifest, bundle)
    clips = manifest["clips"]
    train_x, train_y = _matrix_and_labels(clips, windows, "train")
    val_x, val_y = _matrix_and_labels(clips, windows, "val")
    # Note: held-out test features/labels are intentionally not even loaded
    # until training and threshold selection have completed.
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale = np.where(scale < 1e-6, 1.0, scale)
    x = _normalize_for_fit_and_inference(train_x, mean, scale)
    w = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    # Equal total class contribution; no test/val statistics involved.
    count_pos, count_neg = np.count_nonzero(train_y), np.count_nonzero(1 - train_y)
    weights = np.where(train_y == 1, .5 / count_pos, .5 / count_neg)
    for _ in range(600):
        logits = np.clip(x @ w + bias, -45, 45)
        p = 1 / (1 + np.exp(-logits))
        err = (p - train_y) * weights
        grad = x.T @ err + 0.02 * w
        w -= 0.12 * grad
        bias -= 0.12 * err.sum()
    model = TemporalLinearModel(mean=mean, scale=scale, weights=w, bias=bias,
                                threshold=.5)
    validation_probs = model.predict_probability(val_x)
    # Pick threshold maximizing balanced accuracy on validation participants.
    # Ties prefer the *higher* threshold, reducing false alarms.
    best = (-1.0, 0.5)
    for threshold in np.linspace(0.05, .95, 91)[::-1]:
        pred = validation_probs >= threshold
        hit = np.mean(pred[val_y == 1])
        spec = np.mean(~pred[val_y == 0])
        score = float((hit + spec) / 2)
        if score > best[0] + 1e-10:
            best = (score, float(threshold))
    model.threshold = best[1]
    test_x, test_y = _matrix_and_labels(clips, windows, "test")
    test_pred = model.predict_probability(test_x) >= model.threshold
    report = {
        "stage": "research_supervised_baseline",
        "architecture": "pooled_temporal_logistic_v1_NOT_TCN_OR_GRU",
        "real_world_accuracy_established": False,
        "inference_preprocessing": "train_only_zscore_clamp_minus12_plus12",
        "trained_on": "declared train subjects only",
        "threshold_selected_on": "declared validation subjects only",
        "test_subjects_excluded_from_fitting": True,
        "model_deployed": False,
        "automated_fall_alerting_authorized": False,
        "input_feature_channels": list(FEATURE_NAMES),
        "time_bins": TIME_BINS,
        "window_frames": WINDOW_FRAMES,
        "model_parameters_bytes_approx": model.model_bytes,
        "chosen_threshold": round(model.threshold, 3),
        "split_audit": split_audit,
        "validation": _metrics(val_y, validation_probs >= model.threshold),
        "heldout_test": _metrics(test_y, test_pred),
        "important": (
            "Metadata subject identities/licenses are not independently verified. "
            "Clip-level metrics cannot establish real-world false alarms per hour. "
            "No trained model is wired into production."
        ),
    }
    return model, report


def synthetic_demo(seed: int = 7) -> tuple[dict, dict]:
    """Invented numerical motion only, no humans or videos: smoke test."""
    np = _numpy()
    rng = np.random.default_rng(seed)
    entries = []
    windows = []
    for split, people in (("train", 8), ("val", 3), ("test", 3)):
        for person in range(people):
            subject = f"fictional-{split}-{person:02d}"
            for positive in (False, True):
                clip_id = f"{subject}-{'fall' if positive else 'adl'}"
                rows = []
                for t in range(WINDOW_FRAMES):
                    progress = t / (WINDOW_FRAMES - 1)
                    signal = 1.0 if positive and progress >= .55 else 0.0
                    # Not actual human pose, no physical movement validity.
                    rows.append([
                        float(.2 + .55 * signal + rng.normal(0, .04)),
                        float(.45 + .30 * signal + rng.normal(0, .03)),
                        float(.06 + .9 * signal + rng.normal(0, .05)),
                        float(.05 + .7 * signal + rng.normal(0, .05)),
                        .99, 1.0,
                    ])
                entries.append({
                    "clip_id": clip_id, "dataset_id": "fictional-only",
                    "subject_id": subject, "recording_id": clip_id,
                    "split": split, "expected_fall": positive,
                })
                windows.append({"clip_id": clip_id, "features": rows})
    return ({
        "version": 2,
        "permission_basis": "FICTIONAL numerical features; no humans, no external media",
        "clips": entries,
    }, {"version": 1, "feature_set": "experimental_pose_motion_v1",
        "windows": windows})


def _read_bounded_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Research JSON input missing or exceeds 15 MiB")
    return json.loads(path.read_text("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Research-only NumPy temporal baseline, NO alerts")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--synthetic-demo", action="store_true",
                        help="INVENTED features, not real accuracy validation")
    args = parser.parse_args(argv)
    if args.synthetic_demo:
        if args.manifest or args.features:
            parser.error("Synthetic demonstration cannot combine with real inputs")
        manifest, bundle = synthetic_demo()
    else:
        if not args.manifest or not args.features:
            parser.error("Both --manifest and --features are required for real data")
        try:
            manifest = _read_bounded_json(args.manifest)
            bundle = _read_bounded_json(args.features)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f"Untrusted research input rejected: {exc}")
    try:
        _, report = train_and_evaluate(manifest, bundle)
    except (ValueError, TypeError, RuntimeError, KeyError) as exc:
        parser.error(f"Training refused: {exc}")
    report["synthetic_data_only"] = args.synthetic_demo
    report["human_dataset_accuracy_claim"] = False
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
