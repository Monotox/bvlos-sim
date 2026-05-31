# Ticket 103: Backend-Facing CLI Exit-Code Contract

## Status

Planned.

## Goal

Document the exit code of every command in one authoritative place and close the
holes that let an unexpected exception escape as a bare shell status. A
long-running caller — the Mission Control worker — branches on the exit code, and
today the meanings are spread across `docs/USAGE.md` prose and four independent
code definitions.

## Why This Matters

`docs/VERSIONING_POLICY.md` lists "CLI exit-code semantics" as a public contract
(line 26) and forbids changing exit-code meanings (line 40), yet no file
enumerates, per command, which of `{0, 10, 11, 12, 13}` it can return. A backend
that assumes `estimate`'s convention (10 = infeasible NO-GO) holds everywhere
will misread results:

- `sample` and `propagate` always exit `0` once a run completes — an infeasible
  Monte Carlo or stochastic outcome is reported in the envelope body, never via
  `10` (`adapters/commands/sample.py:93`, `adapters/commands/propagate.py:93`).
- `scenario` collapses every non-`PASSED` outcome to `10`; `ScenarioExitCode` has
  no `12`, so an unsupported scenario exits `10` while the same condition under
  `estimate` exits `12` (`adapters/cli.py:26-31`,
  `adapters/commands/scenario.py:152-155`).
- `estimate` is the only long-running command that returns `12` for a
  feasibility-class outcome, and it returns `11` for a computed
  `FailureKind.INVALID_INPUT` even when the input files are valid
  (`adapters/commands/estimate.py:50-53,235-241`).
- `sora`, `size-battery`, `sitl`, `export`, `convert`, `validate`, and
  `calibrate` never return `10`; a NO answer lives in the body.

`validate`, `sora`, and `calibrate` also have no catch-all handler, so an
unexpected exception escapes as an uncaught traceback and shell status `1`, which
is not a defined `CliExitCode` (`adapters/commands/validate.py:137-142`,
`sora.py:95-100`, `calibrate.py:86-91`; compare `sample.py:113-120`, which catches
it).

## Scope

- Add `docs/CLI_EXIT_CODES.md`: a per-command table mapping each command to the
  exact subset of `{0,10,11,12,13}` it can emit and the meaning, with the
  divergences above stated explicitly. Reference it from the "CLI exit-code
  semantics" entry in `docs/VERSIONING_POLICY.md`.
- Add the `except typer.Exit: raise` then `except Exception -> INTERNAL_ERROR(13)`
  tail to `validate`, `sora`, and `calibrate`, matching the pattern already in
  `sample`/`propagate`, so an unexpected error is a documented `13` rather than a
  bare traceback. The leading `except typer.Exit: raise` is required so the
  success exit is not swallowed by the catch-all.
- Optionally consolidate the four exit-code definitions (`CliExitCode`,
  `ScenarioExitCode`, `cli_sitl_support._EXIT_*`, and the hardcoded ints in
  `cli_batch_support._batch_exit_code`) onto one shared enum to stop future drift.
- Add a short "programmatic callers" note to the new doc: pass absolute `--output`
  paths, do not register the developer-only `bump` command in a service surface,
  and do not set `BVLOS_SIM_TOOL_VERSION` in the worker environment — it overrides
  the version embedded in every envelope (`adapters/version.py:20-22`).

## Acceptance Criteria

- `docs/CLI_EXIT_CODES.md` lists every command and its possible exit codes; the
  three divergences (sample/propagate always 0, scenario never 12, estimate 11 on
  a computed invalid input) are called out.
- `validate`, `sora`, and `calibrate` return `13` on an unexpected exception
  instead of an uncaught traceback; their success exit is unchanged.
- `docs/VERSIONING_POLICY.md` references the table.
- Existing tests pass; new tests assert the `13` path for the three commands.

## Out of Scope

- Changing any existing exit-code value or the meaning of `0/10/11/12/13`. This
  ticket documents and hardens the current contract; it does not alter it.
- Giving `scenario` a `12`; that is a contract change and needs its own version
  decision.
