"""Route altitude profile report rendering."""

from bvlos_sim.adapters.envelope import EstimatorResultEnvelope
from bvlos_sim.adapters.scenario_envelope import ScenarioResultEnvelope
from bvlos_sim.estimator.core.results import LegEstimate, MissionEstimate
from bvlos_sim.estimator.environment.terrain import TerrainProvider


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _terrain_and_clearance(
    leg: LegEstimate,
    terrain_provider: TerrainProvider | None,
) -> tuple[float | None, float | None]:
    if terrain_provider is None:
        return None, None
    t_start = terrain_provider.elevation_at(leg.start_lat, leg.start_lon)
    t_end = terrain_provider.elevation_at(leg.end_lat, leg.end_lon)
    if t_start is None and t_end is None:
        return None, None
    # Use the worse-case (minimum clearance) across the two endpoints.
    if t_start is not None and t_end is not None:
        clearance_start = leg.start_alt_amsl_m - t_start
        clearance_end = leg.end_alt_amsl_m - t_end
        terrain = min(t_start, t_end)
        clearance = min(clearance_start, clearance_end)
    elif t_end is not None:
        terrain = t_end
        clearance = leg.end_alt_amsl_m - t_end
    else:
        assert t_start is not None
        terrain = t_start
        clearance = leg.start_alt_amsl_m - t_start
    return terrain, clearance


def _render_altitude_table(
    legs: list[LegEstimate],
    terrain_provider: TerrainProvider | None,
) -> list[str]:
    has_terrain = terrain_provider is not None
    header = (
        "| Leg | ID | Phase | Dist m | Start AMSL m | End AMSL m"
        + (" | Terrain m | Clearance m |" if has_terrain else " |")
    )
    separator = (
        "|----:|-----|---------|-------:|-------------:|----------:"
        + ("|---------:|-----------:|" if has_terrain else "|")
    )
    rows: list[str] = [header, separator]
    for leg in legs:
        leg_id = leg.route_item_id or "—"
        terrain, clearance = _terrain_and_clearance(leg, terrain_provider)
        base = (
            f"| {leg.leg_index} | {leg_id} | {leg.phase} "
            f"| {_fmt(leg.path_distance_m)} | {_fmt(leg.start_alt_amsl_m)} "
            f"| {_fmt(leg.end_alt_amsl_m)}"
        )
        if has_terrain:
            t_str = _fmt(terrain) if terrain is not None else "—"
            c_str = _fmt(clearance) if clearance is not None else "—"
            rows.append(f"{base} | {t_str} | {c_str} |")
        else:
            rows.append(f"{base} |")
    return rows


def _render_profile(
    result: MissionEstimate | None,
    terrain_provider: TerrainProvider | None,
) -> str:
    lines: list[str] = ["## Route Altitude Profile", ""]
    if result is None or not result.legs:
        lines.append("*No legs available.*")
        lines.append("")
        return "\n".join(lines)

    if terrain_provider is None:
        lines.append(
            "*Terrain data not available. Include `assets.terrain_file` in the mission "
            "YAML to populate the Terrain and Clearance columns.*"
        )
        lines.append("")

    lines.extend(_render_altitude_table(result.legs, terrain_provider))
    lines.append("")
    return "\n".join(lines)


def render_profile_markdown(
    envelope: EstimatorResultEnvelope,
    *,
    terrain_provider: TerrainProvider | None = None,
) -> str:
    """Render a route altitude profile report as Markdown."""
    return _render_profile(envelope.result, terrain_provider)


def render_profile_markdown_from_scenario(
    envelope: ScenarioResultEnvelope,
    *,
    terrain_provider: TerrainProvider | None = None,
) -> str:
    """Render a route altitude profile from a scenario envelope."""
    return _render_profile(envelope.estimate, terrain_provider)


__all__ = [
    "render_profile_markdown",
    "render_profile_markdown_from_scenario",
]
