"""Canonical result envelope for scenario runner CLI outputs."""

from pydantic import BaseModel, ConfigDict

from adapters.canonical_json import render_canonical_json
from adapters.envelope import DeterminismMetadata, ProvenanceInput
from adapters.version import tool_version
from adapters.io import InputDocument, InputLoadError
from estimator.core.results import MissionEstimate
from estimator.core.scenario import (
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
    ScenarioStatus,
    TimelinePoint,
)

SCENARIO_REPORT_SCHEMA_VERSION = "scenario-report.v2"
SCENARIO_INPUT_SCHEMA_VERSION = "scenario.v1"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class ScenarioProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_runner_api: str
    inputs: dict[str, ProvenanceInput]


# ---------------------------------------------------------------------------
# Envelope model
# ---------------------------------------------------------------------------


class ScenarioResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_version: str
    scenario_schema_version: str
    scenario_id: str
    status: ScenarioStatus
    determinism_metadata: DeterminismMetadata
    provenance: ScenarioProvenance
    timeline: list[TimelinePoint]
    event_outcomes: list[ScenarioEventOutcome]
    assertion_results: list[ScenarioAssertionResult]
    estimate: MissionEstimate | None = None


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------


def _provenance_input(document: InputDocument) -> ProvenanceInput:
    return ProvenanceInput(format=document.format, sha256=document.sha256)


def _build_provenance(
    scenario_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    *,
    geofence_document: InputDocument | None = None,
    landing_zone_document: InputDocument | None = None,
    terrain_document: InputDocument | None = None,
    population_document: InputDocument | None = None,
    wind_grid_document: InputDocument | None = None,
) -> ScenarioProvenance:
    inputs = {
        "scenario": _provenance_input(scenario_document),
        "mission": _provenance_input(mission_document),
        "vehicle": _provenance_input(vehicle_document),
    }
    optional_inputs = {
        "geofences": geofence_document,
        "landing_zones": landing_zone_document,
        "terrain": terrain_document,
        "population": population_document,
        "wind_grid": wind_grid_document,
    }
    inputs.update(
        {
            name: _provenance_input(document)
            for name, document in optional_inputs.items()
            if document is not None
        }
    )
    return ScenarioProvenance(
        scenario_runner_api="scenario_runner.run_scenario",
        inputs=inputs,
    )


def _empty_provenance() -> ScenarioProvenance:
    return ScenarioProvenance(
        scenario_runner_api="scenario_runner.run_scenario",
        inputs={},
    )


def _partial_provenance(
    known: dict[str, InputDocument | None],
) -> ScenarioProvenance:
    return ScenarioProvenance(
        scenario_runner_api="scenario_runner.run_scenario",
        inputs={
            name: _provenance_input(doc)
            for name, doc in known.items()
            if doc is not None
        },
    )


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------


def _base_envelope(
    *,
    scenario_id: str,
    status: ScenarioStatus,
    provenance: ScenarioProvenance,
    result: ScenarioResult | None,
) -> ScenarioResultEnvelope:
    return ScenarioResultEnvelope(
        schema_version=SCENARIO_REPORT_SCHEMA_VERSION,
        tool_version=tool_version(),
        scenario_schema_version=SCENARIO_INPUT_SCHEMA_VERSION,
        scenario_id=scenario_id,
        status=status,
        determinism_metadata=DeterminismMetadata(),
        provenance=provenance,
        timeline=result.timeline if result is not None else [],
        event_outcomes=result.event_outcomes if result is not None else [],
        assertion_results=result.assertion_results if result is not None else [],
        estimate=result.estimate if result is not None else None,
    )


def build_scenario_envelope(
    *,
    result: ScenarioResult,
    scenario_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    geofence_document: InputDocument | None = None,
    landing_zone_document: InputDocument | None = None,
    terrain_document: InputDocument | None = None,
    population_document: InputDocument | None = None,
    wind_grid_document: InputDocument | None = None,
) -> ScenarioResultEnvelope:
    """Build the canonical scenario result envelope from a completed run."""
    provenance = _build_provenance(
        scenario_document,
        mission_document,
        vehicle_document,
        geofence_document=geofence_document,
        landing_zone_document=landing_zone_document,
        terrain_document=terrain_document,
        population_document=population_document,
        wind_grid_document=wind_grid_document,
    )
    return _base_envelope(
        scenario_id=result.scenario_id,
        status=result.status,
        provenance=provenance,
        result=result,
    )


def build_scenario_invalid_input_envelope(
    *,
    scenario_id: str,
    error: InputLoadError,
    scenario_document: InputDocument | None = None,
    mission_document: InputDocument | None = None,
    vehicle_document: InputDocument | None = None,
    known_documents: dict[str, InputDocument | None] | None = None,
) -> ScenarioResultEnvelope:
    """Build an error envelope for input load failures."""
    known: dict[str, InputDocument | None] = {
        "scenario": scenario_document,
        "mission": mission_document,
        "vehicle": vehicle_document,
    }
    if known_documents is not None:
        known.update(known_documents)
    # Attach partial document from the error if available and not yet known.
    if error.document is not None and known.get(error.input_name) is None:
        known[error.input_name] = error.document

    return _base_envelope(
        scenario_id=scenario_id,
        status=ScenarioStatus.ERROR,
        provenance=_partial_provenance(known),
        result=None,
    )


def build_scenario_internal_error_envelope(
    *,
    scenario_id: str,
    known_documents: dict[str, InputDocument | None] | None = None,
) -> ScenarioResultEnvelope:
    """Build an error envelope for unexpected internal errors."""
    provenance = (
        _partial_provenance(known_documents)
        if known_documents is not None
        else _empty_provenance()
    )
    return _base_envelope(
        scenario_id=scenario_id,
        status=ScenarioStatus.ERROR,
        provenance=provenance,
        result=None,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_scenario_envelope_json(envelope: ScenarioResultEnvelope) -> str:
    """Render the envelope as canonical deterministic JSON."""
    payload = envelope.model_dump(mode="json")
    return render_canonical_json(payload)
