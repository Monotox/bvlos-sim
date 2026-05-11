# Ticket 034: Resource and Link Feasibility Abstractions

## Goal

Generalize flight feasibility around configurable resource and communication
systems instead of assuming every aircraft is only battery-limited and every
scenario only needs a simple lost-link policy outcome.

This should let bvlos-sim model aircraft powered by direct battery, tethered or
optical-fiber power delivery, hybrid onboard/external sources, and future
resource systems while also modeling communication architectures such as direct
radio, mesh networks, LTE/5G, satellite links, Starlink-class terminals, and
hybrid failover stacks.

## Current Gap

Energy feasibility is currently battery-centric: vehicle YAML defines capacity,
usable energy, reserve, and phase power values. Communication modeling is also
scenario-centric: scenarios can declare lost-link events and policy outcomes,
but there is no reusable link-system model that can affect feasibility before
or during a mission.

These two domains are coupled in real BVLOS planning. A tethered or optical
fiber system can change energy endurance, weight assumptions, route limits, and
failure modes. A mesh, satellite, or hybrid comms stack can change whether a
route is feasible, whether a lost-link policy should fire, and whether a
divert/RTL/loiter action remains valid.

## Scope

- Define abstract resource-system models for mission feasibility:
  - onboard battery
  - externally supplied power, including tethered or optical-fiber power
  - hybrid onboard/external power
  - reserved extension points for fuel, hydrogen, or other resource types
- Define abstract communication-link system models:
  - direct point-to-point link
  - mesh network
  - cellular/LTE/5G link
  - satellite or Starlink-class link
  - hybrid failover and priority order
- Add schema support for resource and link systems without breaking existing
  vehicle `energy` fields.
- Add deterministic feasibility evaluation for configured resource and link
  systems.
- Add structured diagnostics when resource or link constraints make a mission
  infeasible.
- Add report fields that separate kinematic, resource, and link feasibility.
- Document migration from existing battery-only energy configuration to the
  generalized resource model.

## Integration Requirements

- Extend existing vehicle YAML and mission YAML rather than adding isolated
  one-off input formats. Battery-only vehicle YAML must keep working.
- Add examples under `examples/vehicles/`, `examples/missions/`, and
  `examples/scenarios/` that combine resource systems and link systems with
  terrain, wind-grid, geofence, landing-zone, and fidelity-v2 features.
- Ensure `estimate` can evaluate deterministic resource and link feasibility
  for a mission before scenario events are involved.
- Ensure `scenario` can use the same resource and link models together with
  lost-link events, wind-change events, dynamic landing-zone availability, and
  computed divert routing.
- Keep live network integrations out of the deterministic core. Live comms
  adapters in later tickets should replay into the same link-system model.
- Update canonical JSON envelopes, Markdown reports, golden fixtures, and
  regression tests if public result fields change.
- Update field-semantics documentation so every new schema field is either
  operative, explicitly reserved, or rejected.

## Design Notes

- Treat "energy" as one resource type, not the whole feasibility domain.
- Use stable domain terms such as `resource_system`, `resource_budget`,
  `link_system`, `link_segment`, and `availability_policy` rather than naming
  schemas around one vendor or transport.
- Model external power delivery as deterministic constraints first: maximum
  route length, available power, outage behavior, attachment constraints,
  additional mass/drag assumptions, and reserve/fallback battery policy.
- Model communication links as deterministic coverage/availability evidence
  first: coverage asset, availability window, link priority, failover behavior,
  required command-and-control continuity, and policy trigger conditions.
- Preserve current battery fields as a compatibility layer until a versioned
  migration path is documented.

## Acceptance Criteria

- Existing battery-only examples and tests remain valid.
- A vehicle can declare a resource system that is not a simple direct battery
  without bypassing energy/resource feasibility.
- A mission or scenario can declare a communication-link system that affects
  feasibility and lost-link policy evaluation.
- JSON and Markdown reports clearly show whether infeasibility came from route
  kinematics, resource limits, link availability, geofences, landing zones, or
  scenario policy outcomes.
- Resource and link feasibility compose with mission YAML, vehicle YAML,
  scenario YAML, terrain assets, wind assets, geofence assets, landing-zone
  assets, `estimate`, `scenario`, package-root APIs, and golden fixtures.

## Out of Scope

- Live Starlink, LTE, mesh, or radio adapter implementations.
- Vendor-specific modem APIs.
- Certified command-and-control compliance claims.
- Real-time network planning or spectrum analysis.
- Replacing later live comms, Remote ID, traffic, or UTM integration tickets.
