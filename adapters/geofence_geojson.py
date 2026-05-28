"""Compatibility exports for static geofence asset loading."""

from adapters.assets.geofence_geojson import (
    GeofenceLoadError,
    GeofenceLoadStage,
    load_geofences,
)

__all__ = ["GeofenceLoadError", "GeofenceLoadStage", "load_geofences"]