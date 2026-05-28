"""Compatibility exports for static landing-zone asset loading."""

from adapters.assets.landing_zone_geojson import (
    LandingZoneLoadError,
    LandingZoneLoadStage,
    load_landing_zones,
)

__all__ = ["LandingZoneLoadError", "LandingZoneLoadStage", "load_landing_zones"]