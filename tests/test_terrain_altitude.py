"""Tests for terrain-referenced altitude resolution."""

import pytest

from bvlos_sim.estimator import (
    ConstantElevationProvider,
    EstimateStatus,
    FailureCode,
    UnsupportedEstimatorFeatureError,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.environment.terrain import GridTerrainProvider, terrain_provider_id
from bvlos_sim.schemas.mission import AltitudeReference
from tests.helpers import make_mission, make_vehicle


def _terrain_mission(default_reference: AltitudeReference = AltitudeReference.TERRAIN):
    mission = make_mission()
    mission.defaults.altitude_reference = default_reference
    return mission


# --- ConstantElevationProvider ---


def test_constant_elevation_provider_always_returns_value() -> None:
    provider = ConstantElevationProvider(50.0)
    assert provider.elevation_at(52.0, 4.0) == 50.0
    assert provider.elevation_at(0.0, 0.0) == 50.0


def test_constant_elevation_provider_id() -> None:
    provider = ConstantElevationProvider(10.0)
    assert provider.provider_id == "constant"
    assert terrain_provider_id(provider) == "constant"


# --- GridTerrainProvider ---


def test_grid_terrain_provider_bilinear_interpolation() -> None:
    provider = GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.001,
        step_lon_deg=0.001,
        elevations_m=[[10.0, 20.0], [30.0, 40.0]],
    )
    # At origin exactly
    assert provider.elevation_at(52.0, 4.0) == pytest.approx(10.0)
    # Midpoint should be average
    assert provider.elevation_at(52.0005, 4.0005) == pytest.approx(25.0)


def test_grid_terrain_provider_returns_none_outside_bounds() -> None:
    provider = GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.001,
        step_lon_deg=0.001,
        elevations_m=[[10.0, 20.0], [30.0, 40.0]],
    )
    assert provider.elevation_at(51.0, 4.0) is None  # south of grid
    assert provider.elevation_at(53.0, 4.0) is None  # north of grid
    assert provider.elevation_at(52.0, 3.0) is None  # west of grid


def test_grid_terrain_provider_id() -> None:
    provider = GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.001,
        step_lon_deg=0.001,
        elevations_m=[[10.0, 10.0], [10.0, 10.0]],
    )
    assert terrain_provider_id(provider) == "uniform_grid"


# --- terrain altitude resolution via estimator ---


def test_terrain_reference_without_provider_fails_unsupported() -> None:
    mission = _terrain_mission()
    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())
    assert (
        exc_info.value.failure.code
        == FailureCode.UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN
    )


def test_terrain_reference_with_constant_provider_succeeds() -> None:
    mission = _terrain_mission()
    provider = ConstantElevationProvider(10.0)
    result = estimate_mission_distance_time(
        mission, make_vehicle(), terrain_provider=provider
    )
    assert result.status == EstimateStatus.SUCCESS


def test_terrain_resolves_amsl_as_ground_plus_altitude() -> None:
    """Leg start altitude should equal ground_elevation + altitude_m above ground."""
    mission = _terrain_mission()
    ground_elevation = 20.0
    provider = ConstantElevationProvider(ground_elevation)

    result = estimate_mission_distance_time(
        mission, make_vehicle(), terrain_provider=provider
    )
    # TAKEOFF leg starts at home; home ground elevation = 20.0; altitude_m = 80.0
    # So AMSL = 20.0 + 80.0 = 100.0
    takeoff_leg = result.legs[0]
    assert takeoff_leg.end_alt_amsl_m == pytest.approx(ground_elevation + 80.0)


def test_terrain_coverage_missing_fails_with_structured_diagnostic() -> None:
    """GridTerrainProvider returning None should produce TERRAIN_COVERAGE_MISSING."""
    mission = _terrain_mission()
    # Grid that does NOT cover the mission area (home at 52.0, 4.0; grid starts at 60.0)
    provider = GridTerrainProvider(
        origin_lat=60.0,
        origin_lon=10.0,
        step_lat_deg=0.001,
        step_lon_deg=0.001,
        elevations_m=[[100.0, 100.0], [100.0, 100.0]],
    )
    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(
            mission, make_vehicle(), terrain_provider=provider
        )
    assert exc_info.value.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING
    assert "lat" in exc_info.value.failure.context
    assert "lon" in exc_info.value.failure.context


def test_amsl_reference_unaffected_by_terrain_provider() -> None:
    """AMSL route items must ignore terrain provider entirely."""
    mission = make_mission()  # defaults altitude_reference: relative_home
    # Set a specific item to AMSL
    mission.route[1].altitude_reference = AltitudeReference.AMSL
    mission.route[1].altitude_m = 90.0

    provider = ConstantElevationProvider(999.0)
    result = estimate_mission_distance_time(
        mission, make_vehicle(), terrain_provider=provider
    )
    # wp1 is AMSL 90.0; terrain should not affect it
    wp1_leg = next(leg for leg in result.legs if leg.route_item_id == "wp1")
    assert wp1_leg.end_alt_amsl_m == pytest.approx(90.0)


def test_relative_home_reference_unaffected_by_terrain_provider() -> None:
    """relative_home route items must ignore terrain provider."""
    mission = make_mission()  # uses relative_home by default
    provider = ConstantElevationProvider(999.0)
    result_with = estimate_mission_distance_time(
        mission, make_vehicle(), terrain_provider=provider
    )
    result_without = estimate_mission_distance_time(mission, make_vehicle())
    assert result_with.total_time_s == pytest.approx(result_without.total_time_s)


def test_terrain_provider_id_in_metadata() -> None:
    """terrain_provider_id must appear in result metadata when provider is used."""
    mission = _terrain_mission()
    provider = ConstantElevationProvider(10.0)
    result = estimate_mission_distance_time(
        mission, make_vehicle(), terrain_provider=provider
    )
    assert result.metadata.get("terrain_provider_id") == "constant"


def test_no_terrain_provider_means_no_terrain_metadata() -> None:
    """terrain_provider_id must NOT appear in metadata when no provider is configured."""
    mission = make_mission()
    result = estimate_mission_distance_time(mission, make_vehicle())
    assert "terrain_provider_id" not in result.metadata


def test_try_api_terrain_without_provider_returns_error_status() -> None:
    mission = _terrain_mission()
    result = try_estimate_mission_distance_time(mission, make_vehicle())
    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN


# --- adapter ---


def test_load_terrain_grid_from_yaml(tmp_path) -> None:
    from bvlos_sim.adapters.terrain_grid import load_terrain_grid

    grid_file = tmp_path / "terrain.yaml"
    grid_file.write_text(
        "origin_lat: 52.0\n"
        "origin_lon: 4.0\n"
        "step_lat_deg: 0.001\n"
        "step_lon_deg: 0.001\n"
        "elevations_m:\n"
        "  - [10.0, 10.5]\n"
        "  - [11.0, 11.5]\n"
    )
    provider, doc = load_terrain_grid(grid_file)
    assert provider.elevation_at(52.0, 4.0) == pytest.approx(10.0)
    assert doc.format == "yaml"


def test_load_terrain_grid_missing_key_raises_load_error(tmp_path) -> None:
    from bvlos_sim.adapters.terrain_grid import TerrainGridLoadError, load_terrain_grid

    grid_file = tmp_path / "terrain.yaml"
    grid_file.write_text("origin_lat: 52.0\n")  # missing required keys
    with pytest.raises(TerrainGridLoadError):
        load_terrain_grid(grid_file)


def test_load_terrain_grid_non_mapping_raises_load_error(tmp_path) -> None:
    from bvlos_sim.adapters.terrain_grid import TerrainGridLoadError, load_terrain_grid

    grid_file = tmp_path / "terrain.yaml"
    grid_file.write_text("- 1\n- 2\n")  # list, not mapping
    with pytest.raises(TerrainGridLoadError):
        load_terrain_grid(grid_file)
