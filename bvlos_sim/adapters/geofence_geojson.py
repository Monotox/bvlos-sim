"""Compatibility exports for static geofence asset loading."""

from bvlos_sim.adapters.assets.geofence_geojson import (
    GeofenceLoadError,
    GeofenceLoadStage,
    load_geofences,
)

__all__ = ["GeofenceLoadError", "GeofenceLoadStage", "load_geofences"]