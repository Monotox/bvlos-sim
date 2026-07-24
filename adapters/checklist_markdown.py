"""Pre-flight go/no-go checklist rendering."""

from collections.abc import Sequence

from adapters.envelope import EnvelopeDiagnostic, EstimatorResultEnvelope
from adapters.scenario_envelope import ScenarioResultEnvelope
from adapters.operational_readiness import (
    OperationalReadiness,
    evaluate_operational_readiness,
)
from estimator.core.results import (
    EnergyEstimate,
    GeofenceEstimate,
    GroundRiskEstimate,
    LandingZoneEstimate,
    LinkEstimate,
    MissionEstimate,
    ObstacleEstimate,
    ResourceEstimate,
    WeatherEstimate,
)

_PASS = "✓"  # ✓
_FAIL = "✗"  # ✗
_NA = "◌"  # ◌
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
    reachable = sum(1 for s in landing_zone.states if s.reachable_zone_id is not None)
    total = landing_zone.checked_state_count
    detail = f"reachable zone missing at {total - reachable}/{total} state(s)"
    return _row(_FAIL, "Landing-zone coverage", "FAIL", detail)


def _resource_row(resource: ResourceEstimate | None) -> str:
    if resource is None:
        return _row(_NA, "Resource availability", "N/A", "not evaluated")
    if resource.is_feasible:
        return _row(
            _PASS,
            "Resource availability",
            "PASS",
            f"system {resource.selected_resource_id!r} sufficient",
        )
    return _row(
        _FAIL,
        "Resource availability",
        "FAIL",
        f"system {resource.selected_resource_id!r} insufficient",
    )


def _link_row(link: LinkEstimate | None) -> str:
    if link is None:
        return _row(_NA, "Link availability", "N/A", "not evaluated")
    if link.is_feasible and link.selected_link_id is not None:
        return _row(
            _PASS,
            "Link availability",
            "PASS",
            f"link {link.selected_link_id!r} available",
        )
    detail = (
        "no configured link is available"
        if link.selected_link_id is None
        else f"link {link.selected_link_id!r} unavailable"
    )
    return _row(
        _FAIL,
        "Link availability",
        "FAIL",
        detail,
    )


def _weather_row(weather: WeatherEstimate | None) -> str:
    if weather is None:
        return _row(_NA, "Weather limits", "N/A", "not evaluated")
    worst = weather.worst_wind_speed_mps
    where = (
        f" at leg {weather.worst_leg_index} ({weather.worst_route_item_id})"
        if weather.worst_leg_index is not None
        else ""
    )
    worst_text = (
        f"worst wind {_fmt(worst)} m/s{where}" if worst is not None else "no wind data"
    )
    if weather.is_feasible:
        return _row(_PASS, "Weather limits", "PASS", worst_text)
    violation = weather.violations[0]
    detail = (
        f"{violation.code.value}: {_fmt(violation.observed_mps)} m/s "
        f"exceeds {_fmt(violation.limit_mps)} m/s at leg {violation.leg_index}"
    )
    return _row(_FAIL, "Weather limits", "FAIL", detail)


def _obstacle_row(obstacle: ObstacleEstimate | None) -> str:
    if obstacle is None:
        return _row(_NA, "Obstacle clearance", "N/A", "not evaluated")
    if obstacle.is_feasible:
        detail = (
            f"0 violations across {obstacle.checked_leg_count} leg(s) "
            f"and {obstacle.checked_obstacle_count} obstacle(s)"
        )
        return _row(_PASS, "Obstacle clearance", "PASS", detail)
    violation = obstacle.violations[0]
    target = (
        f"obstacle {violation.obstacle_id!r}"
        if violation.obstacle_id is not None
        else "terrain"
    )
    detail = (
        f"{violation.code.value}: {target} at leg {violation.leg_index} "
        f"(clearance {_fmt(violation.vertical_clearance_m)} m)"
    )
    return _row(_FAIL, "Obstacle clearance", "FAIL", detail)


def _rth_reserve_row(result: MissionEstimate) -> str | None:
    if result.rth_is_feasible is None:
        return None
    if (
        result.rth_is_feasible
        and result.resource is not None
        and result.resource.selected_resource_id is not None
    ):
        selected = next(
            (
                item
                for item in result.resource.systems
                if item.resource_id == result.resource.selected_resource_id
            ),
            None,
        )
        if selected is not None and selected.kind == "external_power":
            return _row(
                _PASS,
                "RTH feasibility",
                "PASS",
                "selected external resource covers RTH peak power",
            )
    timeline = result.energy.rth_reserve_timeline if result.energy is not None else None
    leg_count = len(timeline) if timeline is not None else 0
    if result.rth_is_feasible:
        detail = f"reserve intact for RTH from all {leg_count} leg(s)"
        return _row(_PASS, "RTH reserve", "PASS", detail)
    infeasible = [point for point in timeline or [] if not point.is_feasible]
    if not infeasible:
        return _row(
            _FAIL,
            "RTH reserve",
            "FAIL",
            "RTH feasibility failed; reserve timeline details unavailable",
        )
    first = infeasible[0]
    detail = (
        f"RTH below reserve from {len(infeasible)}/{leg_count} leg(s); "
        f"first at leg {first.leg_index} (margin {_fmt(first.reserve_margin_wh)} Wh)"
    )
    return _row(_FAIL, "RTH reserve", "FAIL", detail)


def _ground_risk_row(ground_risk: GroundRiskEstimate | None) -> str:
    if ground_risk is None:
        return _row(_NA, "Ground risk class", "N/A", "not evaluated")
    detail = f"mission iGRC {ground_risk.mission_igrc}"
    if ground_risk.mission_igrc > 7:
        detail = f"{detail}; exceeds specific-category envelope"
    return _row(" ", "Ground risk class", "INFO", detail)


def _warnings_row(result: MissionEstimate) -> str:
    n = len(result.warnings)
    if n == 0:
        return _row(" ", "Advisory warnings", "NONE", "")
    codes = ", ".join(str(w.code) for w in result.warnings[:5])
    suffix = f" + {n - 5} more" if n > 5 else ""
    return _row(" ", "Advisory warnings", str(n), f"{codes}{suffix}")


def _departure_time_row(result: MissionEstimate) -> str | None:
    departure_time = result.metadata.get("departure_time")
    if not isinstance(departure_time, str):
        return None
    return _row(" ", "Departure time", "INFO", departure_time)


def checklist_is_go(result: MissionEstimate) -> bool:
    """Return the fail-closed operational verdict rendered by the checklist."""
    return evaluate_operational_readiness(result).is_go


def _render_checklist(
    result: MissionEstimate | None,
    mission_id: str,
    diagnostics: Sequence[EnvelopeDiagnostic] = (),
    readiness: OperationalReadiness | None = None,
) -> str:
    lines: list[str] = [f"## Pre-Flight Checklist: {mission_id}", ""]
    if result is None:
        lines.append(_row(_FAIL, "Estimate", "FAIL", "estimate not available"))
        for diagnostic in diagnostics:
            detail = str(diagnostic.code)
            context_path = diagnostic.context.get("path")
            if isinstance(context_path, str):
                detail += f" ({context_path})"
            lines.append(f"  {detail}: {diagnostic.message}")
        lines.extend(["", "Status: NO-GO", ""])
        return "\n".join(lines)

    lines.append(_energy_row(result.energy))
    lines.append(_geofence_row(result.geofence))
    lines.append(_landing_zone_row(result.landing_zone))
    lines.append(_resource_row(result.resource))
    lines.append(_link_row(result.link))
    lines.append(_obstacle_row(result.obstacle))
    lines.append(_weather_row(result.weather))
    rth_row = _rth_reserve_row(result)
    if rth_row is not None:
        lines.append(rth_row)
    lines.append(_ground_risk_row(result.ground_risk))
    departure_row = _departure_time_row(result)
    if departure_row is not None:
        lines.append(departure_row)
    lines.append(_warnings_row(result))
    lines.append("")
    if readiness is None:
        readiness = evaluate_operational_readiness(result)
    if readiness.acknowledged_warning_codes:
        lines.insert(
            len(lines) - 1,
            _row(
                " ",
                "Acknowledged warnings",
                str(len(readiness.acknowledged_warning_codes)),
                ", ".join(readiness.acknowledged_warning_codes),
            ),
        )
    lines.append(f"Status: {'GO' if readiness.is_go else 'NO-GO'}")
    if not readiness.is_go:
        reason = _blocked_by(readiness)
        if reason:
            lines.append(reason)
    lines.append("")
    return "\n".join(lines)


def _blocked_by(readiness: OperationalReadiness) -> str:
    parts: list[str] = []
    if readiness.missing_evidence:
        parts.append(
            "missing evidence (" + ", ".join(readiness.missing_evidence) + ")"
        )
    failed = [check for check in readiness.failed_checks if check != "warnings"]
    if failed:
        parts.append("failed checks (" + ", ".join(failed) + ")")
    if "warnings" in readiness.failed_checks:
        blocking = [
            code
            for code in readiness.warning_codes
            if code not in readiness.acknowledged_warning_codes
        ]
        parts.append("blocking warnings (" + ", ".join(blocking) + ")")
    if not parts:
        return ""
    return "Blocked by: " + "; ".join(parts) + " — the checklist is fail-closed"


def render_checklist_markdown(
    envelope: EstimatorResultEnvelope,
    *,
    mission_id: str = "mission",
) -> str:
    """Render a pre-flight go/no-go checklist for an estimate envelope."""
    return _render_checklist(envelope.result, mission_id, envelope.diagnostics)


def render_checklist_markdown_from_scenario(envelope: ScenarioResultEnvelope) -> str:
    """Render a pre-flight go/no-go checklist from a scenario envelope.

    Renders the readiness the envelope already carries rather than recomputing
    it from the estimate, so a failed or unevaluated assertion reaches the card
    an operator actually signs off on.
    """

    return _render_checklist(
        envelope.estimate,
        envelope.scenario_id,
        readiness=envelope.operational_readiness,
    )


__all__ = [
    "checklist_is_go",
    "render_checklist_markdown",
    "render_checklist_markdown_from_scenario",
]
