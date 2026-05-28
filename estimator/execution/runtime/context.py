"""Execution context used while expanding mission route items."""

from dataclasses import dataclass
from math import sqrt
from typing import NoReturn

from pyproj import Geod

from estimator.core.enums import FailureCode, FailureKind, LegPhase, WarningCode
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.results import (
    EstimatorContextValue,
    EstimatorFailure,
    EstimatorWarning,
    LegEstimate,
    WindVector,
)
from estimator.environment.population import GridPopulationProvider
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.runtime.capabilities import Capabilities
from estimator.execution.runtime.failure_translation import error_from_failure
from estimator.execution.runtime.options import ResolvedOptions
from estimator.execution.runtime.state import FlightState
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile


@dataclass
class EstimationContext:
    mission: MissionPlan
    vehicle: VehicleProfile
    wind_provider: WindProvider
    terrain_provider: TerrainProvider | None
    population_provider: GridPopulationProvider | None
    geod: Geod
    capabilities: Capabilities
    geofences: tuple[GeofenceZone, ...] | None
    landing_zones: tuple[LandingZone, ...] | None
    resolved_options: ResolvedOptions
    max_crab_angle_deg: float
    metadata: dict[str, EstimatorContextValue]
    warnings: list[EstimatorWarning]
    route_legs: list[LegEstimate]
    state: FlightState

    @property
    def current_leg_index(self) -> int:
        return len(self.route_legs)

    def append_leg(self, leg: LegEstimate) -> None:
        self.route_legs.append(leg)
        self.state.lat = leg.end_lat
        self.state.lon = leg.end_lon
        self.state.alt_amsl_m = leg.end_alt_amsl_m
        self.state.elapsed_time_s += leg.time_s
        if leg.ground_track_deg is not None:
            self.state.last_track_deg = leg.ground_track_deg
        elif leg.phase == LegPhase.LOITER_DWELL:
            # Orbit exit heading is arbitrary; reset so the next leg never
            # inherits a stale inbound track as its turn-entry heading.
            self.state.last_track_deg = None

    def add_warning(
        self,
        code: WarningCode,
        message: str,
        *,
        route_item_index: int | None,
        route_item_id: str | None,
        leg_index: int | None = None,
    ) -> None:
        self.warnings.append(
            EstimatorWarning(
                code=code,
                message=message,
                leg_index=self.current_leg_index if leg_index is None else leg_index,
                route_item_index=route_item_index,
                route_item_id=route_item_id,
            )
        )

    @staticmethod
    def wind_speed(wind: WindVector) -> float:
        return sqrt(wind.wind_east_mps**2 + wind.wind_north_mps**2)

    def fail(
        self,
        *,
        kind: FailureKind,
        code: FailureCode,
        message: str,
        route_item_index: int | None,
        route_item_id: str | None,
        context: dict[str, EstimatorContextValue] | None = None,
        leg_index: int | None = None,
    ) -> NoReturn:
        failure = EstimatorFailure(
            kind=kind,
            code=code,
            message=message,
            leg_index=self.current_leg_index if leg_index is None else leg_index,
            route_item_index=route_item_index,
            route_item_id=route_item_id,
            context=context or {},
        )
        raise error_from_failure(
            failure,
            partial_legs=self.route_legs,
            warnings=self.warnings,
            metadata=self.metadata,
        )
