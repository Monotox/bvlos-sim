# Ticket 069: Per-Event Lost-Link Policy Override

## Goal

Allow each `lost_link` event in a scenario to carry its own `LostLinkPolicy`,
overriding the global `initial_conditions.lost_link_policy` for that specific
event. This lets operators model realistic contingency plans where the right
action depends on where in the route link loss occurs — RTL early in the
mission, DIVERT to the nearest landing zone at the midpoint, and LAND in a
designated field near the destination.

## Motivation

A single global `lost_link_policy` is sufficient for simple scenarios but does
not reflect real BVLOS operations. UTM/CAA flight approvals often require
demonstrating that the aircraft has a valid contingency action **at every
waypoint**. Testing this requires multiple `lost_link` events fired at
different route items, each with a different action, and asserting that all
of them produce feasible outcomes.

Today, a scenario with two `lost_link` events (e.g., one at waypoint 2 and
one at waypoint 6) must use the same policy for both. Operators work around
this by writing one scenario file per waypoint, which multiplies files and
makes it impossible to assert cross-waypoint properties in a single run.

A concrete example: a quadplane flying a 40 km pipeline route may need to
RTL at km 0–15 (battery sufficient), DIVERT to a mid-route LZ at km 15–35
(reserve margin shrinks), and LAND at the nearest available zone beyond km 35
(no RTL reserve left). Modelling this requires three distinct policies bound
to three distinct trigger points.

## Current Behaviour

`ScenarioEvent` has no `policy` field. The scenario runner reads
`scenario.initial_conditions.lost_link_policy` once and passes it to
`_process_events` as the uniform policy for all `lost_link` events. Placing
`policy:` on a `ScenarioEvent` yields `extra_forbidden` validation error.

## Implementation

### 1 — Schema: `schemas/scenario.py`

Add an optional `policy` field to `ScenarioEvent`:

```python
class ScenarioEvent(BaseModel):
    ...
    policy: LostLinkPolicy | None = Field(
        default=None,
        description=(
            "Per-event lost-link policy override. When set on a lost_link event, "
            "this policy takes precedence over initial_conditions.lost_link_policy. "
            "Not valid on other event kinds."
        ),
    )
```

Add a validator that raises if `policy` is set on a non-`lost_link` event:

```python
@model_validator(mode="after")
def validate_policy_field(self) -> "ScenarioEvent":
    if self.policy is not None and self.kind != ScenarioEventKind.LOST_LINK:
        raise ValueError(
            "policy is only valid on lost_link events"
        )
    return self
```

### 2 — Execution: `estimator/execution/scenario.py`

Change `_process_event` to resolve the effective policy from the event first,
falling back to the global policy:

```python
def _process_event(
    event: ScenarioEvent,
    timeline: list[TimelinePoint],
    lost_link_policy: LostLinkPolicy | None,
    *,
    ...
) -> ScenarioEventOutcome:
    trigger_index = resolve_trigger_index(event, timeline)
    if trigger_index is None:
        return _not_fired_event_outcome(event)
    if event.kind == ScenarioEventKind.LOST_LINK:
        effective_policy = event.policy if event.policy is not None else lost_link_policy
        return _process_lost_link_event(
            event,
            timeline,
            effective_policy,
            trigger_index,
            ...
        )
    return _fired_event_outcome(event, trigger_index)
```

`_process_events` and `run_scenario` are unchanged; the fallback chain is
encapsulated in `_process_event`.

### 3 — Tests: `tests/test_scenario_per_event_policy.py`

New acceptance tests:

- `test_per_event_policy_overrides_global_policy` — scenario with global RTL
  and a single `lost_link` event carrying `policy: {action: land}`. Assert
  `policy_action_eq` is `land`, not `rtl`.
- `test_two_events_different_policies` — scenario with two `lost_link` events
  at different route items, first with `action: rtl`, second with
  `action: divert`. Assert both policy outcomes independently.
- `test_event_without_policy_uses_global` — scenario with global `loiter` and
  an event that has no `policy` field. Assert policy action is `loiter`.
- `test_policy_field_on_wind_change_event_raises_schema_error` — confirms
  Pydantic rejects `policy:` on a `wind_change` event with a validation error.
- `test_per_event_policy_none_and_no_global_produces_no_outcome` — when event
  has no `policy` and `initial_conditions.lost_link_policy` is `None`, the
  policy outcome must be `None`.
- `test_divert_policy_on_second_event_resolves_divert_estimate` — scenario with
  a DIVERT policy only on the second `lost_link` event. Assert `divert_estimate`
  is populated in that event's outcome and `is_feasible` is True or False.

### 4 — Example scenario

Add `examples/scenarios/pipeline_demo_001_waypoint_policy_scenario.yaml`
demonstrating three `lost_link` events with distinct per-event policies:

```yaml
schema_version: scenario.v1
scenario_id: waypoint-policy-demo
mission_file: ../missions/pipeline_demo_001.yaml
vehicle_file: ../vehicles/quadplane_v1.yaml
initial_conditions:
  wind_east_mps: 3.0
  wind_north_mps: 0.0
events:
  - event_id: link-loss-early
    kind: lost_link
    trigger: at_route_item
    trigger_route_item_id: wp-002
    policy:
      action: rtl
      loiter_s: 30
  - event_id: link-loss-mid
    kind: lost_link
    trigger: at_route_item
    trigger_route_item_id: wp-005
    policy:
      action: divert
      loiter_s: 30
      divert_target_id: lz-alpha
  - event_id: link-loss-late
    kind: lost_link
    trigger: at_route_item
    trigger_route_item_id: wp-008
    policy:
      action: land
      loiter_s: 0
assertions:
  - assertion_id: early-rtl
    kind: policy_action_eq
    event_id: link-loss-early
    expected: rtl
  - assertion_id: mid-divert
    kind: policy_action_eq
    event_id: link-loss-mid
    expected: divert
  - assertion_id: late-land
    kind: policy_action_eq
    event_id: link-loss-late
    expected: land
```

### 5 — Docs: `docs/USAGE.md`

In the Scenario Execution section, add a subsection "Per-Event Contingency
Policies" explaining that `policy:` on a `lost_link` event overrides the
global `initial_conditions.lost_link_policy` for that event, and showing a
YAML snippet with two events using different actions.

### 6 — Schema version

`scenario.v1` is the only schema version and there are no versioned envelope
outputs for scenarios; no version bump is required. Existing scenario files
that do not set `policy` on events are fully forward-compatible.

## Integration

Composes with Ticket 021 (comms-link and contingency policies) as a direct
extension of `LostLinkPolicy`. The global `initial_conditions.lost_link_policy`
remains the fallback and is still the only way to configure policy for operators
who want a uniform policy across all events. Ticket 068 (divert-route GeoJSON
layer) benefits directly: a scenario with multiple divert events at different
waypoints will now render multiple distinct divert-route LineStrings.

## Acceptance Criteria

- A `lost_link` event with an explicit `policy` field uses that policy instead
  of the global policy.
- A `lost_link` event without a `policy` field falls back to
  `initial_conditions.lost_link_policy` (unchanged behaviour).
- Setting `policy:` on a non-`lost_link` event (e.g. `wind_change`) raises a
  Pydantic validation error with a clear message.
- Two `lost_link` events in the same scenario can carry different `action`
  values and both resolve correctly.
- All existing scenario tests pass without modification.
- The example scenario file runs without errors via the `scenario` CLI.
