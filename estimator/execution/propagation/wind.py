"""Wind-provider composition helpers for sampled uncertainty components."""

from dataclasses import dataclass

from estimator.core.results import WindVector
from estimator.environment.wind import WindProvider


@dataclass(frozen=True, slots=True)
class ComponentOverrideWindProvider:
    """Override sampled wind components while preserving the base provider."""

    wind_east_mps: float | None
    wind_north_mps: float | None
    base_provider: WindProvider | None
    provider_id: str = "component-override"

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        needs_base = self.wind_east_mps is None or self.wind_north_mps is None
        base = (
            self.base_provider.wind_at(
                lat=lat,
                lon=lon,
                altitude_amsl_m=altitude_amsl_m,
                elapsed_time_s=elapsed_time_s,
            )
            if needs_base and self.base_provider is not None
            else WindVector(wind_east_mps=0.0, wind_north_mps=0.0)
        )
        return WindVector(
            wind_east_mps=(
                self.wind_east_mps
                if self.wind_east_mps is not None
                else base.wind_east_mps
            ),
            wind_north_mps=(
                self.wind_north_mps
                if self.wind_north_mps is not None
                else base.wind_north_mps
            ),
        )


def build_component_override_wind_provider(
    east: float | None,
    north: float | None,
    base_provider: WindProvider | None,
) -> WindProvider | None:
    """Return a provider that replaces only the components that were sampled."""
    if east is None and north is None:
        return base_provider
    return ComponentOverrideWindProvider(
        wind_east_mps=east,
        wind_north_mps=north,
        base_provider=base_provider,
    )


__all__ = [
    "ComponentOverrideWindProvider",
    "build_component_override_wind_provider",
]
