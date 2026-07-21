"""Terrain elevation provider abstractions."""

import math

from pyproj import Geod

from typing import Protocol


def _finite_numeric_input(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a finite number, not a boolean")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


class TerrainProvider(Protocol):
    provider_id: str

    def elevation_at(self, lat: float, lon: float) -> float | None:
        """Return ground elevation AMSL in metres, or None if outside coverage."""

    def conservative_max_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
        """Return a conservative maximum or None when it cannot be proven."""

    def conservative_min_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
        """Return a conservative minimum or None when it cannot be proven."""


class ConstantElevationProvider:
    """Provider returning a fixed ground elevation AMSL for all positions."""

    provider_id = "constant"

    def __init__(self, elevation_m: float) -> None:
        value = _finite_numeric_input(elevation_m, label="elevation_m")
        self._elevation_m = value

    def elevation_at(self, lat: float, lon: float) -> float | None:
        return self._elevation_m

    def conservative_max_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
        return self._elevation_m

    def conservative_min_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
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
        self._origin_lat = _finite_numeric_input(origin_lat, label="origin_lat")
        self._origin_lon = _finite_numeric_input(origin_lon, label="origin_lon")
        self._step_lat = _finite_numeric_input(step_lat_deg, label="step_lat_deg")
        self._step_lon = _finite_numeric_input(step_lon_deg, label="step_lon_deg")
        self._elevations: tuple[tuple[float, ...], ...] = tuple(
            tuple(_finite_numeric_input(value, label="elevations_m") for value in row)
            for row in elevations_m
        )
        self._rows = len(self._elevations)
        self._cols = len(self._elevations[0]) if self._elevations else 0
        self._validate()

    def _validate(self) -> None:
        scalars = (
            self._origin_lat,
            self._origin_lon,
            self._step_lat,
            self._step_lon,
        )
        if not all(math.isfinite(value) for value in scalars):
            raise ValueError("terrain grid origin and steps must be finite")
        if not -90.0 <= self._origin_lat <= 90.0:
            raise ValueError("terrain grid origin_lat must be between -90 and 90")
        if not -180.0 <= self._origin_lon <= 180.0:
            raise ValueError("terrain grid origin_lon must be between -180 and 180")
        if self._step_lat <= 0.0 or self._step_lon <= 0.0:
            raise ValueError("terrain grid steps must be positive")
        if self._rows < 2 or self._cols < 2:
            raise ValueError("terrain grid must contain at least two rows and columns")
        if any(len(row) != self._cols for row in self._elevations):
            raise ValueError("terrain grid rows must have equal length")
        if any(not math.isfinite(value) for row in self._elevations for value in row):
            raise ValueError("terrain grid elevations must be finite")
        if self._origin_lat + self._step_lat * (self._rows - 1) > 90.0:
            raise ValueError("terrain grid extends beyond latitude 90")
        if self._origin_lon + self._step_lon * (self._cols - 1) > 180.0:
            raise ValueError("terrain grid extends beyond longitude 180")

    def elevation_at(self, lat: float, lon: float) -> float | None:
        if not math.isfinite(lat) or not math.isfinite(lon):
            return None
        r = (lat - self._origin_lat) / self._step_lat
        c = (lon - self._origin_lon) / self._step_lon
        tolerance = 1e-9
        if (
            r < -tolerance
            or c < -tolerance
            or r > self._rows - 1 + tolerance
            or c > self._cols - 1 + tolerance
        ):
            return None
        r = min(max(r, 0.0), self._rows - 1)
        c = min(max(c, 0.0), self._cols - 1)
        # Select the final interpolation cell for points on the north/east
        # boundary.  ``floor`` is essential here: ``int(-0.5)`` truncates to
        # zero and used to extrapolate southwest out-of-coverage positions.
        r0 = min(math.floor(r), self._rows - 2)
        c0 = min(math.floor(c), self._cols - 2)
        t, u = r - r0, c - c0
        e = self._elevations
        return (
            (1 - t) * (1 - u) * e[r0][c0]
            + (1 - t) * u * e[r0][c0 + 1]
            + t * (1 - u) * e[r0 + 1][c0]
            + t * u * e[r0 + 1][c0 + 1]
        )

    def recommended_sample_spacing_m(self, lat: float) -> float:
        """Return a conservative half-cell spacing for route coverage checks."""

        metres_per_degree_lat = 111_320.0
        metres_per_degree_lon = metres_per_degree_lat * max(
            abs(math.cos(math.radians(lat))), 1e-6
        )
        return 0.5 * min(
            self._step_lat * metres_per_degree_lat,
            self._step_lon * metres_per_degree_lon,
        )

    def conservative_max_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
        """Return a conservative bilinear maximum along a geodesic segment."""

        coordinates = (start_lat, start_lon, end_lat, end_lon)
        if not all(math.isfinite(value) for value in coordinates):
            return None
        interior = geod.npts(start_lon, start_lat, end_lon, end_lat, 7)
        route_points = [
            (start_lon, start_lat),
            *interior,
            (end_lon, end_lat),
        ]
        route_lons = [point_lon for point_lon, _ in route_points]
        route_lats = [point_lat for _, point_lat in route_points]
        if max(route_lons) - min(route_lons) > 180.0:
            return None
        return self._elevation_extreme_in_bounds(
            lat_min=min(route_lats),
            lat_max=max(route_lats),
            lon_min=min(route_lons),
            lon_max=max(route_lons),
            find_maximum=True,
        )

    def conservative_min_elevation_along_segment(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        *,
        geod: Geod,
    ) -> float | None:
        """Return a conservative bilinear minimum around a geodesic segment."""
        coordinates = (start_lat, start_lon, end_lat, end_lon)
        if not all(math.isfinite(value) for value in coordinates):
            return None
        interior = geod.npts(start_lon, start_lat, end_lon, end_lat, 7)
        route_points = [
            (start_lon, start_lat),
            *interior,
            (end_lon, end_lat),
        ]
        route_lons = [point_lon for point_lon, _ in route_points]
        route_lats = [point_lat for _, point_lat in route_points]
        if max(route_lons) - min(route_lons) > 180.0:
            return None
        return self._elevation_extreme_in_bounds(
            lat_min=min(route_lats),
            lat_max=max(route_lats),
            lon_min=min(route_lons),
            lon_max=max(route_lons),
            find_maximum=False,
        )

    def _elevation_extreme_in_bounds(
        self,
        *,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        find_maximum: bool,
    ) -> float | None:
        latitudes = _axis_partition_points(
            self._origin_lat,
            self._step_lat,
            self._rows,
            lat_min,
            lat_max,
        )
        longitudes = _axis_partition_points(
            self._origin_lon,
            self._step_lon,
            self._cols,
            lon_min,
            lon_max,
        )
        if latitudes is None or longitudes is None:
            return None
        elevations = [
            self.elevation_at(candidate_lat, candidate_lon)
            for candidate_lat in latitudes
            for candidate_lon in longitudes
        ]
        if any(value is None for value in elevations):
            return None
        finite_elevations = [float(value) for value in elevations if value is not None]
        return max(finite_elevations) if find_maximum else min(finite_elevations)


def _axis_partition_points(
    origin: float,
    step: float,
    count: int,
    lower: float,
    upper: float,
) -> list[float] | None:
    axis_upper = origin + step * (count - 1)
    tolerance = 1e-9
    if lower < origin - tolerance or upper > axis_upper + tolerance:
        return None
    lower = max(lower, origin)
    upper = min(upper, axis_upper)
    first_internal = max(0, math.ceil((lower - origin) / step))
    last_internal = min(count - 1, math.floor((upper - origin) / step))
    return [
        lower,
        *(origin + index * step for index in range(first_internal, last_internal + 1)),
        upper,
    ]


def terrain_provider_id(provider: TerrainProvider) -> str:
    pid = getattr(provider, "provider_id", None)
    if isinstance(pid, str) and pid:
        return pid
    return "custom"
