"""Read-only, offline Member 1 model download integrity check.

Checks actual *pinned* private 1500ms linear model and official MediaPipe
Lite .task bytes before team use. No download, model fit, pose extraction,
network, file writes, incidents, notifications, or score export.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

from sentinel_edge.causal_1500ms_artifact import (
    ARTIFACT_FORMAT, Causal1500msPredictor, read_causal_artifact,
)
from sentinel_edge.causal_1500ms_shadow import Causal1500msModelShadow

# Hashes verified against actual original source files by the Member 1
# developer; neither weight, photo nor any dataset bytes are committed.
POSE_FILE_BYTES = 5_777_746
POSE_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
CLASSIFIER_FILE_BYTES = 2_654
CLASSIFIER_SHA256 = (
    "2faad54ea929f9f44ed8e1bfb733c59d907cb4516fe3979cc4b5f551697f3abb"
)
EXPECTED_MODEL_BYTES = 736
DEFAULT_CLASSIFIER = "caucafall-1500ms-linear-research-model-20261028.json"


def digest_and_size(path: Path, *, expected_size: int, expected_sha256: str) -> None:
    """Reject swapped/truncated files; stream chunks without extra data storage."""
    if not path.is_file() or path.stat().st_size != expected_size:
        raise ValueError("Model missing or unexpected file size")
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("Model SHA-256 mismatch: do not use tampered model")


def verify_handoff_bundle(*, classifier: Path, pose_task: Path) -> dict:
    """Strictly pin both model bytes, version and private file location."""
    root = Path(__file__).resolve().parents[3]
    private = (root / "data" / "private").resolve()
    classifier = classifier.resolve(strict=True)
    pose_task = pose_task.resolve(strict=True)
    if not classifier.is_relative_to(private) or classifier.suffix != ".json":
        raise ValueError("Research classifier must stay inside ignored data/private")
    if pose_task.suffix != ".task":
        raise ValueError("Official pose model must have .task extension")

    digest_and_size(
        classifier, expected_size=CLASSIFIER_FILE_BYTES,
        expected_sha256=CLASSIFIER_SHA256,
    )
    digest_and_size(
        pose_task, expected_size=POSE_FILE_BYTES, expected_sha256=POSE_SHA256,
    )
    fitted = read_causal_artifact(classifier)
    if (not isinstance(fitted, Causal1500msPredictor)
            or fitted.temporal_context_ms != 1500
            or fitted.input_dimensions != 30
            or fitted.linear.model_bytes != EXPECTED_MODEL_BYTES):
        raise ValueError("Research model fails pinned 1500ms contract")
    shadow = Causal1500msModelShadow(fitted)
    if shadow.summary()["scored_windows"] != 0:
        raise ValueError("A newly initialized shadow must have no scores")
    return {
        "validation": "passed_offline_sha256_and_model_contract",
        "pose_task_bytes": POSE_FILE_BYTES,
        "private_research_classifier_bytes": CLASSIFIER_FILE_BYTES,
        "linear_numeric_parameters_bytes": EXPECTED_MODEL_BYTES,
        "research_artifact_format": ARTIFACT_FORMAT,
        "context_ms": 1500,
        "shadow_hop_ms": 250,
        "model_files_checked": 2,
        "model_deployed": False,
        "live_fall_detection_authorized": False,
        "alert_or_network_action_performed": False,
        "no_weight_video_person_or_pose_data_exported": True,
        "not_an_accuracy_or_latency_benchmark": True,
    }


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = ArgumentParser(description="Verify the pinned offline Member1 model bundle")
    parser.add_argument(
        "--classifier", type=Path,
        default=root / "data" / "private" / DEFAULT_CLASSIFIER,
    )
    parser.add_argument(
        "--pose-task", type=Path,
        default=root / "models" / "pose_landmarker_lite.task",
    )
    args = parser.parse_args(argv)
    try:
        data = verify_handoff_bundle(classifier=args.classifier, pose_task=args.pose_task)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        parser.error("Member 1 handoff verification refused: " + str(exc))
    print(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
