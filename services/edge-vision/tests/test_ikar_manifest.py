"""Tests for license-aware manifest selection. Fake empty local files only."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest


def get_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_ikar_manifest.py"
    spec = spec_from_file_location("prepare_ikar_manifest", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def generate_dataset(root, count=2):
    for category in ("blackouts", "faintings", "slips", "trips"):
        folder = root / category / "videos"
        folder.mkdir(parents=True)
        for index in range(count):
            (folder / f"{category}_{index}.mp4").write_bytes(b"fake")


def test_manifest_has_four_labels_and_no_fabricated_onsets(tmp_path):
    script = get_script()
    generate_dataset(tmp_path)
    manifest = script.build_manifest(tmp_path)
    assert len(manifest["clips"]) == 8
    assert all(clip["expected_fall"] is True for clip in manifest["clips"])
    assert all("onset_ms" not in clip for clip in manifest["clips"])
    assert len({clip["id"] for clip in manifest["clips"]}) == 8
    assert script.DOI in manifest["permission_basis"]
    assert "CC BY" in manifest["permission_basis"]
    assert all(".." not in clip["video"] for clip in manifest["clips"])


def test_reject_missing_category_and_unavailable_samples(tmp_path):
    script = get_script()
    with pytest.raises(ValueError, match="Expected"):
        script.build_manifest(tmp_path)
    generate_dataset(tmp_path, count=1)
    with pytest.raises(ValueError, match="requires 2"):
        script.build_manifest(tmp_path)


def test_requires_operator_attribution_and_does_not_overwrite(tmp_path):
    script = get_script()
    generate_dataset(tmp_path)
    with pytest.raises(SystemExit):
        script.main(["--dataset-root", str(tmp_path)])
    assert script.main(["--dataset-root", str(tmp_path), "--acknowledge-cc-by"]) == 0
    content = json.loads((tmp_path / "ikar_sample_manifest.json").read_text("utf-8"))
    assert content["permission_basis"].startswith("IKAR")
    with pytest.raises(SystemExit):
        script.main(["--dataset-root", str(tmp_path), "--acknowledge-cc-by"])
