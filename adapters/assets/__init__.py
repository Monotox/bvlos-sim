"""Static asset loading adapters."""

from adapters.assets.geofence_geojson import (
    GeofenceLoadError,
    GeofenceLoadStage,
    load_geofences,
)
from adapters.assets.landing_zone_geojson import (
    LandingZoneLoadError,
    LandingZoneLoadStage,
    load_landing_zones,
)
from adapters.assets.terrain_grid import TerrainGridLoadError, load_terrain_grid
from adapters.assets.wind_grid import WindGridLoadError, load_wind_grid

__all__ = [
    "GeofenceLoadError",
    "GeofenceLoadStage",
    "LandingZoneLoadError",
    "LandingZoneLoadStage",
    "TerrainGridLoadError",
    "WindGridLoadError",
    "load_geofences",
    "load_landing_zones",
    "load_terrain_grid",
    "load_wind_grid",
]