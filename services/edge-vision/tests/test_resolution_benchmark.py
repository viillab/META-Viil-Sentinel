"""Optional resolution experiment must never change the default path."""
import json

import pytest

from sentinel_edge.video_benchmark import evaluate_video_manifest


def test_custom_mock_collector_cannot_pretend_to_support_resize(tmp_path):
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"synthetic stub not a real video")
    model = tmp_path / "fake.task"
    model.write_bytes(b"fake")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1, "permission_basis": "fake bytes with no people",
        "clips": [{"id": "fictional", "video": "sample.mp4", "expected_fall": False}]
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="real local video collector"):
        evaluate_video_manifest(manifest, model, max_inference_side=640,
                                collector=lambda *args, **kwargs: None)


def test_invalid_resolution_is_rejected_before_loading_media(tmp_path):
    with pytest.raises(ValueError, match="max_inference_side"):
        evaluate_video_manifest(tmp_path / "no_manifest.json",
                                tmp_path / "no_model.task", max_inference_side=257.5)
