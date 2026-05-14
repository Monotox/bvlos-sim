"""Connect-only ArduPilot SITL adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import ClassVar, cast

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

    def __init__(self, config: ArduPilotSitlConfig | None = None) -> None:
        self.config = config or ArduPilotSitlConfig()
        self._connection = None
        self._heartbeat = None
        self._mission_item_count = None

    def connect(self) -> None:
        connection_string = self._connection_string()
        connection = self._open_connection(connection_string)
        heartbeat = self._wait_for_heartbeat(connection, connection_string)
        self._connection = connection
        self._heartbeat = heartbeat

    def upload_mission(self, mission: MissionPlan) -> MissionUploadResult:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        items = build_mission_items(cast(MissionLike, mission))

        MissionUploadProtocol(
            timeout_s=self.config.mission_upload_timeout_s,
        ).upload(connection, mavlink, items)
        self._mission_item_count = len(items)
        return MissionUploadResult(item_count=len(items), acknowledged=True)

    def arm_and_start(self) -> None:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        send_arm_command(connection, mavlink)
        wait_for_armed_state_if_supported(connection, self.config.arm_timeout_s)
        set_auto_mode(connection, mavlink)

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
        connection.close()

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        connection = self._connection
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode="live_sitl" if connection is not None else "connect_only",
            simulator_name="ArduPilot SITL",
            simulator_version=None,
            autopilot=_vehicle_autopilot(vehicle),
            frame=_vehicle_frame(vehicle),
            metadata=_connection_metadata(self.config, connection),
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        return SitlObservedArtifacts()

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
