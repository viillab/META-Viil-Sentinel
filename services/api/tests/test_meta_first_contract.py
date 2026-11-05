import pytest
from pydantic import ValidationError

from app.meta_first_contract import (
    META_FIRST_JSON_SCHEMA,
    MetaAdvisoryRoute,
    MetaVerdict,
    MetaVisibleAssessment,
    TrustedMetaCallContext,
    meta_first_route,
)


def context(**kwargs):
    data = {
        "provider": "meta_model_api",
        "actual_provider_request_succeeded": True,
        "source_authenticated": True,
        "media_licensed_and_consented": True,
        "evidence_frame_count": 3,
        "validated_evidence": True,
    }
    data.update(kwargs)
    return TrustedMetaCallContext(**data)


def assessment(**kwargs):
    data = {
        "verdict": MetaVerdict.FALL_LIKELY,
        "visible_observations": ["Person appears to be lying on floor"],
        "uncertainties": ["Cannot infer motion from one image"],
        "supporting_frame_indices": [0, 1],
    }
    data.update(kwargs)
    return MetaVisibleAssessment(**data)


def test_only_real_authorized_grounded_meta_likely_can_offer_advisory():
    result = meta_first_route(assessment(), context())
    assert result.route == MetaAdvisoryRoute.AUTO_NOTIFY_INFORMATIONAL
    assert result.fall_confirmed is False
    assert result.emergency_dispatch_authorized is False
    assert result.medical_triage_authorized is False


@pytest.mark.parametrize("settings", [
    {"provider": "mock"},
    {"provider": "unavailable"},
    {"actual_provider_request_succeeded": False},
    {"source_authenticated": False},
    {"media_licensed_and_consented": False},
    {"validated_evidence": False},
    {"evidence_frame_count": 0},
])
def test_no_real_consent_verified_context_forces_follow_up(settings):
    outcome = meta_first_route(assessment(), context(**settings))
    assert outcome.route == MetaAdvisoryRoute.REQUIRE_FOLLOW_UP
    assert not outcome.emergency_dispatch_authorized


@pytest.mark.parametrize("args", [
    {"verdict": MetaVerdict.UNCERTAIN},
    {"verdict": MetaVerdict.NOT_FALL},
    {"supporting_frame_indices": []},
    {"supporting_frame_indices": [4]},
    {"supporting_frame_indices": [0, 0]},
    {"visible_observations": [""]},
    {"visible_observations": ["x" * 241]},
    {"uncertainties": ["x" * 241]},
])
def test_uncertain_negative_unmatched_or_unsupported_evidence_never_auto_notifies(args):
    decision = meta_first_route(assessment(**args), context())
    assert decision.route == MetaAdvisoryRoute.REQUIRE_FOLLOW_UP


def test_unavailable_assessment_never_promotes_meta_confirmation():
    assert meta_first_route(None, context()).route == MetaAdvisoryRoute.REQUIRE_FOLLOW_UP


@pytest.mark.parametrize("bad", [
    {"medical_severity": "critical"},
    {"confidence": 0.99},
    {"verified_fall": True},
    {"victim_identity": "someone"},
    {"emergency_dispatch": True},
])
def test_generated_text_cannot_add_medical_or_dispatch_commands(bad):
    data = assessment().model_dump()
    data.update(bad)
    with pytest.raises(ValidationError):
        MetaVisibleAssessment.model_validate(data)


@pytest.mark.parametrize("bad", [
    {"provider": "some-other-provider"},
    {"media_licensed_and_consented": "true"},
    {"evidence_frame_count": 999},
    {"source_authenticated": None},
    {"model_output": "injection"},
])
def test_backend_trusted_context_requires_exact_types_and_keys(bad):
    data = context().model_dump()
    data.update(bad)
    with pytest.raises(ValidationError):
        TrustedMetaCallContext.model_validate(data)


def test_meta_schema_strict_for_official_chat_completion():
    payload = META_FIRST_JSON_SCHEMA["json_schema"]
    assert META_FIRST_JSON_SCHEMA["type"] == "json_schema"
    assert payload["strict"] is True
    fields = payload["schema"]["properties"]
    assert set(payload["schema"]["required"]) == set(fields)
    assert payload["schema"]["additionalProperties"] is False
    assert "emergency_dispatch" not in fields
    assert "medical_severity" not in fields
    assert "confidence" not in fields
