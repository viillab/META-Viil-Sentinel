"""Only synthetic bytes and protocol tests. Never include real human videos."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from sentinel_edge import assist_external as ext, window_export


def _fake_private(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    module = repo / "services" / "edge-vision" / "sentinel_edge" / "assist_external.py"
    monkeypatch.setattr(ext, "__file__", str(module))
    monkeypatch.setattr(window_export, "__file__", str(module.parent / "window_export.py"))
    private = repo / "data" / "private"
    private.mkdir(parents=True)
    return private


def _fake_catalog(monkeypatch):
    files = {}
    rows = []
    for group, name in (("adl", "09_mock_hard_adl.mp4"), ("fall", "01_mock_fall.mp4")):
        data = b"\x00\x00\x00\x18ftypisom" + (group.encode() * 90)
        url = f"{ext.SOURCE_URL}/videos/{group}/{name}"
        files[url] = data
        rows.append((group, name, len(data), ext._github_blob_sha1(data)))
    monkeypatch.setattr(ext, "CATALOG", tuple(rows))
    return files


def test_fixed_clip_inventory_covers_tough_adls_and_falls():
    assert ext.PINNED_COMMIT == "7a11c96b9a3576cef92f0795a19b3786c69a3335"
    assert ext.EXPECTED_MODEL_SHA256 == (
        "2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab"
    )
    assert sum(r[0] == "adl" for r in ext.CATALOG) == 8
    assert sum(r[0] == "fall" for r in ext.CATALOG) == 3
    assert sum(r[2] for r in ext.CATALOG) < ext.MAX_TOTAL_BYTES
    assert ext.source_url("adl", "15_stumbling.mp4").endswith(
        "/videos/adl/15_stumbling.mp4"
    )
    with pytest.raises(ValueError, match="frozen allowlist"):
        ext.source_url("fall", "../bad.mp4")


@pytest.mark.parametrize(("milliseconds", "expected"), [
    (900, [(0, 900)]),
    (5000, [(0, 5000)]),
    (8000, [(0, 8000)]),
    (15000, [(0, 8000), (8000, 15000)]),
    (25000, [(0, 8000), (8000, 16000), (16000, 24000),
             (24000, 25000)]),
    (89999, [(i * 8000, min((i + 1) * 8000, 89999)) for i in range(11)] +
            [(88000, 89999)]),
])
def test_predeclared_nonoverlap_window_ranges(milliseconds, expected):
    assert ext.windows_of(milliseconds) == expected


@pytest.mark.parametrize("ms", [0, -1, 899, 90001, True, 95000, "10000"])
def test_invalid_windows_fail_closed(ms):
    with pytest.raises(ValueError, match="Invalid external reference duration"):
        ext.windows_of(ms)


def test_private_verified_download_resume_and_manifest_never_claims_subjects(
    monkeypatch, tmp_path,
):
    private = _fake_private(monkeypatch, tmp_path)
    files = _fake_catalog(monkeypatch)
    root = private / "assist"
    def mock_get(url, size):
        return files[url]
    def metadata_reader(path):
        assert path.is_file()
        return 250, 25.0
    result = ext.verify_download(root, fetcher=mock_get, metadata_reader=metadata_reader)
    assert result["selected"] == 2
    assert result["new_downloads"] == 2
    assert result["subject_identity_verified"] is False
    assert result["manual_label_review"] is False
    manifest = json.loads((root / "assist-frozen-video-manifest-v1.json").read_text())
    assert manifest["subject_identities_for_reference_videos"] == "unknown"
    assert manifest["labels_independently_reviewed"] is False
    assert all(len(c["media_sha256"]) == 64 for c in manifest["clips"])
    again = ext.verify_download(
        root, fetcher=lambda *_: pytest.fail("download again"),
        metadata_reader=metadata_reader,
    )
    assert again["verified_reused"] == 2
    assert again["new_downloads"] == 0


def test_tampering_is_rejected_before_reuse(monkeypatch, tmp_path):
    private = _fake_private(monkeypatch, tmp_path)
    files = _fake_catalog(monkeypatch)
    root = private / "assist"
    def m(_):
        return 250, 25.0
    ext.verify_download(root, fetcher=lambda u, n: files[u], metadata_reader=m)
    source = root / "clips" / "adl" / "09_mock_hard_adl.mp4"
    source.write_bytes(source.read_bytes() + b"x")
    with pytest.raises(ValueError, match="footage modified"):
        ext.verify_download(root, fetcher=lambda u, n: files[u], metadata_reader=m)


def test_pinned_hash_prevents_untrusted_download(monkeypatch, tmp_path):
    private = _fake_private(monkeypatch, tmp_path)
    files = _fake_catalog(monkeypatch)
    root = private / "assist"
    with pytest.raises(ValueError, match="expected Git blob"):
        ext.verify_download(
            root, fetcher=lambda u, n: files[u] + b"corrupt",
            metadata_reader=lambda _: (250, 25.0),
        )
    assert not list(root.rglob("*.mp4"))


def test_private_path_and_required_acknowledgements(monkeypatch, tmp_path):
    _fake_private(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="data/private"):
        ext.private_root(tmp_path / "other")
    with pytest.raises(SystemExit) as e:
        ext.main(["--mode", "evaluate", "--root", "root"])
    assert e.value.code == 2


def test_summarizer_does_not_treat_partial_pose_falls_as_confirmed_misses():
    def row(group, score, selected, visible):
        return {
            "publisher_class": group,
            "any_window_fall_candidate": score,
            "selected_windows": selected,
            "pose_eligible_windows": visible,
            "pose_abstentions": selected - visible,
            "fully_pose_covered": visible == selected,
        }
    rows = [
        row("fall", False, 3, 2),
        row("fall", False, 3, 1),
        row("fall", False, 2, 2),
        row("adl", False, 2, 2),
        row("adl", True, 1, 1),
        row("adl", None, 1, 0),
    ]
    fall = ext.summarize_class(rows, "fall")
    assert fall["no_fall_candidate_videos"] == 3
    assert fall["fully_covered_no_candidate_videos"] == 1
    assert fall["partly_pose_abstained_videos"] == 2
    assert fall["windows_abstained"] == 3
    adl = ext.summarize_class(rows, "adl")
    assert adl["any_window_fall_candidate_videos"] == 1
    assert adl["video_pose_abstained"] == 1
    with pytest.raises(ValueError, match="Unexpected"):
        ext.summarize_class(rows, "other")


def test_frozen_model_digest_and_no_overwrite_checked_before_any_video(
    monkeypatch, tmp_path,
):
    private = _fake_private(monkeypatch, tmp_path)
    root = private / "dataset"
    root.mkdir()
    model = private / "joint.json"
    model.write_bytes(b"placeholder weights")
    result = private / "report.json"
    with pytest.raises(ValueError, match="Frozen model artifact SHA256"):
        ext.evaluate_external(root, Path("unused.task"), model, result)
    assert not result.exists()
    assert sha256(model.read_bytes()).hexdigest() != ext.EXPECTED_MODEL_SHA256
