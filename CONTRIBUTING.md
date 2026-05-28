# Contributing

Thanks for helping improve bvlos-sim. This guide covers the workflow expected
for code, documentation, and test changes.

## Development Setup

Install the project dependencies with uv:

```bash
uv sync
```

Run the CLI locally:

```bash
uv run bvlos-sim --help
```

If your local environment is not installing console entry points, the module
entrypoint is equivalent:

```bash
uv run python -m main --help
```

## Tests and Linting

Run the full test suite:

```bash
uv run pytest
```

Run the linter:

```bash
uv run ruff check .
```

Run the release-oriented CLI batch audit:

```bash
uv run python scripts/cli_batch_audit.py
```

The batch audit invokes the installed `bvlos-sim` command through subprocesses
and checks broad success, invalid input, unsupported, infeasible, output-format,
asset-loading, and scenario cases.

Before opening a pull request, run these checks and include the result in the
PR test plan.

## Branch and Pull Request Workflow

1. Create a focused branch from `main`.
2. Keep changes scoped to one fix or feature.
3. Add or update tests for behavior changes.
4. Update docs when changing public behavior, output formats, supported inputs,
   or known limitations.
5. Open a pull request with a concise summary and test plan.

Pull requests should explain user-visible behavior changes and call out any
contract impact explicitly.

## Commit Messages

Use short, imperative commit messages with one of these prefixes:

- `feat:` for a new capability
- `fix:` for a bug fix
- `docs:` for documentation-only changes
- `test:` for test-only changes
- `refactor:` for behavior-preserving code cleanup

Examples:

```text
feat: add scenario markdown report
fix: preserve mission wind layers in CLI scenarios
docs: document fidelity v2 YAML options
```

## Contributing a Vehicle Profile

Community vehicle profiles live in `examples/vehicles/community/`. To add a
new profile:

1. Copy the closest existing profile as a starting point.
2. Set `vehicle_id` to a lowercase, hyphen-separated identifier (e.g.,
   `my_aircraft_v1`). This must match `mission.vehicle_profile` when using
   the profile.
3. Fill in all required fields:

   | Section | Required fields |
   |---|---|
   | top-level | `vehicle_id`, `display_name`, `vehicle_class` |
   | `mass` | `empty_kg`, `max_takeoff_kg` |
   | `performance` | `cruise_speed_mps`, `hover_speed_mps`, `climb_rate_mps`, `descent_rate_mps`, `max_wind_mps` |
   | `energy` | `battery_capacity_wh`, `hover_power_w`, `cruise_power_w`, `climb_power_w` |
   | `capabilities` | `hover`, `forward_flight` |
   | `metadata` | `calibration_status`, `source`, `notes` |

4. Set `metadata.calibration_status` to one of these conventional values:
   - `manufacturer_derived` — all values are from published manufacturer specs
     or directly derived from published endurance/capacity figures
   - `placeholder_values` — values are typical-class estimates with no
     manufacturer source
   - `log_calibrated` — power and speed values have been fitted to observed
     flight logs

5. Set `metadata.source` to the manufacturer spec page URL, datasheet link,
   or `null` for placeholder profiles.
6. In `metadata.notes`, document which values were directly published and which
   were derived or estimated, so reviewers can evaluate the derivation.
7. Add an entry in `examples/vehicles/community/README.md` using the same
   format as existing entries: key specs, primary provenance, and a statement
   of which values are estimates.

A pull request adding a vehicle profile should include the YAML file and the
README entry. The review will check that every derived or estimated value is
clearly labeled as such and that no value is presented as manufacturer-sourced
without a link.

## Public Contract Changes

The public contract surfaces must not change casually. These include:

- schema versions such as `mission.v6`, `vehicle.v4`, and `scenario.v1`
- canonical JSON envelopes such as `estimator-envelope.v6` and `scenario-report.v2`
- CLI exit codes
- documented package-root imports from `estimator`

If a contract change is intentional, follow
[docs/VERSIONING_POLICY.md](./docs/VERSIONING_POLICY.md): bump the relevant
version identifier, update golden fixtures, update regression tests, and update
the user-facing docs in the same change.
