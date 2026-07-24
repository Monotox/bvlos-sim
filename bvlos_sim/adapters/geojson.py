"""Compatibility exports for static GeoJSON asset helpers."""

from bvlos_sim.adapters.assets.geojson import (
    GeoJsonEntry,
    GeoJsonErrorFactory,
    GeoJsonGeometryType,
    GeoJsonLoadStage,
    UnsupportedGeometryErrorFactory,
    geojson_entries_from_root,
    polygon_payload_from_coordinates,
    polygon_payloads_from_geometry,
    position_payload_from_coordinates,
    read_geojson_object,
    ring_payload_from_coordinates,
)

__all__ = [
    "GeoJsonEntry",
    "GeoJsonErrorFactory",
    "GeoJsonGeometryType",
    "GeoJsonLoadStage",
    "UnsupportedGeometryErrorFactory",
    "geojson_entries_from_root",
    "polygon_payload_from_coordinates",
    "polygon_payloads_from_geometry",
    "position_payload_from_coordinates",
    "read_geojson_object",
    "ring_payload_from_coordinates",
]