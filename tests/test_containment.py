import pytest
from pydantic import ValidationError

from bvlos_sim.estimator.execution.containment import (
    adjacent_area_outer_limit_m,
    derive_containment_requirement,
)
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


def _footprint(*, ground_risk_buffer_m: float = 300.0) -> GroundRiskFootprint:
    return GroundRiskFootprint(
        operational_volume_margin_m=30.0,
        ground_risk_buffer_m=ground_risk_buffer_m,
        vertical_contingency_margin_m=10.0,
        maximum_height_agl_m=130.0,
        derivation="Test footprint assessment",
    )


def _evidence(
    *,
    density: float = 12.0,
    assembly: OutdoorAssemblyCategory = OutdoorAssemblyCategory.BELOW_40000,
    sheltering: bool = False,
    revalidation_reference: str | None = "TEST-GRC-RECHECK",
) -> AdjacentAreaContainmentEvidence:
    return AdjacentAreaContainmentEvidence(
        assessment_reference="TEST-CONTAINMENT",
        average_population_density_ppl_km2=density,
        largest_outdoor_assembly=assembly,
        sheltering_applicable=sheltering,
        ground_risk_buffer_revalidation_reference=revalidation_reference,
    )


@pytest.mark.parametrize(
    ("speed_mps", "expected_m"),
    [(1.0, 5_000.0), (100.0, 18_000.0), (300.0, 35_000.0)],
)
def test_adjacent_area_uses_three_minute_distance_clamped_to_5_35_km(
    speed_mps: float,
    expected_m: float,
) -> None:
    assert adjacent_area_outer_limit_m(speed_mps) == expected_m


def test_sub_250g_requires_low_containment_without_dimension_or_evidence() -> None:
    requirement = derive_containment_requirement(
        aircraft_mass_kg=0.249999,
        characteristic_dimension_m=None,
        max_speed_mps=25.0,
        sail=Sail.II,
        footprint=_footprint(),
        evidence=None,
    )
    assert requirement.method == ContainmentMethod.SUB_250G
    assert requirement.required_robustness == ContainmentRobustness.LOW
    assert requirement.adjacent_area_assessment_required is False


def test_exactly_250g_requires_adjacent_area_evidence() -> None:
    with pytest.raises(ValueError, match="at least 250 g"):
        derive_containment_requirement(
            aircraft_mass_kg=0.25,
            characteristic_dimension_m=1.0,
            max_speed_mps=24.0,
            sail=Sail.II,
            footprint=_footprint(),
            evidence=None,
        )


def test_grb_equal_to_adjacent_limit_skips_adjacent_assessment() -> None:
    requirement = derive_containment_requirement(
        aircraft_mass_kg=1.0,
        characteristic_dimension_m=1.0,
        max_speed_mps=25.0,
        sail=Sail.II,
        footprint=_footprint(ground_risk_buffer_m=5_000.0),
        evidence=None,
    )
    assert requirement.method == ContainmentMethod.GRB_COVERS_ADJACENT_AREA
    assert requirement.adjacent_area_assessment_required is False


@pytest.mark.parametrize(
    ("speed_mps", "dimension_m", "sheltering", "expected_table"),
    [
        (24.999, 1.0, True, 8),
        (25.0, 1.0, True, 9),
        (34.999, 3.0, False, 10),
        (35.0, 3.0, False, 11),
        (74.999, 8.0, False, 11),
        (75.0, 8.0, False, 12),
        (124.999, 20.0, False, 12),
        (125.0, 20.0, False, 13),
        (199.999, 39.999, False, 13),
    ],
)
def test_speed_dimension_boundaries_select_conservative_next_table(
    speed_mps: float,
    dimension_m: float,
    sheltering: bool,
    expected_table: int,
) -> None:
    requirement = derive_containment_requirement(
        aircraft_mass_kg=10.0,
        characteristic_dimension_m=dimension_m,
        max_speed_mps=speed_mps,
        sail=Sail.VI,
        footprint=_footprint(),
        evidence=_evidence(sheltering=sheltering),
    )
    assert requirement.selected_table == expected_table


@pytest.mark.parametrize(("speed_mps", "dimension_m"), [(200.0, 39.0), (199.0, 40.0)])
def test_aircraft_outside_table_13_is_out_of_scope(
    speed_mps: float,
    dimension_m: float,
) -> None:
    requirement = derive_containment_requirement(
        aircraft_mass_kg=10.0,
        characteristic_dimension_m=dimension_m,
        max_speed_mps=speed_mps,
        sail=Sail.VI,
        footprint=_footprint(),
        evidence=_evidence(),
    )
    assert requirement.required_robustness == ContainmentRobustness.OUT_OF_SCOPE
    assert requirement.within_specific_category_method_scope is False


def test_exact_density_threshold_uses_next_higher_risk_column() -> None:
    below = derive_containment_requirement(
        aircraft_mass_kg=2.0,
        characteristic_dimension_m=3.0,
        max_speed_mps=34.0,
        sail=Sail.I,
        footprint=_footprint(),
        evidence=_evidence(density=499.999, revalidation_reference=None),
    )
    at = derive_containment_requirement(
        aircraft_mass_kg=2.0,
        characteristic_dimension_m=3.0,
        max_speed_mps=34.0,
        sail=Sail.I,
        footprint=_footprint(),
        evidence=_evidence(density=500.0),
    )
    assert below.required_robustness == ContainmentRobustness.LOW
    assert at.required_robustness == ContainmentRobustness.MEDIUM


def test_assembly_assessment_becomes_inapplicable_only_above_one_km_grb() -> None:
    with pytest.raises(ValueError, match="must not be 'not_applicable'"):
        derive_containment_requirement(
            aircraft_mass_kg=2.0,
            characteristic_dimension_m=3.0,
            max_speed_mps=34.0,
            sail=Sail.VI,
            footprint=_footprint(ground_risk_buffer_m=1_000.0),
            evidence=_evidence(assembly=OutdoorAssemblyCategory.NOT_APPLICABLE),
        )
    requirement = derive_containment_requirement(
        aircraft_mass_kg=2.0,
        characteristic_dimension_m=3.0,
        max_speed_mps=34.0,
        sail=Sail.VI,
        footprint=_footprint(ground_risk_buffer_m=1_000.1),
        evidence=_evidence(assembly=OutdoorAssemblyCategory.NOT_APPLICABLE),
    )
    assert (
        requirement.outdoor_assembly_operational_limit
        == OutdoorAssemblyOperationalLimit.NOT_APPLICABLE
    )


def test_medium_or_high_containment_requires_grb_revalidation_reference() -> None:
    with pytest.raises(ValueError, match="ground_risk_buffer_revalidation_reference"):
        derive_containment_requirement(
            aircraft_mass_kg=2.0,
            characteristic_dimension_m=3.0,
            max_speed_mps=34.0,
            sail=Sail.I,
            footprint=_footprint(),
            evidence=_evidence(density=500.0, revalidation_reference=None),
        )


def test_containment_output_rejects_contradictory_scope_artifact() -> None:
    with pytest.raises(ValidationError, match="method-scope flag"):
        ContainmentRequirement(
            method=ContainmentMethod.SUB_250G,
            adjacent_area_outer_limit_m=5_000.0,
            adjacent_area_assessment_required=False,
            population_density_operational_limit=(
                PopulationDensityOperationalLimit.NOT_REQUIRED
            ),
            outdoor_assembly_operational_limit=(
                OutdoorAssemblyOperationalLimit.NOT_REQUIRED
            ),
            required_robustness=ContainmentRobustness.LOW,
            within_specific_category_method_scope=False,
        )
