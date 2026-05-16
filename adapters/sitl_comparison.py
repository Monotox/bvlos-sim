"""SITL scenario comparison report builder."""

import json
from dataclasses import dataclass, field

from adapters.sitl_comparison_dimensions import SitlComparisonDimensionBuilder
from adapters.sitl_comparison_summary import SitlComparisonSummaryCalculator
from adapters.version import tool_version
from schemas.sitl import SitlEvidenceBundle
from schemas.sitl_comparison import (
    SITL_COMPARISON_SCHEMA_VERSION,
    SitlComparisonReport,
)


@dataclass(frozen=True)
class SitlComparisonReportBuilder:
    """Build deterministic SITL comparison reports."""

    dimensions: SitlComparisonDimensionBuilder = field(
        default_factory=SitlComparisonDimensionBuilder,
    )
    summaries: SitlComparisonSummaryCalculator = field(
        default_factory=SitlComparisonSummaryCalculator,
    )

    def build(
        self,
        *,
        comparison_id: str,
        bundle: SitlEvidenceBundle,
        position_tolerance_m: float = 500.0,
    ) -> SitlComparisonReport:
        scenario_report = bundle.expected.scenario_report or {}
        items = self.dimensions.items(bundle, scenario_report, position_tolerance_m)
        return SitlComparisonReport(
            schema_version=SITL_COMPARISON_SCHEMA_VERSION,
            comparison_id=comparison_id,
            evidence_id=bundle.evidence_id,
            tool_version=tool_version(),
            summary=self.summaries.summary_for(items),
            items=items,
            metadata={"position_tolerance_m": position_tolerance_m},
        )


def build_sitl_comparison_report(
    *,
    comparison_id: str,
    bundle: SitlEvidenceBundle,
    position_tolerance_m: float = 500.0,
) -> SitlComparisonReport:
    """Build a deterministic comparison report from a SITL evidence bundle."""

    return SitlComparisonReportBuilder().build(
        comparison_id=comparison_id,
        bundle=bundle,
        position_tolerance_m=position_tolerance_m,
    )


def render_sitl_comparison_json(report: SitlComparisonReport) -> str:
    """Render a SITL comparison report as canonical deterministic JSON."""

    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


__all__ = [
    "SITL_COMPARISON_SCHEMA_VERSION",
    "SitlComparisonReport",
    "SitlComparisonReportBuilder",
    "build_sitl_comparison_report",
    "render_sitl_comparison_json",
]
