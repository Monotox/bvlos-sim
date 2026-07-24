"""Summary calculation for SITL comparison reports."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from bvlos_sim.schemas.sitl_comparison import (
    SitlComparisonItem,
    SitlComparisonOutcome,
    SitlComparisonSummary,
)


@dataclass(frozen=True)
class _SitlComparisonSummaryCalculator:
    """Reduce item outcomes to a report summary."""

    supported_outcomes: ClassVar[frozenset[SitlComparisonOutcome]] = frozenset(
        {
            SitlComparisonOutcome.MATCHED,
            SitlComparisonOutcome.DRIFTED,
            SitlComparisonOutcome.MISSING,
        }
    )
    summary_priority: ClassVar[
        tuple[tuple[SitlComparisonOutcome, SitlComparisonSummary], ...]
    ] = (
        (SitlComparisonOutcome.MISSING, SitlComparisonSummary.FAILED),
        (SitlComparisonOutcome.DRIFTED, SitlComparisonSummary.DRIFTED),
    )

    def summary_for(
        self,
        items: Sequence[SitlComparisonItem],
    ) -> SitlComparisonSummary:
        outcomes = {item.outcome for item in items}
        if not outcomes & self.supported_outcomes:
            return SitlComparisonSummary.UNSUPPORTED
        return self._priority_summary(outcomes) or SitlComparisonSummary.PASSED

    def _priority_summary(
        self,
        outcomes: set[SitlComparisonOutcome],
    ) -> SitlComparisonSummary | None:
        return next(
            (
                summary
                for outcome, summary in self.summary_priority
                if outcome in outcomes
            ),
            None,
        )


__all__: list[str] = []
