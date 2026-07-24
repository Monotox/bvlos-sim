"""Command modules must be importable without the command registry."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMAND_MODULES = sorted(
    f"adapters.commands.{path.stem}"
    for path in (_REPO_ROOT / "adapters" / "commands").glob("*.py")
    if path.stem != "__init__"
)


def test_command_modules_are_discovered() -> None:
    assert len(_COMMAND_MODULES) >= 15


@pytest.mark.parametrize("module", [*_COMMAND_MODULES, "adapters.preflight"])
def test_module_imports_standalone(module: str) -> None:
    """Importing one command must not pull in every other command.

    adapters.cli registers every command at import time, so a command module
    that imported adapters.cli could not be imported first: the registry tried
    to read a name back out of the half-initialised module. Each command now
    depends on the leaf adapters.cli_contract instead.
    """

    # A subprocess so the already-imported test session cannot mask the cycle.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_cli_contract_does_not_import_commands() -> None:
    """The leaf must stay a leaf, or the cycle comes straight back."""

    source = (_REPO_ROOT / "adapters" / "cli_contract.py").read_text(encoding="utf-8")
    assert "adapters.commands" not in source
    assert "adapters.cli " not in source
    importlib.import_module("adapters.cli_contract")
