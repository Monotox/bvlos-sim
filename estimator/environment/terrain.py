"""Terrain elevation provider abstractions."""

from typing import Protocol


class TerrainProvider(Protocol):
    provider_id: str

    def elevation_at(self, lat: float, lon: float) -> float | None:
        """Return ground elevation AMSL in metres, or None if outside coverage."""


class ConstantElevationProvider:
    """Provider returning a fixed ground elevation AMSL for all positions."""

    provider_id = "constant"

    def __init__(self, elevation_m: float) -> None:
        self._elevation_m = float(elevation_m)

    def elevation_at(self, lat: float, lon: float) -> float | None:
        return self._elevation_m


class GridTerrainProvider:
    """Provider backed by a uniform elevation grid with bilinear interpolation.

    The grid is indexed as elevations_m[row][col] where row increases with
    increasing latitude and col increases with increasing longitude.
    Returns None for positions outside grid bounds.
    """

    provider_id = "uniform_grid"

    def __init__(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        step_lat_deg: float,
        step_lon_deg: float,
        elevations_m: list[list[float]],
    ) -> None:
        self._origin_lat = origin_lat
        self._origin_lon = origin_lon
        self._step_lat = step_lat_deg
        self._step_lon = step_lon_deg
        self._elevations: tuple[tuple[float, ...], ...] = tuple(
            tuple(row) for row in elevations_m
        )
        self._rows = len(self._elevations)
        self._cols = len(self._elevations[0]) if self._elevations else 0

    def elevation_at(self, lat: float, lon: float) -> float | None:
        r = (lat - self._origin_lat) / self._step_lat
        c = (lon - self._origin_lon) / self._step_lon
        r0, c0 = int(r), int(c)
        if r0 < 0 or c0 < 0 or r0 >= self._rows - 1 or c0 >= self._cols - 1:
            return None
        t, u = r - r0, c - c0
        e = self._elevations
        return (
            (1 - t) * (1 - u) * e[r0][c0]
            + (1 - t) * u * e[r0][c0 + 1]
            + t * (1 - u) * e[r0 + 1][c0]
            + t * u * e[r0 + 1][c0 + 1]
        )


def terrain_provider_id(provider: TerrainProvider) -> str:
    pid = getattr(provider, "provider_id", None)
    if isinstance(pid, str) and pid:
        return pid
    return "custom"
