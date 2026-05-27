"""Single-line summary rendering for estimator and scenario results."""

from collections.abc import Iterable

from estimator.core.enums import (
    AssertionOutcome,
    EstimateStatus,
    FailureCode,
    ScenarioStatus,
)
from estimator.core.results import EnergyEstimate, MissionEstimate, EstimatorWarning
from estimator.core.uncertainty import MonteCarloResult
from schemas.stochastic import StochasticPropagationResult
from estimator.core.scenario import (
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
)

_FIELD_SEPARATOR = "   "
_MINUS_SIGN = "\u2212"
_ESTIMATE_STATUS_LABELS: dict[EstimateStatus, str] = {
    EstimateStatus.SUCCESS: "FEASIBLE",
    EstimateStatus.INFEASIBLE: "INFEASIBLE",
    EstimateStatus.ERROR: "ERROR",
}
_SCENARIO_STATUS_LABELS: dict[ScenarioStatus, str] = {
    ScenarioStatus.PASSED: "PASSED",
    ScenarioStatus.FAILED: "FAILED",
    ScenarioStatus.ERROR: "ERROR",
}


def _join_fields(fields: Iterable[str | None]) -> str:
    return _FIELD_SEPARATOR.join(field for field in fields if field is not None)


def _format_signed_decimal(value: float) -> str:
    formatted = f"{abs(value):.1f}"
    prefix = _MINUS_SIGN if value < 0 else ""
    return f"{prefix}{formatted}"


def _reserve_margin_percent(energy: EnergyEstimate | None) -> float | None:
    if energy is None:
        return None
    if energy.reserve_threshold_wh == 0:
        return None
    return (energy.reserve_at_landing_wh / energy.reserve_threshold_wh - 1) * 100


def _reserve_margin_field(energy: EnergyEstimate | None) -> str | None:
    reserve_margin_pct = _reserve_margin_percent(energy)
    if reserve_margin_pct is None:
        return None
    return f"reserve {_format_signed_decimal(reserve_margin_pct)} %"


def _flight_time_field(total_time_s: float) -> str | None:
    if total_time_s == 0:
        return None
    minutes = int(total_time_s // 60)
    seconds = int(total_time_s % 60)
    return f"flight {minutes}m {seconds:02d}s"


def _estimate_status_label(estimate: MissionEstimate) -> str:
    return _ESTIMATE_STATUS_LABELS.get(estimate.status, "ERROR")


def _failure_code(estimate: MissionEstimate) -> FailureCode | None:
    return estimate.failure.code if estimate.failure is not None else None


def _failure_field(estimate: MissionEstimate) -> str | None:
    code = _failure_code(estimate)
    return f"[{code.name}]" if code is not None else None


def _warnings_field(warnings: list[EstimatorWarning]) -> str | None:
    n = len(warnings)
    return f"warnings {n}" if n > 0 else None


def format_estimate_summary(estimate: MissionEstimate) -> str:
    """Format an estimate as a single summary line."""
    return _join_fields(
        (
            _estimate_status_label(estimate),
            _reserve_margin_field(estimate.energy),
            _flight_time_field(estimate.total_time_s),
            _warnings_field(estimate.warnings),
            _failure_field(estimate),
        )
    )


def _passed_assertion_count(assertions: Iterable[ScenarioAssertionResult]) -> int:
    return sum(assertion.outcome == AssertionOutcome.PASSED for assertion in assertions)


def _scenario_status_field(result: ScenarioResult) -> str:
    status = _SCENARIO_STATUS_LABELS.get(result.status, "FAILED")
    if result.status == ScenarioStatus.ERROR:
        return status
    passed_count = _passed_assertion_count(result.assertion_results)
    total_count = len(result.assertion_results)
    return f"{status} {passed_count}/{total_count}"


def _policy_outcome(
    event_outcomes: Iterable[ScenarioEventOutcome],
) -> CommsLinkPolicyOutcome | None:
    return next(
        (
            outcome.policy_outcome
            for outcome in event_outcomes
            if outcome.policy_outcome is not None
        ),
        None,
    )


def _policy_action_field(result: ScenarioResult) -> str | None:
    policy = _policy_outcome(result.event_outcomes)
    if policy is None:
        return None
    return f"policy {policy.action.upper()}"


def _first_failed_assertion(
    assertions: Iterable[ScenarioAssertionResult],
) -> ScenarioAssertionResult | None:
    return next(
        (
            assertion
            for assertion in assertions
            if assertion.outcome == AssertionOutcome.FAILED
        ),
        None,
    )


def _unsupported_assertion_field(assertions: Iterable[ScenarioAssertionResult]) -> str | None:
    count = sum(a.outcome == AssertionOutcome.UNSUPPORTED for a in assertions)
    return f"[{count} unsupported]" if count > 0 else None


def _failed_assertion_field(result: ScenarioResult) -> str | None:
    assertion = _first_failed_assertion(result.assertion_results)
    if assertion is None:
        return None
    assertion_field = assertion.field_path or assertion.assertion_id
    return f"[ASSERTION: {assertion_field}]"


def _estimate_fields(estimate: MissionEstimate | None) -> tuple[str | None, str | None]:
    if estimate is None:
        return None, None
    return (
        _reserve_margin_field(estimate.energy),
        _flight_time_field(estimate.total_time_s),
    )


def format_uncertainty_summary(result: MonteCarloResult) -> str:
    """Format a Monte Carlo result as a single summary line."""
    feasibility = result.feasibility_rate
    feasibility_field = (
        f"feasible {feasibility * 100:.0f}%" if feasibility is not None else None
    )
    reserve = result.reserve_at_landing_wh
    reserve_field: str | None = None
    if reserve is not None:
        reserve_field = (
            f"reserve p5 {reserve.p5:.1f} Wh   p50 {reserve.p50:.1f} Wh"
            f"   p95 {reserve.p95:.1f} Wh"
        )
    time_field: str | None = None
    if result.total_time_s is not None:
        minutes = int(result.total_time_s.p50 // 60)
        seconds = int(result.total_time_s.p50 % 60)
        time_field = f"time p50 {minutes}m {seconds:02d}s"
    samples_field = f"n={result.completed_sample_count}"
    failed_field = (
        f"failed={result.failed_sample_count}" if result.failed_sample_count > 0 else None
    )
    return _join_fields((feasibility_field, reserve_field, time_field, samples_field, failed_field))


def format_stochastic_summary(result: StochasticPropagationResult) -> str:
    """Format a stochastic propagation result as a single summary line."""
    feasibility_field = f"feasible {result.feasibility_rate * 100:.0f}%"
    reserve = result.reserve_at_landing_wh
    reserve_field: str | None = None
    if reserve is not None:
        reserve_field = (
            f"reserve p5 {reserve.p5:.1f} Wh   p50 {reserve.p50:.1f} Wh"
            f"   p95 {reserve.p95:.1f} Wh"
        )
    time_field: str | None = None
    total_time = result.baseline.total_time_s
    if total_time:
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        time_field = f"time {minutes}m {seconds:02d}s"
    samples_field = f"n={result.sample_count}"
    failed_field = (
        f"failed={result.failed_sample_count}" if result.failed_sample_count > 0 else None
    )
    spatial_field = (
        f"spatial_infeasible={result.spatial_infeasible_count}"
        if result.spatial_infeasible_count > 0
        else None
    )
    return _join_fields(
        (feasibility_field, reserve_field, time_field, samples_field, failed_field, spatial_field)
    )


def format_scenario_summary(result: ScenarioResult) -> str:
    """Format a scenario result as a single summary line."""
    reserve_field, flight_time_field = _estimate_fields(result.estimate)
    warnings = result.estimate.warnings if result.estimate is not None else []
    return _join_fields(
        (
            _scenario_status_field(result),
            reserve_field,
            flight_time_field,
            _warnings_field(warnings),
            _policy_action_field(result),
            _failed_assertion_field(result),
            _unsupported_assertion_field(result.assertion_results),
        )
    )
