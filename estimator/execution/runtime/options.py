"""Execution-only resolved option models."""

from dataclasses import dataclass

from estimator.core.enums import FidelityMode, OptionSource


@dataclass(frozen=True)
class ResolvedOptions:
    wind_east_mps: float
    wind_north_mps: float
    min_groundspeed_mps: float
    options_source: OptionSource
    max_segment_length_m: float | None = None
    fidelity: FidelityMode = FidelityMode.V1
