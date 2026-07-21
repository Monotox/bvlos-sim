"""Atomic output writes and clean cancellation (Ticket 104)."""

import os
import signal
from pathlib import Path

import pytest

import adapters.atomic_write as atomic_write_module
from adapters.atomic_write import AtomicWriteDurabilityError, atomic_write_text
from adapters.cli import (
    CliExitCode,
    _handle_cancellation_signal,
    install_cancellation_handlers,
)


# --- atomic_write_text ----------------------------------------------------


def test_atomic_write_creates_file_with_content(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write_text(target, '{"ok": true}\n')
    assert target.read_text(encoding="utf-8") == '{"ok": true}\n'


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_preserves_existing_permissions(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new")

    assert target.stat().st_mode & 0o777 == 0o640


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write_text(target, "content")
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_failed_write_preserves_original_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.json"
    target.write_text("prior", encoding="utf-8")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "partial-data-that-must-not-land")

    # The destination keeps its prior content, never a truncated write...
    assert target.read_text(encoding="utf-8") == "prior"
    # ...and the temp file is cleaned up.
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_missing_parent_directory_raises_oserror(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "out.json"
    with pytest.raises(OSError):
        atomic_write_text(target, "content")


def test_directory_fsync_failure_reports_already_committed_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "out.json"
    target.write_text("prior", encoding="utf-8")

    def _fail_directory_fsync(_directory: Path) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(
        atomic_write_module,
        "_fsync_directory",
        _fail_directory_fsync,
    )

    with pytest.raises(AtomicWriteDurabilityError) as exc_info:
        atomic_write_text(target, "new")

    assert exc_info.value.committed is True
    assert target.read_text(encoding="utf-8") == "new"


# --- cancellation signal handling -----------------------------------------


def test_cancellation_handler_exits_with_cancelled_code() -> None:
    with pytest.raises(SystemExit) as excinfo:
        _handle_cancellation_signal(signal.SIGTERM, None)
    assert excinfo.value.code == int(CliExitCode.CANCELLED)
    assert int(CliExitCode.CANCELLED) == 14


def test_install_cancellation_handlers_registers_both_signals() -> None:
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        install_cancellation_handlers()
        assert signal.getsignal(signal.SIGTERM) is _handle_cancellation_signal
        assert signal.getsignal(signal.SIGINT) is _handle_cancellation_signal
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
