"""Atomic file writes (Ticket 104).

A killed or interrupted process must never leave a truncated artifact at a path a
consuming backend then reads. ``atomic_write_text`` writes to a sibling temp file
in the destination directory, flushes it to disk, then ``os.replace``s it onto the
target. ``os.replace`` is atomic on POSIX within a single filesystem, so an
interrupted run leaves either the prior file or nothing — never a partial one.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

__all__ = ["AtomicWriteDurabilityError", "atomic_write_text"]


class AtomicWriteDurabilityError(OSError):
    """Replacement succeeded, but directory durability was not confirmed."""

    committed = True


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    The temp file is created in ``path``'s parent directory so the final
    ``os.replace`` stays within one filesystem (a cross-device rename is not
    atomic). On any failure the temp file is removed and the original ``OSError``
    propagates and the destination is left untouched. If the replacement
    succeeds but directory ``fsync`` fails, ``AtomicWriteDurabilityError`` is
    raised with ``committed = True`` because the new destination is already
    visible even though crash durability could not be confirmed.
    """
    directory = path.parent
    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        pass
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
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)
        os.replace(temp_path, path)
        try:
            _fsync_directory(directory)
        except OSError as exc:
            raise AtomicWriteDurabilityError(
                f"Replaced {path}, but could not fsync directory {directory}"
            ) from exc
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _fsync_directory(directory: Path) -> None:
    """Persist the directory entry after an atomic replacement when supported."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
