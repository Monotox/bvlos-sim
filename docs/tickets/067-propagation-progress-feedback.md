# Ticket 067: Propagation Progress Feedback

## Goal

Emit periodic progress lines to stderr during `propagate` runs so operators
know the command is still working. With 500–10 000 samples and a 2-second
time step, a propagation can take tens of seconds to minutes with no output.
Silent progress is a common source of confusion and premature Ctrl-C.

## Motivation

`propagate` is the slowest command in the tool. A run with 1 000 samples and
`dt_s = 1.0` over a 3-minute mission processes ~180 000 physics ticks with
zero terminal feedback. Operators running this in a CI gate or pre-flight
check assume the command hung. A simple progress line — `propagating  250/1000
samples  25%  0.3 s/sample  ETA 2m 15s` — costs nothing in output terms and
eliminates the ambiguity.

## Design

Progress is written to stderr, not stdout, so it does not contaminate the JSON
output when `--format json --output /dev/stdout` is used. Progress is suppressed
when stderr is not a TTY (e.g., piped into a log file) unless `--progress` is
explicitly passed.

Emit a progress line:
- After the first sample completes (to show rate immediately)
- Every 5 % of total samples thereafter
- After the final sample, with total elapsed time

Example output:

```
propagating    50/1000 samples   5%   0.31 s/sample   ETA 2m 54s
propagating   100/1000 samples  10%   0.30 s/sample   ETA 2m 42s
...
propagating  1000/1000 samples 100%   0.30 s/sample   2m 58s elapsed
```

## Implementation Path

1. Add a `ProgressCallback` protocol to `estimator/execution/propagator.py`:
   ```python
   class ProgressCallback(Protocol):
       def __call__(self, *, completed: int, total: int, elapsed_s: float) -> None: ...
   ```
2. Thread the callback through `run_stochastic_propagation` and call it
   after each sample completes.
3. In `adapters/cli.py`, the `propagate` command creates a stderr-writing
   callback and passes it to `run_stochastic_propagation`.
4. Add `--progress / --no-progress` flag (default: `--progress` when TTY).

## Acceptance Criteria

1. `propagate` with 50+ samples writes at least one progress line to stderr.
2. Progress lines do not appear in `--output file.json` JSON output.
3. Progress lines are suppressed when stderr is not a TTY and `--progress`
   is not passed.
4. `--no-progress` fully suppresses all progress output.
5. `ProgressCallback` protocol is tested via a mock callback that records
   calls: call count ≥ 1, completed values are monotonically increasing,
   final call has `completed == total`.

## Scope

- `estimator/execution/propagator.py` — `ProgressCallback` protocol and
  callback wiring in `_ParticleSampler.run()`
- `adapters/cli.py` — `--progress / --no-progress` flag, stderr callback
  builder, rate and ETA formatting
- `tests/test_stochastic_propagator.py` — callback invocation tests

## Notes

- The callback has zero overhead when not wired (default `None`).
- Do not use `tqdm` or any third-party progress library — keep the
  dependency footprint clean.
- The progress line format uses `\r` and ANSI clear-to-EOL if TTY, so
  the cursor stays on one line; otherwise each line ends with `\n`.
- This ticket has no impact on the JSON output contract or golden fixtures.
