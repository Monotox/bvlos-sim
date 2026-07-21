# Ticket 104: Atomic Output Writes and Clean Cancellation

## Status

Implemented.

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
- `SIGTERM`/`SIGINT` during a run exits with the documented cancellation code;
  output is never partial, though a signal after the atomic commit may leave the
  new complete artifact present.
- The atomic-write change does not alter output bytes for a normal run; golden
  fixtures are unchanged.
- New tests cover the temp-then-replace path and the signal exit code.

## Out of Scope

- A partial-result envelope on interruption. Consumers use the exit code to
  distinguish a completed command from a cancellation even when a fully committed
  artifact exists.

## Notes

- The atomic-write half is the high-value correctness fix and is independent of
  the signal-handling half; either can ship first.
- Adding `CliExitCode.CANCELLED` is an additive contract change — record it in
  `docs/CLI_EXIT_CODES.md` and `docs/VERSIONING_POLICY.md` in the same commit.

## Implementation

| File | Change |
| --- | --- |
| `adapters/atomic_write.py` | New `atomic_write_text(path, text)`: temp file in the destination directory → `flush` + `os.fsync` → `os.replace`; cleans up the temp file and re-raises on any failure. |
| `adapters/cli_support.py` | `_write_output` routes file writes through `atomic_write_text` (stdout path unchanged). |
| `adapters/flight_log/io.py`, `validation/io.py`, `phase_segmentation/io.py`, `calibration/io.py`, `sitl/artifacts.py` | The five other on-disk writers now use `atomic_write_text`. |
| `adapters/cli.py` | Added `CliExitCode.CANCELLED = 14`, `_handle_cancellation_signal` (raises `SystemExit(14)`), and `install_cancellation_handlers()` routing `SIGTERM`/`SIGINT` to it. |
| `main.py` | The console-script entrypoint installs the cancellation handlers before running the app. |
| `docs/CLI_EXIT_CODES.md`, `docs/VERSIONING_POLICY.md`, `docs/USAGE.md` | Documented the `14`/`CANCELLED` code and the atomic-write guarantee. |
| `tests/test_atomic_write.py` | Covers the temp-then-replace path, no-leftover-temp-files, original-preserved-on-failure, the missing-parent error, and the signal exit code / handler registration. `tests/test_cli.py`'s output-write-failure test was retargeted from `Path.write_text` to `os.replace`. |

The signal handlers are installed only by the console-script entrypoint, not at
import, so the in-process Typer test runner keeps Python's default
`KeyboardInterrupt` behaviour and existing tests are unaffected. The atomic-write
change does not alter output bytes for a normal run, so the golden fixtures are
unchanged.
