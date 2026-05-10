"""Core geofence domain models.

These models intentionally use lat/lon domain coordinates. External formats
such as GeoJSON are converted in adapters before reaching the estimator core.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from estimator.core.enums import GeofenceKind
from estimator.core.spatial import validate_closed_ring


class GeofenceCoordinate(BaseModel):
    """Geodetic coordinate in decimal degrees."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeofencePolygon(BaseModel):
    """Polygon rings in domain coordinate order.

    Rings must be closed. The exterior ring is followed by zero or more holes.
    """

    model_config = ConfigDict(extra="forbid")

    exterior: list[GeofenceCoordinate] = Field(min_length=4)
    holes: list[list[GeofenceCoordinate]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rings(self) -> "GeofencePolygon":
        validate_closed_ring(self.exterior, "exterior")
        for hole_index, hole in enumerate(self.holes):
            validate_closed_ring(hole, f"holes.{hole_index}")
        return self


class GeofenceGeometry(BaseModel):
    """Supported static geofence geometry.

    A single polygon and a multipolygon are both represented as one or more
    polygons. GeoJSON geometry type details are adapter concerns.
    """

    model_config = ConfigDict(extra="forbid")

    polygons: list[GeofencePolygon] = Field(min_length=1)


class GeofenceZone(BaseModel):
    """A named static geofence zone."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: GeofenceKind
    geometry: GeofenceGeometry
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "GeofenceCoordinate",
    "GeofenceGeometry",
    "GeofencePolygon",
    "GeofenceZone",
]
