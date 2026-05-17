"""SITL scenario comparison report builder."""

from dataclasses import dataclass, field

from adapters.canonical_json import render_canonical_json
from adapters.sitl.comparison_dimensions import _SitlComparisonDimensionBuilder
from adapters.sitl.comparison_summary import _SitlComparisonSummaryCalculator
from adapters.version import tool_version
from schemas.sitl import SitlEvidenceBundle, SitlEvidenceStatus
from schemas.sitl_comparison import (
    SITL_COMPARISON_SCHEMA_VERSION,
    SitlComparisonReport,
    SitlComparisonSummary,
)


@dataclass(frozen=True)
class _SitlComparisonReportBuilder:
    """Build deterministic SITL comparison reports."""

    dimensions: _SitlComparisonDimensionBuilder = field(
        default_factory=_SitlComparisonDimensionBuilder,
    )
    summaries: _SitlComparisonSummaryCalculator = field(
        default_factory=_SitlComparisonSummaryCalculator,
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
        summary = (
            SitlComparisonSummary.UNSUPPORTED
            if bundle.status == SitlEvidenceStatus.CONTRACT_ONLY
            else self.summaries.summary_for(items)
        )
        return SitlComparisonReport(
            schema_version=SITL_COMPARISON_SCHEMA_VERSION,
            comparison_id=comparison_id,
            evidence_id=bundle.evidence_id,
            tool_version=tool_version(),
            summary=summary,
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

    return _SitlComparisonReportBuilder().build(
        comparison_id=comparison_id,
        bundle=bundle,
        position_tolerance_m=position_tolerance_m,
    )


def render_sitl_comparison_json(report: SitlComparisonReport) -> str:
    """Render a SITL comparison report as canonical deterministic JSON."""

    return render_canonical_json(report.model_dump(mode="json"))


__all__ = [
    "SITL_COMPARISON_SCHEMA_VERSION",
    "SitlComparisonReport",
    "build_sitl_comparison_report",
    "render_sitl_comparison_json",
]
