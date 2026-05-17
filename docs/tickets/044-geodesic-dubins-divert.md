# Ticket 044: Geodesic Dubins Divert Path

## Status

Implemented.

## Goal

Replace the planar East-North approximation in the Dubins divert solver with a
geodesic formulation so that divert distance estimates remain accurate for
routes longer than approximately 50 km.

## Current Gap

The Dubins divert path solver (`estimator/execution/divert.py`) works in a
flat local East-North plane. It converts the geodesic bearing and distance from
the action point to the nearest landing-zone point into Cartesian coordinates
and solves the RS/LS path in 2D. For divert legs shorter than ~50 km the
planar error is a fraction of a percent and is negligible. Beyond that
threshold, the Earth's curvature means the flat-plane bearing and distance no
longer faithfully represent the geometry, and path-length error grows with
distance.

Ticket 039 added a `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning when the
geodesic divert distance exceeds 50 km, but did not fix the underlying
approximation. Long-range divert routes (e.g. offshore energy or corridor
missions with alternate aerodromes tens to hundreds of kilometres away) will
receive this warning and an inaccurate divert distance until this ticket is
implemented.

## Scope

- Replace the planar path computation in `_dubins_distance_to_geometry_m` with
  a geodesic Dubins formulation. Two approaches are acceptable:
  - **Multi-segment geodesic**: decompose the Dubins path into the turning arc
    (approximated as a sequence of short geodesic steps along the great-circle
    arc) plus the straight tangent leg (as a geodesic), and sum the two
    distances. Accurate for all practical divert ranges.
  - **Vincentys / direct geodesic arc**: compute the arc length on the
    ellipsoid by integrating arc-length increments along the constant-radius
    circular path projected onto the WGS-84 ellipsoid.
- The simplest correct implementation is the multi-segment geodesic approach:
  discretise the arc into N short steps (e.g. 1° per step), accumulate
  geodesic leg distances, and add the straight-leg geodesic distance.
- Remove or downgrade the `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning
  once the geodesic solver is operative for all distances, or retain it as a
  documentation note only.
- Update `ESTIMATOR_V1_FIELD_SEMANTICS.md` Divert Routing Semantics to reflect
  the geodesic formulation.
- Update `_ASSUMPTIONS` in `adapters/envelope.py` and regenerate golden
  fixtures if divert distance values change for existing test cases (they
  should not change meaningfully for the short-range cases in the test suite).
- Add unit tests verifying that geodesic and planar results agree within 0.1 %
  for distances under 10 km, and that the geodesic result is returned without
  the planar-limit warning for distances beyond 50 km.

## Integration Requirements

- Fidelity v1 and v2 behavior must remain unchanged.
- All existing divert routing result field names remain stable; only the
  computed `distance_m` value changes for long-range diverts.
- The fix must compose with existing terrain, wind, geofence, resource, link,
  and scenario behavior.
- The `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning must no longer be
  emitted (or must be removed) once the geodesic solver handles all distances
  correctly.

## Acceptance Criteria

- Divert distance is accurate within 0.5 % of the true Dubins path length on
  the WGS-84 ellipsoid for divert legs up to 500 km.
- The `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning is no longer emitted
  for correctly handled distances.
- The test suite passes; new geodesic accuracy tests are added.
- `ESTIMATOR_V1_FIELD_SEMANTICS.md` reflects the geodesic formulation.

## Out of Scope

- Full 3D Dubins paths or obstacle-aware replanning.
- Real-time path replanning.
- Geodesic treatment of fidelity v2 transit leg geometry (transit legs already
  use pyproj geodesic distance and are not affected by this ticket).
