# Estimator Report

- Status: `error`
- Envelope schema: `estimator-envelope.v10`
- Tool version: `0.0.0-test`

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

- `error` `UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN`: terrain altitude reference requires a terrain provider. Set assets.terrain_file in the mission or pass terrain_provider at runtime.

## Assumptions

- Estimator v1 is deterministic and uses no randomness.
- Wind input is constant in space and time unless a layered, time-varying, or spatiotemporal grid provider is used.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.
- Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 replaces feasible corners with connected circular fillets, trims adjacent transit legs to their tangent points, and samples wind along the materialized path. Corners that cannot fit the configured turn radius fail closed.
- Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.
- Takeoff and landing-transit legs report path_distance_m equal to vertical_distance_m; for purely vertical movement this is the 3D slant path distance.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Explicit resource systems are evaluated after route expansion; when configured, they determine resource feasibility while result.energy remains the legacy battery-only energy view. Onboard and hybrid resources include per-state RTH reserve demand; continuous external power replaces battery reserve gating but must cover RTH peak power.
- Communication-link feasibility is deterministic and uses configured static availability and range constraints only; live network calls are not performed.
- Static geofence feasibility uses the materialized 2D lon/lat flown path, including fidelity-v2 turn arcs; zones declaring floor_m/ceiling_m additionally constrain the leg's altitude band, treated as AMSL.
- Static landing-zone reachability uses geodesic-aware Dubins distance when entry heading and vehicle turn radius are known, otherwise straight-line geodesic distance; divert energy integrates the active wind provider through a per-segment wind-triangle ground speed and adds the terminal vertical energy to the landing-surface altitude.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.
- Minimum terrain clearance is evaluated on airborne legs only; vertical-takeoff and landing-transit legs touch the landing surface by definition and are exempt. Obstacle clearance is still evaluated on every leg, including those two.
- Energy feasibility is only as good as the vehicle's power coefficients. A vehicle declaring calibration_status placeholder_values, or declaring nothing, raises ENERGY_MODEL_UNCALIBRATED, which blocks the operational GO until the operator supplies a calibration profile or acknowledges the code.
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use geodesic-aware Dubins path distance (bank-angle-constrained arc + straight sampled to target geometry boundary points) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. When a wind provider is configured, a wind-triangle correction is applied to the divert ground speed; without a wind provider, TAS is used and a DIVERT_ENERGY_TAS_ONLY warning is emitted.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `4dd16a901d2117bf52366158806e473f8e843cee49e03f250013f939f5ea58c0`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `176.77`
- Vertical distance m: `120.00`
- Path distance m: `176.77`
- Time: `0m 40s (40.00 s)`
- Legs: `1`

## Leg Breakdown

| # | ID | Action | Dist m | Time s | Alt m | GS m/s | Wind m/s | Energy Wh |
|---|-----|--------|-------:|-------:|------:|-------:|---------:|----------:|
| 0 | wp1 | waypoint | 176.77 | 40.00 | 132.00 | 18.00 | 0.00 | — |
