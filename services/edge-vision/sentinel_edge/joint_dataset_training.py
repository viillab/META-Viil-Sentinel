"""Two-source Fall/ADL V1 research fit; publisher labels, no live safety use.

CAUCAFall and GMDCSA-24 have distinct declared subject namespaces. Source
manifests, each actual video's SHA256 and all cross-source identifiers are
revalidated before fitting. All sensitive motion windows live in memory.
"""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from sentinel_edge.caucafall_curator import publisher_label_pilot
from sentinel_edge.private_model_training import (
    MAX_MODEL_JSON_BYTES, checked_artifact, read_private_artifact,
)
from sentinel_edge.split_audit import audit_subject_splits
from sentinel_edge.temporal_training import (
    _metrics, _numpy, _read_bounded_json, pool_temporal_window,
    train_and_evaluate,
)
from sentinel_edge.window_export import _private_output_path

SOURCE_NAMES = ("caucafall-omnifall", "gmdcsa24")
SOURCE_FILENAMES = (
    ("caucafall-research-groups-v2.json", "caucafall-review-proposals-v1.json"),
    ("gmdcsa-research-groups-v2.json", "gmdcsa-publisher-proposals-v1.json"),
)
JOINT_NAME = "caucafall-gmdcsa24-joint"


def _digest_sources(records):
    """Unambiguous aggregate digest; preserve source name and ordering."""
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def merge_eligible_sources(parts: list[tuple[dict, dict]]) -> tuple[dict, dict]:
    """Prove cross-source subject/recording/media isolation again."""
    if len(parts) != len(SOURCE_NAMES):
        raise ValueError("Exactly two distinct source datasets are required")
    clips, windows = [], []
    seen = set()
    counts = Counter()
    for expected_name, (manifest, bundle) in zip(SOURCE_NAMES, parts):
        audit_subject_splits(manifest)
        if bundle.get("version") != 1 or bundle.get("feature_set") != (
            "experimental_pose_motion_v1"
        ):
            raise ValueError("Unexpected private motion format")
        if not all(c["dataset_id"] == expected_name for c in manifest["clips"]):
            raise ValueError("Dataset identity drift or swapped sources")
        if any(c["clip_id"] in seen for c in manifest["clips"]):
            raise ValueError("Duplicate clip ID across source datasets")
        seen.update(c["clip_id"] for c in manifest["clips"])
        clips.extend(manifest["clips"])
        windows.extend(bundle["windows"])
        counts[expected_name] += len(manifest["clips"])
    if any(counts[name] < 4 for name in SOURCE_NAMES):
        raise ValueError("Each dataset needs at least four pose-eligible clips")
    merged_manifest = {
        "version": 2,
        "permission_basis": (
            "Publisher MIT GMDCSA-24 and CC BY 4.0 CAUCAFall derived media; "
            "labels unreviewed; source-specific rights and consent not proven"
        ),
        "clips": clips,
    }
    merged_bundle = {
        "version": 1, "feature_set": "experimental_pose_motion_v1",
        "windows": windows,
    }
    # _validate_bundle in train_and_evaluate also checks every 30x6 frame.
    audit_subject_splits(merged_manifest)
    return merged_manifest, merged_bundle


def _source_diagnostic(eligible: dict, merged_windows: dict, model) -> dict:
    np = _numpy()
    clips = [c for c in eligible["clips"] if c["split"] == "test"]
    test_frames = {r["clip_id"]: r["features"] for r in merged_windows["windows"]}
    x = np.stack([pool_temporal_window(test_frames[c["clip_id"]]) for c in clips])
    labels = np.asarray([c["expected_fall"] for c in clips], dtype=bool)
    scores = model.predict_probability(x)
    return _metrics(labels, scores >= model.threshold)


def train_joint_model(source_roots: tuple[Path, Path], pose_model: Path,
                      output: Path, *, collector=None) -> dict:
    """Fit one genuine shared V1 using only two sources' TRAIN people.

    Selection is frozen to the existing 30-D NumPy baseline; Validation
    chooses its threshold. Former held-out test people are diagnostic only.
    """
    if len(source_roots) != 2:
        raise ValueError("Exactly two source roots required")
    private = (Path(__file__).resolve().parents[3] / "data" / "private").resolve()
    destination = _private_output_path(output)  # forbid overwrite and public
    if destination.exists():
        raise ValueError("Model output already exists; choose a new version")
    parts, source_manifests, source_proposals, original_totals = [], [], [], {}
    fingerprints = []
    for name, file_names, raw_root in zip(SOURCE_NAMES, SOURCE_FILENAMES, source_roots):
        root = raw_root.resolve(strict=True)
        if not root.is_dir() or not root.is_relative_to(private):
            raise ValueError("All source footage must be under ignored data/private")
        m = (root / file_names[0]).resolve(strict=True)
        p = (root / file_names[1]).resolve(strict=True)
        if not m.is_relative_to(root) or not p.is_relative_to(root):
            raise ValueError("Source manifest escapes private dataset root")
        groups, proposals = _read_bounded_json(m), _read_bounded_json(p)
        if not all(c["dataset_id"] == name for c in groups["clips"]):
            raise ValueError("Unexpected input dataset; source order is fixed")
        audit_subject_splits(groups)
        original_totals[name] = Counter(c["split"] for c in groups["clips"])
        source_manifests.append({"dataset": name, "sha256": sha256(m.read_bytes()).hexdigest()})
        source_proposals.append({"dataset": name, "sha256": sha256(p.read_bytes()).hexdigest()})
        fingerprints.append((m, p))
        # Same validated streaming pose extraction as original offline pilot.
        # Does NOT train a per-source model or score an old TEST here.
        eligible, bundle = publisher_label_pilot(
            root, pose_model, groups, proposals,
            collector=collector, collect_only=True,
        )
        parts.append((eligible, bundle))

    combined_manifest, combined_bundle = merge_eligible_sources(parts)
    model, report = train_and_evaluate(combined_manifest, combined_bundle)
    # Do not change the candidate, threshold, or weights using these results.
    per_dataset = {}
    for name, (eligible, _) in zip(SOURCE_NAMES, parts):
        count = Counter(c["split"] for c in eligible["clips"])
        per_dataset[name] = {
            "selected_clips": sum(original_totals[name].values()),
            "pose_eligible_clips": len(eligible["clips"]),
            "pose_abstained_clips": sum(original_totals[name].values()) -
                                  len(eligible["clips"]),
            "eligible_train": count["train"],
            "eligible_val": count["val"],
            "eligible_test": count["test"],
            "old_exposed_test_diagnostic": _source_diagnostic(
                eligible, combined_bundle, model
            ),
        }
    for (m, p), ms, ps in zip(fingerprints, source_manifests, source_proposals):
        if (sha256(m.read_bytes()).hexdigest() != ms["sha256"]
                or sha256(p.read_bytes()).hexdigest() != ps["sha256"]):
            raise ValueError("Publisher manifests drifted while fitting")
    artifact = checked_artifact(
        model, manifest_digest=_digest_sources(source_manifests),
        proposal_digest=_digest_sources(source_proposals),
        dataset=JOINT_NAME,
    )
    payload = json.dumps(artifact, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf8")) > MAX_MODEL_JSON_BYTES:
        raise ValueError("Joint model exceeds private numeric bounds")
    with destination.open("x", encoding="utf8") as stream:
        stream.write(payload)
    verified = read_private_artifact(destination)
    np = _numpy()
    if (any(not np.array_equal(getattr(model, key), getattr(verified, key))
            for key in ("mean", "scale", "weights"))
            or model.threshold != verified.threshold or model.bias != verified.bias):
        raise ValueError("Saved shared research artifact reload mismatched")
    report.update({
        "dataset_origin": "Publisher-labeled CAUCAFall plus GMDCSA-24 research videos",
        "source_diagnostics": per_dataset,
        "fit_datasets": list(SOURCE_NAMES),
        "all_source_ids_audited_together": True,
        "research_weights_saved_privately": True,
        "reloaded_model_verified": True,
        "publisher_labels_only": True,
        "independent_human_label_review": False,
        "old_heldout_test_exposed_before_this_work": True,
        "old_test_must_not_influence_promotion_or_threshold": True,
        "fresh_untouched_test_required": True,
        "cross_dataset_generalization_proven": False,
        "production_alerts_enabled": False,
        "real_world_accuracy_established": False,
        "artifact_path_displayed": False,
    })
    return report


def main(argv=None) -> int:
    parser = ArgumentParser(description="Research-only joint V1 public video fit")
    parser.add_argument("--cauca-root", type=Path, required=True)
    parser.add_argument("--gmdcsa-root", type=Path, required=True)
    parser.add_argument("--pose-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-publisher-labels", action="store_true")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.acknowledge_publisher_labels and args.acknowledge_pose_privacy):
        parser.error("Unreviewed source labels and sensitive pose privacy must be acknowledged")
    try:
        report = train_joint_model(
            (args.cauca_root, args.gmdcsa_root), args.pose_model, args.output
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        parser.error("Joint research model refused: " + str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
