"""Multimodal AI boundary. Mock results are labelled and never presented as live inference.

A genuine Meta adapter should be implemented after validating the latest official
Model API image input/structured-output contract and model access, using consented
keyframes only. Never upload patient imagery under research/demo free credits.
"""
from typing import Protocol

from app.models import EvidenceObservation


class IncidentInterpreter(Protocol):
    async def interpret(self, *, source_id: str, confidence: float) -> EvidenceObservation: ...


class MockIncidentInterpreter:
    async def interpret(self, *, source_id: str, confidence: float) -> EvidenceObservation:
        del source_id, confidence
        return EvidenceObservation(
            posture="Unknown — mock demonstration, no real frames analyzed",
            surroundings="Staged event metadata only",
            uncertainty=[
                "No image, pose, or clinical information was analyzed",
                "Mock report must never be described as Muse Spark output",
            ],
            evidence_refs=[],
            generated_by="mock",
        )


def provider_for(provider_name: str) -> IncidentInterpreter:
    if provider_name != "mock":
        raise RuntimeError(
            "Live Meta calls have not been configured or verified. "
            "Set META_PROVIDER=mock for this foundation."
        )
    return MockIncidentInterpreter()
