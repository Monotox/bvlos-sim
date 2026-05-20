"""Tests for stochastic observation model and twin-state tracking."""

from pathlib import Path

from adapters.io import load_mission, load_vehicle
from estimator.execution.propagator import run_stochastic_propagation
from schemas.stochastic import StochasticPropagationPlan
from schemas.uncertainty import NormalDistribution, UncertaintyParameters
from schemas.vehicle_sensors import BatteryMeterModel, GpsModel, SensorProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"


def _mission_vehicle():
    mission, _mission_document = load_mission(MISSION_PATH)
    vehicle, _vehicle_document = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _plan(
    *,
    samples: int = 20,
    seed: int = 1,
    dt_s: float = 5.0,
    parameters: UncertaintyParameters | None = None,
) -> StochasticPropagationPlan:
    return StochasticPropagationPlan(
        schema_version="stochastic.v1",
        propagation_id="test-observation",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=dt_s,
        samples=samples,
        seed=seed,
        wind_process_noise_std_mps=0.0,
        parameters=(
            parameters
            if parameters is not None
            else UncertaintyParameters(
                battery_capacity_wh=NormalDistribution(
                    kind="normal", mean=260.0, std=80.0
                )
            )
        ),
    )



def test_perfect_gps_produces_zero_position_error() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(
                    horizontal_accuracy_m=0.001,
                    availability=1.0,
                    fix_rate_hz=10.0,
                )
            )
        }
    )

    result = run_stochastic_propagation(_plan(samples=20, seed=4), mission, vehicle)

    assert all(
        point.position_error_m.mean < 0.01
        for point in result.estimation_error_timeline
    )


def test_gps_unavailable_position_error_grows() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={"sensors": SensorProfile(gps=GpsModel(availability=0.0))}
    )

    result = run_stochastic_propagation(_plan(samples=20, seed=4), mission, vehicle)
    errors = [p.position_error_m.mean for p in result.estimation_error_timeline]

    assert errors[-1] > errors[0]


def test_higher_gps_accuracy_produces_wider_error() -> None:
    mission, vehicle = _mission_vehicle()
    gps_accurate = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=1.0, availability=1.0)
            )
        }
    )
    gps_noisy = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=50.0, availability=1.0)
            )
        }
    )

    accurate = run_stochastic_propagation(
        _plan(samples=60, seed=5), mission, gps_accurate
    )
    noisy = run_stochastic_propagation(_plan(samples=60, seed=5), mission, gps_noisy)

    assert (
        noisy.estimation_error_timeline[-1].position_error_m.std
        > accurate.estimation_error_timeline[-1].position_error_m.std
    )


def test_sensors_none_results_identical_to_ticket_047() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(samples=30, seed=12)
    vehicle_no_sensors = vehicle.model_copy(update={"sensors": None})

    result = run_stochastic_propagation(plan, mission, vehicle_no_sensors)
    result_no_sensors = run_stochastic_propagation(plan, mission, vehicle)

    assert result.timeline == result_no_sensors.timeline
    assert result.estimation_error_timeline == []


def test_battery_meter_noise_affects_p_reserve_violation() -> None:
    mission, vehicle = _mission_vehicle()
    low_energy = vehicle.energy.model_copy(update={"battery_capacity_wh": 56.0})
    low_battery_vehicle = vehicle.model_copy(update={"energy": low_energy})
    parameters = UncertaintyParameters(
        cruise_power_w=NormalDistribution(kind="normal", mean=450.0, std=30.0)
    )
    perfect_meter = low_battery_vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                battery_meter=BatteryMeterModel(current_sensor_noise_pct=0.0)
            )
        }
    )
    noisy_meter = low_battery_vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                battery_meter=BatteryMeterModel(current_sensor_noise_pct=5.0)
            )
        }
    )

    perfect = run_stochastic_propagation(
        _plan(samples=80, seed=9, dt_s=2.0, parameters=parameters),
        mission,
        perfect_meter,
    )
    noisy = run_stochastic_propagation(
        _plan(samples=80, seed=9, dt_s=2.0, parameters=parameters),
        mission,
        noisy_meter,
    )

    assert perfect.timeline[-1].p_reserve_violation != noisy.timeline[-1].p_reserve_violation


def test_same_seed_identical_results_with_sensors() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=5.0, availability=0.8),
                battery_meter=BatteryMeterModel(current_sensor_noise_pct=2.0),
            )
        }
    )
    plan = _plan(samples=30, seed=15)

    first = run_stochastic_propagation(plan, mission, vehicle)
    second = run_stochastic_propagation(plan, mission, vehicle)

    assert first.timeline == second.timeline


def test_estimation_error_timeline_populated_when_sensors_set() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={"sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=2.5))}
    )

    result = run_stochastic_propagation(_plan(samples=20, seed=6), mission, vehicle)

    assert len(result.estimation_error_timeline) == len(result.timeline)
    assert all(
        point.position_error_m.mean >= 0 and point.energy_error_wh.mean >= 0
        for point in result.estimation_error_timeline
    )


def test_estimation_error_timeline_empty_when_no_sensors() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(update={"sensors": None})

    result = run_stochastic_propagation(_plan(samples=20, seed=6), mission, vehicle)

    assert result.estimation_error_timeline == []
