"""Mission translation helpers for the ArduPilot SITL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from adapters.sitl.ardupilot_types import ArduPilotAdapterError
from schemas.mission import AltitudeReference, MissionAction

MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_TIME = 19
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_NAV_VTOL_TAKEOFF = 84

MAV_FRAME_GLOBAL = 0
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_FRAME_GLOBAL_TERRAIN_ALT = 10

COORDINATE_SCALE = 10_000_000

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


class MissionDefaultsLike(Protocol):
    altitude_reference: object


class MissionRouteItemLike(Protocol):
    action: object
    lat: float | None
    lon: float | None
    altitude_m: float | None
    altitude_reference: object | None
    loiter_time_s: float | None
    acceptance_radius_m: float | None


class MissionLike(Protocol):
    defaults: MissionDefaultsLike
    route: Sequence[MissionRouteItemLike]


@dataclass(frozen=True)
class MissionItem:
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


def build_mission_items(mission: MissionLike) -> tuple[MissionItem, ...]:
    default_altitude_reference = mission.defaults.altitude_reference
    return tuple(
        _build_mission_item(route_item, default_altitude_reference)
        for route_item in mission.route
    )


def _build_mission_item(
    route_item: MissionRouteItemLike,
    default_altitude_reference: object,
) -> MissionItem:
    return MissionItem(
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
    route_item: MissionRouteItemLike,
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


__all__ = [
    "ALTITUDE_REFERENCE_TO_MAVLINK_FRAME",
    "MISSION_ACTION_TO_MAVLINK_CMD",
    "MissionItem",
    "MissionLike",
    "altitude_reference_to_mavlink_frame",
    "build_mission_items",
    "mission_action_to_mavlink_cmd",
]
