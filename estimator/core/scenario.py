"""Public scenario result models for scenario runner v1."""

from pydantic import BaseModel, ConfigDict, Field

from estimator.core.enums import AssertionOutcome, ScenarioStatus
from estimator.core.results import MissionEstimate

# Re-export so callers that already import from this module continue to work.
__all__ = [
    "AssertionOutcome",
    "AssertionFieldValue",
    "CommsLinkPolicyOutcome",
    "ScenarioAssertionResult",
    "ScenarioEventOutcome",
    "ScenarioResult",
    "ScenarioStatus",
    "TimelinePoint",
]

# Canonical field-value type for assertion comparisons.
# bool must come before int/float to avoid bool being subsumed.
AssertionFieldValue = bool | float | str


class TimelinePoint(BaseModel):
    """A point on the deterministic scenario execution timeline.

    Each point represents either the mission-start home position (index 0)
    or the end position of a completed estimator leg.
    """

    model_config = ConfigDict(extra="forbid")

    index: int = Field(description="Zero-based index into the timeline.")
    elapsed_time_s: float = Field(description="Cumulative elapsed time in seconds.")
    lat: float
    lon: float
    altitude_amsl_m: float
    leg_index: int | None = None
    route_item_index: int | None = None
    route_item_id: str | None = None


class CommsLinkPolicyOutcome(BaseModel):
    """Outcome of evaluating a lost-link contingency policy.

    Populated on a ScenarioEventOutcome when a lost_link event fires and a
    LostLinkPolicy is configured in the scenario initial conditions.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(description="Contingency action decided by the policy.")
    loiter_s: float = Field(description="Loiter duration before the action executes.")
    link_lost_at_timeline_index: int = Field(
        description="Timeline index of the point where link loss was resolved."
    )
    link_lost_at_elapsed_s: float = Field(
        description="Elapsed time in seconds at the link-loss timeline point."
    )
    action_at_elapsed_s: float = Field(
        description="Elapsed time when the contingency action would execute."
    )
    action_at_timeline_index: int = Field(
        description="Timeline index of the nearest point at or after action_at_elapsed_s."
    )
    action_lat: float = Field(description="Vehicle latitude at action execution point.")
    action_lon: float = Field(description="Vehicle longitude at action execution point.")
    action_altitude_amsl_m: float = Field(
        description="Vehicle altitude AMSL in metres at action execution point."
    )
    divert_target_id: str | None = Field(
        default=None,
        description="Landing zone ID for divert action, if configured.",
    )


class ScenarioEventOutcome(BaseModel):
    """Outcome of processing a single scenario event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: str
    fired: bool = Field(description="True if the event fired on the timeline.")
    timeline_index: int | None = Field(
        default=None,
        description="Timeline index where the event fired, if fired.",
    )
    unsupported: bool = False
    unsupported_reason: str | None = None
    policy_outcome: CommsLinkPolicyOutcome | None = Field(
        default=None,
        description="Policy outcome when a lost_link event fires with a configured policy.",
    )


class ScenarioAssertionResult(BaseModel):
    """Result of evaluating a single scenario assertion."""

    model_config = ConfigDict(extra="forbid")

    assertion_id: str
    kind: str
    outcome: AssertionOutcome
    message: str
    field_path: str | None = None
    expected: AssertionFieldValue | None = None
    actual: AssertionFieldValue | None = None
    unsupported_reason: str | None = None


class ScenarioResult(BaseModel):
    """Complete deterministic scenario execution result."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    status: ScenarioStatus
    deterministic: bool = True
    timeline: list[TimelinePoint] = Field(default_factory=list)
    event_outcomes: list[ScenarioEventOutcome] = Field(default_factory=list)
    assertion_results: list[ScenarioAssertionResult] = Field(default_factory=list)
    estimate: MissionEstimate | None = None
