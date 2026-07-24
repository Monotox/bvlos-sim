"""The YAML examples in docs/missions.md must validate exactly as written.

A new user without the repository's examples/ directory authors their first
mission from these blocks; a doc example that fails schema validation is a
broken front door, not a typo.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile

_DOC = Path(__file__).resolve().parents[1] / "docs" / "missions.md"


def _yaml_blocks(section_heading: str) -> list[str]:
    text = _DOC.read_text(encoding="utf-8")
    start = text.index(section_heading)
    end = text.find("\n## ", start + 1)
    section = text[start : end if end != -1 else len(text)]
    return re.findall(r"```yaml\n(.*?)```", section, flags=re.DOTALL)

def test_minimal_mission_example_validates() -> None:
    blocks = _yaml_blocks("## Mission (`mission.v7`)")
    assert blocks, "missions.md lost its minimal mission example"
    MissionPlan.model_validate(yaml.safe_load(blocks[0]))


def test_vehicle_example_validates() -> None:
    blocks = _yaml_blocks("## Vehicle (`vehicle.v4`)")
    assert blocks, "missions.md lost its vehicle example"
    VehicleProfile.model_validate(yaml.safe_load(blocks[0]))


def test_constraints_example_validates_inside_minimal_mission() -> None:
    mission = yaml.safe_load(_yaml_blocks("## Mission (`mission.v7`)")[0])
    constraint_blocks = _yaml_blocks("### Constraints")
    assert constraint_blocks
    mission.update(yaml.safe_load(constraint_blocks[0]))
    MissionPlan.model_validate(mission)


def test_alpine_terrain_asset_has_no_sea_level_voids() -> None:
    """SRTM voids were written as 0.0, claiming sea level in the Alps."""

    import yaml

    asset = (
        Path(__file__).resolve().parents[1]
        / "examples/real_world/assets/terrain.yaml"
    )
    elevations = yaml.safe_load(asset.read_text(encoding="utf-8"))["elevations_m"]
    values = [value for row in elevations for value in row]

    assert 0.0 not in values
    assert min(values) > 100.0


def test_alpine_wind_asset_covers_the_altitudes_the_route_flies() -> None:
    """The demo shipped a wind grid that was zero everywhere the route flew.

    Its altitude axis was height above ground while the provider queries metres
    AMSL, and only the 10 m band held real values, so the flagship example
    demonstrated the wind model on a null input and reported 0.00 m/s.
    """

    import yaml

    asset = (
        Path(__file__).resolve().parents[1]
        / "examples/real_world/assets/wind_grid.yaml"
    )
    grid = yaml.safe_load(asset.read_text(encoding="utf-8"))

    assert grid["metadata"]["vertical_reference"] == "AMSL"
    # The route cruises around 550 m AMSL, so the axis has to bracket it.
    altitudes = grid["axes"]["altitude_m"]
    assert min(altitudes) < 550.0 < max(altitudes)

    speeds = [
        (east**2 + north**2) ** 0.5
        for time_slice in grid["values"]
        for band in time_slice
        for row in band
        for east, north in row
    ]
    assert min(speeds) > 0.0, "every cell must carry a real forecast value"


def test_alpine_demo_reports_non_zero_wind() -> None:
    """End to end: the checklist must not claim a calm flight on real data."""

    from typer.testing import CliRunner

    from adapters.cli import app

    repo = Path(__file__).resolve().parents[1]
    result = CliRunner().invoke(
        app,
        [
            "estimate",
            str(repo / "examples/real_world/alpine_mission.yaml"),
            str(repo / "examples/real_world/quadplane_v1.yaml"),
            "--format",
            "checklist",
        ],
    )

    assert "worst wind 0.00 m/s" not in result.stdout
    assert "Weather limits" in result.stdout
