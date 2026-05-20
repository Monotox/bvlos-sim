"""Canonical result envelope for stochastic propagation CLI outputs."""

from pydantic import BaseModel, ConfigDict

from adapters.canonical_json import render_canonical_json
from adapters.envelope import DeterminismMetadata, ProvenanceInput
from adapters.io import InputDocument
from adapters.version import tool_version
from schemas.stochastic import StochasticPropagationResult

STOCHASTIC_ENVELOPE_SCHEMA_VERSION = "stochastic-envelope.v1"
STOCHASTIC_INPUT_SCHEMA_VERSION = "stochastic.v1"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class StochasticProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator_api: str
    inputs: dict[str, ProvenanceInput]


# ---------------------------------------------------------------------------
# Envelope model
# ---------------------------------------------------------------------------


class StochasticResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_version: str
    stochastic_schema_version: str
    propagation_id: str
    determinism_metadata: DeterminismMetadata
    provenance: StochasticProvenance
    result: StochasticPropagationResult


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _provenance_input(doc: InputDocument) -> ProvenanceInput:
    return ProvenanceInput(format=doc.format, sha256=doc.sha256)


def build_stochastic_envelope(
    *,
    result: StochasticPropagationResult,
    stochastic_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
) -> StochasticResultEnvelope:
    """Construct the canonical stochastic propagation envelope."""
    return StochasticResultEnvelope(
        schema_version=STOCHASTIC_ENVELOPE_SCHEMA_VERSION,
        tool_version=tool_version(),
        stochastic_schema_version=STOCHASTIC_INPUT_SCHEMA_VERSION,
        propagation_id=result.propagation_id,
        determinism_metadata=DeterminismMetadata(
            deterministic=False,
            randomness_used=True,
            external_network_access_used=False,
            canonical_json=True,
            canonical_json_sort_keys=True,
        ),
        provenance=StochasticProvenance(
            estimator_api="estimator.v1",
            inputs={
                "stochastic": _provenance_input(stochastic_document),
                "mission": _provenance_input(mission_document),
                "vehicle": _provenance_input(vehicle_document),
            },
        ),
        result=result,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_stochastic_envelope_json(envelope: StochasticResultEnvelope) -> str:
    """Render the stochastic envelope to canonical sorted JSON with a trailing newline."""
    return render_canonical_json(envelope.model_dump(mode="json"), ensure_ascii=False)
