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
