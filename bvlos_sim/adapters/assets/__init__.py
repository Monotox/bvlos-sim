"""Static asset loading adapters."""

from bvlos_sim.adapters.assets.geofence_geojson import (
    GeofenceLoadError,
    GeofenceLoadStage,
    load_geofences,
)
from bvlos_sim.adapters.assets.landing_zone_geojson import (
    LandingZoneLoadError,
    LandingZoneLoadStage,
    load_landing_zones,
)
from bvlos_sim.adapters.assets.terrain_grid import TerrainGridLoadError, load_terrain_grid
from bvlos_sim.adapters.assets.wind_grid import WindGridLoadError, load_wind_grid

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