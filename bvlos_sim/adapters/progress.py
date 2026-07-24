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
import os
import sys
import time
from collections.abc import Iterable, Iterator
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

    def __call__(
        self, completed: int, total: int, label: str | None = None
    ) -> None:
        if self._final_emitted:
            return
        step = self._interval if self._interval is not None else _emit_interval(total)
        is_final = completed >= total
        if is_final or completed - self._last_emitted >= step:
            self._emit(completed, total, label)
            self._last_emitted = completed
            self._final_emitted = is_final

    def _emit(self, completed: int, total: int, label: str | None) -> None:
        record = {
            "event": "progress",
            "command": self._command,
            "completed": completed,
            "total": total,
            "elapsed_s": round(time.monotonic() - self._start, 3),
        }
        if label is not None:
            # For batch runs the label is the id of the run that just
            # completed, so a worker tailing the stream can attribute stalls.
            record["run_id"] = label
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
    protected_paths: Iterable[Path | None] = (),
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
        progress_target = progress_file.resolve(strict=False)
        protected_identities: set[tuple[int, int]] = set()
        for protected_path in protected_paths:
            if protected_path is None:
                continue
            if progress_target == protected_path.resolve(strict=False):
                raise ValueError(
                    f"Progress file {progress_file} would overwrite an input or output file"
                )
            try:
                protected_stat = protected_path.stat()
            except FileNotFoundError:
                continue
            protected_identities.add((protected_stat.st_dev, protected_stat.st_ino))
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(progress_file, flags, 0o666)
        try:
            target_stat = os.fstat(descriptor)
            if (target_stat.st_dev, target_stat.st_ino) in protected_identities:
                raise ValueError(
                    f"Progress file {progress_file} would overwrite an input or output file"
                )
            os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                yield ProgressReporter(handle, command)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        return
    yield ProgressReporter(sys.stderr, command)


__all__ = ["ProgressReporter", "progress_reporter"]
