"""Tool version lookup for adapter outputs."""

import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path


def tool_version() -> str:
    """Return the installed bvlos-sim package version."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])
    try:
        return importlib_metadata.version("bvlos-sim")
    except importlib_metadata.PackageNotFoundError:
        return "0+unknown"
