# Example Batch Manifests

Batch manifest files for running multiple estimate jobs in one command.

| File | Description |
|---|---|
| `demo_batch.yaml` | Three-run manifest: Alpine standard, Alpine infeasible, and pipeline demo. |

## Quick start

```bash
# Summary table (stdout)
uv run bvlos-sim batch examples/batch/demo_batch.yaml --format summary

# Write per-run JSON files to a directory
uv run bvlos-sim batch examples/batch/demo_batch.yaml \
  --format json --output-dir /tmp/batch_out/

# CSV for import into a spreadsheet
uv run bvlos-sim batch examples/batch/demo_batch.yaml --format csv

# Validate all referenced files without running estimates
uv run bvlos-sim batch examples/batch/demo_batch.yaml --validate-only
```

## Manifest format

```yaml
format_version: "batch.v1"
runs:
  - id: my_run          # used as output filename stem
    mission: path/to/mission.yaml
    vehicle: path/to/vehicle.yaml
```

Paths are resolved relative to the manifest file. Run IDs must be unique and
match `^[A-Za-z0-9][A-Za-z0-9_-]*$`.
