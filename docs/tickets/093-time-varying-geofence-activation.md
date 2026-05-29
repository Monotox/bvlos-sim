# Ticket 093: Time-Varying Geofence Activation

## Status

Implemented.

## Goal

Allow geofence zones to carry optional activation time windows so that
Temporary Flight Restrictions (TFRs), curfew zones, and time-limited airspace
reservations are only checked when the route actually passes through the active
period. This is a direct prerequisite for Ticket 058 (NOTAM integration) since
most NOTAMs describe time-bounded restrictions.

## Why This Is High Impact

The majority of real-world geofence conflicts in BVLOS operations involve
*temporary* restrictions — a TFR around an event venue active from 14:00–22:00,
a military exercise area active Mon–Fri 08:00–17:00, a VIP movement corridor
active for two hours. A tool that cannot model "this restriction is only active
during our planned flight window" will produce false infeasible results and lose
operator trust.

Currently all geofence zones are treated as permanently active. Adding time
windows allows operators to model real airspace more accurately, reducing both
false positives (cancelled flights due to inactive restrictions) and false
negatives (planned flights through a restriction that activates mid-mission).

## Scope

### GeoJSON schema extension

Time window fields are added as GeoJSON feature `properties`:

```json
{
  "type": "Feature",
  "id": "tfr_event_zone",
  "properties": {
    "kind": "forbidden",
    "active_from": "2026-06-01T14:00:00Z",   // ISO-8601, UTC
    "active_until": "2026-06-01T22:00:00Z",  // ISO-8601, UTC
    "recurrence": "daily"                    // optional: "daily", "weekdays"
  },
  "geometry": { ... }
}
```

If `active_from` / `active_until` are absent, the zone is always active
(current behaviour, backward-compatible).

### Mission departure time

A new optional field on the mission root:

```yaml
departure_time: "2026-06-01T15:00:00Z"   # ISO-8601 UTC
```

When set, each route point's absolute time is computed as
`departure_time + elapsed_time_s`. Geofence zones with time windows are only
checked when the route segment's time interval overlaps the zone's active window.

When `departure_time` is absent, all zones with time windows are checked as if
always active and a `DEPARTURE_TIME_MISSING` advisory warning is emitted.

### Estimator changes

- Load `active_from`, `active_until`, and `recurrence` from GeoJSON properties
  during geofence loading.
- Extend `GeofenceZone` with `active_from`, `active_until`, `recurrence` fields.
- In `estimator/execution/geofence.py`: for each leg, compute the leg's
  departure-relative time window and skip any zone whose active window does not
  overlap.

### Scenario support

Scenarios already have a timeline. The scenario runner computes elapsed time
per event. Time-varying geofences should be evaluated at the correct elapsed
time automatically, using the scenario's departure time if set.

### Fetch script integration

`scripts/fetch_geofences.py` extended to include time windows when fetching
from OpenAIP or similar sources that provide NOTAM-derived boundaries with
activation times.

### New WarningCode

```python
DEPARTURE_TIME_MISSING = "DEPARTURE_TIME_MISSING"
# Emitted when a time-windowed geofence zone exists but no departure_time is set.
```

### Files to create or modify

| File | Change |
|---|---|
| `schemas/mission.py` | Add `departure_time: datetime | None` to `MissionPlan` |
| `estimator/core/geofence.py` | Add `active_from`, `active_until`, `recurrence` to `GeofenceZone` |
| `estimator/core/enums.py` | Add `DEPARTURE_TIME_MISSING` warning code |
| `estimator/execution/geofence.py` | Time-window filtering in intersection check |
| `adapters/assets/geofence_geojson.py` | Parse time window properties from GeoJSON |
| `scripts/fetch_geofences.py` | Include time windows from source data |
| `tests/test_time_varying_geofence.py` | New — unit and integration tests |
| `docs/USAGE.md` | Document `departure_time` and time-windowed geofences |

### Composition with Ticket 058 (NOTAM integration)

Ticket 058 fetches NOTAM data and converts it to GeoJSON. The fetched GeoJSON
will naturally include `active_from`/`active_until` properties from the NOTAM's
effective period. This ticket provides the runtime enforcement; Ticket 058
provides the data source. They are independent and can be implemented in either
order.

### Acceptance criteria

1. A geofence zone with `active_from: "2026-06-01T20:00:00Z"` and a mission
   with `departure_time: "2026-06-01T14:00:00Z"` producing a route that
   finishes before 20:00 UTC returns `FEASIBLE` for that zone.
2. The same mission with a route that ends after 20:00 UTC returns `INFEASIBLE`
   with `ROUTE_ENTERS_FORBIDDEN_ZONE`.
3. A mission with a time-windowed geofence but no `departure_time` emits
   `DEPARTURE_TIME_MISSING` advisory and treats the zone as always active.
4. Zones without time window fields continue to behave as always active
   (backward compatibility).
5. `--format checklist` shows the departure time when set.
