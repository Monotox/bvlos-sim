from estimator.core.enums import (
    AssertionOutcome,
    EstimateStatus,
    FailureCode,
    FailureKind,
    ScenarioStatus,
    WarningCode,
)
from estimator.core.results import EnergyEstimate, EstimatorFailure, EstimatorWarning, MissionEstimate
from estimator.core.scenario import (
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
)
from estimator.core.uncertainty import MonteCarloResult, SampledOutputStats
from schemas.stochastic import PropagationTimelinePoint, StochasticPropagationResult
from adapters.summary import (
    format_estimate_summary,
    format_scenario_summary,
    format_stochastic_summary,
    format_uncertainty_summary,
)


def _energy(
    *, reserve_wh: float = 138.2, threshold_wh: float = 100.0
) -> EnergyEstimate:
    return EnergyEstimate(
        is_feasible=reserve_wh >= threshold_wh,
        total_energy_wh=500.0,
        battery_capacity_wh=900.0,
        usable_energy_wh=675.0,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=threshold_wh,
        reserve_at_landing_wh=reserve_wh,
        reserve_at_landing_percent=15.0,
    )


def _warning(code: WarningCode = WarningCode.MAX_WIND_EXCEEDED) -> EstimatorWarning:
    return EstimatorWarning(code=code, message="test warning")


def _estimate(
    *,
    status: EstimateStatus = EstimateStatus.SUCCESS,
    energy: EnergyEstimate | None = None,
    failure: EstimatorFailure | None = None,
    total_time_s: float = 1453.0,
    warnings: list[EstimatorWarning] | None = None,
) -> MissionEstimate:
    return MissionEstimate(
        status=status,
        total_horizontal_distance_m=1000.0,
        total_vertical_distance_m=100.0,
        total_path_distance_m=1100.0,
        total_time_s=total_time_s,
        totals_are_partial=False,
        energy=energy,
        failure=failure,
        warnings=warnings or [],
    )


def _failure(code: FailureCode) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=code,
        message="not feasible",
    )


def _assert_one_line(output: str) -> None:
    assert "\n" not in output
    assert output.strip() == output


def test_feasible_estimate_summary_contains_reserve_and_flight() -> None:
    output = format_estimate_summary(_estimate(energy=_energy()))

    assert output.startswith("FEASIBLE")
    assert "reserve 38.2 %" in output
    assert "flight 24m 13s" in output
    _assert_one_line(output)


def test_infeasible_estimate_summary_ends_with_failure_code() -> None:
    output = format_estimate_summary(
        _estimate(
            status=EstimateStatus.INFEASIBLE,
            energy=_energy(reserve_wh=87.6),
            failure=_failure(FailureCode.RESERVE_BELOW_THRESHOLD),
        )
    )

    assert output.startswith("INFEASIBLE")
    assert "reserve \u221212.4 %" in output
    assert output.endswith("[RESERVE_BELOW_THRESHOLD]")
    _assert_one_line(output)


def test_error_estimate_summary_without_energy_starts_with_error() -> None:
    output = format_estimate_summary(
        _estimate(
            status=EstimateStatus.ERROR,
            energy=None,
            failure=_failure(FailureCode.INVALID_MISSION_PROFILE),
            total_time_s=0.0,
        )
    )

    assert output.startswith("ERROR")
    assert output == "ERROR   [INVALID_MISSION_PROFILE]"
    _assert_one_line(output)


def _assertion(
    assertion_id: str,
    outcome: AssertionOutcome,
    *,
    field_path: str | None = None,
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion_id,
        kind="field_gt",
        outcome=outcome,
        message="ok",
        field_path=field_path,
    )


def _policy_outcome(action: str = "rtl") -> ScenarioEventOutcome:
    return ScenarioEventOutcome(
        event_id="link-lost",
        kind="lost_link",
        fired=True,
        timeline_index=1,
        policy_outcome=CommsLinkPolicyOutcome(
            action=action,
            loiter_s=30.0,
            link_lost_at_timeline_index=1,
            link_lost_at_elapsed_s=40.0,
            action_at_elapsed_s=70.0,
            action_at_timeline_index=2,
            action_lat=52.0,
            action_lon=4.0,
            action_altitude_amsl_m=120.0,
        ),
    )


def test_passed_scenario_summary_starts_with_passed_count() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.PASSED,
        assertion_results=[
            _assertion("estimate-succeeds", AssertionOutcome.PASSED),
            _assertion("energy-ok", AssertionOutcome.PASSED),
        ],
        estimate=_estimate(energy=_energy()),
    )

    output = format_scenario_summary(result)

    assert output.startswith("PASSED 2/2")
    assert "policy" not in output
    _assert_one_line(output)


def test_failed_scenario_summary_ends_with_first_failed_assertion() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.FAILED,
        assertion_results=[
            _assertion("estimate-succeeds", AssertionOutcome.PASSED),
            _assertion(
                "reserve-ok",
                AssertionOutcome.FAILED,
                field_path="estimate.energy.reserve_at_landing_wh",
            ),
        ],
        event_outcomes=[_policy_outcome()],
        estimate=_estimate(energy=_energy(reserve_wh=95.9), total_time_s=1628.0),
    )

    output = format_scenario_summary(result)

    assert output.startswith("FAILED 1/2")
    assert "reserve \u22124.1 %" in output
    assert "flight 27m 08s" in output
    assert "policy RTL" in output
    assert output.endswith("[ASSERTION: estimate.energy.reserve_at_landing_wh]")
    _assert_one_line(output)


def test_passed_scenario_summary_ignores_skipped_assertion_tag() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.PASSED,
        assertion_results=[
            _assertion("estimate-succeeds", AssertionOutcome.PASSED),
            _assertion("optional-check", AssertionOutcome.SKIPPED),
        ],
        estimate=_estimate(energy=_energy()),
    )

    output = format_scenario_summary(result)

    assert output.startswith("PASSED")
    assert "[ASSERTION:" not in output
    _assert_one_line(output)


def test_passed_scenario_summary_shows_unsupported_count_when_nonzero() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.PASSED,
        assertion_results=[
            _assertion("ok", AssertionOutcome.PASSED),
            _assertion("bad-path", AssertionOutcome.UNSUPPORTED),
        ],
        estimate=_estimate(energy=_energy()),
    )

    output = format_scenario_summary(result)

    assert "[1 unsupported]" in output
    assert output.startswith("PASSED 1/2")
    _assert_one_line(output)


def test_error_scenario_summary_shows_error_without_assertion_count() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.ERROR,
        assertion_results=[],
        event_outcomes=[],
        estimate=None,
    )

    output = format_scenario_summary(result)

    assert output == "ERROR"
    _assert_one_line(output)


def test_estimate_summary_includes_warnings_count_when_nonzero() -> None:
    output = format_estimate_summary(
        _estimate(
            energy=_energy(),
            warnings=[_warning(), _warning(WarningCode.LOITER_RADIUS_IGNORED)],
        )
    )

    assert "warnings 2" in output
    _assert_one_line(output)


def test_estimate_summary_omits_warnings_field_when_no_warnings() -> None:
    output = format_estimate_summary(_estimate(energy=_energy()))

    assert "warnings" not in output
    _assert_one_line(output)


def test_scenario_summary_includes_warnings_count_when_nonzero() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.PASSED,
        assertion_results=[_assertion("ok", AssertionOutcome.PASSED)],
        estimate=_estimate(
            energy=_energy(),
            warnings=[_warning()],
        ),
    )

    output = format_scenario_summary(result)

    assert "warnings 1" in output
    _assert_one_line(output)


def test_scenario_summary_omits_warnings_field_when_no_warnings() -> None:
    result = ScenarioResult(
        scenario_id="scenario-1",
        status=ScenarioStatus.PASSED,
        assertion_results=[_assertion("ok", AssertionOutcome.PASSED)],
        estimate=_estimate(energy=_energy()),
    )

    output = format_scenario_summary(result)

    assert "warnings" not in output
    _assert_one_line(output)


# --- Stochastic summary format tests ---


def _stats(mean: float = 850.0) -> SampledOutputStats:
    return SampledOutputStats(
        count=100,
        mean=mean,
        std=20.0,
        min=mean - 60,
        p5=mean - 40,
        p50=mean,
        p95=mean + 40,
        max=mean + 60,
    )


def _timeline_point() -> PropagationTimelinePoint:
    return PropagationTimelinePoint(
        elapsed_time_s=10.0,
        lat_mean=52.0,
        lon_mean=4.0,
        energy_remaining_wh=_stats(),
        p_reserve_violation=0.0,
    )


def _stochastic_result(
    *,
    sample_count: int = 100,
    failed_sample_count: int = 0,
    spatial_infeasible_count: int = 0,
    feasibility_rate: float = 1.0,
    total_time_s: float = 169.0,
    reserve: SampledOutputStats | None = None,
) -> StochasticPropagationResult:
    baseline = _estimate(total_time_s=total_time_s)
    return StochasticPropagationResult(
        propagation_id="test",
        seed=42,
        dt_s=2.0,
        sample_count=sample_count,
        failed_sample_count=failed_sample_count,
        spatial_infeasible_count=spatial_infeasible_count,
        timeline=[_timeline_point()],
        reserve_at_landing_wh=reserve if reserve is not None else _stats(),
        feasibility_rate=feasibility_rate,
        baseline=baseline,
    )


def test_stochastic_summary_contains_feasibility_and_sample_count() -> None:
    output = format_stochastic_summary(_stochastic_result())

    assert "feasible 100%" in output
    assert "n=100" in output
    _assert_one_line(output)


def test_stochastic_summary_omits_failed_field_when_zero() -> None:
    output = format_stochastic_summary(_stochastic_result(failed_sample_count=0))

    assert "failed=" not in output
    _assert_one_line(output)


def test_stochastic_summary_includes_failed_field_when_nonzero() -> None:
    output = format_stochastic_summary(
        _stochastic_result(sample_count=97, failed_sample_count=3)
    )

    assert "failed=3" in output
    _assert_one_line(output)


def test_stochastic_summary_omits_spatial_infeasible_field_when_zero() -> None:
    output = format_stochastic_summary(_stochastic_result(spatial_infeasible_count=0))

    assert "spatial_infeasible=" not in output
    _assert_one_line(output)


def test_stochastic_summary_includes_spatial_infeasible_field_when_nonzero() -> None:
    output = format_stochastic_summary(
        _stochastic_result(
            sample_count=0,
            spatial_infeasible_count=6,
            feasibility_rate=0.0,
        )
    )

    assert "spatial_infeasible=6" in output
    assert "feasible 0%" in output
    _assert_one_line(output)


def test_stochastic_summary_includes_reserve_percentiles() -> None:
    output = format_stochastic_summary(_stochastic_result(reserve=_stats(850.0)))

    assert "p5" in output
    assert "p50" in output
    assert "p95" in output
    _assert_one_line(output)


# --- Uncertainty summary format tests ---


def _mc_result(
    *,
    completed: int = 200,
    failed: int = 0,
    feasibility_rate: float = 1.0,
) -> MonteCarloResult:
    baseline = _estimate(total_time_s=169.0)
    reserve = _stats(850.0)
    return MonteCarloResult(
        uncertainty_id="test",
        seed=42,
        sample_count=completed + failed,
        completed_sample_count=completed,
        failed_sample_count=failed,
        feasibility_rate=feasibility_rate,
        total_time_s=reserve,
        reserve_at_landing_wh=reserve,
        reserve_at_landing_percent=None,
        baseline=baseline,
    )


def test_uncertainty_summary_contains_feasibility_and_sample_count() -> None:
    output = format_uncertainty_summary(_mc_result())

    assert "feasible 100%" in output
    assert "n=200" in output
    _assert_one_line(output)


def test_uncertainty_summary_omits_failed_field_when_zero() -> None:
    output = format_uncertainty_summary(_mc_result(failed=0))

    assert "failed=" not in output
    _assert_one_line(output)


def test_uncertainty_summary_includes_failed_field_when_nonzero() -> None:
    output = format_uncertainty_summary(_mc_result(completed=197, failed=3))

    assert "failed=3" in output
    _assert_one_line(output)
