"""Mission schema detection and v6→v7 migration."""

import math
from typing import Any

from schemas.mission import MISSION_SCHEMA_VERSION

from .registry import register_migration

MISSION_V6 = "mission.v6"


def detect_mission_version(payload: dict[str, object]) -> str:
    """Detect explicit mission versions; unversioned files are legacy v6."""

    explicit = payload.get("schema_version")
    if explicit is None:
        return MISSION_V6
    if not isinstance(explicit, str):
        raise ValueError("mission schema_version must be a string")
    if explicit in {MISSION_V6, MISSION_SCHEMA_VERSION}:
        return str(explicit)
    raise ValueError(f"unsupported mission schema_version {explicit!r}")


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"legacy mission field {field} must be a mapping")
    return value


def _applied(declaration: object, *, field: str) -> bool:
    mapping = _mapping(declaration, field=field)
    applied = mapping.get("applied")
    if not isinstance(applied, bool):
        raise ValueError(f"legacy mission field {field}.applied must be a boolean")
    return applied


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"legacy mission field {field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"legacy mission field {field} must be a finite number")
    return number


@register_migration(
    "mission",
    from_version=MISSION_V6,
    to_version=MISSION_SCHEMA_VERSION,
)
def migrate_mission_v6_to_v7(payload: dict[str, object]) -> dict[str, object]:
    """Upgrade unambiguous v6 declarations; reject unsafe semantic guesses."""

    migrated = dict(payload)
    migrated["schema_version"] = MISSION_SCHEMA_VERSION

    airspace_value = migrated.get("airspace")
    if airspace_value is not None:
        airspace = dict(_mapping(airspace_value, field="airspace"))
        assessment_reference = airspace.get(
            "operational_and_contingency_volume_assessment_reference"
        )
        worst_case_declared = airspace.get("worst_case_arc_declared")
        if (
            not isinstance(assessment_reference, str)
            or not assessment_reference.strip()
            or worst_case_declared is not True
        ):
            raise ValueError(
                "mission.v6 airspace cannot be migrated until the operator "
                "provides a nonblank whole-volume assessment reference and "
                "declares worst_case_arc_declared=true"
            )
        for required_boolean in (
            "near_aerodrome",
            "transponder_mandatory_zone",
        ):
            if not isinstance(airspace.get(required_boolean), bool):
                raise ValueError(
                    "mission.v6 airspace cannot be migrated until the operator "
                    f"declares {required_boolean}=true or false for the entire "
                    "operational and contingency volumes"
                )
        airspace["aerodrome_environment"] = airspace.pop("near_aerodrome")
        old_fl600 = airspace.pop("above_flight_level_600", None)
        if old_fl600 is True:
            raise ValueError(
                "mission.v6 above_flight_level_600=true is ambiguous: declare "
                "whether the entire operational volume is above FL600"
            )
        if old_fl600 is not None and old_fl600 is not False:
            raise ValueError(
                "mission.v6 above_flight_level_600 must be a boolean or null"
            )
        if old_fl600 is False:
            airspace["entirely_above_flight_level_600"] = False
        legacy_strategic = airspace.pop("strategic_mitigation", None)
        if legacy_strategic is True:
            raise ValueError(
                "mission.v6 strategic_mitigation=true cannot be migrated from a "
                "boolean credit; provide encounter-rate evidence"
            )
        if legacy_strategic is not None and legacy_strategic is not False:
            raise ValueError(
                "mission.v6 strategic_mitigation must be a boolean declaration"
            )
        uncontrolled = airspace.get("class") in {"F", "G"}
        low_altitude = (
            _finite_number(
                airspace.get("max_altitude_agl_m"),
                field="airspace.max_altitude_agl_m",
            )
            <= 152.4
        )
        typical = not any(
            airspace.get(field) is True
            for field in (
                "aerodrome_environment",
                "atypical_or_segregated",
                "transponder_mandatory_zone",
                "entirely_above_flight_level_600",
            )
        )
        if (
            uncontrolled
            and low_altitude
            and typical
            and "over_urban_area" not in airspace
        ):
            raise ValueError(
                "mission.v6 low-altitude uncontrolled airspace requires an operator "
                "choice for over_urban_area in mission.v7"
            )
        migrated["airspace"] = airspace

    sora_value = migrated.get("sora")
    if sora_value is not None:
        sora = dict(_mapping(sora_value, field="sora"))
        version_value = sora.get("version", "2.0")
        if not isinstance(version_value, str):
            raise ValueError("legacy SORA version must be a string")
        version = version_value
        if version not in {"2.0", "2.5"}:
            raise ValueError(f"unsupported legacy SORA version {version!r}")
        if version == "2.0":
            raise ValueError(
                "mission.v6 SORA 2.0 declarations cannot be relabelled as SORA "
                "2.5; perform and document a new SORA 2.5 assessment"
            )

        ground_value = sora.get("ground_risk_mitigations")
        if ground_value is not None:
            ground = dict(
                _mapping(
                    ground_value,
                    field="sora.ground_risk_mitigations",
                )
            )
            legacy_m1 = ground.pop("m1_strategic", None)
            if legacy_m1 is not None and _applied(
                legacy_m1,
                field="sora.ground_risk_mitigations.m1_strategic",
            ):
                raise ValueError(
                    "mission.v6 M1 strategic credit cannot be mapped safely to "
                    "SORA 2.5 M1(A), M1(B), or M1(C)"
                )
            legacy_m3 = ground.pop("m3_erp", None)
            if legacy_m3 is not None and _applied(
                legacy_m3,
                field="sora.ground_risk_mitigations.m3_erp",
            ):
                raise ValueError(
                    "mission.v6 M3 ERP credit has no SORA 2.5 ground-credit mapping"
                )
            legacy_m2 = ground.get("m2_impact_reduction")
            if legacy_m2 is not None and _applied(
                legacy_m2,
                field="sora.ground_risk_mitigations.m2_impact_reduction",
            ):
                raise ValueError(
                    "mission.v6 M2 credit requires new evidence and a revalidated "
                    "SORA 2.5 ground-risk footprint"
                )
            sora["ground_risk_mitigations"] = ground

        air_risk_value = sora.get("air_risk")
        if air_risk_value is not None:
            air_risk = dict(_mapping(air_risk_value, field="sora.air_risk"))
            tactical = air_risk.get("tactical_mitigation")
            if tactical is not None:
                if _applied(tactical, field="sora.air_risk.tactical_mitigation"):
                    raise ValueError(
                        "mission.v6 tactical ARC credit cannot be migrated; SORA "
                        "2.5 tactical mitigation fulfils TMPR and does not lower ARC"
                    )
                air_risk["tactical_mitigation"] = {
                    "applied": False,
                    "robustness": "none",
                }
            sora["air_risk"] = air_risk
        migrated["sora"] = sora

    return migrated


__all__ = [
    "MISSION_V6",
    "detect_mission_version",
    "migrate_mission_v6_to_v7",
]
