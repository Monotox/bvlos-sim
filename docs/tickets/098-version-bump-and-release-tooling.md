# Ticket 098: Version Bump and Release Tooling

## Status

Planned.

## Goal

Provide a single command — `bvlos-sim bump <major|minor|patch>` (or a
`scripts/bump_version.py`) — that performs a release-ready version bump
atomically and consistently, so cutting a release is one reviewed step instead
of several easy-to-forget manual edits.

## Why This Is High Impact

A release today touches several places that must stay in lock-step, and missing
any one of them produces a broken or misleading release. This was observed
directly when cutting `v0.32.0`:

- `pyproject.toml` had drifted to `0.30.0` while the last git tag was `v0.31.0`
  and the golden fixtures embedded `0.30.0` — three sources of truth, none
  agreeing.
- Bumping the version immediately broke **16 golden-fixture tests**, because the
  estimator/scenario/stochastic/battery envelopes and Markdown reports embed
  `tool_version` (resolved by `adapters/version.py` via
  `importlib.metadata.version("bvlos-sim")`). Every bump silently invalidates
  those fixtures until they are regenerated.

A bump tool removes that footgun and makes releases reproducible and reviewable.

## Current gap

There is no bump command or script. The version lives in `pyproject.toml`, the
human history in `CHANGELOG.md`, the released marker in a git tag, and a copy of
the version in 16 golden fixtures under `tests/fixtures/golden/`. Keeping them
aligned is entirely manual.

## Scope

### Behaviour

`bvlos-sim bump <part>` (part = major | minor | patch), with `--dry-run`:

1. Read the current version from `pyproject.toml`, compute the next version for
   the requested part (semver).
2. Write the new version to `pyproject.toml`.
3. Roll `CHANGELOG.md`: rename the `## [Unreleased]` section to
   `## [X.Y.Z] - <today>` and insert a fresh empty `## [Unreleased]` above it.
4. Refresh the version embedded in golden fixtures so the suite stays green
   (see "Fixture strategy").
5. Print a summary and the suggested follow-up commands (tag + push + release);
   do **not** create the tag or push automatically — keep release side effects
   explicit and operator-controlled.

### Fixture strategy (pick one; (B) preferred)

- **(A) Regenerate**: re-render every version-pinned golden fixture as part of
  the bump. Keeps fixtures exact but couples them to the version.
- **(B) Make fixtures version-agnostic** (recommended): normalise `tool_version`
  to a placeholder (e.g. `"0.0.0-test"`) in the golden-comparison helpers, and
  assert the live version separately in one focused test. After this, a version
  bump no longer churns 16 fixtures, and releases stop being able to break the
  golden suite. The bump tool then only touches `pyproject.toml` and
  `CHANGELOG.md`.

### Consistency check

Add a `--check` mode (usable in CI) that fails if `pyproject.toml`, the latest
git tag, and the fixture version are not consistent — preventing the drift seen
before `v0.32.0`.

### Files to create or modify

| File | Change |
|---|---|
| `adapters/commands/bump.py` (or `scripts/bump_version.py`) | New — bump command/script |
| `adapters/cli.py` | Register `bump` if implemented as a CLI command |
| `tests/test_contract_golden.py` and sibling golden tests | Normalise `tool_version` in comparisons (strategy B) |
| `adapters/version.py` | Optional: expose a test hook / placeholder for normalised fixtures |
| `tests/test_bump_version.py` | New — bump arithmetic, changelog roll, `--check`, `--dry-run` |
| `docs/USAGE.md` | Document the release/bump workflow |
| `CONTRIBUTING.md` | Document the one-command release process |

### Acceptance criteria

1. `bvlos-sim bump patch --dry-run` reports the next version and the exact edits
   without modifying any file.
2. `bvlos-sim bump minor` updates `pyproject.toml` and `CHANGELOG.md` and leaves
   the full test suite green with no manual fixture edits.
3. `bvlos-sim bump --check` exits non-zero when `pyproject.toml`, the latest tag,
   and the fixtures disagree, and zero when they match.
4. The bump command never creates tags, pushes, or publishes a GitHub release on
   its own; it only prints the suggested commands.
5. New unit tests cover semver arithmetic for major/minor/patch and the
   changelog roll.
