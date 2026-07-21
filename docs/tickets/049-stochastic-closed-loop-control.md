# Ticket 049: Stochastic Closed-Loop Control

> Safety status: disabled in `stochastic.v2`. Vehicles containing a
> `controller` profile are rejected by `propagate`; the prototype behavior and
> acceptance claims below are retained only as historical design notes.

## Goal

Close the full physical loop of the simulation by adding an autopilot tracking
controller model that connects the EKF estimated state (from Ticket 048) back
to the true trajectory. After this ticket the flown path is a stochastic
process: estimation error causes actual position deviations from the planned
path, which the controller partially corrects — producing realistic
cross-track error statistics and a path-length distribution that affects
reserve consumption.

## Current Gap

After Ticket 048 the twin-state architecture maintains a true state and an
estimated state that diverge due to sensor noise. However, the true-state
kinematics still assume the vehicle flies the *planned* trajectory perfectly.
The control loop is missing: there is no model of how the autopilot uses the
EKF estimate to generate steering commands, and no model of how estimation
error causes deviations in the actually flown path.

In reality the full physical loop is:

```
true_state ──► sensor measurements ──► EKF estimate ──► tracking controller
     ▲                                                          │
     └────────────────── control input ◄───────────────────────┘
```

Without the controller leg, estimation error never feeds back into the true
trajectory. Cross-track deviation, path-length growth due to weaving, and the
associated reserve penalties are all invisible. This ticket adds that feedback
path.

## Tracking Controller Model

The autopilot's path-following controller is modelled as a proportional
cross-track error (CXTE) regulator — the dominant term in fixed-wing L1 and
multirotor PD path-following controllers:

```
cross_track_error_m   = perpendicular distance from estimated position to
                        planned segment, positive to the right
along_track_error_m   = estimated position ahead (+) or behind (−) the
                        nominal position on the segment at time t

heading_correction_rad = -Kp_xte * cross_track_error_m
speed_correction_mps   = -Kp_ate * along_track_error_m
```

The corrected heading and speed are applied to the true-state dynamics in
the next time step. Estimation error enters via the cross-track computation:
the controller measures cross-track from the *estimated* position, but the
correction is applied to the *true* velocity vector.

### `ControllerProfile`

```python
class ControllerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Kp_cross_track: float = 0.15    # heading correction per metre of XTE (rad/m)
    Kp_along_track: float = 0.05    # speed correction per metre of ATE (m/s/m)
    max_heading_correction_rad: float = 0.524  # ±30°
    max_speed_correction_mps: float = 2.0
```

Add `controller: ControllerProfile | None = None` to `VehicleProfile`.
When `None`, the vehicle follows the planned path exactly (Ticket 047 and 048
behaviour is preserved).

## State Extension

The per-sample state gains two new components carried across time steps:

```
cross_track_error_m    # accumulated lateral deviation from planned path
along_track_error_m    # longitudinal deviation from nominal position
```

These are used by the controller at each step and reset to zero at waypoint
transitions.

## Timeline Extension

`PropagationTimelinePoint` gains:

```python
class CrossTrackStats(BaseModel):
    elapsed_time_s: float
    cross_track_error_m: SampleStats   # distribution of |CXTE| across samples
    along_track_error_m: SampleStats   # distribution of ATE across samples
    path_length_excess_m: SampleStats  # extra distance flown vs planned leg
```

`StochasticPropagationResult` gains:

```python
cross_track_timeline: list[CrossTrackStats] = []
```

`path_length_excess_m` affects energy consumption: excess path length
multiplies cruise-power energy draw proportionally, feeding back into
`p_reserve_violation` via the energy state.

## Propagation Loop Changes

At each time step `t`, for each sample, after the EKF update (Ticket 048):

1. **Controller step**: compute `cross_track_error` and `along_track_error`
   from the *estimated* position vs. the planned segment at `t`.
2. **Apply corrections**: compute corrected heading and speed from the
   controller gains; clamp to configured limits.
3. **True-state advance**: integrate the true-state position using the
   corrected heading and speed (not the planned heading and speed).
4. **Path excess**: accumulate `|true_position − nominal_position_on_segment|`
   as `path_length_excess_m`.
5. **Energy update**: consume cruise power for the true path length stepped,
   not the nominal planned-segment increment.

## Schema Changes

New file: `schemas/vehicle_controller.py`
- `ControllerProfile`

Modified: `schemas/vehicle.py`
- Add `controller: ControllerProfile | None = None` to `VehicleProfile`

Modified: `schemas/stochastic.py`
- Add `CrossTrackStats` model
- Add `cross_track_timeline: list[CrossTrackStats] = []` to
  `StochasticPropagationResult`

Modified: `schemas/__init__.py`
- Export `ControllerProfile`, `CrossTrackStats`

## File Plan

New files:

| File | Purpose |
|---|---|
| `schemas/vehicle_controller.py` | `ControllerProfile` |
| `estimator/execution/tracking_controller.py` | Cross-track/along-track error and controller step |
| `tests/test_tracking_controller.py` | Unit tests for controller model and feedback loop |

Modified files:

- `schemas/vehicle.py` — add `controller` field
- `schemas/stochastic.py` — add `CrossTrackStats`, `cross_track_timeline`
- `schemas/__init__.py` — export new types
- `estimator/execution/propagator.py` — wire in controller step after EKF update
- `estimator/execution/propagator_ekf.py` — expose per-sample state struct

## Integration Requirements

- When `vehicle.controller is None`, the propagation loop must produce
  numerically identical results to Ticket 048 output (same seed, same inputs).
- Requires `vehicle.sensors` to be set (Ticket 048) for the EKF estimated state
  that drives the controller; if `sensors is None` the controller is also
  treated as absent.
- Must compose with all existing `WindProvider` implementations.
- `path_length_excess_m` contributions must feed back into energy state so
  that `p_reserve_violation` reflects path-length growth.

## Acceptance Criteria

1. With `controller=None`, results are numerically identical to Ticket 048
   output (backwards compatibility).
2. With non-zero `Kp_cross_track` and a perfect GPS model, mean
   `cross_track_error_m` converges to near zero after a few correction steps.
3. With GPS `availability=0` (no fixes, dead-reckoning only), mean
   `cross_track_error_m` grows monotonically due to accumulating estimation
   error.
4. A higher GPS `horizontal_accuracy_m` produces a wider
   `cross_track_error_m` distribution.
5. `path_length_excess_m.mean > 0` when GPS noise is non-zero, confirming
   the controller weaves around the planned path.
6. `p_reserve_violation` with a noisy GPS and controller enabled is greater
   than with a perfect GPS, reflecting the energy cost of path deviations.
7. Same seed produces identical results across two runs.
8. All existing tests continue to pass.
9. `uv run ruff check` passes.

## Out of Scope

- Ticket 050: contingency trigger probability — P(lost-link policy fires
  before waypoint N) derived from the twin-state timeline and cross-track
  statistics.
- Ticket 051: SITL telemetry replay to condition the belief state
  retrospectively and validate the controller model against observed tracks.
- Attitude dynamics (roll, pitch) — the controller model operates on position
  and heading only; full 6-DOF flight dynamics are out of scope for MVP.
- Multi-segment lookahead — the L1 guidance law uses a lookahead distance;
  this MVP uses instantaneous cross-track error only.
