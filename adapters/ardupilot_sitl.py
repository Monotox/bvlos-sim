"""Connect-only ArduPilot SITL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import ClassVar, cast

from adapters.sitl_artifacts import SitlArtifactRecorder
from adapters.ardupilot_sitl_mavlink import (
    RUN_STATE_MESSAGE_TYPES,
    MavConnection,
    MavutilModule,
    mission_current_reached,
    send_arm_command,
    set_auto_mode,
    wait_for_armed_state_if_supported,
)
from adapters.ardupilot_sitl_mission import (
    ALTITUDE_REFERENCE_TO_MAVLINK_FRAME,
    MISSION_ACTION_TO_MAVLINK_CMD,
    MissionLike,
    altitude_reference_to_mavlink_frame,
    build_mission_items,
    mission_action_to_mavlink_cmd,
)
from adapters.ardupilot_sitl_types import (
    ArduPilotAdapterError,
    ArduPilotSitlConfig,
    MissionUploadResult,
    RunState,
)
from adapters.ardupilot_sitl_upload import MissionUploadProtocol
from schemas.mission import MissionPlan
from schemas.sitl import (
    SitlAdapterKind,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)
from schemas.vehicle import VehicleProfile


@dataclass(init=False)
class ArduPilotSitlAdapter:
    config: ArduPilotSitlConfig = field(init=False)

    adapter_id: ClassVar[str] = "ardupilot-sitl-v1"
    adapter_kind: ClassVar[SitlAdapterKind] = SitlAdapterKind.ARDUPILOT
    adapter_version: ClassVar[str] = "0.1.0"

    _connection: MavConnection | None = field(init=False, default=None, repr=False)
    _heartbeat: object | None = field(init=False, default=None, repr=False)
    _mission_item_count: int | None = field(init=False, default=None, repr=False)
    _artifact_recorder: SitlArtifactRecorder | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def __init__(self, config: ArduPilotSitlConfig | None = None) -> None:
        self.config = config or ArduPilotSitlConfig()
        self._connection = None
        self._heartbeat = None
        self._mission_item_count = None
        self._artifact_recorder = None

    def connect(self) -> None:
        connection_string = self._connection_string()
        connection = self._open_connection(connection_string)
        heartbeat = self._wait_for_heartbeat(connection, connection_string)
        self._connection = connection
        self._heartbeat = heartbeat
        self._record_simulator_event(
            "connected",
            {
                "connection_string": connection_string,
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )

    def upload_mission(self, mission: MissionPlan) -> MissionUploadResult:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        items = build_mission_items(cast(MissionLike, mission))

        MissionUploadProtocol(
            timeout_s=self.config.mission_upload_timeout_s,
            command_recorder=self._record_command,
        ).upload(connection, mavlink, items)
        self._mission_item_count = len(items)
        self._record_adapter_event("mission_uploaded", {"item_count": len(items)})
        return MissionUploadResult(item_count=len(items), acknowledged=True)

    def arm_and_start(self) -> None:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        send_arm_command(connection, mavlink)
        self._record_command(
            "COMMAND_LONG_ARM",
            {
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )
        wait_for_armed_state_if_supported(connection, self.config.arm_timeout_s)
        set_auto_mode(connection, mavlink)
        self._record_command(
            "SET_MODE_AUTO",
            {
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )

    def wait_for_mission_complete(self, timeout_s: float = 300.0) -> RunState:
        connection = self._require_connection()
        if self._mission_item_count is None:
            return RunState.ERROR

        deadline = monotonic() + timeout_s
        final_sequence = max(0, self._mission_item_count - 1)
        while monotonic() < deadline:
            try:
                message = self._receive_run_state_message(connection)
                if mission_current_reached(message, final_sequence):
                    return RunState.COMPLETE
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                return RunState.ERROR
        return RunState.TIMEOUT

    def disconnect(self) -> None:
        connection = self._connection
        self._connection = None
        self._heartbeat = None
        if connection is None:
            return
        artifacts_were_flushed = (
            self._artifact_recorder is not None
            and self._artifact_recorder.observed is not None
        )
        self._record_simulator_event(
            "disconnected",
            {
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )
        connection.close()
        if artifacts_were_flushed and self._artifact_recorder is not None:
            self._artifact_recorder.write()

    def start_recording(self, artifact_dir: Path) -> None:
        self._artifact_recorder = SitlArtifactRecorder(artifact_dir=artifact_dir)
        self._record_adapter_event("adapter_initialized")
        self._record_adapter_event("recording_started", {"artifact_dir": str(artifact_dir)})

    def record_telemetry(
        self,
        *,
        sample_count: int,
        timeout_s: float = 30.0,
        message_types: Sequence[str] = RUN_STATE_MESSAGE_TYPES,
    ) -> SitlObservedArtifacts:
        if sample_count <= 0:
            raise ArduPilotAdapterError("sample_count must be greater than zero")

        connection = self._require_connection()
        recorder = self._require_artifact_recorder()
        for _ in range(sample_count):
            message = connection.recv_match(
                type=list(message_types),
                blocking=True,
                timeout=timeout_s,
            )
            if message is None:
                raise ArduPilotAdapterError("Timed out waiting for SITL telemetry")
            recorder.record_telemetry_message(monotonic(), message)
        return recorder.write()

    def flush_artifacts(self) -> SitlObservedArtifacts:
        return self._require_artifact_recorder().write()

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        connection = self._connection
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode=_execution_mode(connection, self._artifact_recorder),
            simulator_name="ArduPilot SITL",
            simulator_version=None,
            autopilot=_vehicle_autopilot(vehicle),
            frame=_vehicle_frame(vehicle),
            metadata=_connection_metadata(self.config, connection),
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        if self._artifact_recorder is None:
            return SitlObservedArtifacts()
        cached = self._artifact_recorder.observed
        if cached is None:
            return SitlObservedArtifacts()
        return cached

    def _mavutil(self) -> MavutilModule:
        try:
            from pymavlink import mavutil

            return cast(MavutilModule, mavutil)
        except ImportError as exc:
            raise ArduPilotAdapterError(
                "pymavlink is required for the ArduPilot SITL adapter. "
                "Install it with: pip install pymavlink",
            ) from exc

    def _connection_string(self) -> str:
        return f"tcp:{self.config.host}:{self.config.port}"

    def _open_connection(self, connection_string: str) -> MavConnection:
        try:
            return self._mavutil().mavlink_connection(
                connection_string,
                autoreconnect=False,
            )
        except OSError as exc:
            raise ArduPilotAdapterError(
                f"Could not connect to ArduPilot SITL at {connection_string}",
            ) from exc

    def _wait_for_heartbeat(
        self,
        connection: MavConnection,
        connection_string: str,
    ) -> object:
        heartbeat = connection.wait_heartbeat(
            timeout=self.config.connection_timeout_s,
        )
        if heartbeat is None:
            raise ArduPilotAdapterError(
                f"Timed out waiting for ArduPilot heartbeat on {connection_string}",
            )
        return heartbeat

    def _require_connection(self) -> MavConnection:
        if self._connection is None:
            raise ArduPilotAdapterError("ArduPilot SITL is not connected")
        return self._connection

    def _receive_run_state_message(
        self,
        connection: MavConnection,
    ) -> object | None:
        return connection.recv_match(
            type=list(RUN_STATE_MESSAGE_TYPES),
            blocking=True,
            timeout=1.0,
        )

    def _require_artifact_recorder(self) -> SitlArtifactRecorder:
        if self._artifact_recorder is None:
            raise ArduPilotAdapterError("SITL artifact recording is not configured")
        return self._artifact_recorder

    def _record_command(self, command: str, fields: Mapping[str, object]) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_command(monotonic(), command, fields)

    def _record_simulator_event(
        self,
        event: str,
        fields: Mapping[str, object],
    ) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_simulator_event(monotonic(), event, fields)

    def _record_adapter_event(
        self,
        event: str,
        fields: Mapping[str, object] | None = None,
    ) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_adapter_event(monotonic(), event, fields or {})

def _vehicle_autopilot(vehicle: VehicleProfile) -> str | None:
    if vehicle.autopilot is None:
        return None
    return vehicle.autopilot.value


def _vehicle_frame(vehicle: VehicleProfile) -> str | None:
    if vehicle.sitl is None:
        return None
    return vehicle.sitl.frame


def _connection_metadata(
    config: ArduPilotSitlConfig,
    connection: MavConnection | None,
) -> dict[str, str | int | bool | None]:
    return {
        "host": config.host,
        "port": config.port,
        "connected": connection is not None,
        "target_system": _connection_target_system(connection),
        "target_component": _connection_target_component(connection),
    }


def _execution_mode(
    connection: MavConnection | None,
    recorder: SitlArtifactRecorder | None,
) -> str:
    if connection is not None:
        return "live_sitl"
    if recorder is not None and recorder.observed is not None:
        return "live_sitl"
    return "connect_only"


def _connection_target_system(connection: MavConnection | None) -> int | None:
    if connection is None:
        return None
    return connection.target_system


def _connection_target_component(connection: MavConnection | None) -> int | None:
    if connection is None:
        return None
    return connection.target_component


__all__ = [
    "ALTITUDE_REFERENCE_TO_MAVLINK_FRAME",
    "MISSION_ACTION_TO_MAVLINK_CMD",
    "ArduPilotAdapterError",
    "ArduPilotSitlAdapter",
    "ArduPilotSitlConfig",
    "MissionUploadResult",
    "RunState",
    "altitude_reference_to_mavlink_frame",
    "mission_action_to_mavlink_cmd",
]
