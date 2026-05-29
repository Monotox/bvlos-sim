"""Core obstacle domain models.

GeoJSON and source-specific obstacle tags are adapter concerns. The estimator
uses geodetic coordinates and top-of-obstacle altitude in AMSL metres.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from estimator.core.spatial import validate_closed_ring


class ObstacleGeometryType(StrEnum):
    POINT = "point"
    LINE = "line"
    POLYGON = "polygon"


class ObstacleCoordinate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ObstaclePolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exterior: list[ObstacleCoordinate] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_exterior(self) -> "ObstaclePolygon":
        validate_closed_ring(self.exterior, "exterior")
        return self


class ObstacleGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ObstacleGeometryType
    points: list[ObstacleCoordinate] = Field(default_factory=list)
    polygon: ObstaclePolygon | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ObstacleGeometry":
        if self.type == ObstacleGeometryType.POINT and len(self.points) == 1:
            return self
        if self.type == ObstacleGeometryType.LINE and len(self.points) >= 2:
            return self
        if self.type == ObstacleGeometryType.POLYGON and self.polygon is not None:
            return self
        raise ValueError("obstacle geometry does not match its type")


class Obstacle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    geometry: ObstacleGeometry
    height_m: float = Field(ge=0, description="Obstacle top altitude in metres AMSL.")
    radius_m: float = Field(default=0.0, ge=0)
    uncertainty_m: float = Field(default=0.0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Obstacle",
    "ObstacleCoordinate",
    "ObstacleGeometry",
    "ObstacleGeometryType",
    "ObstaclePolygon",
]
