"""Tests for SITL telemetry and evidence artifacts (Ticket 042)."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from adapters.io import InputDocument, load_vehicle
from adapters.scenario_envelope import ScenarioResultEnvelope, build_scenario_envelope
from adapters.sitl_artifacts import (
    SITL_COMMAND_LOG_SCHEMA_VERSION,
    SITL_TELEMETRY_SCHEMA_VERSION,
    SitlArtifactError,
    SitlArtifactRecorder,
)
from adapters.sitl_evidence import build_sitl_evidence_bundle
from estimator.core.scenario import ScenarioResult, ScenarioStatus
from schemas import (
    SitlAdapterKind,
    SitlEvidenceStatus,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
    VehicleProfile,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VEHICLE_PATH = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"


class SyntheticTelemetryMessage:
    def __init__(self, message_type: str, **fields: object) -> None:
        self._message_type = message_type
        self._fields = fields

    def get_type(self) -> str:
        return self._message_type

    def to_dict(self) -> dict[str, object]:
        return dict(self._fields)


class MalformedTelemetryMessage:
    def get_type(self) -> str:
        return "GLOBAL_POSITION_INT"


class NonMappingTelemetryMessage:
    def get_type(self) -> str:
        return "GLOBAL_POSITION_INT"

    def to_dict(self) -> list[int]:
        return [1, 2, 3]


class RaisingTelemetryMessage:
    def get_type(self) -> str:
        return "GLOBAL_POSITION_INT"

    def to_dict(self) -> dict[str, object]:
        raise ValueError("synthetic conversion failure")


@dataclass(frozen=True)
class CompletedEvidenceAdapter:
    observed: SitlObservedArtifacts

    adapter_id: str = "test-ardupilot"
    adapter_kind: SitlAdapterKind = SitlAdapterKind.ARDUPILOT
    adapter_version: str = "0.1.0"

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode="live_sitl",
            simulator_name="ArduPilot SITL",
            simulator_version=None,
            autopilot=vehicle.autopilot.value,
            frame=vehicle.sitl.frame if vehicle.sitl is not None else None,
            metadata={"connected": True},
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        return self.observed


def _document(name: str) -> InputDocument:
    return InputDocument(
        path=Path(name),
        format="yaml",
        sha256="0" * 64,
    )


def _scenario_envelope() -> ScenarioResultEnvelope:
    return build_scenario_envelope(
        result=ScenarioResult(
            scenario_id="sitl-artifact-test",
            status=ScenarioStatus.PASSED,
        ),
        scenario_document=_document("scenario.yaml"),
        mission_document=_document("mission.yaml"),
        vehicle_document=_document("vehicle.yaml"),
    )


def _vehicle() -> VehicleProfile:
    vehicle, _document = load_vehicle(VEHICLE_PATH)
    return vehicle


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sitl_artifact_recorder_writes_deterministic_artifacts(tmp_path: Path) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)
    recorder.record_telemetry_message(
        1.25,
        SyntheticTelemetryMessage(
            "GLOBAL_POSITION_INT",
            lat=523456789,
            lon=41234567,
            relative_alt=12000,
        ),
    )
    recorder.record_command(1.5, "MISSION_COUNT", {"item_count": 3})
    recorder.record_simulator_event(1.75, "connected", {"target_system": 1})
    recorder.record_adapter_event(2.0, "mission_uploaded", {"item_count": 3})

    first = recorder.write()
    second = recorder.write()

    assert first == second
    telemetry = json.loads((tmp_path / "telemetry.json").read_text(encoding="utf-8"))
    command_log = json.loads(
        (tmp_path / "command_log.json").read_text(encoding="utf-8")
    )
    assert telemetry["schema_version"] == SITL_TELEMETRY_SCHEMA_VERSION
    assert telemetry["records"][0]["message_type"] == "GLOBAL_POSITION_INT"
    assert command_log["schema_version"] == SITL_COMMAND_LOG_SCHEMA_VERSION
    assert command_log["commands"][0]["command"] == "MISSION_COUNT"
    assert first.telemetry[0].sha256 is not None
    assert first.command_logs[0].sha256 is not None


def test_sitl_artifact_recorder_write_without_records_returns_empty_observed(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)

    observed = recorder.write()

    assert observed == SitlObservedArtifacts()
    assert list(tmp_path.iterdir()) == []


def test_sitl_artifact_recorder_rewrites_after_mutation_and_refreshes_hashes(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)
    recorder.record_telemetry_message(
        1.0,
        SyntheticTelemetryMessage("HEARTBEAT", system_status=4),
    )
    observed = recorder.write()
    telemetry_path = Path(observed.telemetry[0].path)
    original_hash = observed.telemetry[0].sha256

    recorder.record_telemetry_message(
        2.0,
        SyntheticTelemetryMessage("MISSION_CURRENT", seq=1),
    )
    rewritten = recorder.write()

    assert rewritten is observed
    assert rewritten.telemetry[0].sha256 == _sha256(telemetry_path)
    assert rewritten.telemetry[0].sha256 != original_hash
    records = json.loads(telemetry_path.read_text(encoding="utf-8"))["records"]
    assert [record["message_type"] for record in records] == [
        "HEARTBEAT",
        "MISSION_CURRENT",
    ]


def test_malformed_telemetry_raises_explicit_artifact_error(tmp_path: Path) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)

    with pytest.raises(SitlArtifactError, match="replayable fields"):
        recorder.record_telemetry_message(1.0, MalformedTelemetryMessage())


def test_non_mapping_telemetry_to_dict_raises_explicit_artifact_error(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)

    with pytest.raises(SitlArtifactError, match=r"to_dict\(\).*list"):
        recorder.record_telemetry_message(1.0, NonMappingTelemetryMessage())


def test_telemetry_to_dict_exception_is_wrapped_as_artifact_error(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)

    with pytest.raises(SitlArtifactError, match="synthetic conversion failure"):
        recorder.record_telemetry_message(1.0, RaisingTelemetryMessage())


def test_non_finite_artifact_value_raises_explicit_artifact_error(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)

    with pytest.raises(SitlArtifactError, match="not finite: nan"):
        recorder.record_telemetry_message(
            1.0,
            SyntheticTelemetryMessage("HEARTBEAT", value=float("nan")),
        )


def test_artifact_write_fails_when_artifact_dir_is_not_directory(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact-dir"
    artifact_dir.write_text("not a directory", encoding="utf-8")
    recorder = SitlArtifactRecorder(artifact_dir=artifact_dir)

    with pytest.raises(FileExistsError):
        recorder.write()


def test_build_sitl_evidence_bundle_completed_with_observed_artifacts(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)
    recorder.record_telemetry_message(
        1.0,
        SyntheticTelemetryMessage("HEARTBEAT", system_status=4),
    )
    observed = recorder.write()

    bundle = build_sitl_evidence_bundle(
        evidence_id="sitl-completed",
        scenario_envelope=_scenario_envelope(),
        scenario_document=_document("scenario.yaml"),
        mission_document=_document("mission.yaml"),
        vehicle_document=_document("vehicle.yaml"),
        uncertainty_document=_document("uncertainty.yaml"),
        vehicle=_vehicle(),
        adapter=CompletedEvidenceAdapter(observed),
    )

    assert bundle.status == SitlEvidenceStatus.COMPLETED
    assert bundle.metadata["contract_only"] is False
    assert bundle.observed.telemetry[0].schema_version == SITL_TELEMETRY_SCHEMA_VERSION
    assert {artifact.role for artifact in bundle.inputs} >= {"uncertainty"}


def test_build_sitl_evidence_bundle_without_telemetry_remains_contract_only(
    tmp_path: Path,
) -> None:
    recorder = SitlArtifactRecorder(artifact_dir=tmp_path)
    recorder.record_command(1.0, "MISSION_COUNT", {"item_count": 1})
    observed = recorder.write()

    bundle = build_sitl_evidence_bundle(
        evidence_id="sitl-command-only",
        scenario_envelope=_scenario_envelope(),
        scenario_document=_document("scenario.yaml"),
        mission_document=_document("mission.yaml"),
        vehicle_document=_document("vehicle.yaml"),
        vehicle=_vehicle(),
        adapter=CompletedEvidenceAdapter(observed),
    )

    assert bundle.status == SitlEvidenceStatus.CONTRACT_ONLY
    assert bundle.metadata["contract_only"] is True
    assert bundle.observed.command_logs
