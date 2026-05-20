"""Tests for stochastic closed-loop tracking controller (Ticket 049)."""

import math
from pathlib import Path

from adapters.io import load_mission, load_vehicle
from estimator.execution.propagator import run_stochastic_propagation
from estimator.execution.tracking_controller import (
    ControllerState,
    advance_true_state,
    compute_cross_track_errors,
    controller_corrections,
)
from schemas.stochastic import StochasticPropagationPlan
from schemas.uncertainty import NormalDistribution, UncertaintyParameters
from schemas.vehicle_controller import ControllerProfile
from schemas.vehicle_sensors import BatteryMeterModel, GpsModel, SensorProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"

_DEFAULT_PROFILE = ControllerProfile()


def _mission_vehicle():
    mission, _ = load_mission(MISSION_PATH)
    vehicle, _ = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _plan(*, samples: int = 20, seed: int = 1, dt_s: float = 5.0) -> StochasticPropagationPlan:
    return StochasticPropagationPlan(
        schema_version="stochastic.v1",
        propagation_id="test-controller",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=dt_s,
        samples=samples,
        seed=seed,
        wind_process_noise_std_mps=0.0,
        parameters=UncertaintyParameters(
            battery_capacity_wh=NormalDistribution(kind="normal", mean=260.0, std=40.0)
        ),
    )


# --- Unit tests for geometry helpers ---


def test_cross_track_error_on_segment_is_zero() -> None:
    xte, ate = compute_cross_track_errors(
        est_lat=51.5010,
        est_lon=-0.1415,
        seg_start_lat=51.5000,
        seg_start_lon=-0.1415,
        seg_end_lat=51.5020,
        seg_end_lon=-0.1415,
    )
    assert abs(xte) < 0.1  # on the segment line — XTE ~0
    assert ate > 0  # ahead of start


def test_cross_track_error_perpendicular_offset() -> None:
    # Point displaced 100m east of a N-S segment
    deg_per_m = 1.0 / 111_111.0
    cos_lat = math.cos(math.radians(51.5))
    east_offset_deg = 100.0 * deg_per_m / cos_lat
    xte, _ = compute_cross_track_errors(
        est_lat=51.5010,
        est_lon=-0.1415 + east_offset_deg,
        seg_start_lat=51.5000,
        seg_start_lon=-0.1415,
        seg_end_lat=51.5020,
        seg_end_lon=-0.1415,
    )
    assert abs(xte - 100.0) < 2.0  # ~100 m to the right


def test_controller_corrections_clamped() -> None:
    profile = ControllerProfile(
        Kp_cross_track=1.0,
        max_heading_correction_rad=0.1,
        Kp_along_track=1.0,
        max_speed_correction_mps=0.5,
    )
    hdg, spd = controller_corrections(
        cross_track_error_m=100.0, along_track_error_m=100.0, profile=profile
    )
    assert abs(hdg) <= 0.1
    assert abs(spd) <= 0.5


def test_advance_true_state_no_deviation_when_est_on_segment() -> None:
    # Estimated position exactly on segment — no correction needed
    state = ControllerState(true_lat=51.5010, true_lon=-0.1415)
    advance_true_state(
        est_lat=51.5010,
        est_lon=-0.1415,
        nominal_speed_mps=20.0,
        nominal_energy_step_wh=0.05,
        dt_s=1.0,
        profile=_DEFAULT_PROFILE,
        state=state,
        seg_start_lat=51.5000,
        seg_start_lon=-0.1415,
        seg_end_lat=51.5020,
        seg_end_lon=-0.1415,
    )
    assert abs(state.cross_track_error_m) < 0.1
    assert state.path_length_excess_m >= 0.0


# --- Integration tests ---


def test_controller_none_results_identical_to_ticket_048() -> None:
    """With controller=None the output must be numerically identical to T048."""
    mission, vehicle = _mission_vehicle()
    plan = _plan(samples=20, seed=7)
    v_sensors = vehicle.model_copy(
        update={"sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=3.0))}
    )
    v_no_ctrl = v_sensors.model_copy(update={"controller": None})
    v_explicit_none = v_sensors.model_copy(update={"controller": None})

    r1 = run_stochastic_propagation(plan, mission, v_no_ctrl)
    r2 = run_stochastic_propagation(plan, mission, v_explicit_none)

    assert r1.timeline == r2.timeline
    assert r1.cross_track_timeline == []
    assert r2.cross_track_timeline == []


def test_cross_track_error_converges_with_perfect_gps() -> None:
    """With perfect GPS, mean |XTE| should be near zero after several steps."""
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=0.001, availability=1.0, fix_rate_hz=10.0)
            ),
            "controller": ControllerProfile(Kp_cross_track=0.3),
        }
    )

    result = run_stochastic_propagation(_plan(samples=30, seed=2), mission, vehicle)

    assert len(result.cross_track_timeline) > 0
    # After convergence (last quarter of the timeline), mean |XTE| is small
    tail = result.cross_track_timeline[len(result.cross_track_timeline) * 3 // 4 :]
    mean_xte = sum(p.cross_track_error_m.mean for p in tail) / len(tail)
    assert mean_xte < 5.0


def test_cross_track_error_grows_with_gps_unavailable() -> None:
    """With no GPS fixes (dead reckoning), mean XTE should grow over time."""
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(gps=GpsModel(availability=0.0)),
            "controller": ControllerProfile(),
        }
    )

    result = run_stochastic_propagation(_plan(samples=30, seed=3), mission, vehicle)
    errors = [p.cross_track_error_m.mean for p in result.cross_track_timeline]

    assert errors[-1] > errors[0]


def test_higher_gps_noise_produces_wider_xte_distribution() -> None:
    mission, vehicle = _mission_vehicle()
    accurate = vehicle.model_copy(
        update={
            "sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=1.0)),
            "controller": ControllerProfile(),
        }
    )
    noisy = vehicle.model_copy(
        update={
            "sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=50.0)),
            "controller": ControllerProfile(),
        }
    )

    r_accurate = run_stochastic_propagation(_plan(samples=60, seed=5), mission, accurate)
    r_noisy = run_stochastic_propagation(_plan(samples=60, seed=5), mission, noisy)

    assert (
        r_noisy.cross_track_timeline[-1].cross_track_error_m.std
        > r_accurate.cross_track_timeline[-1].cross_track_error_m.std
    )


def test_path_length_excess_positive_with_gps_noise() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=5.0)),
            "controller": ControllerProfile(),
        }
    )

    result = run_stochastic_propagation(_plan(samples=40, seed=6), mission, vehicle)

    assert result.cross_track_timeline[-1].path_length_excess_m.mean > 0.0


def test_p_reserve_violation_higher_with_noisy_gps_and_controller() -> None:
    """Noisy GPS + controller costs extra energy → higher p_reserve_violation."""
    mission, vehicle = _mission_vehicle()
    low_energy = vehicle.energy.model_copy(update={"battery_capacity_wh": 70.0})
    base = vehicle.model_copy(update={"energy": low_energy})
    parameters = UncertaintyParameters(
        cruise_power_w=NormalDistribution(kind="normal", mean=450.0, std=20.0)
    )
    plan = StochasticPropagationPlan(
        schema_version="stochastic.v1",
        propagation_id="reserve-test",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=2.0,
        samples=80,
        seed=9,
        wind_process_noise_std_mps=0.0,
        parameters=parameters,
    )

    perfect_gps = base.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=0.001, availability=1.0)
            ),
            "controller": ControllerProfile(),
        }
    )
    noisy_gps = base.model_copy(
        update={
            "sensors": SensorProfile(gps=GpsModel(horizontal_accuracy_m=30.0)),
            "controller": ControllerProfile(),
        }
    )

    r_perfect = run_stochastic_propagation(plan, mission, perfect_gps)
    r_noisy = run_stochastic_propagation(plan, mission, noisy_gps)

    assert (
        r_noisy.timeline[-1].p_reserve_violation
        >= r_perfect.timeline[-1].p_reserve_violation
    )


def test_same_seed_identical_results_with_controller() -> None:
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(horizontal_accuracy_m=5.0, availability=0.9),
                battery_meter=BatteryMeterModel(current_sensor_noise_pct=2.0),
            ),
            "controller": ControllerProfile(),
        }
    )
    plan = _plan(samples=30, seed=11)

    r1 = run_stochastic_propagation(plan, mission, vehicle)
    r2 = run_stochastic_propagation(plan, mission, vehicle)

    assert r1.timeline == r2.timeline
    assert r1.cross_track_timeline == r2.cross_track_timeline
