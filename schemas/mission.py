"""Mission plan schema.

The mission schema is intentionally human-first. MAVLink/QGroundControl import
and export should happen in adapters, while the simulator works with these
domain models.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AltitudeReference(StrEnum):
    """Altitude reference frame for mission authoring and simulation."""

    RELATIVE_HOME = "relative_home"
    AMSL = "amsl"
    TERRAIN = "terrain"


class MissionAction(StrEnum):
    """Supported first-pass mission actions."""

    TAKEOFF = "takeoff"
    VTOL_TAKEOFF = "vtol_takeoff"
    WAYPOINT = "waypoint"
    LOITER_TIME = "loiter_time"
    LAND = "land"
    RTL = "rtl"


class RouteItemInvariantReason(StrEnum):
    FORBIDDEN_TARGET_FIELDS = "forbidden_target_fields"
    MISSING_POSITION = "missing_position"
    MISSING_ALTITUDE = "missing_altitude"
    MISSING_LOITER_TIME = "missing_loiter_time"
    PARTIAL_COORDINATES = "partial_coordinates"
    ALTITUDE_REFERENCE_WITHOUT_ALTITUDE = "altitude_reference_without_altitude"


@dataclass(frozen=True)
class _RouteActionRequirements:
    requires_position: bool = False
    requires_altitude: bool = False
    requires_loiter_time: bool = False
    forbidden_target_fields: tuple[str, ...] = ()
    forbidden_target_fields_message: str = ""


ROUTE_ACTION_REQUIREMENTS = {
    MissionAction.TAKEOFF: _RouteActionRequirements(requires_altitude=True),
    MissionAction.VTOL_TAKEOFF: _RouteActionRequirements(requires_altitude=True),
    MissionAction.WAYPOINT: _RouteActionRequirements(
        requires_position=True,
        requires_altitude=True,
    ),
    MissionAction.LOITER_TIME: _RouteActionRequirements(
        requires_position=True,
        requires_altitude=True,
        requires_loiter_time=True,
    ),
    MissionAction.LAND: _RouteActionRequirements(requires_position=True),
    MissionAction.RTL: _RouteActionRequirements(
        forbidden_target_fields=(
            "lat",
            "lon",
            "altitude_m",
            "altitude_reference",
            "acceptance_radius_m",
            "loiter_time_s",
            "loiter_radius_m",
        ),
        forbidden_target_fields_message=(
            "rtl should not define target coordinates or loiter fields"
        ),
    ),
}


class RouteItemInvariantError(ValueError):
    """Typed route-item invariant failure shared by schema and runtime."""

    def __init__(self, reason: RouteItemInvariantReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def validate_route_item_invariants(item: "RouteItem") -> None:
    has_lat = item.lat is not None
    has_lon = item.lon is not None
    requirements = ROUTE_ACTION_REQUIREMENTS[item.action]
    checks = (
        (
            bool(requirements.forbidden_target_fields)
            and any(
                getattr(item, field_name) is not None
                for field_name in requirements.forbidden_target_fields
            ),
            RouteItemInvariantReason.FORBIDDEN_TARGET_FIELDS,
            requirements.forbidden_target_fields_message,
        ),
        (
            requirements.requires_position and (not has_lat or not has_lon),
            RouteItemInvariantReason.MISSING_POSITION,
            f"{item.action.value} requires lat and lon",
        ),
        (
            requirements.requires_altitude and item.altitude_m is None,
            RouteItemInvariantReason.MISSING_ALTITUDE,
            f"{item.action.value} requires altitude_m",
        ),
        (
            requirements.requires_loiter_time and item.loiter_time_s is None,
            RouteItemInvariantReason.MISSING_LOITER_TIME,
            "loiter_time requires loiter_time_s",
        ),
        (
            has_lat != has_lon,
            RouteItemInvariantReason.PARTIAL_COORDINATES,
            "lat and lon must either both be provided or both be omitted",
        ),
        (
            item.altitude_reference is not None and item.altitude_m is None,
            RouteItemInvariantReason.ALTITUDE_REFERENCE_WITHOUT_ALTITUDE,
            "altitude_reference requires altitude_m",
        ),
    )
    for invalid, reason, message in checks:
        if invalid:
            raise RouteItemInvariantError(reason, message)


class PlannedHome(BaseModel):
    """Home position used when no vehicle is connected.

    This mirrors the planning role of QGroundControl's plannedHomePosition.
    """

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90, description="Home latitude in decimal degrees.")
    lon: float = Field(ge=-180, le=180, description="Home longitude in decimal degrees.")
    altitude_amsl_m: float = Field(description="Home altitude above mean sea level.")


class MissionDefaults(BaseModel):
    """Plan-wide defaults similar to QGroundControl mission defaults."""

    model_config = ConfigDict(extra="forbid")

    cruise_speed_mps: float | None = Field(
        default=None,
        gt=0,
        description="Default fixed-wing/VTOL cruise speed. Source: QGC cruiseSpeed.",
    )
    hover_speed_mps: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Default multirotor forward speed. Source: QGC hoverSpeed. "
            "Accepted for broader mission compatibility, but estimator v1 does "
            "not consume this field."
        ),
    )
    altitude_reference: AltitudeReference = Field(
        default=AltitudeReference.RELATIVE_HOME,
        description="Default altitude frame for route items.",
    )


class WindLayerConfig(BaseModel):
    """A single altitude-band wind layer for YAML-configured layered wind.

    When ``wind_layers`` is set on ``MissionEstimation`` or
    ``ScenarioInitialConditions`` the estimator builds a ``LayeredWindProvider``
    from these entries instead of the scalar ``wind_east_mps`` / ``wind_north_mps``
    constant-wind values.
    """

    model_config = ConfigDict(extra="forbid")

    altitude_m: float = Field(
        description="Lower bound of this wind band in metres AMSL.",
    )
    wind_east_mps: float = Field(
        default=0.0,
        description="Wind east component in m/s for this band.",
    )
    wind_north_mps: float = Field(
        default=0.0,
        description="Wind north component in m/s for this band.",
    )


class MissionEstimation(BaseModel):
    """Optional persisted estimator options.

    These values are used by the estimator only when runtime options are not
    explicitly provided. ``wind_layers`` and scalar wind values may coexist for
    authoring convenience; when layers are present, the scalar
    ``wind_east_mps`` / ``wind_north_mps`` values are ignored.
    """

    model_config = ConfigDict(extra="forbid")

    wind_east_mps: float = Field(
        default=0.0,
        description=(
            "Constant wind east component in m/s. Ignored when ``wind_layers`` is set."
        ),
    )
    wind_north_mps: float = Field(
        default=0.0,
        description=(
            "Constant wind north component in m/s. Ignored when ``wind_layers`` is set."
        ),
    )
    wind_layers: list[WindLayerConfig] | None = Field(
        default=None,
        description=(
            "Altitude-banded wind layers. When set, supersedes ``wind_east_mps`` and "
            "``wind_north_mps`` and builds a LayeredWindProvider. Layers need not be "
            "sorted; the estimator picks the highest layer not exceeding the query altitude."
        ),
    )
    min_groundspeed_mps: float | None = Field(
        default=None,
        description="Optional mission-level minimum operational groundspeed in m/s.",
    )
    max_segment_length_m: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Sub-segment wind sampling interval in metres. When set, transit legs are "
            "divided into sub-segments of at most this length and wind is sampled at "
            "each midpoint. Must be > 0."
        ),
    )
    fidelity: Literal["v1", "v2"] = Field(
        default="v1",
        description=(
            "Estimator fidelity mode. 'v1' (default): leg-to-leg geodesic model. "
            "'v2': adds turn-arc dynamics at waypoints and fixed-wing circular loiter."
        ),
    )


class RouteItem(BaseModel):
    """Human-readable route item that can later map to MAVLink mission commands."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable route item identifier used in reports and timeline output.",
    )
    action: MissionAction = Field(
        description=(
            "Mission action. The MAVLink adapter maps this to MAV_CMD_NAV_* "
            "or related commands."
        ),
    )
    lat: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="Target latitude in decimal degrees when the action needs a position.",
    )
    lon: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="Target longitude in decimal degrees when the action needs a position.",
    )
    altitude_m: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Target altitude in meters. The reference is altitude_reference or "
            "mission defaults."
        ),
    )
    altitude_reference: AltitudeReference | None = Field(
        default=None,
        description="Optional per-item altitude reference override.",
    )
    acceptance_radius_m: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Waypoint acceptance radius. Maps to MAV_CMD_NAV_WAYPOINT param2. "
            "Accepted for interoperability, but estimator v1 ignores it and "
            "flies to the exact target coordinates."
        ),
    )
    loiter_time_s: float | None = Field(
        default=None,
        description=(
            "Loiter duration in seconds. Required for loiter_time actions. "
            "Negative values are rejected at execution time by the estimator."
        ),
    )
    loiter_radius_m: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional loiter radius. Accepted for interoperability, but "
            "station-keep loiter in estimator v1 ignores this value."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form route item notes or source references ignored by estimator v1.",
    )

    @model_validator(mode="after")
    def validate_action_requirements(self) -> "RouteItem":
        validate_route_item_invariants(self)
        return self


class MissionConstraints(BaseModel):
    """Mission-level safety constraints evaluated by the validator."""

    model_config = ConfigDict(extra="forbid")

    min_landing_reserve_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Optional mission reserve override. When omitted, deterministic "
            "energy feasibility uses vehicle.energy.reserve_percent_default."
        ),
    )
    max_wind_mps: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Mission wind limit. Reserved for later feasibility layers; "
            "estimator v1 does not enforce it."
        ),
    )
    min_distance_to_landing_zone_m: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum tolerated straight-line distance to an emergency landing zone."
        ),
    )


class MissionAssets(BaseModel):
    """External files used by the simulator but not uploaded as a MAVLink mission."""

    model_config = ConfigDict(extra="forbid")

    geofences_file: Path | None = Field(
        default=None,
        description="Optional GeoJSON static geofence file used by feasibility checks.",
    )
    landing_zones_file: Path | None = Field(
        default=None,
        description="Optional GeoJSON emergency landing zone file used by reachability checks.",
    )
    terrain_file: Path | None = Field(
        default=None,
        description="Optional elevation grid file (YAML/JSON uniform grid) for terrain-referenced altitude resolution.",
    )
    comms_coverage_file: Path | None = Field(
        default=None,
        description="GeoJSON or raster communication coverage file reserved for later simulator phases.",
    )


class MissionPolicyRef(BaseModel):
    """Policy references used by the scenario and policy engines."""

    model_config = ConfigDict(extra="forbid")

    lost_link_policy: str | None = Field(
        default=None,
        description="Named lost-link policy reserved for later scenario/policy phases.",
    )


class MissionPlan(BaseModel):
    """Top-level mission definition used by validation and simulation."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable mission identifier.",
    )
    vehicle_profile: str = Field(
        min_length=1,
        description="Vehicle profile id referenced by this mission.",
    )
    planned_home: PlannedHome = Field(
        description="Planned home position used for route planning and RTL assumptions.",
    )
    defaults: MissionDefaults = Field(default_factory=MissionDefaults)
    route: list[RouteItem] = Field(
        min_length=1,
        description="Ordered mission route.",
    )
    constraints: MissionConstraints
    assets: MissionAssets = Field(default_factory=MissionAssets)
    policy: MissionPolicyRef = Field(default_factory=MissionPolicyRef)
    estimation: MissionEstimation | None = Field(
        default=None,
        description="Optional persisted estimator settings used when runtime options are absent.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form mission notes or source references ignored by estimator v1.",
    )

    @model_validator(mode="after")
    def validate_route_ids(self) -> "MissionPlan":
        route_ids = [item.id for item in self.route]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("route item ids must be unique")
        return self
