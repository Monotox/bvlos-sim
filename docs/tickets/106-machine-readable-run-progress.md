# Ticket 106: Machine-Readable Run Progress for Long Commands

## Status

Implemented.

## Goal

Emit structured, parseable progress during the long-running commands so a
non-interactive caller — a queue worker — can surface live progress to a user
instead of showing a flat "running" until the process exits.

## Why This Matters

`propagate`, `sample`, and `batch` produce nothing until completion: each runs
its loop with no callback, no stderr progress, no progress file, and no logging.
A 1,000-sample propagation runs for minutes with no signal of life. Ticket 067
plans progress for `propagate` only, and as written it targets human-readable TTY
text that is suppressed when stderr is not a TTY
(`docs/tickets/067-propagation-progress-feedback.md:21-24,51`) — which is exactly
the worker case. The `sitl` command (`_emit_sitl_progress` in
`adapters/cli_sitl_support.py`) shows the pattern is feasible but emits
unstructured stage text, not per-iteration machine-readable framing.

## Scope

- Add a `--progress-format=jsonl` mode (and/or `--progress-file PATH`) that emits
  one JSON object per N iterations — for example
  `{"event":"progress","command":"propagate","completed":250,"total":1000,"elapsed_s":75.3}`
  — to stderr or a sidecar file, never to the `--output` stream.
- Thread a progress callback through the propagation sampler
  (`estimator/execution/propagator.py`), the Monte Carlo loop (`run_monte_carlo`),
  and the batch runner (`run_batch_manifest`).
- Treat Ticket 067 as the TTY/human half; this ticket adds the machine-readable,
  non-TTY half and extends coverage to `sample` and `batch`.

## Acceptance Criteria

- `propagate`, `sample`, and `batch` can emit JSONL progress records to stderr or
  a file, with monotonically increasing `completed` and a final record where
  `completed == total`.
- Progress output never appears in the `--output` JSON.
- Progress is opt-in and off by default; a run with no progress flag behaves
  exactly as today.
- The JSON output contract and golden fixtures are unaffected.

## Out of Scope

- A persistent event bus, websocket, or progress transport. This is line-oriented
  stdout/stderr framing only; live delivery to a browser belongs to the consuming
  service.
- Third-party progress libraries (`tqdm` and similar) — keep the dependency
  footprint clean, consistent with Ticket 067.

## Implementation

### New files

| File | Purpose |
|------|---------|
| `adapters/progress.py` | `ProgressReporter` (JSONL emitter) and the `progress_reporter` context manager that binds it to stderr or a file, or yields `None` when disabled. |
| `tests/test_run_progress.py` | CLI progress-file/stderr tests for all three commands, off-by-default invariance, and a direct callback contract on `run_monte_carlo`. |

### Progress helper

`ProgressReporter` is constructed with a sink (an open text stream), the command
name, and an optional explicit interval. It is called once per finished
iteration as `reporter(completed, total)` and emits a record when at least
`interval` iterations have completed since the last one, always emitting the
final `completed == total` record. When no interval is given it derives one from
the total so a run emits roughly 20 records (about one per 5%) rather than one
per iteration. Each record is a single compact line:

```json
{"event":"progress","command":"propagate","completed":250,"total":1000,"elapsed_s":75.3}
```

`json.dumps(..., separators=(",", ":"))` keeps it compact, the sink is flushed
after every line so a worker sees progress live, and `elapsed_s` is wall-clock
seconds from construction via `time.monotonic()` (kept out of anything golden).

`progress_reporter(command, *, enabled, progress_file)` is a context manager:
it yields a reporter bound to the file (opened for live tailing, not an atomic
replace) when `progress_file` is set, else to stderr when `enabled`, else
`None`. The file is always closed on exit, even if the run raises.

### Threaded callback

A keyword-only `progress: Callable[[int, int], None] | None = None` parameter was
added to `run_monte_carlo` (`estimator/execution/monte_carlo.py`),
`run_stochastic_propagation` (`estimator/execution/propagator.py`, forwarded into
`ParticleSampler`), and `run_batch_manifest` (`adapters/batch_support.py`). Each
loop calls `progress(completed, total)` once per iteration with `total` equal to
the plan sample count or `len(manifest.runs)`. Default `None` means no callback
is invoked, so the hot loop pays only a single `is not None` check and behaves
exactly as before. The per-iteration `continue` paths in the Monte Carlo and
particle-sampler loops were refactored to `if/else` so the progress tick fires
on every iteration, including failed/spatial-infeasible samples; the computed
results are unchanged.

### CLI flags

`sample`, `propagate`, and `batch` each gained two flags: `--progress-format`
(a `ProgressFormat` enum, default `none`, set `jsonl` to enable on stderr) and
`--progress-file PATH` (writes the JSONL stream to a file, implying `jsonl`).
The command opens a `progress_reporter` around the run call and passes its
callback (or `None`) down.

### Side-channel only / off by default

Progress goes to stderr or the sidecar file and never to the `--output` stream;
the result envelope, the golden fixtures, and the deterministic results are
unchanged, and no new schema or envelope version is introduced. With no progress
flag a run is byte-for-byte identical to before (covered by a test that compares
the `--output` bytes of a plain run against a progress-enabled run and asserts an
empty stderr). This is the machine-readable, non-TTY half of progress; the human
TTY bar remains Ticket 067's scope and is not implemented here.
