"""Energy drain curves and position interpolation along a mission route."""

import math
from dataclasses import dataclass

from pyproj import Geod

from estimator.core.results import EnergyLegEstimate, LegEstimate, MissionEstimate

_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True, slots=True)
class EnergyLegDrain:
    duration_s: float
    energy_wh: float


@dataclass(frozen=True, slots=True)
class EnergyDrainCurve:
    legs: tuple[EnergyLegDrain, ...]

    @classmethod
    def from_estimate(cls, estimate: MissionEstimate) -> "EnergyDrainCurve | None":
        if estimate.energy is None:
            return None
        energy_by_leg = _energy_by_leg_index(estimate.energy.legs)
        legs = tuple(
            EnergyLegDrain(
                duration_s=leg.time_s,
                energy_wh=energy_by_leg.get(leg.leg_index, 0.0),
            )
            for leg in estimate.legs
        )
        if not legs:
            return None
        return cls(legs=legs)

    @property
    def total_duration_s(self) -> float:
        return sum(leg.duration_s for leg in self.legs)

    def energy_consumed_at(self, elapsed_time_s: float) -> float:
        elapsed = 0.0
        consumed = 0.0
        for leg in self.legs:
            next_elapsed = elapsed + leg.duration_s
            next_consumed = consumed + leg.energy_wh
            if elapsed_time_s <= next_elapsed:
                return _interpolated_energy(
                    elapsed_time_s=elapsed_time_s,
                    leg_start_s=elapsed,
                    leg_duration_s=leg.duration_s,
                    consumed_before_leg_wh=consumed,
                    leg_energy_wh=leg.energy_wh,
                    consumed_after_leg_wh=next_consumed,
                )
            elapsed = next_elapsed
            consumed = next_consumed
        return consumed


@dataclass(frozen=True, slots=True)
class PositionInterpolator:
    legs: list[LegEstimate]
    fallback_lat: float
    fallback_lon: float

    def at(self, elapsed_time_s: float) -> tuple[float, float]:
        if not self.legs:
            return self.fallback_lat, self.fallback_lon
        elapsed = 0.0
        for leg in self.legs:
            next_elapsed = elapsed + leg.time_s
            if elapsed_time_s <= next_elapsed:
                return _interpolate_leg_position(
                    leg,
                    elapsed_time_s=elapsed_time_s,
                    leg_start_s=elapsed,
                )
            elapsed = next_elapsed
        last_leg = self.legs[-1]
        return last_leg.end_lat, last_leg.end_lon


def timeline_steps(t_max: float, dt_s: float) -> list[float]:
    if t_max <= 0.0:
        return [0.0]
    step_count = math.floor(t_max / dt_s)
    steps = [i * dt_s for i in range(step_count + 1)]
    if t_max - steps[-1] > 1e-9:
        steps.append(t_max)
    return steps


def _energy_by_leg_index(energy_legs: list[EnergyLegEstimate]) -> dict[int, float]:
    return {e.leg_index: e.energy_wh for e in energy_legs}


def _interpolated_energy(
    *,
    elapsed_time_s: float,
    leg_start_s: float,
    leg_duration_s: float,
    consumed_before_leg_wh: float,
    leg_energy_wh: float,
    consumed_after_leg_wh: float,
) -> float:
    if leg_duration_s <= 0.0:
        return consumed_after_leg_wh
    fraction = (elapsed_time_s - leg_start_s) / leg_duration_s
    return consumed_before_leg_wh + (leg_energy_wh * _clamp_unit(fraction))


def _interpolate_leg_position(
    leg: LegEstimate,
    *,
    elapsed_time_s: float,
    leg_start_s: float,
) -> tuple[float, float]:
    if leg.time_s <= 0.0:
        return leg.end_lat, leg.end_lon
    fraction = _clamp_unit((elapsed_time_s - leg_start_s) / leg.time_s)
    forward_azimuth_deg, _back_azimuth_deg, distance_m = _GEOD.inv(
        leg.start_lon,
        leg.start_lat,
        leg.end_lon,
        leg.end_lat,
    )
    lon, lat, _back_azimuth_deg = _GEOD.fwd(
        leg.start_lon,
        leg.start_lat,
        forward_azimuth_deg,
        distance_m * fraction,
    )
    return lat, lon


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))
