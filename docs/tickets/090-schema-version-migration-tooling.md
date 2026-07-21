# Ticket 090: Schema Version Migration Tooling

## Status

Implemented for the `mission.v6` → `mission.v7` migration path. The registry is
chained and ready for additional schema steps.

## Goal

Provide a `bvlos-sim migrate` command that reads an existing mission YAML/JSON
input, detects its schema version, and writes an upgraded file that conforms to
the latest schema.

## Motivation

Before this ticket, schema changes required operators to update YAML manually.
The implemented mission path now provides a guarded `mission.v6` →
`mission.v7` conversion. Other schema families still require a registered
migration before `migrate` can process them.

The current schema surfaces that operators write directly include:

| Schema | Version | Input file |
|--------|---------|------------|
| mission | v7 | `mission.yaml` |
| vehicle | v4 | `vehicle.yaml` |
| scenario | v1 | `scenario.yaml` |
| uncertainty | v1 | `uncertainty.yaml` |
| stochastic | v1 | `stochastic.yaml` |
| batch manifest | v1 | `batch.yaml` |

The mission family now has a machine-readable path. Other families need a
registered migration step before their next breaking version can be upgraded
automatically.

## Scope

### CLI

```bash
# In-place upgrade with backup
bvlos-sim migrate mission.yaml --backup

# Detect schema and print current/target version without writing
bvlos-sim migrate mission.yaml --dry-run

# Batch: migrate all missions in a directory
bvlos-sim migrate missions/ --glob "*.yaml" --backup
```

Supported flags:
- `--dry-run` — print detected version, target version, and diff; do not write
- `--backup` — write the original as `<file>.bak` before overwriting
- `--output FILE` — write upgraded content to a new file instead of overwriting
- `--glob PATTERN` — when path is a directory, process all matching files

### Version detection

The implemented command accepts mission `.yaml`, `.yml`, and `.json` files and
inspects the root `schema_version`. A missing version is treated as legacy
`mission.v6` **only inside the migration command**. Normal mission loaders
require an explicit `schema_version: mission.v7` and direct legacy users to
`bvlos-sim migrate`. Unknown explicit versions are rejected rather than guessed.

The v6→v7 step refuses semantic guesses that could manufacture a safety credit:
applied legacy M1/M2/M3 or tactical ARC credits, a strategic boolean credit,
ambiguous `above_flight_level_600: true`, and missing urban/rural classification
where that choice affects ARC. Those cases require an operator-authored v7
declaration and evidence.

### Migration registry

A migration is a pure function `(dict) → dict` registered against a
`(schema_name, from_version, to_version)` triple:

```python
@register_migration("mission", from_version="mission.v6", to_version="mission.v7")
def migrate_mission_v6_to_v7(payload: dict) -> dict:
    # e.g. rename field, add default, restructure nested key
    ...
```

Migrations are chained automatically: `v3 → v4 → v5` applies both functions
in sequence. This means each migration only needs to handle one version step.

### YAML rendering

YAML output uses PyYAML with `sort_keys=False`, so mapping order is retained but
comments are not preserved. Use `--dry-run` to inspect the exact diff and
`--backup` to retain the original before an in-place migration.

### Acceptance criteria

1. `bvlos-sim migrate --help` shows usage and exits 0.
2. `bvlos-sim migrate mission.v6.yaml --dry-run` prints the detected version,
   the target version, and the fields that would change; does not write.
3. `bvlos-sim migrate mission.v6.yaml --output mission.v7.yaml` writes a file
   that passes `bvlos-sim estimate mission.v7.yaml vehicle.yaml --validate-only`.
4. `bvlos-sim migrate mission.v7.yaml --dry-run` reports "already at latest version"
   and exits 0.
5. `bvlos-sim migrate nonexistent.yaml` exits 11 (invalid input).
6. Migration functions are unit-tested in isolation against known before/after payloads.
7. At least one real migration is implemented (whichever schema version bump
   ships first after this ticket).

## Composition

- New `adapters/commands/migrate.py` registered on the CLI app.
- New `adapters/migration/` package containing the registry and migration
  functions for each schema type.
- `mission.v7` is the only mission schema accepted by normal loaders; the
  migration package owns legacy-version detection and conversion.
- `docs/USAGE.md` updated with a `## Schema Migration` section.
- `CONTRIBUTING.md` updated with instructions for writing a migration function
  when a schema version bumps.
