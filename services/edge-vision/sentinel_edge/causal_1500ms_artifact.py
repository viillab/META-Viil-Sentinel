"""PRIVATE research-only portable 1500ms Linear model, NOT a safety classifier.

The original 8s V1/V2 research model artifacts are intentionally INCOMPATIBLE.
An explicit 1500ms contract is essential before a different member can load
real trained weights into an offline-only streaming shadow. All human-derived
data stays inside ignored data/private. Never silently publish this file.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import ClassVar

from sentinel_edge.private_model_training import (
    MODEL_FIELDS, checked_artifact,
)
from sentinel_edge.temporal_training import TemporalLinearModel, _numpy
from sentinel_edge.window_export import _private_output_path

ARTIFACT_FORMAT = "viil.edge.causal_1500ms.linear_research.v1"
ARCHITECTURE = "pooled_temporal_logistic_1500ms_only_NOT_GRU_OR_TCN"
CONTEXT_MS = 1500
SAMPLE_SLOTS = 30
HOP_MS = 250
MAX_JSON_BYTES = 12_000
FIELDS = MODEL_FIELDS | frozenset({
    "format", "temporal_context_ms", "sample_slots", "shadow_hop_ms",
    "research_only_usage",
})


@dataclass(frozen=True, slots=True)
class Causal1500msPredictor:
    """Typed adapter; will not fit into original pinned 8s loader."""

    linear: TemporalLinearModel
    temporal_context_ms: ClassVar[int] = CONTEXT_MS
    input_dimensions: ClassVar[int] = SAMPLE_SLOTS

    @property
    def threshold(self) -> float:
        return self.linear.threshold

    def predict_probability(self, vector):
        return self.linear.predict_probability(vector)


def checked_causal_artifact(model: TemporalLinearModel, *,
                            manifest_digest: str, proposal_digest: str,
                            dataset: str) -> dict:
    """Strict 30D numeric and source SHA provenance; no raw motion windows."""
    item = checked_artifact(
        model, manifest_digest=manifest_digest,
        proposal_digest=proposal_digest, dataset=dataset,
    )
    item.update({
        "format": ARTIFACT_FORMAT,
        "architecture": ARCHITECTURE,
        "temporal_context_ms": CONTEXT_MS,
        "sample_slots": SAMPLE_SLOTS,
        "shadow_hop_ms": HOP_MS,
        "research_only_usage": "private_offline_shadow_no_alert_authority",
    })
    if set(item) != FIELDS:
        raise ValueError("Unexpected short-window artifact field set")
    return item


def _unique_fields(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate private model JSON key")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError("Nonfinite JSON numeric constant is forbidden")


def read_causal_artifact(path: Path) -> Causal1500msPredictor:
    """Fail-closed read of only Git-ignored private research model JSON."""
    path = path.resolve(strict=True)
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    if (not path.is_relative_to(private) or path.suffix != ".json"
            or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_JSON_BYTES):
        raise ValueError("Short model must be bounded JSON in ignored data/private")
    item = json.loads(path.read_text("utf-8"),
                      object_pairs_hook=_unique_fields,
                      parse_constant=_reject_json_constant)
    if not isinstance(item, dict) or set(item) != FIELDS:
        raise ValueError("Unexpected private short-window artifact schema")
    if (item["format"] != ARTIFACT_FORMAT
            or item["architecture"] != ARCHITECTURE
            or type(item["version"]) is not int or item["version"] != 2
            or type(item["temporal_context_ms"]) is not int
            or item["temporal_context_ms"] != CONTEXT_MS
            or type(item["sample_slots"]) is not int
            or item["sample_slots"] != SAMPLE_SLOTS
            or type(item["shadow_hop_ms"]) is not int
            or item["shadow_hop_ms"] != HOP_MS
            or item["research_only_usage"] !=
            "private_offline_shadow_no_alert_authority"):
        raise ValueError("Incorrect 1500ms/30D research model contract")
    for name in ("model_deployed", "automated_fall_alerting_authorized",
                 "real_world_accuracy_established", "publisher_labels_only",
                 "independent_human_label_review"):
        if type(item[name]) is not bool:
            raise ValueError("Research model safety flags must be actual booleans")
    for name in ("mean", "scale", "weights"):
        values = item[name]
        if (not isinstance(values, list) or len(values) != SAMPLE_SLOTS
                or any(type(x) is not float for x in values)):
            raise ValueError("Short model weights must be exact float arrays")
    if type(item["bias"]) is not float or type(item["threshold"]) is not float:
        raise ValueError("Short model scalars must be floats")
    # The original numeric validator performs finite/positive scale/score,
    # source sha, flags and bounds checks; reconstruction then demands exact
    # equivalence of every serialized metadata flag and value.
    base = TemporalLinearModel(
        mean=item["mean"], scale=item["scale"], weights=item["weights"],
        bias=item["bias"], threshold=item["threshold"],
    )
    canonical = checked_causal_artifact(
        base,
        manifest_digest=item["source_manifest_sha256"],
        proposal_digest=item["source_proposals_sha256"],
        dataset=item["source_dataset"],
    )
    if item != canonical:
        raise ValueError("Private short model safety/provenance metadata modified")
    np = _numpy()
    return Causal1500msPredictor(TemporalLinearModel(
        mean=np.asarray(base.mean, dtype=np.float64),
        scale=np.asarray(base.scale, dtype=np.float64),
        weights=np.asarray(base.weights, dtype=np.float64),
        bias=float(base.bias), threshold=float(base.threshold),
    ))


def save_causal_artifact(model: TemporalLinearModel, destination: Path, *,
                         groups_path: Path, proposals_path: Path,
                         dataset: str) -> dict:
    """Exclusive-create private-only model then bitwise validate its readback."""
    destination = _private_output_path(destination)
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    paths = [groups_path.resolve(strict=True), proposals_path.resolve(strict=True)]
    if (any(not p.is_file() or not p.is_relative_to(private)
            or not 0 < p.stat().st_size <= 5_000_000 for p in paths)
            or destination.exists()):
        raise ValueError("Short model requires immutable private source files")
    payload = checked_causal_artifact(
        model, manifest_digest=sha256(paths[0].read_bytes()).hexdigest(),
        proposal_digest=sha256(paths[1].read_bytes()).hexdigest(),
        dataset=dataset,
    )
    blob = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    if len(blob.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Short model JSON unexpectedly large")
    # Source metadata must not drift during fit and serialization.
    for i, path in enumerate(paths):
        field = ("source_manifest_sha256", "source_proposals_sha256")[i]
        if sha256(path.read_bytes()).hexdigest() != payload[field]:
            raise ValueError("Short model training provenance changed")
    with destination.open("x", encoding="utf-8") as output:
        output.write(blob)
    loaded = read_causal_artifact(destination)
    np = _numpy()
    if (not all(np.array_equal(getattr(loaded.linear, name),
                               np.asarray(getattr(model, name), dtype=np.float64))
                for name in ("mean", "scale", "weights"))
            or loaded.threshold != model.threshold
            or loaded.linear.bias != model.bias):
        raise ValueError("Short model readback differs from trained values")
    return {
        "private_model_format": ARTIFACT_FORMAT,
        "artifact_size_bytes": len(blob.encode("utf-8")),
        "model_parameters_bytes_in_ram": loaded.linear.model_bytes,
        "readback_verified": True,
        "context_ms": CONTEXT_MS,
        "model_not_deployed": True,
        "alerts_unauthorized": True,
        "publisher_labels_unreviewed": True,
        "artifact_stored_only_in_gitignored_private": True,
    }
