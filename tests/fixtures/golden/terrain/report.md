# Estimator Report

- Status: `success`
- Envelope schema: `estimator-envelope.v5`
- Tool version: `0.22.0`

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
- Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 adds turn-arc geometry, sub-segment sampling, and tangent-point offset subtraction (turn_radius_m * tan(|Δθ|/2)) from adjacent transit leg path_distance_m values so total path distance reflects the true Dubins-path length.
- Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.
- Takeoff and landing-transit legs report path_distance_m equal to vertical_distance_m; for purely vertical movement this is the 3D slant path distance.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Explicit resource systems are evaluated after route expansion; when configured, they determine resource feasibility while result.energy remains the legacy battery-only energy view.
- Communication-link feasibility is deterministic and uses configured static availability and range constraints only; live network calls are not performed.
- Static geofence feasibility uses 2D lon/lat route-segment geometry.
- Static landing-zone reachability uses straight-line geodesic distance and deterministic cruise-power divert energy.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use geodesic-aware Dubins path distance (bank-angle-constrained arc + straight sampled to target geometry boundary points) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. TAS-based transit time is used without wind correction or geofence intersection on the divert leg.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `b8bb0971a34817a6a6048a41300f15c3a0e9cce2baed2705855c8fd1d9cebe14`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`
- terrain: `yaml` sha256 `69c0c7349f2d821bb69c116ad41f03f40e4d9c9d31ac2c3455a08e9d811e00c8`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.0645449`
- Vertical distance m: `236.0`
- Path distance m: `785.0645449`
- Time s: `168.15360851`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.1025344`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.8974656`
- Reserve at landing percent: `95.43305173`
- Energy legs: `5`
