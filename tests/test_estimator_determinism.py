from estimator import estimate_mission_distance_time
from tests.helpers import make_mission
from tests.helpers import make_vehicle


def test_estimator_is_deterministic_for_same_inputs() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    first = estimate_mission_distance_time(mission, vehicle)
    second = estimate_mission_distance_time(mission, vehicle)

    assert first.model_dump() == second.model_dump()

