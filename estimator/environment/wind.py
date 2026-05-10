"""Wind provider abstractions."""

from dataclasses import dataclass
from typing import Protocol

from estimator.core.results import WindVector


class WindProvider(Protocol):
    provider_id: str

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        """Return wind vector at a spatiotemporal point."""


class ConstantWindProvider:
    """Provider returning a fixed EN wind vector."""

    provider_id = "constant"

    def __init__(self, wind_east_mps: float, wind_north_mps: float) -> None:
        self.wind_east_mps = float(wind_east_mps)
        self.wind_north_mps = float(wind_north_mps)

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        return WindVector(
            wind_east_mps=self.wind_east_mps,
            wind_north_mps=self.wind_north_mps,
        )


@dataclass(frozen=True)
class WindLayer:
    """A constant wind layer active from `altitude_m` upward."""

    altitude_m: float
    wind_east_mps: float
    wind_north_mps: float


class LayeredWindProvider:
    """Provider returning wind from stacked altitude layers.

    Each layer is active from its `altitude_m` upward to the next layer.
    Queries below the lowest layer's altitude return the lowest layer's wind.
    """

    provider_id = "layered"

    def __init__(self, layers: list[WindLayer]) -> None:
        if not layers:
            raise ValueError("LayeredWindProvider requires at least one layer.")
        self._layers: tuple[WindLayer, ...] = tuple(
            sorted(layers, key=lambda la: la.altitude_m, reverse=True)
        )

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        for layer in self._layers:
            if altitude_amsl_m >= layer.altitude_m:
                return WindVector(
                    wind_east_mps=layer.wind_east_mps,
                    wind_north_mps=layer.wind_north_mps,
                )
        lowest = self._layers[-1]
        return WindVector(
            wind_east_mps=lowest.wind_east_mps,
            wind_north_mps=lowest.wind_north_mps,
        )


@dataclass(frozen=True)
class TimedWindChange:
    """Wind provider replacement effective from an elapsed mission time onward."""

    effective_elapsed_time_s: float
    provider: WindProvider


class TimeVaryingWindProvider:
    """Provider that switches wind models at deterministic elapsed times."""

    provider_id = "time-varying"

    def __init__(
        self,
        base_provider: WindProvider,
        changes: list[TimedWindChange],
    ) -> None:
        self._base_provider = base_provider
        self._changes: tuple[TimedWindChange, ...] = tuple(
            sorted(changes, key=lambda c: c.effective_elapsed_time_s)
        )

    def _provider_for_elapsed_time(self, elapsed_time_s: float) -> WindProvider:
        for change in reversed(self._changes):
            if elapsed_time_s >= change.effective_elapsed_time_s:
                return change.provider
        return self._base_provider

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        provider = self._provider_for_elapsed_time(elapsed_time_s)
        return provider.wind_at(
            lat=lat,
            lon=lon,
            altitude_amsl_m=altitude_amsl_m,
            elapsed_time_s=elapsed_time_s,
        )


def wind_provider_id(provider: WindProvider) -> str:
    provider_id = getattr(provider, "provider_id", None)
    if isinstance(provider_id, str) and provider_id:
        return provider_id
    return "custom"
