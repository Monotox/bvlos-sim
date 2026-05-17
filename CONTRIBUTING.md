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

## Public Contract Changes

The public contract surfaces must not change casually. These include:

- schema versions such as `mission.v5`, `vehicle.v3`, and `scenario.v1`
- canonical JSON envelopes such as `estimator-envelope.v5` and `scenario-report.v2`
- CLI exit codes
- documented package-root imports from `estimator`

If a contract change is intentional, follow
[docs/VERSIONING_POLICY.md](./docs/VERSIONING_POLICY.md): bump the relevant
version identifier, update golden fixtures, update regression tests, and update
the user-facing docs in the same change.
