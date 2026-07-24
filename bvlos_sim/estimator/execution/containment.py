"""JARUS SORA 2.5 Step 8 containment requirement derivation.

This module implements only the requirements-identification task in Main Body
Tables 8-13. It deliberately never claims compliance with the integrity and
assurance criteria in Annex E.
"""

from dataclasses import dataclass

from bvlos_sim.schemas.sora import (
    AdjacentAreaContainmentEvidence,
    ContainmentMethod,
    ContainmentRequirement,
    ContainmentRobustness,
    GroundRiskFootprint,
    OutdoorAssemblyCategory,
    OutdoorAssemblyOperationalLimit,
    PopulationDensityOperationalLimit,
    Sail,
)

_MIN_ADJACENT_AREA_M = 5_000.0
_MAX_ADJACENT_AREA_M = 35_000.0
_FLYAWAY_DURATION_S = 180.0


@dataclass(frozen=True, slots=True)
class _OperationalColumn:
    population_limit: PopulationDensityOperationalLimit
    population_upper_exclusive: float | None
    assembly_limit: OutdoorAssemblyOperationalLimit


_NO_UPPER = _OperationalColumn(
    PopulationDensityOperationalLimit.NO_UPPER_LIMIT,
    None,
    OutdoorAssemblyOperationalLimit.NO_UPPER_LIMIT,
)
_NO_UPPER_400K = _OperationalColumn(
    PopulationDensityOperationalLimit.NO_UPPER_LIMIT,
    None,
    OutdoorAssemblyOperationalLimit.MAXIMUM_400000,
)


def _below(
    density: int,
    *,
    assembly_limit: OutdoorAssemblyOperationalLimit,
) -> _OperationalColumn:
    return _OperationalColumn(
        PopulationDensityOperationalLimit[f"BELOW_{density}"],
        float(density),
        assembly_limit,
    )


_TABLE_COLUMNS: dict[int, tuple[_OperationalColumn, ...]] = {
    8: (
        _NO_UPPER,
        _NO_UPPER_400K,
        _below(50000, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
    ),
    9: (
        _NO_UPPER,
        _NO_UPPER_400K,
        _below(50000, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
        _below(5000, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
    ),
    10: (
        _NO_UPPER,
        _below(
            50000,
            assembly_limit=OutdoorAssemblyOperationalLimit.MAXIMUM_400000,
        ),
        _below(5000, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
        _below(500, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
    ),
}
_LARGE_COLUMNS = (
    _NO_UPPER,
    _below(
        50000,
        assembly_limit=OutdoorAssemblyOperationalLimit.MAXIMUM_400000,
    ),
    _below(5000, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
    _below(500, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
    _below(50, assembly_limit=OutdoorAssemblyOperationalLimit.BELOW_40000),
)
_TABLE_COLUMNS.update({11: _LARGE_COLUMNS, 12: _LARGE_COLUMNS, 13: _LARGE_COLUMNS})

_L = ContainmentRobustness.LOW
_M = ContainmentRobustness.MEDIUM
_H = ContainmentRobustness.HIGH
_OOS = ContainmentRobustness.OUT_OF_SCOPE

_TABLE_REQUIREMENTS: dict[int, dict[Sail, tuple[ContainmentRobustness, ...]]] = {
    8: {
        Sail.I: (_H, _M, _L),
        Sail.II: (_H, _M, _L),
        Sail.III: (_M, _L, _L),
        Sail.IV: (_L, _L, _L),
        Sail.V: (_L, _L, _L),
        Sail.VI: (_L, _L, _L),
    },
    9: {
        Sail.I: (_OOS, _H, _M, _L),
        Sail.II: (_OOS, _H, _M, _L),
        Sail.III: (_OOS, _M, _L, _L),
        Sail.IV: (_M, _L, _L, _L),
        Sail.V: (_L, _L, _L, _L),
        Sail.VI: (_L, _L, _L, _L),
    },
    10: {
        Sail.I: (_OOS, _H, _M, _L),
        Sail.II: (_OOS, _H, _M, _L),
        Sail.III: (_OOS, _M, _L, _L),
        Sail.IV: (_M, _L, _L, _L),
        Sail.V: (_L, _L, _L, _L),
        Sail.VI: (_L, _L, _L, _L),
    },
    11: {
        Sail.I: (_OOS, _OOS, _H, _M, _L),
        Sail.II: (_OOS, _OOS, _H, _M, _L),
        Sail.III: (_OOS, _OOS, _M, _L, _L),
        Sail.IV: (_OOS, _M, _L, _L, _L),
        Sail.V: (_M, _L, _L, _L, _L),
        Sail.VI: (_L, _L, _L, _L, _L),
    },
    12: {
        Sail.I: (_OOS, _OOS, _OOS, _H, _M),
        Sail.II: (_OOS, _OOS, _OOS, _H, _M),
        Sail.III: (_OOS, _OOS, _OOS, _M, _L),
        Sail.IV: (_OOS, _OOS, _M, _L, _L),
        Sail.V: (_OOS, _M, _L, _L, _L),
        Sail.VI: (_M, _L, _L, _L, _L),
    },
    13: {
        Sail.I: (_OOS, _OOS, _OOS, _OOS, _H),
        Sail.II: (_OOS, _OOS, _OOS, _OOS, _H),
        Sail.III: (_OOS, _OOS, _OOS, _OOS, _M),
        Sail.IV: (_OOS, _OOS, _OOS, _M, _L),
        Sail.V: (_OOS, _OOS, _M, _L, _L),
        Sail.VI: (_OOS, _M, _L, _L, _L),
    },
}


def adjacent_area_outer_limit_m(max_speed_mps: float) -> float:
    """Return the 3-minute flyaway distance clamped to 5-35 km."""
    return min(
        max(max_speed_mps * _FLYAWAY_DURATION_S, _MIN_ADJACENT_AREA_M),
        _MAX_ADJACENT_AREA_M,
    )


def _table_for_aircraft(
    *,
    characteristic_dimension_m: float,
    max_speed_mps: float,
    sheltering_applicable: bool,
) -> int | None:
    if characteristic_dimension_m <= 1.0 and max_speed_mps < 25.0:
        if not sheltering_applicable:
            raise ValueError(
                "SORA Table 8 assumes sheltering for a 1 m-class UA; the "
                "unsupported no-shelter case requires an authority-agreed method"
            )
        return 8
    if characteristic_dimension_m <= 3.0 and max_speed_mps < 35.0:
        return 9 if sheltering_applicable else 10
    if sheltering_applicable:
        raise ValueError(
            "sheltering credit for a UA outside the 3 m class requires the "
            "unsupported SORA Annex F alternative-method evaluator"
        )
    if characteristic_dimension_m <= 8.0 and max_speed_mps < 75.0:
        return 11
    if characteristic_dimension_m <= 20.0 and max_speed_mps < 125.0:
        return 12
    if characteristic_dimension_m < 40.0 and max_speed_mps < 200.0:
        return 13
    return None


def _assembly_is_covered(
    actual: OutdoorAssemblyCategory,
    limit: OutdoorAssemblyOperationalLimit,
) -> bool:
    if actual == OutdoorAssemblyCategory.NOT_APPLICABLE:
        return True
    if limit == OutdoorAssemblyOperationalLimit.NO_UPPER_LIMIT:
        return True
    if limit == OutdoorAssemblyOperationalLimit.MAXIMUM_400000:
        return actual in {
            OutdoorAssemblyCategory.BETWEEN_40000_AND_400000,
            OutdoorAssemblyCategory.BELOW_40000,
        }
    return actual == OutdoorAssemblyCategory.BELOW_40000


def _select_column(
    *,
    table: int,
    evidence: AdjacentAreaContainmentEvidence,
) -> tuple[int, _OperationalColumn]:
    for index in range(len(_TABLE_COLUMNS[table]) - 1, -1, -1):
        column = _TABLE_COLUMNS[table][index]
        density_covered = (
            column.population_upper_exclusive is None
            or evidence.average_population_density_ppl_km2
            < column.population_upper_exclusive
        )
        if density_covered and _assembly_is_covered(
            evidence.largest_outdoor_assembly, column.assembly_limit
        ):
            return index, column
    raise AssertionError("the no-upper-limit containment column must cover all inputs")


def _unassessed_requirement(
    *,
    adjacent_limit_m: float,
    method: ContainmentMethod,
    robustness: ContainmentRobustness,
    eligible: bool,
) -> ContainmentRequirement:
    return ContainmentRequirement(
        method=method,
        adjacent_area_outer_limit_m=adjacent_limit_m,
        adjacent_area_assessment_required=False,
        population_density_operational_limit=(
            PopulationDensityOperationalLimit.NOT_REQUIRED
        ),
        outdoor_assembly_operational_limit=(
            OutdoorAssemblyOperationalLimit.NOT_REQUIRED
        ),
        required_robustness=robustness,
        within_specific_category_method_scope=eligible,
    )


def derive_containment_requirement(
    *,
    aircraft_mass_kg: float,
    characteristic_dimension_m: float | None,
    max_speed_mps: float,
    sail: Sail | None,
    footprint: GroundRiskFootprint,
    evidence: AdjacentAreaContainmentEvidence | None,
) -> ContainmentRequirement:
    """Derive Step 8 operational limits and robustness without claiming compliance."""
    adjacent_limit_m = adjacent_area_outer_limit_m(max_speed_mps)
    if sail is None:
        return _unassessed_requirement(
            adjacent_limit_m=adjacent_limit_m,
            method=ContainmentMethod.OUTSIDE_SPECIFIC_CATEGORY,
            robustness=_OOS,
            eligible=False,
        )
    if aircraft_mass_kg < 0.25:
        return _unassessed_requirement(
            adjacent_limit_m=adjacent_limit_m,
            method=ContainmentMethod.SUB_250G,
            robustness=_L,
            eligible=True,
        )
    if footprint.ground_risk_buffer_m >= adjacent_limit_m:
        return _unassessed_requirement(
            adjacent_limit_m=adjacent_limit_m,
            method=ContainmentMethod.GRB_COVERS_ADJACENT_AREA,
            robustness=_L,
            eligible=True,
        )
    if characteristic_dimension_m is None:
        raise ValueError(
            "vehicle.characteristic_dimension_m is required for Step 8 at or "
            "above 250 g"
        )
    if evidence is None:
        raise ValueError(
            "SORA Step 8 requires containment_evidence for an aircraft of at "
            "least 250 g when the Ground Risk Buffer is smaller than the "
            "adjacent-area limit"
        )

    assembly_not_applicable = footprint.ground_risk_buffer_m > 1_000.0
    if assembly_not_applicable != (
        evidence.largest_outdoor_assembly == OutdoorAssemblyCategory.NOT_APPLICABLE
    ):
        expectation = "must" if assembly_not_applicable else "must not"
        raise ValueError(
            "largest_outdoor_assembly "
            f"{expectation} be 'not_applicable' for the declared Ground Risk Buffer"
        )

    table = _table_for_aircraft(
        characteristic_dimension_m=characteristic_dimension_m,
        max_speed_mps=max_speed_mps,
        sheltering_applicable=evidence.sheltering_applicable,
    )
    if table is None:
        return ContainmentRequirement(
            method=ContainmentMethod.OUTSIDE_SPECIFIC_CATEGORY,
            adjacent_area_outer_limit_m=adjacent_limit_m,
            adjacent_area_assessment_required=True,
            assessment_reference=evidence.assessment_reference,
            average_population_density_ppl_km2=(
                evidence.average_population_density_ppl_km2
            ),
            largest_outdoor_assembly=evidence.largest_outdoor_assembly,
            sheltering_assumed=evidence.sheltering_applicable,
            population_density_operational_limit=(
                PopulationDensityOperationalLimit.NOT_REQUIRED
            ),
            outdoor_assembly_operational_limit=(
                OutdoorAssemblyOperationalLimit.NOT_REQUIRED
            ),
            required_robustness=_OOS,
            within_specific_category_method_scope=False,
        )

    column_index, column = _select_column(table=table, evidence=evidence)
    robustness = _TABLE_REQUIREMENTS[table][sail][column_index]
    revalidation_reference = evidence.ground_risk_buffer_revalidation_reference
    if robustness in {_M, _H} and revalidation_reference is None:
        raise ValueError(
            "medium or high containment requires a nonblank "
            "ground_risk_buffer_revalidation_reference proving that Step 2 GRC "
            "was re-evaluated with the containment-informed Ground Risk Buffer"
        )

    assembly_limit = (
        OutdoorAssemblyOperationalLimit.NOT_APPLICABLE
        if assembly_not_applicable
        else column.assembly_limit
    )
    return ContainmentRequirement(
        method=ContainmentMethod.TABLES_8_TO_13,
        adjacent_area_outer_limit_m=adjacent_limit_m,
        adjacent_area_assessment_required=True,
        selected_table=table,
        assessment_reference=evidence.assessment_reference,
        average_population_density_ppl_km2=(
            evidence.average_population_density_ppl_km2
        ),
        largest_outdoor_assembly=evidence.largest_outdoor_assembly,
        sheltering_assumed=evidence.sheltering_applicable,
        population_density_operational_limit=column.population_limit,
        outdoor_assembly_operational_limit=assembly_limit,
        required_robustness=robustness,
        ground_risk_buffer_revalidation_reference=revalidation_reference,
        within_specific_category_method_scope=robustness != _OOS,
    )


__all__ = ["adjacent_area_outer_limit_m", "derive_containment_requirement"]
