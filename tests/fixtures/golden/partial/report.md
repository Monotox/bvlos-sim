# Estimator Report

- Status: `error`
- Envelope schema: `estimator-envelope.v4`
- Tool version: `0.2.0`

## Result Validity

- Complete: `false`
- Partial: `true`
- Valid for full mission: `false`
- Scope: `completed_legs_only`

### Invalidated Fields

- `result.total_horizontal_distance_m`
- `result.total_vertical_distance_m`
- `result.total_path_distance_m`
- `result.total_time_s`

## Diagnostics

- `error` `INVALID_MISSION_PROFILE`: loiter_time_s must be non-negative.

## Assumptions

- Estimator v1 is deterministic and uses no randomness.
- Wind input is constant in space and time unless a different provider is added.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.
- Turn dynamics and sub-segment integration are excluded from estimator v1.
- Fixed-wing circular loiter is unsupported in estimator v1.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Static geofence feasibility uses 2D lon/lat route-segment geometry.
- Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `5d6cab40974459fcdcde15d97cdb18d58382cf9a349de2421931654770ce36c0`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `176.76731936998286`
- Vertical distance m: `120.0`
- Path distance m: `176.76731936998286`
- Time s: `40.0`
- Legs: `1`
