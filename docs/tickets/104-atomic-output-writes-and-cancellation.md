# Ticket 104: Atomic Output Writes and Clean Cancellation

## Status

Planned.

## Goal

Guarantee that a killed or interrupted run never leaves a truncated `--output`
file, and that termination produces a defined outcome. A backend worker may kill
a run on user cancel or timeout; today that can corrupt the exact file the worker
then reads back.

## Why This Matters

`_write_output` truncates the destination in place with `Path.write_text` and no
temp-then-rename (`adapters/cli_support.py:504-511`). A `SIGTERM`/`SIGINT`
arriving mid-write leaves a partial JSON document at the output path, and the
consuming backend cannot tell a partial file from a complete one. There is no
signal handling in non-test code — a search for `signal`/`SIGTERM`/`SIGINT`/
`KeyboardInterrupt`/`atexit` across `adapters/` and `estimator/` returns nothing —
so `SIGTERM` terminates the process with no defined `CliExitCode`, and `SIGINT`
raises `KeyboardInterrupt` (a `BaseException`) that bypasses every
`except Exception` handler and exits `130`.

## Scope

- Make `_write_output` atomic: write to a sibling temp file in the destination
  directory, `fsync`, then `os.replace()` onto the target. A killed process then
  leaves either the prior file or nothing, never a truncated one.
- Apply the same temp-then-replace to the other on-disk writers
  (`adapters/phase_segmentation/io.py`, `adapters/validation/io.py`,
  `adapters/flight_log/io.py`, `adapters/calibration/io.py`,
  `adapters/sitl/artifacts.py`).
- Install a `SIGTERM` handler at the Typer entrypoint (`main.py` /
  `adapters/cli.py`) that exits with a dedicated documented code (add
  `CliExitCode.CANCELLED`, e.g. `14`) and writes no partial envelope; route
  `SIGINT` to the same outcome.
- Document the cancellation contract alongside the exit-code table in Ticket 103.

## Acceptance Criteria

- Interrupting any command mid-write never leaves a partial `--output` file; the
  destination is either the prior content or absent.
- `SIGTERM`/`SIGINT` during a run exits with the documented cancellation code and
  writes no output file.
- The atomic-write change does not alter output bytes for a normal run; golden
  fixtures are unchanged.
- New tests cover the temp-then-replace path and the signal exit code.

## Out of Scope

- A partial-result envelope on interruption. A clean abort with no output file is
  the safer contract for a consuming backend and is what this ticket implements.

## Notes

- The atomic-write half is the high-value correctness fix and is independent of
  the signal-handling half; either can ship first.
- Adding `CliExitCode.CANCELLED` is an additive contract change — record it in
  `docs/CLI_EXIT_CODES.md` and `docs/VERSIONING_POLICY.md` in the same commit.
