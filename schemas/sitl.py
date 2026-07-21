"""SITL evidence bundle schema models."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type SitlJsonScalar = str | int | float | bool | None
type SitlJsonValue = SitlJsonScalar | list[SitlJsonValue] | dict[str, SitlJsonValue]


class SitlEvidenceStatus(StrEnum):
    """Execution status for a SITL evidence bundle."""

    CONTRACT_ONLY = "contract_only"
    COMPLETED = "completed"
    ERROR = "error"


class SitlAdapterKind(StrEnum):
    """SITL adapter families supported by the evidence contract."""

    NOOP_CONTRACT = "noop_contract"
    ARDUPILOT = "ardupilot"
    PX4 = "px4"


class SitlArtifactRole(StrEnum):
    """Artifact roles accepted by the SITL evidence schema."""

    MISSION = "mission"
    VEHICLE = "vehicle"
    SCENARIO = "scenario"
    TERRAIN = "terrain"
    POPULATION = "population"
    OBSTACLES = "obstacles"
    WIND_GRID = "wind_grid"
    GEOFENCES = "geofences"
    LANDING_ZONES = "landing_zones"
    UNCERTAINTY = "uncertainty"
    ESTIMATOR_REPORT = "estimator_report"
    SCENARIO_REPORT = "scenario_report"
    UNCERTAINTY_REPORT = "uncertainty_report"
    TELEMETRY = "telemetry"
    COMMAND_LOG = "command_log"
    SIMULATOR_LOG = "simulator_log"
    ADAPTER_LOG = "adapter_log"
    COMPARISON_REPORT = "comparison_report"
    OTHER = "other"


class SitlArtifactReference(BaseModel):
    """Reference to an input, expected-output, or observed SITL artifact.

    Artifact references are metadata only. The deterministic estimator and
    scenario runner never dereference SITL telemetry, command, simulator, or
    adapter-log artifacts.
    """

    model_config = ConfigDict(extra="forbid")

    role: SitlArtifactRole = Field(description="Artifact role in the evidence bundle.")
    path: str = Field(min_length=1, description="Artifact path or URI.")
    format: str | None = Field(default=None, description="Artifact format name.")
    sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="Optional SHA-256 digest for immutable local artifacts.",
    )
    schema_version: str | None = Field(
        default=None,
        description="Optional schema or report version for structured artifacts.",
    )
    description: str | None = Field(
        default=None, description="Human-readable artifact note."
    )


class SitlSimulatorMetadata(BaseModel):
    """Simulator and adapter metadata for a SITL evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    adapter_kind: SitlAdapterKind = Field(
        description="Adapter family used for the run."
    )
    adapter_id: str = Field(
        min_length=1, description="Adapter implementation identifier."
    )
    adapter_version: str = Field(
        min_length=1, description="Adapter implementation version."
    )
    execution_mode: str = Field(
        min_length=1,
        description="Execution mode, for example contract_only or live_sitl.",
    )
    simulator_name: str | None = Field(
        default=None, description="Simulator name, if any."
    )
    simulator_version: str | None = Field(
        default=None, description="Simulator version, if known."
    )
    autopilot: str | None = Field(
        default=None, description="Autopilot family from vehicle metadata."
    )
    frame: str | None = Field(
        default=None, description="SITL frame or model from vehicle metadata."
    )
    metadata: dict[str, SitlJsonValue] = Field(
        default_factory=dict,
        description="Free-form adapter metadata ignored by deterministic estimator logic.",
    )


class SitlObservedArtifacts(BaseModel):
    """Observed artifacts produced by a SITL adapter.

    The contract-only adapter leaves these lists empty. Live adapters fill
    them without changing the evidence bundle shape.
    """

    model_config = ConfigDict(extra="forbid")

    telemetry: list[SitlArtifactReference] = Field(default_factory=list)
    command_logs: list[SitlArtifactReference] = Field(default_factory=list)
    simulator_logs: list[SitlArtifactReference] = Field(default_factory=list)
    adapter_logs: list[SitlArtifactReference] = Field(default_factory=list)


class SitlExpectedOutputs(BaseModel):
    """Deterministic outputs used as expected behavior for SITL comparison."""

    model_config = ConfigDict(extra="forbid")

    scenario_report: dict[str, SitlJsonValue] | None = Field(
        default=None,
        description="Canonical scenario report payload used as expected behavior.",
    )
    estimator_result: dict[str, SitlJsonValue] | None = Field(
        default=None,
        description="Embedded deterministic estimator result from the scenario report.",
    )
    reports: list[SitlArtifactReference] = Field(
        default_factory=list,
        description="Optional references to persisted deterministic report artifacts.",
    )


class SitlEvidenceBundle(BaseModel):
    """Versioned SITL evidence bundle contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sitl-evidence.v1"] = Field(
        description="SITL evidence schema version.",
    )
    evidence_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable evidence bundle identifier.",
    )
    status: SitlEvidenceStatus = Field(description="SITL evidence collection status.")
    tool_version: str = Field(min_length=1, description="bvlos-sim tool version.")
    created_by: str = Field(min_length=1, description="Creator API or CLI command.")
    inputs: list[SitlArtifactReference] = Field(
        default_factory=list,
        description="Mission, vehicle, scenario, and asset artifacts used for the run.",
    )
    expected: SitlExpectedOutputs = Field(
        description="Deterministic expected outputs for later comparison.",
    )
    simulator: SitlSimulatorMetadata = Field(
        description="Simulator and adapter metadata."
    )
    observed: SitlObservedArtifacts = Field(
        default_factory=SitlObservedArtifacts,
        description="Telemetry and command artifacts captured from the simulator.",
    )
    metadata: dict[str, SitlJsonValue] = Field(
        default_factory=dict,
        description="Free-form evidence-bundle metadata.",
    )


__all__ = [
    "SitlAdapterKind",
    "SitlArtifactReference",
    "SitlArtifactRole",
    "SitlEvidenceBundle",
    "SitlEvidenceStatus",
    "SitlExpectedOutputs",
    "SitlObservedArtifacts",
    "SitlSimulatorMetadata",
]
