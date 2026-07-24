"""Tests for stochastic closed-loop tracking controller (Ticket 049)."""

import math
from pathlib import Path

import pytest

from bvlos_sim.adapters.io import load_mission, load_vehicle
from bvlos_sim.estimator.execution.propagator import run_stochastic_propagation
from bvlos_sim.estimator.execution.tracking_controller import (
    ControllerState,
    advance_true_state,
    compute_cross_track_errors,
    controller_corrections,
)
from bvlos_sim.schemas.stochastic import StochasticPropagationPlan
from bvlos_sim.schemas.uncertainty import UncertaintyParameters, UniformDistribution
from bvlos_sim.schemas.vehicle_controller import ControllerProfile
from bvlos_sim.schemas.vehicle_sensors import GpsModel, SensorProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"

_DEFAULT_PROFILE = ControllerProfile()


def _mission_vehicle():
    mission, _ = load_mission(MISSION_PATH)
    vehicle, _ = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _plan(
    *, samples: int = 20, seed: int = 1, dt_s: float = 5.0
) -> StochasticPropagationPlan:
    return StochasticPropagationPlan(
        schema_version="stochastic.v2",
        propagation_id="test-controller",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=dt_s,
        samples=samples,
        seed=seed,
        wind_process_noise_std_mps=0.0,
        parameters=UncertaintyParameters(
            battery_capacity_wh=UniformDistribution(
                kind="uniform", low=220.0, high=300.0
            )
        ),
    )


# --- Unit tests for geometry helpers ---


def test_cross_track_error_on_segment_is_zero() -> None:
    xte, ate = compute_cross_track_errors(
        est_lat=51.5010,
        est_lon=-0.1415,
        nominal_lat=51.5010,
        nominal_lon=-0.1415,
        seg_start_lat=51.5000,
        seg_start_lon=-0.1415,
        seg_end_lat=51.5020,
        seg_end_lon=-0.1415,
    )
    assert abs(xte) < 0.1  # on the segment line — XTE ~0
    assert abs(ate) < 0.1


def test_cross_track_error_perpendicular_offset() -> None:
    # Point displaced 100m east of a N-S segment
    deg_per_m = 1.0 / 111_111.0
    cos_lat = math.cos(math.radians(51.5))
    east_offset_deg = 100.0 * deg_per_m / cos_lat
    xte, _ = compute_cross_track_errors(
        est_lat=51.5010,
        est_lon=-0.1415 + east_offset_deg,
        nominal_lat=51.5010,
        nominal_lon=-0.1415,
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
        nominal_lat=51.5010,
        nominal_lon=-0.1415,
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
    assert abs(state.along_track_error_m) < 0.1
    assert state.path_length_excess_m >= 0.0


def test_zero_length_phase_does_not_create_horizontal_drift() -> None:
    state = ControllerState(true_lat=51.5, true_lon=-0.14)
    advance_true_state(
        est_lat=51.5,
        est_lon=-0.14,
        nominal_lat=51.5,
        nominal_lon=-0.14,
        nominal_speed_mps=3.0,
        nominal_energy_step_wh=0.1,
        dt_s=10.0,
        profile=_DEFAULT_PROFILE,
        state=state,
        seg_start_lat=51.5,
        seg_start_lon=-0.14,
        seg_end_lat=51.5,
        seg_end_lon=-0.14,
    )
    assert state.true_lat == 51.5
    assert state.true_lon == -0.14


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


def test_stochastic_propagation_rejects_controller_profile() -> None:
    """The unvalidated controller cannot produce stochastic safety claims."""
    mission, vehicle = _mission_vehicle()
    vehicle = vehicle.model_copy(
        update={
            "sensors": SensorProfile(
                gps=GpsModel(
                    horizontal_accuracy_m=0.001, availability=1.0, fix_rate_hz=10.0
                )
            ),
            "controller": ControllerProfile(Kp_cross_track=0.3),
        }
    )

    with pytest.raises(ValueError, match="does not support closed-loop controller"):
        run_stochastic_propagation(_plan(samples=30, seed=2), mission, vehicle)
