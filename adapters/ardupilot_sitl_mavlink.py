"""MAVLink-shaped helpers for the ArduPilot SITL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeVar, cast

from adapters.ardupilot_sitl_types import ArduPilotAdapterError

MAV_MISSION_ACCEPTED = 0
MAV_MISSION_TYPE_MISSION = 0
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_CMD_COMPONENT_ARM_DISARM = 400

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

_T = TypeVar("_T")


class MavSender(Protocol):
    def mission_count_send(self, *args: object) -> None: ...

    def mission_item_int_send(self, *args: object) -> None: ...

    def command_long_send(self, *args: object) -> None: ...

    def set_mode_send(self, *args: object) -> None: ...


class MavConnection(Protocol):
    mav: MavSender
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


class MavutilModule(Protocol):
    mavlink: object

    def mavlink_connection(
        self,
        device: str,
        *,
        autoreconnect: bool,
    ) -> MavConnection: ...


def message_type(message: object) -> str | None:
    get_type = getattr(message, "get_type", None)
    if callable(get_type):
        value = get_type()
        if isinstance(value, str):
            return value

    value = getattr(message, "message_type", None)
    if isinstance(value, str):
        return value
    return None


def message_sequence(message: object) -> int:
    try:
        return int(getattr(message, "seq"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ArduPilotAdapterError(
            "MAVLink mission request did not include seq"
        ) from exc


def raise_for_rejected_mission_ack(message: object, mavlink: object) -> None:
    ack_type = _mission_ack_type(message)
    if ack_type == mission_accepted(mavlink):
        return
    raise ArduPilotAdapterError(
        f"ArduPilot rejected mission upload with ACK type {ack_type}",
    )


def is_mission_item_request(received_message_type: str | None) -> bool:
    return received_message_type in {"MISSION_REQUEST_INT", "MISSION_REQUEST"}


def item_at_sequence(items: Sequence[_T], sequence: int) -> _T:
    try:
        return items[sequence]
    except IndexError as exc:
        raise ArduPilotAdapterError(
            f"ArduPilot requested invalid mission item sequence {sequence}",
        ) from exc


def mission_current_reached(message: object | None, final_sequence: int) -> bool:
    if message is None:
        return False
    if message_type(message) != "MISSION_CURRENT":
        return False
    return message_sequence(message) >= final_sequence


def send_arm_command(connection: MavConnection, mavlink: object) -> None:
    connection.mav.command_long_send(
        connection.target_system,
        connection.target_component,
        arm_command(mavlink),
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def wait_for_armed_state_if_supported(
    connection: MavConnection,
    timeout_s: float,
) -> None:
    wait_for_arm = getattr(connection, "motors_armed_wait", None)
    if callable(wait_for_arm):
        wait_for_arm(timeout=timeout_s)


def set_auto_mode(connection: MavConnection, mavlink: object) -> None:
    if _connection_set_mode(connection, AUTO_MODE):
        return

    modes = _connection_mode_mapping(connection)
    connection.mav.set_mode_send(
        connection.target_system,
        auto_mode_flag(mavlink),
        modes[AUTO_MODE],
    )


def mission_type(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MISSION_TYPE_MISSION",
        MAV_MISSION_TYPE_MISSION,
    )


def mission_accepted(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MISSION_ACCEPTED",
        MAV_MISSION_ACCEPTED,
    )


def arm_command(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_CMD_COMPONENT_ARM_DISARM",
        MAV_CMD_COMPONENT_ARM_DISARM,
    )


def auto_mode_flag(mavlink: object) -> int:
    return _mavlink_constant(
        mavlink,
        "MAV_MODE_FLAG_CUSTOM_MODE_ENABLED",
        MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    )


def _mission_ack_type(message: object) -> int:
    try:
        return int(getattr(message, "type"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ArduPilotAdapterError("MAVLink mission ACK did not include type") from exc


def _connection_set_mode(connection: MavConnection, mode: str) -> bool:
    set_mode = getattr(connection, "set_mode", None)
    if not callable(set_mode):
        return False
    set_mode(mode)
    return True


def _connection_mode_mapping(connection: MavConnection) -> Mapping[str, int]:
    mode_mapping = getattr(connection, "mode_mapping", None)
    if not callable(mode_mapping):
        raise ArduPilotAdapterError("ArduPilot connection does not expose AUTO mode")

    modes = mode_mapping()
    if not isinstance(modes, Mapping) or AUTO_MODE not in modes:
        raise ArduPilotAdapterError("ArduPilot connection does not support AUTO mode")
    return cast(Mapping[str, int], modes)


def _mavlink_constant(mavlink: object, name: str, default: int) -> int:
    return int(getattr(mavlink, name, default))


__all__ = [
    "MISSION_UPLOAD_MESSAGE_TYPES",
    "RUN_STATE_MESSAGE_TYPES",
    "MavConnection",
    "MavSender",
    "MavutilModule",
    "is_mission_item_request",
    "item_at_sequence",
    "message_sequence",
    "message_type",
    "mission_current_reached",
    "mission_type",
    "raise_for_rejected_mission_ack",
    "send_arm_command",
    "set_auto_mode",
    "wait_for_armed_state_if_supported",
]
