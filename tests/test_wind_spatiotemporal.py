"""Tests for SpatiotemporalWindProvider and wind grid adapter."""

import pytest

from estimator import (
    SpatiotemporalWindProvider,
    estimate_mission_distance_time,
)
from estimator.environment.wind import wind_provider_id
from tests.helpers import make_mission, make_vehicle


# --- SpatiotemporalWindProvider ---

def _uniform_provider(east: float = 2.0, north: float = 0.0) -> SpatiotemporalWindProvider:
    """Minimal 2×2×2×2 grid with uniform wind.

    Structure: values[t_idx][alt_idx][lat_idx][lon_idx] = [east, north]
    """
    cell = [east, north]
    lat_row = [cell, cell]          # 2 lon entries
    alt_slice = [lat_row, lat_row]  # 2 lat rows
    t_snap = [alt_slice, alt_slice] # 2 alt bands
    v = [t_snap, t_snap]            # 2 time snapshots
    return SpatiotemporalWindProvider(
        time_s=[0.0, 600.0],
        altitude_m=[0.0, 200.0],
        lat=[52.0, 52.01],
        lon=[4.0, 4.01],
        values=v,
    )


def test_uniform_grid_returns_constant_wind() -> None:
    provider = _uniform_provider(east=3.0, north=-1.0)
    wind = provider.wind_at(52.005, 4.005, 100.0, 300.0)
    assert wind.wind_east_mps == pytest.approx(3.0)
    assert wind.wind_north_mps == pytest.approx(-1.0)


def test_provider_id() -> None:
    provider = _uniform_provider()
    assert provider.provider_id == "spatiotemporal_grid"
    assert wind_provider_id(provider) == "spatiotemporal_grid"


def test_wind_interpolates_across_time() -> None:
    """Wind at time midpoint should interpolate between two time snapshots."""
    # v_t[alt][lat][lon] = [east, north]; 2 alts, 2 lats, 2 lons
    v_t0 = [[[[2.0, 0.0], [2.0, 0.0]], [[2.0, 0.0], [2.0, 0.0]]],
            [[[2.0, 0.0], [2.0, 0.0]], [[2.0, 0.0], [2.0, 0.0]]]]
    v_t1 = [[[[4.0, 0.0], [4.0, 0.0]], [[4.0, 0.0], [4.0, 0.0]]],
            [[[4.0, 0.0], [4.0, 0.0]], [[4.0, 0.0], [4.0, 0.0]]]]
    provider = SpatiotemporalWindProvider(
        time_s=[0.0, 600.0],
        altitude_m=[0.0, 200.0],
        lat=[52.0, 52.01],
        lon=[4.0, 4.01],
        values=[v_t0, v_t1],
    )
    wind = provider.wind_at(52.005, 4.005, 100.0, 300.0)
    assert wind.wind_east_mps == pytest.approx(3.0)


def test_wind_interpolates_across_altitude() -> None:
    """Wind should interpolate between altitude bands."""
    # v_low/v_high[lat][lon] = [east, north]; 2 lats, 2 lons
    v_low = [[[2.0, 0.0], [2.0, 0.0]], [[2.0, 0.0], [2.0, 0.0]]]
    v_high = [[[4.0, 0.0], [4.0, 0.0]], [[4.0, 0.0], [4.0, 0.0]]]
    provider = SpatiotemporalWindProvider(
        time_s=[0.0, 600.0],
        altitude_m=[0.0, 200.0],
        lat=[52.0, 52.01],
        lon=[4.0, 4.01],
        values=[[v_low, v_high], [v_low, v_high]],
    )
    wind = provider.wind_at(52.005, 4.005, 100.0, 0.0)
    assert wind.wind_east_mps == pytest.approx(3.0)


def test_wind_clamps_below_time_axis() -> None:
    provider = _uniform_provider(east=5.0)
    wind = provider.wind_at(52.005, 4.005, 100.0, -100.0)
    assert wind.wind_east_mps == pytest.approx(5.0)


def test_wind_clamps_above_time_axis() -> None:
    provider = _uniform_provider(east=5.0)
    wind = provider.wind_at(52.005, 4.005, 100.0, 99999.0)
    assert wind.wind_east_mps == pytest.approx(5.0)


def test_wind_clamps_outside_lat_lon_bounds() -> None:
    provider = _uniform_provider(east=2.0)
    wind = provider.wind_at(53.0, 5.0, 100.0, 0.0)
    assert wind.wind_east_mps == pytest.approx(2.0)


def test_wind_interpolates_linearly_at_time_midpoint() -> None:
    """At exactly t=300s (midpoint of [0, 600]), wind should be the exact average."""
    # values[t_idx][alt_idx][lat_idx][lon_idx] = [east, north]
    cell_t0 = [2.0, 0.0]
    lat_row_t0 = [cell_t0, cell_t0]           # 2 lon entries
    alt_slice_t0 = [lat_row_t0, lat_row_t0]   # 2 lat rows
    t_snap_t0 = [alt_slice_t0, alt_slice_t0]  # 2 alt bands

    cell_t1 = [6.0, 0.0]
    lat_row_t1 = [cell_t1, cell_t1]
    alt_slice_t1 = [lat_row_t1, lat_row_t1]
    t_snap_t1 = [alt_slice_t1, alt_slice_t1]

    provider = SpatiotemporalWindProvider(
        time_s=[0.0, 600.0],
        altitude_m=[0.0, 200.0],
        lat=[52.0, 52.01],
        lon=[4.0, 4.01],
        values=[t_snap_t0, t_snap_t1],
    )
    wind = provider.wind_at(52.005, 4.005, 100.0, 300.0)
    assert wind.wind_east_mps == pytest.approx(4.0)


def test_spatiotemporal_wind_changes_estimation_time() -> None:
    """Estimation with spatiotemporal wind should differ from zero-wind baseline."""
    mission = make_mission()
    vehicle = make_vehicle()

    result_no_wind = estimate_mission_distance_time(mission, vehicle)
    provider = _uniform_provider(east=5.0, north=0.0)
    result_wind = estimate_mission_distance_time(mission, vehicle, wind_provider=provider)

    assert result_wind.total_time_s != result_no_wind.total_time_s


def test_spatiotemporal_wind_metadata_records_provider_id() -> None:
    mission = make_mission()
    provider = _uniform_provider()
    result = estimate_mission_distance_time(mission, make_vehicle(), wind_provider=provider)
    assert result.metadata.get("wind_provider_id") == "spatiotemporal_grid"


# --- load_wind_grid adapter ---

def _minimal_grid_yaml() -> str:
    return (
        "axes:\n"
        "  time_s: [0.0, 600.0]\n"
        "  altitude_m: [0.0, 200.0]\n"
        "  lat: [52.0, 52.01]\n"
        "  lon: [4.0, 4.01]\n"
        "values:\n"
        "  - - - [[2.0, 0.0], [2.0, 0.0]]\n"
        "      - [[2.0, 0.0], [2.0, 0.0]]\n"
        "    - - [[3.0, 0.0], [3.0, 0.0]]\n"
        "      - [[3.0, 0.0], [3.0, 0.0]]\n"
        "  - - - [[2.0, 0.0], [2.0, 0.0]]\n"
        "      - [[2.0, 0.0], [2.0, 0.0]]\n"
        "    - - [[3.0, 0.0], [3.0, 0.0]]\n"
        "      - [[3.0, 0.0], [3.0, 0.0]]\n"
    )


def test_load_wind_grid_from_yaml(tmp_path) -> None:
    from adapters.wind_grid import load_wind_grid
    grid_file = tmp_path / "wind.yaml"
    grid_file.write_text(_minimal_grid_yaml())
    provider, doc = load_wind_grid(grid_file)
    assert provider.provider_id == "spatiotemporal_grid"
    assert doc.format == "yaml"
    # At altitude midpoint between 0 m (east=2.0) and 200 m (east=3.0), east ≈ 2.5
    wind = provider.wind_at(52.005, 4.005, 100.0, 300.0)
    assert wind.wind_east_mps == pytest.approx(2.5)


def test_load_wind_grid_non_mapping_raises(tmp_path) -> None:
    from adapters.wind_grid import WindGridLoadError, load_wind_grid
    f = tmp_path / "wind.yaml"
    f.write_text("- 1\n- 2\n")
    with pytest.raises(WindGridLoadError):
        load_wind_grid(f)


def test_load_wind_grid_missing_axes_raises(tmp_path) -> None:
    from adapters.wind_grid import WindGridLoadError, load_wind_grid
    f = tmp_path / "wind.yaml"
    f.write_text("values: []\n")
    with pytest.raises(WindGridLoadError):
        load_wind_grid(f)


def test_load_wind_grid_non_monotonic_axis_raises(tmp_path) -> None:
    from adapters.wind_grid import WindGridLoadError, load_wind_grid
    f = tmp_path / "wind.yaml"
    f.write_text(
        "axes:\n"
        "  time_s: [0.0, 600.0]\n"
        "  altitude_m: [200.0, 0.0]\n"  # descending — invalid
        "  lat: [52.0, 52.01]\n"
        "  lon: [4.0, 4.01]\n"
        "values: []\n"
    )
    with pytest.raises(WindGridLoadError):
        load_wind_grid(f)


def test_load_wind_grid_wrong_values_shape_raises(tmp_path) -> None:
    from adapters.wind_grid import WindGridLoadError, load_wind_grid
    f = tmp_path / "wind.yaml"
    f.write_text(
        "axes:\n"
        "  time_s: [0.0, 600.0]\n"
        "  altitude_m: [0.0, 200.0]\n"
        "  lat: [52.0, 52.01]\n"
        "  lon: [4.0, 4.01]\n"
        "values:\n"
        "  - []\n"  # wrong shape
        "  - []\n"
    )
    with pytest.raises(WindGridLoadError):
        load_wind_grid(f)


def test_load_wind_grid_single_element_axis_raises(tmp_path) -> None:
    from adapters.wind_grid import WindGridLoadError, load_wind_grid
    f = tmp_path / "wind.yaml"
    f.write_text(
        "axes:\n"
        "  time_s: [0.0]\n"  # single element — invalid
        "  altitude_m: [0.0, 200.0]\n"
        "  lat: [52.0, 52.01]\n"
        "  lon: [4.0, 4.01]\n"
        "values: []\n"
    )
    with pytest.raises(WindGridLoadError):
        load_wind_grid(f)
