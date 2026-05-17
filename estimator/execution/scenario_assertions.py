"""Assertion evaluation for scenario runner v1."""

import math
from collections.abc import Callable
from typing import cast

from estimator.core.enums import AssertionOutcome, EstimateStatus
from estimator.core.results import MissionEstimate
from estimator.core.scenario import (
    AssertionFieldValue,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioStatus,
)
from schemas.scenario import (
    FIELD_ASSERTION_KINDS,
    ScenarioAssertion,
    ScenarioAssertionKind,
)

# ---------------------------------------------------------------------------
# Supported field paths and resolvers
# ---------------------------------------------------------------------------

_SUPPORTED_FIELD_PATHS: frozenset[str] = frozenset(
    {
        "estimate.status",
        "estimate.total_time_s",
        "estimate.total_horizontal_distance_m",
        "estimate.total_vertical_distance_m",
        "estimate.total_path_distance_m",
        "estimate.energy.is_feasible",
        "estimate.energy.reserve_at_landing_percent",
        "estimate.energy.reserve_at_landing_wh",
        "estimate.resource.is_feasible",
        "estimate.link.is_feasible",
        "estimate.geofence.is_feasible",
        "estimate.landing_zone.is_feasible",
    }
)

FieldResolver = Callable[[MissionEstimate], AssertionFieldValue | None]

_FIELD_RESOLVERS: dict[str, FieldResolver] = {
    "estimate.status": lambda e: str(e.status),
    "estimate.total_time_s": lambda e: e.total_time_s,
    "estimate.total_horizontal_distance_m": lambda e: e.total_horizontal_distance_m,
    "estimate.total_vertical_distance_m": lambda e: e.total_vertical_distance_m,
    "estimate.total_path_distance_m": lambda e: e.total_path_distance_m,
    "estimate.energy.is_feasible": lambda e: (
        e.energy.is_feasible if e.energy is not None else None
    ),
    "estimate.energy.reserve_at_landing_percent": lambda e: (
        e.energy.reserve_at_landing_percent if e.energy is not None else None
    ),
    "estimate.energy.reserve_at_landing_wh": lambda e: (
        e.energy.reserve_at_landing_wh if e.energy is not None else None
    ),
    "estimate.resource.is_feasible": lambda e: (
        e.resource.is_feasible if e.resource is not None else None
    ),
    "estimate.link.is_feasible": lambda e: (
        e.link.is_feasible if e.link is not None else None
    ),
    "estimate.geofence.is_feasible": lambda e: (
        e.geofence.is_feasible if e.geofence is not None else None
    ),
    "estimate.landing_zone.is_feasible": lambda e: (
        e.landing_zone.is_feasible if e.landing_zone is not None else None
    ),
}

NumericComparator = Callable[[float, float], bool]

_NUMERIC_COMPARATORS: dict[ScenarioAssertionKind, NumericComparator] = {
    ScenarioAssertionKind.FIELD_LT: lambda a, e: a < e,
    ScenarioAssertionKind.FIELD_GT: lambda a, e: a > e,
    ScenarioAssertionKind.FIELD_LE: lambda a, e: a <= e,
    ScenarioAssertionKind.FIELD_GE: lambda a, e: a >= e,
}
_ASSERTION_FLOAT_DECIMAL_PLACES = 8


# ---------------------------------------------------------------------------
# Field resolution
# ---------------------------------------------------------------------------


def resolve_field_value(
    field_path: str, estimate: MissionEstimate | None
) -> AssertionFieldValue | None:
    if estimate is None:
        return None
    resolver = _FIELD_RESOLVERS.get(field_path)
    if resolver is None:
        return None
    return resolver(estimate)


# ---------------------------------------------------------------------------
# Assertion result builders
# ---------------------------------------------------------------------------


def _passed(
    assertion: ScenarioAssertion,
    message: str,
    *,
    field_path: str | None = None,
    expected: AssertionFieldValue | None = None,
    actual: AssertionFieldValue | None = None,
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.PASSED,
        message=message,
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _failed(
    assertion: ScenarioAssertion,
    message: str,
    *,
    expected: AssertionFieldValue | None = None,
    actual: AssertionFieldValue | None = None,
    field_path: str | None = None,
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.FAILED,
        message=message,
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _skipped(assertion: ScenarioAssertion, message: str) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.SKIPPED,
        message=message,
        field_path=assertion.field_path,
        expected=assertion.expected,
    )


def _unsupported(assertion: ScenarioAssertion, reason: str) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.UNSUPPORTED,
        message=f"Assertion is not supported: {reason}",
        field_path=assertion.field_path,
        unsupported_reason=reason,
    )


# ---------------------------------------------------------------------------
# Assertion evaluators
# ---------------------------------------------------------------------------


def _evaluate_estimate_succeeds(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    if estimate is None:
        return _failed(
            assertion, "Estimate is None; estimation did not produce a result."
        )
    if estimate.status == EstimateStatus.SUCCESS:
        return _passed(assertion, f"Estimate status is '{estimate.status}' (success).")
    return _failed(
        assertion,
        f"Estimate status is '{estimate.status}', expected 'success'.",
        field_path="estimate.status",
        expected="success",
        actual=str(estimate.status),
    )


def _evaluate_estimate_fails(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    if estimate is None:
        return _passed(
            assertion, "Estimate is None; estimation did not produce a result."
        )
    if estimate.status != EstimateStatus.SUCCESS:
        return _passed(
            assertion, f"Estimate status is '{estimate.status}' (not success)."
        )
    return _failed(
        assertion,
        "Estimate status is 'success', expected a non-success status.",
        field_path="estimate.status",
        expected="<not success>",
        actual=str(estimate.status),
    )


def _is_numeric_value(value: AssertionFieldValue) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_assertion_value(value: AssertionFieldValue) -> str:
    if isinstance(value, float) and math.isfinite(value):
        rounded = round(value, _ASSERTION_FLOAT_DECIMAL_PLACES)
        return repr(0.0 if rounded == 0.0 else rounded)
    return repr(value)


def _evaluate_eq_assertion(
    assertion: ScenarioAssertion,
    actual: AssertionFieldValue,
    expected: AssertionFieldValue,
    field_path: str,
) -> ScenarioAssertionResult:
    def values_equal(a: AssertionFieldValue, e: AssertionFieldValue) -> bool:
        if isinstance(e, bool) and isinstance(a, bool):
            return a == e
        if isinstance(e, (int, float)) and isinstance(a, (int, float)):
            return a == e
        if isinstance(a, str) and isinstance(e, str):
            return a == e
        return False

    if values_equal(actual, expected):
        return _passed(
            assertion,
            f"'{field_path}' == {_format_assertion_value(expected)} "
            f"(actual: {_format_assertion_value(actual)}).",
            field_path=field_path,
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"'{field_path}' expected {_format_assertion_value(expected)} "
        f"but was {_format_assertion_value(actual)}.",
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _evaluate_numeric_assertion(
    assertion: ScenarioAssertion,
    actual: AssertionFieldValue,
    expected: AssertionFieldValue,
    field_path: str,
) -> ScenarioAssertionResult:
    if not _is_numeric_value(actual):
        reason = (
            f"Field '{field_path}' has a non-numeric value; "
            f"cannot apply '{assertion.kind}' comparison."
        )
        return _unsupported(assertion, reason)
    if not _is_numeric_value(expected):
        reason = (
            f"Expected value {expected!r} is not numeric; "
            f"cannot apply '{assertion.kind}' comparison."
        )
        return _unsupported(assertion, reason)

    comparator = _NUMERIC_COMPARATORS[assertion.kind]
    if comparator(cast(float, actual), cast(float, expected)):
        return _passed(
            assertion,
            f"'{field_path}' {assertion.kind} "
            f"{_format_assertion_value(expected)} satisfied "
            f"(actual: {_format_assertion_value(actual)}).",
            field_path=field_path,
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"'{field_path}' {assertion.kind} "
        f"{_format_assertion_value(expected)} not satisfied "
        f"(actual: {_format_assertion_value(actual)}).",
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _evaluate_field_assertion(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    field_path = cast(str, assertion.field_path)

    if field_path not in _SUPPORTED_FIELD_PATHS:
        reason = (
            f"Field path '{field_path}' is not supported in scenario.v1. "
            "See docs for supported field paths."
        )
        return _unsupported(assertion, reason)

    actual = resolve_field_value(field_path, estimate)
    if actual is None:
        return _skipped(
            assertion,
            f"Field '{field_path}' is not available in the estimate result.",
        )

    expected = cast(AssertionFieldValue, assertion.expected)

    if assertion.kind == ScenarioAssertionKind.FIELD_EQ:
        return _evaluate_eq_assertion(assertion, actual, expected, field_path)

    return _evaluate_numeric_assertion(assertion, actual, expected, field_path)


def _evaluate_policy_action_eq(
    assertion: ScenarioAssertion,
    event_outcomes: list[ScenarioEventOutcome],
) -> ScenarioAssertionResult:
    event_id = cast(str, assertion.event_id)
    outcome = next((o for o in event_outcomes if o.event_id == event_id), None)
    if outcome is None:
        return _skipped(
            assertion,
            f"No event with id '{event_id}' found in event outcomes.",
        )
    if not outcome.fired:
        return _skipped(assertion, f"Event '{event_id}' did not fire.")
    if outcome.policy_outcome is None:
        return _skipped(
            assertion,
            f"Event '{event_id}' has no policy outcome; no lost_link_policy configured.",
        )
    actual: AssertionFieldValue = outcome.policy_outcome.action
    expected: AssertionFieldValue = str(assertion.expected)
    if actual == expected:
        return _passed(
            assertion,
            f"Policy action for event '{event_id}' is '{actual}' as expected.",
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"Policy action for event '{event_id}' is '{actual}', expected '{expected}'.",
        expected=expected,
        actual=actual,
    )


_ASSERTION_EVALUATORS: dict[
    ScenarioAssertionKind,
    Callable[[ScenarioAssertion, MissionEstimate | None], ScenarioAssertionResult],
] = {
    ScenarioAssertionKind.ESTIMATE_SUCCEEDS: _evaluate_estimate_succeeds,
    ScenarioAssertionKind.ESTIMATE_FAILS: _evaluate_estimate_fails,
    **{kind: _evaluate_field_assertion for kind in FIELD_ASSERTION_KINDS},
}

PolicyEvaluator = Callable[
    [ScenarioAssertion, list[ScenarioEventOutcome]], ScenarioAssertionResult
]

_POLICY_EVALUATORS: dict[ScenarioAssertionKind, PolicyEvaluator] = {
    ScenarioAssertionKind.POLICY_ACTION_EQ: _evaluate_policy_action_eq,
}


def evaluate_assertion(
    assertion: ScenarioAssertion,
    estimate: MissionEstimate | None,
    event_outcomes: list[ScenarioEventOutcome],
) -> ScenarioAssertionResult:
    policy_evaluator = _POLICY_EVALUATORS.get(assertion.kind)
    if policy_evaluator is not None:
        return policy_evaluator(assertion, event_outcomes)
    evaluator = _ASSERTION_EVALUATORS.get(assertion.kind)
    if evaluator is None:
        return _unsupported(
            assertion,
            f"Assertion kind '{assertion.kind}' is not handled in scenario.v1.",
        )
    return evaluator(assertion, estimate)


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------


def determine_scenario_status(
    assertion_results: list[ScenarioAssertionResult],
) -> ScenarioStatus:
    any_failed = any(r.outcome == AssertionOutcome.FAILED for r in assertion_results)
    return ScenarioStatus.FAILED if any_failed else ScenarioStatus.PASSED
