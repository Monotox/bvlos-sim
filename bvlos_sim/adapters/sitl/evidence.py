"""SITL adapter contract and evidence-bundle rendering."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from bvlos_sim.adapters.canonical_json import render_canonical_json
from bvlos_sim.adapters.envelope import (
    GEOFENCE_SCHEMA_VERSION,
    LANDING_ZONE_SCHEMA_VERSION,
    MISSION_SCHEMA_VERSION,
    POPULATION_SCHEMA_VERSION,
    TERRAIN_SCHEMA_VERSION,
    VEHICLE_SCHEMA_VERSION,
    WIND_GRID_SCHEMA_VERSION,
)
from bvlos_sim.adapters.io import InputDocument
from bvlos_sim.adapters.scenario_envelope import (
    SCENARIO_INPUT_SCHEMA_VERSION,
    SCENARIO_REPORT_SCHEMA_VERSION,
    ScenarioResultEnvelope,
)
from bvlos_sim.adapters.sitl.comparison import build_sitl_comparison_report
from bvlos_sim.adapters.uncertainty_envelope import UNCERTAINTY_INPUT_SCHEMA_VERSION
from bvlos_sim.adapters.version import tool_version
from bvlos_sim.schemas.vehicle import VehicleProfile
from bvlos_sim.schemas.sitl import (
    SitlAdapterKind,
    SitlArtifactReference,
    SitlArtifactRole,
    SitlEvidenceBundle,
    SitlEvidenceStatus,
    SitlExpectedOutputs,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)
from bvlos_sim.schemas.sitl_comparison import SitlComparisonReport

SITL_EVIDENCE_SCHEMA_VERSION = "sitl-evidence.v1"
NOOP_SITL_ADAPTER_ID = "noop-contract"
OBSTACLE_SCHEMA_VERSION = "obstacle-geojson.v1"


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
    """Contract-only adapter for workflows that intentionally skip live SITL."""

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


def _document_reference(
    document: InputDocument,
    *,
    role: SitlArtifactRole,
    schema_version: str | None,
    reference_base_dir: Path | None,
) -> SitlArtifactReference:
    return SitlArtifactReference(
        role=role,
        path=_portable_artifact_path(document.path, reference_base_dir),
        format=document.format,
        sha256=document.sha256,
        schema_version=schema_version,
    )


def _optional_document_references(
    *,
    geofence_document: InputDocument | None,
    landing_zone_document: InputDocument | None,
    terrain_document: InputDocument | None,
    population_document: InputDocument | None,
    obstacle_document: InputDocument | None,
    wind_grid_document: InputDocument | None,
    uncertainty_document: InputDocument | None,
    reference_base_dir: Path | None,
) -> list[SitlArtifactReference]:
    optional_documents = (
        (geofence_document, SitlArtifactRole.GEOFENCES, GEOFENCE_SCHEMA_VERSION),
        (
            landing_zone_document,
            SitlArtifactRole.LANDING_ZONES,
            LANDING_ZONE_SCHEMA_VERSION,
        ),
        (terrain_document, SitlArtifactRole.TERRAIN, TERRAIN_SCHEMA_VERSION),
        (
            population_document,
            SitlArtifactRole.POPULATION,
            POPULATION_SCHEMA_VERSION,
        ),
        (obstacle_document, SitlArtifactRole.OBSTACLES, OBSTACLE_SCHEMA_VERSION),
        (wind_grid_document, SitlArtifactRole.WIND_GRID, WIND_GRID_SCHEMA_VERSION),
        (
            uncertainty_document,
            SitlArtifactRole.UNCERTAINTY,
            UNCERTAINTY_INPUT_SCHEMA_VERSION,
        ),
    )
    return [
        _document_reference(
            document,
            role=role,
            schema_version=schema_version,
            reference_base_dir=reference_base_dir,
        )
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
    population_document: InputDocument | None,
    obstacle_document: InputDocument | None,
    wind_grid_document: InputDocument | None,
    uncertainty_document: InputDocument | None,
    reference_base_dir: Path | None,
) -> list[SitlArtifactReference]:
    return [
        _document_reference(
            scenario_document,
            role=SitlArtifactRole.SCENARIO,
            schema_version=SCENARIO_INPUT_SCHEMA_VERSION,
            reference_base_dir=reference_base_dir,
        ),
        _document_reference(
            mission_document,
            role=SitlArtifactRole.MISSION,
            schema_version=MISSION_SCHEMA_VERSION,
            reference_base_dir=reference_base_dir,
        ),
        _document_reference(
            vehicle_document,
            role=SitlArtifactRole.VEHICLE,
            schema_version=VEHICLE_SCHEMA_VERSION,
            reference_base_dir=reference_base_dir,
        ),
        *_optional_document_references(
            geofence_document=geofence_document,
            landing_zone_document=landing_zone_document,
            terrain_document=terrain_document,
            population_document=population_document,
            obstacle_document=obstacle_document,
            wind_grid_document=wind_grid_document,
            uncertainty_document=uncertainty_document,
            reference_base_dir=reference_base_dir,
        ),
    ]


def _portable_artifact_path(path: Path, reference_base_dir: Path | None) -> str:
    if reference_base_dir is None:
        return str(path)
    resolved_path = path.resolve(strict=False)
    resolved_base = reference_base_dir.resolve(strict=False)
    try:
        return Path(os.path.relpath(resolved_path, resolved_base)).as_posix()
    except ValueError:
        # Different Windows drives cannot be expressed as a relative path.
        return str(resolved_path)


def _is_artifact_uri(path: str) -> bool:
    scheme = urlsplit(path).scheme
    return bool(scheme and not (len(scheme) == 1 and path[1:3] in {":/", ":\\"}))


def _portable_reference(
    reference: SitlArtifactReference,
    reference_base_dir: Path | None,
) -> SitlArtifactReference:
    if reference_base_dir is None or _is_artifact_uri(reference.path):
        return reference
    return reference.model_copy(
        update={
            "path": _portable_artifact_path(Path(reference.path), reference_base_dir)
        }
    )


def _portable_observed_artifacts(
    observed: SitlObservedArtifacts,
    reference_base_dir: Path | None,
) -> SitlObservedArtifacts:
    if reference_base_dir is None:
        return observed
    return observed.model_copy(
        update={
            field_name: [
                _portable_reference(reference, reference_base_dir)
                for reference in getattr(observed, field_name)
            ]
            for field_name in (
                "telemetry",
                "command_logs",
                "simulator_logs",
                "adapter_logs",
            )
        }
    )


def _evidence_status(
    observed: SitlObservedArtifacts,
    simulator: SitlSimulatorMetadata,
) -> SitlEvidenceStatus:
    if simulator.adapter_kind is SitlAdapterKind.NOOP_CONTRACT:
        return SitlEvidenceStatus.CONTRACT_ONLY
    if (
        observed.telemetry
        and simulator.metadata.get("mission_run_state") == "complete"
        and simulator.metadata.get("mission_execution_verified") is True
    ):
        return SitlEvidenceStatus.COMPLETED
    return SitlEvidenceStatus.ERROR


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
    population_document: InputDocument | None = None,
    obstacle_document: InputDocument | None = None,
    wind_grid_document: InputDocument | None = None,
    uncertainty_document: InputDocument | None = None,
    adapter: SitlAdapter | None = None,
    reference_base_dir: Path | None = None,
) -> SitlEvidenceBundle:
    """Build a deterministic SITL evidence bundle from existing scenario outputs."""

    resolved_adapter = adapter or NoopSitlAdapter()
    scenario_payload = scenario_envelope.model_dump(mode="json")
    observed = _portable_observed_artifacts(
        resolved_adapter.observed_artifacts(), reference_base_dir
    )
    simulator = resolved_adapter.simulator_metadata(vehicle)
    status = _evidence_status(observed, simulator)
    estimate_payload = (
        scenario_envelope.estimate.model_dump(mode="json")
        if scenario_envelope.estimate is not None
        else None
    )
    return SitlEvidenceBundle(
        schema_version=SITL_EVIDENCE_SCHEMA_VERSION,
        evidence_id=evidence_id,
        status=status,
        tool_version=tool_version(),
        created_by="bvlos-sim sitl",
        inputs=_input_references(
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            geofence_document=geofence_document,
            landing_zone_document=landing_zone_document,
            terrain_document=terrain_document,
            population_document=population_document,
            obstacle_document=obstacle_document,
            wind_grid_document=wind_grid_document,
            uncertainty_document=uncertainty_document,
            reference_base_dir=reference_base_dir,
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
        simulator=simulator,
        observed=observed,
        metadata={
            "contract_only": status == SitlEvidenceStatus.CONTRACT_ONLY,
            "mission_execution_verified": status == SitlEvidenceStatus.COMPLETED,
            "live_dependencies_required": status != SitlEvidenceStatus.CONTRACT_ONLY,
            "follow_on_tickets": "041-043, 045-046",
        },
    )


def render_sitl_evidence_json(bundle: SitlEvidenceBundle) -> str:
    """Render a SITL evidence bundle as canonical deterministic JSON."""

    payload = bundle.model_dump(mode="json")
    return render_canonical_json(payload)


def compare_sitl_evidence_bundle(
    bundle: SitlEvidenceBundle,
    *,
    comparison_id: str,
    position_tolerance_m: float = 500.0,
) -> SitlComparisonReport:
    """Build a comparison report from an evidence bundle."""

    return build_sitl_comparison_report(
        comparison_id=comparison_id,
        bundle=bundle,
        position_tolerance_m=position_tolerance_m,
    )


__all__ = [
    "NOOP_SITL_ADAPTER_ID",
    "SITL_EVIDENCE_SCHEMA_VERSION",
    "NoopSitlAdapter",
    "SitlAdapter",
    "build_sitl_evidence_bundle",
    "compare_sitl_evidence_bundle",
    "render_sitl_evidence_json",
]
