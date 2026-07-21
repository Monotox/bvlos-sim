# Ticket 039: Path-Planning Model Gaps

## Status

Implemented. The original offset-subtraction proposal below was superseded by
connected circular fillets: each transit ends at a tangent point, the arc has
non-zero displacement, and geometry that cannot fit fails instead of clamping.

## Goal

Address the remaining path-planning model gaps left after Ticket 038: tangent-point
offsets for fidelity v2 turn arcs, 3D slant path distance for vertical legs, and
the planar-approximation limitation of the Dubins divert solver for very long routes.

## Gap at the Time

Three related gaps remain after the Ticket 038 Dubins implementation:

- **Fidelity v2 turn arcs do not subtract tangent-point offsets.** The arc is
  placed at the waypoint and the adjacent transit legs extend all the way to the
  waypoint. A proper Dubins-path model shortens each adjacent transit leg by
  `turn_radius_m * tan(|Δθ| / 2)` (the tangent offset). The current model
  therefore overestimates total path distance for routes with sharp turns.
- **Vertical-only legs have zero horizontal distance.** `takeoff` and `land`
  route items produce a leg with `horizontal_distance_m = 0` and
  `path_distance_m = 0` even when the vehicle climbs or descends over a
  horizontal displacement. The true 3D slant path distance is
  `sqrt(horizontal_distance_m² + vertical_distance_m²)`.
- **Dubins divert uses a planar East-North approximation.** The RS/LS path solver
  works in a flat plane using a bearing + distance from pyproj. For divert legs
  shorter than ~50 km the error is negligible, but the approximation is not
  documented as a numeric limit.

## Historical Scope

- Fidelity v2 transit legs: subtract `turn_radius_m * tan(|Δθ| / 2)` from
  `path_distance_m` of each transit leg adjacent to a turn arc so that
  total path distance reflects the true Dubins-path length.
- 3D slant path distance: set `path_distance_m = sqrt(horizontal_distance_m² +
  vertical_distance_m²)` for `takeoff` and `land` legs when both components are
  non-zero.
- Dubins divert planar limit: document the ~50 km planar approximation error
  bound in `ESTIMATOR_V1_FIELD_SEMANTICS.md` and add a structured diagnostic
  warning when the computed geodesic divert distance exceeds the limit.
- Update golden fixtures if path-distance values change.
- Update `ESTIMATOR_V1_FIELD_SEMANTICS.md` Fidelity Semantics and Divert Routing
  Semantics sections.

## Integration Requirements

- Fidelity v1 behavior must remain unchanged.
- All existing divert routing result field names remain stable; only values change.
- Changes must compose with existing terrain, wind, geofence, resource, link, and
  scenario behavior.

## Current Acceptance Criteria

- Fidelity v2 total path distance equals the geodesically recomputed transit
  portions between tangent points plus the connected circular fillet lengths.
- A corner whose tangent geometry does not fit both adjacent legs returns
  `INVALID_GEOMETRY`; tangent offsets are never silently clamped.
- `takeoff` and `land` legs report the correct 3D slant path distance in
  `path_distance_m` when horizontal displacement is non-zero.
- A diagnostic warning is emitted when Dubins divert distance exceeds the planar
  approximation accuracy limit.
- Fidelity v1 behavior is unchanged.

## Out of Scope

- Full 3D Dubins paths or obstacle-aware replanning.
- Real-time path replanning.
