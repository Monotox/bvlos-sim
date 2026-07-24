"""Command modules must be importable without the command registry."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMAND_MODULES = sorted(
    f"bvlos_sim.adapters.commands.{path.stem}"
    for path in (_REPO_ROOT / "bvlos_sim" / "adapters" / "commands").glob("*.py")
    if path.stem != "__init__"
)


def test_command_modules_are_discovered() -> None:
    assert len(_COMMAND_MODULES) >= 15


@pytest.mark.parametrize("module", [*_COMMAND_MODULES, "bvlos_sim.adapters.preflight"])
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

    source = (_REPO_ROOT / "bvlos_sim" / "adapters" / "cli_contract.py").read_text(encoding="utf-8")
    assert "bvlos_sim.adapters.commands" not in source
    assert "bvlos_sim.adapters.cli " not in source
    importlib.import_module("bvlos_sim.adapters.cli_contract")


def test_distribution_declares_one_top_level_package() -> None:
    """Generic top-level names collide silently with co-installed packages.

    pip does not detect file conflicts, so shipping ``adapters``/``schemas``/
    ``scripts``/``main`` let any other distribution using those names overwrite
    ours, and ours overwrite theirs, with no warning either way.
    """

    import tomllib

    pyproject = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    setuptools_config = pyproject["tool"]["setuptools"]

    assert setuptools_config["packages"]["find"]["include"] == ["bvlos_sim*"]
    # A bare top-level module is the same hazard as a bare top-level package.
    assert "py-modules" not in setuptools_config

    for entry_point in pyproject["project"]["scripts"].values():
        assert entry_point.startswith("bvlos_sim."), entry_point
