# CLI Exit Codes

This is the authoritative, per-command map of the process exit codes the
`bvlos-sim` CLI can return. The exit-code semantics are a public contract (see
[`VERSIONING_POLICY.md`](VERSIONING_POLICY.md)); their meanings do not change
within a published version.

A long-running caller (such as a Mission Control worker) branches on the exit
code, so it must not assume one command's convention holds for another. The
divergences below are intentional and are called out explicitly.

## Code meanings

| Code | Name             | Meaning                                                              |
| ---- | ---------------- | ------------------------------------------------------------------- |
| `0`  | `SUCCESS`        | The command completed. A feasibility verdict, if any, is in the body. |
| `10` | `INFEASIBLE`     | A feasibility-class NO-GO outcome (e.g. estimate reports infeasible). |
| `11` | `INVALID_INPUT`  | Input files, arguments, or referenced assets failed to load or validate. |
| `12` | `UNSUPPORTED`    | The requested computation is not supported for these inputs.        |
| `13` | `INTERNAL_ERROR` | An output could not be written, or an unexpected error occurred.    |
| `14` | `CANCELLED`      | The run received `SIGTERM`/`SIGINT` and aborted; no output was written. |

Every command returns `13` rather than a bare traceback (shell status `1`) when
an unexpected exception escapes. A shell status `2` comes from the argument
parser (Typer/Click) for malformed invocations (unknown option, missing
argument); it is not one of the codes above.

## Cancellation contract

Any command may receive `SIGTERM` or `SIGINT` (e.g. a worker cancelling a job or
enforcing a timeout). When it does:

- The process exits `14` (`CANCELLED`) instead of the shell defaults (`143` for
  `SIGTERM`, `130` for `SIGINT`), so a caller can branch on a defined code.
- No `--output` file is left in a partial state. All on-disk writes go through an
  atomic temp-file-then-`os.replace`, so an interrupted run leaves the
  destination either at its prior content or absent — never truncated. A consumer
  can therefore trust that any file that exists is complete.

The `CANCELLED` code is only installed by the console-script entrypoint
(`main:main`); importing the Typer app in-process (as the test runner does) keeps
Python's default `KeyboardInterrupt` behaviour.

## Per-command exit codes

| Command        | `0` | `10` | `11` | `12` | `13` | Notes                                                       |
| -------------- | :-: | :--: | :--: | :--: | :--: | ----------------------------------------------------------- |
| `estimate`     |  ✓  |  ✓   |  ✓   |  ✓   |  ✓   | Full feasibility surface. `11` can also be a *computed* `FailureKind.INVALID_INPUT` (see divergences). |
| `scenario`     |  ✓  |  ✓   |  ✓   |      |  ✓   | No `12`: every non-`PASSED` outcome collapses to `10` (divergence). |
| `sample`       |  ✓  |      |  ✓   |      |  ✓   | Never `10`: an infeasible Monte Carlo result is in the body, exit is `0` (divergence). |
| `propagate`    |  ✓  |      |  ✓   |      |  ✓   | Never `10`: an infeasible stochastic result is in the body, exit is `0` (divergence). |
| `size-battery` |  ✓  |      |  ✓   |      |  ✓   | A NO answer (no feasible capacity) is in the body, not via `10`. |
| `sora`         |  ✓  |      |  ✓   |      |  ✓   | SAIL / risk verdict is in the body, not via `10`.           |
| `validate`     |  ✓  |      |  ✓   |      |  ✓   | Comparison metrics are in the body; a poor match is not `10`. |
| `calibrate`    |  ✓  |      |  ✓   |      |  ✓   | Fitted profile is in the body.                              |
| `compare`      |  ✓  |  ✓   |  ✓   |  ✓   |  ✓   | SITL drift/fail maps to `10`; unsupported comparison maps to `12`. |
| `batch`        |  ✓  |  ✓   |  ✓   |      |  ✓   | `10` if any run is infeasible; `11` if any run failed to load. No `12`. |
| `export`       |  ✓  |      |  ✓   |      |  ✓   | Mission load / exportability failures are `11`.             |
| `convert`      |  ✓  |      |  ✓   |      |  ✓   | A missing/blank `--vehicle-profile` and parse errors are `11`. |
| `sitl`         |  ✓  |      |  ✓   |      |  ✓   | Adapter and asset-load errors are `11`.                     |
| `bump`         |  ✓  |      |  ✓   |      |      | Developer-only release tool. `11` on drift or a missing version part. |
| `schema-versions` |  ✓  |      |      |      |      | Read-only contract discovery (alias `contracts`). Loads no input; always `0`. |

## Divergences to branch on carefully

These are the cases where a caller that assumes `estimate`'s convention will
misread a result:

1. **`sample` and `propagate` always exit `0` once a run completes.** An
   infeasible Monte Carlo or stochastic outcome is reported in the envelope
   body, never via `10`. Read the body's feasibility field; do not rely on the
   exit code for a NO-GO.
2. **`scenario` has no `12`.** Every non-`PASSED` outcome — including an
   unsupported scenario — collapses to `10`. The same unsupported condition
   under `estimate` exits `12`. Giving `scenario` a `12` is a deliberate future
   contract change, not a bug.
3. **`estimate` returns `11` for a computed `FailureKind.INVALID_INPUT`** even
   when the input *files* are valid. So `11` from `estimate` means "invalid
   input *or* an input-class feasibility failure"; inspect the body to tell them
   apart.

## Notes for programmatic callers

- **Pass absolute `--output` paths.** Relative paths resolve against the
  worker's current directory, which is rarely what you intend.
- **Do not register the `bump` command in a service surface.** It is a
  developer-only release tool that edits `pyproject.toml` and `CHANGELOG.md`.
- **Do not set `BVLOS_SIM_TOOL_VERSION` in the worker environment.** It
  overrides the version embedded in every envelope and is meant only for the
  test suite (it pins fixtures to a placeholder). In production the version must
  reflect the installed package.
- **Treat any code outside `{0, 10, 11, 12, 13}` as a harness fault.** Shell
  status `1` (an uncaught traceback) and `2` (argument-parser error) are not
  part of this contract; if you see `1`, file it as a bug.
