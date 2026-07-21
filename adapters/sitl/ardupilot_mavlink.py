"""MAVLink-shaped helpers for the ArduPilot SITL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import monotonic
from typing import Protocol, TypeVar, cast

from adapters.sitl.ardupilot_types import ArduPilotAdapterError

MAV_MISSION_ACCEPTED = 0
MAV_MISSION_TYPE_MISSION = 0
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_MODE_FLAG_SAFETY_ARMED = 128
MAV_CMD_COMPONENT_ARM_DISARM = 400

AUTO_MODE = "AUTO"
MISSION_UPLOAD_MESSAGE_TYPES = (
    "MISSION_REQUEST_INT",
    "MISSION_REQUEST",
    "MISSION_ACK",
)
RUN_STATE_MESSAGE_TYPES = (
    "MISSION_CURRENT",
    "MISSION_ITEM_REACHED",
    "HEARTBEAT",
    "GLOBAL_POSITION_INT",
)
MISSION_STATE_COMPLETE = 5
MISSION_STATE_UNKNOWN = 0
MISSION_STATE_ACTIVE = 3

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


def mission_execution_complete(
    message: object | None,
    *,
    final_sequence: int,
    item_count: int,
) -> bool:
    """Return true only for explicit mission-completion evidence.

    ``MISSION_CURRENT.seq`` identifies the item being executed, so selecting
    the final item is not proof that it finished. MAVLink 2 systems can report
    ``MISSION_STATE_COMPLETE`` on ``MISSION_CURRENT``; older systems report
    final progress with ``MISSION_ITEM_REACHED``. Some stacks advance
    ``MISSION_CURRENT.seq`` one past the final zero-based item on completion.
    """
    if message is None:
        return False
    current_type = message_type(message)
    if current_type == "MISSION_ITEM_REACHED":
        return message_sequence(message) == final_sequence
    if current_type != "MISSION_CURRENT":
        return False

    try:
        mission_state = int(getattr(message, "mission_state"))
    except (AttributeError, TypeError, ValueError):
        mission_state = None
    if mission_state not in (None, MISSION_STATE_UNKNOWN):
        return mission_state == MISSION_STATE_COMPLETE
    return message_sequence(message) == item_count


def mission_execution_progressed(
    message: object | None,
    *,
    final_sequence: int,
    item_count: int,
) -> bool:
    """Return true for non-completion progress attributable to the current run.

    Completion messages can remain queued or arrive late from an earlier AUTO
    run.  A completion is therefore accepted only after a separate, valid
    progress message has been observed after the current run started.
    """
    if message is None:
        return False
    current_type = message_type(message)
    if current_type == "MISSION_ITEM_REACHED":
        sequence = message_sequence(message)
        return 0 <= sequence < final_sequence
    if current_type != "MISSION_CURRENT":
        return False

    sequence = message_sequence(message)
    if not 0 <= sequence < item_count:
        return False
    try:
        mission_state = int(getattr(message, "mission_state"))
    except (AttributeError, TypeError, ValueError):
        mission_state = None
    return mission_state in (None, MISSION_STATE_UNKNOWN, MISSION_STATE_ACTIVE)


def drain_mission_progress_messages(
    connection: MavConnection,
    *,
    max_messages: int = 1_000,
) -> int:
    """Discard queued progress from an earlier run before entering AUTO.

    The bounded loop prevents a continuously publishing endpoint from holding
    mission start forever. A non-empty queue at the limit is treated as an
    adapter error because stale completion evidence could otherwise remain.
    """
    for count in range(max_messages):
        message = connection.recv_match(
            type=["MISSION_CURRENT", "MISSION_ITEM_REACHED"],
            blocking=False,
            timeout=0.0,
        )
        if message is None:
            return count
    raise ArduPilotAdapterError(
        "Could not drain stale MAVLink mission progress before starting AUTO"
    )


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


def arm_with_retry(
    connection: MavConnection,
    mavlink: object,
    timeout_s: float,
    retry_interval_s: float = 5.0,
) -> None:
    """Re-send the arm command until an armed HEARTBEAT arrives.

    A freshly booted SITL rejects arming while pre-arm checks (EKF origin,
    GPS lock) are still settling, so a single command followed by a long
    wait can never arm; the command has to be repeated.
    """
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        send_arm_command(connection, mavlink)
        wait_slice_s = min(retry_interval_s, max(0.0, deadline - monotonic()))
        try:
            wait_for_armed_state(connection, wait_slice_s)
        except ArduPilotAdapterError:
            continue
        return
    raise ArduPilotAdapterError(
        f"Timed out waiting {timeout_s:.1f}s for ArduPilot to arm"
    )


def wait_for_armed_state(
    connection: MavConnection,
    timeout_s: float,
) -> None:
    """Wait for an armed HEARTBEAT without relying on an unbounded helper."""
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        heartbeat = connection.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=max(0.0, deadline - monotonic()),
        )
        if heartbeat is None:
            continue
        try:
            base_mode = int(getattr(heartbeat, "base_mode"))
        except (AttributeError, TypeError, ValueError):
            continue
        if base_mode & MAV_MODE_FLAG_SAFETY_ARMED:
            return
    raise ArduPilotAdapterError(
        f"Timed out waiting {timeout_s:.1f}s for ArduPilot to arm"
    )


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
    "drain_mission_progress_messages",
    "is_mission_item_request",
    "item_at_sequence",
    "message_sequence",
    "message_type",
    "mission_execution_complete",
    "mission_execution_progressed",
    "mission_type",
    "raise_for_rejected_mission_ack",
    "arm_with_retry",
    "send_arm_command",
    "set_auto_mode",
    "wait_for_armed_state",
]
