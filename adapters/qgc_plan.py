"""QGroundControl .plan JSON to mission.v5 YAML converter."""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

JsonObject = dict[str, object]
RouteItemDict = dict[str, object]
RouteAction = Literal["vtol_takeoff", "waypoint", "loiter_time", "rtl", "land"]
RouteCounters = defaultdict[RouteAction, int]

_MAV_CMD_NAV_WAYPOINT = 16
_MAV_CMD_NAV_LOITER_TIME = 19
_MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
_MAV_CMD_NAV_LAND = 21
_MAV_CMD_NAV_TAKEOFF = 22
_MAV_CMD_NAV_VTOL_TAKEOFF = 84
_MAV_CMD_NAV_VTOL_LAND = 85
_FRAME_GLOBAL = 0
_FRAME_GLOBAL_RELATIVE_ALT = 3
_PLAN_FILE_TYPE = "Plan"
_ROUTE_ID_BASES: dict[RouteAction, str] = {
    "vtol_takeoff": "takeoff",
    "waypoint": "wp",
    "loiter_time": "loiter",
    "rtl": "rtl",
    "land": "land",
}
_NUMBERED_ROUTE_ID_ACTIONS: set[RouteAction] = {"waypoint", "loiter_time"}
_CONVERTED_PLAN_NOTE = (
    "Converted from QGC .plan. Set vehicle_profile and review all values before use."
)


@dataclass(frozen=True)
class ConvertDiagnostic:
    item_index: int
    command: int | None
    message: str


@dataclass(frozen=True)
class _QgcCoordinate:
    lat: float
    lon: float
    altitude_m: float

    def route_fields(self) -> dict[str, float]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "altitude_m": self.altitude_m,
        }

    def planned_home_fields(self) -> dict[str, float]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "altitude_amsl_m": self.altitude_m,
        }


@dataclass(frozen=True)
class _QgcItem:
    item_index: int
    item_type: str | None
    command: int | None
    frame: int | None
    coordinate: _QgcCoordinate | None
    params: list[object]


CommandHandler = Callable[[_QgcItem, RouteCounters], tuple[RouteItemDict | None, str | None]]


def _diagnostic(
    *,
    item_index: int,
    command: int | None,
    message: str,
) -> ConvertDiagnostic:
    return ConvertDiagnostic(
        item_index=item_index,
        command=command,
        message=message,
    )


def _mapping(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    converted: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        converted[key] = item
    return converted


def _sequence(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return value


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _coordinate_from_raw(value: object) -> _QgcCoordinate | None:
    coordinate = _sequence(value)
    if coordinate is None or len(coordinate) < 3:
        return None
    lat = _number(coordinate[0])
    lon = _number(coordinate[1])
    altitude_m = _number(coordinate[2])
    if lat is None or lon is None or altitude_m is None:
        return None
    return _QgcCoordinate(lat=lat, lon=lon, altitude_m=altitude_m)


def _param_value(params: list[object], index: int) -> float | None:
    if index >= len(params):
        return None
    return _number(params[index])


def _validate_plan_file_type(raw: JsonObject) -> None:
    file_type = raw.get("fileType")
    if file_type != _PLAN_FILE_TYPE:
        raise ValueError(".plan fileType must be 'Plan'")


def _mission_mapping(raw: JsonObject) -> JsonObject:
    mission = _mapping(raw.get("mission"))
    if mission is None:
        raise ValueError("mission missing from .plan")
    return mission


def _mission_items(mission: JsonObject) -> list[object]:
    raw_items = mission.get("items")
    if raw_items is None:
        return []
    items = _sequence(raw_items)
    if items is None:
        raise ValueError("mission.items must be a list in .plan mission")
    return items


def _altitude_reference(items: list[object]) -> str:
    frames: list[int | None] = []
    for raw_item in items:
        item = _mapping(raw_item)
        if item is None:
            continue
        frames.append(_integer(item.get("frame")))

    if any(frame == _FRAME_GLOBAL_RELATIVE_ALT for frame in frames):
        return "relative_home"
    if frames and all(frame == _FRAME_GLOBAL for frame in frames):
        return "amsl"
    return "relative_home"


def _planned_home(mission: JsonObject) -> dict[str, float]:
    planned_home = _coordinate_from_raw(mission.get("plannedHomePosition"))
    if planned_home is None:
        raise ValueError("plannedHomePosition missing or invalid in .plan mission")
    return planned_home.planned_home_fields()


def _defaults(mission: JsonObject, items: list[object]) -> JsonObject:
    defaults: JsonObject = {"altitude_reference": _altitude_reference(items)}
    cruise_speed_mps = _number(mission.get("cruiseSpeed"))
    if cruise_speed_mps is not None:
        defaults["cruise_speed_mps"] = cruise_speed_mps
    hover_speed_mps = _number(mission.get("hoverSpeed"))
    if hover_speed_mps is not None:
        defaults["hover_speed_mps"] = hover_speed_mps
    return defaults


def _route_id(action: RouteAction, counters: RouteCounters) -> str:
    counters[action] += 1
    index = counters[action]
    base = _ROUTE_ID_BASES.get(action, action)
    if index == 1 and action not in _NUMBERED_ROUTE_ID_ACTIONS:
        return base
    return f"{base}{index}"


def _route_item(
    *,
    action: RouteAction,
    counters: RouteCounters,
    fields: JsonObject | None = None,
) -> RouteItemDict:
    item: RouteItemDict = {
        "id": _route_id(action, counters),
        "action": action,
    }
    if fields is not None:
        item.update(fields)
    return item


def _takeoff_altitude(item: _QgcItem) -> float | None:
    if item.coordinate is not None:
        return item.coordinate.altitude_m
    return _param_value(item.params, 6)


def _convert_takeoff(
    item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, str | None]:
    altitude_m = _takeoff_altitude(item)
    if altitude_m is None:
        return None, "takeoff altitude missing or invalid"
    return _route_item(
        action="vtol_takeoff",
        counters=counters,
        fields={"altitude_m": altitude_m},
    ), None


def _convert_waypoint(
    item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, str | None]:
    if item.coordinate is None:
        return None, "waypoint coordinate missing or invalid"
    return _route_item(
        action="waypoint",
        counters=counters,
        fields=item.coordinate.route_fields(),
    ), None


def _convert_loiter(
    item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, str | None]:
    if item.coordinate is None:
        return None, "loiter coordinate missing or invalid"
    loiter_time_s = _param_value(item.params, 0)
    if loiter_time_s is None:
        return None, "loiter time parameter missing or invalid"

    fields: JsonObject = {
        **item.coordinate.route_fields(),
        "loiter_time_s": loiter_time_s,
    }
    loiter_radius_m = _param_value(item.params, 2)
    if loiter_radius_m is not None and loiter_radius_m != 0:
        fields["loiter_radius_m"] = abs(loiter_radius_m)
    return _route_item(
        action="loiter_time",
        counters=counters,
        fields=fields,
    ), None


def _convert_rtl(
    _item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, str | None]:
    return _route_item(action="rtl", counters=counters), None


def _convert_land(
    _item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, str | None]:
    return _route_item(action="land", counters=counters), None


_COMMAND_HANDLERS: dict[int, CommandHandler] = {
    _MAV_CMD_NAV_TAKEOFF: _convert_takeoff,
    _MAV_CMD_NAV_VTOL_TAKEOFF: _convert_takeoff,
    _MAV_CMD_NAV_WAYPOINT: _convert_waypoint,
    _MAV_CMD_NAV_LOITER_TIME: _convert_loiter,
    _MAV_CMD_NAV_RETURN_TO_LAUNCH: _convert_rtl,
    _MAV_CMD_NAV_LAND: _convert_land,
    _MAV_CMD_NAV_VTOL_LAND: _convert_land,
}


def _qgc_item(
    raw_item: object,
    *,
    item_index: int,
) -> tuple[_QgcItem | None, ConvertDiagnostic | None]:
    item = _mapping(raw_item)
    if item is None:
        return None, _diagnostic(
            item_index=item_index,
            command=None,
            message="mission item is not an object; item skipped",
        )

    item_type = item.get("type")
    return _QgcItem(
        item_index=item_index,
        item_type=item_type if isinstance(item_type, str) else None,
        command=_integer(item.get("command")),
        frame=_integer(item.get("frame")),
        coordinate=_coordinate_from_raw(item.get("coordinate")),
        params=_sequence(item.get("params")) or [],
    ), None


def _preflight_diagnostic(item: _QgcItem) -> ConvertDiagnostic | None:
    if item.item_type != "SimpleItem":
        return _diagnostic(
            item_index=item.item_index,
            command=item.command,
            message="unsupported mission item type; item skipped",
        )
    if item.command is None:
        return _diagnostic(
            item_index=item.item_index,
            command=None,
            message="mission item command missing or invalid; item skipped",
        )
    return None


def _convert_item(
    item: _QgcItem,
    counters: RouteCounters,
) -> tuple[RouteItemDict | None, ConvertDiagnostic | None]:
    if item.command is None:
        return None, _diagnostic(
            item_index=item.item_index,
            command=None,
            message="mission item command missing or invalid; item skipped",
        )

    handler = _COMMAND_HANDLERS.get(item.command)
    if handler is None:
        return None, _diagnostic(
            item_index=item.item_index,
            command=item.command,
            message=f"unsupported MAVLink command {item.command}; item skipped",
        )

    route_item, message = handler(item, counters)
    if route_item is not None:
        return route_item, None
    return None, _diagnostic(
        item_index=item.item_index,
        command=item.command,
        message=message
        if message is not None
        else "mission item could not be converted; item skipped",
    )


def _route_items(
    items: list[object],
) -> tuple[list[RouteItemDict], list[ConvertDiagnostic]]:
    route: list[RouteItemDict] = []
    diagnostics: list[ConvertDiagnostic] = []
    counters: RouteCounters = defaultdict(int)
    for item_index, raw_item in enumerate(items):
        item, diagnostic = _qgc_item(raw_item, item_index=item_index)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        if item is None:
            continue

        preflight_diagnostic = _preflight_diagnostic(item)
        if preflight_diagnostic is not None:
            diagnostics.append(preflight_diagnostic)
            continue

        route_item, conversion_diagnostic = _convert_item(item, counters)
        if route_item is not None:
            route.append(route_item)
        if conversion_diagnostic is not None:
            diagnostics.append(conversion_diagnostic)
    return route, diagnostics


def _converted_mission(
    *,
    mission_id: str,
    mission: JsonObject,
    items: list[object],
    route: list[RouteItemDict],
) -> JsonObject:
    return {
        "mission_id": mission_id,
        "vehicle_profile": "",
        "planned_home": _planned_home(mission),
        "defaults": _defaults(mission, items),
        "route": route,
        "metadata": {"notes": _CONVERTED_PLAN_NOTE},
    }


def parse_qgc_plan(
    raw: dict[str, object],
) -> tuple[dict[str, object], list[ConvertDiagnostic]]:
    """Parse a decoded QGC .plan dict and return a mission.v5 dict + diagnostics.

    The returned mission dict has no policy or assets. The caller is responsible
    for filling operational values before use.
    """
    _validate_plan_file_type(raw)
    mission = _mission_mapping(raw)
    items = _mission_items(mission)
    route, diagnostics = _route_items(items)
    return _converted_mission(
        mission_id="imported",
        mission=mission,
        items=items,
        route=route,
    ), diagnostics


def load_and_convert_plan(
    path: Path,
) -> tuple[dict[str, object], list[ConvertDiagnostic]]:
    """Read a .plan file, parse JSON, and return the converted mission dict."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read .plan file: {path}") from exc

    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unable to parse .plan JSON: {exc.msg}") from exc

    plan = _mapping(raw)
    if plan is None:
        raise ValueError(".plan root must be a JSON object")

    mission, diagnostics = parse_qgc_plan(plan)
    mission["mission_id"] = path.stem
    return mission, diagnostics
