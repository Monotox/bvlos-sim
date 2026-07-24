"""Compatibility exports for static population grid loading."""

from bvlos_sim.adapters.assets.population_grid import (
    PopulationGridLoadError,
    load_population_grid,
)

__all__ = ["PopulationGridLoadError", "load_population_grid"]
