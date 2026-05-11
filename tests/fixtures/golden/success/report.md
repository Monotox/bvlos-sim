# Estimator Report

- Status: `success`
- Envelope schema: `estimator-envelope.v4`
- Tool version: `0.2.0`

## Result Validity

- Complete: `true`
- Partial: `false`
- Valid for full mission: `true`
- Scope: `full_mission`

## Diagnostics

- `warning` `LOITER_ASSUMED_ZERO_GROUND_DISTANCE`: Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.

## Assumptions

- Estimator v1 is deterministic and uses no randomness.
- Wind input is constant in space and time unless a layered, time-varying, or spatiotemporal grid provider is used.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.
- Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 adds turn-arc geometry and sub-segment sampling.
- Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Static geofence feasibility uses 2D lon/lat route-segment geometry.
- Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `7bab3b2b9b996564f04f80c9cbb92051e2e187f2d4198b355e0939e9eec4473c`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.0645448969212`
- Vertical distance m: `240.0`
- Path distance m: `707.0645448969212`
- Time s: `169.820275172818`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.50531217438002`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.49468782562`
- Reserve at landing percent: `95.38829864729111`
- Energy legs: `5`
