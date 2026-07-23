"""Mission plan schema.

The mission schema is intentionally human-first. MAVLink/QGroundControl import
and export should happen in adapters, while the simulator works with these
domain models.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from schemas.resource_link import LinkSystemConfig
from schemas.numeric import FiniteFloat
from schemas.sora import SoraMitigations

MISSION_SCHEMA_VERSION = "mission.v7"


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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lat: FiniteFloat = Field(
        ge=-90, le=90, description="Home latitude in decimal degrees."
    )
    lon: FiniteFloat = Field(
        ge=-180, le=180, description="Home longitude in decimal degrees."
    )
    altitude_amsl_m: FiniteFloat = Field(
        description="Home altitude above mean sea level."
    )


class MissionDefaults(BaseModel):
    """Plan-wide defaults similar to QGroundControl mission defaults."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    cruise_speed_mps: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description="Default fixed-wing/VTOL cruise speed. Source: QGC cruiseSpeed.",
    )
    hover_speed_mps: FiniteFloat | None = Field(
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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    altitude_m: FiniteFloat = Field(
        description="Lower bound of this wind band in metres AMSL.",
    )
    wind_east_mps: FiniteFloat = Field(
        default=0.0,
        description="Wind east component in m/s for this band.",
    )
    wind_north_mps: FiniteFloat = Field(
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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    wind_east_mps: FiniteFloat = Field(
        default=0.0,
        description=(
            "Constant wind east component in m/s. Ignored when ``wind_layers`` is set."
        ),
    )
    wind_north_mps: FiniteFloat = Field(
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
    min_groundspeed_mps: FiniteFloat | None = Field(
        default=None,
        description="Optional mission-level minimum operational groundspeed in m/s.",
    )
    max_segment_length_m: FiniteFloat | None = Field(
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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

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
    lat: FiniteFloat | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="Target latitude in decimal degrees when the action needs a position.",
    )
    lon: FiniteFloat | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="Target longitude in decimal degrees when the action needs a position.",
    )
    altitude_m: FiniteFloat | None = Field(
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
    acceptance_radius_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Waypoint acceptance radius. Maps to MAV_CMD_NAV_WAYPOINT param2. "
            "Accepted for interoperability, but estimator v1 ignores it and "
            "flies to the exact target coordinates."
        ),
    )
    loiter_time_s: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description="Loiter duration in seconds. Required for loiter_time actions.",
    )
    loiter_radius_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional loiter radius. Accepted for interoperability and schema "
            "stability, but always ignored by the estimator. Fidelity v2 "
            "fixed-wing circular loiter uses vehicle.performance.turn_radius_m "
            "instead."
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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    accepted_warning_codes: list[str] = Field(
        default_factory=list,
        description=(
            "Advisory warning codes the operator has reviewed and explicitly "
            "accepts for this mission. Acknowledged warnings are still "
            "reported in every artifact but no longer block the operational "
            "GO verdict. Unlisted warnings keep blocking."
        ),
    )
    min_landing_reserve_percent: FiniteFloat | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Optional mission reserve override. When omitted, deterministic "
            "energy feasibility uses vehicle.energy.reserve_percent_default."
        ),
    )
    require_rth_reserve: StrictBool = Field(
        default=True,
        description=(
            "Return-to-home reserve must remain above the landing reserve "
            "threshold at every evaluated route leg. Defaults to true so "
            "missions fail closed unless an operator explicitly accepts a "
            "non-operational engineering-only estimate."
        ),
    )
    max_wind_mps: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Mission-level sustained wind limit in m/s. When a wind provider is "
            "configured, any route leg whose sampled wind speed exceeds this "
            "limit makes the mission INFEASIBLE (WIND_LIMIT_EXCEEDED)."
        ),
    )
    max_gust_mps: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum gust speed in m/s. The active providers do not currently "
            "supply gust observations, so configuring this limit fails closed "
            "with WEATHER_DATA_UNAVAILABLE."
        ),
    )
    max_crosswind_mps: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum wind component perpendicular to a route leg's ground track "
            "in m/s. Any leg exceeding this makes the mission INFEASIBLE "
            "(CROSSWIND_LIMIT_EXCEEDED) when a wind provider is configured."
        ),
    )
    min_visibility_m: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Minimum horizontal visibility in metres. The active providers do "
            "not currently supply visibility observations, so configuring this "
            "limit fails closed with WEATHER_DATA_UNAVAILABLE."
        ),
    )
    max_precipitation_mm_h: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum precipitation rate in mm/h. The active providers do not "
            "currently supply precipitation observations, so configuring this "
            "limit fails closed with WEATHER_DATA_UNAVAILABLE."
        ),
    )
    min_obstacle_clearance_m: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Minimum horizontal and vertical safety buffer in metres around "
            "configured static obstacles."
        ),
    )
    min_terrain_clearance_m: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Minimum required clearance in metres above sampled terrain along "
            "each route leg when a terrain grid is configured."
        ),
    )
    min_distance_to_landing_zone_m: FiniteFloat | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum tolerated straight-line distance to an emergency landing zone."
        ),
    )

    @model_validator(mode="after")
    def _validate_accepted_warning_codes(self) -> "MissionConstraints":
        # Imported lazily: estimator.execution imports this module, so a
        # top-level estimator import would be circular.
        from estimator.core.enums import WarningCode

        valid = {code.value for code in WarningCode}
        seen: set[str] = set()
        for code in self.accepted_warning_codes:
            if code not in valid:
                raise ValueError(
                    f"accepted_warning_codes entry {code!r} is not a known "
                    f"warning code; valid codes: {', '.join(sorted(valid))}"
                )
            if code in seen:
                raise ValueError(
                    f"accepted_warning_codes entry {code!r} is duplicated"
                )
            seen.add(code)
        return self


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
    population_grid_file: Path | None = Field(
        default=None,
        description="Optional population-density grid file (YAML/JSON uniform grid) for SORA ground-risk classification.",
    )
    obstacles_file: Path | None = Field(
        default=None,
        description="Optional GeoJSON obstacle file used by vertical clearance checks.",
    )
    wind_grid_file: Path | None = Field(
        default=None,
        description="Optional spatiotemporal wind grid file (YAML/JSON) for 4D wind estimation.",
    )
    comms_coverage_file: Path | None = Field(
        default=None,
        description="GeoJSON or raster communication coverage file reserved for later simulator phases.",
    )


class IcaoAirspaceClass(StrEnum):
    """ICAO airspace class at the operational altitude."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class Airspace(BaseModel):
    """Whole-volume airspace descriptor used for SORA Air Risk classification."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, allow_inf_nan=False
    )

    airspace_class: IcaoAirspaceClass = Field(
        alias="class",
        description="ICAO airspace class at the operational altitude.",
    )
    max_altitude_agl_m: FiniteFloat = Field(
        gt=0,
        description=(
            "Worst-case ceiling above ground level across the operational and "
            "contingency volumes, in metres."
        ),
    )
    operational_and_contingency_volume_assessment_reference: str = Field(
        min_length=1,
        description=(
            "Auditable reference for the assessment covering the entire "
            "operational and contingency volumes."
        ),
    )
    worst_case_arc_declared: StrictBool = Field(
        description=(
            "Confirms that every airspace descriptor is the worst-case condition "
            "anywhere in the operational or contingency volume."
        ),
    )
    aerodrome_environment: StrictBool = Field(
        description=(
            "SORA Annex I aerodrome-environment result for the entire volume: "
            "includes applicable aerodrome-connected controlled airspace, a "
            "Mode-C veil/TMZ in Class A-E, or the defined 5/3/2 NM proximity to "
            "an airport or heliport."
        ),
    )
    atypical_or_segregated: StrictBool = Field(
        default=False,
        description=(
            "Reserved ARC-a declaration. True is rejected until an authority-backed "
            "atypical-airspace evidence workflow is implemented."
        ),
    )
    over_urban_area: StrictBool | None = Field(
        default=None,
        description=(
            "Whether the operational volume is over an urban rather than rural "
            "area. Required for typical uncontrolled operations at or below 500 ft AGL."
        ),
    )
    transponder_mandatory_zone: StrictBool = Field(
        description="True when the assessed volume lies in a Mode-C veil or TMZ.",
    )
    entirely_above_flight_level_600: StrictBool = Field(
        default=False,
        description=(
            "Reserved above-FL600 declaration. True is rejected until a "
            "pressure-altitude evidence workflow is implemented."
        ),
    )
    strategic_mitigation: StrictBool = Field(
        default=False,
        description=(
            "Reserved for a future evidence-backed strategic air-risk assessment."
        ),
    )

    @model_validator(mode="after")
    def validate_air_risk_inputs(self) -> "Airspace":
        if not self.operational_and_contingency_volume_assessment_reference.strip():
            raise ValueError(
                "operational_and_contingency_volume_assessment_reference must not "
                "be blank"
            )
        if not self.worst_case_arc_declared:
            raise ValueError(
                "worst_case_arc_declared must be true after assessing the entire "
                "operational and contingency volumes"
            )
        if self.atypical_or_segregated:
            raise ValueError(
                "atypical_or_segregated ARC-a assignment is unsupported until an "
                "authority-backed atypical-airspace evidence workflow is implemented"
            )
        if self.entirely_above_flight_level_600:
            raise ValueError(
                "entirely_above_flight_level_600 assignment is unsupported until a "
                "pressure-altitude evidence workflow is implemented"
            )
        if self.strategic_mitigation:
            raise ValueError(
                "strategic_mitigation cannot be credited from a boolean declaration; "
                "an evidence-backed local encounter-rate assessment is required"
            )
        if (
            self.transponder_mandatory_zone
            and self.airspace_class
            in {
                IcaoAirspaceClass.A,
                IcaoAirspaceClass.B,
                IcaoAirspaceClass.C,
                IcaoAirspaceClass.D,
                IcaoAirspaceClass.E,
            }
            and not self.aerodrome_environment
        ):
            raise ValueError(
                "a Mode-C veil/TMZ in Class A-E is an aerodrome_environment "
                "under SORA Annex I"
            )
        uncontrolled = self.airspace_class in {
            IcaoAirspaceClass.F,
            IcaoAirspaceClass.G,
        }
        if (
            uncontrolled
            and self.max_altitude_agl_m <= 152.4
            and not self.aerodrome_environment
            and not self.atypical_or_segregated
            and not self.transponder_mandatory_zone
            and not self.entirely_above_flight_level_600
            and self.over_urban_area is None
        ):
            raise ValueError(
                "over_urban_area is required for typical uncontrolled operations "
                "at or below 500 ft AGL"
            )
        return self


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

    schema_version: Literal["mission.v7"] = MISSION_SCHEMA_VERSION
    mission_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable mission identifier.",
    )
    vehicle_profile: str = Field(
        min_length=1,
        description="Vehicle profile id referenced by this mission.",
    )
    departure_time: datetime | None = Field(
        default=None,
        description=(
            "Optional planned mission departure time as an ISO-8601 UTC timestamp."
        ),
    )
    planned_home: PlannedHome = Field(
        description="Planned home position used for route planning and RTL assumptions.",
    )
    defaults: MissionDefaults = Field(default_factory=MissionDefaults)
    route: list[RouteItem] = Field(
        min_length=1,
        description="Ordered mission route.",
    )
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)
    assets: MissionAssets = Field(default_factory=MissionAssets)
    airspace: Airspace | None = Field(
        default=None,
        description=(
            "Optional operational airspace descriptor used for SORA Air Risk "
            "classification and SAIL determination."
        ),
    )
    sora: SoraMitigations | None = Field(
        default=None,
        description=(
            "Optional SORA 2.5 M1(A/B/C) and M2 ground-risk declarations used "
            "to derive the final GRC and SAIL. Tactical mitigation determines "
            "TMPR compliance and is not an ARC reduction."
        ),
    )
    policy: MissionPolicyRef = Field(default_factory=MissionPolicyRef)
    link_systems: list[LinkSystemConfig] = Field(
        default_factory=list,
        description=(
            "Optional deterministic communication-link systems evaluated for "
            "mission feasibility. No live network calls are made."
        ),
    )
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
