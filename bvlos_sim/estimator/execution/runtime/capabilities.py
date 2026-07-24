"""Execution-only capability models."""

from dataclasses import dataclass

from bvlos_sim.estimator.core.enums import CapabilitySource


@dataclass(frozen=True)
class Capabilities:
    hover: bool
    forward_flight: bool
    source: CapabilitySource
