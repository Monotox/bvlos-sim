"""Canonical result envelope for SORA pre-assessment CLI outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from adapters.canonical_json import render_canonical_json
from adapters.envelope import MISSION_SCHEMA_VERSION
from adapters.envelope import DeterminismMetadata, ProvenanceInput
from adapters.io import InputDocument
from adapters.version import tool_version
from schemas.sora import SORA_ASSESSMENT_SCHEMA_VERSION, SoraAssessment

SORA_ENVELOPE_SCHEMA_VERSION = "sora-envelope.v3"
VEHICLE_SCHEMA_VERSION = "vehicle.v4"


class SoraProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator_api: str
    inputs: dict[str, ProvenanceInput]


class SoraResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sora-envelope.v3"]
    tool_version: str
    sora_schema_version: Literal["sora-assessment.v3"]
    mission_schema_version: Literal["mission.v7"]
    vehicle_schema_version: Literal["vehicle.v4"]
    determinism_metadata: DeterminismMetadata
    provenance: SoraProvenance
    result: SoraAssessment


def _provenance_input(doc: InputDocument) -> ProvenanceInput:
    return ProvenanceInput(format=doc.format, sha256=doc.sha256)


def build_sora_envelope(
    *,
    result: SoraAssessment,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    population_document: InputDocument | None = None,
) -> SoraResultEnvelope:
    """Construct the canonical SORA assessment envelope."""
    inputs = {
        "mission": _provenance_input(mission_document),
        "vehicle": _provenance_input(vehicle_document),
    }
    if population_document is not None:
        inputs["population"] = _provenance_input(population_document)

    return SoraResultEnvelope(
        schema_version=SORA_ENVELOPE_SCHEMA_VERSION,
        tool_version=tool_version(),
        sora_schema_version=SORA_ASSESSMENT_SCHEMA_VERSION,
        mission_schema_version=MISSION_SCHEMA_VERSION,
        vehicle_schema_version=VEHICLE_SCHEMA_VERSION,
        determinism_metadata=DeterminismMetadata(),
        provenance=SoraProvenance(
            estimator_api="estimator.try_estimate_mission_distance_time",
            inputs=inputs,
        ),
        result=result,
    )


def render_sora_envelope_json(envelope: SoraResultEnvelope) -> str:
    """Render the SORA envelope to canonical sorted JSON with a trailing newline."""
    return render_canonical_json(envelope.model_dump(mode="json"), ensure_ascii=False)


__all__ = [
    "SORA_ENVELOPE_SCHEMA_VERSION",
    "SoraProvenance",
    "SoraResultEnvelope",
    "build_sora_envelope",
    "render_sora_envelope_json",
]
