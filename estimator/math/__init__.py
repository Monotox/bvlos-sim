"""Math and geometry helpers for estimator internals."""

from estimator.math.atmosphere import isa_air_density_kgm3
from estimator.math.wind_triangle import (
    WindTriangleSolution,
    normalize_deg,
    normalize_signed,
    solve_wind_triangle,
)

__all__ = [
    "WindTriangleSolution",
    "isa_air_density_kgm3",
    "normalize_deg",
    "normalize_signed",
    "solve_wind_triangle",
]
