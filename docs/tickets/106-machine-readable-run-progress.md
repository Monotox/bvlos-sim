# Ticket 106: Machine-Readable Run Progress for Long Commands

## Status

Planned.

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
