"""Core landing-zone domain models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from estimator.core.spatial import validate_closed_ring


class LandingZoneCoordinate(BaseModel):
    """Geodetic coordinate in decimal degrees."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LandingZonePolygon(BaseModel):
    """Landing-zone polygon rings in domain coordinate order."""

    model_config = ConfigDict(extra="forbid")

    exterior: list[LandingZoneCoordinate] = Field(min_length=4)
    holes: list[list[LandingZoneCoordinate]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rings(self) -> "LandingZonePolygon":
        validate_closed_ring(self.exterior, "exterior")
        for hole_index, hole in enumerate(self.holes):
            validate_closed_ring(hole, f"holes.{hole_index}")
        return self


class LandingZoneGeometry(BaseModel):
    """Supported static landing-zone geometry."""

    model_config = ConfigDict(extra="forbid")

    points: list[LandingZoneCoordinate] = Field(default_factory=list)
    polygons: list[LandingZonePolygon] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_has_geometry(self) -> "LandingZoneGeometry":
        if self.points or self.polygons:
            return self
        raise ValueError("landing zone geometry must contain a point or polygon")


class LandingZone(BaseModel):
    """A named static landing zone."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    geometry: LandingZoneGeometry
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "LandingZone",
    "LandingZoneCoordinate",
    "LandingZoneGeometry",
    "LandingZonePolygon",
]
