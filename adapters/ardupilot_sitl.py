"""Connect-only ArduPilot SITL adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Any, ClassVar

from schemas.mission import AltitudeReference, MissionAction, MissionPlan, RouteItem
from schemas.sitl import (
    SitlAdapterKind,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)
from schemas.vehicle import VehicleProfile


MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_TIME = 19
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_NAV_VTOL_TAKEOFF = 84

MAV_FRAME_GLOBAL = 0
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_FRAME_GLOBAL_TERRAIN_ALT = 10

MISSION_ACTION_TO_MAVLINK_CMD = {
    MissionAction.TAKEOFF: MAV_CMD_NAV_TAKEOFF,
    MissionAction.VTOL_TAKEOFF: MAV_CMD_NAV_VTOL_TAKEOFF,
    MissionAction.WAYPOINT: MAV_CMD_NAV_WAYPOINT,
    MissionAction.LOITER_TIME: MAV_CMD_NAV_LOITER_TIME,
    MissionAction.LAND: MAV_CMD_NAV_LAND,
    MissionAction.RTL: MAV_CMD_NAV_RETURN_TO_LAUNCH,
}

ALTITUDE_REFERENCE_TO_MAVLINK_FRAME = {
    AltitudeReference.RELATIVE_HOME: MAV_FRAME_GLOBAL_RELATIVE_ALT,
    AltitudeReference.AMSL: MAV_FRAME_GLOBAL,
    AltitudeReference.TERRAIN: MAV_FRAME_GLOBAL_TERRAIN_ALT,
}


@dataclass(frozen=True)
class ArduPilotSitlConfig:
    host: str = "127.0.0.1"
    port: int = 5760
    connection_timeout_s: float = 30.0
    mission_upload_timeout_s: float = 60.0
    arm_timeout_s: float = 30.0


@dataclass(frozen=True)
class MissionUploadResult:
    item_count: int
    acknowledged: bool


class RunState(StrEnum):
    COMPLETE = "complete"
    TIMEOUT = "timeout"
    ERROR = "error"


class ArduPilotAdapterError(RuntimeError):
    pass


@dataclass
class ArduPilotSitlAdapter:
    config: ArduPilotSitlConfig | None = None

    adapter_id: ClassVar[str] = "ardupilot-sitl-v1"
    adapter_kind: ClassVar[SitlAdapterKind] = SitlAdapterKind.ARDUPILOT
    adapter_version: ClassVar[str] = "0.1.0"

    _connection: Any = field(init=False, default=None, repr=False)
    _heartbeat: Any = field(init=False, default=None, repr=False)
    _mission_item_count: int | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = ArduPilotSitlConfig()

    def connect(self) -> None:
        mavutil = self._mavutil()
        connection_string = f"tcp:{self.config.host}:{self.config.port}"
        connection = mavutil.mavlink_connection(
            connection_string,
            autoreconnect=False,
        )
        heartbeat = connection.wait_heartbeat(
            timeout=self.config.connection_timeout_s,
        )
        if heartbeat is None:
            raise ArduPilotAdapterError(
                f"Timed out waiting for ArduPilot heartbeat on {connection_string}",
            )
        self._connection = connection
        self._heartbeat = heartbeat

    def upload_mission(self, mission: MissionPlan) -> MissionUploadResult:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        items = [
            _build_mission_item(
                route_item,
                mission.defaults.altitude_reference,
            )
            for route_item in mission.route
        ]

        self._send_mission_count(connection, mavlink, len(items))
        deadline = monotonic() + self.config.mission_upload_timeout_s

        while monotonic() < deadline:
            message = connection.recv_match(
                type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"],
                blocking=True,
                timeout=max(0.0, deadline - monotonic()),
            )
            if message is None:
                continue

            message_type = _message_type(message)
            if message_type == "MISSION_ACK":
                acknowledged = _mission_ack_accepted(message, mavlink)
                if not acknowledged:
                    raise ArduPilotAdapterError(
                        f"ArduPilot rejected mission upload with ACK type {message.type}",
                    )
                self._mission_item_count = len(items)
                return MissionUploadResult(
                    item_count=len(items),
                    acknowledged=True,
                )

            if message_type in {"MISSION_REQUEST_INT", "MISSION_REQUEST"}:
                sequence = int(message.seq)
                try:
                    item = items[sequence]
                except IndexError as exc:
                    raise ArduPilotAdapterError(
                        f"ArduPilot requested invalid mission item sequence {sequence}",
                    ) from exc
                self._send_mission_item_int(connection, mavlink, sequence, item)

        raise ArduPilotAdapterError(
            f"Timed out uploading {len(items)} mission items to ArduPilot SITL",
        )

    def arm_and_start(self) -> None:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        connection.mav.command_long_send(
            connection.target_system,
            connection.target_component,
            getattr(mavlink, "MAV_CMD_COMPONENT_ARM_DISARM", 400),
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        motors_armed_wait = getattr(connection, "motors_armed_wait", None)
        if motors_armed_wait is not None:
            motors_armed_wait(timeout=self.config.arm_timeout_s)
        _set_auto_mode(connection, mavlink)

    def wait_for_mission_complete(self, timeout_s: float = 300.0) -> RunState:
        connection = self._require_connection()
        if self._mission_item_count is None:
            return RunState.ERROR

        final_sequence = max(0, self._mission_item_count - 1)
        deadline = monotonic() + timeout_s
        try:
            while monotonic() < deadline:
                message = connection.recv_match(
                    type=["MISSION_CURRENT", "HEARTBEAT"],
                    blocking=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                if _message_type(message) == "MISSION_CURRENT":
                    if int(message.seq) >= final_sequence:
                        return RunState.COMPLETE
            return RunState.TIMEOUT
        except Exception:
            return RunState.ERROR

    def disconnect(self) -> None:
        if self._connection is not None:
            close = getattr(self._connection, "close", None)
            if close is not None:
                close()
        self._connection = None
        self._heartbeat = None

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        connected = self._connection is not None
        frame = vehicle.sitl.frame if vehicle.sitl is not None else None
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode="live_sitl" if connected else "connect_only",
            simulator_name="ArduPilot SITL",
            simulator_version=None,
            autopilot=vehicle.autopilot.value if vehicle.autopilot is not None else None,
            frame=frame,
            metadata={
                "host": self.config.host,
                "port": self.config.port,
                "connected": connected,
                "target_system": getattr(self._connection, "target_system", None),
                "target_component": getattr(
                    self._connection,
                    "target_component",
                    None,
                ),
            },
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        return SitlObservedArtifacts()

    def _mavutil(self) -> Any:
        try:
            from pymavlink import mavutil

            return mavutil
        except ImportError as exc:
            raise ArduPilotAdapterError(
                "pymavlink is required for the ArduPilot SITL adapter. "
                "Install it with: pip install pymavlink",
            ) from exc

    def _require_connection(self) -> Any:
        if self._connection is None:
            raise ArduPilotAdapterError("ArduPilot SITL is not connected")
        return self._connection

    def _send_mission_count(
        self,
        connection: Any,
        mavlink: Any,
        item_count: int,
    ) -> None:
        mission_type = getattr(mavlink, "MAV_MISSION_TYPE_MISSION", 0)
        try:
            connection.mav.mission_count_send(
                connection.target_system,
                connection.target_component,
                item_count,
                mission_type,
            )
        except TypeError:
            connection.mav.mission_count_send(
                connection.target_system,
                connection.target_component,
                item_count,
            )

    def _send_mission_item_int(
        self,
        connection: Any,
        mavlink: Any,
        sequence: int,
        item: "_MissionItem",
    ) -> None:
        mission_type = getattr(mavlink, "MAV_MISSION_TYPE_MISSION", 0)
        args = (
            connection.target_system,
            connection.target_component,
            sequence,
            item.frame,
            item.command,
            1 if sequence == 0 else 0,
            1,
            item.param1,
            item.param2,
            item.param3,
            item.param4,
            item.latitude_int,
            item.longitude_int,
            item.altitude_m,
        )
        try:
            connection.mav.mission_item_int_send(*args, mission_type)
        except TypeError:
            connection.mav.mission_item_int_send(*args)


@dataclass(frozen=True)
class _MissionItem:
    command: int
    frame: int
    latitude_int: int
    longitude_int: int
    altitude_m: float
    param1: float = 0.0
    param2: float = 0.0
    param3: float = 0.0
    param4: float = 0.0


def mission_action_to_mavlink_cmd(action: MissionAction) -> int:
    try:
        return MISSION_ACTION_TO_MAVLINK_CMD[action]
    except KeyError as exc:
        raise ArduPilotAdapterError(
            f"Unsupported mission action for ArduPilot SITL: {action}",
        ) from exc


def altitude_reference_to_mavlink_frame(reference: AltitudeReference) -> int:
    try:
        return ALTITUDE_REFERENCE_TO_MAVLINK_FRAME[reference]
    except KeyError as exc:
        raise ArduPilotAdapterError(
            f"Unsupported altitude reference for ArduPilot SITL: {reference}",
        ) from exc


def _build_mission_item(
    route_item: RouteItem,
    default_altitude_reference: AltitudeReference,
) -> _MissionItem:
    altitude_reference = (
        route_item.altitude_reference
        if route_item.altitude_reference is not None
        else default_altitude_reference
    )
    latitude = 0.0 if route_item.lat is None else route_item.lat
    longitude = 0.0 if route_item.lon is None else route_item.lon
    altitude_m = 0.0 if route_item.altitude_m is None else route_item.altitude_m
    return _MissionItem(
        command=mission_action_to_mavlink_cmd(route_item.action),
        frame=altitude_reference_to_mavlink_frame(altitude_reference),
        latitude_int=round(latitude * 10_000_000),
        longitude_int=round(longitude * 10_000_000),
        altitude_m=altitude_m,
        param1=0.0 if route_item.loiter_time_s is None else route_item.loiter_time_s,
        param2=(
            0.0
            if route_item.acceptance_radius_m is None
            else route_item.acceptance_radius_m
        ),
    )


def _message_type(message: Any) -> str | None:
    get_type = getattr(message, "get_type", None)
    if get_type is not None:
        return get_type()
    return getattr(message, "message_type", None)


def _mission_ack_accepted(message: Any, mavlink: Any) -> bool:
    accepted_type = getattr(mavlink, "MAV_MISSION_ACCEPTED", 0)
    return int(message.type) == accepted_type


def _set_auto_mode(connection: Any, mavlink: Any) -> None:
    set_mode = getattr(connection, "set_mode", None)
    if set_mode is not None:
        set_mode("AUTO")
        return

    mode_mapping = getattr(connection, "mode_mapping", None)
    if mode_mapping is None:
        raise ArduPilotAdapterError("ArduPilot connection does not expose AUTO mode")

    modes = mode_mapping()
    if "AUTO" not in modes:
        raise ArduPilotAdapterError("ArduPilot connection does not support AUTO mode")

    connection.mav.set_mode_send(
        connection.target_system,
        getattr(mavlink, "MAV_MODE_FLAG_CUSTOM_MODE_ENABLED", 1),
        modes["AUTO"],
    )


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
