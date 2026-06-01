# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning once public releases begin.

## [Unreleased]

### Added

- Atomic output writes and clean cancellation (Ticket 104). Every `--output`
  write and every on-disk artifact writer (flight trace, phase segments,
  validation report, calibration profile, SITL artifacts) now writes to a sibling
  temp file, `fsync`s, and `os.replace`s it onto the target, so a killed or
  interrupted run never leaves a truncated file — the destination is either the
  prior content or absent. A new `CliExitCode.CANCELLED` (`14`) is returned when a
  run receives `SIGTERM`/`SIGINT`, installed by the console-script entrypoint, in
  place of the shell defaults (`143`/`130`). The cancellation contract is
  documented in `docs/CLI_EXIT_CODES.md` and `docs/VERSIONING_POLICY.md`.
- Calibration profiles and parameter fitting (Ticket 083). A new `bvlos-sim
  calibrate VEHICLE TRACE [TRACE ...]` command fits a narrow set of vehicle
  performance parameters from observed flights and emits a versioned,
  deterministic `calibration-profile.v1` artifact that *layers on* a base vehicle
  (it references `base_vehicle_id`, never replacing the profile). It fits
  `cruise_speed_mps` (mean transit-phase groundspeed), `climb_rate_mps` /
  `descent_rate_mps` (mean vertical rate over climbing/descending records), and
  `max_station_keep_wind_mps` (strongest wind held against in loiter dwell),
  reusing Ticket 081 segmentation as the phase bridge and touching no core
  estimator formula. Each fitted record carries the value, observed range, sample
  spread, sample count, applicable conditions, and provenance (source trace IDs,
  validation-report links, tool version); parameters with no samples are reported
  in `notes`, never fabricated. Calibrations are opt-in everywhere via
  `--calibration PATH` on `estimate`, `scenario`, and `validate`: the apply seam
  overrides only the fitted fields on a re-validated vehicle copy, leaves behaviour
  unchanged when absent, and rejects a `base_vehicle_id` mismatch as invalid input.
  Output is a Markdown report or the `calibration-profile.v1` envelope
  (`--format json`); the fit is deterministic. New public API:
  `adapters.calibration.fit_calibration_profile`, `apply_calibration`,
  `load_and_apply_calibration`, `write_calibration_profile`,
  `load_calibration_profile`, `CalibrationInput`, `CalibrationMismatchError`. New
  schemas exported from `schemas`: `CalibrationProfile`, `CalibratedParameter`,
  `CalibratedParameterName`, `CalibrationProvenance`,
  `CALIBRATION_PROFILE_SCHEMA_VERSION`. Adds a worked example under
  `examples/calibration/`. Energy-coefficient fitting and online auto-tuning remain
  out of scope.

- Version bump and release tooling (Ticket 098). A new `bvlos-sim bump
  <major|minor|patch>` command performs a release-ready version bump atomically:
  it updates `pyproject.toml` and rolls `CHANGELOG.md` (renaming `[Unreleased]`
  to the dated release section and opening a fresh `[Unreleased]`), then prints
  the suggested `git tag`/`push` follow-ups without ever tagging, pushing, or
  publishing. `--dry-run` previews the edits without writing; `--check` (for CI)
  fails when `pyproject.toml` is behind the latest git tag, preventing the
  version drift seen before v0.32.0. Golden fixtures are now version-agnostic:
  `tool_version()` honours a `BVLOS_SIM_TOOL_VERSION` override that `conftest.py`
  pins to `0.0.0-test`, so a version bump no longer churns the 16 golden fixtures
  and a release can no longer break the golden suite. New module
  `adapters.release` exposes the reusable semver/changelog/consistency helpers.

- Predicted-vs-observed validation metrics (Ticket 082). The new `bvlos-sim
  validate MISSION VEHICLE TRACE` command compares a deterministic mission
  estimate against an observed flight trace (`flight-trace.v1` from flight-log
  ingestion). It segments the trace into flight phases and lines predicted legs
  up with observed segments on their shared estimator leg-phase, then reports
  predicted-vs-observed time, horizontal distance (WGS-84 geodesic), mean
  groundspeed, and reserve at landing — at mission and per-phase level, each with
  absolute and percent error. Observed phases with no estimator counterpart and
  missing observed fields are reported in `notes`, never silently dropped. Output
  is a Markdown report or the versioned `validation-report.v1` envelope
  (`--format json`); the comparison is deterministic. New public API:
  `adapters.validation.build_validation_report`, `write_validation_report`,
  `load_validation_report`. New schemas exported from `schemas`: `ValidationReport`,
  `MissionValidationMetrics`, `PhaseValidation`, `MetricComparison`,
  `VALIDATION_REPORT_SCHEMA_VERSION`. Adds an example flight log and ingested trace
  under `examples/flight_logs/`. No changes to existing estimate, scenario, SITL,
  or SORA surfaces.

- Flight phase segmentation (Ticket 081). A `NormalizedFlightTrace` can now be
  deterministically segmented into contiguous `PhaseSegment` blocks using a
  mode-first algorithm: ArduPilot flight mode strings (TAKEOFF, RTL, LAND, LOITER,
  etc.) are mapped directly to `TracePhase` values; records in AUTO/GUIDED mode or
  without mode data fall back to kinematic rules derived from vertical rate and
  groundspeed. A single-record smoothing pass absorbs sensor-noise blips. Each segment
  carries the nearest estimator `LegPhase` string where a mapping exists (takeoff →
  `vertical_takeoff`, transit → `transit`, loiter → `loiter_dwell`, landing →
  `landing_transit`, rtl → `rtl_transit`). Climb, descent, divert, and unknown have no
  estimator counterpart and report `estimator_leg_phase: null`. Segmentation metadata
  records the algorithm identifier, which trace fields were available, and how many
  records could not be classified. Public API:
  `adapters.phase_segmentation.segment_trace`, `write_phase_segments`,
  `load_phase_segments`. Kinematic thresholds
  (`CLIMB_VERT_RATE_MPS`, `LOITER_SPEED_MPS`, `TRANSIT_SPEED_MPS`) are exported for
  downstream calibration use. New schemas exported from `schemas` package root:
  `TracePhase`, `PhaseSegment`, `PhaseSegmentResult`, `SegmentationMetadata`,
  `PHASE_SEGMENT_SCHEMA_VERSION`. No changes to existing estimate, scenario, or SITL
  surfaces.

- Flight log ingestion and trace normalization (Ticket 080). ArduPilot DataFlash text
  (`.log`) files can now be ingested into a versioned `NormalizedFlightTrace` artifact
  (`flight-trace.v1`). The adapter extracts GPS position, groundspeed, ground course,
  battery voltage/current/remaining, flight mode, and EKF wind estimate (NKF6/XKF6),
  merges auxiliary channels into GPS records by carry-forward timestamp, and records
  parsing assumptions and missing fields in a `FlightTraceProvenance` block. Traces can
  optionally reference a paired mission and vehicle YAML via `FlightTraceMissionRef`.
  Public API: `adapters.flight_log.ingest_dataflash_log`, `write_flight_trace`,
  `load_flight_trace`. New schemas exported from `schemas` package root:
  `NormalizedFlightTrace`, `FlightTraceRecord`, `FlightTraceProvenance`,
  `FlightTraceMissionRef`, `FLIGHT_TRACE_SCHEMA_VERSION`. No changes to existing
  estimate, scenario, or SITL surfaces.

- SORA mitigation depth: the `sora` command now applies operator-declared ground-risk mitigations (M1 strategic, M2 impact reduction, M3 ERP) and a tactical air-risk mitigation, declared in an optional `sora` block on the mission. The assessment reports the full credit ladder (iGRC → credits → final GRC), the residual ARC, and both the intrinsic and mitigated SAIL. Mitigation/credit tables are versioned data keyed by SORA revision; an unrecognised version is reported with a `MITIGATION_VERSION_UNSUPPORTED` advisory and no credits are applied. With no `sora` block the result is unchanged. The output remains a pre-assessment aid, not a certified determination.

- Opt-in return-to-home reserve gate via `constraints.require_rth_reserve`, returning `RTH_RESERVE_BELOW_THRESHOLD` and a checklist `NO-GO` when a route leg cannot preserve reserve after RTH.

- Altitude-aware geofence bounds via GeoJSON `floor_m` and `ceiling_m` properties. Forbidden zones now require both horizontal intersection and altitude-band overlap, while required zones must contain the full leg altitude band.

## [0.32.0] - 2026-05-29

### Changed

- Moved SITL adapter modules into `adapters/sitl/` subpackage. Module paths
  changed: `adapters.ardupilot_sitl` → `adapters.sitl.ardupilot`,
  `adapters.sitl_evidence` → `adapters.sitl.evidence`,
  `adapters.sitl_comparison` → `adapters.sitl.comparison`, and so on for all
  18 SITL-related files. The public schema contracts and CLI behaviour are
  unchanged.

### Added

- Dubins path solver (`estimator.math.dubins`) for bank-angle-constrained 2D path planning; evaluates RS (right arc + straight) and LS (left arc + straight) path types with unconstrained exit heading.
- Divert route estimates now use Dubins path distance (bank-angle-constrained arc + straight) when entry heading and `vehicle.performance.turn_radius_m` are available, replacing the previous straight-line geodesic approximation. Falls back to straight-line when heading or turn radius is unavailable.
- Fidelity v2 now subtracts the tangent-point offset (`turn_radius_m * tan(|Δθ|/2)`) from `path_distance_m` of both transit legs adjacent to each TURN_ARC, so total path distance reflects the true Dubins-path length through waypoints.
- Takeoff and landing-transit legs now report `path_distance_m` equal to `vertical_distance_m` (3D slant path distance for purely vertical legs), replacing the previous value of zero.
- `DivertRouteEstimate.warnings` field added; `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` is emitted when the geodesic distance to the target zone exceeds 50 km and the planar East-North approximation may accumulate meaningful error.

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
- `sitl-evidence.v1` evidence bundle schema for SITL adapter runs, including input artifacts, expected deterministic outputs, simulator metadata, and observed telemetry/command-log artifact references.
- Contract-only `sitl` CLI command that builds a no-op SITL evidence bundle from existing scenario YAML without launching a live simulator.
- ArduPilot SITL artifact recorder for telemetry, command logs, simulator events, and adapter events, with completed `sitl-evidence.v1` bundles when observed artifacts are present.
