import json
from pathlib import Path

import pytest
import yaml
from pyproj import Geod
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from estimator import (
    EstimateStatus,
    FailureCode,
    WarningCode,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.environment.population import GridPopulationProvider
from estimator.execution.ground_risk import (
    compute_ground_risk,
    controlled_ground_area_igrc,
    intrinsic_ground_risk_class,
)
from schemas.vehicle import VehicleProfile
from tests.helpers import (
    make_mission,
    make_mission_payload,
    make_vehicle,
    make_vehicle_payload,
)

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
_RUNNER = CliRunner()


def _population_provider(density_ppl_km2: float) -> GridPopulationProvider:
    return GridPopulationProvider(
        origin_lat=51.99,
        origin_lon=3.99,
        step_lat_deg=0.01,
        step_lon_deg=0.01,
        density_ppl_km2=[
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
        ],
    )


def _vehicle_with_dimension(dimension_m: float | None = 1.0) -> VehicleProfile:
    vehicle = make_vehicle()
    if dimension_m is None:
        return vehicle
    return vehicle.model_copy(update={"characteristic_dimension_m": dimension_m})


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize(
    ("density_ppl_km2", "expected_by_aircraft"),
    [
        (0.0, (2, 3, 4, 5, 6)),
        (5.0, (3, 4, 5, 6, 7)),
        (50.0, (4, 5, 6, 7, 8)),
        (500.0, (5, 6, 7, 8, 9)),
        (5_000.0, (6, 7, 8, 9, 10)),
    ],
)
@pytest.mark.parametrize(
    ("dimension_m", "max_speed_mps", "column"),
    [
        (1.0, 25.0, 0),
        (3.0, 35.0, 1),
        (8.0, 75.0, 2),
        (20.0, 120.0, 3),
        (40.0, 200.0, 4),
    ],
)
def test_intrinsic_ground_risk_class_maps_density_boundary_rows(
    density_ppl_km2: float,
    expected_by_aircraft: tuple[int, int, int, int, int],
    dimension_m: float,
    max_speed_mps: float,
    column: int,
) -> None:
    assert (
        intrinsic_ground_risk_class(
            characteristic_dimension_m=dimension_m,
            max_speed_mps=max_speed_mps,
            density_ppl_km2=density_ppl_km2,
        )
        == expected_by_aircraft[column]
    )


@pytest.mark.parametrize(
    ("dimension_m", "max_speed_mps", "expected_igrc"),
    [
        (1.0, 25.0, 3),
        (1.0001, 25.0, 4),
        (1.0, 25.0001, 4),
        (3.0, 35.0, 4),
        (3.0001, 35.0, 5),
        (3.0, 35.0001, 5),
        (8.0, 75.0, 5),
        (8.0001, 75.0, 6),
    ],
)
def test_intrinsic_ground_risk_class_uses_leftmost_size_and_speed_column(
    dimension_m: float,
    max_speed_mps: float,
    expected_igrc: int,
) -> None:
    assert (
        intrinsic_ground_risk_class(
            characteristic_dimension_m=dimension_m,
            max_speed_mps=max_speed_mps,
            density_ppl_km2=12.0,
        )
        == expected_igrc
    )


def test_controlled_ground_area_igrc_uses_declared_row() -> None:
    aircraft = [(1.0, 25.0), (3.0, 35.0), (8.0, 75.0), (20.0, 120.0), (40.0, 200.0)]
    assert [controlled_ground_area_igrc(*values) for values in aircraft] == [
        1,
        1,
        2,
        3,
        3,
    ]


@pytest.mark.parametrize(
    ("dimension_m", "max_speed_mps"),
    [(8.0, 75.0), (20.0, 120.0), (40.0, 200.0)],
)
def test_dense_population_unsupported_cells_are_rejected(
    dimension_m: float, max_speed_mps: float
) -> None:
    with pytest.raises(ValueError, match="outside the SORA 2.5 table"):
        intrinsic_ground_risk_class(
            characteristic_dimension_m=dimension_m,
            max_speed_mps=max_speed_mps,
            density_ppl_km2=50_000.0,
        )


@pytest.mark.parametrize(
    ("dimension_m", "max_speed_mps", "expected_igrc"),
    [(1.0, 25.0, 7), (3.0, 35.0, 8)],
)
def test_exactly_50_000_density_uses_conservative_highest_band(
    dimension_m: float,
    max_speed_mps: float,
    expected_igrc: int,
) -> None:
    assert (
        intrinsic_ground_risk_class(
            characteristic_dimension_m=dimension_m,
            max_speed_mps=max_speed_mps,
            density_ppl_km2=50_000.0,
        )
        == expected_igrc
    )


@pytest.mark.parametrize("density", [0.0, 5.0, 50.0, 500.0, 5_000.0, 50_000.0])
def test_250g_25mps_exception_is_igrc_one_regardless_of_population(
    density: float,
) -> None:
    assert (
        intrinsic_ground_risk_class(
            characteristic_dimension_m=None,
            max_speed_mps=25.0,
            density_ppl_km2=density,
            aircraft_mass_kg=0.250,
        )
        == 1
    )


def test_compute_ground_risk_samples_population_grid() -> None:
    estimate = estimate_mission_distance_time(make_mission(), _vehicle_with_dimension())

    ground_risk, warnings = compute_ground_risk(
        estimate,
        population_provider=_population_provider(12.0),
        characteristic_dimension_m=1.0,
        max_speed_mps=25.0,
        geod=Geod(ellps="WGS84"),
        max_segment_length_m=100.0,
    )

    assert warnings == []
    assert ground_risk is not None
    assert ground_risk.mission_igrc == 3
    assert ground_risk.sora_version == "2.5"
    assert ground_risk.aircraft_column == 1
    assert ground_risk.controlled_ground_area_reference_igrc == 1
    assert all(
        leg.max_density_ppl_km2 == pytest.approx(12.0) for leg in ground_risk.legs
    )
    assert all(leg.igrc == 3 for leg in ground_risk.legs)


def test_assessed_population_buffer_captures_dense_area_beside_route() -> None:
    values = [[12.0] * 16 for _ in range(16)]
    values[7][5] = 600.0
    provider = GridPopulationProvider(
        origin_lat=51.995,
        origin_lon=3.995,
        step_lat_deg=0.001,
        step_lon_deg=0.001,
        density_ppl_km2=values,
    )
    estimate = estimate_mission_distance_time(make_mission(), _vehicle_with_dimension())
    kwargs = {
        "estimate": estimate,
        "population_provider": provider,
        "characteristic_dimension_m": 1.0,
        "max_speed_mps": 25.0,
        "geod": Geod(ellps="WGS84"),
        "max_segment_length_m": 100.0,
    }

    centerline, _ = compute_ground_risk(**kwargs)
    footprint, _ = compute_ground_risk(
        **kwargs,
        population_assessment_buffer_m=250.0,
    )

    assert centerline is not None
    assert footprint is not None
    assert centerline.mission_igrc == 3
    assert footprint.mission_igrc == 5
    assert footprint.population_assessment_buffer_m == 250.0


def test_estimate_ground_risk_increases_with_population_density() -> None:
    mission = make_mission()
    vehicle = _vehicle_with_dimension(1.0)

    low = estimate_mission_distance_time(
        mission,
        vehicle,
        population_provider=_population_provider(12.0),
    )
    high = estimate_mission_distance_time(
        mission,
        vehicle,
        population_provider=_population_provider(5_000.0),
    )

    assert low.ground_risk is not None
    assert high.ground_risk is not None
    assert low.ground_risk.mission_igrc == 3
    assert high.ground_risk.mission_igrc == 6


def test_population_grid_without_vehicle_dimension_warns() -> None:
    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        population_provider=_population_provider(12.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.ground_risk is None
    assert WarningCode.POPULATION_DENSITY_DIMENSION_MISSING in {
        warning.code for warning in result.warnings
    }


def test_missing_population_grid_leaves_ground_risk_inactive() -> None:
    result = try_estimate_mission_distance_time(
        make_mission(),
        _vehicle_with_dimension(1.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.ground_risk is None
    assert WarningCode.POPULATION_DENSITY_DIMENSION_MISSING not in {
        warning.code for warning in result.warnings
    }


def test_partial_population_coverage_fails_closed() -> None:
    provider = GridPopulationProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.0005,
        step_lon_deg=0.0005,
        density_ppl_km2=[[12.0, 12.0], [12.0, 12.0]],
    )

    result = try_estimate_mission_distance_time(
        make_mission(),
        _vehicle_with_dimension(1.0),
        population_provider=provider,
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.POPULATION_COVERAGE_MISSING
    assert "sample_lat" in result.failure.context


def test_estimate_ground_risk_format_renders_table(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_ground_risk_inputs(tmp_path)

    result = _RUNNER.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "ground-risk",
            "--engineering-only",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "# Ground Risk Class" in result.stdout
    assert "| Leg | Route Item ID | Max Density (ppl/km^2) | iGRC |" in result.stdout
    assert "Mission iGRC" in result.stdout
    assert "wp1" in result.stdout


def test_estimate_geojson_includes_igrc_on_route_legs(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_ground_risk_inputs(tmp_path)

    result = _RUNNER.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "geojson",
            "--engineering-only",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.stdout)
    route_features = [
        feature
        for feature in payload["features"]
        if feature["properties"]["layer"] == "route"
    ]
    assert route_features
    assert all(feature["properties"]["igrc"] == 3 for feature in route_features)


def _write_ground_risk_inputs(tmp_path: Path) -> tuple[Path, Path]:
    population_path = tmp_path / "population.yaml"
    population_path.write_text(
        (_FIXTURE_ROOT / "population_grid_12.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    mission_payload = make_mission_payload()
    mission_payload["assets"] = {"population_grid_file": population_path.name}
    vehicle_payload = make_vehicle_payload()
    vehicle_payload["characteristic_dimension_m"] = 1.0

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, vehicle_payload)
    return mission_path, vehicle_path
