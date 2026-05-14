"""Connect-only ArduPilot SITL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import ClassVar, Protocol, cast

from schemas.mission import AltitudeReference, MissionAction, MissionPlan
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

MAV_MISSION_ACCEPTED = 0
MAV_MISSION_TYPE_MISSION = 0
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_CMD_COMPONENT_ARM_DISARM = 400

COORDINATE_SCALE = 10_000_000
AUTO_MODE = "AUTO"
MISSION_UPLOAD_MESSAGE_TYPES = (
    "MISSION_REQUEST_INT",
    "MISSION_REQUEST",
    "MISSION_ACK",
)
RUN_STATE_MESSAGE_TYPES = (
    "MISSION_CURRENT",
    "HEARTBEAT",
)

MISSION_ACTION_TO_MAVLINK_CMD: Mapping[MissionAction, int] = {
    MissionAction.TAKEOFF: MAV_CMD_NAV_TAKEOFF,
    MissionAction.VTOL_TAKEOFF: MAV_CMD_NAV_VTOL_TAKEOFF,
    MissionAction.WAYPOINT: MAV_CMD_NAV_WAYPOINT,
    MissionAction.LOITER_TIME: MAV_CMD_NAV_LOITER_TIME,
    MissionAction.LAND: MAV_CMD_NAV_LAND,
    MissionAction.RTL: MAV_CMD_NAV_RETURN_TO_LAUNCH,
}

ALTITUDE_REFERENCE_TO_MAVLINK_FRAME: Mapping[AltitudeReference, int] = {
    AltitudeReference.RELATIVE_HOME: MAV_FRAME_GLOBAL_RELATIVE_ALT,
    AltitudeReference.AMSL: MAV_FRAME_GLOBAL,
    AltitudeReference.TERRAIN: MAV_FRAME_GLOBAL_TERRAIN_ALT,
}


class _MavSender(Protocol):
    def mission_count_send(self, *args: object) -> None: ...

    def mission_item_int_send(self, *args: object) -> None: ...

    def command_long_send(self, *args: object) -> None: ...

    def set_mode_send(self, *args: object) -> None: ...


class _MavConnection(Protocol):
    mav: _MavSender
    target_system: int
    target_component: int

    def wait_heartbeat(self, timeout: float) -> object | None: ...

    def recv_match(
        self,
        *,
        type: str | Sequence[str],
        blocking: bool,
        timeout: float,
    ) -> object | None: ...

    def close(self) -> None: ...


class _MavutilModule(Protocol):
    mavlink: object

    def mavlink_connection(
        self,
        device: str,
        *,
        autoreconnect: bool,
    ) -> _MavConnection: ...


class _MissionDefaultsLike(Protocol):
    altitude_reference: object


class _MissionRouteItemLike(Protocol):
    action: object
    lat: float | None
    lon: float | None
    altitude_m: float | None
    altitude_reference: object | None
    loiter_time_s: float | None
    acceptance_radius_m: float | None


class _MissionLike(Protocol):
    defaults: _MissionDefaultsLike
    route: Sequence[_MissionRouteItemLike]


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


@dataclass(init=False)
class ArduPilotSitlAdapter:
    config: ArduPilotSitlConfig = field(init=False)

    adapter_id: ClassVar[str] = "ardupilot-sitl-v1"
    adapter_kind: ClassVar[SitlAdapterKind] = SitlAdapterKind.ARDUPILOT
    adapter_version: ClassVar[str] = "0.1.0"

    _connection: _MavConnection | None = field(init=False, default=None, repr=False)
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
        items = _build_mission_items(cast(_MissionLike, mission))

        self._send_mission_count(connection, mavlink, len(items))
        self._complete_mission_upload(connection, mavlink, items)
        self._mission_item_count = len(items)
        return MissionUploadResult(item_count=len(items), acknowledged=True)

    def arm_and_start(self) -> None:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        self._send_arm_command(connection, mavlink)
        self._wait_for_armed_state_if_supported(connection)
        self._set_auto_mode(connection, mavlink)

    def wait_for_mission_complete(self, timeout_s: float = 300.0) -> RunState:
        connection = self._require_connection()
        if self._mission_item_count is None:
            return RunState.ERROR

        deadline = monotonic() + timeout_s
        final_sequence = max(0, self._mission_item_count - 1)
        while monotonic() < deadline:
            try:
                message = self._receive_run_state_message(connection)
                if _mission_current_reached(message, final_sequence):
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

    def _mavutil(self) -> _MavutilModule:
        try:
            from pymavlink import mavutil

            return cast(_MavutilModule, mavutil)
        except ImportError as exc:
            raise ArduPilotAdapterError(
                "pymavlink is required for the ArduPilot SITL adapter. "
                "Install it with: pip install pymavlink",
            ) from exc

    def _connection_string(self) -> str:
        return f"tcp:{self.config.host}:{self.config.port}"

    def _open_connection(self, connection_string: str) -> _MavConnection:
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
        connection: _MavConnection,
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

    def _require_connection(self) -> _MavConnection:
        if self._connection is None:
            raise ArduPilotAdapterError("ArduPilot SITL is not connected")
        return self._connection

    def _send_mission_count(
        self,
        connection: _MavConnection,
        mavlink: object,
        item_count: int,
    ) -> None:
        connection.mav.mission_count_send(
            connection.target_system,
            connection.target_component,
            item_count,
            _mission_type(mavlink),
        )

    def _complete_mission_upload(
        self,
        connection: _MavConnection,
        mavlink: object,
        items: Sequence["_MissionItem"],
    ) -> None:
        deadline = monotonic() + self.config.mission_upload_timeout_s
        while monotonic() < deadline:
            message = self._receive_upload_message(connection, deadline)
            if message is None:
                continue

            message_type = _message_type(message)
            if message_type == "MISSION_ACK":
                _raise_for_rejected_mission_ack(message, mavlink)
                return
            if _is_mission_item_request(message_type):
                self._send_requested_mission_item(connection, mavlink, message, items)
                continue
            raise ArduPilotAdapterError(
                f"Unexpected ArduPilot mission upload message: {message_type}",
            )

        raise ArduPilotAdapterError(
            f"Timed out uploading {len(items)} mission items to ArduPilot SITL",
        )

    def _receive_upload_message(
        self,
        connection: _MavConnection,
        deadline: float,
    ) -> object | None:
        return connection.recv_match(
            type=list(MISSION_UPLOAD_MESSAGE_TYPES),
            blocking=True,
            timeout=max(0.0, deadline - monotonic()),
        )

    def _send_requested_mission_item(
        self,
        connection: _MavConnection,
        mavlink: object,
        request: object,
        items: Sequence["_MissionItem"],
    ) -> None:
        sequence = _message_sequence(request)
        item = _mission_item_at_sequence(items, sequence)
        self._send_mission_item_int(connection, mavlink, sequence, item)

    def _send_mission_item_int(
        self,
        connection: _MavConnection,
        mavlink: object,
        sequence: int,
        item: "_MissionItem",
    ) -> None:
        connection.mav.mission_item_int_send(
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
            _mission_type(mavlink),
        )

    def _send_arm_command(
        self,
        connection: _MavConnection,
        mavlink: object,
    ) -> None:
        connection.mav.command_long_send(
            connection.target_system,
            connection.target_component,
            _arm_command(mavlink),
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
        )

    def _wait_for_armed_state_if_supported(self, connection: _MavConnection) -> None:
        wait_for_arm = getattr(connection, "motors_armed_wait", None)
        if callable(wait_for_arm):
            wait_for_arm(timeout=self.config.arm_timeout_s)

    def _set_auto_mode(self, connection: _MavConnection, mavlink: object) -> None:
        if _connection_set_mode(connection, AUTO_MODE):
            return

        modes = _connection_mode_mapping(connection)
        connection.mav.set_mode_send(
            connection.target_system,
            _auto_mode_flag(mavlink),
            modes[AUTO_MODE],
        )

    def _receive_run_state_message(
        self,
        connection: _MavConnection,
    ) -> object | None:
        return connection.recv_match(
            type=list(RUN_STATE_MESSAGE_TYPES),
            blocking=True,
            timeout=1.0,
        )


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


def mission_action_to_mavlink_cmd(action: object) -> int:
    mission_action = _coerce_mission_action(action)
    return MISSION_ACTION_TO_MAVLINK_CMD[mission_action]


def altitude_reference_to_mavlink_frame(reference: object) -> int:
    altitude_reference = _coerce_altitude_reference(reference)
    return ALTITUDE_REFERENCE_TO_MAVLINK_FRAME[altitude_reference]


def _build_mission_items(mission: _MissionLike) -> tuple[_MissionItem, ...]:
    default_altitude_reference = mission.defaults.altitude_reference
    return tuple(
        _build_mission_item(route_item, default_altitude_reference)
        for route_item in mission.route
    )


def _build_mission_item(
    route_item: _MissionRouteItemLike,
    default_altitude_reference: object,
) -> _MissionItem:
    return _MissionItem(
        command=mission_action_to_mavlink_cmd(route_item.action),
        frame=altitude_reference_to_mavlink_frame(
            _route_altitude_reference(route_item, default_altitude_reference),
        ),
        latitude_int=_coordinate_to_int(_zero_if_none(route_item.lat)),
        longitude_int=_coordinate_to_int(_zero_if_none(route_item.lon)),
        altitude_m=_zero_if_none(route_item.altitude_m),
        param1=_zero_if_none(route_item.loiter_time_s),
        param2=_zero_if_none(route_item.acceptance_radius_m),
    )


def _route_altitude_reference(
    route_item: _MissionRouteItemLike,
    default_altitude_reference: object,
) -> object:
    if route_item.altitude_reference is not None:
        return route_item.altitude_reference
    return default_altitude_reference


def _zero_if_none(value: float | None) -> float:
    if value is None:
        return 0.0
    return value


def _coordinate_to_int(value: float) -> int:
    return round(value * COORDINATE_SCALE)


def _coerce_mission_action(action: object) -> MissionAction:
    if isinstance(action, MissionAction):
        return action
    try:
        return MissionAction(str(action))
    except ValueError as exc:
        raise ArduPilotAdapterError(
            f"Unsupported mission action for ArduPilot SITL: {action}",
        ) from exc


def _coerce_altitude_reference(reference: object) -> AltitudeReference:
    if isinstance(reference, AltitudeReference):
        return reference
    try:
        return AltitudeReference(str(reference))
    except ValueError as exc:
        raise ArduPilotAdapterError(
            f"Unsupported altitude reference for ArduPilot SITL: {reference}",
        ) from exc


def _message_type(message: object) -> str | None:
    get_type = getattr(message, "get_type", None)
    if callable(get_type):
        value = get_type()
        if isinstance(value, str):
            return value

    value = getattr(message, "message_type", None)
    if isinstance(value, str):
        return value
    return None


def _message_sequence(message: object) -> int:
    try:
        return int(getattr(message, "seq"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ArduPilotAdapterError("MAVLink mission request did not include seq") from exc


def _mission_ack_type(message: object) -> int:
    try:
        return int(getattr(message, "type"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ArduPilotAdapterError("MAVLink mission ACK did not include type") from exc


def _raise_for_rejected_mission_ack(message: object, mavlink: object) -> None:
    ack_type = _mission_ack_type(message)
    if ack_type == _mission_accepted(mavlink):
        return
    raise ArduPilotAdapterError(
        f"ArduPilot rejected mission upload with ACK type {ack_type}",
    )


def _is_mission_item_request(message_type: str | None) -> bool:
    return message_type in {"MISSION_REQUEST_INT", "MISSION_REQUEST"}


def _mission_item_at_sequence(
    items: Sequence[_MissionItem],
    sequence: int,
) -> _MissionItem:
    try:
        return items[sequence]
    except IndexError as exc:
        raise ArduPilotAdapterError(
            f"ArduPilot requested invalid mission item sequence {sequence}",
        ) from exc


def _mission_current_reached(message: object | None, final_sequence: int) -> bool:
    if message is None:
        return False
    if _message_type(message) != "MISSION_CURRENT":
        return False
    return _message_sequence(message) >= final_sequence


def _connection_set_mode(connection: _MavConnection, mode: str) -> bool:
    set_mode = getattr(connection, "set_mode", None)
    if not callable(set_mode):
        return False
    set_mode(mode)
    return True


def _connection_mode_mapping(connection: _MavConnection) -> Mapping[str, int]:
    mode_mapping = getattr(connection, "mode_mapping", None)
    if not callable(mode_mapping):
        raise ArduPilotAdapterError("ArduPilot connection does not expose AUTO mode")

    modes = mode_mapping()
    if not isinstance(modes, Mapping) or AUTO_MODE not in modes:
        raise ArduPilotAdapterError("ArduPilot connection does not support AUTO mode")
    return cast(Mapping[str, int], modes)


def _mavlink_constant(mavlink: object, name: str, default: int) -> int:
    return int(getattr(mavlink, name, default))


def _mission_type(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MISSION_TYPE_MISSION",
        MAV_MISSION_TYPE_MISSION,
    )


def _mission_accepted(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MISSION_ACCEPTED",
        MAV_MISSION_ACCEPTED,
    )


def _arm_command(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_CMD_COMPONENT_ARM_DISARM",
        MAV_CMD_COMPONENT_ARM_DISARM,
    )


def _auto_mode_flag(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MODE_FLAG_CUSTOM_MODE_ENABLED",
        MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
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
    connection: _MavConnection | None,
) -> dict[str, str | int | bool | None]:
    return {
        "host": config.host,
        "port": config.port,
        "connected": connection is not None,
        "target_system": _connection_target_system(connection),
        "target_component": _connection_target_component(connection),
    }


def _connection_target_system(connection: _MavConnection | None) -> int | None:
    if connection is None:
        return None
    return connection.target_system


def _connection_target_component(connection: _MavConnection | None) -> int | None:
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
