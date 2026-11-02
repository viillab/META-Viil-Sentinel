"""Fail-closed, EVENT-BOUND synthetic pose evidence (not camera evidence).

The only input is an already validated Member 1 Edge candidate created from
one SHA256-pinned, fictional pose trace. The image is a schematic with four
torso points; no real human, face, video, patient data, or image upload occurs.

This module is an offline evidence *preparation* boundary, NOT proof of
ownership/consent for real media and NOT permission to call paid Meta AI.
"""
import base64
import hashlib
import hmac
import json
import struct
import zlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.candidate_ingest import parse_candidate
from app.edge_emitter_e2e import EXPECTED_TRACE_HASHES, SYNTHETIC_ROOT, SYNTHETIC_SOURCE
from app.meta_first_contract import META_FIRST_JSON_SCHEMA
from app.meta_live import MODEL, PNG_SIGNATURE

# Immutable, checked-in mathematical traces only. NOT user-selectable paths.
TRACE_NAME = "fall"
CANONICAL_CANDIDATE_FIXTURE_SHA256 = (
    "f2efcab929ba0f8eb08e967d8a12aabc9b50fd35c0f60b716de8cbab78489515"
)
RENDERER_VERSION = "viil.synthetic.pose-strip.v1"
SOURCE_TIMES = (0, 300, 850)
PANEL = 112
IMAGE_WIDTH, IMAGE_HEIGHT = PANEL * len(SOURCE_TIMES), PANEL
MAX_TRACE_BYTES = 65_536
MAX_IMAGE_BYTES = 128 * 1024
SHA_PATTERN = r"^[0-9a-f]{64}$"
POINTS = ("11", "12", "23", "24")


class EvidenceRejected(ValueError):
    """Untrusted, unbound, modified or non-synthetic evidence must not proceed."""


class SyntheticEvidenceManifest(BaseModel):
    """Exact privacy-safe metadata; all fields are required and frozen."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["viil.synthetic.evidence.v1"]
    source_id: Literal["synthetic-clip-01"]
    event_id: UUID
    source_timestamp_ms: Literal[850]
    candidate_sha256: str = Field(pattern=SHA_PATTERN)
    trace_sha256: str = Field(pattern=SHA_PATTERN)
    image_sha256: str = Field(pattern=SHA_PATTERN)
    frame_timestamps_ms: tuple[Literal[0], Literal[300], Literal[850]]
    image_mime: Literal["image/png"]
    renderer_version: Literal["viil.synthetic.pose-strip.v1"]
    image_origin: Literal["pinned_mathematical_pose_trace"]
    simulated: Literal[True]
    contains_real_person: Literal[False]
    consent_for_real_media_verified: Literal[False]
    external_upload_authorized: Literal[False]
    meta_inference_performed: Literal[False]
    permanent_storage_allowed: Literal[False]
    fall_confirmed: Literal[False]


@dataclass(frozen=True, slots=True)
class SyntheticEvidence:
    manifest: SyntheticEvidenceManifest
    png: bytes


def _read_known_trace() -> list[dict]:
    path = SYNTHETIC_ROOT / f"{TRACE_NAME}.jsonl"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TRACE_BYTES:
        raise EvidenceRejected("Pinned synthetic trace is unavailable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_TRACE_HASHES[TRACE_NAME]:
        raise EvidenceRejected("Pinned synthetic trace has changed")
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    except (UnicodeError, ValueError):
        raise EvidenceRejected("Pinned synthetic trace cannot be parsed") from None
    if len(rows) != 7 or [row.get("timestamp_ms") for row in rows] != [
        0, 100, 200, 300, 500, 700, 850,
    ]:
        raise EvidenceRejected("Pinned synthetic trace timeline changed")
    for row in rows:
        if set(row) != {"timestamp_ms", "landmarks"}:
            raise EvidenceRejected("Invalid synthetic frame fields")
        if not isinstance(row["landmarks"], dict) or set(row["landmarks"]) != set(POINTS):
            raise EvidenceRejected("Invalid synthetic landmark set")
        for point in row["landmarks"].values():
            if not isinstance(point, dict) or set(point) != {"x", "y", "visibility"}:
                raise EvidenceRejected("Invalid synthetic point fields")
            if any(type(value) not in (int, float) for value in point.values()):
                raise EvidenceRejected("Non-numeric synthetic point")
            if not 0 <= point["x"] <= 1 or not 0 <= point["y"] <= 1:
                raise EvidenceRejected("Synthetic point outside canvas")
            if not 0.9 <= point["visibility"] <= 1:
                raise EvidenceRejected("Synthetic point is occluded")
    return rows


def _verify_candidate(raw_candidate: bytes) -> UUID:
    candidate = parse_candidate(raw_candidate)
    if candidate.source_id != SYNTHETIC_SOURCE:
        raise EvidenceRejected("Candidate source is not the pinned synthetic source")
    example = SYNTHETIC_ROOT / "candidate_v1.example.json"
    if example.is_symlink() or not example.is_file() or example.stat().st_size > 4096:
        raise EvidenceRejected("Missing canonical Edge contract fixture")
    frozen = example.read_bytes()
    if hashlib.sha256(frozen).hexdigest() != CANONICAL_CANDIDATE_FIXTURE_SHA256:
        raise EvidenceRejected("Canonical candidate fixture has changed")
    try:
        canonical = json.loads(frozen)
        current = json.loads(raw_candidate)
    except (UnicodeError, ValueError):
        raise EvidenceRejected("Invalid canonical candidate") from None
    if not isinstance(canonical, dict) or not isinstance(current, dict):
        raise EvidenceRejected("Candidate is not a JSON object")
    # Only the real detector's new UUID is variable for this frozen fixture.
    canonical.pop("event_id", None)
    current.pop("event_id", None)
    if canonical != current:
        raise EvidenceRejected("Candidate is not tied to the pinned fall trace")
    if candidate.source_timestamp_ms != SOURCE_TIMES[-1] or not candidate.simulated:
        raise EvidenceRejected("Candidate timeline or provenance is not synthetic")
    return candidate.event_id


def _line(buf: bytearray, x0: int, y0: int, x1: int, y1: int, rgb: tuple[int, ...]) -> None:
    """Tiny bounded integer line rasterizer; four torso points only."""
    delta_x, delta_y = abs(x1 - x0), -abs(y1 - y0)
    step_x, step_y = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = delta_x + delta_y
    while True:
        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                x, y = x0 + offset_x, y0 + offset_y
                if 0 <= x < IMAGE_WIDTH and 0 <= y < IMAGE_HEIGHT:
                    index = (y * IMAGE_WIDTH + x) * 3
                    buf[index:index + 3] = bytes(rgb)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= delta_y:
            error += delta_y
            x0 += step_x
        if doubled <= delta_x:
            error += delta_x
            y0 += step_y


def _pose_png(frames: list[dict]) -> bytes:
    """Render exactly three static diagrams with stdlib; never read camera pixels."""
    canvas = bytearray(b"\xfa\xfa\xf6" * (IMAGE_WIDTH * IMAGE_HEIGHT))
    for panel_idx, frame in enumerate(frames):
        base = panel_idx * PANEL
        # Panel boundary and synthetic ground line.
        _line(canvas, base + 5, 100, base + PANEL - 5, 100, (180, 190, 190))
        if panel_idx:
            _line(canvas, base, 0, base, PANEL - 1, (180, 190, 190))
        vertices: dict[str, tuple[int, int]] = {}
        for point_id in POINTS:
            point = frame["landmarks"][point_id]
            vertices[point_id] = (
                base + 12 + round(point["x"] * (PANEL - 24)),
                8 + round(point["y"] * (PANEL - 20)),
            )
        for left, right in (("11", "12"), ("11", "23"), ("12", "24"), ("23", "24")):
            _line(canvas, *vertices[left], *vertices[right], (25, 83, 103))
        for coordinate in vertices.values():
            x, y = coordinate
            _line(canvas, x - 2, y, x + 2, y, (225, 90, 70))

    def chunk(kind: bytes, data: bytes) -> bytes:
        part = kind + data
        return (struct.pack(">I", len(data)) + part
                + struct.pack(">I", zlib.crc32(part) & 0xffffffff))

    stride = IMAGE_WIDTH * 3
    scan = b"".join(
        b"\x00" + canvas[y * stride:(y + 1) * stride]
        for y in range(IMAGE_HEIGHT)
    )
    png = (
        PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", IMAGE_WIDTH, IMAGE_HEIGHT, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scan, level=9))
        + chunk(b"IEND", b"")
    )
    if len(png) > MAX_IMAGE_BYTES:
        raise EvidenceRejected("Synthetic diagram exceeded size limit")
    return png


def build_synthetic_evidence(raw_candidate: bytes) -> SyntheticEvidence:
    """Render a deterministic diagram tied to validated candidate UUID/body/timestamp."""
    try:
        event_id = _verify_candidate(raw_candidate)
        trace = _read_known_trace()
    except (TypeError, ValueError, OSError):
        raise EvidenceRejected("Not a supported synthetic Edge candidate or trace") from None
    by_time = {row["timestamp_ms"]: row for row in trace}
    frames = [by_time[stamp] for stamp in SOURCE_TIMES]
    image = _pose_png(frames)
    manifest = SyntheticEvidenceManifest(
        schema_version="viil.synthetic.evidence.v1",
        source_id=SYNTHETIC_SOURCE,
        event_id=event_id,
        source_timestamp_ms=SOURCE_TIMES[-1],
        candidate_sha256=hashlib.sha256(raw_candidate).hexdigest(),
        trace_sha256=EXPECTED_TRACE_HASHES[TRACE_NAME],
        image_sha256=hashlib.sha256(image).hexdigest(),
        frame_timestamps_ms=SOURCE_TIMES,
        image_mime="image/png",
        renderer_version=RENDERER_VERSION,
        image_origin="pinned_mathematical_pose_trace",
        simulated=True,
        contains_real_person=False,
        consent_for_real_media_verified=False,
        external_upload_authorized=False,
        meta_inference_performed=False,
        permanent_storage_allowed=False,
        fall_confirmed=False,
    )
    return SyntheticEvidence(manifest=manifest, png=image)


def verify_synthetic_evidence(raw_candidate: bytes, evidence: SyntheticEvidence) -> None:
    """Reject any mismatched event/source/trace/image, even if PNG parses."""
    if not isinstance(evidence, SyntheticEvidence) or type(evidence.png) is not bytes:
        raise EvidenceRejected("Not a supported synthetic evidence bundle")
    if not PNG_SIGNATURE == evidence.png[:len(PNG_SIGNATURE)]:
        raise EvidenceRejected("Not a PNG")
    if not 48 <= len(evidence.png) <= MAX_IMAGE_BYTES:
        raise EvidenceRejected("Invalid synthetic evidence image size")
    expected = build_synthetic_evidence(raw_candidate)
    try:
        same_manifest = hmac.compare_digest(
            evidence.manifest.model_dump_json(),
            expected.manifest.model_dump_json(),
        )
        same_image = hmac.compare_digest(evidence.png, expected.png)
    except (AttributeError, TypeError, ValueError):
        raise EvidenceRejected("Malformed evidence manifest") from None
    if not same_manifest or not same_image:
        raise EvidenceRejected("Event-bound synthetic evidence mismatch")


def build_offline_pose_meta_request(raw_candidate: bytes, evidence: SyntheticEvidence) -> dict:
    """Prepare a would-be request; NO network, spend authorization or paid-call path.

    The real provider adapter STILL refuses this PNG because only the legacy
    uniform-color image is approved for live calls. The local 4-call Meta
    budget remains exhausted; this is not an invitation to bypass it.
    """
    verify_synthetic_evidence(raw_candidate, evidence)
    return {
        "model": MODEL,
        "reasoning_effort": "minimal",
        "max_completion_tokens": 1024,
        "messages": [
            {"role": "developer", "content": (
                "Contract test ONLY. This is a synthetic 3-panel stick-pose "
                "schematic generated from mathematical fixture coordinates, "
                "not video or photographs of real humans. Do not call it a "
                "verified fall or claim medical severity. Return uncertain "
                "with zero supporting_frame_indices."
            )},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    "Describe only the visible synthetic torso geometry. "
                    "There are three static schematic panels; never infer a "
                    "real person's fall. Strict JSON output."
                )},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(evidence.png).decode("ascii"),
                }},
            ]},
        ],
        "response_format": META_FIRST_JSON_SCHEMA,
    }
