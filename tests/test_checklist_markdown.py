"""Tests for the pre-flight go/no-go checklist renderer."""

from pathlib import Path

from adapters.checklist_markdown import (
    render_checklist_markdown,
    render_checklist_markdown_from_scenario,
)
from adapters.cli import CliExitCode, app
from adapters.envelope import (
    DeterminismMetadata,
    EnvelopeInputs,
    EstimatorResultEnvelope,
    ProvenanceInput,
    build_estimator_envelope,
)
from adapters.io import InputDocument, InputLoadError, InputLoadStage
from estimator.core.enums import (
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    LegPhase,
    ScenarioStatus,
    WarningCode,
)
from estimator.core.results import (
    EnergyEstimate,
    EnergyLegEstimate,
    EstimatorWarning,
    GeofenceEstimate,
    GroundRiskEstimate,
    GroundRiskLegEstimate,
    LandingZoneEstimate,
    LandingZoneStateReachability,
    LinkEstimate,
    LinkSystemEstimate,
    LegEstimate,
    MissionEstimate,
    ObstacleEstimate,
    ResourceEstimate,
    ResourceSystemEstimate,
    RthReserveTimelinePoint,
    WeatherEstimate,
)
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _det_meta() -> DeterminismMetadata:
    return DeterminismMetadata(
        deterministic=True,
        randomness_used=False,
        external_network_access_used=False,
        canonical_json=True,
        canonical_json_sort_keys=True,
    )


def _prov_input() -> ProvenanceInput:
    return ProvenanceInput(format="yaml", sha256="abc123")


def _estimate(
    *,
    status: EstimateStatus = EstimateStatus.SUCCESS,
    energy: EnergyEstimate | None = None,
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
    warnings: list[EstimatorWarning] | None = None,
    metadata: dict | None = None,
) -> MissionEstimate:
    return MissionEstimate(
        status=status,
        total_horizontal_distance_m=1000.0,
        total_vertical_distance_m=100.0,
        total_path_distance_m=1100.0,
        total_time_s=1200.0,
        totals_are_partial=False,
        energy=energy,
        geofence=geofence,
        landing_zone=landing_zone,
        warnings=warnings or [],
        metadata=metadata or {},
    )


def _fake_doc(name: str) -> InputDocument:
    return InputDocument(path=Path(f"{name}.yaml"), format="yaml", sha256="abc123")


def _envelope(result: MissionEstimate | None = None) -> EstimatorResultEnvelope:
    if result is None:
        result = _estimate()
    return build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(
            mission=_fake_doc("mission"), vehicle=_fake_doc("vehicle")
        ),
    )


def _energy(
    *,
    reserve_wh: float = 250.0,
    threshold_wh: float = 200.0,
) -> EnergyEstimate:
    return EnergyEstimate(
        is_feasible=reserve_wh >= threshold_wh,
        total_energy_wh=500.0,
        battery_capacity_wh=900.0,
        usable_energy_wh=675.0,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=threshold_wh,
        reserve_at_landing_wh=reserve_wh,
        reserve_at_landing_percent=reserve_wh / 900.0 * 100.0,
    )


def _geofence(*, is_feasible: bool = True, conflicts: int = 0) -> GeofenceEstimate:
    from estimator.core.results import GeofenceConflict

    conflict_list = [
        GeofenceConflict(
            code=FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE,
            message="route enters forbidden zone",
            zone_id=f"zone-{i}",
            zone_kind="forbidden",
            leg_index=0,
            route_item_index=0,
        )
        for i in range(conflicts)
    ]
    return GeofenceEstimate(
        is_feasible=is_feasible,
        checked_zone_count=2,
        checked_leg_count=3,
        conflicts=conflict_list,
    )


def _lz_state(i: int, *, reachable: bool = True) -> LandingZoneStateReachability:
    return LandingZoneStateReachability(
        state_index=i,
        leg_index=i,
        route_item_index=i,
        lat=52.0,
        lon=4.0,
        altitude_amsl_m=100.0,
        reachable_zone_id=f"lz-{i}" if reachable else None,
        energy_remaining_before_divert_wh=300.0,
        is_reachable=reachable,
        reserve_ok=reachable,
    )


def _landing_zone(
    *,
    is_feasible: bool = True,
    checked_states: int = 3,
    reachable_states: int | None = None,
) -> LandingZoneEstimate:
    if reachable_states is None:
        reachable_states = checked_states if is_feasible else max(0, checked_states - 1)

    states = [
        _lz_state(i, reachable=i < reachable_states) for i in range(checked_states)
    ]
    return LandingZoneEstimate(
        is_feasible=is_feasible,
        checked_zone_count=2,
        checked_state_count=checked_states,
        states=states,
        max_allowed_distance_m=500.0,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=200.0,
    )


# ---------------------------------------------------------------------------
# Unit tests for render_checklist_markdown
# ---------------------------------------------------------------------------


def test_checklist_header_contains_mission_id() -> None:
    output = render_checklist_markdown(
        _envelope(_estimate()), mission_id="pipeline_survey_001"
    )
    assert "## Pre-Flight Checklist: pipeline_survey_001" in output


def test_checklist_default_mission_id_shows_mission() -> None:
    output = render_checklist_markdown(_envelope(_estimate()))
    assert "## Pre-Flight Checklist:" in output


def test_checklist_all_pass_shows_go() -> None:
    result = _complete_estimate()
    output = render_checklist_markdown(_envelope(result))
    assert "Status: GO" in output


def test_checklist_error_status_cannot_go_without_failure_object() -> None:
    result = _complete_estimate().model_copy(
        update={"status": EstimateStatus.ERROR, "failure": None}
    )
    output = render_checklist_markdown(_envelope(result))
    assert "Status: NO-GO" in output


def test_checklist_partial_or_incomplete_coverage_cannot_go() -> None:
    partial = _complete_estimate().model_copy(update={"totals_are_partial": True})
    assert "Status: NO-GO" in render_checklist_markdown(_envelope(partial))

    incomplete = _complete_estimate()
    assert incomplete.geofence is not None
    incomplete = incomplete.model_copy(
        update={
            "geofence": incomplete.geofence.model_copy(update={"checked_leg_count": 0})
        }
    )
    assert "Status: NO-GO" in render_checklist_markdown(_envelope(incomplete))


def test_checklist_energy_fail_shows_no_go() -> None:
    result = _estimate(energy=_energy(reserve_wh=50.0, threshold_wh=200.0))
    output = render_checklist_markdown(_envelope(result))
    assert "Status: NO-GO" in output
    assert "FAIL" in output


def test_checklist_geofence_fail_shows_no_go() -> None:
    result = _estimate(geofence=_geofence(is_feasible=False, conflicts=2))
    output = render_checklist_markdown(_envelope(result))
    assert "Status: NO-GO" in output
    assert "2 conflict(s)" in output


def test_checklist_landing_zone_fail_shows_no_go() -> None:
    result = _estimate(
        landing_zone=_landing_zone(
            is_feasible=False, checked_states=5, reachable_states=4
        )
    )
    output = render_checklist_markdown(_envelope(result))
    assert "Status: NO-GO" in output
    assert "1/5" in output


def test_checklist_missing_energy_shows_na() -> None:
    result = _estimate(energy=None)
    output = render_checklist_markdown(_envelope(result))
    assert "◌" in output
    assert "N/A" in output
    assert "Energy feasibility" in output


def test_checklist_no_warnings_shows_none() -> None:
    result = _estimate(energy=_energy())
    output = render_checklist_markdown(_envelope(result))
    assert "NONE" in output


def test_checklist_warnings_shows_count_and_code() -> None:
    result = _estimate(
        energy=_energy(),
        warnings=[
            EstimatorWarning(
                code=WarningCode.MAX_WIND_EXCEEDED, message="wind too high"
            ),
            EstimatorWarning(
                code=WarningCode.LOITER_RADIUS_IGNORED, message="radius ignored"
            ),
        ],
    )
    output = render_checklist_markdown(_envelope(result))
    assert "Advisory warnings" in output
    assert "MAX_WIND_EXCEEDED" in output
    assert "2" in output


def test_checklist_many_warnings_truncated() -> None:
    result = _estimate(
        energy=_energy(),
        warnings=[
            EstimatorWarning(code=WarningCode.MAX_WIND_EXCEEDED, message=f"w{i}")
            for i in range(8)
        ],
    )
    output = render_checklist_markdown(_envelope(result))
    assert "+ 3 more" in output


def test_checklist_warning_blocks_go() -> None:
    result = _complete_estimate(
        warnings=[
            EstimatorWarning(
                code=WarningCode.MAX_WIND_EXCEEDED,
                message="wind limit evidence is incomplete",
            )
        ]
    )

    output = render_checklist_markdown(_envelope(result))

    assert "Status: NO-GO" in output


def test_checklist_missing_operational_evidence_blocks_go() -> None:
    result = _complete_estimate().model_copy(update={"link": None})

    output = render_checklist_markdown(_envelope(result))

    assert "Link availability" in output
    assert "N/A" in output
    assert "Status: NO-GO" in output


def test_checklist_no_result_shows_no_go() -> None:
    from adapters.envelope import build_invalid_input_envelope

    error = InputLoadError(
        "Mission file not found",
        input_name="mission",
        path=Path("missing.yaml"),
        stage=InputLoadStage.READ,
    )
    envelope = build_invalid_input_envelope(
        error=error,
        mission_document=None,
        vehicle_document=None,
    )
    output = render_checklist_markdown(envelope)
    assert "Status: NO-GO" in output


def test_checklist_energy_detail_shows_margin() -> None:
    result = _estimate(energy=_energy(reserve_wh=300.0, threshold_wh=200.0))
    output = render_checklist_markdown(_envelope(result), mission_id="demo")
    assert "100" in output  # margin = 300 - 200
    assert "300" in output  # reserve_at_landing_wh


def _rth_point(leg_index: int, *, feasible: bool) -> RthReserveTimelinePoint:
    margin = 50.0 if feasible else -25.0
    return RthReserveTimelinePoint(
        leg_index=leg_index,
        route_item_index=leg_index,
        route_item_id=f"wp-{leg_index}",
        rth_distance_m=1000.0,
        rth_energy_wh=100.0,
        energy_remaining_before_rth_wh=400.0,
        reserve_after_rth_wh=200.0 + margin,
        reserve_margin_wh=margin,
        is_feasible=feasible,
    )


def _complete_estimate(
    *,
    energy: EnergyEstimate | None = None,
    rth_is_feasible: bool = True,
    warnings: list[EstimatorWarning] | None = None,
) -> MissionEstimate:
    leg = LegEstimate(
        leg_index=0,
        route_item_index=0,
        route_item_id="wp-1",
        action="waypoint",
        phase=LegPhase.TRANSIT,
        start_lat=52.0,
        start_lon=4.0,
        start_alt_amsl_m=100.0,
        end_lat=52.001,
        end_lon=4.001,
        end_alt_amsl_m=100.0,
        horizontal_distance_m=1000.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=1000.0,
        time_s=1200.0,
    )
    energy_leg = EnergyLegEstimate(
        leg_index=0,
        route_item_index=0,
        route_item_id="wp-1",
        phase=LegPhase.TRANSIT,
        time_s=1200.0,
        power_w=500.0,
        power_source=EnergyPowerSource.CRUISE_POWER,
        energy_wh=500.0,
    )
    resolved_energy = energy or _energy().model_copy(
        update={
            "legs": [energy_leg],
            "rth_reserve_timeline": [_rth_point(0, feasible=True)],
        }
    )
    if not resolved_energy.legs:
        resolved_energy = resolved_energy.model_copy(update={"legs": [energy_leg]})
    return _estimate(
        energy=resolved_energy,
        geofence=_geofence().model_copy(update={"checked_leg_count": 1}),
        landing_zone=_landing_zone(),
        warnings=warnings,
    ).model_copy(
        update={
            "legs": [leg],
            "rth_is_feasible": rth_is_feasible,
            "resource": ResourceEstimate(
                is_feasible=True,
                selected_resource_id="battery",
                total_demand_wh=500.0,
                peak_power_w=800.0,
                route_distance_m=1_100.0,
                route_time_s=1_200.0,
                max_observed_home_distance_m=500.0,
                systems=[
                    ResourceSystemEstimate(
                        resource_id="battery",
                        kind="battery",
                        priority=0,
                        is_feasible=True,
                        demand_energy_wh=500.0,
                        available_energy_wh=900.0,
                        reserve_threshold_wh=200.0,
                        reserve_after_resource_wh=250.0,
                        peak_power_w=800.0,
                        route_distance_m=1_100.0,
                        route_time_s=1_200.0,
                        max_observed_home_distance_m=500.0,
                    )
                ],
            ),
            "link": LinkEstimate(
                is_feasible=True,
                selected_link_id="primary",
                required_link_count=1,
                available_link_count=1,
                max_observed_range_m=500.0,
                systems=[
                    LinkSystemEstimate(
                        link_id="primary",
                        kind="direct",
                        required=True,
                        priority=0,
                        is_feasible=True,
                        availability="available",
                        max_observed_range_m=500.0,
                    )
                ],
            ),
            "obstacle": ObstacleEstimate(
                is_feasible=True,
                checked_obstacle_count=1,
                checked_leg_count=1,
            ),
            "weather": WeatherEstimate(
                is_feasible=True,
                checked_leg_count=1,
                worst_wind_speed_mps=5.0,
            ),
            "ground_risk": GroundRiskEstimate(
                characteristic_dimension_m=2.0,
                max_speed_mps=25.0,
                sora_version="2.5",
                mission_igrc=3,
                legs=[
                    GroundRiskLegEstimate(
                        leg_index=0,
                        route_item_id="wp-1",
                        max_density_ppl_km2=12.0,
                        igrc=3,
                    )
                ],
            ),
        }
    )


def test_checklist_rth_feasible_is_a_required_pass() -> None:
    energy = _energy().model_copy(
        update={
            "rth_reserve_timeline": [
                _rth_point(0, feasible=True),
                _rth_point(1, feasible=True),
            ]
        }
    )
    result = _complete_estimate(energy=energy)
    output = render_checklist_markdown(_envelope(result))
    assert "RTH reserve (advisory)" not in output
    assert "RTH reserve" in output
    assert "PASS" in output
    assert "all 2 leg(s)" in output
    assert "Status: GO" in output


def test_checklist_external_power_reports_rth_feasibility() -> None:
    result = _complete_estimate().model_copy(
        update={
            "resource": ResourceEstimate(
                is_feasible=True,
                selected_resource_id="fiber-power",
                total_demand_wh=500.0,
                peak_power_w=800.0,
                route_distance_m=1_100.0,
                route_time_s=1_200.0,
                max_observed_home_distance_m=500.0,
                systems=[
                    ResourceSystemEstimate(
                        resource_id="fiber-power",
                        kind="external_power",
                        priority=0,
                        is_feasible=True,
                        demand_energy_wh=500.0,
                        peak_power_w=800.0,
                        available_power_w=2_000.0,
                        route_distance_m=1_100.0,
                        route_time_s=1_200.0,
                        max_observed_home_distance_m=500.0,
                    )
                ],
            )
        }
    )

    output = render_checklist_markdown(_envelope(result))

    assert "RTH feasibility" in output
    assert "external resource covers RTH peak power" in output
    assert "Status: GO" in output


def test_checklist_rth_infeasible_shows_first_failing_leg() -> None:
    energy = _energy().model_copy(
        update={
            "rth_reserve_timeline": [
                _rth_point(0, feasible=True),
                _rth_point(1, feasible=False),
            ]
        }
    )
    result = _complete_estimate(energy=energy, rth_is_feasible=False)
    output = render_checklist_markdown(_envelope(result))
    assert "RTH reserve (advisory)" not in output
    assert "first at leg 1" in output
    assert "Status: NO-GO" in output


def test_checklist_rth_infeasible_without_timeline_details_fails_closed() -> None:
    energy = _energy().model_copy(update={"rth_reserve_timeline": []})
    result = _complete_estimate(energy=energy, rth_is_feasible=False)

    output = render_checklist_markdown(_envelope(result))

    assert "details unavailable" in output
    assert "Status: NO-GO" in output


def test_checklist_optional_unavailable_links_cannot_go() -> None:
    result = _complete_estimate().model_copy(
        update={
            "link": LinkEstimate(
                is_feasible=True,
                selected_link_id=None,
                required_link_count=0,
                available_link_count=0,
                max_observed_range_m=500.0,
            )
        }
    )

    output = render_checklist_markdown(_envelope(result))

    assert "no configured link is available" in output
    assert "Status: NO-GO" in output


def test_checklist_rth_gate_failure_blocks_go() -> None:
    energy = _energy().model_copy(
        update={
            "rth_reserve_timeline": [
                _rth_point(0, feasible=True),
                _rth_point(1, feasible=False),
            ]
        }
    )
    result = _complete_estimate(energy=energy, rth_is_feasible=False)

    output = render_checklist_markdown(_envelope(result))

    assert "RTH reserve (advisory)" not in output
    assert "RTH reserve" in output
    assert "FAIL" in output
    assert "Status: NO-GO" in output


def test_checklist_rth_gate_feasible_passes_without_blocking_go() -> None:
    energy = _energy().model_copy(
        update={
            "rth_reserve_timeline": [
                _rth_point(0, feasible=True),
                _rth_point(1, feasible=True),
            ]
        }
    )
    result = _complete_estimate(energy=energy)

    output = render_checklist_markdown(_envelope(result))

    assert "RTH reserve (advisory)" not in output
    assert "RTH reserve" in output
    assert "PASS" in output
    assert "Status: GO" in output


def test_checklist_omits_rth_row_when_not_computed() -> None:
    result = _estimate(energy=_energy())
    output = render_checklist_markdown(_envelope(result))
    assert "RTH reserve" not in output


def test_checklist_ends_with_newline() -> None:
    output = render_checklist_markdown(_envelope(_estimate()))
    assert output.endswith("\n")


# ---------------------------------------------------------------------------
# render_checklist_markdown_from_scenario
# ---------------------------------------------------------------------------


def test_checklist_from_scenario_uses_scenario_id() -> None:
    from adapters.scenario_envelope import build_scenario_envelope
    from estimator.core.scenario import ScenarioResult

    result = ScenarioResult(
        scenario_id="my_scenario_001",
        status=ScenarioStatus.PASSED,
        assertion_results=[],
        event_outcomes=[],
        estimate=_complete_estimate(),
    )
    envelope = build_scenario_envelope(
        result=result,
        scenario_document=_fake_doc("scenario"),
        mission_document=_fake_doc("mission"),
        vehicle_document=_fake_doc("vehicle"),
    )
    output = render_checklist_markdown_from_scenario(envelope)
    assert "## Pre-Flight Checklist: my_scenario_001" in output
    assert "Status: GO" in output


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_estimate_checklist_fails_closed_without_required_evidence() -> None:
    result = _runner.invoke(
        app,
        [
            "estimate",
            str(REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"),
            str(REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"),
            "--format",
            "checklist",
        ],
    )
    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "## Pre-Flight Checklist:" in result.output
    assert "Status: NO-GO" in result.output


def test_estimate_checklist_format_shows_no_go_for_infeasible_mission() -> None:
    result = _runner.invoke(
        app,
        [
            "estimate",
            str(REPO_ROOT / "examples/real_world/alpine_infeasible.yaml"),
            str(REPO_ROOT / "examples/real_world/quadplane_small_battery.yaml"),
            "--format",
            "checklist",
        ],
    )
    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "Status: NO-GO" in result.output
    assert "FAIL" in result.output
