import math

import pytest

from bvlos_sim.estimator.environment.population import GridPopulationProvider
from bvlos_sim.estimator.environment.population import _conservative_radius_bounds
from bvlos_sim.estimator.environment.terrain import ConstantElevationProvider, GridTerrainProvider


def _terrain() -> GridTerrainProvider:
    return GridTerrainProvider(
        origin_lat=10.0,
        origin_lon=20.0,
        step_lat_deg=1.0,
        step_lon_deg=1.0,
        elevations_m=[[10.0, 20.0], [30.0, 40.0]],
    )


def _population() -> GridPopulationProvider:
    return GridPopulationProvider(
        origin_lat=10.0,
        origin_lon=20.0,
        step_lat_deg=1.0,
        step_lon_deg=1.0,
        density_ppl_km2=[[10.0, 20.0], [30.0, 40.0]],
    )


def test_grid_queries_southwest_of_origin_do_not_extrapolate() -> None:
    # Regression: int(-0.5) == 0 previously treated these as in-coverage.
    assert _terrain().elevation_at(9.5, 19.5) is None
    assert _population().density_at(9.5, 19.5) is None


def test_grid_includes_exact_north_east_boundary_node() -> None:
    assert _terrain().elevation_at(11.0, 21.0) == pytest.approx(40.0)
    assert _population().density_at(11.0, 21.0) == pytest.approx(40.0)


@pytest.mark.parametrize(
    "values",
    [[], [[1.0]], [[1.0, 2.0], [3.0]], [[1.0, math.nan], [2.0, 3.0]]],
)
def test_malformed_terrain_grids_are_rejected(values: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        GridTerrainProvider(
            origin_lat=10.0,
            origin_lon=20.0,
            step_lat_deg=1.0,
            step_lon_deg=1.0,
            elevations_m=values,
        )


def test_negative_or_nonfinite_population_density_is_rejected() -> None:
    for invalid in (-1.0, math.inf, math.nan):
        with pytest.raises(ValueError):
            GridPopulationProvider(
                origin_lat=10.0,
                origin_lon=20.0,
                step_lat_deg=1.0,
                step_lon_deg=1.0,
                density_ppl_km2=[[0.0, invalid], [0.0, 0.0]],
            )


def test_nonpositive_grid_steps_are_rejected() -> None:
    with pytest.raises(ValueError, match="steps must be positive"):
        GridTerrainProvider(
            origin_lat=10.0,
            origin_lon=20.0,
            step_lat_deg=0.0,
            step_lon_deg=1.0,
            elevations_m=[[0.0, 0.0], [0.0, 0.0]],
        )


def test_constant_terrain_rejects_nonfinite_elevation() -> None:
    with pytest.raises(ValueError, match="finite"):
        ConstantElevationProvider(math.nan)


def test_population_radius_bounds_enclose_high_latitude_geodesic_circle() -> None:
    from pyproj import Geod

    bounds = _conservative_radius_bounds(85.0, 20.0, 20_000.0)
    assert bounds is not None
    lat_min, lat_max, lon_min, lon_max = bounds
    geod = Geod(ellps="WGS84")
    perimeter = [geod.fwd(20.0, 85.0, azimuth, 20_000.0)[:2] for azimuth in range(360)]

    assert min(lat for _, lat in perimeter) >= lat_min
    assert max(lat for _, lat in perimeter) <= lat_max
    assert min(lon for lon, _ in perimeter) >= lon_min
    assert max(lon for lon, _ in perimeter) <= lon_max
