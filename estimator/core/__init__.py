"""Estimator public enums, results, options, constants, and typed errors."""

from estimator.core.errors import EstimatorError
from estimator.core.errors import EstimatorInfeasibleError
from estimator.core.errors import InvalidEstimatorInputError
from estimator.core.errors import UnsupportedEstimatorFeatureError
from estimator.core.enums import EnergyPowerSource
from estimator.core.enums import EstimateStatus
from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
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
from estimator.core.constants import DEFAULT_MAX_CRAB_ANGLE_DEG
from estimator.core.constants import DEFAULT_MIN_GROUNDSPEED_MPS
from estimator.core.constants import EPS_DISTANCE_M

__all__ = [
    "DEFAULT_MAX_CRAB_ANGLE_DEG",
    "DEFAULT_MIN_GROUNDSPEED_MPS",
    "EPS_DISTANCE_M",
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
    "SpeedSource",
    "UnsupportedEstimatorFeatureError",
    "WarningCode",
    "WindVector",
]
