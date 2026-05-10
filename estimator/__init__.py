"""Public estimator API."""

from estimator.core.errors import EstimatorError
from estimator.core.errors import EstimatorInfeasibleError
from estimator.core.errors import InvalidEstimatorInputError
from estimator.core.errors import UnsupportedEstimatorFeatureError
from estimator.core.enums import EnergyPowerSource
from estimator.core.enums import EstimateStatus
from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.core.enums import FidelityMode
from estimator.core.enums import GeofenceKind
from estimator.core.enums import LegPhase
from estimator.core.enums import SpeedSource
from estimator.core.enums import WarningCode
from estimator.core.geofence import GeofenceCoordinate
from estimator.core.geofence import GeofenceGeometry
from estimator.core.geofence import GeofencePolygon
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.landing_zone import LandingZoneCoordinate
from estimator.core.landing_zone import LandingZoneGeometry
from estimator.core.landing_zone import LandingZonePolygon
from estimator.core.options import EstimationOptions
from estimator.core.results import EnergyEstimate
from estimator.core.results import EnergyLegEstimate
from estimator.core.results import EstimatorFailure
from estimator.core.results import EstimatorWarning
from estimator.core.results import GeofenceConflict
from estimator.core.results import GeofenceEstimate
from estimator.core.results import LandingZoneEstimate
from estimator.core.results import LandingZoneStateReachability
from estimator.core.results import LegEstimate
from estimator.core.results import MissionEstimate
from estimator.core.results import WindVector
from estimator.core.scenario import (
    AssertionOutcome,
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
    ScenarioStatus,
    TimelinePoint,
)
from estimator.environment.wind import ConstantWindProvider
from estimator.environment.wind import LayeredWindProvider
from estimator.environment.wind import WindLayer
from estimator.environment.wind import WindProvider
from estimator.execution.engine import estimate_mission_distance_time
from estimator.execution.engine import try_estimate_mission_distance_time
from estimator.execution.scenario import run_scenario

__all__ = [
    "AssertionOutcome",
    "CommsLinkPolicyOutcome",
    "ConstantWindProvider",
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
    "ScenarioEventOutcome",
    "ScenarioResult",
    "ScenarioStatus",
    "SpeedSource",
    "TimelinePoint",
    "UnsupportedEstimatorFeatureError",
    "WarningCode",
    "WindProvider",
    "WindVector",
    "estimate_mission_distance_time",
    "run_scenario",
    "try_estimate_mission_distance_time",
]
