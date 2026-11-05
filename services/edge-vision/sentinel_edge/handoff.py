"""Versioned, fail-closed Member1 -> Member2 fall-candidate handoff.

This module does not send network requests or make medical claims. It only
serializes limited detection metadata: no frame pixels, raw landmarks,
personal names, patient information, or unvetted evidence references.
"""
from dataclasses import asdict, dataclass
from math import isfinite
import re
from uuid import UUID

from sentinel_edge.contracts import FallCandidateEvent

SCHEMA_VERSION = "viil.edge.candidate.v1"
SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$", re.ASCII)
DETECTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$", re.ASCII)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
PROVENANCE_MODES = frozenset({
    "synthetic_pose_trace", "consented_staged_video", "authorized_local_camera",
})


@dataclass(frozen=True, slots=True)
class CandidateEnvelopeV1:
    schema_version: str
    event_type: str
    event_id: str
    source_id: str
    source_timestamp_ms: int
    timestamp_basis: str
    detector: str
    model_sha256: str | None
    input_provenance: str
    detector_score: float
    detector_score_type: str
    score_calibrated: bool
    confirmed_fall: bool
    human_review_required: bool
    medical_assessment_performed: bool
    simulated: bool
    evidence_refs: tuple[str, ...]
    delivery_mode: str

    def to_dict(self) -> dict:
        """JSON-compatible mapping with no extended/raw evidence."""
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


def to_envelope(
    event: FallCandidateEvent, *,
    input_provenance: str,
    model_sha256: str | None = None,
) -> CandidateEnvelopeV1:
    """Turn an unverified detector candidate into a strictly minimal contract.

    Provenance must be declared by the caller; this does not prove consent.
    The event UUID can be used as a deduplication key by a future authenticated
    ingestion service. Do not attempt to ingest this via the simulated API.
    """
    try:
        canonical_id = str(UUID(event.id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("event.id must be a UUID") from exc
    if canonical_id != event.id:
        raise ValueError("event.id must be a canonical UUID")
    if not SOURCE_ID_PATTERN.fullmatch(event.source_id):
        raise ValueError("source_id must be a pseudonymous slug (1..80 ASCII characters)")
    if not DETECTOR_PATTERN.fullmatch(event.detector):
        raise ValueError("detector identifier must be a bounded ASCII slug")
    if type(event.timestamp_ms) is not int or event.timestamp_ms < 0:
        raise ValueError("source timestamp must be a non-negative integer")
    if type(event.confidence) not in (float, int) or not isfinite(event.confidence):
        raise ValueError("detector score must be a finite number")
    if not 0 <= event.confidence <= 1:
        raise ValueError("detector score must be in range 0..1")
    if type(event.simulated) is not bool:
        raise ValueError("event.simulated must be a boolean")
    if event.evidence_refs:
        raise ValueError("raw or unreviewed evidence references are not allowed in v1")
    if input_provenance not in PROVENANCE_MODES:
        raise ValueError("invalid or undeclared input provenance")
    if model_sha256 is not None and (
        not isinstance(model_sha256, str)
        or SHA256_PATTERN.fullmatch(model_sha256) is None
    ):
        raise ValueError("model_sha256 must be a lowercase 64-character SHA256 digest")
    if input_provenance == "synthetic_pose_trace" and not event.simulated:
        raise ValueError("synthetic trace events must be explicitly simulated")
    if input_provenance != "synthetic_pose_trace" and event.simulated:
        raise ValueError("real-input provenance cannot be assigned to simulated events")

    return CandidateEnvelopeV1(
        schema_version=SCHEMA_VERSION,
        event_type="FALL_CANDIDATE",
        event_id=event.id,
        source_id=event.source_id,
        source_timestamp_ms=event.timestamp_ms,
        timestamp_basis="relative_to_source_start",
        detector=event.detector,
        model_sha256=model_sha256,
        input_provenance=input_provenance,
        detector_score=round(event.confidence, 3),
        detector_score_type="uncalibrated_heuristic",
        score_calibrated=False,
        confirmed_fall=False,
        human_review_required=True,
        medical_assessment_performed=False,
        simulated=event.simulated,
        evidence_refs=(),
        delivery_mode="local_stdout_only",
    )
