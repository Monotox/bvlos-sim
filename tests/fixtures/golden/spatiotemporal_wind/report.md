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
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use straight-line geodesic distance and TAS-based transit time without wind correction or geofence intersection on the divert leg.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `d5cf66b6a52da6e9106b51885d13735eafd5053e87a1e6e74869dbb2c0cca7da`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`
- wind_grid: `yaml` sha256 `10326e2f5c6d70305d94bbd79e38824ea5fd8db0ed0d2cd056c6ce60dc9fc216`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.0645448969212`
- Vertical distance m: `240.0`
- Path distance m: `707.0645448969212`
- Time s: `169.06024195158028`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.410308021725314`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.5896919782747`
- Reserve at landing percent: `95.39885466425274`
- Energy legs: `5`
