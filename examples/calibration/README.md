# Calibration example

Pairs a base vehicle profile with a calibration artifact fitted from an observed
flight, demonstrating the full ingestion → segmentation → fitting → apply path
with no manual data translation.

| File | Role |
|------|------|
| [`../vehicles/quadplane_v1.yaml`](../vehicles/quadplane_v1.yaml) | Base vehicle profile (placeholder/spec-sheet values) |
| [`../flight_logs/pipeline_demo_001_trace.json`](../flight_logs/pipeline_demo_001_trace.json) | Observed `flight-trace.v1` (from flight-log ingestion) |
| [`quadplane_v1_calibration.json`](quadplane_v1_calibration.json) | Fitted `calibration-profile.v1` artifact |

## Reproduce the artifact

The committed artifact is generated deterministically — the same vehicle and
trace always produce byte-identical output (the embedded `tool_version` aside):

```bash
uv run bvlos-sim calibrate \
  examples/vehicles/quadplane_v1.yaml \
  examples/flight_logs/pipeline_demo_001_trace.json \
  --format json -o examples/calibration/quadplane_v1_calibration.json
```

This demo flight only climbs and cruises, so the fitter calibrates
`cruise_speed_mps` and `climb_rate_mps`; `descent_rate_mps` and
`max_station_keep_wind_mps` have no supporting samples and are reported in the
artifact's `notes` rather than fabricated.

## Apply it

The calibration layers on the base vehicle — it overrides only the fitted fields
and is opt-in everywhere:

```bash
# Estimate with calibrated performance
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --calibration examples/calibration/quadplane_v1_calibration.json

# Validate the calibrated model against the same flight
uv run bvlos-sim validate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  examples/flight_logs/pipeline_demo_001_trace.json \
  --calibration examples/calibration/quadplane_v1_calibration.json
```

The calibration's `base_vehicle_id` must match the vehicle's `vehicle_id`;
a mismatch is rejected as invalid input.
