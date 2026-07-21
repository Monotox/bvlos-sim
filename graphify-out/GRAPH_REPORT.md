# Graph Report - bvlos-sim  (2026-07-21)

## Corpus Check
- 454 files · ~293,328 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 5679 nodes · 19188 edges · 217 communities (206 shown, 11 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1669 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eea79b95`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- cli.py
- make_vehicle
- __init__.py
- test_sora_mitigations.py
- sora_envelope.py
- test_geojson_export.py
- test_qgc_convert.py
- InputDocument
- FailureCode
- InputLoadError
- run_scenario
- LegEstimate
- ingest_dataflash_log
- run_monte_carlo
- test_batch.py
- MissionEstimate
- __init__.py
- test_bump_version.py
- test_schemas.py
- test_scenario_envelope.py
- solve_wind_triangle
- test_dubins.py
- test_ardupilot_sitl.py
- test_checklist_markdown.py
- evidence.py
- SitlEvidenceBundle
- MissionPlan
- Pipeline Scenario Variant Family
- try_estimate_mission_distance_time
- test_tracking_controller.py
- test_scenario_schemas.py
- geofence.py
- test_propagation_units.py
- cli_support.py
- wind_grid.py
- battery_sizer.py
- summary.py
- test_sitl_live.py
- Pipeline Failed v1 Scenario
- segment_trace
- test_estimator_fidelity_v2.py
- ardupilot.py
- uncertainty_envelope.py
- make_mission_payload
- test_calibration.py
- validator.py
- sensitivity.py
- obstacle.py
- test_contract_golden.py
- size_battery.py
- test_sitl_comparison.py
- test_sitl_artifacts.py
- isa_air_density_kgm3
- ScenarioResultEnvelope
- test_preflight_validation.py
- Graphify
- test_divert_routing.py
- atomic_write_text
- fitter.py
- test_yaml_config_features.py
- test_summary_format.py
- LandingZone
- VehicleProfile
- ScenarioAssertionResult
- cli_batch_audit.py
- LayeredWindProvider
- test_sitl_evidence.py
- test_validation_metrics.py
- run_stochastic_propagation
- AltitudeReference
- _SitlComparisonMarkdownRenderer
- EnergyEstimate
- geofence_geojson.py
- StochasticResultEnvelope
- propagator_ekf.py
- test_uncertainty_cli.py
- test_scenario_cli.py
- fetch_wind.py
- test_stochastic_cli.py
- timeline.py
- fetch_geofences.py
- sora.py
- FlightTraceRecord
- ArduPilotSitlAdapter
- test_terrain_altitude.py
- test_qgc_export.py
- Estimator Field Semantics
- test_weather_limits.py
- test_profile_markdown.py
- Usage Guide
- checklist_markdown.py
- Community Vehicle Profiles
- scenario.py
- BVLOS Mission Simulator Brief
- Versioning Policy
- Calibration Profiles and Parameter Fitting
- test_dynamic_landing_zone.py
- _SitlPositionProximityComparator
- _write_obstacle_inputs
- test_ground_risk.py
- Pipeline Demo Stochastic EKF Plan
- ProvenanceInput
- AirRiskClass
- SITL Adapter Contract
- SensorProfile
- Project Changelog
- Ticket 047: Stochastic State Propagation
- test_sora_cli.py
- sora.py
- fetch_obstacles.py
- Ticket 043: SITL Scenario Comparison Report
- Deterministic Sensitivity Sweep
- SORA Intrinsic Ground Risk Class
- ScenarioPlan
- SITL Adapter Contract and Evidence Schema
- 80 m Multirotor Demo Route
- Deterministic Divert Route Construction
- Ticket 056: Community Vehicle Profiles
- Ticket 107: Machine-Readable Preflight Validation
- Canonical Result Envelope
- geofence-geojson.v1 Output
- Alpine Infeasible 001 Mission
- Example Missions Catalog
- tool_version
- progress_reporter
- Deterministic Energy Feasibility
- Resource and Link Feasibility Abstractions
- Batch Scenario and Batch Propagate Modes
- Ticket Backlog
- Pipeline Demo Infeasible Mission
- _SitlComparisonValueCoercer
- CLI Exit Code Contract
- Ticket 044: Geodesic Dubins Divert Path
- Ticket 058: NOTAM and Live Airspace Integration
- Physically Aware Energy Model
- 120 m VTOL Demo Route
- fetch_population.py
- Fidelity v2 Layered Wind and Subsegment Sampling
- Shared CLI, API, and UI Core Path
- Scenario Route Export Builder
- Hardware-in-the-Loop Validation
- Pipeline Demo 001 Ground-Risk Mission
- divert.py
- Operational Integration Seams
- Route Altitude Profile Report
- Binary Flight-Log Ingestion
- Backend-Facing CLI Exit-Code Contract
- Pipeline Demo 001 Mission
- Pipeline Spatiotemporal Wind Grid
- Partial Estimator Golden Report
- Lost Link Policy Evaluator
- SITL Evidence v1 Bundle
- Per-Leg RTH Reserve Timeline
- Demo batch.v1 Manifest
- Pipeline Demo 001 EKF Mission
- Graphify Repository Guidance
- test_time_varying_geofence.py
- Terrain Referenced Altitude Execution
- Preflight CLI Command
- Versioned Migration Registry
- QGroundControl Mission Export
- Weather Minimums GO/NO-GO Gate
- Time-Varying Geofence Activation
- Version Bump Command
- Three-Dimensional Obstacle Clearance Check
- Input and Output Contract-Version Map
- Prioritized Resource Systems
- QuadPlane v1 EKF and Tracking Profile
- test_link_failure_has_full_mission_result_validity
- Bug Report Template
- Feature Request Template
- Code of Conduct
- Dropped Sample Count
- Explicit Vehicle Profile Selection
- Behavior-Preserving Propagator Module Split
- MkDocs Material GitHub Pages Site
- BVLOS Simulator Documentation Site
- launch.sh
- __init__.py
- Atomic Output Write
- One-Metre Aircraft Characteristic Dimension
- Partial Fixture Vehicle Profile
- Population Density Grid
- bvlos-sim
- Q: One production regression remains: explicit feasible external power may replace base battery/RTH feasibility, while onboard/hybrid resources must still account for RTH reserve.
- Contributing Guide
- ulog.py
- geojson_export.py
- Ticket 054: Reference Inputs for Calibration and Import
- test_terrain_altitude.py
- test_migrations.py
- kml_export.py
- Q: now write project and find gaps, issues, bad math, bad science or anything that will prevent a real team from using it
- test_sora_cli.py
- enums.py
- test_time_varying_geofence.py
- __init__.py
- test_sail.py
- migrate.py
- fetch_population.py
- Project Knowledge Graph
- test_exit_codes_contract.py
- _write_ground_risk_inputs
- _PlanItemBuilder
- fetch_terrain.py
- fetch_all.py
- SKILL.md
- FakeMav
- Q: Review the current uncommitted root-owned integration changes for correctness, security, contract, and test gaps
- RTK - Rust Token Killer (Codex CLI)
- test_checklist_shows_departure_time_when_set
- test_numeric_input_safety.py
- _write_obstacle_inputs
- test_link_failure_has_full_mission_result_validity
- .fail

## God Nodes (most connected - your core abstractions)
1. `make_vehicle()` - 361 edges
2. `make_mission()` - 323 edges
3. `InputDocument` - 190 edges
4. `MissionEstimate` - 187 edges
5. `estimate_mission_distance_time()` - 177 edges
6. `LegEstimate` - 163 edges
7. `try_estimate_mission_distance_time()` - 143 edges
8. `FailureCode` - 138 edges
9. `VehicleProfile` - 133 edges
10. `EstimationContext` - 120 edges

## Surprising Connections (you probably didn't know these)
- `Machine-Readable Run Progress` --semantically_similar_to--> `Run Progress JSONL`  [INFERRED] [semantically similar]
  CHANGELOG.md → docs/USAGE.md
- `Return-to-Home Reserve Gate` --semantically_similar_to--> `Return-to-Home Reserve Checks`  [INFERRED] [semantically similar]
  CHANGELOG.md → docs/USAGE.md
- `test_load_terrain_grid_from_yaml()` --calls--> `load_terrain_grid()`  [INFERRED]
  tests/test_terrain_altitude.py → adapters/assets/terrain_grid.py
- `_EstimatedPositionState` --uses--> `SensorProfile`  [INFERRED]
  estimator/execution/propagator_ekf.py → schemas/vehicle_sensors.py
- `Python 3.12 and 3.13 Matrix` --conceptually_related_to--> `BVLOS Simulator`  [INFERRED]
  .github/workflows/ci.yml → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Codex Graphify Build Pipeline** — _codex_skills_graphify_skill_graphify, _codex_skills_graphify_skill_structural_extraction, _codex_skills_graphify_skill_semantic_extraction, _codex_skills_graphify_skill_community_detection, _codex_skills_graphify_skill_graph_health_diagnostics [EXTRACTED 1.00]
- **Release Quality and Contract Governance** — _github_pull_request_template_contract_impact_review, _github_workflows_ci_release_quality_gates, contributing_public_contract_changes, docs_versioning_policy_compatibility_rules, docs_versioning_policy_golden_fixtures [EXTRACTED 1.00]
- **Flight Log Validation and Calibration Flow** — changelog_flight_log_ingestion, changelog_phase_segmentation, docs_usage_flight_validation_workflow, docs_usage_calibration_workflow [INFERRED 0.95]
- **Flight-Team Evidence Pipeline** — docs_usage_mission_estimation, docs_usage_scenario_execution, docs_usage_monte_carlo_sampling, docs_usage_live_sitl_evidence, docs_sitl_adapter_contract_sitl_comparison_report [EXTRACTED 1.00]
- **Deterministic Feasibility Stack** — docs_tickets_010_deterministic_energy_feasibility_deterministic_energy_feasibility, docs_tickets_011_static_geofence_feasibility_static_geofence_feasibility, docs_tickets_012_static_landing_zone_reachability_static_landing_zone_reachability, docs_tickets_034_resource_and_link_feasibility_abstractions_resource_and_link_feasibility_abstractions [INFERRED 0.85]
- **Fidelity v2 Path Model Evolution** — docs_tickets_031_fidelity_v2_turns_and_fixed_wing_loiter_turn_arc_dynamics, docs_tickets_038_bank_angle_and_dubins_path_optimization_dubins_path_solver, docs_tickets_039_path_planning_model_gaps_tangent_point_offset_correction [EXTRACTED 1.00]
- **SITL Evidence Delivery Chain** — docs_tickets_040_sitl_adapter_contract_and_evidence_schema_sitl_adapter_contract_and_evidence_schema, docs_tickets_041_ardupilot_sitl_launch_and_mission_upload_ardupilot_sitl_launch_and_mission_upload, docs_tickets_042_sitl_telemetry_recorder_and_evidence_bundle_sitl_telemetry_recorder_and_evidence_bundle [EXTRACTED 1.00]
- **PX4 SITL Evidence and Comparison Flow** — docs_tickets_045_px4_sitl_launch_and_mission_upload_px4_sitl_adapter_lifecycle, docs_tickets_045_px4_sitl_launch_and_mission_upload_px4_mission_upload, docs_tickets_046_px4_sitl_telemetry_recorder_and_evidence_bundle_px4_telemetry_capture, docs_tickets_046_px4_sitl_telemetry_recorder_and_evidence_bundle_observed_evidence_bundle, docs_tickets_043_sitl_scenario_comparison_report_sitl_comparison_v1 [EXTRACTED 1.00]
- **Stochastic Closed-Loop Pipeline** — docs_tickets_047_stochastic_state_propagation_time_stepped_propagator, docs_tickets_048_observation_model_and_twin_state_twin_state_architecture, docs_tickets_048_observation_model_and_twin_state_ekf_update, docs_tickets_049_stochastic_closed_loop_control_tracking_controller, docs_tickets_049_stochastic_closed_loop_control_path_energy_feedback [EXTRACTED 1.00]
- **Real-World Airspace Asset Pipeline** — docs_tickets_052_real_world_data_fetch_scripts_mission_compatible_assets, docs_tickets_053_airspace_geofence_fetch_script_openaip_airspace_source, docs_tickets_053_airspace_geofence_fetch_script_geofence_geojson_output, docs_tickets_058_notam_live_airspace_integration_active_restriction_fetch, docs_tickets_058_notam_live_airspace_integration_static_dynamic_geofence_merge [INFERRED 0.95]
- **Real Flight Validation and Calibration Chain** — docs_tickets_080_flight_log_ingestion_and_trace_normalization_flight_log_ingestion_and_trace_normalization, docs_tickets_081_flight_phase_segmentation_flight_phase_segmentation, docs_tickets_082_predicted_vs_observed_validation_metrics_predicted_vs_observed_validation_metrics, docs_tickets_083_calibration_profile_data_and_fitting_calibration_profiles_and_parameter_fitting, docs_tickets_084_holdout_validation_reports_holdout_validation_reports [EXTRACTED 1.00]
- **Preflight Operator Readiness Decision** — docs_tickets_089_preflight_report_command_preflight_command, docs_tickets_089_preflight_report_command_preflight_report_v1, docs_tickets_089_preflight_report_command_go_no_go_composition, docs_tickets_089_preflight_report_command_preflight_validation_v1 [EXTRACTED 1.00]
- **SORA Pre-Assessment Risk Pipeline** — docs_tickets_094_sora_ground_risk_class_sora_intrinsic_ground_risk_class, docs_tickets_095_sora_air_risk_and_sail_sora_air_risk_class, docs_tickets_095_sora_air_risk_and_sail_sail_determination, docs_tickets_101_sora_mitigation_depth_sora_mitigation_ladder, docs_tickets_101_sora_mitigation_depth_intrinsic_and_mitigated_sail [EXTRACTED 1.00]
- **Backend-Safe CLI Artifact Contract** — docs_tickets_103_backend_cli_exit_code_contract_cli_exit_code_contract, docs_tickets_104_atomic_output_writes_and_cancellation_atomic_output_write, docs_tickets_104_atomic_output_writes_and_cancellation_cancellation_exit_code, docs_tickets_105_contract_version_discovery_command_schema_versions_command [INFERRED 0.85]
- **Long-Running Command Progress Contract** — docs_tickets_106_machine_readable_run_progress_progress_reporter, docs_tickets_106_machine_readable_run_progress_progress_reporter_context, docs_tickets_106_machine_readable_run_progress_progress_callback_contract, docs_tickets_106_machine_readable_run_progress_side_channel_invariance, examples_batch_readme_batch_quick_start [EXTRACTED 1.00]
- **Pipeline Mission Variant Family** — examples_missions_pipeline_demo_001_pipeline_demo_001, examples_missions_pipeline_demo_001_ekf_pipeline_demo_001_ekf, examples_missions_pipeline_demo_001_ground_risk_pipeline_demo_001_ground_risk, examples_missions_pipeline_demo_001_integrated_pipeline_demo_001_integrated, examples_missions_pipeline_demo_001_resource_link_pipeline_demo_001_resource_link [EXTRACTED 1.00]
- **Alpine Failure Batch Evidence** — examples_batch_demo_batch_alpine_infeasible_run, examples_real_world_readme_failing_mission_walkthrough, examples_real_world_alpine_infeasible_alpine_infeasible_001, examples_real_world_alpine_infeasible_reserve_below_threshold_outcome [EXTRACTED 1.00]
- **Alpine Offline Environment Stack** — examples_real_world_alpine_mission_alpine_demo_001, examples_real_world_assets_terrain_alpine_terrain_grid, examples_real_world_assets_wind_grid_alpine_wind_grid, examples_real_world_quadplane_v1_quadplane_v1 [EXTRACTED 1.00]
- **Pipeline Scenario Variant Suite** — examples_scenarios_pipeline_demo_001_divert_routing_scenario_pipeline_demo_divert_routing, examples_scenarios_pipeline_demo_001_integrated_scenario_pipeline_demo_integrated, examples_scenarios_pipeline_demo_001_lz_availability_scenario_pipeline_demo_lz_availability, examples_scenarios_pipeline_demo_001_resource_link_scenario_pipeline_demo_resource_link, examples_scenarios_pipeline_demo_001_scenario_pipeline_demo_baseline, examples_scenarios_pipeline_demo_001_v2_scenario_pipeline_demo_fidelity_v2, examples_scenarios_pipeline_demo_001_waypoint_policy_scenario_waypoint_policy_demo [EXTRACTED 1.00]
- **Probabilistic Risk Example Family** — examples_stochastic_pipeline_demo_001_stochastic_pipeline_demo_stochastic, examples_stochastic_pipeline_demo_001_stochastic_ekf_pipeline_demo_stochastic_ekf, examples_uncertainty_pipeline_demo_001_speed_uncertainty_pipeline_demo_speed_uncertainty, examples_stochastic_readme_time_stepped_risk_model, examples_uncertainty_readme_monte_carlo_sampling [INFERRED 0.95]
- **Community Vehicle Profile Collection** — examples_vehicles_community_readme_community_vehicle_profiles, examples_vehicles_community_autel_evo_max_4t_autel_evo_max_4t, examples_vehicles_community_dji_matrice_300_rtk_dji_matrice_300_rtk, examples_vehicles_community_generic_survey_hexacopter_generic_survey_hexacopter, examples_vehicles_community_qs_trinity_f90_plus_qs_trinity_f90_plus, examples_vehicles_community_wingtra_one_gen2_wingtra_one_gen2 [EXTRACTED 1.00]
- **QuadPlane Resource Priority Chain** — examples_vehicles_quadplane_resource_link_quadplane_resource_link, examples_vehicles_quadplane_resource_link_prioritized_resource_systems, examples_vehicles_quadplane_resource_link_optical_fiber_external_power, examples_vehicles_quadplane_resource_link_onboard_battery_backup [EXTRACTED 1.00]
- **Partial Result Validity Contract** — tests_fixtures_golden_partial_mission_pipeline_demo_partial_mission, tests_fixtures_golden_partial_report_partial_estimator_report, tests_fixtures_golden_partial_report_unsupported_terrain_reference, tests_fixtures_golden_partial_report_completed_legs_only_scope [EXTRACTED 1.00]
- **QuadPlane v1 Golden Vehicle Profiles** — tests_fixtures_golden_partial_vehicle_partial_fixture_vehicle_profile, tests_fixtures_golden_spatiotemporal_wind_vehicle_spatiotemporal_fixture_quadplane_profile, tests_fixtures_golden_stochastic_vehicle_stochastic_fixture_quadplane_profile, tests_fixtures_golden_success_vehicle_success_fixture_quadplane_profile, tests_fixtures_golden_terrain_vehicle_terrain_fixture_quadplane_profile [INFERRED 0.95]

## Communities (217 total, 11 thin omitted)

### Community 0 - "cli.py"
Cohesion: 0.04
Nodes (122): BatchOutputFormat, StrEnum, BatterySizingOutputFormat, CliExitCode, _document_output_format(), DocumentOutputFormat, _exit_with_cli_error(), main() (+114 more)

### Community 1 - "make_vehicle"
Cohesion: 0.05
Nodes (99): estimate_mission_distance_time(), isa_air_density_kgm3(), Atmosphere helpers for closed-form energy scaling., Return ISA troposphere density in kg/m3 for a geometric altitude., MissionEstimation, Optional persisted estimator options.      These values are used by the estima, make_vehicle(), Tests for engine-level advisory warnings: max_wind, failsafe thresholds, and rou (+91 more)

### Community 2 - "__init__.py"
Cohesion: 0.08
Nodes (52): _datetime(), GeofenceRecurrence, StrEnum, GeofenceConflict, Route-vs-geofence conflict record., _check_failsafe_thresholds(), _check_max_wind(), _check_route_structure() (+44 more)

### Community 3 - "test_sora_mitigations.py"
Cohesion: 0.12
Nodes (24): apply_grc_mitigations(), Return intrinsic GRC, rejecting mitigation credit until criteria exist.      A r, supported_sora_versions(), GroundRiskFootprint, GroundRiskMitigation, GroundRiskMitigations, MitigationRobustness, A single declared SORA 2.5 ground-risk mitigation. (+16 more)

### Community 4 - "sora_envelope.py"
Cohesion: 0.20
Nodes (16): _arc_label(), _containment_lines(), _grc_line(), _mitigation_lines(), _oso_lines(), _party_dependency_label(), Markdown renderer for the SORA pre-assessment report., render_sora_markdown() (+8 more)

### Community 5 - "test_geojson_export.py"
Cohesion: 0.06
Nodes (84): build_geojson_export(), _energy_by_leg_index(), _energy_feasible(), _feature(), _geofence_feature(), _geofence_features(), _igrc_by_leg_index(), _landing_zone_feature() (+76 more)

### Community 6 - "test_qgc_convert.py"
Cohesion: 0.06
Nodes (57): ConvertDiagnostic, _integer(), load_and_convert_plan(), _make_diagnostic(), _mapping(), _MissionAssembler, _number(), parse_qgc_plan() (+49 more)

### Community 7 - "InputDocument"
Cohesion: 0.08
Nodes (79): _detect_geojson_format(), _entry_from_feature(), _feature_geometry(), _feature_properties(), geojson_entries_from_root(), GeoJsonEntry, GeoJsonGeometryType, GeoJsonLoadStage (+71 more)

### Community 8 - "FailureCode"
Cohesion: 0.04
Nodes (122): CapabilitySource, FailureKind, FidelityMode, LegPhase, OptionSource, StrEnum, Public estimator enums., Estimator fidelity level.      V1 is the original leg-to-leg geodesic model. (+114 more)

### Community 9 - "InputLoadError"
Cohesion: 0.07
Nodes (55): load_batch_manifest(), Path, Batch manifest loading for multi-run estimate workflows., Load and validate a batch.v1 manifest YAML or JSON file., _resolve_manifest_path(), _resolve_run_paths(), load_and_apply_calibration(), load_calibration_profile() (+47 more)

### Community 10 - "run_scenario"
Cohesion: 0.10
Nodes (76): Execute a deterministic scenario and return a structured result.      This funct, run_scenario(), make_mission(), test_scenario_link_systems_override_mission_link_systems(), _assertion(), _divert_assertion(), _lost_link_event(), _make_turning_mission() (+68 more)

### Community 11 - "LegEstimate"
Cohesion: 0.10
Nodes (58): EnergyLegEstimate, EstimatorFailure, LegEstimate, Internal flown-path polyline, intentionally absent from contracts., Internal transit timing, intentionally absent from contracts., Per-leg deterministic energy estimate., Per-phase estimate record.      A single mission route item may expand into mult, _active_emergency_wind_provider() (+50 more)

### Community 12 - "ingest_dataflash_log"
Cohesion: 0.14
Nodes (29): ingest_dataflash_log(), Ingest an ArduPilot DataFlash text log (.log) into a NormalizedFlightTrace., Write a normalized flight trace to a JSON file with canonical formatting., write_flight_trace(), _ingest(), Path, Tests for flight log ingestion and trace normalization (Ticket 080)., test_dataflash_ingest_all_records_without_fix_raises() (+21 more)

### Community 13 - "run_monte_carlo"
Cohesion: 0.06
Nodes (66): _build_sample_wind_provider(), Random, UncertaintyDistribution, Run a seeded diagnostic parameter sweep and return conditional results.      The, run_monte_carlo(), _sample(), _stats(), Reject distributions that can silently produce nonphysical values. (+58 more)

### Community 14 - "test_batch.py"
Cohesion: 0.06
Nodes (82): BatchRunResult, BatchSummary, format_flight_time(), format_reserve_margin(), Batch estimate execution support for CLI and tests., Run all estimates in a validated batch manifest., Summarize batch run statuses., Format a signed reserve margin for batch table output. (+74 more)

### Community 15 - "MissionEstimate"
Cohesion: 0.10
Nodes (41): compute_turn_arc_geometry(), Compute the arc length for a constant-radius turn between two tracks., make_fw_vehicle(), _make_turning_mission(), Tests for fidelity v2: turn-arc dynamics and fixed-wing circular loiter., Arc length must equal R · |Δθ| within floating-point tolerance., ground_track_deg on a TURN_ARC must match the next transit's ground_track_deg., Mission with a clear ~90° heading change: home→north, then east. (+33 more)

### Community 16 - "__init__.py"
Cohesion: 0.16
Nodes (13): _ArtifactRecords, _first_record_with(), _has_record_with(), _list_of_mappings(), _ArtifactRecord, Artifact-record loading for SITL comparison reports., Read already-written SITL artifact logs., _SitlArtifactLogReader (+5 more)

### Community 17 - "test_bump_version.py"
Cohesion: 0.07
Nodes (57): bump(), Version bump and release-consistency command., Bump the project version, rolling CHANGELOG.md, or check release consistency., _run_bump(), _run_check(), apply_bump(), bump_version(), BumpPart (+49 more)

### Community 18 - "test_schemas.py"
Cohesion: 0.05
Nodes (55): FailsafeProfile, BaseModel, Vehicle energy and failsafe schema models., Failsafe thresholds used for advisory warnings.      The estimator emits RESERVE, Battery usable-capacity fraction at a state of charge., UsableCapacityPoint, AirspeedModel, Airspeed sensor noise model.      Non-operative in the current EKF implementatio (+47 more)

### Community 19 - "test_scenario_envelope.py"
Cohesion: 0.12
Nodes (38): Render the envelope as canonical deterministic JSON., render_scenario_envelope_json(), _assertion_counts(), Render a scenario result envelope as a human-readable Markdown report., render_scenario_markdown(), _policy_outcome(), AssertionOutcome, ScenarioStatus (+30 more)

### Community 20 - "solve_wind_triangle"
Cohesion: 0.20
Nodes (15): Math and geometry helpers for estimator internals., normalize_deg(), normalize_signed(), Pure wind-triangle math utilities., Normalize signed angle to [-180, 180)., Solve wind-triangle for required heading and resulting groundspeed.      Returns, Normalize heading angle to [0, 360)., solve_wind_triangle() (+7 more)

### Community 21 - "test_dubins.py"
Cohesion: 0.08
Nodes (50): battery_capacity_recommendations(), BatteryCapacityRecommendation, BatterySizingResult, _capacity_is_feasible_or_raise(), _capacity_with_margin(), compute_minimum_battery_capacity(), _estimate_at_capacity(), _find_first_feasible_interval() (+42 more)

### Community 22 - "test_ardupilot_sitl.py"
Cohesion: 0.12
Nodes (42): _connected_adapter(), _document(), FakeConnection, FakeMavutil, FakeMessage, MissingHeartbeatConnection, Path, Tests for the ArduPilot SITL adapter. (+34 more)

### Community 23 - "test_checklist_markdown.py"
Cohesion: 0.10
Nodes (57): _departure_time_row(), _energy_row(), _fmt(), _geofence_row(), _ground_risk_row(), _landing_zone_row(), _link_row(), _obstacle_row() (+49 more)

### Community 24 - "evidence.py"
Cohesion: 0.08
Nodes (39): _document_reference(), _evidence_status(), _input_references(), Path, _resolve_bundle_references(), _resolved_reference(), _is_artifact_uri(), _artifact_row() (+31 more)

### Community 25 - "SitlEvidenceBundle"
Cohesion: 0.10
Nodes (24): Comparison dimension orchestration for SITL evidence bundles., Build ordered comparison items for a SITL evidence bundle., _SitlComparisonDimensionBuilder, _ArtifactRecord, Expected-output comparison dimensions for SITL reports., Build comparisons from deterministic expected outputs., _SitlExpectedComparisonBuilder, _PositionMatch (+16 more)

### Community 26 - "MissionPlan"
Cohesion: 0.06
Nodes (45): Core geofence domain models.  These models intentionally use lat/lon domain co, Core landing-zone domain models., Public estimator options., Protocol, Shared core spatial validation helpers., Coordinate shape required for closed-ring validation., RingCoordinate, validate_closed_ring() (+37 more)

### Community 27 - "Pipeline Scenario Variant Family"
Cohesion: 0.05
Nodes (52): Alpine Demo 001 Mission, 25% Reserve, 15 m/s Wind, and 8 km Landing-Zone Constraints, Terrain, Wind, Landing-Zone, and Geofence Asset Stack, Lucerne-Zug VTOL Ridge and Valley Route, Alpine SRTM Terrain Grid, Mountain Elevation Surface, 46.9–47.2°N by 8.15–8.45°E Grid, Alpine Spatiotemporal Wind Grid (+44 more)

### Community 28 - "try_estimate_mission_distance_time"
Cohesion: 0.06
Nodes (77): ListObstacleProvider, In-memory obstacle provider backed by an immutable obstacle list., Run the estimator and return a result without raising on infeasibility.      U, try_estimate_mission_distance_time(), _point_zone(), Tests for dynamic landing-zone availability (Ticket 035)., Regression: apply_lz_unavailability must pass the converged wind provider., _scenario() (+69 more)

### Community 29 - "test_tracking_controller.py"
Cohesion: 0.12
Nodes (21): GeofenceZone, A named static geofence zone., Protocol, Return wind vector at a spatiotemporal point., WindProvider, ParticlePopulation, apply_mission_overrides(), apply_vehicle_overrides() (+13 more)

### Community 30 - "test_scenario_schemas.py"
Cohesion: 0.08
Nodes (41): _make_assertion(), _make_event(), _make_scenario_payload(), Tests for scenario.v1 schema validation., test_assertion_extra_fields_rejected(), test_assertion_id_with_spaces_rejected(), test_at_elapsed_time_negative_rejected(), test_at_elapsed_time_with_trigger_elapsed_time_s_accepted() (+33 more)

### Community 31 - "geofence.py"
Cohesion: 0.17
Nodes (37): apply_calibration(), Return a copy of ``vehicle`` with calibrated performance fields overridden., CalibrationInput, One observed flight: a normalized trace and its phase segmentation., Write a calibration profile to a JSON file with canonical formatting., write_calibration_profile(), _calibrated_param(), _calibration() (+29 more)

### Community 32 - "test_propagation_units.py"
Cohesion: 0.06
Nodes (64): _clamp_unit(), _energy_by_leg_index(), EnergyDrainCurve, EnergyLegDrain, _interpolate_leg_position(), _interpolated_energy(), PositionInterpolator, Energy drain curves and position interpolation along a mission route. (+56 more)

### Community 33 - "cli_support.py"
Cohesion: 0.08
Nodes (60): checklist_is_go(), Return the fail-closed operational verdict rendered by the checklist., _build_estimation_options(), _empty_failed_result(), _envelope_inputs_for_static_asset_error(), _envelope_output_format(), _geojson_asset_input_name(), _input_error_for_geojson_asset_error() (+52 more)

### Community 34 - "wind_grid.py"
Cohesion: 0.10
Nodes (37): Static asset loading adapters., _build_provider(), load_terrain_grid(), Any, Path, YAML/JSON uniform elevation grid terrain adapter., Raised when an elevation grid file cannot be loaded., Load a GridTerrainProvider from a YAML or JSON elevation grid file. (+29 more)

### Community 35 - "battery_sizer.py"
Cohesion: 0.13
Nodes (32): _baseline_line(), _EastWindOverlayProvider, _estimate_level(), _fmt(), _level_from_result(), _overall_status(), _percent_label(), Energy reserve sensitivity sweep and Markdown rendering. (+24 more)

### Community 36 - "summary.py"
Cohesion: 0.14
Nodes (44): _render_uncertainty_summary(), format_scenario_summary(), format_stochastic_summary(), format_uncertainty_summary(), _join_fields(), _policy_action_field(), Format a diagnostic sampled-parameter result as a single summary line., Format a diagnostic stochastic result as a single summary line. (+36 more)

### Community 37 - "test_sitl_live.py"
Cohesion: 0.07
Nodes (56): build_scenario_envelope(), Build the canonical scenario result envelope from a completed run., ArduPilotSitlConfig, MissionConstraints, MissionDefaults, PlannedHome, BaseModel, Home position used when no vehicle is connected.      This mirrors the plannin (+48 more)

### Community 38 - "Pipeline Failed v1 Scenario"
Cohesion: 0.05
Nodes (45): Failed Golden Scenario Report, Failed Time Assertion Evidence, Lost Link RTL Outcome, Scenario Report v2, Lost Link RTL Policy, Pipeline Failed v1 Scenario, Time Too Short Assertion, Unsupported Boolean Comparison (+37 more)

### Community 39 - "segment_trace"
Cohesion: 0.12
Nodes (45): Flight phase segmentation adapters., load_phase_segments(), Path, File I/O helpers for phase segment result artifacts., Write a phase segment result to a JSON file with canonical formatting., Load a phase segment result, returning the model and its InputDocument.      Rai, write_phase_segments(), Segment a normalized flight trace into contiguous flight phases.      Phase assi (+37 more)

### Community 40 - "test_estimator_fidelity_v2.py"
Cohesion: 0.07
Nodes (59): ingest_dataflash_binary(), _ingest_dataflash_binary_bytes(), _iter_dataflash_messages(), _normalise_row(), Any, Path, _RawRow, _python_scalar() (+51 more)

### Community 41 - "ardupilot.py"
Cohesion: 0.08
Nodes (45): _connection_metadata(), _connection_target_component(), _connection_target_system(), _execution_mode(), arm_command(), auto_mode_flag(), _connection_mode_mapping(), _connection_set_mode() (+37 more)

### Community 42 - "uncertainty_envelope.py"
Cohesion: 0.19
Nodes (16): _fmt(), Markdown rendering for Monte Carlo uncertainty reports., render_uncertainty_markdown(), _stats_row(), MonteCarloResult, BaseModel, Aggregated results from a seeded diagnostic parameter sweep.      The baseline e, _det_meta() (+8 more)

### Community 43 - "make_mission_payload"
Cohesion: 0.18
Nodes (40): make_mission_payload(), make_vehicle_payload(), Path, --max-segment-length-m alone must not downgrade mission estimation.fidelity., test_cli_combines_fidelity_wind_layer_and_max_segment_length(), test_cli_energy_infeasible_result_has_complete_result_validity(), test_cli_explicit_fidelity_v1_overrides_mission_yaml_v2(), test_cli_fidelity_v1_default_unchanged() (+32 more)

### Community 44 - "test_calibration.py"
Cohesion: 0.30
Nodes (22): AssertionFieldValue, Result of evaluating a single scenario assertion., ScenarioAssertionResult, determine_scenario_status(), evaluate_assertion(), _evaluate_eq_assertion(), _evaluate_estimate_fails(), _evaluate_estimate_succeeds() (+14 more)

### Community 45 - "validator.py"
Cohesion: 0.09
Nodes (35): _metric_row(), _num(), _pct(), Predicted-vs-observed validation Markdown report renderer., Render a validation report as a Markdown document., render_validation_markdown(), _mean(), _mission_metrics() (+27 more)

### Community 46 - "sensitivity.py"
Cohesion: 0.21
Nodes (8): _emit_interval(), progress_reporter(), ProgressReporter, Path, Machine-readable run progress for long commands (Ticket 106).  A small, dependen, Emits JSONL progress records to a sink at a fixed completed-count interval., Yield a ProgressReporter when progress is enabled, else ``None``.      Progress, TextIO

### Community 47 - "obstacle.py"
Cohesion: 0.16
Nodes (24): Obstacle, ObstacleClearanceViolation, A route sample that violates obstacle or terrain clearance., _compile_obstacle(), CompiledObstacle, _continuous_obstacle_violations(), _continuous_terrain_checks(), evaluate_obstacle_clearance() (+16 more)

### Community 48 - "test_contract_golden.py"
Cohesion: 0.08
Nodes (60): canonical_float(), canonical_json_value(), format_canonical_float(), JsonValue, Return a JSON-compatible value with stable float precision., Round insignificant platform-specific float noise., Format a float using canonical JSON precision., _energy_by_leg() (+52 more)

### Community 49 - "size_battery.py"
Cohesion: 0.17
Nodes (25): _error(), GeofenceLoadError, _invalid_geometry_error(), load_geofences(), _parse_altitude_property(), _parse_kind(), EstimatorContextValue, Path (+17 more)

### Community 50 - "test_sitl_comparison.py"
Cohesion: 0.14
Nodes (38): build_sitl_comparison_report(), Build a deterministic comparison report from a SITL evidence bundle., Render a SITL comparison report as canonical deterministic JSON., render_sitl_comparison_json(), compare_sitl_evidence_bundle(), Build a comparison report from an evidence bundle., Deterministic outputs used as expected behavior for SITL comparison., SitlExpectedOutputs (+30 more)

### Community 51 - "test_sitl_artifacts.py"
Cohesion: 0.16
Nodes (30): RuntimeError, SitlArtifactError, SitlArtifactRecorder, build_sitl_evidence_bundle(), Build a deterministic SITL evidence bundle from existing scenario outputs., CompletedEvidenceAdapter, _document(), MalformedTelemetryMessage (+22 more)

### Community 52 - "isa_air_density_kgm3"
Cohesion: 0.08
Nodes (65): FailureCode, LandingZoneStateReachability, Reachability record from one route state to static landing zones., EmergencyPathEstimate, _aircraft_column(), compute_ground_risk(), controlled_ground_area_igrc(), GrcMitigationResult (+57 more)

### Community 53 - "ScenarioResultEnvelope"
Cohesion: 0.14
Nodes (19): _check_unique_ids(), _has_complete_scalar_wind_payload(), _has_layered_wind_payload(), _has_scalar_wind_payload(), _has_wind_payload(), Scenario plan schema for deterministic scenario runner (scenario.v1)., Initial simulation state for scenario execution.      These values override mi, _require_elapsed_time() (+11 more)

### Community 54 - "test_preflight_validation.py"
Cohesion: 0.14
Nodes (32): PreflightError, PreflightValidationReport, BaseModel, Structured failure detail for a single file check., Deterministic per-file preflight validation envelope., _batch_manifest(), _evidence_bundle(), _file_by_role() (+24 more)

### Community 55 - "Graphify"
Cohesion: 0.08
Nodes (34): Debounced Folder Watch, URL Ingestion, Neo4j and FalkorDB Exports, Graphify MCP Server, Token Reduction Benchmark, Wiki Export, Confidence and Provenance Rubric, Deterministic Full-Path Node IDs (+26 more)

### Community 56 - "test_divert_routing.py"
Cohesion: 0.13
Nodes (37): DivertRouteEstimate, Deterministic divert route estimate.      Computed when a divert policy action f, compute_divert_estimate(), _energy_remaining_at_index(), _no_estimate(), Compute a deterministic divert route estimate.      When entry_heading_deg and v, _divert_scenario(), _energy() (+29 more)

### Community 57 - "atomic_write_text"
Cohesion: 0.19
Nodes (19): atomic_write_text(), AtomicWriteDurabilityError, _fsync_directory(), OSError, Path, Atomic file writes (Ticket 104).  A killed or interrupted process must never lea, Replacement succeeded, but directory durability was not confirmed., Write ``text`` to ``path`` atomically.      The temp file is created in ``path`` (+11 more)

### Community 58 - "fitter.py"
Cohesion: 0.08
Nodes (39): CalibrationMismatchError, ValueError, Apply a calibration profile to a base vehicle.  Opt-in and non-destructive: a ca, Raised when a calibration profile does not match the base vehicle., _altitude_band(), _dataset_version(), fit_calibration_profile(), _fit_climb_rate() (+31 more)

### Community 59 - "test_yaml_config_features.py"
Cohesion: 0.06
Nodes (21): _make_scenario_plan(), Tests proving all implemented features are accessible via YAML configuration.  C, fidelity: v2 in mission estimation YAML must produce TURN_ARC legs., fidelity: v1 (default) must not produce TURN_ARC legs., estimator_version metadata must read 'v2' when fidelity v2 comes from mission YA, wind_layers in mission estimation YAML must apply to leg wind fields., Runtime options (CLI) must override mission YAML wind_layers., fidelity: v2 in scenario initial_conditions must produce TURN_ARC legs. (+13 more)

### Community 60 - "test_summary_format.py"
Cohesion: 0.14
Nodes (24): Provider backed by a 4D (time × altitude × lat × lon) wind grid.      All four a, SpatiotemporalWindProvider, _minimal_grid_yaml(), _provider_kwargs(), Tests for SpatiotemporalWindProvider and wind grid adapter., Wind at time midpoint should interpolate between two time snapshots., Wind should interpolate between altitude bands., At exactly t=300s (midpoint of [0, 600]), wind should be the exact average. (+16 more)

### Community 61 - "LandingZone"
Cohesion: 0.09
Nodes (37): _minimal_energy(), _point_zone(), Tests for Ticket 039: path-planning model gaps.  Covers: - Fidelity v2 materiali, The transit leg that follows a TURN_ARC must have path_distance_m reduced., With tangent offsets removed, v2 total < v1 total + sum of raw arc lengths., total_path_distance_m is always the exact sum of individual leg distances., Fidelity v1 is unchanged: path_distance_m == horizontal_distance_m for transit l, Without turn_radius_m, no TURN_ARC is injected and path_distance equals horizont (+29 more)

### Community 62 - "VehicleProfile"
Cohesion: 0.09
Nodes (25): Strict finite numeric types for safety-relevant input contracts., BaseModel, Vehicle capability schema models., Explicit estimator capabilities for action feasibility checks., VehicleCapabilities, AutopilotStack, StrEnum, Vehicle enums shared across schema modules. (+17 more)

### Community 63 - "ScenarioAssertionResult"
Cohesion: 0.11
Nodes (30): _has_full_mission_failure_with_legs(), _has_static_feasibility_failure(), _is_complete_success_result(), _is_partial_result(), Adapter layer for CLI, input loading, and output rendering., OperationalVerdict, StrEnum, _estimate_fields() (+22 more)

### Community 64 - "cli_batch_audit.py"
Cohesion: 0.18
Nodes (31): CaseCheck, Namespace, _build_cases(), Case, CommandResult, _estimate_case_status(), _expect_diagnostic_code(), _expect_json_field() (+23 more)

### Community 65 - "LayeredWindProvider"
Cohesion: 0.12
Nodes (27): _finite_float(), _grid_sequence(), _interp_index(), LayeredWindProvider, Wind provider abstractions., Return (lower_index, fraction) for linear interpolation along a sorted axis., A constant wind layer active from `altitude_m` upward., Provider returning wind from stacked altitude layers.      Each layer is active (+19 more)

### Community 66 - "test_sitl_evidence.py"
Cohesion: 0.14
Nodes (26): Render a SITL evidence bundle as canonical deterministic JSON., render_sitl_evidence_json(), _artifact_reference(), _build_bundle(), _build_drifted_bundle(), _build_failed_assertion_bundle(), MonkeyPatch, Path (+18 more)

### Community 67 - "test_validation_metrics.py"
Cohesion: 0.21
Nodes (21): _build_sitl_evidence_from_context(), _emit_sitl_progress(), _load_sitl_scenario_context(), Path, SITL-specific CLI support helpers., Live SITL connection and artifact recording options., _record_live_sitl_artifacts(), _render_sitl_evidence_output() (+13 more)

### Community 68 - "run_stochastic_propagation"
Cohesion: 0.15
Nodes (34): Run a seeded open-loop parameter sweep and return diagnostic timelines., run_stochastic_propagation(), Inputs for a bounded, open-loop stochastic diagnostic.      Version 2 deliberate, StochasticPropagationPlan, _far_landing_zone(), _mission_vehicle(), _mission_with_lax_distance_constraint(), _plan() (+26 more)

### Community 69 - "AltitudeReference"
Cohesion: 0.13
Nodes (24): altitude_reference_to_mavlink_frame(), _build_mission_item(), build_mission_items(), _coerce_altitude_reference(), _coerce_mission_action(), _coordinate_to_int(), mission_action_to_mavlink_cmd(), MissionDefaultsLike (+16 more)

### Community 70 - "_SitlComparisonMarkdownRenderer"
Cohesion: 0.13
Nodes (20): _message_fields(), _message_type(), _normalize_mapping(), _normalize_value(), Path, Artifact recording helpers for SITL evidence bundles., Write all recorded artifacts to disk and return the observed-artifacts object., _reference() (+12 more)

### Community 71 - "EnergyEstimate"
Cohesion: 0.09
Nodes (58): EnergyEstimate, LinkSystemEstimate, Mission-level deterministic energy and reserve result., Per-resource deterministic feasibility result., Per-link deterministic feasibility result., ResourceSystemEstimate, adjusted_cruise_power_for_vehicle(), _rth_is_feasible() (+50 more)

### Community 72 - "geofence_geojson.py"
Cohesion: 0.14
Nodes (27): _build_assumptions(), _build_dataflash_trace(), _build_record(), _by_timeus(), _collect_rows(), _core0_only(), _detect_missing_fields(), _float() (+19 more)

### Community 73 - "StochasticResultEnvelope"
Cohesion: 0.11
Nodes (42): _render_stochastic_summary(), BaseModel, StochasticResultEnvelope, _cross_track_points(), _estimation_error_points(), _fmt(), _fmt_duration(), Lines (+34 more)

### Community 74 - "propagator_ekf.py"
Cohesion: 0.10
Nodes (20): ParticleTrack, _EstimatedPositionState, EstimatedStateTracker, _kalman_scalar_update(), Random, Scalar EKF estimated-state tracker for the twin-state propagator., Return updated (estimate, variance) from a scalar Kalman measurement update., Tracks the autopilot's estimated state for one particle. (+12 more)

### Community 75 - "test_uncertainty_cli.py"
Cohesion: 0.15
Nodes (27): Path, Tests for the sample CLI command (Ticket 037)., Different seeds must produce different random samples end-to-end., Error output includes first_error_path when a required field is missing., _run(), test_sample_command_determinism_metadata_not_deterministic(), test_sample_command_different_seeds_produce_different_output(), test_sample_command_exits_zero() (+19 more)

### Community 76 - "test_scenario_cli.py"
Cohesion: 0.15
Nodes (27): Path, Tests for the scenario CLI command., _run(), test_checklist_format_produces_go_no_go_status(), test_divert_routing_example_scenario_runs_from_cli(), test_failing_scenario_exits_10(), test_geojson_format_produces_feature_collection(), test_integrated_example_scenario_loads_mission_assets_from_cli() (+19 more)

### Community 77 - "fetch_wind.py"
Cohesion: 0.18
Nodes (21): date, _build_grid(), _decompose(), _fetch(), _finite_number(), _hourly_datetime(), main(), _object_dict() (+13 more)

### Community 78 - "test_stochastic_cli.py"
Cohesion: 0.16
Nodes (25): Path, Tests for the propagate CLI command (Ticket 047)., Error output includes field-level validation details for operator diagnosis., _run(), test_legacy_stochastic_v1_is_rejected(), test_propagate_canonical_json_matches_golden_fixture(), test_propagate_command_determinism_metadata_not_deterministic(), test_propagate_command_exits_zero() (+17 more)

### Community 79 - "timeline.py"
Cohesion: 0.35
Nodes (19): build_validation_report(), Compare a predicted mission estimate against an observed flight trace.      Rais, _estimate(), _leg(), Path, Tests for predicted-vs-observed validation metrics (Ticket 082)., _record(), _segments() (+11 more)

### Community 80 - "fetch_geofences.py"
Cohesion: 0.14
Nodes (24): main(), _node_coordinate(), _object_dict(), _object_list(), _openaip_feature(), _openaip_features(), _openaip_kind(), _overpass_elements() (+16 more)

### Community 81 - "sora.py"
Cohesion: 0.16
Nodes (18): applicable_osos(), _party_dependencies(), _party_dependency(), Return every Table 14 OSO row, including explicit NR rows., _PartyCriterionRefs, _PartyDependencies, _dependency_signature(), test_applicable_osos_grows_with_sail() (+10 more)

### Community 82 - "FlightTraceRecord"
Cohesion: 0.23
Nodes (6): _finite_numeric_input(), GridPopulationProvider, Geod, Return a conservative half-cell spacing for route coverage checks., Return a conservative maximum over a metric circle's bounding box.          The, Provider backed by a uniform population-density grid.      The grid is indexed a

### Community 83 - "ArduPilotSitlAdapter"
Cohesion: 0.13
Nodes (8): ArduPilotSitlAdapter, Path, Final observed mission execution state, if a run was attempted., StrEnum, RunState, FakeMavlink, test_adapter_satisfies_sitl_adapter_protocol(), test_observed_artifacts_are_empty_in_ticket_041()

### Community 84 - "test_terrain_altitude.py"
Cohesion: 0.24
Nodes (25): _render_scenario_summary(), _scenario_result_from_envelope(), BaseModel, ScenarioResultEnvelope, _empty_section(), _fmt(), _fmt_duration(), _fmt_event_outcome() (+17 more)

### Community 85 - "test_qgc_export.py"
Cohesion: 0.25
Nodes (15): _boundary_sample_count(), _candidate_target_points(), _compile_zone_geometry(), _distance_to_geometry_m(), _dubins_distance_to_geometry_m(), _dubins_distance_to_target_m(), _geodesic_dubins_distance_m(), BaseGeometry (+7 more)

### Community 86 - "Estimator Field Semantics"
Cohesion: 0.10
Nodes (22): Altitude-Aware Geofences, Data Assets, Demo Geofence Assets, Demo Landing-Zone Assets, Deterministic Modeling Approach, Deterministic Execution Rules, Estimator Field Semantics, Fidelity v1 and v2 Semantics (+14 more)

### Community 87 - "test_weather_limits.py"
Cohesion: 0.19
Nodes (20): ConstantWindProvider, Provider returning a fixed EN wind vector., Path, A takeoff -> waypoint -> rtl mission (no loiter, no station-keep)., test_checklist_shows_weather_fail(), test_checklist_shows_weather_pass(), test_crosswind_over_limit_is_infeasible_for_known_heading(), test_gust_limit_without_gust_data_fails_closed() (+12 more)

### Community 88 - "test_profile_markdown.py"
Cohesion: 0.05
Nodes (49): _fmt(), Route altitude profile report rendering., Render a route altitude profile from a scenario envelope., Render a route altitude profile report as Markdown., _render_altitude_table(), _render_profile(), render_profile_markdown(), render_profile_markdown_from_scenario() (+41 more)

### Community 89 - "Usage Guide"
Cohesion: 0.16
Nodes (21): Machine-Readable Run Progress, SORA Mitigation Depth, Energy and Reserve Semantics, Monte Carlo Sampling Semantics, Wind Provider and Precedence Semantics, Batch Estimation Workflow, Minimum Battery Sizing, Energy Reserve Sensitivity (+13 more)

### Community 90 - "checklist_markdown.py"
Cohesion: 0.06
Nodes (62): dubins_path_to_point(), dubins_path_to_point_m(), DubinsPath, geodesic_dubins_path_to_point_m(), _left_center(), _ls_path(), _ls_path_length(), Geod (+54 more)

### Community 91 - "Community Vehicle Profiles"
Cohesion: 0.10
Nodes (21): Independent Normal Wind, Power, and Capacity Variation, Pipeline Demo Wind Uncertainty Plan, Seeded Monte Carlo Sampling, Autel EVO Max 4T Vehicle Profile, Autel Endurance-Derived Power Model, DJI Matrice 300 RTK Vehicle Profile, DJI M300 Endurance-Derived Power Model, Generic Survey Hexacopter Vehicle Profile (+13 more)

### Community 92 - "scenario.py"
Cohesion: 0.08
Nodes (58): LandingZone, A named static landing zone., A point on the deterministic scenario execution timeline.      Each point repres, TimelinePoint, _build_options(), _build_policy_outcome(), _entry_heading_at_index(), _fired_event_outcome() (+50 more)

### Community 93 - "BVLOS Mission Simulator Brief"
Cohesion: 0.14
Nodes (20): Documentation Workflow, GitHub Pages Deployment, Strict MkDocs Build, Deterministic Mission Validation, BVLOS Mission Simulator Brief, Engineering-Evidence Safety Scope, Target Users, Documentation Index (+12 more)

### Community 94 - "Versioning Policy"
Cohesion: 0.13
Nodes (19): Contract Impact Review, Pull Request Template, Quality Gate Checklist, Contract Version Discovery, Layered Architecture Boundaries, Behavior-Focused Testing, Contribution Style Guide, Package Boundaries (+11 more)

### Community 95 - "Calibration Profiles and Parameter Fitting"
Cohesion: 0.17
Nodes (19): DataFlash Log Ingestion, Flight Log Ingestion and Trace Normalization, NormalizedFlightTrace, Telemetry Carry Forward Merge, Flight Phase Segmentation, Kinematic Phase Fallback, Mode First Phase Segmentation, PhaseSegmentResult (+11 more)

### Community 96 - "test_dynamic_landing_zone.py"
Cohesion: 0.16
Nodes (20): _assign_phase(), _compute_vert_rates(), _encode_segments(), _kinematic_phase(), _make_segment(), Deterministic flight phase segmentation over normalized traces., Absorb single-record phase blips into their surrounding phase.      A lone recor, _smooth() (+12 more)

### Community 97 - "_SitlPositionProximityComparator"
Cohesion: 0.18
Nodes (20): advance_true_state(), _clamp(), compute_cross_track_errors(), controller_corrections(), ControllerState, Proportional cross-track / along-track path-following controller model., Advance state.true_lat/true_lon via controller feedback.      Accumulates path_l, Mutable per-particle controller state carried across time steps. (+12 more)

### Community 98 - "_write_obstacle_inputs"
Cohesion: 0.21
Nodes (16): _density_row(), intrinsic_ground_risk_class(), Select the conservative population band at every displayed boundary.      In par, _population_provider(), test_250g_25mps_exception_is_igrc_one_regardless_of_population(), test_assessed_population_buffer_captures_dense_area_beside_route(), test_compute_ground_risk_samples_population_grid(), test_dense_population_unsupported_cells_are_rejected() (+8 more)

### Community 99 - "test_ground_risk.py"
Cohesion: 0.08
Nodes (43): EstimationOptions, BaseModel, Runtime estimator options.      Every non-null runtime field takes precedence ov, Sample every leg, including endpoints and reconstructed turn arcs.      ``max_se, route_leg_samples(), Circular loiter starts and ends at the same position (zero ground translation)., LOITER_RADIUS_IGNORED warning is emitted when loiter_radius_m is set on a FW loi, Fixed-wing circular loiter path_distance_m should equal TAS × loiter_time_s. (+35 more)

### Community 100 - "Pipeline Demo Stochastic EKF Plan"
Cohesion: 0.14
Nodes (18): EKF Mission and Vehicle References, 100 EKF Particles, 2 s Steps, Seed 42, Estimation-Error and Cross-Track Timelines, Pipeline Demo Stochastic EKF Plan, 100 Particles, 2 s Steps, Seed 42, Pipeline Demo Stochastic Plan, Wind, Cruise-Power, and Battery Distributions, 0.5 m/s Wind Process Noise (+10 more)

### Community 101 - "ProvenanceInput"
Cohesion: 0.33
Nodes (22): _invoke(), Path, test_aerodrome_environment_yields_higher_arc_than_low_altitude(), test_airspace_ceiling_must_cover_verified_maximum_height(), test_conservative_ground_risk_buffer_must_cover_operational_height(), test_grc_above_seven_flags_certified_category(), test_ground_risk_mitigation_credit_is_rejected_without_criteria_evaluator(), test_markdown_request_cannot_bypass_mitigation_credit_gate() (+14 more)

### Community 102 - "AirRiskClass"
Cohesion: 0.12
Nodes (30): AirRiskAssessment, compute_air_risk(), initial_air_risk_class(), _is_controlled(), JARUS SORA 2.5 Air Risk Class (ARC) assignment.  The initial ARC follows the gen, Compute initial/residual ARC and the resulting TMPR requirement.      Residual A, Assign the SORA 2.5 initial ARC from the generalised AEC table., Airspace (+22 more)

### Community 103 - "SITL Adapter Contract"
Cohesion: 0.15
Nodes (16): Continuous Integration Workflow, Python 3.12 and 3.13 Matrix, Release Quality Gates, SITL Adapter Package Migration, Development Verification Workflow, Complementary Drone Tool Ecosystem, Adapter Boundary Rules, SITL Adapter Dependency Boundary (+8 more)

### Community 104 - "SensorProfile"
Cohesion: 0.12
Nodes (38): adjacent_area_outer_limit_m(), _assembly_is_covered(), _below(), derive_containment_requirement(), _OperationalColumn, JARUS SORA 2.5 Step 8 containment requirement derivation.  This module implement, Return the 3-minute flyaway distance clamped to 5-35 km., Derive Step 8 operational limits and robustness without claiming compliance. (+30 more)

### Community 105 - "Project Changelog"
Cohesion: 0.17
Nodes (16): Calibration Profiles and Parameter Fitting, Project Changelog, Flight Log Ingestion and Trace Normalization, Predicted-versus-Observed Validation, Flight Phase Segmentation, Version Bump and Release Tooling, Return-to-Home Reserve Gate, Contributing Guide (+8 more)

### Community 106 - "Ticket 047: Stochastic State Propagation"
Cohesion: 0.17
Nodes (15): Position, Energy, and Wind Belief State, Per-Step Reserve-Violation Probability, stochastic-envelope.v1, Ticket 047: Stochastic State Propagation, Time-Stepped Stochastic Propagator, EKF Predict-Measure-Update Cycle, Estimated-State Policy Decisions, Ticket 048: Closed-Loop Observation Model and Twin-State Architecture (+7 more)

### Community 107 - "test_sora_cli.py"
Cohesion: 0.20
Nodes (10): SitlJsonValue, Markdown rendering for SITL comparison reports., Render SITL comparison reports as Markdown., Render a SITL comparison report as Markdown., render_sitl_comparison_markdown(), _SitlComparisonMarkdownRenderer, Build deterministic SITL comparison reports., _SitlComparisonReportBuilder (+2 more)

### Community 108 - "sora.py"
Cohesion: 0.09
Nodes (39): PopulationEvidence, Provenance and validity contract for a SORA-eligible population grid., determine_sail(), SORA SAIL determination and Operational Safety Objective (OSO) assignment.  The, Look up the SAIL from the final GRC and residual ARC., _air_risk(), build_sora_assessment(), _conservative_route_max_agl_m() (+31 more)

### Community 109 - "fetch_obstacles.py"
Cohesion: 0.33
Nodes (13): _closed_ring(), _feature(), _features(), _height_amsl(), main(), _node_coordinate(), _node_feature(), _object_dict() (+5 more)

### Community 110 - "Ticket 043: SITL Scenario Comparison Report"
Cohesion: 0.19
Nodes (13): Adapter-Level Comparison Boundary, Deterministic and Observed Comparison Dimensions, Passed, Drifted, Failed, and Unsupported Summary Rules, sitl-comparison.v1 Report, Ticket 043: SITL Scenario Comparison Report, Optional Adapter-Local Dependencies, PX4 MAVLink Mission Upload, PX4 SITL Adapter Lifecycle (+5 more)

### Community 111 - "Deterministic Sensitivity Sweep"
Cohesion: 0.15
Nodes (13): Deterministic Sensitivity Sweep, Energy Reserve Sensitivity Table, SensitivityLevel, BatterySizingResult, Minimum Battery Binary Search, Minimum Battery Sizing Calculator, Best Window Selection, Departure Window Finder (+5 more)

### Community 112 - "SORA Intrinsic Ground Risk Class"
Cohesion: 0.18
Nodes (13): Aircraft Characteristic Dimension, SORA-Style iGRC Lookup Table, Population-Density Grid, SORA Intrinsic Ground Risk Class, Operational Airspace Descriptor, Specific Assurance and Integrity Level Determination, SORA Air Risk Class, SORA Pre-Assessment Disclaimer (+5 more)

### Community 113 - "ScenarioPlan"
Cohesion: 0.33
Nodes (10): _landing_zone(), _lost_link_event(), _outcome_actions(), _plan(), Tests for per-event lost-link policy overrides., test_divert_policy_on_second_event_resolves_divert_estimate(), test_event_without_policy_uses_global(), test_per_event_policy_none_and_no_global_produces_no_outcome() (+2 more)

### Community 114 - "SITL Adapter Contract and Evidence Schema"
Cohesion: 0.21
Nodes (12): NoopSitlAdapter, SITL Adapter Contract and Evidence Schema, SITL CLI Contract, SitlAdapter Interface, ArduPilot SITL Launch and Mission Upload, ArduPilotSitlAdapter, MAVLink Mission Upload, Optional Pymavlink Dependency (+4 more)

### Community 115 - "80 m Multirotor Demo Route"
Cohesion: 0.21
Nodes (12): Autel EVO Max 4T Demo Mission, 80 m Multirotor Demo Route, 20% Landing Reserve and Wind-Limit Constraints, autel_evo_max_4t Vehicle Binding, 80 m Multirotor Demo Route, DJI Matrice 300 RTK Demo Mission, 20% Landing Reserve and Wind-Limit Constraints, dji_matrice_300_rtk Vehicle Binding (+4 more)

### Community 116 - "Deterministic Divert Route Construction"
Cohesion: 0.22
Nodes (11): Fidelity v2 Turns and Fixed Wing Loiter, Fixed Wing Circular Loiter, Turn Arc Dynamics, Deterministic Divert Route Construction, Bank Angle Constrained Divert Path, Bank Angle Model and Dubins Path Optimization, Dubins Path Solver, Dubins Planar Accuracy Warning (+3 more)

### Community 117 - "Ticket 056: Community Vehicle Profiles"
Cohesion: 0.18
Nodes (11): PX4 ULog Reference Flights, Five Commercial UAS Profiles, Ticket 056: Community Vehicle Profiles, Operational Calibration Disclaimer, Published and Derived Profile Provenance, Single-Line Estimate Summary, Single-Line Scenario Summary, Ticket 057: Summary Output Format (+3 more)

### Community 118 - "Ticket 107: Machine-Readable Preflight Validation"
Cohesion: 0.20
Nodes (11): Ticket 106: Machine-Readable Run Progress, Keyword-Only Progress Callback Contract, ProgressReporter JSONL Emitter, progress_reporter Context Manager, Progress Side-Channel Invariance, Collect-All Preflight Failure Engine, Ticket 107: Machine-Readable Preflight Validation, PreflightValidationReport, FileCheck, and PreflightError (+3 more)

### Community 119 - "Canonical Result Envelope"
Cohesion: 0.24
Nodes (10): Canonical Result Envelope, CLI Exit Code Contract, Estimator CLI and Result Envelope, Golden Compatibility Fixtures, Public Schema Versioning Policy, Versioning Policy and Golden Fixtures, Deterministic Error Envelopes, Field Semantics Contract (+2 more)

### Community 120 - "geofence-geojson.v1 Output"
Cohesion: 0.24
Nodes (10): Offline Alpine Demonstration, Mission-Compatible Offline Assets, Ticket 052: Real-World Data Fetch Scripts, Open-Meteo, SRTM, and Overpass Fetchers, Ticket 053: Airspace Geofence Fetch Script, geofence-geojson.v1 Output, OpenAIP Airspace Source, Way-Based Overpass Airspace Fallback (+2 more)

### Community 121 - "Alpine Infeasible 001 Mission"
Cohesion: 0.29
Nodes (10): Alpine Infeasible Batch Run, Alpine Terrain, Wind, Landing-Zone, and Geofence Assets, Alpine Infeasible 001 Mission, Expected Reserve-Below-Threshold Outcome, quadplane_small_battery Vehicle Binding, Alpine Reserve-Failure Walkthrough, Committed Offline Terrain, Wind, Landing-Zone, and Geofence Assets, Overpass Airspace Coverage Limitation (+2 more)

### Community 122 - "Example Missions Catalog"
Cohesion: 0.24
Nodes (10): Fidelity v2 and 500 m Sub-Segment Settings, Pipeline Demo 001 Integrated Mission, Terrain and Spatiotemporal Wind Asset Stack, Primary Mesh Network Link, Pipeline Demo 001 Resource-Link Mission, Terrain, Wind, Geofence, and Landing-Zone Asset Stack, Starlink Backup Link, Example Missions Catalog (+2 more)

### Community 123 - "tool_version"
Cohesion: 0.04
Nodes (114): BatteryCapacityRecommendationPayload, BatterySizingEnvelope, BatterySizingPayload, BatterySizingProvenance, build_battery_sizing_envelope(), _provenance_input(), _provenance_inputs(), BaseModel (+106 more)

### Community 124 - "progress_reporter"
Cohesion: 0.19
Nodes (24): Particle track and population dataclasses for stochastic propagation., BatteryMeterModel, GpsModel, BaseModel, Vehicle sensor model schema (sensors are optional; absent = perfect measurements, SensorProfile, _mission_vehicle(), _plan() (+16 more)

### Community 125 - "Deterministic Energy Feasibility"
Cohesion: 0.25
Nodes (9): Deterministic Energy Feasibility, Phase Based Energy Model, Reserve at Landing Calculation, Forbidden and Required Zone Semantics, GeoJSON Geofence Adapter, Static Geofence Feasibility, Scenario Assertion Engine, Scenario Runner Core (+1 more)

### Community 126 - "Resource and Link Feasibility Abstractions"
Cohesion: 0.31
Nodes (9): GeoJSON Landing Zone Adapter, Static Landing Zone Reachability, Straight Line Contingency Reachability, Generalized Feasibility Result, Resource and Link Feasibility Abstractions, Dynamic Landing Zone Availability, Landing Zone Availability Events, Computed Divert Routing (+1 more)

### Community 127 - "Batch Scenario and Batch Propagate Modes"
Cohesion: 0.22
Nodes (9): Batch Per Run Envelopes, Batch Scenario and Batch Propagate Modes, BatchManifest Run Type Dispatch, Reserve Violation Probability Timeline, Stochastic GeoJSON and KML Adapters, Stochastic Propagation GeoJSON Export, ProgressCallback, Propagation Progress Feedback (+1 more)

### Community 128 - "Ticket Backlog"
Cohesion: 0.25
Nodes (9): Backend Integration Readiness Track, Calibration and Validation Track, Deterministic Core Rule, Cross-Capability Integration Standard, Ticket Backlog, Calibration Example, Ingestion, Segmentation, Fitting, and Apply Pipeline, Deterministic calibration-profile.v1 Artifact (+1 more)

### Community 129 - "Pipeline Demo Infeasible Mission"
Cohesion: 0.25
Nodes (9): Thirty-Metre-per-Second Crosswind Scenario, Pipeline Demo Infeasible Mission, Golden Mission Weather and Reserve Constraints, Deterministic Offline Estimator Provenance, Infeasible Estimator Golden Report, No Valid Result Scope, WIND_TRIANGLE_NO_SOLUTION, Golden Deterministic QuadPlane Energy Profile (+1 more)

### Community 130 - "_SitlComparisonValueCoercer"
Cohesion: 0.29
Nodes (3): SitlJsonValue, Coerce loose artifact payload values into typed comparison values., _SitlComparisonValueCoercer

### Community 131 - "CLI Exit Code Contract"
Cohesion: 0.18
Nodes (12): Public schema-migration helpers., _applied(), detect_mission_version(), _finite_number(), _mapping(), Any, Mission schema detection and v6→v7 migration., Detect explicit mission versions; unversioned files are legacy v6. (+4 more)

### Community 132 - "Ticket 044: Geodesic Dubins Divert Path"
Cohesion: 0.32
Nodes (8): Ticket 044: Geodesic Dubins Divert Path, Geodesic Dubins Formulation, Long-Range Accuracy with Stable Result Fields, DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT Retirement, Landing-Zone TAS-Only Energy Gap, Ticket 062: Wind-Corrected Divert and Landing-Zone Energy, Wind-Corrected Divert Estimate, Wind-Triangle Groundspeed and Energy

### Community 133 - "Ticket 058: NOTAM and Live Airspace Integration"
Cohesion: 0.29
Nodes (8): Time-Windowed NOTAM and TFR Fetch, Polygon and Circular NOTAM Normalization, Ticket 058: NOTAM and Live Airspace Integration, Explicit Warning for Unresolvable Geometry, Ticket 061: 3D Geofence Altitude Bounds, Geofence floor_m and ceiling_m Bands, Leg-to-Zone Altitude Overlap, Unbounded-Zone Backward Compatibility

### Community 134 - "Physically Aware Energy Model"
Cohesion: 0.25
Nodes (8): Opt-In RTH Gate Backward Compatibility, Return-to-Home Reserve Feasibility Gate, RTH Reserve Timeline, Closed-Form Energy Calibration Boundary, ISA Atmosphere Density Helper, Mass and Air-Density Power Scaling, Physically Aware Energy Model, State-of-Charge Usable-Capacity Derating

### Community 135 - "120 m VTOL Demo Route"
Cohesion: 0.32
Nodes (8): 120 m VTOL Demo Route, 20% Landing Reserve and Wind-Limit Constraints, Quantum-Systems Trinity F90+ Demo Mission, qs_trinity_f90_plus Vehicle Binding, 120 m VTOL Demo Route, 20% Landing Reserve and Wind-Limit Constraints, wingtra_one_gen2 Vehicle Binding, Wingtra One Gen II Demo Mission

### Community 136 - "fetch_population.py"
Cohesion: 0.28
Nodes (13): _assert_valid_progress(), Path, Tests for machine-readable run progress (Ticket 106).  Covers the JSONL progress, _read_progress_records(), test_batch_progress_file_cannot_overwrite_hardlinked_input(), test_batch_progress_file_cannot_overwrite_mission_asset(), test_batch_progress_file_must_be_outside_output_directory(), test_batch_progress_file_records() (+5 more)

### Community 137 - "Fidelity v2 Layered Wind and Subsegment Sampling"
Cohesion: 0.29
Nodes (7): Deterministic Subsegment Sampling, Fidelity v2 Layered Wind and Subsegment Sampling, LayeredWindProvider, Continuous Spatiotemporal Wind Grid, Quadrilinear Wind Interpolation, SpatiotemporalWindProvider, Wind Grid v1 Schema

### Community 138 - "Shared CLI, API, and UI Core Path"
Cohesion: 0.33
Nodes (7): REST API and Web Map UI, Shared CLI, API, and UI Core Path, Ticket 050: User Interfaces and Service Adapters, Ticket 055: GeoJSON and KML Route Export, KML Route Export, Pure Map-Adapter Projection, Terse Adapter Projection

### Community 139 - "Scenario Route Export Builder"
Cohesion: 0.29
Nodes (7): Divert Action Point, Divert Route Layer, Divert Route Layer in Scenario GeoJSON and KML Export, Scenario Route Export Builder, Effective Policy Fallback, Per Event Lost Link Policy Override, ScenarioEvent Policy Override

### Community 140 - "Hardware-in-the-Loop Validation"
Cohesion: 0.33
Nodes (7): HITL Hardware Descriptor, Hardware-in-the-Loop Validation, SITL Adapter Contract Reuse, sitl-evidence.v1 HITL Evidence Bundle, Estimator Latency and Throughput Baseline, Performance Benchmark Suite, Twenty-Percent Performance Regression Gate

### Community 141 - "Pipeline Demo 001 Ground-Risk Mission"
Cohesion: 0.33
Nodes (7): Pipeline Population-Density Grid, Uniform 12 people/km² Density Grid, Class G Airspace Descriptor, Pipeline Demo 001 Ground-Risk Mission, Population Grid Asset Binding, SORA iGRC Pre-Assessment, SORA Ground-Risk Mission Variant

### Community 142 - "divert.py"
Cohesion: 0.26
Nodes (12): _active_provider_next_change(), evaluate_weather_feasibility(), _failure_from_violation(), _leg_crosswind_mps(), _legs_with_weather_observations(), Deterministic, fail-closed weather-minimums feasibility evaluation.  Enforces su, Evaluate wind/crosswind limits after kinematic route expansion., Sample endpoints, scheduled changes, and at most 60-second intervals. (+4 more)

### Community 143 - "Operational Integration Seams"
Cohesion: 0.47
Nodes (6): Operational Integration Seams, Operational Seam Interfaces, Replayable Operational Intent, Live Comms Remote ID and Traffic Integrations, Live Operational Signal Adapters, Replayable Live Evidence

### Community 144 - "Route Altitude Profile Report"
Cohesion: 0.33
Nodes (6): Altitude and Terrain Clearance Table, ASCII Terrain Cross Section, Route Altitude Profile Report, Checklist Markdown Renderer, Go No Go Status Aggregation, Pre Flight Go No Go Checklist Output

### Community 145 - "Binary Flight-Log Ingestion"
Cohesion: 0.33
Nodes (6): ArduPilot DataFlash Binary Adapter, Binary Flight-Log Ingestion, Content-Magic Flight-Log Dispatch, Deterministic Canonical Flight-Trace Output, NormalizedFlightTrace, PX4 ULog Adapter

### Community 146 - "Backend-Facing CLI Exit-Code Contract"
Cohesion: 0.33
Nodes (6): Catch-All INTERNAL_ERROR Exit, Backend-Facing CLI Exit-Code Contract, Command-Specific Exit-Code Divergences, Authoritative Per-Command Exit-Code Table, CANCELLED Exit Code 14, SIGTERM and SIGINT Cancellation Handlers

### Community 147 - "Pipeline Demo 001 Mission"
Cohesion: 0.33
Nodes (6): Referenced Mission Asset Checks, Geofence and Landing-Zone Static Checks, Pipeline Demo 001 Mission, standard_lost_link_v1 Policy, Geofence and Landing-Zone Assets, Baseline Pipeline Mission Variant

### Community 148 - "Pipeline Spatiotemporal Wind Grid"
Cohesion: 0.33
Nodes (6): Time-Altitude-Latitude-Longitude Wind Axes, Pipeline Spatiotemporal Wind Grid, Time- and Altitude-Varying Easterly Wind, Open-Meteo Wind Fetch Workflow, Quadrilinear Wind Interpolation, Spatiotemporal Wind Grid Examples

### Community 149 - "Partial Estimator Golden Report"
Cohesion: 0.40
Nodes (6): Pipeline Demo Partial Mission, Terrain-Referenced Waypoint Without Terrain Asset, Completed-Legs-Only Result Scope, Geodesic Fidelity and Dubins-Path Assumptions, Partial Estimator Golden Report, UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN

### Community 150 - "Lost Link Policy Evaluator"
Cohesion: 0.40
Nodes (5): Deterministic Scenario Timeline, Comms Link Model and Contingency Policies, Contingency Policy Actions, Lost Link Policy Evaluator, Communication Link System Model

### Community 151 - "SITL Evidence v1 Bundle"
Cohesion: 0.50
Nodes (5): Monte Carlo Uncertainty Modeling, Seeded Monte Carlo Execution, Uncertainty Report Contract, SITL Evidence v1 Bundle, Completed Evidence Bundle

### Community 152 - "Per-Leg RTH Reserve Timeline"
Cohesion: 0.60
Nodes (5): GeoJSON Route, Landing-Zone, and Geofence Layers, Mission-Wide RTH Feasibility, RTH Markdown and GeoJSON Views, Ticket 063: Return-to-Home Reserve Check, Per-Leg RTH Reserve Timeline

### Community 153 - "Demo batch.v1 Manifest"
Cohesion: 0.40
Nodes (5): Alpine Standard Batch Run, Demo batch.v1 Manifest, Pipeline Demo Batch Run, batch.v1 Manifest Format, Example Batch Manifests

### Community 154 - "Pipeline Demo 001 EKF Mission"
Cohesion: 0.40
Nodes (5): quadplane_v1_ekf Vehicle Binding, Pipeline Demo 001 EKF Mission, Stochastic EKF and Tracking-Controller Route Variant, VTOL Takeoff, Waypoint, Loiter, and RTL Route, EKF Twin-State Mission Variant

### Community 156 - "test_time_varying_geofence.py"
Cohesion: 0.10
Nodes (62): Estimator core constants., EnergyPowerSource, EstimateStatus, GeofenceKind, SpeedSource, EstimatorError, EstimatorInfeasibleError, InvalidEstimatorInputError (+54 more)

### Community 157 - "Terrain Referenced Altitude Execution"
Cohesion: 0.67
Nodes (4): GridTerrainProvider, Terrain Coverage Diagnostics, Terrain Referenced Altitude Execution, TerrainProvider

### Community 158 - "Preflight CLI Command"
Cohesion: 0.67
Nodes (4): Composite Preflight GO/NO-GO Decision, Preflight CLI Command, preflight-report.v1, preflight-validation.v1

### Community 159 - "Versioned Migration Registry"
Cohesion: 0.50
Nodes (4): Chained Pure Schema Migrations, Versioned Migration Registry, Schema Migration Command, YAML Comment and Key-Order Preservation

### Community 160 - "QGroundControl Mission Export"
Cohesion: 0.50
Nodes (4): MAVLink Altitude-Frame Mapping, QGC-to-bvlos-sim Mission Round Trip, QGroundControl Mission Export, QGC SimpleItem .plan Format

### Community 161 - "Weather Minimums GO/NO-GO Gate"
Cohesion: 0.50
Nodes (4): Per-Leg Crosswind Component Check, Gust-Data-Unavailable Advisory, Weather Minimums GO/NO-GO Gate, Sustained-Wind Limit Enforcement

### Community 162 - "Time-Varying Geofence Activation"
Cohesion: 0.50
Nodes (4): Route-Leg and Active-Window Overlap, Missing-Departure Conservative Fallback, Mission Departure Time, Time-Varying Geofence Activation

### Community 163 - "Version Bump Command"
Cohesion: 0.50
Nodes (4): Explicit Release Side Effects, Release Version Consistency Check, Version-Agnostic Golden Fixtures, Version Bump Command

### Community 164 - "Three-Dimensional Obstacle Clearance Check"
Cohesion: 0.50
Nodes (4): Along-Leg Terrain Clearance, Three-Dimensional Obstacle Clearance Check, Obstacle GeoJSON Layer, Operator Obstacle-Data Quality Responsibility

### Community 165 - "Input and Output Contract-Version Map"
Cohesion: 0.50
Nodes (4): Canonical JSON Version Discovery, Input and Output Contract-Version Map, Module-Owned Version Constants, schema-versions Command

### Community 166 - "Prioritized Resource Systems"
Cohesion: 0.50
Nodes (4): Onboard Battery Backup, Optical-Fiber External Power, Prioritized Resource Systems, QuadPlane Resource/Link Vehicle Profile

### Community 167 - "QuadPlane v1 EKF and Tracking Profile"
Cohesion: 0.83
Nodes (4): GPS and Battery-Meter Sensor Models, Proportional Cross-Track Tracking Controller, QuadPlane v1 EKF and Tracking Profile, Twin-State Stochastic Tracking Timelines

### Community 168 - "test_link_failure_has_full_mission_result_validity"
Cohesion: 0.30
Nodes (11): _apply_migration(), migrate(), _MigrationPlan, _parse_mapping(), _plan_migration(), Path, Schema migration command., Migrate mission.v6 YAML/JSON inputs to mission.v7. (+3 more)

### Community 169 - "Bug Report Template"
Cohesion: 0.67
Nodes (3): Bug Report Template, Minimal Mission and Simulation Inputs, Reproducible Problem Report

### Community 170 - "Feature Request Template"
Cohesion: 0.67
Nodes (3): Contract Impact Assessment, Feature Request Template, Use Case and Alternatives Considered

### Community 171 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Code of Conduct, Conduct Enforcement and Reporting, Respectful Contributor Community

### Community 172 - "Dropped Sample Count"
Cohesion: 1.00
Nodes (3): Dropped Sample Count, Geofence and Landing Zone Awareness in Stochastic Propagation, Stochastic Feasibility Accounting

### Community 173 - "Explicit Vehicle Profile Selection"
Cohesion: 1.00
Nodes (3): Explicit Vehicle Profile Selection, QGC Conversion Boundary, QGC Convert Vehicle Profile Selection

### Community 174 - "Behavior-Preserving Propagator Module Split"
Cohesion: 0.67
Nodes (3): Behavior-Preserving Propagator Module Split, run_stochastic_propagation Public Facade, Seed-Exact Stochastic Reproducibility

### Community 175 - "MkDocs Material GitHub Pages Site"
Cohesion: 0.67
Nodes (3): Isolated Documentation Toolchain, MkDocs Material GitHub Pages Site, Strict Documentation Build

### Community 176 - "BVLOS Simulator Documentation Site"
Cohesion: 0.67
Nodes (3): BVLOS Simulator Documentation Site, MkDocs Material Theme, Strict Documentation Navigation

### Community 186 - "Q: One production regression remains: explicit feasible external power may replace base battery/RTH feasibility, while onboard/hybrid resources must still account for RTH reserve."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: One production regression remains: explicit feasible external power may replace base battery/RTH feasibility, while onboard/hybrid resources must still account for RTH reserve., Source Nodes

### Community 187 - "Contributing Guide"
Cohesion: 0.50
Nodes (4): Dubins Path Solver, Divert Routing Semantics, Scenario Execution Workflow, Contingency Planning

### Community 188 - "ulog.py"
Cohesion: 0.22
Nodes (24): _altitude_m(), _battery_rows(), _dataset(), _first_dataset(), _first_number(), _gps_rows(), _ingest_ulog_bytes(), _integer() (+16 more)

### Community 189 - "geojson_export.py"
Cohesion: 0.23
Nodes (14): _build_provider(), _finite_number(), load_population_grid(), _nonblank_string(), _population_evidence(), PopulationGridLoadError, Any, Path (+6 more)

### Community 190 - "Ticket 054: Reference Inputs for Calibration and Import"
Cohesion: 0.40
Nodes (6): ULog and QGC Field-Mapping Design Notes, QGroundControl Plan References, Ticket 054: Reference Inputs for Calibration and Import, Ticket 060: Import, Export, and Batch Workflows, QGroundControl Mission Conversion, Shared Single and Batch Estimate Behavior

### Community 191 - "test_terrain_altitude.py"
Cohesion: 0.11
Nodes (25): ConstantElevationProvider, Provider returning a fixed ground elevation AMSL for all positions., AltitudeReference, Altitude reference frame for mission authoring and simulation., test_estimator_is_deterministic_with_terrain_provider(), Tests for terrain-referenced altitude resolution., Leg start altitude should equal ground_elevation + altitude_m above ground., GridTerrainProvider returning None should produce TERRAIN_COVERAGE_MISSING. (+17 more)

### Community 192 - "test_migrations.py"
Cohesion: 0.22
Nodes (22): migrate_mission_v6_to_v7(), Upgrade unambiguous v6 declarations; reject unsafe semantic guesses., _legacy_payload(), Path, test_migrate_backup_preserves_original(), test_migrate_cli_rejects_non_string_schema_version(), test_migrate_directory_validates_every_file_before_writing(), test_migrate_dry_run_never_copies_latest_input() (+14 more)

### Community 193 - "kml_export.py"
Cohesion: 0.20
Nodes (10): _handle_cancellation_signal(), install_cancellation_handlers(), NoReturn, Exit with the documented CANCELLED code on SIGTERM/SIGINT.      Atomic output wr, Route SIGTERM and SIGINT to the CANCELLED exit code.      Called from the consol, FrameType, main(), Entry point for the bvlos-sim CLI. (+2 more)

### Community 194 - "Q: now write project and find gaps, issues, bad math, bad science or anything that will prevent a real team from using it"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: now write project and find gaps, issues, bad math, bad science or anything that will prevent a real team from using it, Source Nodes

### Community 195 - "test_sora_cli.py"
Cohesion: 0.25
Nodes (8): Atomic Output Writes and Clean Cancellation, Machine-Readable Preflight Validation, Cancellation Contract, CLI Exit Code Contract, Per-Command Exit-Code Divergences, Programmatic Caller Guidance, Fifteen-Command CLI Surface, preflight-validation.v1 JSON

### Community 196 - "enums.py"
Cohesion: 0.52
Nodes (6): _fmt(), _ground_risk_lines(), _igrc_label(), render_ground_risk_markdown(), render_ground_risk_markdown_for_estimate(), render_ground_risk_markdown_from_scenario()

### Community 197 - "test_time_varying_geofence.py"
Cohesion: 0.36
Nodes (10): _large_battery_vehicle(), _mission_crossing_zone_after_2000(), _mission_departing_at(), Tests for time-varying geofence activation windows., test_daily_recurring_geofence_applies_on_later_dates(), test_geofence_without_time_window_remains_always_active(), test_time_windowed_geofence_active_after_active_from_is_infeasible(), test_time_windowed_geofence_inactive_before_active_from_is_feasible() (+2 more)

### Community 199 - "test_sail.py"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Audit and fix battery sizing's monotonic-search assumption. Induced power can scale superlinearly with battery mass, so exponential upper-bound probes can skip a feasible capacity interval., Source Nodes

### Community 200 - "migrate.py"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Review the newly changed SORA 2.5 implementation and migration changes for correctness, fail-open behavior, contract inconsistencies, wrong Table 14/TMPR/SAIL values, and tests that assert implementation rather than official semantics., Source Nodes

### Community 201 - "fetch_population.py"
Cohesion: 0.21
Nodes (13): _axis(), _chunks(), main(), Fetch a diagnostic WorldPop point-sampled population grid.  The script samples W, _sample_density(), _sample_grid(), _sample_value(), _year_epoch_ms() (+5 more)

### Community 202 - "Project Knowledge Graph"
Cohesion: 0.33
Nodes (5): Keep the graph current, Project Knowledge Graph, Project-local setup, Query before browsing, Version-control policy

### Community 203 - "test_exit_codes_contract.py"
Cohesion: 0.24
Nodes (8): _boom(), MonkeyPatch, Path, Backend-facing CLI exit-code contract (Ticket 103).  These tests pin the part of, test_calibrate_internal_error_exit_code(), test_sora_internal_error_exit_code(), test_validate_internal_error_exit_code(), test_validate_rejects_mismatched_trace_hash()

### Community 204 - "_write_ground_risk_inputs"
Cohesion: 0.70
Nodes (5): Path, test_estimate_geojson_includes_igrc_on_route_legs(), test_estimate_ground_risk_format_renders_table(), _write_ground_risk_inputs(), _write_yaml()

### Community 205 - "_PlanItemBuilder"
Cohesion: 0.11
Nodes (28): build_qgc_plan(), ExportDiagnostic, _frame_and_alt_mode(), _has_omitted_fields(), _mission_block(), _PlanItemBuilder, mission.v7 YAML to QGroundControl .plan JSON exporter.  This is the inverse of `, Build a QGC .plan dict and export diagnostics from a mission. (+20 more)

### Community 206 - "fetch_terrain.py"
Cohesion: 0.27
Nodes (9): ModuleType, _axis(), main(), Fetch SRTM terrain elevation and write a terrain.yaml for GridTerrainProvider., _sample_grid(), MonkeyPatch, test_fetch_entrypoint_help_works_without_optional_dependencies(), test_fetch_entrypoint_missing_dependency_has_wheel_install_guidance() (+1 more)

### Community 207 - "fetch_all.py"
Cohesion: 0.31
Nodes (9): _bbox(), main(), Fetch terrain, wind, and landing zones for a mission area in one command.  Write, _time_axis_count(), main(), _object_dict(), _query(), Fetch aeroway landing zones from Overpass API and write a landing_zones.geojson. (+1 more)

### Community 208 - "SKILL.md"
Cohesion: 0.33
Nodes (5): Auto-Clarity, Boundaries, Intensity, Persistence, Rules

### Community 210 - "Q: Review the current uncommitted root-owned integration changes for correctness, security, contract, and test gaps"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Review the current uncommitted root-owned integration changes for correctness, security, contract, and test gaps, Source Nodes

### Community 211 - "RTK - Rust Token Killer (Codex CLI)"
Cohesion: 0.40
Nodes (4): Meta Commands, RTK - Rust Token Killer (Codex CLI), Rule, Verification

### Community 212 - "test_checklist_shows_departure_time_when_set"
Cohesion: 0.60
Nodes (5): Path, test_checklist_shows_departure_time_when_set(), test_geojson_loader_parses_time_window_properties(), _write_json(), _write_yaml()

### Community 213 - "test_numeric_input_safety.py"
Cohesion: 0.50
Nodes (3): test_mission_rejects_boolean_numeric_fields(), test_sora_footprint_rejects_boolean_distances(), test_vehicle_rejects_nonfinite_and_boolean_safety_numbers()

### Community 214 - "_write_obstacle_inputs"
Cohesion: 0.83
Nodes (4): Path, test_obstacle_outputs_surface_clearance_result(), _write_obstacle_inputs(), _write_yaml()

### Community 215 - "test_link_failure_has_full_mission_result_validity"
Cohesion: 0.83
Nodes (4): Path, test_link_failure_has_full_mission_result_validity(), test_resource_failure_has_full_mission_result_validity(), _write_yaml()

## Knowledge Gaps
- **189 isolated node(s):** `bvlos-sim`, `Persistence`, `Rules`, `Intensity`, `Auto-Clarity` (+184 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `VehicleProfile` connect `test_dubins.py` to `cli.py`, `make_vehicle`, `FailureCode`, `InputLoadError`, `run_scenario`, `LegEstimate`, `run_monte_carlo`, `MissionEstimate`, `test_schemas.py`, `test_ardupilot_sitl.py`, `evidence.py`, `MissionPlan`, `try_estimate_mission_distance_time`, `test_tracking_controller.py`, `geofence.py`, `cli_support.py`, `battery_sizer.py`, `test_sitl_live.py`, `ardupilot.py`, `test_contract_golden.py`, `test_sitl_artifacts.py`, `isa_air_density_kgm3`, `test_divert_routing.py`, `fitter.py`, `VehicleProfile`, `test_validation_metrics.py`, `run_stochastic_propagation`, `_SitlComparisonMarkdownRenderer`, `EnergyEstimate`, `ArduPilotSitlAdapter`, `test_qgc_export.py`, `test_numeric_input_safety.py`, `scenario.py`, `_SitlPositionProximityComparator`, `_write_obstacle_inputs`, `sora.py`, `progress_reporter`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `InputDocument` connect `InputDocument` to `cli.py`, `make_vehicle`, `FailureCode`, `InputLoadError`, `test_ardupilot_sitl.py`, `test_checklist_markdown.py`, `evidence.py`, `try_estimate_mission_distance_time`, `cli_support.py`, `wind_grid.py`, `test_sitl_live.py`, `segment_trace`, `test_contract_golden.py`, `size_battery.py`, `test_sitl_artifacts.py`, `geojson_export.py`, `test_sitl_evidence.py`, `test_validation_metrics.py`, `StochasticResultEnvelope`, `FakeMav`, `ArduPilotSitlAdapter`, `test_terrain_altitude.py`, `test_profile_markdown.py`, `tool_version`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `MissionEstimate` connect `ScenarioAssertionResult` to `make_vehicle`, `__init__.py`, `test_geojson_export.py`, `FailureCode`, `run_scenario`, `test_batch.py`, `test_scenario_envelope.py`, `test_dubins.py`, `test_checklist_markdown.py`, `MissionPlan`, `test_time_varying_geofence.py`, `test_tracking_controller.py`, `try_estimate_mission_distance_time`, `test_propagation_units.py`, `cli_support.py`, `battery_sizer.py`, `summary.py`, `uncertainty_envelope.py`, `test_calibration.py`, `validator.py`, `test_contract_golden.py`, `isa_air_density_kgm3`, `test_divert_routing.py`, `enums.py`, `run_stochastic_propagation`, `StochasticResultEnvelope`, `propagator_ekf.py`, `timeline.py`, `test_terrain_altitude.py`, `test_profile_markdown.py`, `scenario.py`, `sora.py`, `tool_version`, `progress_reporter`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `InputDocument` (e.g. with `GeofenceLoadError` and `GeoJsonEntry`) actually correct?**
  _`InputDocument` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `MissionEstimate` (e.g. with `BatteryCapacityRecommendation` and `BatterySizingResult`) actually correct?**
  _`MissionEstimate` has 38 INFERRED edges - model-reasoned connections that need verification._
- **What connects `bvlos-sim`, `Persistence`, `Rules` to the rest of the system?**
  _189 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cli.py` be split into smaller, more focused modules?**
  _Cohesion score 0.04367053620784964 - nodes in this community are weakly interconnected._