# Example Vehicle Profiles

Vehicle profiles for the pipeline demo and community reference aircraft.

| File | Class | Description |
|---|---|---|
| `quadplane_v1.yaml` | VTOL | Baseline VTOL quadplane used by most pipeline demo missions. |
| `quadplane_v1_ekf.yaml` | VTOL | Same airframe with GPS and battery sensor profiles for EKF twin-state stochastic propagation. |
| `quadplane_resource_link.yaml` | VTOL | Variant with explicit resource and communication-link systems. |
| `quadplane_v1_complete.yaml` | VTOL | Resource systems plus `characteristic_dimension_m`, so `pipeline_demo_001_go.yaml` can reach `GO`. Same `vehicle_id` as the baseline, so the bundled calibration profile applies. |
| `quadplane_v1_ground_risk.yaml` | VTOL | Baseline plus `characteristic_dimension_m` for SORA iGRC. |
| `community/` | Various | Five manufacturer-sourced profiles — see `community/README.md`. |

## Quick start

```bash
# Check a vehicle profile is valid (no estimation)
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --validate-only

# Estimate with the baseline VTOL (--engineering-only: the demo mission has no
# resource/link/obstacle/ground-risk evidence, so the operational verdict is NO-GO)
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --format summary --engineering-only
```

## Adding your own profile

Copy `quadplane_v1.yaml` as a starting point. Set `vehicle_id` to a unique
slug (e.g. `my_hex_v1`), update `vehicle_class`, and fill in `mass`,
`performance`, and `energy` from your aircraft's datasheet. Reference the same
`vehicle_id` in your `mission.yaml` `vehicle_profile` field.
