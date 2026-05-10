# Estimator Report

- Status: `infeasible`
- Envelope schema: `estimator-envelope.v4`
- Tool version: `0.2.0`

## Result Validity

- Complete: `false`
- Partial: `false`
- Valid for full mission: `false`
- Scope: `none`

### Unavailable Fields

- `result.total_horizontal_distance_m`
- `result.total_vertical_distance_m`
- `result.total_path_distance_m`
- `result.total_time_s`

## Diagnostics

- `error` `WIND_TRIANGLE_NO_SOLUTION`: No wind-triangle solution exists for required crosswind correction.

## Assumptions

- Estimator v1 is deterministic and uses no randomness.
- Wind input is constant in space and time unless a different provider is added.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude is unsupported in estimator v1.
- Turn dynamics and sub-segment integration are excluded from estimator v1.
- Fixed-wing circular loiter is unsupported in estimator v1.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Static geofence feasibility uses 2D lon/lat route-segment geometry.
- Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `b232030aa35508ce45d2f34dd74779fc24013b66121a4ad2ff6c6e551bfd5db9`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `0.0`
- Vertical distance m: `0.0`
- Path distance m: `0.0`
- Time s: `0.0`
- Legs: `0`
