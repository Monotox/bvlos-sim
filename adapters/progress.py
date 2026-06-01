"""Machine-readable run progress for long commands (Ticket 106).

A small, dependency-free progress side-channel for the long-running loops
(``propagate``, ``sample``, ``batch``). When enabled, one compact JSON object is
written per emit interval plus a guaranteed final record where
``completed == total``:

    {"event":"progress","command":"propagate","completed":250,"total":1000,"elapsed_s":75.3}

Records go to stderr or a sidecar file, NEVER to the ``--output`` stream, and the
feature is opt-in. When disabled the command passes ``None`` as the callback, so
the hot loop pays nothing beyond a single ``is not None`` check.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

# Target number of progress records over a run when no explicit interval is set.
# The reporter derives the per-tick interval from this and the run's total so a
# 1,000-sample run emits roughly one line per 5% rather than 1,000 lines.
_DEFAULT_RECORD_TARGET = 20


class ProgressReporter:
    """Emits JSONL progress records to a sink at a fixed completed-count interval.

    Call the instance as ``reporter(completed, total)`` once per finished
    iteration. It emits when at least ``interval`` iterations have completed since
    the last record, and always emits the final ``completed == total`` record.
    ``elapsed_s`` is wall-clock seconds from construction, via a monotonic clock.
    """

    def __init__(
        self,
        sink: TextIO,
        command: str,
        *,
        interval: int | None = None,
    ) -> None:
        self._sink = sink
        self._command = command
        self._interval = interval
        self._start = time.monotonic()
        self._last_emitted = 0
        self._final_emitted = False

    def __call__(self, completed: int, total: int) -> None:
        if self._final_emitted:
            return
        step = self._interval if self._interval is not None else _emit_interval(total)
        is_final = completed >= total
        if is_final or completed - self._last_emitted >= step:
            self._emit(completed, total)
            self._last_emitted = completed
            self._final_emitted = is_final

    def _emit(self, completed: int, total: int) -> None:
        record = {
            "event": "progress",
            "command": self._command,
            "completed": completed,
            "total": total,
            "elapsed_s": round(time.monotonic() - self._start, 3),
        }
        self._sink.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._sink.flush()


def _emit_interval(total: int) -> int:
    return max(1, total // _DEFAULT_RECORD_TARGET)


@contextmanager
def progress_reporter(
    command: str,
    *,
    enabled: bool,
    progress_file: Path | None,
) -> Iterator[ProgressReporter | None]:
    """Yield a ProgressReporter when progress is enabled, else ``None``.

    Progress is enabled when ``enabled`` is set or a ``progress_file`` is given.
    With a file the reporter streams JSONL there (opened for live tailing, not an
    atomic replace); otherwise it writes to stderr. The file is always closed on
    exit, even if the wrapped run raises.
    """
    if not enabled and progress_file is None:
        yield None
        return
    if progress_file is not None:
        with progress_file.open("w", encoding="utf-8") as handle:
            yield ProgressReporter(handle, command)
        return
    yield ProgressReporter(sys.stderr, command)


__all__ = ["ProgressReporter", "progress_reporter"]
