# Ticket 090: Schema Version Migration Tooling

## Status

Planned.

## Goal

Provide a `bvlos-sim migrate` command that reads an existing YAML input file,
detects its schema version, and writes an upgraded file that conforms to the
latest schema. This removes the current manual burden on operators when a
schema version bumps (e.g. `mission.v5` → `mission.v6`).

## Motivation

Every schema version change today requires operators to manually update their
YAML files, read the changelog, and re-run validation to discover what changed.
There is no automated path. As the project moves toward operational use, schema
stability and a clear migration story become critical for adoption.

The current schema surfaces that operators write directly include:

| Schema | Version | Input file |
|--------|---------|------------|
| mission | v5 | `mission.yaml` |
| vehicle | v3 | `vehicle.yaml` |
| scenario | v1 | `scenario.yaml` |
| uncertainty | v1 | `uncertainty.yaml` |
| stochastic | v1 | `stochastic.yaml` |
| batch manifest | v1 | `batch.yaml` |

When any of these bumps, operators currently have no machine-readable path to
upgrade their files.

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

The command reads the YAML, inspects `schema_version` / `format_version`
fields, and selects the appropriate migration path. Files with no version field
are treated as the oldest known format for that file type.

Vehicle and mission files have no `schema_version` field at the root — their
version is implied by the content structure. The command should detect version
by attempting `model_validate` against the current schema and reporting the
first unknown field or structural difference.

### Migration registry

A migration is a pure function `(dict) → dict` registered against a
`(schema_name, from_version, to_version)` triple:

```python
@register_migration("mission", from_version="v4", to_version="v5")
def migrate_mission_v4_to_v5(payload: dict) -> dict:
    # e.g. rename field, add default, restructure nested key
    ...
```

Migrations are chained automatically: `v3 → v4 → v5` applies both functions
in sequence. This means each migration only needs to handle one version step.

### YAML preservation

The migrated output should preserve comments and key ordering where possible.
Use `ruamel.yaml` (already available in many environments) if comment
preservation is important; otherwise fall back to `pyyaml` with `sort_keys=False`.

### Acceptance criteria

1. `bvlos-sim migrate --help` shows usage and exits 0.
2. `bvlos-sim migrate mission.v4.yaml --dry-run` prints the detected version,
   the target version, and the fields that would change; does not write.
3. `bvlos-sim migrate mission.v4.yaml --output mission.v5.yaml` writes a file
   that passes `bvlos-sim estimate mission.v5.yaml vehicle.yaml --validate-only`.
4. `bvlos-sim migrate mission.v5.yaml --dry-run` reports "already at latest version"
   and exits 0.
5. `bvlos-sim migrate nonexistent.yaml` exits 11 (invalid input).
6. Migration functions are unit-tested in isolation against known before/after payloads.
7. At least one real migration is implemented (whichever schema version bump
   ships first after this ticket).

## Composition

- New `adapters/commands/migrate.py` registered on the CLI app.
- New `adapters/migration/` package containing the registry and migration
  functions for each schema type.
- No changes to existing schemas, envelopes, or CLI commands.
- `docs/USAGE.md` updated with a `## Schema Migration` section.
- `CONTRIBUTING.md` updated with instructions for writing a migration function
  when a schema version bumps.
