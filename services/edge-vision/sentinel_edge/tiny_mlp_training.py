"""Actual CPU-trained, light NumPy temporal MLP candidate; RESEARCH ONLY.

All fitting uses only declared TRAIN subject pose features, no raw videos
or poses are persisted. Model/threshold selection uses VAL people only.
Old TEST cohorts were already exposed by previous experiments and
therefore cannot establish fresh unbiased generalization. The deployed
fall heuristic and existing frozen V1 research artifact are unchanged.
"""
from argparse import ArgumentParser
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from sentinel_edge.caucafall_curator import publisher_label_pilot
from sentinel_edge.joint_dataset_training import (
    JOINT_NAME, SOURCE_FILENAMES, SOURCE_NAMES, _digest_sources,
    merge_eligible_sources,
)
from sentinel_edge.model_quality import _fit_candidate
from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import (
    _metrics, _numpy, _read_bounded_json, _validate_bundle,
    pool_temporal_window,
)
from sentinel_edge.window_export import _private_output_path

ARCH = "pooled_temporal_tiny_mlp_numpy_v1_NOT_TCN"
HIDDEN = 12
INPUTS = 30
STEPS = 800
LR = 0.15
L2 = 0.02
SEED = 407
VAL_MIN_IMPROVEMENT = 0.02
MAX_ARTIFACT_BYTES = 10_240


@dataclass
class TinyMLP:
    mean: object
    scale: object
    w1: object
    b1: object
    w2: object
    bias: float
    threshold: float

    def score(self, matrix):
        np = _numpy()
        x = np.asarray(matrix, dtype=np.float64)
        if x.shape[-1] != INPUTS or not np.isfinite(x).all():
            raise ValueError("Tiny MLP requires finite pooled 30-D inputs")
        norm = np.clip((x - self.mean) / self.scale, -12, 12)
        h = np.tanh(norm @ self.w1 + self.b1)
        logits = np.clip(h @ self.w2 + self.bias, -45, 45)
        return 1 / (1 + np.exp(-logits))

    @property
    def bytes(self):
        return sum(p.nbytes for p in (
            self.mean, self.scale, self.w1, self.b1, self.w2,
        )) + 16


def _label_matrix(manifest, features, split):
    np = _numpy()
    rows = [clip for clip in manifest["clips"] if clip["split"] == split]
    if not rows:
        raise ValueError("Missing independently declared data split")
    x = np.stack([pool_temporal_window(features[c["clip_id"]]) for c in rows])
    y = np.asarray([c["expected_fall"] for c in rows], dtype=np.int64)
    if not y.any() or y.all():
        raise ValueError("Each split requires Fall and ADL labels")
    return x, y, rows


def fit_tiny_mlp(x_train, y_train) -> TinyMLP:
    """Deterministic balanced full-batch gradient descent, TRAIN only."""
    np = _numpy()
    x = np.asarray(x_train, dtype=np.float64)
    y = np.asarray(y_train, dtype=np.int64)
    if (x.ndim != 2 or x.shape[1] != INPUTS or not 4 <= len(y) <= 10_000
            or len(x) != len(y) or not np.isfinite(x).all()
            or not np.isin(y, [0, 1]).all() or not y.any() or y.all()):
        raise ValueError("Finite balanced two-class TRAIN 30D data required")
    mean = x.mean(axis=0)
    sd = x.std(axis=0)
    scale = np.where(sd < 1e-6, 1.0, sd)
    z = np.clip((x - mean) / scale, -12, 12)
    rng = np.random.default_rng(SEED)
    w1 = rng.normal(0, .2, size=(INPUTS, HIDDEN)) / np.sqrt(INPUTS)
    b1 = np.zeros(HIDDEN, dtype=np.float64)
    w2 = rng.normal(0, .2, size=HIDDEN) / np.sqrt(HIDDEN)
    bias = 0.0
    npos, nneg = np.count_nonzero(y), np.count_nonzero(y == 0)
    balance = np.where(y == 1, .5 / npos, .5 / nneg)
    for _ in range(STEPS):
        hidden = np.tanh(z @ w1 + b1)
        p = 1 / (1 + np.exp(-np.clip(hidden @ w2 + bias, -45, 45)))
        err = (p - y) * balance
        gw2 = hidden.T @ err + L2 * w2
        gb2 = float(err.sum())
        dh = (err[:, None] * w2[None, :]) * (1 - hidden ** 2)
        gw1 = z.T @ dh + L2 * w1
        gb1 = dh.sum(axis=0)
        w1 -= LR * gw1
        b1 -= LR * gb1
        w2 -= LR * gw2
        bias -= LR * gb2
    model = TinyMLP(mean, scale, w1, b1, w2, float(bias), threshold=.5)
    if not all(np.isfinite(t).all() for t in (
        model.mean, model.scale, model.w1, model.b1, model.w2,
    )) or not np.isfinite(model.bias):
        raise ValueError("Tiny MLP produced nonfinite parameters")
    return model


def choose_validation_threshold(model, x_val, y_val) -> tuple[float, float]:
    """Select only using previously frozen VALIDATION subjects."""
    np = _numpy()
    y = np.asarray(y_val, dtype=np.int64)
    if (len(y) < 2 or not y.any() or y.all() or not np.isin(y, [0, 1]).all()):
        raise ValueError("Validation needs both source publisher action labels")
    scores = model.score(x_val)
    if scores.shape != y.shape or not np.isfinite(scores).all():
        raise ValueError("Validation scores/labels mismatch")
    best = (-1.0, .95)
    for th in (i / 100 for i in range(95, 4, -1)):
        preds = scores >= th
        bal = float((np.mean(preds[y == 1]) + np.mean(~preds[y == 0])) / 2)
        if bal > best[0] + 1e-12:
            best = (bal, float(th))
    return best[1], best[0]


def train_compare(manifest, bundle):
    """Fit both candidates and SELECT before ever looking at old TEST rows."""
    audit, windows = _validate_bundle(manifest, bundle)
    x_train, y_train, _ = _label_matrix(manifest, windows, "train")
    x_val, y_val, _ = _label_matrix(manifest, windows, "val")
    tiny = fit_tiny_mlp(x_train, y_train)
    t_tiny, score_tiny = choose_validation_threshold(tiny, x_val, y_val)
    tiny.threshold = t_tiny
    linear_predict, t_base, score_base, nbytes = _fit_candidate(
        x_train, y_train, x_val, y_val
    )
    selected = ("tiny_mlp" if score_tiny > score_base + VAL_MIN_IMPROVEMENT
                else "linear_v1")
    val_tiny = _metrics(y_val, tiny.score(x_val) >= t_tiny)
    val_linear = _metrics(y_val, linear_predict(x_val) >= t_base)
    # Previously exposed TEST features/labels loaded ONLY after above selection.
    x_test, y_test, test_rows = _label_matrix(manifest, windows, "test")
    old_tiny = _metrics(y_test, tiny.score(x_test) >= t_tiny)
    old_linear = _metrics(y_test, linear_predict(x_test) >= t_base)
    return tiny, {
        "architecture": ARCH,
        "research_only": True,
        "training_numpy_only": True,
        "model_weights_fitted_on": "declared TRAIN subjects only",
        "threshold_and_candidate_selected_on": "declared VAL subjects only",
        "selection_rule": "tiny MLP only if VAL balanced accuracy improves >0.02",
        "validation_used_for_selection": True,
        "selected_on_validation": selected,
        "tiny_validation_balanced_accuracy": round(score_tiny, 6),
        "linear_validation_balanced_accuracy": round(score_base, 6),
        "tiny_threshold_val": round(t_tiny, 4),
        "linear_threshold_val": round(t_base, 4),
        "tiny_val": val_tiny, "linear_val": val_linear,
        "tiny_old_exposed_test_diagnostic": old_tiny,
        "linear_old_exposed_test_diagnostic": old_linear,
        "former_test_clips": len(test_rows),
        "all_source_split_audit": audit,
        "tiny_parameters_bytes": tiny.bytes,
        "linear_parameters_bytes": nbytes,
        "tiny_num_parameters": int(
            tiny.mean.size + tiny.scale.size + tiny.w1.size + tiny.b1.size
            + tiny.w2.size + 2
        ),
        "real_world_generalization_proven": False,
        "source_actor_identities_independently_verified": False,
        "publisher_labels_human_reviewed": False,
        "old_test_previously_exposed": True,
        "fresh_subject_camera_test_required": True,
        "production_model_or_alerts_changed": False,
    }


def pack_numeric_model(model, *, source_digest: str) -> dict:
    """Strict bounded numeric-only private artifact (no clip/pose/actor info)."""
    np = _numpy()
    arrays = {name: getattr(model, name) for name in (
        "mean", "scale", "w1", "b1", "w2"
    )}
    for name, array in arrays.items():
        expected = ((INPUTS, HIDDEN) if name == "w1"
                    else (HIDDEN,) if name in ("b1", "w2") else (INPUTS,))
        if (np.asarray(array).shape != expected
                or not np.isfinite(array).all()):
            raise ValueError("Unexpected private MLP numeric dimensions")
    if np.any(model.scale <= 0) or not 0.05 <= model.threshold <= .95:
        raise ValueError("Invalid scaler/threshold")
    if len(source_digest) != 64 or any(ch not in "0123456789abcdef" for ch in source_digest):
        raise ValueError("Source SHA256 must be hex")
    payload = {
        "version": 1, "architecture": ARCH,
        "research_only": True,
        "source_sha256": source_digest,
        "feature_inputs": INPUTS, "hidden": HIDDEN,
        **{name: array.tolist() for name, array in arrays.items()},
        "bias": model.bias, "threshold": model.threshold,
    }
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ValueError("Research model exceeds 10 KiB")
    return payload


def check_numeric_artifact(payload: dict) -> TinyMLP:
    np = _numpy()
    if not isinstance(payload, dict) or set(payload) != {
        "version", "architecture", "research_only", "source_sha256",
        "feature_inputs", "hidden", "mean", "scale", "w1",
        "b1", "w2", "bias", "threshold",
    } or (type(payload["version"]) is not int or payload["version"] != 1
          or payload["architecture"] != ARCH
          or payload["research_only"] is not True
          or payload["feature_inputs"] != INPUTS or payload["hidden"] != HIDDEN):
        raise ValueError("Private research artifact schema mismatch")
    arrays = {}
    for name in ("mean", "scale", "w1", "b1", "w2"):
        obj = payload[name]
        if isinstance(obj, list):
            arr = np.asarray(obj, dtype=np.float64)
            arrays[name] = arr
        else:
            raise ValueError("Numeric MLP arrays only")
    bias, threshold = payload["bias"], payload["threshold"]
    if type(bias) not in (float, int) or type(threshold) not in (float, int):
        raise ValueError("Model bias and threshold must be finite numerics")
    model = TinyMLP(**arrays, bias=float(bias), threshold=float(threshold))
    pack_numeric_model(model, source_digest=payload["source_sha256"])
    return model


def read_numeric_model(path: Path) -> TinyMLP:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES:
        raise ValueError("Missing/oversized private NumPy artifact")
    return check_numeric_artifact(json.loads(path.read_text("utf8")))


def train_real_joint(roots: tuple[Path, Path], pose_task: Path, output: Path,
                     *, collector=None) -> dict:
    """Stream original real source videos, fit once, verify strict reload."""
    if len(roots) != len(SOURCE_NAMES):
        raise ValueError("Exactly two source roots required for joint training")
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    out = _private_output_path(output)
    sources = []
    parts = []
    for name, files, provided in zip(SOURCE_NAMES, SOURCE_FILENAMES, roots):
        root = provided.resolve(strict=True)
        if not root.is_dir() or not root.is_relative_to(private):
            raise ValueError("Training media must stay under ignored data/private")
        m, p = (root / files[0]).resolve(strict=True), (root / files[1]).resolve(strict=True)
        if not m.is_relative_to(root) or not p.is_relative_to(root):
            raise ValueError("Source manifest escapes private media root")
        manifest, proposals = _read_bounded_json(m), _read_bounded_json(p)
        if any(c["dataset_id"] != name for c in manifest["clips"]):
            raise ValueError("Swapped source dataset namespace")
        audit_subject_splits(manifest)
        digest = (sha256(m.read_bytes()).hexdigest(), sha256(p.read_bytes()).hexdigest())
        sources.append((m, p, digest))
        eligible, bundle = publisher_label_pilot(
            root, pose_task, manifest, proposals,
            collector=collector, collect_only=True,
        )
        parts.append((eligible, bundle))
    combined, windows = merge_eligible_sources(parts)
    fitted, report = train_compare(combined, windows)
    for m, p, (dm, dp) in sources:
        if sha256(m.read_bytes()).hexdigest() != dm or sha256(p.read_bytes()).hexdigest() != dp:
            raise ValueError("Source manifests changed during real training")
    src_sha = _digest_sources([
        {"dataset": name, "manifest_sha256": hashes[0], "proposals_sha256": hashes[1]}
        for name, (_, _, hashes) in zip(SOURCE_NAMES, sources)
    ])
    artifact = pack_numeric_model(fitted, source_digest=src_sha)
    serialized = json.dumps(artifact, allow_nan=False, separators=(",", ":"))
    with out.open("x", encoding="utf8") as f:
        f.write(serialized)
    loaded = read_numeric_model(out)
    np = _numpy()
    if not all(np.array_equal(getattr(fitted, name), getattr(loaded, name))
               for name in ("mean", "scale", "w1", "b1", "w2")) or (
                   fitted.bias != loaded.bias or fitted.threshold != loaded.threshold
               ):
        raise ValueError("Saved research MLP differs from exact in-memory fitted values")
    counts = Counter(c["split"] for c in combined["clips"])
    report.update({
        "source_names": list(SOURCE_NAMES),
        "joint_dataset_name": JOINT_NAME,
        "source_groups_sha256": src_sha,
        "usable_train_clips": counts["train"],
        "usable_val_clips": counts["val"],
        "usable_former_test_clips": counts["test"],
        "artifact_private_only": True,
        "artifact_numeric_only": True,
        "real_media_processed": True,
        "source_hashes_checked": True,
    })
    return report


def main(argv=None):
    parser = ArgumentParser(description="Tiny NumPy MLP trained offline, no live alerts")
    parser.add_argument("--cauca-root", type=Path, required=True)
    parser.add_argument("--gmdcsa-root", type=Path, required=True)
    parser.add_argument("--pose-task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_publisher_labels or not args.acknowledge_pose_privacy:
        parser.error("Research use of unreviewed publisher labels and sensitive poses must be acknowledged")
    try:
        report = train_real_joint((args.cauca_root, args.gmdcsa_root),
                                  args.pose_task, args.output)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.error("Private Tiny MLP training refused: " + str(exc))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
