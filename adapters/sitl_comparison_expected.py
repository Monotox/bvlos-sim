"""Expected-output comparison dimensions for SITL reports."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from adapters.sitl_comparison_artifacts import ArtifactRecord, list_of_mappings
from adapters.sitl_comparison_values import SitlComparisonValueCoercer
from schemas.sitl import SitlEvidenceBundle, SitlEvidenceStatus
from schemas.sitl_comparison import SitlComparisonItem, SitlComparisonOutcome


@dataclass(frozen=True)
class SitlExpectedComparisonBuilder:
    """Build comparisons from deterministic expected outputs."""

    values: SitlComparisonValueCoercer = field(
        default_factory=SitlComparisonValueCoercer,
    )

    def items(
        self,
        bundle: SitlEvidenceBundle,
        scenario_report: Mapping[str, object],
    ) -> list[SitlComparisonItem]:
        return [
            self.bundle_completeness_item(bundle),
            *self.scenario_assertion_items(scenario_report),
        ]

    def bundle_completeness_item(
        self,
        bundle: SitlEvidenceBundle,
    ) -> SitlComparisonItem:
        contract_only = bundle.status == SitlEvidenceStatus.CONTRACT_ONLY
        return SitlComparisonItem(
            dimension="bundle_completeness",
            outcome=(
                SitlComparisonOutcome.SKIPPED
                if contract_only
                else SitlComparisonOutcome.MATCHED
            ),
            expected=SitlEvidenceStatus.COMPLETED.value,
            observed=bundle.status.value,
            notes=(
                "Evidence bundle has no live telemetry; all telemetry-dependent "
                "comparisons are skipped."
                if contract_only
                else None
            ),
        )

    def scenario_assertion_items(
        self,
        scenario_report: Mapping[str, object],
    ) -> list[SitlComparisonItem]:
        return [
            self._scenario_assertion_item(assertion)
            for assertion in list_of_mappings(
                scenario_report.get("assertion_results"),
            )
        ]

    def _scenario_assertion_item(
        self,
        assertion: ArtifactRecord,
    ) -> SitlComparisonItem:
        assertion_id = str(assertion.get("assertion_id", "unknown"))
        return SitlComparisonItem(
            dimension=f"assertion:{assertion_id}",
            outcome=self._assertion_outcome(assertion),
            expected=self.values.json_value(
                assertion.get("expected_value", assertion.get("expected")),
            ),
            observed=self.values.json_value(
                assertion.get("observed_value", assertion.get("actual")),
            ),
            notes=self.values.optional_string(assertion.get("message")),
        )

    def _assertion_outcome(
        self,
        assertion: ArtifactRecord,
    ) -> SitlComparisonOutcome:
        return (
            SitlComparisonOutcome.MATCHED
            if self._assertion_passed(assertion)
            else SitlComparisonOutcome.MISSING
        )

    def _assertion_passed(self, assertion: ArtifactRecord) -> bool:
        passed = assertion.get("passed")
        return (
            passed if isinstance(passed, bool) else assertion.get("outcome") == "passed"
        )


__all__ = ["SitlExpectedComparisonBuilder"]
