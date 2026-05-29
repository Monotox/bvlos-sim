"""Public estimator result models.

Units and conventions:
- Resolved altitudes are AMSL meters.
- Distances are meters.
- Times are seconds.
- Speeds are meters per second.
- Energy values are watt-hours.
- Power values are watts.
- Wind vectors describe air-mass motion toward east/north.
- Angles are true degrees clockwise from north.
- `crab_angle_deg` is signed heading offset from desired ground track.
- Phase-inapplicable fields must be None.
"""

from pydantic import BaseModel, ConfigDict, Field

from estimator.core.enums import (
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    FailureKind,
    GeofenceKind,
    LegPhase,
    SpeedSource,
    WarningCode,
)


class WindVector(BaseModel):
    """Wind vector in EN frame (m/s)."""

    model_config = ConfigDict(extra="forbid")

    wind_east_mps: float = Field(
        description="Wind east component (m/s), positive toward east."
    )
    wind_north_mps: float = Field(
        description="Wind north component (m/s), positive toward north."
    )


class EstimatorWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: WarningCode
    message: str
    leg_index: int | None = None
    route_item_index: int | None = None
    route_item_id: str | None = None


EstimatorContextValue = str | int | float | bool | None


class EstimatorFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FailureKind
    code: FailureCode
    message: str
    leg_index: int | None = None
    route_item_index: int | None = None
    route_item_id: str | None = None
    context: dict[str, EstimatorContextValue] = Field(default_factory=dict)


class LegEstimate(BaseModel):
    """Per-phase estimate record.

    A single mission route item may expand into multiple leg records.
    """

    model_config = ConfigDict(extra="forbid")

    leg_index: int
    route_item_index: int
    route_item_id: str | None
    action: str
    phase: LegPhase
    start_lat: float
    start_lon: float
    start_alt_amsl_m: float
    end_lat: float
    end_lon: float
    end_alt_amsl_m: float
    horizontal_distance_m: float
    vertical_delta_m: float
    vertical_distance_m: float
    path_distance_m: float
    time_s: float
    tas_mps: float | None = None
    groundspeed_mps: float | None = None
    ground_track_deg: float | None = None
    required_heading_deg: float | None = None
    crab_angle_deg: float | None = None
    wind_east_mps: float | None = None
    wind_north_mps: float | None = None
    wind_speed_mps: float | None = None
    wind_along_track_mps: float | None = None
    wind_cross_track_mps: float | None = None
    speed_source: SpeedSource | None = None
    warnings: list[WarningCode] = Field(default_factory=list)


class EnergyLegEstimate(BaseModel):
    """Per-leg deterministic energy estimate."""

    model_config = ConfigDict(extra="forbid")

    leg_index: int
    route_item_index: int
    route_item_id: str | None
    phase: LegPhase
    time_s: float
    power_w: float
    power_source: EnergyPowerSource
    energy_wh: float


class EnergyEstimate(BaseModel):
    """Mission-level deterministic energy and reserve result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    total_energy_wh: float
    battery_capacity_wh: float
    usable_energy_wh: float
    reserve_threshold_percent: float
    reserve_threshold_wh: float
    reserve_at_landing_wh: float
    reserve_at_landing_percent: float
    legs: list[EnergyLegEstimate] = Field(default_factory=list)


class ResourceSystemEstimate(BaseModel):
    """Per-resource deterministic feasibility result."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    kind: str
    priority: int
    is_feasible: bool
    demand_energy_wh: float
    available_energy_wh: float | None = None
    reserve_threshold_wh: float | None = None
    reserve_after_resource_wh: float | None = None
    peak_power_w: float
    available_power_w: float | None = None
    route_distance_m: float
    max_route_distance_m: float | None = None
    route_time_s: float
    max_route_time_s: float | None = None
    max_observed_home_distance_m: float
    max_tether_length_m: float | None = None
    limiting_reason: str | None = None


class ResourceEstimate(BaseModel):
    """Mission-level deterministic resource feasibility result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    selected_resource_id: str | None = None
    total_demand_wh: float
    peak_power_w: float
    route_distance_m: float
    route_time_s: float
    max_observed_home_distance_m: float
    systems: list[ResourceSystemEstimate] = Field(default_factory=list)


class LinkSystemEstimate(BaseModel):
    """Per-link deterministic feasibility result."""

    model_config = ConfigDict(extra="forbid")

    link_id: str
    kind: str
    required: bool
    priority: int
    is_feasible: bool
    availability: str
    max_range_m: float | None = None
    max_observed_range_m: float
    limiting_reason: str | None = None


class LinkEstimate(BaseModel):
    """Mission-level deterministic communication-link feasibility result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    selected_link_id: str | None = None
    required_link_count: int
    available_link_count: int
    max_observed_range_m: float
    systems: list[LinkSystemEstimate] = Field(default_factory=list)


class GeofenceConflict(BaseModel):
    """Route-vs-geofence conflict record."""

    model_config = ConfigDict(extra="forbid")

    code: FailureCode
    message: str
    zone_id: str | None = None
    zone_kind: GeofenceKind
    leg_index: int
    route_item_index: int
    route_item_id: str | None = None


class GeofenceEstimate(BaseModel):
    """Mission-level static geofence feasibility result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    checked_zone_count: int
    checked_leg_count: int
    conflicts: list[GeofenceConflict] = Field(default_factory=list)


class LandingZoneStateReachability(BaseModel):
    """Reachability record from one route state to static landing zones."""

    model_config = ConfigDict(extra="forbid")

    state_index: int
    leg_index: int
    route_item_index: int
    route_item_id: str | None = None
    lat: float
    lon: float
    altitude_amsl_m: float
    nearest_zone_id: str | None = None
    nearest_zone_distance_m: float | None = None
    reachable_zone_id: str | None = None
    reachable_zone_distance_m: float | None = None
    divert_energy_wh: float | None = None
    energy_remaining_before_divert_wh: float
    reserve_after_divert_wh: float | None = None
    reserve_after_divert_percent: float | None = None
    is_reachable: bool
    reserve_ok: bool
    available_zone_count: int | None = None
    code: FailureCode | None = None
    message: str | None = None


class LandingZoneEstimate(BaseModel):
    """Mission-level landing-zone reachability result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    checked_zone_count: int
    checked_state_count: int
    max_allowed_distance_m: float | None = None
    reserve_threshold_percent: float
    reserve_threshold_wh: float
    unavailable_zone_ids: list[str] = Field(default_factory=list)
    states: list[LandingZoneStateReachability] = Field(default_factory=list)


class GroundRiskLegEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leg_index: int
    route_item_id: str | None
    max_density_ppl_km2: float
    igrc: int


class GroundRiskEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characteristic_dimension_m: float
    mission_igrc: int
    legs: list[GroundRiskLegEstimate]


class WeatherViolation(BaseModel):
    """A single weather-limit breach on a route leg."""

    model_config = ConfigDict(extra="forbid")

    code: FailureCode
    message: str
    leg_index: int
    route_item_index: int
    route_item_id: str | None = None
    observed_mps: float
    limit_mps: float


class WeatherEstimate(BaseModel):
    """Mission-level weather-minimums feasibility result."""

    model_config = ConfigDict(extra="forbid")

    is_feasible: bool
    checked_leg_count: int
    max_wind_mps: float | None = None
    max_crosswind_mps: float | None = None
    max_gust_mps: float | None = None
    worst_wind_speed_mps: float | None = None
    worst_crosswind_mps: float | None = None
    worst_leg_index: int | None = None
    worst_route_item_id: str | None = None
    violations: list[WeatherViolation] = Field(default_factory=list)


class MissionEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EstimateStatus
    total_horizontal_distance_m: float
    total_vertical_distance_m: float
    total_path_distance_m: float
    total_time_s: float
    totals_are_partial: bool
    legs: list[LegEstimate] = Field(default_factory=list)
    energy: EnergyEstimate | None = None
    resource: ResourceEstimate | None = None
    link: LinkEstimate | None = None
    geofence: GeofenceEstimate | None = None
    landing_zone: LandingZoneEstimate | None = None
    ground_risk: GroundRiskEstimate | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    weather: WeatherEstimate | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    warnings: list[EstimatorWarning] = Field(default_factory=list)
    failure: EstimatorFailure | None = None
    metadata: dict[str, EstimatorContextValue] = Field(default_factory=dict)
