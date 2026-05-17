"""Canonical result envelope for estimator CLI outputs."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from adapters.canonical_json import render_canonical_json
from adapters.io import InputDocument, InputLoadError
from adapters.version import tool_version
from estimator import EstimateStatus, MissionEstimate
from estimator.core.enums import FailureCode, WarningCode
from estimator.core.results import EstimatorContextValue

RESULT_ENVELOPE_SCHEMA_VERSION = "estimator-envelope.v5"
MISSION_SCHEMA_VERSION = "mission.v5"
VEHICLE_SCHEMA_VERSION = "vehicle.v3"
GEOFENCE_SCHEMA_VERSION = "geofence-geojson.v1"
LANDING_ZONE_SCHEMA_VERSION = "landing-zone-geojson.v1"
TERRAIN_SCHEMA_VERSION = "terrain-grid.v1"
WIND_GRID_SCHEMA_VERSION = "wind-grid.v1"

_ASSUMPTIONS = [
    "Estimator v1 is deterministic and uses no randomness.",
    "Wind input is constant in space and time unless a layered, time-varying, or spatiotemporal grid provider is used.",
    "Transit is modeled as geodesic leg-to-leg kinematics.",
    "Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.",
    "Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 adds turn-arc geometry, sub-segment sampling, and tangent-point offset subtraction (turn_radius_m * tan(|Δθ|/2)) from adjacent transit leg path_distance_m values so total path distance reflects the true Dubins-path length.",
    "Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.",
    "Takeoff and landing-transit legs report path_distance_m equal to vertical_distance_m; for purely vertical movement this is the 3D slant path distance.",
    "Energy feasibility uses deterministic phase power values from the vehicle profile.",
    "Explicit resource systems are evaluated after route expansion; when configured, they determine resource feasibility while result.energy remains the legacy battery-only energy view.",
    "Communication-link feasibility is deterministic and uses configured static availability and range constraints only; live network calls are not performed.",
    "Static geofence feasibility uses 2D lon/lat route-segment geometry.",
    "Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.",
    "Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.",
    "Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.",
    "Divert route estimates use geodesic-aware Dubins path distance (bank-angle-constrained arc + straight sampled to target geometry boundary points) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. TAS-based transit time is used without wind correction or geofence intersection on the divert leg.",
    "Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.",
]

_TOTAL_FIELD_PATHS = [
    "result.total_horizontal_distance_m",
    "result.total_vertical_distance_m",
    "result.total_path_distance_m",
    "result.total_time_s",
]

_ENERGY_FIELD_PATHS = [
    "result.energy",
]

_RESOURCE_FIELD_PATHS = [
    "result.resource",
]

_LINK_FIELD_PATHS = [
    "result.link",
]

_GEOFENCE_FIELD_PATHS = [
    "result.geofence",
]

_LANDING_ZONE_FIELD_PATHS = [
    "result.landing_zone",
]

_ENERGY_FAILURE_CODES = frozenset(
    {
        FailureCode.INSUFFICIENT_ENERGY,
        FailureCode.RESERVE_BELOW_THRESHOLD,
        FailureCode.MISSING_ENERGY_MODEL,
        FailureCode.UNSUPPORTED_PHASE_ENERGY_MODEL,
        FailureCode.INVALID_ENERGY_MODEL,
        FailureCode.INVALID_ENERGY_POLICY,
    }
)

_RESOURCE_FAILURE_CODES = frozenset(
    {
        FailureCode.RESOURCE_FEASIBILITY_FAILED,
    }
)

_LINK_FAILURE_CODES = frozenset(
    {
        FailureCode.LINK_FEASIBILITY_FAILED,
    }
)

_GEOFENCE_FAILURE_CODES = frozenset(
    {
        FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE,
        FailureCode.ROUTE_EXITS_REQUIRED_ZONE,
    }
)

_LANDING_ZONE_FAILURE_CODES = frozenset(
    {
        FailureCode.NO_REACHABLE_LANDING_ZONE,
        FailureCode.LANDING_ZONE_REACHABLE_BUT_BELOW_RESERVE,
        FailureCode.ALL_LANDING_ZONES_UNAVAILABLE,
    }
)

_STATIC_FEASIBILITY_FAILURE_CODES = (
    _ENERGY_FAILURE_CODES
    | _RESOURCE_FAILURE_CODES
    | _LINK_FAILURE_CODES
    | _GEOFENCE_FAILURE_CODES
    | _LANDING_ZONE_FAILURE_CODES
)


class DiagnosticLevel(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class DiagnosticKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED = "unsupported"
    INFEASIBLE = "infeasible"
    INTERNAL_ERROR = "internal_error"


class EnvelopeDiagnosticCode(StrEnum):
    INPUT_LOAD_ERROR = "INPUT_LOAD_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ResultScope(StrEnum):
    NONE = "none"
    FULL_MISSION = "full_mission"
    COMPLETED_LEGS_ONLY = "completed_legs_only"


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class EnvelopeDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: DiagnosticLevel
    kind: DiagnosticKind | None = None
    code: FailureCode | WarningCode | EnvelopeDiagnosticCode
    message: str
    leg_index: int | None = None
    route_item_index: int | None = None
    route_item_id: str | None = None
    context: dict[str, EstimatorContextValue] = Field(default_factory=dict)


class ResultValidity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_complete: bool
    is_partial: bool
    is_valid_for_full_mission: bool
    scope: ResultScope
    invalidated_fields: list[str] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)


class ProvenanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str
    sha256: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator_api: str
    inputs: dict[str, ProvenanceInput]


class DeterminismMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deterministic: bool = True
    randomness_used: bool = False
    external_network_access_used: bool = False
    canonical_json: bool = True
    canonical_json_sort_keys: bool = True


class EstimatorResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_version: str
    input_schema_versions: dict[str, str]
    status: EstimateStatus
    diagnostics: list[EnvelopeDiagnostic] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    result_validity: ResultValidity
    provenance: Provenance
    determinism_metadata: DeterminismMetadata
    result: MissionEstimate | None = None


@dataclass(frozen=True)
class EnvelopeInputs:
    mission: InputDocument
    vehicle: InputDocument
    geofences: InputDocument | None = None
    landing_zones: InputDocument | None = None
    terrain: InputDocument | None = None
    wind_grid: InputDocument | None = None


def _build_provenance(inputs: EnvelopeInputs) -> Provenance:
    provenance_inputs = {
        "mission": ProvenanceInput(
            format=inputs.mission.format,
            sha256=inputs.mission.sha256,
        ),
        "vehicle": ProvenanceInput(
            format=inputs.vehicle.format,
            sha256=inputs.vehicle.sha256,
        ),
    }
    if inputs.geofences is not None:
        provenance_inputs["geofences"] = ProvenanceInput(
            format=inputs.geofences.format,
            sha256=inputs.geofences.sha256,
        )
    if inputs.landing_zones is not None:
        provenance_inputs["landing_zones"] = ProvenanceInput(
            format=inputs.landing_zones.format,
            sha256=inputs.landing_zones.sha256,
        )
    if inputs.terrain is not None:
        provenance_inputs["terrain"] = ProvenanceInput(
            format=inputs.terrain.format,
            sha256=inputs.terrain.sha256,
        )
    if inputs.wind_grid is not None:
        provenance_inputs["wind_grid"] = ProvenanceInput(
            format=inputs.wind_grid.format,
            sha256=inputs.wind_grid.sha256,
        )

    return Provenance(
        estimator_api="estimator.try_estimate_mission_distance_time",
        inputs=provenance_inputs,
    )


def _resolve_invalid_input_documents(
    error: InputLoadError,
    *,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
) -> dict[str, InputDocument]:
    documents: dict[str, InputDocument | None] = {
        "mission": mission_document,
        "vehicle": vehicle_document,
    }
    if error.document is not None and documents[error.input_name] is None:
        documents[error.input_name] = error.document

    return {
        name: document for name, document in documents.items() if document is not None
    }


def _static_feasibility_result_validity(result: MissionEstimate) -> ResultValidity:
    if result.failure is None:
        raise ValueError("Static-feasibility result validity requires a failure.")

    artifact_requirements = (
        (True, result.energy is not None, _ENERGY_FIELD_PATHS),
        (
            result.failure.code in _RESOURCE_FAILURE_CODES,
            result.resource is not None,
            _RESOURCE_FIELD_PATHS,
        ),
        (
            result.failure.code in _LINK_FAILURE_CODES,
            result.link is not None,
            _LINK_FIELD_PATHS,
        ),
        (
            result.failure.code in _GEOFENCE_FAILURE_CODES,
            result.geofence is not None,
            _GEOFENCE_FIELD_PATHS,
        ),
        (
            result.failure.code in _LANDING_ZONE_FAILURE_CODES,
            result.landing_zone is not None,
            _LANDING_ZONE_FIELD_PATHS,
        ),
    )
    unavailable_fields = [
        field
        for is_required, is_available, fields in artifact_requirements
        if is_required and not is_available
        for field in fields
    ]
    is_complete = len(unavailable_fields) == 0
    return ResultValidity(
        is_complete=is_complete,
        is_partial=False,
        is_valid_for_full_mission=is_complete,
        scope=ResultScope.FULL_MISSION,
        unavailable_fields=unavailable_fields,
    )


def _build_result_validity(result: MissionEstimate | None) -> ResultValidity:
    if result is None:
        return ResultValidity(
            is_complete=False,
            is_partial=False,
            is_valid_for_full_mission=False,
            scope=ResultScope.NONE,
            invalidated_fields=[],
            unavailable_fields=["result"],
        )

    if result.status == EstimateStatus.SUCCESS and not result.totals_are_partial:
        return ResultValidity(
            is_complete=True,
            is_partial=False,
            is_valid_for_full_mission=True,
            scope=ResultScope.FULL_MISSION,
        )

    if (
        result.failure is not None
        and result.failure.code in _STATIC_FEASIBILITY_FAILURE_CODES
        and not result.totals_are_partial
    ):
        return _static_feasibility_result_validity(result)

    if (
        result.failure is not None
        and result.failure.code not in _STATIC_FEASIBILITY_FAILURE_CODES
        and not result.totals_are_partial
        and result.legs
    ):
        return ResultValidity(
            is_complete=False,
            is_partial=False,
            is_valid_for_full_mission=False,
            scope=ResultScope.FULL_MISSION,
        )

    if result.totals_are_partial:
        return ResultValidity(
            is_complete=False,
            is_partial=True,
            is_valid_for_full_mission=False,
            scope=ResultScope.COMPLETED_LEGS_ONLY,
            invalidated_fields=list(_TOTAL_FIELD_PATHS),
        )

    return ResultValidity(
        is_complete=False,
        is_partial=False,
        is_valid_for_full_mission=False,
        scope=ResultScope.NONE,
        unavailable_fields=list(_TOTAL_FIELD_PATHS),
    )


def _build_diagnostics(result: MissionEstimate | None) -> list[EnvelopeDiagnostic]:
    if result is None:
        return []

    diagnostics = [
        EnvelopeDiagnostic(
            level=DiagnosticLevel.WARNING,
            code=warning.code,
            message=warning.message,
            leg_index=warning.leg_index,
            route_item_index=warning.route_item_index,
            route_item_id=warning.route_item_id,
        )
        for warning in result.warnings
    ]

    if result.failure is not None:
        diagnostics.append(
            EnvelopeDiagnostic(
                level=DiagnosticLevel.ERROR,
                kind=DiagnosticKind(result.failure.kind.value),
                code=result.failure.code,
                message=result.failure.message,
                leg_index=result.failure.leg_index,
                route_item_index=result.failure.route_item_index,
                route_item_id=result.failure.route_item_id,
                context=result.failure.context,
            )
        )
    return diagnostics


def _input_schema_versions() -> dict[str, str]:
    return {
        "mission": MISSION_SCHEMA_VERSION,
        "vehicle": VEHICLE_SCHEMA_VERSION,
        "geofences": GEOFENCE_SCHEMA_VERSION,
        "landing_zones": LANDING_ZONE_SCHEMA_VERSION,
        "terrain": TERRAIN_SCHEMA_VERSION,
        "wind_grid": WIND_GRID_SCHEMA_VERSION,
    }


def _build_envelope(
    *,
    status: EstimateStatus,
    diagnostics: list[EnvelopeDiagnostic],
    provenance: Provenance,
    result: MissionEstimate | None,
) -> EstimatorResultEnvelope:
    return EstimatorResultEnvelope(
        schema_version=RESULT_ENVELOPE_SCHEMA_VERSION,
        tool_version=tool_version(),
        input_schema_versions=_input_schema_versions(),
        status=status,
        diagnostics=diagnostics,
        assumptions=list(_ASSUMPTIONS),
        result_validity=_build_result_validity(result),
        provenance=provenance,
        determinism_metadata=DeterminismMetadata(),
        result=result,
    )


def build_estimator_envelope(
    *,
    result: MissionEstimate,
    inputs: EnvelopeInputs,
) -> EstimatorResultEnvelope:
    return _build_envelope(
        status=result.status,
        diagnostics=_build_diagnostics(result),
        provenance=_build_provenance(inputs),
        result=result,
    )


def build_invalid_input_envelope(
    *,
    error: InputLoadError,
    mission_document: InputDocument | None = None,
    vehicle_document: InputDocument | None = None,
) -> EstimatorResultEnvelope:
    inputs = {
        name: ProvenanceInput(format=document.format, sha256=document.sha256)
        for name, document in _resolve_invalid_input_documents(
            error,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        ).items()
    }
    return _build_envelope(
        status=EstimateStatus.ERROR,
        diagnostics=[
            EnvelopeDiagnostic(
                level=DiagnosticLevel.ERROR,
                kind=DiagnosticKind.INVALID_INPUT,
                code=EnvelopeDiagnosticCode.INPUT_LOAD_ERROR,
                message=str(error),
                context=error.to_context(),
            )
        ],
        provenance=Provenance(
            estimator_api="estimator.try_estimate_mission_distance_time",
            inputs=inputs,
        ),
        result=None,
    )


def build_internal_error_envelope(
    *,
    error: Exception,
    inputs: EnvelopeInputs | None = None,
) -> EstimatorResultEnvelope:
    provenance = (
        _build_provenance(inputs)
        if inputs is not None
        else Provenance(
            estimator_api="estimator.try_estimate_mission_distance_time", inputs={}
        )
    )
    return _build_envelope(
        status=EstimateStatus.ERROR,
        diagnostics=[
            EnvelopeDiagnostic(
                level=DiagnosticLevel.ERROR,
                kind=DiagnosticKind.INTERNAL_ERROR,
                code=EnvelopeDiagnosticCode.INTERNAL_ERROR,
                message="Unexpected internal error while running estimator CLI.",
                context={"error_type": type(error).__name__},
            )
        ],
        provenance=provenance,
        result=None,
    )


def render_envelope_json(envelope: EstimatorResultEnvelope) -> str:
    payload = envelope.model_dump(mode="json")
    return render_canonical_json(payload)
