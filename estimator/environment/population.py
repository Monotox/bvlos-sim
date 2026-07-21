"""Population-density provider abstractions."""

from dataclasses import dataclass
from datetime import datetime
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


class PopulationProvider(Protocol):
    provider_id: str

    def density_at(self, lat: float, lon: float) -> float | None:
        """Return population density in people/km^2, or None outside coverage."""


@dataclass(frozen=True, slots=True)
class PopulationEvidence:
    """Provenance and validity contract for a SORA-eligible population grid."""

    source: str
    population_year: int
    native_resolution_m: float
    effective_resolution_m: float
    authority_assessment_reference: str
    valid_from: datetime
    valid_until: datetime
    transient_population_assessment_reference: str
    operational_footprint_assemblies_present: bool
    value_semantics: str = "conservative_cell_maximum"


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
        sora_evidence: PopulationEvidence | None = None,
    ) -> None:
        self._origin_lat = _finite_numeric_input(origin_lat, label="origin_lat")
        self._origin_lon = _finite_numeric_input(origin_lon, label="origin_lon")
        self._step_lat = _finite_numeric_input(step_lat_deg, label="step_lat_deg")
        self._step_lon = _finite_numeric_input(step_lon_deg, label="step_lon_deg")
        self._density: tuple[tuple[float, ...], ...] = tuple(
            tuple(
                _finite_numeric_input(value, label="density_ppl_km2") for value in row
            )
            for row in density_ppl_km2
        )
        self._rows = len(self._density)
        self._cols = len(self._density[0]) if self._density else 0
        self.sora_evidence = sora_evidence
        self._validate()

    def _validate(self) -> None:
        scalars = (
            self._origin_lat,
            self._origin_lon,
            self._step_lat,
            self._step_lon,
        )
        if not all(math.isfinite(value) for value in scalars):
            raise ValueError("population grid origin and steps must be finite")
        if not -90.0 <= self._origin_lat <= 90.0:
            raise ValueError("population grid origin_lat must be between -90 and 90")
        if not -180.0 <= self._origin_lon <= 180.0:
            raise ValueError("population grid origin_lon must be between -180 and 180")
        if self._step_lat <= 0.0 or self._step_lon <= 0.0:
            raise ValueError("population grid steps must be positive")
        if self._rows < 2 or self._cols < 2:
            raise ValueError(
                "population grid must contain at least two rows and columns"
            )
        if any(len(row) != self._cols for row in self._density):
            raise ValueError("population grid rows must have equal length")
        if any(
            not math.isfinite(value) or value < 0.0
            for row in self._density
            for value in row
        ):
            raise ValueError(
                "population grid densities must be finite and non-negative"
            )
        if self._origin_lat + self._step_lat * (self._rows - 1) > 90.0:
            raise ValueError("population grid extends beyond latitude 90")
        if self._origin_lon + self._step_lon * (self._cols - 1) > 180.0:
            raise ValueError("population grid extends beyond longitude 180")

    def density_at(self, lat: float, lon: float) -> float | None:
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
        r0 = min(math.floor(r), self._rows - 2)
        c0 = min(math.floor(c), self._cols - 2)
        t, u = r - r0, c - c0
        d = self._density
        if self.sora_evidence is not None:
            # Each value is declared to be a conservative maximum for its source
            # cell. Taking the maximum of the surrounding values preserves that
            # semantics; bilinear interpolation could smooth away a peak.
            density = max(
                d[r0][c0],
                d[r0][c0 + 1],
                d[r0 + 1][c0],
                d[r0 + 1][c0 + 1],
            )
            if self.sora_evidence.operational_footprint_assemblies_present:
                # SORA's assemblies-of-people row is the >50k density band.
                density = max(density, 50_000.0)
            return density
        return (
            (1 - t) * (1 - u) * d[r0][c0]
            + (1 - t) * u * d[r0][c0 + 1]
            + t * (1 - u) * d[r0 + 1][c0]
            + t * u * d[r0 + 1][c0 + 1]
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

    def conservative_max_density_in_radius(
        self,
        lat: float,
        lon: float,
        radius_m: float,
        *,
        geod: Geod,
    ) -> float | None:
        """Return a conservative maximum over a metric circle's bounding box.

        The density surface is bilinear within each grid cell. Its extrema over
        an axis-aligned subrectangle occur at the rectangle/grid intersections,
        all of which are checked here. Using the circle's bounding rectangle is
        intentionally conservative for a safety assessment.
        """

        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not math.isfinite(radius_m)
            or radius_m < 0.0
        ):
            return None
        if radius_m == 0.0:
            return self.density_at(lat, lon)
        bounds = _conservative_radius_bounds(lat, lon, radius_m)
        if bounds is None:
            return None
        lat_min, lat_max, lon_min, lon_max = bounds
        return self._max_density_in_bounds(
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
        )

    def _max_density_in_bounds(
        self,
        *,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
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
        densities = [
            self.density_at(candidate_lat, candidate_lon)
            for candidate_lat in latitudes
            for candidate_lon in longitudes
        ]
        if any(value is None for value in densities):
            return None
        return max(float(value) for value in densities if value is not None)


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


def _conservative_radius_bounds(
    lat: float,
    lon: float,
    radius_m: float,
) -> tuple[float, float, float, float] | None:
    """Bound a geodesic circle using deliberately low metres/degree factors."""

    # WGS84 meridional metres per degree never falls this low. Using 110 km
    # therefore expands the latitude bound beyond the true geodesic circle.
    lat_delta = radius_m / 110_000.0
    lat_min = lat - lat_delta
    lat_max = lat + lat_delta
    max_abs_lat = max(abs(lat_min), abs(lat_max))
    if lat_min <= -90.0 or lat_max >= 90.0:
        return None
    # Evaluate longitude scale at the most poleward latitude reached. 111 km
    # per equatorial degree is below WGS84, so this also expands the bound.
    metres_per_degree_lon = 111_000.0 * math.cos(math.radians(max_abs_lat))
    if metres_per_degree_lon <= 0.0:
        return None
    lon_delta = radius_m / metres_per_degree_lon
    lon_min = lon - lon_delta
    lon_max = lon + lon_delta
    # Uniform grids in this provider do not wrap across the antimeridian.
    if lon_min < -180.0 or lon_max > 180.0:
        return None
    return lat_min, lat_max, lon_min, lon_max


def population_provider_id(provider: PopulationProvider) -> str:
    pid = getattr(provider, "provider_id", None)
    if isinstance(pid, str) and pid:
        return pid
    return "custom"


__all__ = [
    "GridPopulationProvider",
    "PopulationEvidence",
    "PopulationProvider",
    "population_provider_id",
]
