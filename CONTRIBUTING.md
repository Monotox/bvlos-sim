# Contributing

## Setup

```bash
uv sync
uv run bvlos-sim --help     # or: uv run python -m main --help
```

Before every pull request, run and report:

```bash
uv run ruff check .
uv run pytest
uv run python bvlos_sim/scripts/cli_batch_audit.py   # exercises the CLI end to end
```

Optional extras: `--extra flight-logs` (binary log readers), `--extra sitl`
(live SITL tests), `--extra scripts` (data-fetch helpers).

## Workflow

1. Branch from `main`, scoped to one fix or feature.
2. Add or update tests for behavior changes.
3. Update docs in the same change — a stale doc is a bug.
4. Open a PR with a concise summary and test plan; call out any public
   contract impact explicitly.

Commit messages are short and imperative, prefixed `feat:` / `fix:` /
`docs:` / `test:` / `refactor:`.

Releases are one command: `uv run bvlos-sim bump <major|minor|patch>` updates
`pyproject.toml` and rolls `CHANGELOG.md`, then prints the commit/tag/push
follow-ups. `--dry-run` previews; `--check` fails CI on version drift. Golden
fixtures pin `tool_version` to `0.0.0-test`, so a release can never break
them.

## Architecture rules

Package responsibilities are boundaries, not suggestions:

| Package | Owns |
|---|---|
| `schemas/` | Pydantic input models; never depends on adapters or execution |
| `estimator/core/` | Public enums, options, result models, typed errors; no execution logic |
| `estimator/execution/` | Estimation, static checks, scenario runner |
| `estimator/environment/` | Wind/terrain/population providers |
| `estimator/math/` | Pure geometry helpers |
| `adapters/` | CLI, file I/O, envelopes, report rendering; no domain rules |
| `adapters/sitl/` | ArduPilot adapter; the only home for simulator/MAVLink imports |

Style: `StrEnum` for closed sets, typed models over ad hoc dicts, typed
exceptions over message-only `ValueError`, table-driven dispatch, pure math
helpers, structured failures instead of raw dependency exceptions, and
determinism everywhere. Schema validation owns field shape and bounds;
runtime validation owns cross-object consistency and feasibility. Tests
verify behavior and contracts — not Pydantic internals, not brittle
implementation snapshots.

## Public contracts

These are stable within a published version: the versioned input schemas and
output envelopes (`bvlos-sim schema-versions` prints the full set), CLI
exit-code semantics, package-root `estimator` imports, and the Markdown
shapes covered by golden fixtures. Within a version, never remove or rename
public fields, change enum/status/exit-code meanings, make the operational
verdict renderer-dependent, or change canonical JSON rendering.

An intentional contract change updates, in one commit: the version
identifier, golden fixtures, regression tests, and the user-facing docs.
Review fixture diffs as contract changes, not snapshot churn.

## Vehicle profiles

Community profiles live in `examples/vehicles/community/`. A new profile
needs: `vehicle_id`/`display_name`/`vehicle_class`; `mass.empty_kg` and
`max_takeoff_kg`; `performance` cruise/hover speed, climb/descent rate, and
`max_wind_mps`; `energy` capacity and hover/cruise/climb power;
`capabilities`; and `metadata` with `calibration_status`
(`manufacturer_derived` | `placeholder_values` | `log_calibrated`), `source`
(spec URL, or `null` for placeholders), and `notes` stating which values are
published and which are derived. Add a README entry in the same format as the
existing ones. Review checks that no estimated value masquerades as
manufacturer-sourced.

## Documentation style

Docs live in `docs/` as kebab-case files, one Diátaxis mode each: tutorial
([getting-started](docs/getting-started.md)), how-to
([missions](docs/missions.md), [sitl](docs/sitl.md)), reference
([cli](docs/cli.md)), explanation ([design](docs/design.md)). Voice: second
person, present tense, active, sentence-case headings, no filler
("simply", "just", "easy"). One term per concept, matching the code: mission,
vehicle profile, envelope, checklist, fail-closed. Every command shown must
run exactly as written; verify against the CLI before asserting. When
behavior changes, its doc changes in the same commit.
