"""Canonical result envelope for Monte Carlo uncertainty CLI outputs."""

import json
import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from adapters.envelope import DeterminismMetadata, ProvenanceInput
from adapters.io import InputDocument
from estimator.core.uncertainty import MonteCarloResult

UNCERTAINTY_REPORT_SCHEMA_VERSION = "uncertainty-report.v1"
UNCERTAINTY_INPUT_SCHEMA_VERSION = "uncertainty.v1"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class UncertaintyProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator_api: str
    inputs: dict[str, ProvenanceInput]


# ---------------------------------------------------------------------------
# Envelope model
# ---------------------------------------------------------------------------


class UncertaintyResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_version: str
    uncertainty_schema_version: str
    uncertainty_id: str
    determinism_metadata: DeterminismMetadata
    provenance: UncertaintyProvenance
    result: MonteCarloResult


# ---------------------------------------------------------------------------
# Tool version
# ---------------------------------------------------------------------------


def _tool_version() -> str:
    try:
        return importlib_metadata.version("bvlos-sim")
    except importlib_metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _provenance_input(doc: InputDocument) -> ProvenanceInput:
    return ProvenanceInput(format=doc.format, sha256=doc.sha256)


def build_uncertainty_envelope(
    *,
    result: MonteCarloResult,
    uncertainty_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
) -> UncertaintyResultEnvelope:
    """Construct the canonical uncertainty report envelope."""
    return UncertaintyResultEnvelope(
        schema_version=UNCERTAINTY_REPORT_SCHEMA_VERSION,
        tool_version=_tool_version(),
        uncertainty_schema_version=UNCERTAINTY_INPUT_SCHEMA_VERSION,
        uncertainty_id=result.uncertainty_id,
        determinism_metadata=DeterminismMetadata(
            deterministic=False,
            randomness_used=True,
            external_network_access_used=False,
            canonical_json=True,
            canonical_json_sort_keys=True,
        ),
        provenance=UncertaintyProvenance(
            estimator_api="estimator.v1",
            inputs={
                "uncertainty": _provenance_input(uncertainty_document),
                "mission": _provenance_input(mission_document),
                "vehicle": _provenance_input(vehicle_document),
            },
        ),
        result=result,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_uncertainty_envelope_json(envelope: UncertaintyResultEnvelope) -> str:
    """Render the uncertainty envelope to canonical sorted JSON with a trailing newline."""
    return json.dumps(
        envelope.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
