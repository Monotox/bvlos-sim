# Estimator Report

- Status: `success`
- Envelope schema: `estimator-envelope.v5`
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
- Divert route estimates use Dubins path distance (bank-angle-constrained arc + straight) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. TAS-based transit time is used without wind correction or geofence intersection on the divert leg. The Dubins distance uses a planar East-North approximation; a DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT warning is emitted when the geodesic divert distance exceeds 50 km.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `7bab3b2b9b996564f04f80c9cbb92051e2e187f2d4198b355e0939e9eec4473c`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.0645448997484`
- Vertical distance m: `240.0`
- Path distance m: `787.0645448997484`
- Time s: `169.82027517283754`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.50531217438247`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.4946878256176`
- Reserve at landing percent: `95.38829864729084`
- Energy legs: `5`
