"""mission.v7 YAML to QGroundControl .plan JSON exporter.

This is the inverse of ``qgc_plan`` (the importer). It emits a QGC 4.x ``.plan``
document so an operator can author in bvlos-sim's richer YAML and upload via
QGroundControl. bvlos-sim-specific fields (constraints, assets, policy) have no
QGC equivalent and are omitted; they remain in the source YAML only.

Each item carries the standard QGC ``params`` (lat/lon/alt in indices 4-6) and a
``coordinate`` array so the file both loads in QGC and round-trips back through
``bvlos-sim convert``.
"""

import json
from dataclasses import dataclass

from schemas.mission import (
    AltitudeReference,
    MissionAction,
    MissionPlan,
    RouteItem,
)

_PLAN_FILE_TYPE = "Plan"
_GROUND_STATION = "bvlos-sim"
_PLAN_VERSION = 1
_MISSION_VERSION = 2
_GEOFENCE_VERSION = 2
_RALLY_VERSION = 2
_FIRMWARE_TYPE_GENERIC = 0
_VEHICLE_TYPE_GENERIC = 0

_FRAME_GLOBAL = 0
_FRAME_MISSION = 2
_FRAME_GLOBAL_RELATIVE_ALT = 3

# QGC 4.x QGCMAVLink.AltitudeMode values.
_ALT_MODE_RELATIVE = 1
_ALT_MODE_ABSOLUTE = 2

_MAV_CMD_NAV_WAYPOINT = 16
_MAV_CMD_NAV_LOITER_TIME = 19
_MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
_MAV_CMD_NAV_LAND = 21
_MAV_CMD_NAV_VTOL_TAKEOFF = 84


@dataclass(frozen=True)
class ExportDiagnostic:
    """An export warning.

    ``route_item_id`` is set when the exporter rewrote the semantics of a
    single route item (e.g. a terrain altitude falling back to frame 3);
    ``sections`` names mission sections omitted wholesale from the .plan.
    """

    route_item_id: str | None
    message: str
    sections: tuple[str, ...] = ()


def _frame_and_alt_mode(reference: AltitudeReference) -> tuple[int, int]:
    if reference == AltitudeReference.AMSL:
        return _FRAME_GLOBAL, _ALT_MODE_ABSOLUTE
    return _FRAME_GLOBAL_RELATIVE_ALT, _ALT_MODE_RELATIVE


def _simple_item(
    *,
    command: int,
    frame: int,
    params: list[float | None],
    coordinate: list[float],
    altitude: float,
    altitude_mode: int,
    do_jump_id: int,
) -> dict[str, object]:
    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": altitude,
        "AltitudeMode": altitude_mode,
        "autoContinue": True,
        "command": command,
        "coordinate": coordinate,
        "doJumpId": do_jump_id,
        "frame": frame,
        "params": params,
        "type": "SimpleItem",
    }


class _PlanItemBuilder:
    """Builds QGC SimpleItem dicts from mission route items."""

    def __init__(self, mission: MissionPlan) -> None:
        self._mission = mission
        self._default_reference = mission.defaults.altitude_reference
        self._home = mission.planned_home
        self.diagnostics: list[ExportDiagnostic] = []

    def _resolve_frame(self, item: RouteItem) -> tuple[int, int]:
        reference = item.altitude_reference or self._default_reference
        if reference == AltitudeReference.TERRAIN:
            self.diagnostics.append(
                ExportDiagnostic(
                    route_item_id=item.id,
                    message=(
                        "altitude_reference 'terrain' has no direct QGC frame; "
                        "exported as relative-altitude (frame 3)."
                    ),
                )
            )
            return _FRAME_GLOBAL_RELATIVE_ALT, _ALT_MODE_RELATIVE
        return _frame_and_alt_mode(reference)

    def _build_takeoff(self, item: RouteItem, do_jump_id: int) -> dict[str, object]:
        if item.action == MissionAction.TAKEOFF:
            self.diagnostics.append(
                ExportDiagnostic(
                    route_item_id=item.id,
                    message=(
                        "action 'takeoff' exported as MAV_CMD_NAV_VTOL_TAKEOFF "
                        "(84); the fixed-wing takeoff distinction is not "
                        "preserved in the .plan."
                    ),
                )
            )
        frame, altitude_mode = self._resolve_frame(item)
        altitude = item.altitude_m if item.altitude_m is not None else 0.0
        return _simple_item(
            command=_MAV_CMD_NAV_VTOL_TAKEOFF,
            frame=frame,
            params=[0.0, 0.0, 0.0, None, self._home.lat, self._home.lon, altitude],
            coordinate=[self._home.lat, self._home.lon, altitude],
            altitude=altitude,
            altitude_mode=altitude_mode,
            do_jump_id=do_jump_id,
        )

    def _build_waypoint(self, item: RouteItem, do_jump_id: int) -> dict[str, object]:
        frame, altitude_mode = self._resolve_frame(item)
        altitude = item.altitude_m if item.altitude_m is not None else 0.0
        acceptance = (
            item.acceptance_radius_m if item.acceptance_radius_m is not None else 0.0
        )
        return _simple_item(
            command=_MAV_CMD_NAV_WAYPOINT,
            frame=frame,
            params=[0.0, acceptance, 0.0, None, item.lat, item.lon, altitude],
            coordinate=[item.lat, item.lon, altitude],
            altitude=altitude,
            altitude_mode=altitude_mode,
            do_jump_id=do_jump_id,
        )

    def _build_loiter(self, item: RouteItem, do_jump_id: int) -> dict[str, object]:
        frame, altitude_mode = self._resolve_frame(item)
        altitude = item.altitude_m if item.altitude_m is not None else 0.0
        radius = item.loiter_radius_m if item.loiter_radius_m is not None else 0.0
        return _simple_item(
            command=_MAV_CMD_NAV_LOITER_TIME,
            frame=frame,
            params=[
                item.loiter_time_s,
                0.0,
                radius,
                None,
                item.lat,
                item.lon,
                altitude,
            ],
            coordinate=[item.lat, item.lon, altitude],
            altitude=altitude,
            altitude_mode=altitude_mode,
            do_jump_id=do_jump_id,
        )

    def _build_land(self, item: RouteItem, do_jump_id: int) -> dict[str, object]:
        frame, altitude_mode = self._resolve_frame(item)
        altitude = item.altitude_m if item.altitude_m is not None else 0.0
        return _simple_item(
            command=_MAV_CMD_NAV_LAND,
            frame=frame,
            params=[0.0, 0.0, 0.0, None, item.lat, item.lon, altitude],
            coordinate=[item.lat, item.lon, altitude],
            altitude=altitude,
            altitude_mode=altitude_mode,
            do_jump_id=do_jump_id,
        )

    def _build_rtl(self, item: RouteItem, do_jump_id: int) -> dict[str, object]:
        return _simple_item(
            command=_MAV_CMD_NAV_RETURN_TO_LAUNCH,
            frame=_FRAME_MISSION,
            params=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            coordinate=[0.0, 0.0, 0.0],
            altitude=0.0,
            altitude_mode=_ALT_MODE_RELATIVE,
            do_jump_id=do_jump_id,
        )

    def build_items(self) -> list[dict[str, object]]:
        builders = {
            MissionAction.TAKEOFF: self._build_takeoff,
            MissionAction.VTOL_TAKEOFF: self._build_takeoff,
            MissionAction.WAYPOINT: self._build_waypoint,
            MissionAction.LOITER_TIME: self._build_loiter,
            MissionAction.LAND: self._build_land,
            MissionAction.RTL: self._build_rtl,
        }
        return [
            builders[route_item.action](route_item, do_jump_id=index + 1)
            for index, route_item in enumerate(self._mission.route)
        ]


def _omitted_sections(mission: MissionPlan) -> tuple[str, ...]:
    sections: list[str] = []
    if mission.constraints.model_dump(exclude_none=True):
        sections.append("constraints")
    if mission.assets.model_dump(exclude_none=True):
        sections.append("assets")
    return tuple(sections)


def _mission_block(
    mission: MissionPlan, items: list[dict[str, object]]
) -> dict[str, object]:
    default_reference = mission.defaults.altitude_reference
    _, global_alt_mode = _frame_and_alt_mode(
        AltitudeReference.RELATIVE_HOME
        if default_reference == AltitudeReference.TERRAIN
        else default_reference
    )
    block: dict[str, object] = {
        "firmwareType": _FIRMWARE_TYPE_GENERIC,
        "globalPlanAltitudeMode": global_alt_mode,
        "items": items,
        "plannedHomePosition": [
            mission.planned_home.lat,
            mission.planned_home.lon,
            mission.planned_home.altitude_amsl_m,
        ],
        "vehicleType": _VEHICLE_TYPE_GENERIC,
        "version": _MISSION_VERSION,
    }
    if mission.defaults.cruise_speed_mps is not None:
        block["cruiseSpeed"] = mission.defaults.cruise_speed_mps
    if mission.defaults.hover_speed_mps is not None:
        block["hoverSpeed"] = mission.defaults.hover_speed_mps
    return block


def build_qgc_plan(
    mission: MissionPlan,
) -> tuple[dict[str, object], list[ExportDiagnostic]]:
    """Build a QGC .plan dict and export diagnostics from a mission."""
    builder = _PlanItemBuilder(mission)
    items = builder.build_items()
    diagnostics = list(builder.diagnostics)
    omitted = _omitted_sections(mission)
    if omitted:
        diagnostics.append(
            ExportDiagnostic(
                route_item_id=None,
                message=(
                    "bvlos-sim constraints and assets have no QGC equivalent and "
                    "were omitted from the export; they remain in the source YAML."
                ),
                sections=omitted,
            )
        )

    plan = {
        "fileType": _PLAN_FILE_TYPE,
        "geoFence": {"circles": [], "polygons": [], "version": _GEOFENCE_VERSION},
        "groundStation": _GROUND_STATION,
        "mission": _mission_block(mission, items),
        "rallyPoints": {"points": [], "version": _RALLY_VERSION},
        "version": _PLAN_VERSION,
    }
    return plan, diagnostics


def render_qgc_plan(plan: dict[str, object]) -> str:
    """Render a QGC .plan dict to indented, key-sorted JSON with a trailing newline."""
    return json.dumps(plan, indent=4, sort_keys=True) + "\n"


def lossy_export_summary(diagnostics: list[ExportDiagnostic]) -> str | None:
    """One-line summary of export rewrites and omissions, or None when clean.

    Export never fails on these: the .plan format simply cannot represent the
    rewritten or omitted content, so the summary makes the loss visible in CI
    logs while the command still exits 0.
    """
    if not diagnostics:
        return None
    rewritten = sum(
        1 for diagnostic in diagnostics if diagnostic.route_item_id is not None
    )
    sections = [
        section for diagnostic in diagnostics for section in diagnostic.sections
    ]
    line = f"lossy conversion: {rewritten} item(s) rewritten"
    if sections:
        line += ", sections: " + ", ".join(sections)
    return line


__all__ = [
    "ExportDiagnostic",
    "build_qgc_plan",
    "lossy_export_summary",
    "render_qgc_plan",
]
