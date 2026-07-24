import json
from pathlib import Path

import pytest
import yaml
from pyproj import Geod
from typer.testing import CliRunner

from bvlos_sim.adapters.assets.obstacle_geojson import load_obstacles
from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.estimator import (
    EstimateStatus,
    EstimationOptions,
    FailureCode,
    FidelityMode,
    LegPhase,
    WarningCode,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.obstacle import Obstacle
from bvlos_sim.estimator.environment.obstacle import ListObstacleProvider
from bvlos_sim.estimator.environment.terrain import GridTerrainProvider
from bvlos_sim.estimator.execution.spatial_sampling import route_leg_samples
from bvlos_sim.schemas.mission import MissionAction, MissionPlan, RouteItem
from tests.helpers import (
    make_mission,
    make_mission_payload,
    make_vehicle,
    make_vehicle_payload,
)

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
_RUNNER = CliRunner()


def _point_obstacle_provider() -> ListObstacleProvider:
    obstacle = Obstacle.model_validate(
        {
            "id": "mast-midpoint",
            "geometry": {
                "type": "point",
                "points": [{"lat": 52.0005, "lon": 4.001}],
            },
            "height_m": 105.0,
            "radius_m": 20.0,
        }
    )
    return ListObstacleProvider([obstacle])


def _mission_with_obstacle_clearance() -> MissionPlan:
    mission = make_mission()
    constraints = mission.constraints.model_copy(
        update={"min_obstacle_clearance_m": 15.0}
    )
    return mission.model_copy(update={"constraints": constraints})


def _mission_with_terrain_clearance() -> MissionPlan:
    payload = make_mission_payload()
    payload["planned_home"]["altitude_amsl_m"] = 100.0
    payload["constraints"]["min_terrain_clearance_m"] = 30.0
    return MissionPlan.model_validate(payload)


def _ridge_provider() -> GridTerrainProvider:
    return GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.0005,
        step_lon_deg=0.001,
        elevations_m=[
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 180.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0],
        ],
    )


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_obstacle_inputs(tmp_path: Path) -> tuple[Path, Path]:
    obstacle_path = tmp_path / "obstacles.geojson"
    obstacle_path.write_text(
        (_FIXTURE_ROOT / "obstacles.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mission_payload = make_mission_payload()
    mission_payload["constraints"]["min_obstacle_clearance_m"] = 15.0
    mission_payload["assets"] = {"obstacles_file": obstacle_path.name}
    vehicle_payload = make_vehicle_payload()

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, vehicle_payload)
    return mission_path, vehicle_path


def test_obstacle_clearance_violation_returns_infeasible() -> None:
    result = try_estimate_mission_distance_time(
        _mission_with_obstacle_clearance(),
        make_vehicle(),
        obstacle_provider=_point_obstacle_provider(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.OBSTACLE_CLEARANCE_VIOLATED
    assert result.failure.context["obstacle_id"] == "mast-midpoint"
    assert result.obstacle is not None
    assert result.obstacle.violations[0].obstacle_id == "mast-midpoint"


def test_terrain_clearance_checks_subsegment_between_waypoints() -> None:
    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
        terrain_provider=_ridge_provider(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_CLEARANCE_VIOLATED
    assert result.obstacle is not None
    assert result.obstacle.violations[0].terrain_elevation_m is not None
    assert result.obstacle.violations[0].terrain_elevation_m > 150.0


def test_terrain_clearance_captures_grid_peak_between_route_samples() -> None:
    mission = make_mission()
    mission.planned_home.altitude_amsl_m = 100.0
    for route_item in mission.route:
        if route_item.altitude_m is not None:
            route_item.altitude_m = 33.0
    mission.constraints = mission.constraints.model_copy(
        update={"min_terrain_clearance_m": 40.0}
    )
    elevations = [[0.0] * 12 for _ in range(8)]
    elevations[2][3] = 100.0
    provider = GridTerrainProvider(
        origin_lat=51.9995,
        origin_lon=3.9995,
        step_lat_deg=0.0005,
        step_lon_deg=0.0005,
        elevations_m=elevations,
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        terrain_provider=provider,
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_CLEARANCE_VIOLATED
    assert result.obstacle is not None
    assert result.obstacle.violations[0].terrain_elevation_m == pytest.approx(100.0)


def test_terrain_constraint_without_provider_fails_closed() -> None:
    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING


def test_custom_terrain_without_continuous_maximum_fails_closed() -> None:
    class _EndpointOnlyTerrainProvider:
        provider_id = "endpoint-only-test"

        @staticmethod
        def elevation_at(lat: float, lon: float) -> float:
            return 0.0

        @staticmethod
        def recommended_sample_spacing_m(lat: float) -> float:
            return 50.0

    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
        terrain_provider=_EndpointOnlyTerrainProvider(),
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING


@pytest.mark.parametrize(
    "invalid_elevation", [float("nan"), float("inf"), -float("inf")]
)
def test_custom_terrain_non_finite_segment_maximum_fails_closed(
    invalid_elevation: float,
) -> None:
    class _NonFiniteTerrainProvider:
        provider_id = "non-finite-test"

        def elevation_at(self, lat: float, lon: float) -> float:
            return invalid_elevation

        def conservative_max_elevation_along_segment(
            self,
            start_lat: float,
            start_lon: float,
            end_lat: float,
            end_lon: float,
            *,
            geod: Geod,
        ) -> float:
            return invalid_elevation

    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
        terrain_provider=_NonFiniteTerrainProvider(),
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING


def test_partial_terrain_coverage_fails_closed() -> None:
    provider = GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.0002,
        step_lon_deg=0.0002,
        elevations_m=[[0.0, 0.0], [0.0, 0.0]],
    )
    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
        terrain_provider=provider,
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING
    assert "sample_lat" in result.failure.context


def test_narrow_obstacle_away_from_midpoint_is_detected() -> None:
    mission = _mission_with_obstacle_clearance()
    geod = Geod(ellps="WGS84")
    track_deg, _, distance_m = geod.inv(4.0, 52.0, 4.002, 52.001)
    lon, lat, _ = geod.fwd(4.0, 52.0, track_deg, distance_m * 0.25)
    obstacle = Obstacle.model_validate(
        {
            "id": "quarter-leg-mast",
            "geometry": {"type": "point", "points": [{"lat": lat, "lon": lon}]},
            "height_m": 110.0,
            "radius_m": 1.0,
        }
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        obstacle_provider=ListObstacleProvider([obstacle]),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.context["obstacle_id"] == "quarter-leg-mast"


def test_grazing_positive_radius_obstacle_is_checked_continuously() -> None:
    mission = make_mission()
    mission.constraints = mission.constraints.model_copy(
        update={"min_obstacle_clearance_m": 0.0}
    )
    options = EstimationOptions(max_segment_length_m=20.0)
    baseline = estimate_mission_distance_time(mission, make_vehicle(), options=options)
    geod = Geod(ellps="WGS84")
    samples_by_leg = route_leg_samples(
        baseline.legs,
        geod=geod,
        max_segment_length_m=20.0,
        hazard_footprint_m=10.0,
    )
    leg_samples = next(samples for samples in samples_by_leg if len(samples) >= 3)
    start, end = leg_samples[1:3]
    track_deg, _, distance_m = geod.inv(start.lon, start.lat, end.lon, end.lat)
    midpoint_lon, midpoint_lat, _ = geod.fwd(
        start.lon,
        start.lat,
        track_deg,
        distance_m / 2.0,
    )
    obstacle_lon, obstacle_lat, _ = geod.fwd(
        midpoint_lon,
        midpoint_lat,
        track_deg + 90.0,
        9.99,
    )
    obstacle = Obstacle.model_validate(
        {
            "id": "grazing-mast",
            "geometry": {
                "type": "point",
                "points": [{"lat": obstacle_lat, "lon": obstacle_lon}],
            },
            "height_m": 10_000.0,
            "radius_m": 10.0,
        }
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=options,
        obstacle_provider=ListObstacleProvider([obstacle]),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.context["obstacle_id"] == "grazing-mast"
    assert result.failure.context["horizontal_distance_m"] == pytest.approx(
        9.99, abs=0.02
    )


def test_zero_width_line_crossing_is_checked_continuously() -> None:
    mission = make_mission()
    mission.constraints = mission.constraints.model_copy(
        update={"min_obstacle_clearance_m": 0.0}
    )
    geod = Geod(ellps="WGS84")
    track_deg, _, distance_m = geod.inv(4.0, 52.0, 4.002, 52.001)
    crossing_lon, crossing_lat, _ = geod.fwd(4.0, 52.0, track_deg, distance_m * 0.31)
    left_lon, left_lat, _ = geod.fwd(crossing_lon, crossing_lat, track_deg - 90.0, 10.0)
    right_lon, right_lat, _ = geod.fwd(
        crossing_lon, crossing_lat, track_deg + 90.0, 10.0
    )
    obstacle = Obstacle.model_validate(
        {
            "id": "zero-width-wire",
            "geometry": {
                "type": "line",
                "points": [
                    {"lat": left_lat, "lon": left_lon},
                    {"lat": right_lat, "lon": right_lon},
                ],
            },
            "height_m": 110.0,
            "radius_m": 0.0,
        }
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        obstacle_provider=ListObstacleProvider([obstacle]),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.context["obstacle_id"] == "zero-width-wire"


def test_turn_arc_footprint_is_checked_for_obstacles() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="north",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.0,
            altitude_m=120.0,
        ),
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.02,
            altitude_m=120.0,
        ),
    ]
    options = EstimationOptions(fidelity=FidelityMode.V2)
    baseline = estimate_mission_distance_time(mission, make_vehicle(), options=options)
    samples_by_leg = route_leg_samples(
        baseline.legs,
        geod=Geod(ellps="WGS84"),
        max_segment_length_m=10.0,
    )
    arc_samples = next(
        samples
        for leg, samples in zip(baseline.legs, samples_by_leg, strict=True)
        if leg.phase == LegPhase.TURN_ARC
    )
    arc_midpoint = arc_samples[len(arc_samples) // 2]
    obstacle = Obstacle.model_validate(
        {
            "id": "turn-arc-mast",
            "geometry": {
                "type": "point",
                "points": [{"lat": arc_midpoint.lat, "lon": arc_midpoint.lon}],
            },
            "height_m": arc_midpoint.altitude_amsl_m,
            "radius_m": 2.0,
        }
    )
    constrained = mission.model_copy(
        update={
            "constraints": mission.constraints.model_copy(
                update={"min_obstacle_clearance_m": 5.0}
            )
        }
    )

    result = try_estimate_mission_distance_time(
        constrained,
        make_vehicle(),
        options=options,
        obstacle_provider=ListObstacleProvider([obstacle]),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.context["obstacle_id"] == "turn-arc-mast"


def test_spatial_sampler_honours_materialized_turn_polyline() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="north",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.0,
            altitude_m=120.0,
        ),
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.02,
            altitude_m=120.0,
        ),
    ]
    baseline = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(fidelity=FidelityMode.V2),
    )
    samples_by_leg = route_leg_samples(
        baseline.legs,
        geod=Geod(ellps="WGS84"),
        max_segment_length_m=1_000.0,
    )
    arc, arc_samples = next(
        (leg, samples)
        for leg, samples in zip(baseline.legs, samples_by_leg, strict=True)
        if leg.phase == LegPhase.TURN_ARC
    )

    assert arc.path_coordinates is not None
    assert len(arc_samples) == len(arc.path_coordinates)
    for sample, (expected_lon, expected_lat) in zip(
        arc_samples, arc.path_coordinates, strict=True
    ):
        assert sample.lon == pytest.approx(expected_lon)
        assert sample.lat == pytest.approx(expected_lat)


def test_spatial_sampler_interpolates_materialized_polyline_on_geodesic() -> None:
    baseline = estimate_mission_distance_time(make_mission(), make_vehicle())
    leg = next(leg for leg in baseline.legs if leg.horizontal_distance_m > 100.0)
    leg._set_path_coordinates(
        ((leg.start_lon, leg.start_lat), (leg.end_lon, leg.end_lat))
    )
    geod = Geod(ellps="WGS84")

    samples = route_leg_samples(
        [leg],
        geod=geod,
        max_segment_length_m=leg.horizontal_distance_m / 2.0,
    )[0]
    track_deg, _, distance_m = geod.inv(
        leg.start_lon,
        leg.start_lat,
        leg.end_lon,
        leg.end_lat,
    )
    expected_lon, expected_lat, _ = geod.fwd(
        leg.start_lon,
        leg.start_lat,
        track_deg,
        distance_m / 2.0,
    )

    midpoint = min(samples, key=lambda sample: abs(sample.fraction - 0.5))
    assert midpoint.fraction == pytest.approx(0.5)
    assert midpoint.lon == pytest.approx(expected_lon)
    assert midpoint.lat == pytest.approx(expected_lat)


def test_spatial_sampler_does_not_coarsen_submetre_hazard_resolution() -> None:
    baseline = estimate_mission_distance_time(make_mission(), make_vehicle())
    samples_by_leg = route_leg_samples(
        baseline.legs,
        geod=Geod(ellps="WGS84"),
        max_segment_length_m=None,
        hazard_footprint_m=0.1,
    )
    geod = Geod(ellps="WGS84")

    for samples in samples_by_leg:
        for start, end in zip(samples, samples[1:]):
            _, _, distance_m = geod.inv(
                start.lon,
                start.lat,
                end.lon,
                end.lat,
            )
            assert abs(distance_m) <= 0.05 + 1e-6


def test_missing_obstacle_inputs_leaves_obstacle_block_inactive() -> None:
    result = try_estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.status == EstimateStatus.SUCCESS
    assert result.obstacle is None


def test_obstacle_loader_reads_fixture() -> None:
    provider, document = load_obstacles(_FIXTURE_ROOT / "obstacles.geojson")

    obstacles = provider.obstacles()
    assert document.format == "geojson"
    assert len(obstacles) == 1
    assert obstacles[0].id == "mast-midpoint"
    assert obstacles[0].height_m == pytest.approx(105.0)


def test_obstacle_outputs_surface_clearance_result(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_obstacle_inputs(tmp_path)

    json_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "json"]
    )
    checklist_result = _RUNNER.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--format", "checklist"],
    )
    summary_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "summary"]
    )
    markdown_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "markdown"]
    )
    geojson_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "geojson"]
    )

    assert json_result.exit_code == int(CliExitCode.INFEASIBLE)
    payload = json.loads(json_result.stdout)
    assert payload["result"]["obstacle"]["is_feasible"] is False
    assert "Obstacle clearance" in checklist_result.stdout
    assert "FAIL" in checklist_result.stdout
    assert "obstacle FAIL" in summary_result.stdout
    assert "## Obstacle Clearance" in markdown_result.stdout
    geojson = json.loads(geojson_result.stdout)
    obstacle_features = [
        feature
        for feature in geojson["features"]
        if feature["properties"]["layer"] == "obstacles"
    ]
    assert obstacle_features
    assert obstacle_features[0]["properties"]["conflict"] is True


def test_obstacle_uncertainty_widens_the_required_clearance() -> None:
    """uncertainty_m must enlarge the keep-out radius, not be advisory.

    Removing the term from the clearance sum left the whole suite green, so a
    survey obstacle whose position is only known to +-30 m could be flown at
    40 m with a 15 m clearance requirement and still report GO.
    """

    geod = Geod(ellps="WGS84")
    offset_m = 40.0
    obstacle_lon, obstacle_lat, _ = geod.fwd(4.01, 52.0, 0.0, offset_m)

    def run(uncertainty_m: float):
        mission = make_mission()
        mission.constraints.require_rth_reserve = False
        mission.constraints.min_obstacle_clearance_m = 15.0
        mission.route = [
            RouteItem(
                id="east",
                action=MissionAction.WAYPOINT,
                lat=52.0,
                lon=4.02,
                altitude_m=120.0,
            )
        ]
        obstacle = Obstacle.model_validate(
            {
                "id": "mast",
                "geometry": {
                    "type": "point",
                    "points": [{"lat": obstacle_lat, "lon": obstacle_lon}],
                },
                "height_m": 200.0,
                "radius_m": 10.0,
                "uncertainty_m": uncertainty_m,
            }
        )
        return try_estimate_mission_distance_time(
            mission,
            make_vehicle(),
            obstacle_provider=ListObstacleProvider([obstacle]),
        )

    # radius 10 + clearance 15 = 25 m < 40 m offset: no violation on its own.
    assert run(0.0).obstacle.is_feasible is True
    # radius 10 + clearance 15 + uncertainty 30 = 55 m > 40 m offset.
    breached = run(30.0)
    assert breached.status == EstimateStatus.INFEASIBLE
    assert breached.obstacle is not None and breached.obstacle.is_feasible is False


def _mission_over(lon: float, *, clearance_m: float | None):
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.constraints.min_obstacle_clearance_m = clearance_m
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=52.0,
            lon=lon,
            altitude_m=120.0,
        )
    ]
    return mission


def test_vertical_only_leg_is_checked_against_obstacles() -> None:
    """A purely vertical leg is two samples at one lat/lon, not a line.

    The segment branch built a zero-length LineString whose intersection with
    the footprint is always empty, so take-off climbs and vertical landings
    were never checked: a 75 m mast 18 m from the pad reported feasible.
    """

    geod = Geod(ellps="WGS84")
    mast_lon, mast_lat, _ = geod.fwd(4.0, 52.0, 90.0, 18.0)
    mast = Obstacle.model_validate(
        {
            "id": "pad-mast",
            "geometry": {"type": "point", "points": [{"lat": mast_lat, "lon": mast_lon}]},
            "height_m": 75.0,
            "radius_m": 0.0,
        }
    )
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.constraints.min_obstacle_clearance_m = 20.0
    mission.route = [
        RouteItem(id="climb", action=MissionAction.VTOL_TAKEOFF, altitude_m=80.0)
    ]

    result = try_estimate_mission_distance_time(
        mission, make_vehicle(), obstacle_provider=ListObstacleProvider([mast])
    )

    assert result.obstacle is not None
    assert result.obstacle.is_feasible is False
    assert result.status == EstimateStatus.INFEASIBLE


def test_empty_obstacle_file_does_not_read_as_proven_clear() -> None:
    """Zero obstacles satisfied the evidence gate and reported PASS."""

    result = try_estimate_mission_distance_time(
        _mission_over(4.02, clearance_m=15.0),
        make_vehicle(),
        obstacle_provider=ListObstacleProvider([]),
    )

    codes = {warning.code for warning in result.warnings}
    assert WarningCode.OBSTACLE_ZERO_FEATURES in codes


def test_zero_width_keep_out_volume_is_flagged() -> None:
    """Zero radius, zero uncertainty and no configured clearance proves nothing."""

    obstacle = Obstacle.model_validate(
        {
            "id": "mast",
            "geometry": {"type": "point", "points": [{"lat": 52.0, "lon": 4.01}]},
            "height_m": 200.0,
            "radius_m": 0.0,
        }
    )
    provider = ListObstacleProvider([obstacle])

    vacuous = try_estimate_mission_distance_time(
        _mission_over(4.02, clearance_m=None), make_vehicle(), obstacle_provider=provider
    )
    configured = try_estimate_mission_distance_time(
        _mission_over(4.02, clearance_m=15.0), make_vehicle(), obstacle_provider=provider
    )

    assert WarningCode.OBSTACLE_KEEP_OUT_NOT_CONFIGURED in {
        warning.code for warning in vacuous.warnings
    }
    # With a real clearance the obstacle is actually detected, not just warned about.
    assert WarningCode.OBSTACLE_KEEP_OUT_NOT_CONFIGURED not in {
        warning.code for warning in configured.warnings
    }
    assert configured.obstacle is not None
    assert configured.obstacle.is_feasible is False
