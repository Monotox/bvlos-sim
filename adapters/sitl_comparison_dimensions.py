"""Comparison dimension orchestration for SITL evidence bundles."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from adapters.sitl_comparison_expected import SitlExpectedComparisonBuilder
from adapters.sitl_comparison_position import SitlPositionProximityComparator
from adapters.sitl_comparison_telemetry import SitlTelemetryComparisonBuilder
from schemas.sitl import SitlEvidenceBundle, SitlEvidenceStatus
from schemas.sitl_comparison import SitlComparisonItem, SitlComparisonOutcome

_TELEMETRY_DEPENDENT_DIMENSIONS = (
    "mission_item_count",
    "telemetry_record_count",
    "heartbeat_observed",
    "adapter_lifecycle",
    "simulator_lifecycle",
    "position_proximity",
)


@dataclass(frozen=True)
class SitlComparisonDimensionBuilder:
    """Build ordered comparison items for a SITL evidence bundle."""

    expected: SitlExpectedComparisonBuilder = field(
        default_factory=SitlExpectedComparisonBuilder,
    )
    telemetry: SitlTelemetryComparisonBuilder = field(
        default_factory=SitlTelemetryComparisonBuilder,
    )
    position: SitlPositionProximityComparator = field(
        default_factory=SitlPositionProximityComparator,
    )

    def items(
        self,
        bundle: SitlEvidenceBundle,
        scenario_report: Mapping[str, object],
        position_tolerance_m: float,
    ) -> list[SitlComparisonItem]:
        return [
            *self.expected.items(bundle, scenario_report),
            *self._observed_items(bundle, scenario_report, position_tolerance_m),
        ]

    def _observed_items(
        self,
        bundle: SitlEvidenceBundle,
        scenario_report: Mapping[str, object],
        position_tolerance_m: float,
    ) -> list[SitlComparisonItem]:
        if bundle.status == SitlEvidenceStatus.CONTRACT_ONLY:
            return self._skipped_telemetry_items()

        telemetry = self.telemetry.telemetry_records(bundle)
        return [
            *self.telemetry.items(bundle, scenario_report, telemetry),
            *self.position.items(scenario_report, telemetry, position_tolerance_m),
        ]

    def _skipped_telemetry_items(self) -> list[SitlComparisonItem]:
        return [
            SitlComparisonItem(
                dimension=dimension,
                outcome=SitlComparisonOutcome.SKIPPED,
                notes="Telemetry-dependent comparison skipped for contract-only evidence.",
            )
            for dimension in _TELEMETRY_DEPENDENT_DIMENSIONS
        ]


__all__ = ["SitlComparisonDimensionBuilder"]
