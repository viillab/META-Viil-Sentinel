"""No third-party media is embedded in tests; byte integrity and safety only."""
from copy import deepcopy
from hashlib import sha1
from pathlib import Path

import pytest

from sentinel_edge import public_dataset_ingest as ingest
from sentinel_edge.split_audit import audit_subject_splits


def fake_catalog(monkeypatch):
    records = []
    buffers = {}
    for sub in range(1, 5):
        for cls in ("Fall", "ADL"):
            n = "01"
            data = (b"\x00\x00\x00\x18ftypisom" +
                    (str(sub) + cls).encode("ascii") * 10)
            url = ingest._source_url(sub, cls, n)
            buffers[url] = data
            records.append((sub, cls, n, len(data), ingest._github_blob_sha1(data)))
    monkeypatch.setattr(ingest, "CATALOG", tuple(records))
    monkeypatch.setattr(ingest, "_video_metadata", lambda path: (110, 25.0))
    return buffers


def test_real_git_sha_uses_blob_object_prefix():
    sample = b"hello\n"
    expected = sha1(b"blob 6\0hello\n").hexdigest()
    assert ingest._github_blob_sha1(sample) == expected


def test_synthetic_bytes_create_ignored_intended_manifest(monkeypatch, tmp_path):
    buffers = fake_catalog(monkeypatch)
    def fetcher(url, n):
        return buffers[url]
    result = ingest.download_subset(tmp_path / "private", fetcher=fetcher)
    assert result["clip_count"] == 8
    assert result["new_downloads"] == 8
    assert result["fall_clips"] == 4
    assert result["adl_clips"] == 4
    assert result["label_reviewed"] is False
    base = tmp_path / "private"
    import json
    groups = json.loads((base / "gmdcsa-research-groups-v2.json").read_text("utf8"))
    proposals = json.loads(
        (base / "gmdcsa-publisher-proposals-v1.json").read_text("utf8")
    )
    assert all(item["label_reviewed"] is False for item in proposals["segments"])
    assert {c["dataset_id"] for c in groups["clips"]} == {"gmdcsa24"}
    assert audit_subject_splits(groups)["test"]["subjects"] == 1
    replay = ingest.download_subset(base, fetcher=lambda *_: pytest.fail("redownload"))
    assert replay["verified_reused"] == 8
    assert replay["new_downloads"] == 0


def test_mutated_existing_media_refused(monkeypatch, tmp_path):
    buffers = fake_catalog(monkeypatch)
    root = tmp_path / "private"
    ingest.download_subset(root, fetcher=lambda url, n: buffers[url])
    path = ingest._local_path(root, 1, "Fall", "01")
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="Existing media modified"):
        ingest.download_subset(root, fetcher=lambda url, n: buffers[url])


def test_download_must_match_pinned_blob_before_file_is_written(monkeypatch, tmp_path):
    buffers = fake_catalog(monkeypatch)
    root = tmp_path / "private"
    with pytest.raises(ValueError, match="pinned integrity"):
        ingest.download_subset(
            root, fetcher=lambda url, n: buffers[url][:-1]
        )
    assert not list(root.rglob("*.mp4"))


def test_existing_dataset_manifest_drift_refused(monkeypatch, tmp_path):
    buffers = fake_catalog(monkeypatch)
    root = tmp_path / "private"
    ingest.download_subset(root, fetcher=lambda url, n: buffers[url])
    import json
    path = root / "gmdcsa-research-groups-v2.json"
    original = json.loads(path.read_text("utf8"))
    changed = deepcopy(original)
    changed["clips"][0]["expected_fall"] = not changed["clips"][0]["expected_fall"]
    path.write_text(json.dumps(changed), encoding="utf8")
    with pytest.raises(ValueError, match="already exists and differs"):
        ingest.download_subset(root, fetcher=lambda url, n: buffers[url])


def test_reject_non_private_cli_path_and_unacknowledged_training(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="ignored data/private"):
        ingest._verified_private_root(Path(tmp_path))
    with pytest.raises(SystemExit) as exc:
        ingest.main(["--mode", "pilot", "--root", str(tmp_path)])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        ingest.main([
            "--mode", "pilot", "--root", str(tmp_path),
            "--acknowledge-publisher-labels",
        ])
    assert exc.value.code == 2


def test_bad_media_container_rejected(monkeypatch, tmp_path):
    buffers = fake_catalog(monkeypatch)
    url = next(iter(buffers))
    altered = b"not-a-video" + buffers[url][11:]
    records = list(ingest.CATALOG)
    first = list(records[0])
    first[3] = len(altered)
    first[4] = ingest._github_blob_sha1(altered)
    records[0] = tuple(first)
    monkeypatch.setattr(ingest, "CATALOG", tuple(records))
    with pytest.raises(ValueError, match="video file header"):
        ingest.download_subset(
            tmp_path / "private",
            fetcher=lambda src, n: altered if src == url else buffers[src],
        )
