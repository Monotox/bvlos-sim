"""Pre-flight go/no-go checklist rendering."""

from adapters.envelope import EstimatorResultEnvelope
from adapters.scenario_envelope import ScenarioResultEnvelope
from estimator.core.results import (
    EnergyEstimate,
    GeofenceEstimate,
    LandingZoneEstimate,
    LinkEstimate,
    MissionEstimate,
    ResourceEstimate,
)

_PASS = "✓"   # ✓
_FAIL = "✗"   # ✗
_NA = "◌"     # ◌
_CAT_WIDTH = 25


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _row(icon: str, category: str, outcome: str, detail: str) -> str:
    padded = category.ljust(_CAT_WIDTH)
    return f"{icon} {padded} {outcome:<4}   {detail}"


def _energy_row(energy: EnergyEstimate | None) -> str:
    if energy is None:
        return _row(_NA, "Energy feasibility", "N/A", "not evaluated")
    margin = energy.reserve_at_landing_wh - energy.reserve_threshold_wh
    if energy.is_feasible:
        detail = (
            f"reserve {_fmt(margin)} Wh above threshold "
            f"({_fmt(energy.reserve_at_landing_wh)} Wh at landing, "
            f"{_fmt(energy.reserve_threshold_wh)} Wh threshold)"
        )
        return _row(_PASS, "Energy feasibility", "PASS", detail)
    detail = (
        f"reserve {_fmt(abs(margin))} Wh below threshold "
        f"({_fmt(energy.reserve_at_landing_wh)} Wh at landing, "
        f"{_fmt(energy.reserve_threshold_wh)} Wh threshold)"
    )
    return _row(_FAIL, "Energy feasibility", "FAIL", detail)


def _geofence_row(geofence: GeofenceEstimate | None) -> str:
    if geofence is None:
        return _row(_NA, "Geofence clearance", "N/A", "not evaluated")
    if geofence.is_feasible:
        detail = f"0 conflicts across {geofence.checked_zone_count} zone(s)"
        return _row(_PASS, "Geofence clearance", "PASS", detail)
    detail = (
        f"{len(geofence.conflicts)} conflict(s) across "
        f"{geofence.checked_zone_count} zone(s)"
    )
    return _row(_FAIL, "Geofence clearance", "FAIL", detail)


def _landing_zone_row(landing_zone: LandingZoneEstimate | None) -> str:
    if landing_zone is None:
        return _row(_NA, "Landing-zone coverage", "N/A", "not evaluated")
    if landing_zone.is_feasible:
        detail = (
            f"reachable zone found at all {landing_zone.checked_state_count} "
            f"checked state(s)"
        )
        return _row(_PASS, "Landing-zone coverage", "PASS", detail)
    reachable = sum(
        1 for s in landing_zone.states if s.reachable_zone_id is not None
    )
    total = landing_zone.checked_state_count
    detail = f"reachable zone missing at {total - reachable}/{total} state(s)"
    return _row(_FAIL, "Landing-zone coverage", "FAIL", detail)


def _resource_row(resource: ResourceEstimate | None) -> str:
    if resource is None:
        return _row(_NA, "Resource availability", "N/A", "not evaluated")
    if resource.is_feasible:
        return _row(_PASS, "Resource availability", "PASS", f"system {resource.selected_resource_id!r} sufficient")
    return _row(_FAIL, "Resource availability", "FAIL", f"system {resource.selected_resource_id!r} insufficient")


def _link_row(link: LinkEstimate | None) -> str:
    if link is None:
        return _row(_NA, "Link availability", "N/A", "not evaluated")
    if link.is_feasible:
        return _row(_PASS, "Link availability", "PASS", f"link {link.selected_link_id!r} available")
    return _row(_FAIL, "Link availability", "FAIL", f"link {link.selected_link_id!r} unavailable")


def _warnings_row(result: MissionEstimate) -> str:
    n = len(result.warnings)
    if n == 0:
        return _row(" ", "Advisory warnings", "NONE", "")
    codes = ", ".join(str(w.code) for w in result.warnings[:5])
    suffix = f" + {n - 5} more" if n > 5 else ""
    return _row(" ", "Advisory warnings", str(n), f"{codes}{suffix}")


def _is_go(result: MissionEstimate) -> bool:
    checks = [result.energy, result.geofence, result.landing_zone, result.resource, result.link]
    return all(c is None or c.is_feasible for c in checks)


def _render_checklist(result: MissionEstimate | None, mission_id: str) -> str:
    lines: list[str] = [f"## Pre-Flight Checklist: {mission_id}", ""]
    if result is None:
        lines.append(_row(_FAIL, "Estimate", "FAIL", "estimate not available"))
        lines.extend(["", "Status: NO-GO", ""])
        return "\n".join(lines)

    lines.append(_energy_row(result.energy))
    lines.append(_geofence_row(result.geofence))
    lines.append(_landing_zone_row(result.landing_zone))
    lines.append(_resource_row(result.resource))
    lines.append(_link_row(result.link))
    lines.append(_warnings_row(result))
    lines.append("")
    status = "GO" if _is_go(result) else "NO-GO"
    lines.append(f"Status: {status}")
    lines.append("")
    return "\n".join(lines)


def render_checklist_markdown(
    envelope: EstimatorResultEnvelope,
    *,
    mission_id: str = "mission",
) -> str:
    """Render a pre-flight go/no-go checklist for an estimate envelope."""
    return _render_checklist(envelope.result, mission_id)


def render_checklist_markdown_from_scenario(envelope: ScenarioResultEnvelope) -> str:
    """Render a pre-flight go/no-go checklist from a scenario envelope."""
    return _render_checklist(envelope.estimate, envelope.scenario_id)


__all__ = [
    "render_checklist_markdown",
    "render_checklist_markdown_from_scenario",
]
