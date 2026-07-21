# Example Stochastic Plans

Stochastic propagation plans for the pipeline demo mission. Use with `bvlos-sim propagate`.

| File | What it models |
|---|---|
| `pipeline_demo_001_stochastic.yaml` | 100 particles, Gaussian wind noise, no sensor model. |
| `pipeline_demo_001_stochastic_ekf.yaml` | Same particles with GPS and battery sensor profiles; outputs `estimation_error_timeline` and `cross_track_timeline`. |

## Quick start

```bash
# One-line diagnostic: modeled-pass rate and conditional p5/p50/p95 end energy
uv run bvlos-sim propagate examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format summary

# Full timeline report
uv run bvlos-sim propagate examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format markdown
```

See `examples/uncertainty/` for Monte Carlo uncertainty sampling (a simpler
per-sample model without time-stepped propagation).
