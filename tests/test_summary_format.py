from estimator.core.enums import (
    AssertionOutcome,
    EstimateStatus,
    FailureCode,
    FailureKind,
    ScenarioStatus,
)
from estimator.core.results import EnergyEstimate, EstimatorFailure, MissionEstimate
from estimator.core.scenario import (
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
)
from adapters.summary import format_estimate_summary, format_scenario_summary


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


def _estimate(
    *,
    status: EstimateStatus = EstimateStatus.SUCCESS,
    energy: EnergyEstimate | None = None,
    failure: EstimatorFailure | None = None,
    total_time_s: float = 1453.0,
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
    assert "policy NONE" in output
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
