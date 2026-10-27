"""Fit and privately persist *real* publisher-labelled research V1 weights.

This does NOT connect to running fall alarms or authorize emergency dispatch.
The single standardized 30-dimensional V1 descriptor, logistic optimizer,
and validation threshold come from the existing frozen baseline function.
Raw windows, pose traces, frames and video MUST remain in memory.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from sentinel_edge.caucafall_curator import publisher_label_pilot
from sentinel_edge.temporal_training import (
    TemporalLinearModel, _numpy, _read_bounded_json, train_and_evaluate,
)
from sentinel_edge.window_export import _private_output_path

ARTIFACT_VERSION = 1
ARCHITECTURE = "pooled_temporal_logistic_v1_NOT_TCN_OR_GRU"
MODEL_FIELDS = frozenset({
    "version", "architecture", "dimension", "mean", "scale", "weights",
    "bias", "threshold", "source_manifest_sha256", "source_proposals_sha256",
    "source_dataset", "training_stage", "publisher_labels_only",
    "independent_human_label_review", "model_deployed",
    "automated_fall_alerting_authorized", "real_world_accuracy_established",
})
MAX_MODEL_JSON_BYTES = 10000


def checked_artifact(model: TemporalLinearModel, *, manifest_digest: str,
                     proposal_digest: str, dataset: str) -> dict:
    """Create only numeric & provenance metadata, never raw feature windows."""
    np = _numpy()
    arrays = [np.asarray(x, dtype=np.float64)
              for x in (model.mean, model.scale, model.weights)]
    if (any(a.shape != (30,) or not np.isfinite(a).all() for a in arrays)
            or np.any(arrays[1] <= 0)
            or any(not isinstance(x, str) or len(x) != 64 or
                   any(c not in "0123456789abcdef" for c in x)
                   for x in (manifest_digest, proposal_digest))
            or not isinstance(dataset, str) or not 1 <= len(dataset) <= 80
            or not isfinite(model.bias) or not isfinite(model.threshold)
            or not .05 <= model.threshold <= .95):
        raise ValueError("Invalid private research model values or provenance")
    return {
        "version": ARTIFACT_VERSION,
        "architecture": ARCHITECTURE,
        "dimension": 30,
        "mean": arrays[0].tolist(),
        "scale": arrays[1].tolist(),
        "weights": arrays[2].tolist(),
        "bias": float(model.bias),
        "threshold": float(model.threshold),
        "source_manifest_sha256": manifest_digest,
        "source_proposals_sha256": proposal_digest,
        "source_dataset": dataset,
        "training_stage": "publisher_label_real_pose_research_only",
        "publisher_labels_only": True,
        "independent_human_label_review": False,
        "model_deployed": False,
        "automated_fall_alerting_authorized": False,
        "real_world_accuracy_established": False,
    }


def read_private_artifact(path: Path) -> TemporalLinearModel:
    """Strict-load private JSON weights, without any eval/pickle/code execution."""
    path = path.resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_MODEL_JSON_BYTES:
        raise ValueError("Missing or oversized private research weights")
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    if not path.is_relative_to(private) or path.suffix != ".json":
        raise ValueError("Weights must remain within ignored data/private")
    item = json.loads(path.read_text("utf-8"))
    if not isinstance(item, dict) or set(item) != MODEL_FIELDS:
        raise ValueError("Unexpected private research weight schema")
    if (type(item["version"]) is not int or item["version"] != ARTIFACT_VERSION
            or item["architecture"] != ARCHITECTURE
            or type(item["dimension"]) is not int or item["dimension"] != 30
            or item["training_stage"] != "publisher_label_real_pose_research_only"
            or item["publisher_labels_only"] is not True
            or item["independent_human_label_review"] is not False
            or any(item[x] is not False for x in (
                "model_deployed", "automated_fall_alerting_authorized",
                "real_world_accuracy_established"
            ))):
        raise ValueError("Unsafe model origin, schema, or deployment claims")
    model = TemporalLinearModel(
        mean=item["mean"], scale=item["scale"], weights=item["weights"],
        bias=item["bias"], threshold=item["threshold"],
    )
    checked_artifact(model,
        manifest_digest=item["source_manifest_sha256"],
        proposal_digest=item["source_proposals_sha256"],
        dataset=item["source_dataset"],
    )
    np = _numpy()
    return TemporalLinearModel(
        mean=np.array(model.mean, dtype=np.float64),
        scale=np.array(model.scale, dtype=np.float64),
        weights=np.array(model.weights, dtype=np.float64),
        bias=float(model.bias), threshold=float(model.threshold),
    )


def fit_private_research_model(root: Path, pose_model: Path, groups_path: Path,
                               proposals_path: Path, output: Path, *,
                               collector=None) -> dict:
    """Local video => source-verified poses => fitted V1 => private numeric JSON.

    Existing held-out metrics are diagnostic only; do not use test labels to
    choose the threshold, feature extraction method or hyperparameters.
    """
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    root = root.resolve(strict=True)
    groups_path = groups_path.resolve(strict=True)
    proposals_path = proposals_path.resolve(strict=True)
    if (not root.is_dir() or not root.is_relative_to(private)
            or not groups_path.is_relative_to(root)
            or not proposals_path.is_relative_to(root)
            or groups_path.suffix != ".json"
            or proposals_path.suffix != ".json"):
        raise ValueError("Research dataset and manifests MUST stay in data/private")
    destination = _private_output_path(output)
    groups = _read_bounded_json(groups_path)
    proposals = _read_bounded_json(proposals_path)
    trained = None

    def _trainer(eligible_groups, windows):
        nonlocal trained
        trained, report = train_and_evaluate(eligible_groups, windows)
        return trained, report

    report = publisher_label_pilot(
        root, pose_model, groups, proposals,
        collector=collector, trainer=_trainer,
        dataset_origin=(groups["clips"][0]["dataset_id"] +
                        " publisher-labeled real staged videos; unreviewed"),
    )
    if trained is None:
        raise ValueError("No trained model returned")
    model_dict = checked_artifact(
        trained,
        manifest_digest=sha256(groups_path.read_bytes()).hexdigest(),
        proposal_digest=sha256(proposals_path.read_bytes()).hexdigest(),
        dataset=groups["clips"][0]["dataset_id"],
    )
    payload = json.dumps(model_dict, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_MODEL_JSON_BYTES:
        raise ValueError("Numerical model unexpectedly large")
    if (sha256(groups_path.read_bytes()).hexdigest()
            != model_dict["source_manifest_sha256"]
            or sha256(proposals_path.read_bytes()).hexdigest()
            != model_dict["source_proposals_sha256"]):
        raise ValueError("Source manifests drifted during training")
    # Never overwrite an existing private artifact; JSON is data, not pickle.
    with destination.open("x", encoding="utf8") as stream:
        stream.write(payload)
    try:
        reloaded = read_private_artifact(destination)
        np = _numpy()
        if (reloaded.model_bytes != trained.model_bytes
                or any(not np.array_equal(getattr(reloaded, attr),
                                          getattr(trained, attr))
                       for attr in ("mean", "scale", "weights"))
                or reloaded.bias != trained.bias
                or reloaded.threshold != trained.threshold):
            raise ValueError("Serialized model was not exactly preserved")
    except Exception:
        # Do not delete another process's artifact: if verification fails
        # the CLI reports failure and requires a human to inspect its path.
        raise
    report["research_weights_saved_privately"] = True
    report["research_weight_format"] = "strict_v1_json_float64_30d"
    report["model_size_bytes"] = trained.model_bytes
    report["reloaded_model_verified"] = True
    report["separate_fresh_test_cohort_required"] = True
    report["production_model_deployed"] = False
    report["output_location"] = "ignored data/private, path withheld from logs"
    return report


def main(argv=None):
    parser = ArgumentParser(description="Train and save PRIVATE research-only V1 weights")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--groups", required=True, type=Path)
    parser.add_argument("--proposals", required=True, type=Path)
    parser.add_argument("--pose-model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Explicit unreviewed publisher-label and pose-privacy acknowledgement required")
    try:
        result = fit_private_research_model(
            args.root, args.pose_model, args.groups, args.proposals, args.output
        )
    except (OSError, ValueError, RuntimeError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        parser.error("Private model training refused: " + str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
