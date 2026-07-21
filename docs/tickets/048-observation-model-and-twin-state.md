# Ticket 048: Closed-Loop Observation Model and Twin-State Architecture

> Safety status: only the sensor/EKF diagnostic path remains enabled in
> `stochastic.v2`. It is conditional on modeled-pass samples and makes no
> operational-feasibility claim.

## Goal

Replace the open-loop propagator from Ticket 047 with a closed-loop
stochastic filter by introducing a separate "true state" and "estimated
state", synthetic sensor measurement models, and a Bayesian (EKF-style)
update step. Policy decisions — reserve checks, lost-link triggers, RTL
firing — are made off the *estimated* state rather than ground truth,
matching how a real autopilot behaves.

## Current Gap

After Ticket 047 the propagator carries a belief distribution forward through
time using process noise, but that distribution is never corrected. Uncertainty
grows monotonically because no measurements arrive to narrow it. More
critically, all policy triggers still operate on the true state: the vehicle
transitions to the next waypoint when its *true* position reaches the
acceptance radius, the reserve check fires when its *true* energy falls below
the threshold. A real autopilot acts on its *estimated* state from an onboard
EKF. The gap between truth and estimate — driven by sensor noise and limited
update rates — determines when and whether policies fire, which is the
operationally relevant question.

This ticket closes that gap by splitting the propagation loop into two parallel
tracks that interact through a sensor model.

## Twin-State Architecture

Each propagation sample maintains two state vectors per time step:

**True state** (`TrueStateVector`) — governed by physics:
```
lat, lon, alt_amsl_m         # true position
energy_remaining_wh          # true energy (from actual power draw)
wind_east_mps, wind_north_mps  # true wind (from WindProvider + process noise)
```

**Estimated state** (`EstimatedStateVector`) — the autopilot's belief:
```
lat, lon, alt_amsl_m         # EKF position estimate
energy_remaining_wh          # coulomb-counted energy estimate
wind_east_mps, wind_north_mps  # EKF wind estimate
covariance: 6×6 matrix       # full state covariance
```

The true state propagates via the existing kinematic model (Ticket 047
prediction step). The estimated state propagates via the EKF prediction step,
then is corrected by synthetic measurements drawn from the sensor models
described below.

All policy decisions use the **estimated state**. All physics (energy
consumption, actual position advance) use the **true state**.

## Sensor Models

Three sensor types for MVP, each configured via a new `SensorProfile` in the
vehicle schema. All are optional; when absent, the corresponding measurement
is assumed perfect (the Ticket 047 behaviour is preserved).

### GPS Position Fix

```python
class GpsModel(BaseModel):
    horizontal_accuracy_m: float = 2.5   # 1-sigma CEP
    vertical_accuracy_m: float = 4.0
    fix_rate_hz: float = 5.0             # measurement arrival rate
    availability: float = 1.0           # fraction of time fix is available [0, 1]
```

Measurement: `z_gps = true_position + N(0, horizontal_accuracy_m²·I)`
delivered at `fix_rate_hz`. When unavailable (sampled from `availability`),
the estimated position propagates dead-reckoning only.

### Battery Voltage / Coulomb Counting

```python
class BatteryMeterModel(BaseModel):
    current_sensor_noise_pct: float = 1.0  # 1-sigma, % of reading
    voltage_noise_mv: float = 10.0
    update_rate_hz: float = 10.0
```

Measurement: energy consumed since last step, corrupted by current sensor
noise. Accumulates coulomb-counting drift over time.

### Airspeed (Pitot)

```python
class AirspeedModel(BaseModel):
    bias_mps: float = 0.0         # systematic offset
    noise_std_mps: float = 0.3    # 1-sigma random noise
    update_rate_hz: float = 10.0
```

Measurement: `z_airspeed = true_tas + bias + N(0, noise_std_mps²)`. Used to
correct the wind estimate component of the EKF.

### `SensorProfile` addition to `VehicleProfile`

```python
class SensorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gps: GpsModel | None = None
    battery_meter: BatteryMeterModel | None = None
    airspeed: AirspeedModel | None = None
```

Add `sensors: SensorProfile | None = None` to `VehicleProfile`. When `None`,
all measurements are perfect and the twin-state update reduces to the Ticket
047 open-loop propagator (full backwards compatibility).

## EKF Update Step

At each time step `t`, for each sample:

1. **Predict**: advance estimated state and covariance using the kinematic
   model (same as the true-state prediction, using the estimated wind).
2. **Measure**: for each sensor whose `1/update_rate_hz` aligns with `t`,
   draw a noisy measurement from the true state.
3. **Update**: apply the standard EKF innovation step:
   `K = P·Hᵀ·(H·P·Hᵀ + R)⁻¹`, `x̂ ← x̂ + K·(z − H·x̂)`,
   `P ← (I − K·H)·P`.
4. **Policy evaluation**: evaluate reserve check, waypoint transition, and
   any scenario assertions against the updated estimated state.

A linearised `H` matrix is sufficient for MVP (position and energy components
are already linear in the state).

## Schema Changes

New file: `schemas/vehicle_sensors.py`
- `GpsModel`, `BatteryMeterModel`, `AirspeedModel`, `SensorProfile`

Modified: `schemas/vehicle.py`
- Add `sensors: SensorProfile | None = None` to `VehicleProfile`

Modified: `schemas/stochastic.py` (from Ticket 047)
- `StochasticPropagationResult` gains `estimation_error_timeline`:

```python
class EstimationErrorTimelinePoint(BaseModel):
    elapsed_time_s: float
    position_error_m: SampleStats    # |true_pos − estimated_pos|
    energy_error_wh: SampleStats     # |true_energy − estimated_energy|
```

## File Plan

New files:

| File | Purpose |
|---|---|
| `schemas/vehicle_sensors.py` | `GpsModel`, `BatteryMeterModel`, `AirspeedModel`, `SensorProfile` |
| `estimator/execution/propagator_ekf.py` | EKF prediction and update steps |
| `estimator/execution/sensor_models.py` | Measurement draw functions per sensor type |
| `tests/test_observation_model.py` | Unit tests for EKF update, sensor draw, twin-state consistency |

Modified files:

- `schemas/vehicle.py` — add `sensors` field
- `schemas/vehicle_sensors.py` — new module
- `schemas/__init__.py` — export `SensorProfile`, `GpsModel`, etc.
- `estimator/execution/propagator.py` — wire in EKF update when `sensors` is set
- `schemas/stochastic.py` — add `estimation_error_timeline`

## Integration Requirements

- When `vehicle.sensors is None`, the twin-state update must be a no-op and
  results must be numerically identical to Ticket 047 output (same seed,
  same inputs).
- The `propagate` CLI and `stochastic-envelope.v1` schema are unchanged;
  `estimation_error_timeline` is an optional field defaulting to `[]`.
- Must compose with all existing `WindProvider` implementations.

## Acceptance Criteria

1. With a perfect GPS model (`horizontal_accuracy_m=0`, `availability=1`),
   `position_error_m.mean` is zero at all time steps.
2. With `availability=0` (GPS off), position error grows monotonically
   (dead-reckoning drift).
3. A higher `horizontal_accuracy_m` produces a wider `position_error_m`
   distribution at all time steps.
4. With `sensors=None`, results are numerically identical to Ticket 047
   (backwards compatibility).
5. `p_reserve_violation` is affected by battery meter noise: a noisy meter
   produces earlier or later reserve triggers than a perfect meter.
6. Same seed produces identical results across two runs.
7. All existing tests continue to pass.
8. `uv run ruff check` passes.

## Out of Scope

- Ticket 049: stochastic closed-loop control — modeling how estimation error
  propagates into trajectory deviation via the autopilot's tracking controller.
- Ticket 050: contingency trigger probability derived from the twin-state
  timeline.
- Ticket 051: SITL telemetry replay to condition the belief state.
