"""Tool version lookup for adapter outputs."""

import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path


def tool_version() -> str:
    """Return the installed bvlos-sim package version."""
    try:
        return importlib_metadata.version("bvlos-sim")
    except importlib_metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])
