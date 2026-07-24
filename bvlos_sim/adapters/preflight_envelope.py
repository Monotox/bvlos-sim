"""Canonical JSON rendering for the preflight validation envelope."""

from __future__ import annotations

from bvlos_sim.adapters.canonical_json import render_canonical_json
from bvlos_sim.schemas.preflight_validation import PreflightValidationReport


def render_preflight_report(report: PreflightValidationReport) -> str:
    """Render a preflight validation report as canonical JSON.

    Uses the same canonical writer as every other envelope (sorted keys,
    ``indent=2``, normalized floats, trailing newline) so the output is
    deterministic and consistent with the rest of the CLI.
    """
    return render_canonical_json(report.model_dump(mode="json"))


__all__ = ["render_preflight_report"]
