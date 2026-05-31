"""Tool version lookup for adapter outputs."""

import os
import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path

# When set, overrides the resolved tool version everywhere outputs embed it.
# The test suite pins this to a placeholder so golden fixtures stay version-agnostic
# and a release version bump never churns them (Ticket 098, strategy B).
TOOL_VERSION_ENV = "BVLOS_SIM_TOOL_VERSION"


def tool_version() -> str:
    """Return the bvlos-sim version embedded in generated outputs.

    Honors the ``BVLOS_SIM_TOOL_VERSION`` override first, then the version in
    ``pyproject.toml``, then installed-package metadata.
    """
    override = os.environ.get(TOOL_VERSION_ENV)
    if override:
        return override
    return resolved_package_version()


def resolved_package_version() -> str:
    """Return the version from ``pyproject.toml`` or installed metadata, ignoring overrides."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])
    try:
        return importlib_metadata.version("bvlos-sim")
    except importlib_metadata.PackageNotFoundError:
        return "0+unknown"
