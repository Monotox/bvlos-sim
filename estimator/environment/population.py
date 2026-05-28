"""Population-density provider abstractions."""

from typing import Protocol


class PopulationProvider(Protocol):
    provider_id: str

    def density_at(self, lat: float, lon: float) -> float | None:
        """Return population density in people/km^2, or None outside coverage."""


class GridPopulationProvider:
    """Provider backed by a uniform population-density grid.

    The grid is indexed as density_ppl_km2[row][col] where row increases with
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
        density_ppl_km2: list[list[float]],
    ) -> None:
        self._origin_lat = origin_lat
        self._origin_lon = origin_lon
        self._step_lat = step_lat_deg
        self._step_lon = step_lon_deg
        self._density: tuple[tuple[float, ...], ...] = tuple(
            tuple(row) for row in density_ppl_km2
        )
        self._rows = len(self._density)
        self._cols = len(self._density[0]) if self._density else 0

    def density_at(self, lat: float, lon: float) -> float | None:
        r = (lat - self._origin_lat) / self._step_lat
        c = (lon - self._origin_lon) / self._step_lon
        r0, c0 = int(r), int(c)
        if r0 < 0 or c0 < 0 or r0 >= self._rows - 1 or c0 >= self._cols - 1:
            return None
        t, u = r - r0, c - c0
        d = self._density
        return (
            (1 - t) * (1 - u) * d[r0][c0]
            + (1 - t) * u * d[r0][c0 + 1]
            + t * (1 - u) * d[r0 + 1][c0]
            + t * u * d[r0 + 1][c0 + 1]
        )


def population_provider_id(provider: PopulationProvider) -> str:
    pid = getattr(provider, "provider_id", None)
    if isinstance(pid, str) and pid:
        return pid
    return "custom"
