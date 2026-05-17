"""Markdown rendering for SITL evidence bundles."""

from schemas.sitl import (
    SitlArtifactReference,
    SitlEvidenceBundle,
    SitlObservedArtifacts,
)

_EMPTY_ARTIFACT_ROW = "| None |  |  |  |  |"


def _artifact_row(ref: SitlArtifactReference) -> str:
    schema = ref.schema_version or ""
    digest = ref.sha256 or ""
    return f"| `{ref.role.value}` | `{ref.path}` | `{ref.format or ''}` | `{schema}` | `{digest}` |"


def _artifact_rows(refs: list[SitlArtifactReference]) -> list[str]:
    return [_artifact_row(ref) for ref in refs] or [_EMPTY_ARTIFACT_ROW]


def _artifact_table(refs: list[SitlArtifactReference]) -> list[str]:
    return [
        "| Role | Path | Format | Schema | SHA-256 |",
        "|------|------|--------|--------|--------|",
        *_artifact_rows(refs),
    ]


def _observed_refs(observed: SitlObservedArtifacts) -> list[SitlArtifactReference]:
    return [
        *observed.telemetry,
        *observed.command_logs,
        *observed.simulator_logs,
        *observed.adapter_logs,
    ]


def _markdown_bool(value: bool) -> str:
    return str(value).lower()


def _optional_text(value: str | None) -> str:
    return value or ""


def render_sitl_evidence_markdown(bundle: SitlEvidenceBundle) -> str:
    """Render a SITL evidence bundle as Markdown."""

    simulator = bundle.simulator
    lines = [
        "# SITL Evidence Bundle",
        "",
        "## Evidence Bundle",
        "",
        f"- Evidence ID: `{bundle.evidence_id}`",
        f"- Schema: `{bundle.schema_version}`",
        f"- Tool: `{bundle.tool_version}`",
        f"- Created by: `{bundle.created_by}`",
        "",
        "## Status",
        "",
        f"- Status: `{bundle.status.value}`",
        f"- Contract only: `{_markdown_bool(bool(bundle.metadata.get('contract_only', False)))}`",
        "",
        "## Simulator",
        "",
        f"- Adapter kind: `{simulator.adapter_kind.value}`",
        f"- Adapter ID: `{simulator.adapter_id}`",
        f"- Adapter version: `{simulator.adapter_version}`",
        f"- Execution mode: `{simulator.execution_mode}`",
        f"- Simulator: `{_optional_text(simulator.simulator_name)}`",
        f"- Autopilot: `{_optional_text(simulator.autopilot)}`",
        f"- Frame: `{_optional_text(simulator.frame)}`",
        "",
        "## Inputs",
        "",
        *_artifact_table(bundle.inputs),
        "",
        "## Expected Outputs",
        "",
        f"- Scenario report embedded: `{_markdown_bool(bundle.expected.scenario_report is not None)}`",
        f"- Estimator result embedded: `{_markdown_bool(bundle.expected.estimator_result is not None)}`",
        f"- Report references: `{len(bundle.expected.reports)}`",
        "",
        "## Observed Artifacts",
        "",
        *_artifact_table(_observed_refs(bundle.observed)),
    ]
    return "\n".join(lines) + "\n"


__all__ = ["render_sitl_evidence_markdown"]
