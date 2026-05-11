# Estimator Report

- Status: `error`
- Envelope schema: `estimator-envelope.v5`
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
- Wind input is constant in space and time unless a layered, time-varying, or spatiotemporal grid provider is used.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.
- Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 adds turn-arc geometry and sub-segment sampling.
- Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Explicit resource systems are evaluated after route expansion; when configured, they determine resource feasibility while result.energy remains the legacy battery-only energy view.
- Communication-link feasibility is deterministic and uses configured static availability and range constraints only; live network calls are not performed.
- Static geofence feasibility uses 2D lon/lat route-segment geometry.
- Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use Dubins path distance (bank-angle-constrained arc + straight) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. TAS-based transit time is used without wind correction or geofence intersection on the divert leg.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

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
