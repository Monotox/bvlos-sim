from estimator import (
    ConstantElevationProvider,
    LayeredWindProvider,
    WindLayer,
    estimate_mission_distance_time,
)
from estimator.core.enums import FidelityMode
from estimator.core.options import EstimationOptions
from tests.helpers import make_mission, make_vehicle


def test_estimator_is_deterministic_for_same_inputs() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    first = estimate_mission_distance_time(mission, vehicle)
    second = estimate_mission_distance_time(mission, vehicle)

    assert first.model_dump() == second.model_dump()


def test_estimator_is_deterministic_with_wind_provider() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    provider = LayeredWindProvider(
        [
            WindLayer(altitude_m=0.0, wind_east_mps=3.0, wind_north_mps=-1.0),
            WindLayer(altitude_m=200.0, wind_east_mps=6.0, wind_north_mps=0.0),
        ]
    )

    first = estimate_mission_distance_time(mission, vehicle, wind_provider=provider)
    second = estimate_mission_distance_time(mission, vehicle, wind_provider=provider)

    assert first.model_dump() == second.model_dump()


def test_estimator_is_deterministic_with_terrain_provider() -> None:
    from schemas.mission import AltitudeReference

    mission = make_mission()
    mission.defaults.altitude_reference = AltitudeReference.TERRAIN
    vehicle = make_vehicle()
    provider = ConstantElevationProvider(25.0)

    first = estimate_mission_distance_time(mission, vehicle, terrain_provider=provider)
    second = estimate_mission_distance_time(mission, vehicle, terrain_provider=provider)

    assert first.model_dump() == second.model_dump()


def test_estimator_v2_is_deterministic() -> None:
    from schemas.mission import MissionAction, RouteItem

    mission = make_mission()
    wp1 = RouteItem(
        id="north", action=MissionAction.WAYPOINT, lat=52.01, lon=4.0, altitude_m=120.0
    )
    wp2 = RouteItem(
        id="east", action=MissionAction.WAYPOINT, lat=52.01, lon=4.02, altitude_m=120.0
    )
    mission.route = [wp1, wp2, mission.route[-1]]
    vehicle = make_vehicle()
    options = EstimationOptions(
        wind_east_mps=2.0,
        wind_north_mps=-1.0,
        fidelity=FidelityMode.V2,
    )

    first = estimate_mission_distance_time(mission, vehicle, options=options)
    second = estimate_mission_distance_time(mission, vehicle, options=options)

    assert first.model_dump() == second.model_dump()
