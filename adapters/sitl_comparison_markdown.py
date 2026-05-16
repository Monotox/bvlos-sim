"""Markdown rendering for SITL comparison reports."""

import json
from dataclasses import dataclass

from schemas.sitl import SitlJsonValue
from schemas.sitl_comparison import SitlComparisonItem, SitlComparisonReport


@dataclass(frozen=True)
class SitlComparisonMarkdownRenderer:
    """Render SITL comparison reports as Markdown."""

    max_cell_chars: int = 60

    def render(self, report: SitlComparisonReport) -> str:
        lines = [
            "# SITL Comparison Report",
            "",
            f"- Comparison ID: `{report.comparison_id}`",
            f"- Evidence ID: `{report.evidence_id}`",
            f"- Summary: `{report.summary.value}`",
            f"- Schema: `{report.schema_version}`",
            f"- Tool: `{report.tool_version}`",
            "",
            "## Comparison Items",
            "",
            "| Dimension | Outcome | Expected | Observed | Notes |",
            "|-----------|---------|----------|----------|-------|",
        ]
        lines.extend(self._item_line(item) for item in report.items)
        return "\n".join(lines) + "\n"

    def _item_line(self, item: SitlComparisonItem) -> str:
        return (
            "| "
            f"{self._table_cell(item.dimension)} | "
            f"{self._table_cell(item.outcome.value)} | "
            f"{self._table_cell(self._format_value(item.expected))} | "
            f"{self._table_cell(self._format_value(item.observed))} | "
            f"{self._table_cell(item.notes or '')} |"
        )

    def _format_value(self, value: SitlJsonValue) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True)

    def _table_cell(self, value: str) -> str:
        text = value.replace("|", "\\|").replace("\n", " ")
        if len(text) > self.max_cell_chars:
            return f"{text[: self.max_cell_chars - 3]}..."
        return text


def render_sitl_comparison_markdown(report: SitlComparisonReport) -> str:
    """Render a SITL comparison report as Markdown."""

    return SitlComparisonMarkdownRenderer().render(report)


__all__ = [
    "SitlComparisonMarkdownRenderer",
    "render_sitl_comparison_markdown",
]
