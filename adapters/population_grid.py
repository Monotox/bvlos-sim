"""Compatibility exports for static population grid loading."""

from adapters.assets.population_grid import (
    PopulationGridLoadError,
    load_population_grid,
)

__all__ = ["PopulationGridLoadError", "load_population_grid"]
