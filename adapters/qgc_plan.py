"""QGroundControl .plan JSON to mission.v7 YAML converter.

Every conversion loss (a dropped mission item or a dropped .plan section) is
reported as a :class:`ConvertDiagnostic` with ``lossy=True`` so the CLI can
fail closed instead of silently writing an incomplete mission.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from schemas.mission import MISSION_SCHEMA_VERSION

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
_FRAME_GLOBAL_TERRAIN_ALT = 10
_FRAME_ALTITUDE_REFERENCES: dict[int, str] = {
    _FRAME_GLOBAL: "amsl",
    _FRAME_GLOBAL_RELATIVE_ALT: "relative_home",
    _FRAME_GLOBAL_TERRAIN_ALT: "terrain",
}
_DEFAULT_ALTITUDE_REFERENCE = "relative_home"
# Commands whose altitude value is interpreted through the item frame. RTL is
# excluded: QGC writes it with the non-positional MAV_FRAME_MISSION (2).
_ALTITUDE_BEARING_COMMANDS: set[int] = {
    _MAV_CMD_NAV_WAYPOINT,
    _MAV_CMD_NAV_LOITER_TIME,
    _MAV_CMD_NAV_LAND,
    _MAV_CMD_NAV_TAKEOFF,
    _MAV_CMD_NAV_VTOL_TAKEOFF,
    _MAV_CMD_NAV_VTOL_LAND,
}
_DROPPED_SECTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("geoFence", ("circles", "polygons"), "fence geometry"),
    ("rallyPoints", ("points",), "rally points"),
)
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
    "Converted from QGC .plan. Review all values before operational use."
)


@dataclass(frozen=True)
class ConvertDiagnostic:
    """A conversion warning or loss.

    ``lossy`` is True when the diagnostic describes information dropped from
    the converted mission (a skipped item or a dropped .plan section) and
    False for advisory warnings about preserved-but-normalised items.
    ``section`` names the dropped .plan section for section-level losses;
    item-level diagnostics carry ``item_index``/``command`` instead.
    """

    item_index: int | None
    command: int | None
    message: str
    section: str | None = None
    lossy: bool = True


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


# JSON primitive helpers — used across all parsing layers
CommandHandler = Callable[
    [_QgcItem, RouteCounters], tuple[RouteItemDict | None, str | None]
]


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


def _make_diagnostic(
    *,
    item_index: int,
    command: int | None,
    message: str,
    lossy: bool = True,
) -> ConvertDiagnostic:
    return ConvertDiagnostic(
        item_index=item_index,
        command=command,
        message=message,
        lossy=lossy,
    )


class _QgcPlanReader:
    """Validates .plan structure and extracts top-level fields."""

    @staticmethod
    def validate_file_type(raw: JsonObject) -> None:
        file_type = raw.get("fileType")
        if file_type != _PLAN_FILE_TYPE:
            raise ValueError(".plan fileType must be 'Plan'")

    @staticmethod
    def mission_mapping(raw: JsonObject) -> JsonObject:
        mission = _mapping(raw.get("mission"))
        if mission is None:
            raise ValueError("mission missing from .plan")
        return mission

    @staticmethod
    def mission_items(mission: JsonObject) -> list[object]:
        raw_items = mission.get("items")
        if raw_items is None:
            return []
        items = _sequence(raw_items)
        if items is None:
            raise ValueError("mission.items must be a list in .plan mission")
        return items


class _QgcItemParser:
    """Parses raw mission-item dicts into typed _QgcItem instances."""

    @staticmethod
    def coordinate_from_raw(value: object) -> _QgcCoordinate | None:
        coordinate = _sequence(value)
        if coordinate is None or len(coordinate) < 3:
            return None
        lat = _number(coordinate[0])
        lon = _number(coordinate[1])
        altitude_m = _number(coordinate[2])
        if lat is None or lon is None or altitude_m is None:
            return None
        return _QgcCoordinate(lat=lat, lon=lon, altitude_m=altitude_m)

    @staticmethod
    def param_value(params: list[object], index: int) -> float | None:
        if index >= len(params):
            return None
        return _number(params[index])

    @staticmethod
    def parse(
        raw_item: object,
        *,
        item_index: int,
    ) -> tuple[_QgcItem | None, ConvertDiagnostic | None]:
        item = _mapping(raw_item)
        if item is None:
            return None, _make_diagnostic(
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
            coordinate=_QgcItemParser.coordinate_from_raw(item.get("coordinate")),
            params=_sequence(item.get("params")) or [],
        ), None

    @staticmethod
    def preflight_diagnostic(item: _QgcItem) -> ConvertDiagnostic | None:
        if item.item_type != "SimpleItem":
            return _make_diagnostic(
                item_index=item.item_index,
                command=item.command,
                message="unsupported mission item type; item skipped",
            )
        if item.command is None:
            return _make_diagnostic(
                item_index=item.item_index,
                command=None,
                message="mission item command missing or invalid; item skipped",
            )
        return None


_ItemHandler = Callable[[_QgcItem], tuple[RouteItemDict | None, str | None]]


class _RouteConverter:
    """Converts parsed _QgcItem instances into mission.v7 route items."""

    def __init__(self) -> None:
        self._counters: RouteCounters = defaultdict(int)
        self._handlers: dict[int, _ItemHandler] = {
            _MAV_CMD_NAV_TAKEOFF: self._convert_takeoff,
            _MAV_CMD_NAV_VTOL_TAKEOFF: self._convert_takeoff,
            _MAV_CMD_NAV_WAYPOINT: self._convert_waypoint,
            _MAV_CMD_NAV_LOITER_TIME: self._convert_loiter,
            _MAV_CMD_NAV_RETURN_TO_LAUNCH: self._convert_rtl,
            _MAV_CMD_NAV_LAND: self._convert_land,
            _MAV_CMD_NAV_VTOL_LAND: self._convert_land,
        }

    def _route_id(self, action: RouteAction) -> str:
        self._counters[action] += 1
        index = self._counters[action]
        base = _ROUTE_ID_BASES.get(action, action)
        if index == 1 and action not in _NUMBERED_ROUTE_ID_ACTIONS:
            return base
        return f"{base}{index}"

    def _route_item(
        self,
        *,
        action: RouteAction,
        fields: JsonObject | None = None,
    ) -> RouteItemDict:
        item: RouteItemDict = {
            "id": self._route_id(action),
            "action": action,
        }
        if fields is not None:
            item.update(fields)
        return item

    def _convert_takeoff(
        self, item: _QgcItem
    ) -> tuple[RouteItemDict | None, str | None]:
        altitude_m = (
            item.coordinate.altitude_m
            if item.coordinate is not None
            else _QgcItemParser.param_value(item.params, 6)
        )
        if altitude_m is None:
            return None, "takeoff altitude missing or invalid"
        warning = None
        if item.command == _MAV_CMD_NAV_TAKEOFF:
            warning = (
                "MAV_CMD_NAV_TAKEOFF (22) normalised to vtol_takeoff; "
                "fixed-wing-only takeoff is not a separate action in mission.v7. "
                "Review vehicle_class after converting."
            )
        return self._route_item(
            action="vtol_takeoff", fields={"altitude_m": altitude_m}
        ), warning

    def _convert_waypoint(
        self, item: _QgcItem
    ) -> tuple[RouteItemDict | None, str | None]:
        if item.coordinate is None:
            return None, "waypoint coordinate missing or invalid"
        return self._route_item(
            action="waypoint", fields=item.coordinate.route_fields()
        ), None

    def _convert_loiter(
        self, item: _QgcItem
    ) -> tuple[RouteItemDict | None, str | None]:
        if item.coordinate is None:
            return None, "loiter coordinate missing or invalid"
        loiter_time_s = _QgcItemParser.param_value(item.params, 0)
        if loiter_time_s is None or loiter_time_s <= 0:
            return None, "loiter time must be a positive number"
        fields: JsonObject = {
            **item.coordinate.route_fields(),
            "loiter_time_s": loiter_time_s,
        }
        loiter_radius_m = _QgcItemParser.param_value(item.params, 2)
        if loiter_radius_m is not None and loiter_radius_m != 0:
            fields["loiter_radius_m"] = abs(loiter_radius_m)
        return self._route_item(action="loiter_time", fields=fields), None

    def _convert_rtl(self, item: _QgcItem) -> tuple[RouteItemDict | None, str | None]:
        return self._route_item(action="rtl"), None

    def _convert_land(self, item: _QgcItem) -> tuple[RouteItemDict | None, str | None]:
        if item.coordinate is None:
            return None, "land coordinate missing or invalid"
        return self._route_item(
            action="land", fields=item.coordinate.route_fields()
        ), None

    def _convert_item(
        self, item: _QgcItem
    ) -> tuple[RouteItemDict | None, ConvertDiagnostic | None]:
        if item.command is None:
            return None, _make_diagnostic(
                item_index=item.item_index,
                command=None,
                message="mission item command missing or invalid; item skipped",
            )
        handler = self._handlers.get(item.command)
        if handler is None:
            return None, _make_diagnostic(
                item_index=item.item_index,
                command=item.command,
                message=f"unsupported MAVLink command {item.command}; item skipped",
            )
        altitude_reference: str | None = None
        if item.command in _ALTITUDE_BEARING_COMMANDS:
            altitude_reference = (
                _FRAME_ALTITUDE_REFERENCES.get(item.frame)
                if item.frame is not None
                else None
            )
            if altitude_reference is None:
                return None, _make_diagnostic(
                    item_index=item.item_index,
                    command=item.command,
                    message=(
                        f"unsupported altitude frame {item.frame}; item skipped"
                    ),
                )
        route_item, message = handler(item)
        if route_item is not None:
            if altitude_reference is not None:
                route_item["altitude_reference"] = altitude_reference
            diag = (
                _make_diagnostic(
                    item_index=item.item_index,
                    command=item.command,
                    message=message,
                    lossy=False,
                )
                if message is not None
                else None
            )
            return route_item, diag
        return None, _make_diagnostic(
            item_index=item.item_index,
            command=item.command,
            message=(
                message
                if message is not None
                else "mission item could not be converted; item skipped"
            ),
        )

    def convert_items(
        self,
        items: list[object],
    ) -> tuple[list[RouteItemDict], list[ConvertDiagnostic]]:
        route: list[RouteItemDict] = []
        diagnostics: list[ConvertDiagnostic] = []
        for item_index, raw_item in enumerate(items):
            item, diagnostic = _QgcItemParser.parse(raw_item, item_index=item_index)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                continue
            if item is None:
                continue
            preflight_diagnostic = _QgcItemParser.preflight_diagnostic(item)
            if preflight_diagnostic is not None:
                diagnostics.append(preflight_diagnostic)
                continue
            route_item, conversion_diagnostic = self._convert_item(item)
            if route_item is not None:
                route.append(route_item)
            if conversion_diagnostic is not None:
                diagnostics.append(conversion_diagnostic)
        return route, diagnostics


class _MissionAssembler:
    """Builds the final mission.v7 dict from parsed plan components."""

    @staticmethod
    def resolve_altitude_reference(route: list[RouteItemDict]) -> str:
        """Pick the mission default reference and strip matching per-item keys.

        The most common per-item reference becomes the mission default
        (first-seen wins a tie); items that use it lose their redundant
        override while items in another frame keep an explicit
        ``altitude_reference``.
        """
        counts = Counter(
            str(item["altitude_reference"])
            for item in route
            if "altitude_reference" in item
        )
        if not counts:
            return _DEFAULT_ALTITUDE_REFERENCE
        default = counts.most_common(1)[0][0]
        for item in route:
            if item.get("altitude_reference") == default:
                del item["altitude_reference"]
        return default

    @staticmethod
    def planned_home(mission: JsonObject) -> dict[str, float]:
        planned_home = _QgcItemParser.coordinate_from_raw(
            mission.get("plannedHomePosition")
        )
        if planned_home is None:
            raise ValueError("plannedHomePosition missing or invalid in .plan mission")
        return planned_home.planned_home_fields()

    @staticmethod
    def defaults(mission: JsonObject, altitude_reference: str) -> JsonObject:
        result: JsonObject = {"altitude_reference": altitude_reference}
        cruise_speed_mps = _number(mission.get("cruiseSpeed"))
        if cruise_speed_mps is not None:
            result["cruise_speed_mps"] = cruise_speed_mps
        hover_speed_mps = _number(mission.get("hoverSpeed"))
        if hover_speed_mps is not None:
            result["hover_speed_mps"] = hover_speed_mps
        return result

    @staticmethod
    def build(
        *,
        mission_id: str,
        vehicle_profile: str,
        mission: JsonObject,
        route: list[RouteItemDict],
        altitude_reference: str,
    ) -> JsonObject:
        return {
            "schema_version": MISSION_SCHEMA_VERSION,
            "mission_id": mission_id,
            "vehicle_profile": vehicle_profile,
            "planned_home": _MissionAssembler.planned_home(mission),
            "defaults": _MissionAssembler.defaults(mission, altitude_reference),
            "route": route,
            "constraints": {},
            "metadata": {"notes": _CONVERTED_PLAN_NOTE},
        }


def _section_is_populated(value: object, list_keys: tuple[str, ...]) -> bool:
    """True when a .plan section carries data that would be dropped."""
    if value is None:
        return False
    section = _mapping(value)
    if section is None:
        # Unknown section shape: treat as populated so the loss is reported.
        return True
    return any(_sequence(section.get(key)) for key in list_keys)


def _section_diagnostics(raw: JsonObject) -> list[ConvertDiagnostic]:
    diagnostics: list[ConvertDiagnostic] = []
    for section, list_keys, content in _DROPPED_SECTIONS:
        if _section_is_populated(raw.get(section), list_keys):
            diagnostics.append(
                ConvertDiagnostic(
                    item_index=None,
                    command=None,
                    message=(
                        f"{section} section contains {content} with no "
                        "mission.v7 equivalent; section dropped"
                    ),
                    section=section,
                )
            )
    return diagnostics


def parse_qgc_plan(
    raw: dict[str, object],
    *,
    vehicle_profile: str,
) -> tuple[dict[str, object], list[ConvertDiagnostic]]:
    """Parse a decoded QGC .plan dict and return a mission.v7 dict + diagnostics.

    The returned mission dict has no policy or assets. The caller is responsible
    for filling operational values before use. Diagnostics with ``lossy=True``
    describe dropped items and dropped ``geoFence``/``rallyPoints`` sections;
    callers deciding whether the conversion is acceptable must inspect them.
    """
    _QgcPlanReader.validate_file_type(raw)
    mission = _QgcPlanReader.mission_mapping(raw)
    items = _QgcPlanReader.mission_items(mission)
    route, diagnostics = _RouteConverter().convert_items(items)
    diagnostics = [*diagnostics, *_section_diagnostics(raw)]
    altitude_reference = _MissionAssembler.resolve_altitude_reference(route)
    return _MissionAssembler.build(
        mission_id="imported",
        vehicle_profile=vehicle_profile,
        mission=mission,
        route=route,
        altitude_reference=altitude_reference,
    ), diagnostics


def load_and_convert_plan(
    path: Path,
    *,
    vehicle_profile: str,
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

    mission, diagnostics = parse_qgc_plan(plan, vehicle_profile=vehicle_profile)
    mission["mission_id"] = path.stem
    return mission, diagnostics
