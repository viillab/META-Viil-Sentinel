"""Strict future Meta-first assessment proposal; NO live provider wiring.

The output of a multimodal model is untrusted. Meta may automate first-pass
visual observations and low-impact caregiver *advisory* routing only after
authorized real evidence and validated integration. It is not medical triage,
an established fall classifier or a rescue dispatcher.
"""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetaVerdict(StrEnum):
    FALL_LIKELY = "fall_likely"
    NOT_FALL = "not_fall"
    UNCERTAIN = "uncertain"


class MetaVisibleAssessment(BaseModel):
    """Only model-generated visible description; no permissions supplied by AI."""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: MetaVerdict
    visible_observations: list[str] = Field(min_length=1, max_length=4)
    uncertainties: list[str] = Field(max_length=4)
    supporting_frame_indices: list[int] = Field(max_length=5)
    # No ungrounded probability, medical diagnosis, rescue action,
    # identity or medical severity fields are permitted.


class TrustedMetaCallContext(BaseModel):
    """Verified by backend; NEVER copied from generated model JSON."""

    model_config = ConfigDict(extra="forbid", strict=True)

    provider: Literal["meta_model_api", "mock", "unavailable"]
    actual_provider_request_succeeded: bool
    source_authenticated: bool
    media_licensed_and_consented: bool
    evidence_frame_count: int = Field(ge=0, le=5)
    # Real adapter can only assert validated_evidence when its MIME,
    # ownership, size, privacy/cost guards, and source hashes pass.
    validated_evidence: bool


class MetaAdvisoryRoute(StrEnum):
    AUTO_NOTIFY_INFORMATIONAL = "auto_notify_informational"
    REQUIRE_FOLLOW_UP = "require_follow_up"


class MetaRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    route: MetaAdvisoryRoute
    reason: str
    # An advisory describes a visually suspicious event, NOT a confirmed
    # fall, diagnosis, verified incident or emergency-service request.
    fall_confirmed: Literal[False] = False
    emergency_dispatch_authorized: Literal[False] = False
    medical_triage_authorized: Literal[False] = False


def meta_first_route(
    assessment: MetaVisibleAssessment | None,
    trusted: TrustedMetaCallContext,
) -> MetaRouteDecision:
    """Fail-safe Meta-first suggestion, NEVER changes incident state.

    This function has no I/O and is NOT currently invoked by the backend.
    Member 2 needs genuine Meta evidence, provider auth, cost controls, and
    independent validation before enabling optional in-app advisories.
    """

    def follow_up(reason: str) -> MetaRouteDecision:
        return MetaRouteDecision(
            route=MetaAdvisoryRoute.REQUIRE_FOLLOW_UP, reason=reason
        )

    if (trusted.provider != "meta_model_api"
            or not trusted.actual_provider_request_succeeded):
        return follow_up("not_actual_verified_meta_inference")
    if (not trusted.source_authenticated
            or not trusted.media_licensed_and_consented
            or not trusted.validated_evidence
            or trusted.evidence_frame_count == 0):
        return follow_up("missing_authorized_visual_evidence")
    if assessment is None:
        return follow_up("meta_result_unavailable_or_invalid")
    if not all(isinstance(i, str) and 0 < len(i.strip()) <= 240
               for i in assessment.visible_observations):
        return follow_up("invalid_visible_observation")
    if not all(isinstance(s, str) and len(s) <= 240
               for s in assessment.uncertainties):
        return follow_up("invalid_uncertainty_text")
    indices = assessment.supporting_frame_indices
    if any(type(i) is not int or not 0 <= i < trusted.evidence_frame_count
           for i in indices):
        return follow_up("unsupported_evidence_frame_index")
    if len(set(indices)) != len(indices):
        return follow_up("duplicated_evidence_frame")
    if assessment.verdict == MetaVerdict.FALL_LIKELY and indices:
        return MetaRouteDecision(
            route=MetaAdvisoryRoute.AUTO_NOTIFY_INFORMATIONAL,
            reason="visible_candidate_with_real_authorized_meta_evidence",
        )
    return follow_up("no_grounded_fall_likelihood_or_ambiguous_evidence")


# Corresponds to Meta's official structured output response_format.json_schema
# only. This schema does NOT authorize calls or dispatch.
META_FIRST_JSON_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "viil_meta_visible_assessment_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["fall_likely", "not_fall", "uncertain"],
                },
                "visible_observations": {
                    "type": "array", "items": {"type": "string"},
                },
                "uncertainties": {
                    "type": "array", "items": {"type": "string"},
                },
                "supporting_frame_indices": {
                    "type": "array", "items": {"type": "integer"},
                },
            },
            "required": [
                "verdict", "visible_observations",
                "uncertainties", "supporting_frame_indices",
            ],
            "additionalProperties": False,
        },
    },
}
