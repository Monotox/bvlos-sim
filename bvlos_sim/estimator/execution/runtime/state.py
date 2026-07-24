"""Execution state models used during mission expansion."""

from dataclasses import dataclass, field

from bvlos_sim.estimator.core.enums import LegPhase


@dataclass
class FlightState:
    lat: float
    lon: float
    alt_amsl_m: float
    elapsed_time_s: float
    last_track_deg: float | None = field(default=None)


@dataclass
class TargetPhase:
    target_lat: float
    target_lon: float
    target_alt_amsl_m: float
    phase: LegPhase
