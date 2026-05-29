"""Energy reserve sensitivity sweep and Markdown rendering."""

from collections.abc import Sequence
from dataclasses import dataclass

from estimator import (
    EstimateStatus,
    EstimationOptions,
    GeofenceZone,
    GridPopulationProvider,
    GridTerrainProvider,
    LandingZone,
    ObstacleProvider,
    MissionEstimate,
    SpatiotemporalWindProvider,
    WindProvider,
    WindVector,
    try_estimate_mission_distance_time,
)
from schemas import MissionPlan, VehicleProfile

_FEASIBLE = "FEASIBLE"
_INFEASIBLE = "INFEASIBLE"
_ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class SensitivityLevel:
    parameter: str
    variation_label: str
    variation_value: float
    reserve_wh: float
    reserve_pct: float
    status: str


@dataclass(frozen=True, slots=True)
class _EastWindOverlayProvider:
    base_provider: WindProvider | None
    wind_east_delta_mps: float

    provider_id = "sensitivity_east_overlay"

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        if self.base_provider is None:
            base = WindVector(wind_east_mps=0.0, wind_north_mps=0.0)
        else:
            base = self.base_provider.wind_at(
                lat=lat,
                lon=lon,
                altitude_amsl_m=altitude_amsl_m,
                elapsed_time_s=elapsed_time_s,
            )
        return WindVector(
            wind_east_mps=base.wind_east_mps + self.wind_east_delta_mps,
            wind_north_mps=base.wind_north_mps,
        )


def _variation_series(steps: Sequence[int | float]) -> list[float]:
    magnitudes = sorted({abs(float(step)) for step in steps})
    if not magnitudes:
        magnitudes = [0.0]
    values = [-value for value in reversed(magnitudes) if value != 0.0]
    values.append(0.0)
    values.extend(value for value in magnitudes if value != 0.0)
    return values


def _percent_label(value: float) -> str:
    if value == 0.0:
        return "baseline"
    return f"{value:+.0f}%"


def _wind_label(value: float) -> str:
    if value == 0.0:
        return "baseline"
    return f"{value:+g} m/s"


def _status_for_result(result: MissionEstimate) -> str:
    if result.energy is None or result.status == EstimateStatus.ERROR:
        return _ERROR
    if result.status == EstimateStatus.SUCCESS and result.energy.is_feasible:
        return _FEASIBLE
    return _INFEASIBLE


def _level_from_result(
    *,
    parameter: str,
    variation_label: str,
    variation_value: float,
    result: MissionEstimate,
) -> SensitivityLevel:
    energy = result.energy
    if energy is None:
        return SensitivityLevel(
            parameter=parameter,
            variation_label=variation_label,
            variation_value=variation_value,
            reserve_wh=0.0,
            reserve_pct=0.0,
            status=_ERROR,
        )
    return SensitivityLevel(
        parameter=parameter,
        variation_label=variation_label,
        variation_value=variation_value,
        reserve_wh=energy.reserve_at_landing_wh,
        reserve_pct=energy.reserve_at_landing_percent,
        status=_status_for_result(result),
    )


def _estimate_level(
    *,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    parameter: str,
    variation_label: str,
    variation_value: float,
    options: EstimationOptions | None,
    wind_provider: WindProvider | None,
    terrain_provider: GridTerrainProvider | None,
    population_provider: GridPopulationProvider | None,
    obstacle_provider: ObstacleProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> SensitivityLevel:
    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        options=options,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    return _level_from_result(
        parameter=parameter,
        variation_label=variation_label,
        variation_value=variation_value,
        result=result,
    )


def _vehicle_with_cruise_power(
    vehicle: VehicleProfile, pct_delta: float
) -> VehicleProfile:
    factor = 1.0 + pct_delta / 100.0
    energy = vehicle.energy.model_copy(
        update={"cruise_power_w": vehicle.energy.cruise_power_w * factor}
    )
    return vehicle.model_copy(update={"energy": energy})


def _vehicle_with_battery_capacity(
    vehicle: VehicleProfile,
    pct_delta: float,
) -> VehicleProfile:
    factor = 1.0 + pct_delta / 100.0
    energy = vehicle.energy.model_copy(
        update={"battery_capacity_wh": vehicle.energy.battery_capacity_wh * factor}
    )
    return vehicle.model_copy(update={"energy": energy})


def _wind_provider_for_headwind(
    wind_provider: WindProvider | None,
    headwind_mps: float,
) -> WindProvider | None:
    if headwind_mps == 0.0:
        return wind_provider
    return _EastWindOverlayProvider(
        base_provider=wind_provider,
        wind_east_delta_mps=-headwind_mps,
    )


def run_sensitivity_sweep(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    power_steps: list[int],
    wind_steps: list[float],
    battery_steps: list[int],
    wind_provider: SpatiotemporalWindProvider | WindProvider | None = None,
    terrain_provider: GridTerrainProvider | None = None,
    population_provider: GridPopulationProvider | None = None,
    obstacle_provider: ObstacleProvider | None = None,
    geofences: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
    options: EstimationOptions | None = None,
) -> list[SensitivityLevel]:
    levels: list[SensitivityLevel] = []

    for pct_delta in _variation_series(power_steps):
        levels.append(
            _estimate_level(
                mission=mission,
                vehicle=_vehicle_with_cruise_power(vehicle, pct_delta),
                parameter="cruise_power",
                variation_label=_percent_label(pct_delta),
                variation_value=pct_delta,
                options=options,
                wind_provider=wind_provider,
                terrain_provider=terrain_provider,
                population_provider=population_provider,
                obstacle_provider=obstacle_provider,
                geofences=geofences,
                landing_zones=landing_zones,
            )
        )

    for headwind_mps in _variation_series(wind_steps):
        levels.append(
            _estimate_level(
                mission=mission,
                vehicle=vehicle,
                parameter="headwind",
                variation_label=_wind_label(headwind_mps),
                variation_value=headwind_mps,
                options=options,
                wind_provider=_wind_provider_for_headwind(wind_provider, headwind_mps),
                terrain_provider=terrain_provider,
                population_provider=population_provider,
                obstacle_provider=obstacle_provider,
                geofences=geofences,
                landing_zones=landing_zones,
            )
        )

    for pct_delta in _variation_series(battery_steps):
        levels.append(
            _estimate_level(
                mission=mission,
                vehicle=_vehicle_with_battery_capacity(vehicle, pct_delta),
                parameter="battery_capacity",
                variation_label=_percent_label(pct_delta),
                variation_value=pct_delta,
                options=options,
                wind_provider=wind_provider,
                terrain_provider=terrain_provider,
                population_provider=population_provider,
                obstacle_provider=obstacle_provider,
                geofences=geofences,
                landing_zones=landing_zones,
            )
        )

    return levels


def _fmt(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _overall_status(baseline: MissionEstimate, levels: list[SensitivityLevel]) -> str:
    if baseline.status != EstimateStatus.SUCCESS:
        return "INFEASIBLE"
    if any(level.status != _FEASIBLE or level.reserve_wh <= 0.0 for level in levels):
        return "MARGINAL"
    return "ROBUST"


def _status_description(status: str) -> str:
    if status == "ROBUST":
        return "all variations remain FEASIBLE with positive reserve"
    if status == "INFEASIBLE":
        return "baseline mission is infeasible — fix the base mission before interpreting variations"
    return "at least one variation becomes infeasible or sub-threshold"


def _section_rows(levels: list[SensitivityLevel], parameter: str) -> list[str]:
    rows = [
        "| Variation | Reserve Wh | Reserve % | Status |",
        "|-----------|------------|-----------|--------|",
    ]
    for level in levels:
        if level.parameter != parameter:
            continue
        rows.append(
            "| "
            f"{level.variation_label} | "
            f"{_fmt(level.reserve_wh)} | "
            f"{_fmt(level.reserve_pct)} | "
            f"{level.status} |"
        )
    return rows


def _baseline_line(baseline: MissionEstimate) -> str:
    if baseline.energy is None:
        return "Baseline reserve: not available"
    reserve_line = (
        f"Baseline reserve: "
        f"{_fmt(baseline.energy.reserve_at_landing_wh)} Wh "
        f"({_fmt(baseline.energy.reserve_at_landing_percent)}%)"
    )
    if baseline.failure is not None:
        return f"{reserve_line} — infeasible: {baseline.failure.code.value}"
    return reserve_line


def render_sensitivity_markdown(
    baseline: MissionEstimate,
    levels: list[SensitivityLevel],
    *,
    mission_id: str,
) -> str:
    status = _overall_status(baseline, levels)
    parameter_count = len({level.parameter for level in levels})
    levels_per_parameter = len(levels) // parameter_count if parameter_count else 0

    lines = [
        f"# Energy Reserve Sensitivity: {mission_id}",
        "",
        f"Status: {status} - {_status_description(status)}",
        _baseline_line(baseline),
        f"Baseline mission status: {baseline.status.value}",
        "",
        "## Cruise Power Variation",
        "",
        *_section_rows(levels, "cruise_power"),
        "",
        "## Headwind Variation (applied to all legs)",
        "",
        *_section_rows(levels, "headwind"),
        "",
        "## Battery Capacity Variation",
        "",
        *_section_rows(levels, "battery_capacity"),
        "",
        (
            "Sensitivity scan: "
            f"{parameter_count} parameters x {levels_per_parameter} levels = "
            f"{len(levels)} runs"
        ),
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "SensitivityLevel",
    "render_sensitivity_markdown",
    "run_sensitivity_sweep",
]
