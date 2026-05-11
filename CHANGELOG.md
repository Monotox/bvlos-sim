# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning once public releases begin.

## [Unreleased]

### Added

- Dubins path solver (`estimator.math.dubins`) for bank-angle-constrained 2D path planning; evaluates RS (right arc + straight) and LS (left arc + straight) path types with unconstrained exit heading.
- Divert route estimates now use Dubins path distance (bank-angle-constrained arc + straight) when entry heading and `vehicle.performance.turn_radius_m` are available, replacing the previous straight-line geodesic approximation. Falls back to straight-line when heading or turn radius is unavailable.

- Initial `v0.2.0` release.
- Deterministic estimator v1 with fidelity v1 and fidelity v2 modes.
- Deterministic energy feasibility with reserve-at-landing outputs.
- Static GeoJSON geofence conflict checks.
- Static GeoJSON landing-zone reachability checks.
- Scenario runner with deterministic events, assertions, and comms-link lost-link policy outcomes.
- Layered altitude-band wind provider.
- Optional sub-segment wind sampling for long transit legs.
- Turn-arc dynamics in fidelity v2.
- Fixed-wing circular loiter in fidelity v2.
- Full YAML configurability for mission estimation and scenario initial conditions.
- Terrain-referenced altitude execution using an offline uniform elevation grid (`assets.terrain_file`).
- Spatiotemporal wind grid with quadrilinear interpolation (`assets.wind_grid_file`).
- Integrated example combining terrain, wind-grid, geofences, landing zones, energy, and fidelity v2.
- Dynamic landing-zone availability via scenario `landing_zone_unavailable` events; zones can be marked unavailable from a trigger point onward with `ALL_LANDING_ZONES_UNAVAILABLE` failure diagnostics.
- `LandingZoneEstimate.unavailable_zone_ids` and `LandingZoneStateReachability.available_zone_count` output fields for availability tracing.
- `lz_unavailability` parameter on `estimate_mission_distance_time` and `try_estimate_mission_distance_time` for library callers.
- Computed divert route estimates on `CommsLinkPolicyOutcome.divert_estimate` when a `lost_link` event fires with a `divert` policy and landing zones are configured; estimate includes geodesic distance, TAS-based transit time, cruise-power energy, reserve after divert, and feasibility flag.
- `DivertRouteEstimate` model exported from `estimator` package root.
- `estimator/execution/divert.py` with `compute_divert_estimate` as the deterministic divert route computation function.
- Monte Carlo uncertainty analysis via new `sample` CLI command and `run_monte_carlo` Python API; configurable via `uncertainty.v1` YAML with seeded reproducibility and per-parameter distributions (`normal`, `uniform`) for wind, cruise speed, cruise power, and battery capacity.
- `uncertainty-report.v1` JSON envelope and Markdown rendering for uncertainty run outputs.
- `MonteCarloResult` and `SampledOutputStats` result models exported from `estimator` package root.
- `UncertaintyPlan`, `UncertaintyParameters`, `NormalDistribution`, `UniformDistribution` schemas exported from `schemas` package root.
- Resource-system feasibility abstractions on vehicle YAML via `resource_systems`, including onboard battery, external power, hybrid, and reserved future resource kinds.
- Communication-link feasibility abstractions on mission and scenario YAML via `link_systems`, including direct radio, mesh, cellular, satellite, Starlink-class, and hybrid link families.
- `result.resource` and `result.link` outputs in estimator and scenario reports, with structured diagnostics for resource and link infeasibility.
- Scenario assertions for `estimate.resource.is_feasible` and `estimate.link.is_feasible`.
- Integrated resource/link examples combining terrain, wind-grid, geofence, landing-zone, fidelity v2, scenario policies, and existing CLI paths.
