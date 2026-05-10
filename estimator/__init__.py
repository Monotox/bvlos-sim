"""Public estimator API."""

from estimator.core.enums import (
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    FailureKind,
    FidelityMode,
    GeofenceKind,
    LegPhase,
    SpeedSource,
    WarningCode,
)
from estimator.core.errors import (
    EstimatorError,
    EstimatorInfeasibleError,
    InvalidEstimatorInputError,
    UnsupportedEstimatorFeatureError,
)
from estimator.core.geofence import (
    GeofenceCoordinate,
    GeofenceGeometry,
    GeofencePolygon,
    GeofenceZone,
)
from estimator.core.landing_zone import (
    LandingZone,
    LandingZoneCoordinate,
    LandingZoneGeometry,
    LandingZonePolygon,
)
from estimator.core.options import EstimationOptions
from estimator.core.results import (
    EnergyEstimate,
    EnergyLegEstimate,
    EstimatorFailure,
    EstimatorWarning,
    GeofenceConflict,
    GeofenceEstimate,
    LandingZoneEstimate,
    LandingZoneStateReachability,
    LegEstimate,
    MissionEstimate,
    WindVector,
)
from estimator.core.scenario import (
    AssertionOutcome,
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
    ScenarioStatus,
    TimelinePoint,
)
from estimator.environment.terrain import (
    ConstantElevationProvider,
    GridTerrainProvider,
    TerrainProvider,
)
from estimator.environment.wind import (
    ConstantWindProvider,
    LayeredWindProvider,
    SpatiotemporalWindProvider,
    WindLayer,
    WindProvider,
)
from estimator.execution.engine import (
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.execution.scenario import run_scenario

__all__ = [
    "AssertionOutcome",
    "CommsLinkPolicyOutcome",
    "ConstantElevationProvider",
    "ConstantWindProvider",
    "GridTerrainProvider",
    "LayeredWindProvider",
    "WindLayer",
    "EnergyEstimate",
    "EnergyLegEstimate",
    "EnergyPowerSource",
    "EstimateStatus",
    "EstimationOptions",
    "EstimatorError",
    "EstimatorFailure",
    "EstimatorInfeasibleError",
    "EstimatorWarning",
    "FailureCode",
    "FailureKind",
    "FidelityMode",
    "GeofenceConflict",
    "GeofenceCoordinate",
    "GeofenceEstimate",
    "GeofenceGeometry",
    "GeofenceKind",
    "GeofencePolygon",
    "GeofenceZone",
    "InvalidEstimatorInputError",
    "LandingZone",
    "LandingZoneCoordinate",
    "LandingZoneEstimate",
    "LandingZoneGeometry",
    "LandingZonePolygon",
    "LandingZoneStateReachability",
    "LegPhase",
    "LegEstimate",
    "MissionEstimate",
    "ScenarioAssertionResult",
    "SpatiotemporalWindProvider",
    "ScenarioEventOutcome",
    "ScenarioResult",
    "ScenarioStatus",
    "SpeedSource",
    "TimelinePoint",
    "TerrainProvider",
    "UnsupportedEstimatorFeatureError",
    "WarningCode",
    "WindProvider",
    "WindVector",
    "estimate_mission_distance_time",
    "run_scenario",
    "try_estimate_mission_distance_time",
]
