"""Atomic file writes (Ticket 104).

A killed or interrupted process must never leave a truncated artifact at a path a
consuming backend then reads. ``atomic_write_text`` writes to a sibling temp file
in the destination directory, flushes it to disk, then ``os.replace``s it onto the
target. ``os.replace`` is atomic on POSIX within a single filesystem, so an
interrupted run leaves either the prior file or nothing — never a partial one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_text"]


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    The temp file is created in ``path``'s parent directory so the final
    ``os.replace`` stays within one filesystem (a cross-device rename is not
    atomic). On any failure the temp file is removed and the original ``OSError``
    propagates; the destination is left untouched.
    """
    directory = path.parent
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        dir=directory,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
