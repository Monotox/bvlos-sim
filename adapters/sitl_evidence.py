"""SITL adapter contract and evidence-bundle rendering."""

import json
import tomllib
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Protocol

from adapters.envelope import (
    GEOFENCE_SCHEMA_VERSION,
    LANDING_ZONE_SCHEMA_VERSION,
    MISSION_SCHEMA_VERSION,
    TERRAIN_SCHEMA_VERSION,
    VEHICLE_SCHEMA_VERSION,
    WIND_GRID_SCHEMA_VERSION,
)
from adapters.io import InputDocument
from adapters.scenario_envelope import (
    SCENARIO_INPUT_SCHEMA_VERSION,
    SCENARIO_REPORT_SCHEMA_VERSION,
    ScenarioResultEnvelope,
)
from schemas.vehicle import VehicleProfile
from schemas.sitl import (
    SitlAdapterKind,
    SitlArtifactReference,
    SitlArtifactRole,
    SitlEvidenceBundle,
    SitlEvidenceStatus,
    SitlExpectedOutputs,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)

SITL_EVIDENCE_SCHEMA_VERSION = "sitl-evidence.v1"
NOOP_SITL_ADAPTER_ID = "noop-contract"


class SitlAdapter(Protocol):
    """Boundary implemented by live or no-op SITL adapters outside estimator core."""

    adapter_id: str
    adapter_kind: SitlAdapterKind
    adapter_version: str

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        """Return simulator metadata for the evidence bundle."""

    def observed_artifacts(self) -> SitlObservedArtifacts:
        """Return telemetry and command artifacts captured by the adapter."""


@dataclass(frozen=True)
class NoopSitlAdapter:
    """Contract-only adapter used before live SITL execution is implemented."""

    adapter_id: str = NOOP_SITL_ADAPTER_ID
    adapter_kind: SitlAdapterKind = SitlAdapterKind.NOOP_CONTRACT
    adapter_version: str = "0.1.0"

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        sitl = vehicle.sitl
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode="contract_only",
            simulator_name=None,
            simulator_version=None,
            autopilot=vehicle.autopilot.value,
            frame=sitl.frame if sitl is not None else None,
            metadata={
                "live_simulator_started": False,
                "mission_uploaded": False,
                "telemetry_recorded": False,
            },
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        return SitlObservedArtifacts()


def _tool_version() -> str:
    try:
        return importlib_metadata.version("bvlos-sim")
    except importlib_metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])


def _document_reference(
    document: InputDocument,
    *,
    role: SitlArtifactRole,
    schema_version: str | None,
) -> SitlArtifactReference:
    return SitlArtifactReference(
        role=role,
        path=str(document.path),
        format=document.format,
        sha256=document.sha256,
        schema_version=schema_version,
    )


def _optional_document_references(
    *,
    geofence_document: InputDocument | None,
    landing_zone_document: InputDocument | None,
    terrain_document: InputDocument | None,
    wind_grid_document: InputDocument | None,
) -> list[SitlArtifactReference]:
    optional_documents = (
        (geofence_document, SitlArtifactRole.GEOFENCES, GEOFENCE_SCHEMA_VERSION),
        (landing_zone_document, SitlArtifactRole.LANDING_ZONES, LANDING_ZONE_SCHEMA_VERSION),
        (terrain_document, SitlArtifactRole.TERRAIN, TERRAIN_SCHEMA_VERSION),
        (wind_grid_document, SitlArtifactRole.WIND_GRID, WIND_GRID_SCHEMA_VERSION),
    )
    return [
        _document_reference(document, role=role, schema_version=schema_version)
        for document, role, schema_version in optional_documents
        if document is not None
    ]


def _input_references(
    *,
    scenario_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    geofence_document: InputDocument | None,
    landing_zone_document: InputDocument | None,
    terrain_document: InputDocument | None,
    wind_grid_document: InputDocument | None,
) -> list[SitlArtifactReference]:
    return [
        _document_reference(
            scenario_document,
            role=SitlArtifactRole.SCENARIO,
            schema_version=SCENARIO_INPUT_SCHEMA_VERSION,
        ),
        _document_reference(
            mission_document,
            role=SitlArtifactRole.MISSION,
            schema_version=MISSION_SCHEMA_VERSION,
        ),
        _document_reference(
            vehicle_document,
            role=SitlArtifactRole.VEHICLE,
            schema_version=VEHICLE_SCHEMA_VERSION,
        ),
        *_optional_document_references(
            geofence_document=geofence_document,
            landing_zone_document=landing_zone_document,
            terrain_document=terrain_document,
            wind_grid_document=wind_grid_document,
        ),
    ]


def build_sitl_evidence_bundle(
    *,
    evidence_id: str,
    scenario_envelope: ScenarioResultEnvelope,
    scenario_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    vehicle: VehicleProfile,
    geofence_document: InputDocument | None = None,
    landing_zone_document: InputDocument | None = None,
    terrain_document: InputDocument | None = None,
    wind_grid_document: InputDocument | None = None,
    adapter: SitlAdapter | None = None,
) -> SitlEvidenceBundle:
    """Build a deterministic SITL evidence bundle from existing scenario outputs."""

    resolved_adapter = adapter or NoopSitlAdapter()
    scenario_payload = scenario_envelope.model_dump(mode="json")
    estimate_payload = (
        scenario_envelope.estimate.model_dump(mode="json")
        if scenario_envelope.estimate is not None
        else None
    )
    return SitlEvidenceBundle(
        schema_version=SITL_EVIDENCE_SCHEMA_VERSION,
        evidence_id=evidence_id,
        status=SitlEvidenceStatus.CONTRACT_ONLY,
        tool_version=_tool_version(),
        created_by="bvlos-sim sitl",
        inputs=_input_references(
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            geofence_document=geofence_document,
            landing_zone_document=landing_zone_document,
            terrain_document=terrain_document,
            wind_grid_document=wind_grid_document,
        ),
        expected=SitlExpectedOutputs(
            scenario_report=scenario_payload,
            estimator_result=estimate_payload,
            reports=[
                SitlArtifactReference(
                    role=SitlArtifactRole.SCENARIO_REPORT,
                    path=f"embedded:{scenario_envelope.scenario_id}",
                    format="json",
                    schema_version=SCENARIO_REPORT_SCHEMA_VERSION,
                    description="Embedded deterministic scenario report payload.",
                )
            ],
        ),
        simulator=resolved_adapter.simulator_metadata(vehicle),
        observed=resolved_adapter.observed_artifacts(),
        metadata={
            "contract_only": True,
            "live_dependencies_required": False,
            "follow_on_tickets": "041-043",
        },
    )


def render_sitl_evidence_json(bundle: SitlEvidenceBundle) -> str:
    """Render a SITL evidence bundle as canonical deterministic JSON."""

    payload = bundle.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


__all__ = [
    "NOOP_SITL_ADAPTER_ID",
    "SITL_EVIDENCE_SCHEMA_VERSION",
    "NoopSitlAdapter",
    "SitlAdapter",
    "build_sitl_evidence_bundle",
    "render_sitl_evidence_json",
]
