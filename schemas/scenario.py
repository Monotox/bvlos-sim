"""Scenario plan schema for deterministic scenario runner (scenario.v1)."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.mission import WindLayerConfig

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LostLinkAction(StrEnum):
    """Contingency action executed when the comms link is lost."""

    RTL = "rtl"
    LAND = "land"
    LOITER = "loiter"
    DIVERT = "divert"


class ScenarioEventKind(StrEnum):
    """Event kinds for scenario.v1.

    Unsupported kinds are declared here so they produce explicit unsupported
    outcomes rather than schema errors.
    """

    OBSERVE = "observe"
    LOST_LINK = "lost_link"
    WIND_CHANGE = "wind_change"
    LANDING_ZONE_UNAVAILABLE = "landing_zone_unavailable"


class ScenarioTriggerKind(StrEnum):
    """When an event fires on the scenario timeline."""

    AT_MISSION_START = "at_mission_start"
    AT_ROUTE_ITEM = "at_route_item"
    AT_ELAPSED_TIME = "at_elapsed_time"
    AT_MISSION_END = "at_mission_end"


class ScenarioAssertionKind(StrEnum):
    """Assertion types supported in scenario.v1."""

    ESTIMATE_SUCCEEDS = "estimate_succeeds"
    ESTIMATE_FAILS = "estimate_fails"
    FIELD_LT = "field_lt"
    FIELD_GT = "field_gt"
    FIELD_LE = "field_le"
    FIELD_GE = "field_ge"
    FIELD_EQ = "field_eq"
    POLICY_ACTION_EQ = "policy_action_eq"


FIELD_ASSERTION_KINDS: frozenset[ScenarioAssertionKind] = frozenset(
    k for k in ScenarioAssertionKind if k.startswith("field_")
)

POLICY_ASSERTION_KINDS: frozenset[ScenarioAssertionKind] = frozenset(
    k for k in ScenarioAssertionKind if k.startswith("policy_")
)

_VALID_LOST_LINK_ACTIONS: frozenset[str] = frozenset(a.value for a in LostLinkAction)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_route_item_id(event: "ScenarioEvent") -> None:
    if event.trigger_route_item_id is None:
        raise ValueError(
            "trigger_route_item_id is required when trigger is at_route_item"
        )


def _require_elapsed_time(event: "ScenarioEvent") -> None:
    if event.trigger_elapsed_time_s is None:
        raise ValueError(
            "trigger_elapsed_time_s is required when trigger is at_elapsed_time"
        )


def _validate_event_trigger_params(event: "ScenarioEvent") -> None:
    if event.trigger == ScenarioTriggerKind.AT_ROUTE_ITEM:
        _require_route_item_id(event)
    if event.trigger == ScenarioTriggerKind.AT_ELAPSED_TIME:
        _require_elapsed_time(event)


def _has_scalar_wind_payload(event: "ScenarioEvent") -> bool:
    return event.wind_east_mps is not None or event.wind_north_mps is not None


def _has_complete_scalar_wind_payload(event: "ScenarioEvent") -> bool:
    return event.wind_east_mps is not None and event.wind_north_mps is not None


def _has_layered_wind_payload(event: "ScenarioEvent") -> bool:
    return event.wind_layers is not None


def _has_wind_payload(event: "ScenarioEvent") -> bool:
    return _has_scalar_wind_payload(event) or _has_layered_wind_payload(event)


def _validate_non_wind_event_has_no_wind_payload(event: "ScenarioEvent") -> None:
    if not _has_wind_payload(event):
        return
    raise ValueError(
        "wind_east_mps, wind_north_mps, and wind_layers are only valid "
        "for wind_change events"
    )


def _validate_wind_layers_are_non_empty(event: "ScenarioEvent") -> None:
    if event.wind_layers:
        return
    raise ValueError("wind_layers must contain at least one layer")


def _validate_lz_unavailable_params(event: "ScenarioEvent") -> None:
    is_lz_event = event.kind == ScenarioEventKind.LANDING_ZONE_UNAVAILABLE
    has_ids = event.unavailable_zone_ids is not None
    ids_empty = has_ids and len(event.unavailable_zone_ids) == 0  # type: ignore[arg-type]
    checks = (
        (
            is_lz_event and not has_ids,
            "unavailable_zone_ids is required for landing_zone_unavailable events",
        ),
        (
            is_lz_event and ids_empty,
            "unavailable_zone_ids must contain at least one zone id",
        ),
        (
            not is_lz_event and has_ids,
            "unavailable_zone_ids is only valid for landing_zone_unavailable events",
        ),
    )
    for invalid, message in checks:
        if invalid:
            raise ValueError(message)


def _validate_wind_change_params(event: "ScenarioEvent") -> None:
    if event.kind != ScenarioEventKind.WIND_CHANGE:
        _validate_non_wind_event_has_no_wind_payload(event)
        return

    if _has_layered_wind_payload(event) and _has_scalar_wind_payload(event):
        raise ValueError(
            "wind_change events must specify either wind_layers or "
            "wind_east_mps/wind_north_mps, not both"
        )
    if _has_layered_wind_payload(event):
        _validate_wind_layers_are_non_empty(event)
        return
    if _has_complete_scalar_wind_payload(event):
        return
    raise ValueError(
        "wind_east_mps and wind_north_mps are required for scalar "
        "wind_change events"
    )


def _validate_field_assertion_params(assertion: "ScenarioAssertion") -> None:
    if assertion.kind not in FIELD_ASSERTION_KINDS:
        return
    if assertion.field_path is None:
        raise ValueError(f"field_path is required for {assertion.kind} assertions")
    if assertion.expected is None:
        raise ValueError(f"expected is required for {assertion.kind} assertions")


def _validate_policy_assertion_params(assertion: "ScenarioAssertion") -> None:
    if assertion.kind not in POLICY_ASSERTION_KINDS:
        return
    if assertion.event_id is None:
        raise ValueError(f"event_id is required for {assertion.kind} assertions")
    if assertion.expected is None:
        raise ValueError(f"expected is required for {assertion.kind} assertions")
    if assertion.kind == ScenarioAssertionKind.POLICY_ACTION_EQ:
        if str(assertion.expected) not in _VALID_LOST_LINK_ACTIONS:
            raise ValueError(
                f"expected must be a valid LostLinkAction for {assertion.kind}; "
                f"got {assertion.expected!r}. "
                f"Valid values: {sorted(_VALID_LOST_LINK_ACTIONS)}"
            )


def _validate_assertion_params(assertion: "ScenarioAssertion") -> None:
    _validate_field_assertion_params(assertion)
    _validate_policy_assertion_params(assertion)


def _check_unique_ids(ids: list[str], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} must be unique")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LostLinkPolicy(BaseModel):
    """Contingency policy evaluated when a lost_link event fires."""

    model_config = ConfigDict(extra="forbid")

    loiter_s: float = Field(
        default=0.0,
        ge=0,
        description="Seconds to loiter at the link-loss position before executing action.",
    )
    action: LostLinkAction = Field(
        description="Contingency action to execute after the loiter period.",
    )
    divert_target_id: str | None = Field(
        default=None,
        description="Landing zone ID to divert to. Required when action is 'divert'.",
    )

    @model_validator(mode="after")
    def validate_divert_target(self) -> "LostLinkPolicy":
        if self.action == LostLinkAction.DIVERT and self.divert_target_id is None:
            raise ValueError("divert_target_id is required when action is 'divert'")
        return self


class ScenarioEvent(BaseModel):
    """A declarative event to observe or inject on the scenario timeline."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable event identifier unique within this scenario.",
    )
    kind: ScenarioEventKind
    trigger: ScenarioTriggerKind
    trigger_route_item_id: str | None = Field(
        default=None,
        description="Route item ID to fire at. Required when trigger is at_route_item.",
    )
    trigger_elapsed_time_s: float | None = Field(
        default=None,
        ge=0,
        description="Elapsed time in seconds. Required when trigger is at_elapsed_time.",
    )
    wind_east_mps: float | None = Field(
        default=None,
        description=(
            "New constant wind east component in m/s for wind_change events. "
            "Must be paired with wind_north_mps."
        ),
    )
    wind_north_mps: float | None = Field(
        default=None,
        description=(
            "New constant wind north component in m/s for wind_change events. "
            "Must be paired with wind_east_mps."
        ),
    )
    wind_layers: list[WindLayerConfig] | None = Field(
        default=None,
        description=(
            "New altitude-banded wind layers for wind_change events. "
            "Mutually exclusive with scalar wind fields."
        ),
    )
    unavailable_zone_ids: list[str] | None = Field(
        default=None,
        description=(
            "Landing zone IDs to mark unavailable from this event's trigger time onward. "
            "Required and must be non-empty for landing_zone_unavailable events. "
            "Not valid on other event kinds."
        ),
    )
    description: str | None = None

    @model_validator(mode="after")
    def validate_trigger_params(self) -> "ScenarioEvent":
        _validate_event_trigger_params(self)
        _validate_wind_change_params(self)
        _validate_lz_unavailable_params(self)
        return self


class ScenarioAssertion(BaseModel):
    """A declarative assertion to evaluate against the scenario result."""

    model_config = ConfigDict(extra="forbid")

    assertion_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable assertion identifier unique within this scenario.",
    )
    kind: ScenarioAssertionKind
    field_path: str | None = Field(
        default=None,
        description=(
            "Dotted field path into the estimate result. "
            "Required for field_* assertion kinds."
        ),
    )
    expected: bool | float | str | None = Field(
        default=None,
        description="Expected value for comparison assertions.",
    )
    event_id: str | None = Field(
        default=None,
        description=(
            "Event ID to reference. "
            "Required for policy_action_eq assertions."
        ),
    )
    description: str | None = None

    @model_validator(mode="after")
    def validate_assertion_params(self) -> "ScenarioAssertion":
        _validate_assertion_params(self)
        return self


class ScenarioInitialConditions(BaseModel):
    """Initial simulation state for scenario execution.

    These values override mission.estimation settings and library defaults.
    ``wind_layers`` and scalar wind values may coexist; when layers are present,
    the scalar ``wind_east_mps`` / ``wind_north_mps`` values are ignored.
    """

    model_config = ConfigDict(extra="forbid")

    wind_east_mps: float = Field(
        default=0.0,
        description="Constant wind east component in m/s. Ignored when ``wind_layers`` is set.",
    )
    wind_north_mps: float = Field(
        default=0.0,
        description="Constant wind north component in m/s. Ignored when ``wind_layers`` is set.",
    )
    wind_layers: list[WindLayerConfig] | None = Field(
        default=None,
        description=(
            "Altitude-banded wind layers. When set, supersedes ``wind_east_mps`` and "
            "``wind_north_mps`` and builds a LayeredWindProvider."
        ),
    )
    lost_link_policy: LostLinkPolicy | None = Field(
        default=None,
        description="Lost-link contingency policy applied when a lost_link event fires.",
    )
    max_segment_length_m: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Sub-segment wind sampling interval in metres. When set, transit legs are "
            "divided into sub-segments of at most this length and wind is sampled at "
            "each midpoint. Must be > 0."
        ),
    )
    min_groundspeed_mps: float | None = Field(
        default=None,
        gt=0,
        description="Minimum operational groundspeed in m/s for this scenario.",
    )
    fidelity: Literal["v1", "v2"] = Field(
        default="v1",
        description=(
            "Estimator fidelity mode. 'v1' (default): leg-to-leg geodesic model. "
            "'v2': adds turn-arc dynamics at waypoints and fixed-wing circular loiter."
        ),
    )


class ScenarioPlan(BaseModel):
    """Top-level scenario definition for deterministic scenario runner v1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scenario.v1"] = Field(
        description="Schema version. Must be 'scenario.v1'.",
    )
    scenario_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable scenario identifier.",
    )
    description: str | None = None
    mission_file: Path = Field(
        description=(
            "Path to mission YAML/JSON file. "
            "Relative paths are resolved from the scenario file location."
        ),
    )
    vehicle_file: Path = Field(
        description=(
            "Path to vehicle YAML/JSON file. "
            "Relative paths are resolved from the scenario file location."
        ),
    )
    initial_conditions: ScenarioInitialConditions = Field(
        default_factory=ScenarioInitialConditions,
    )
    events: list[ScenarioEvent] = Field(default_factory=list)
    assertions: list[ScenarioAssertion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form notes ignored by the scenario runner.",
    )

    @model_validator(mode="after")
    def validate_unique_event_ids(self) -> "ScenarioPlan":
        _check_unique_ids([e.event_id for e in self.events], "event ids")
        return self

    @model_validator(mode="after")
    def validate_unique_assertion_ids(self) -> "ScenarioPlan":
        _check_unique_ids([a.assertion_id for a in self.assertions], "assertion ids")
        return self
