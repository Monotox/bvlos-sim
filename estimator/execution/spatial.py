"""Shared Shapely conversion helpers for static spatial inputs."""

from collections.abc import Sequence
from typing import Protocol

from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


class CoordinateLike(Protocol):
    lat: float
    lon: float


class PolygonLike(Protocol):
    exterior: Sequence[CoordinateLike]
    holes: Sequence[Sequence[CoordinateLike]]


def polygon_to_shapely(polygon: PolygonLike) -> Polygon:
    exterior = [(point.lon, point.lat) for point in polygon.exterior]
    holes = [[(point.lon, point.lat) for point in hole] for hole in polygon.holes]
    return Polygon(exterior, holes)


def polygon_set_to_shapely(polygons: Sequence[PolygonLike]) -> BaseGeometry:
    compiled = [polygon_to_shapely(polygon) for polygon in polygons]
    if len(compiled) == 1:
        return compiled[0]
    return MultiPolygon(compiled)


def polygon_set_to_geometry_list(polygons: Sequence[PolygonLike]) -> list[BaseGeometry]:
    if not polygons:
        return []
    return [polygon_set_to_shapely(polygons)]


__all__ = [
    "CoordinateLike",
    "PolygonLike",
    "polygon_set_to_geometry_list",
    "polygon_set_to_shapely",
    "polygon_to_shapely",
]
