"""Mission upload protocol for ArduPilot SITL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic

from adapters.ardupilot_sitl_mavlink import (
    MISSION_UPLOAD_MESSAGE_TYPES,
    MavConnection,
    is_mission_item_request,
    item_at_sequence,
    message_sequence,
    message_type,
    mission_type,
    raise_for_rejected_mission_ack,
)
from adapters.ardupilot_sitl_mission import MissionItem
from adapters.ardupilot_sitl_types import ArduPilotAdapterError


@dataclass(frozen=True)
class MissionUploadProtocol:
    timeout_s: float

    def upload(
        self,
        connection: MavConnection,
        mavlink: object,
        items: Sequence[MissionItem],
    ) -> None:
        self._send_count(connection, mavlink, len(items))
        self._complete(connection, mavlink, items)

    def _send_count(
        self,
        connection: MavConnection,
        mavlink: object,
        item_count: int,
    ) -> None:
        connection.mav.mission_count_send(
            connection.target_system,
            connection.target_component,
            item_count,
            mission_type(mavlink),
        )

    def _complete(
        self,
        connection: MavConnection,
        mavlink: object,
        items: Sequence[MissionItem],
    ) -> None:
        deadline = monotonic() + self.timeout_s
        while monotonic() < deadline:
            message = self._receive_message(connection, deadline)
            if message is None:
                continue
            if self._handle_message(connection, mavlink, message, items):
                return

        raise ArduPilotAdapterError(
            f"Timed out uploading {len(items)} mission items to ArduPilot SITL",
        )

    def _receive_message(
        self,
        connection: MavConnection,
        deadline: float,
    ) -> object | None:
        return connection.recv_match(
            type=list(MISSION_UPLOAD_MESSAGE_TYPES),
            blocking=True,
            timeout=max(0.0, deadline - monotonic()),
        )

    def _handle_message(
        self,
        connection: MavConnection,
        mavlink: object,
        message: object,
        items: Sequence[MissionItem],
    ) -> bool:
        received_message_type = message_type(message)
        if received_message_type == "MISSION_ACK":
            raise_for_rejected_mission_ack(message, mavlink)
            return True

        if is_mission_item_request(received_message_type):
            self._send_requested_item(connection, mavlink, message, items)
            return False

        raise ArduPilotAdapterError(
            f"Unexpected ArduPilot mission upload message: {received_message_type}",
        )

    def _send_requested_item(
        self,
        connection: MavConnection,
        mavlink: object,
        request: object,
        items: Sequence[MissionItem],
    ) -> None:
        sequence = message_sequence(request)
        item = item_at_sequence(items, sequence)
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
            mission_type(mavlink),
        )


__all__ = ["MissionUploadProtocol"]
