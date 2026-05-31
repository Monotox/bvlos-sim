# Ticket 098: Version Bump and Release Tooling

## Status

Implemented.

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

---

## Implementation

**Status:** implemented (strategy B — version-agnostic fixtures).

### New / changed files

| File | Change |
|---|---|
| `adapters/release.py` | New — pure semver/changelog/consistency helpers (`bump_version`, `read_pyproject_version`, `set_pyproject_version`, `roll_changelog`, `latest_git_tag`, `check_consistency`, `plan_bump`, `apply_bump`) |
| `adapters/commands/bump.py` | New — `bump` CLI command (`<part>`, `--dry-run`, `--check`) |
| `adapters/cli.py` | Register `bump` |
| `adapters/version.py` | `tool_version()` honours a `BVLOS_SIM_TOOL_VERSION` override; `resolved_package_version()` exposes the real version |
| `conftest.py` | New — pins `BVLOS_SIM_TOOL_VERSION=0.0.0-test` for the whole suite |
| `tests/fixtures/golden/**` | 16 fixtures rewritten from the embedded release version to `0.0.0-test` |
| `tests/test_bump_version.py` | New — 24 tests (semver, pyproject edit, changelog roll, consistency, dry-run/apply, CLI, pinned-version) |

### Fixture strategy (B)

`tool_version()` now reads the `BVLOS_SIM_TOOL_VERSION` env var first. `conftest.py`
sets it to `0.0.0-test` before any adapter imports, so every generated envelope and
Markdown report embeds a fixed placeholder during tests. The 16 golden fixtures were
rewritten once to that placeholder. A version bump therefore no longer touches any
fixture, and releasing can never break the golden suite. The live version is asserted
separately in `test_bump_version.py` via `resolved_package_version()`.

### Command

```bash
bvlos-sim bump patch --dry-run   # show next version + edits, write nothing
bvlos-sim bump minor             # edit pyproject.toml + roll CHANGELOG.md, print next steps
bvlos-sim bump --check           # CI: fail if pyproject.toml is behind the latest git tag
```

`bump` edits only `pyproject.toml` and `CHANGELOG.md` and prints the suggested
`git commit`/`git tag`/`git push` follow-ups; it never tags, pushes, or publishes.
Exit codes: `0` success/consistent, `11` invalid input or detected drift.
