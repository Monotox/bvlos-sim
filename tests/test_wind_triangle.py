import math

from estimator.math.wind_triangle import solve_wind_triangle


def test_no_wind_matches_track_and_tas() -> None:
    solution = solve_wind_triangle(
        track_deg=90.0,
        tas_mps=20.0,
        wind_east_mps=0.0,
        wind_north_mps=0.0,
    )

    assert solution is not None
    assert math.isclose(solution.groundspeed_mps, 20.0, rel_tol=1e-9)
    assert math.isclose(solution.required_heading_deg, 90.0, rel_tol=1e-9)
    assert math.isclose(solution.crab_angle_deg, 0.0, abs_tol=1e-9)


def test_eastbound_east_wind_is_tailwind() -> None:
    solution = solve_wind_triangle(
        track_deg=90.0,
        tas_mps=20.0,
        wind_east_mps=5.0,
        wind_north_mps=0.0,
    )

    assert solution is not None
    assert math.isclose(solution.groundspeed_mps, 25.0, rel_tol=1e-9)
    assert math.isclose(solution.wind_along_track_mps, 5.0, rel_tol=1e-9)


def test_eastbound_west_wind_is_headwind() -> None:
    solution = solve_wind_triangle(
        track_deg=90.0,
        tas_mps=20.0,
        wind_east_mps=-5.0,
        wind_north_mps=0.0,
    )

    assert solution is not None
    assert math.isclose(solution.groundspeed_mps, 15.0, rel_tol=1e-9)
    assert math.isclose(solution.wind_along_track_mps, -5.0, rel_tol=1e-9)


def test_crosswind_no_solution_when_exceeds_tas() -> None:
    solution = solve_wind_triangle(
        track_deg=0.0,
        tas_mps=10.0,
        wind_east_mps=12.0,
        wind_north_mps=0.0,
    )
    assert solution is None


def test_zero_tas_returns_none() -> None:
    solution = solve_wind_triangle(
        track_deg=90.0,
        tas_mps=0.0,
        wind_east_mps=0.0,
        wind_north_mps=0.0,
    )
    assert solution is None


def test_zero_tas_with_headwind_returns_none() -> None:
    solution = solve_wind_triangle(
        track_deg=90.0,
        tas_mps=0.0,
        wind_east_mps=5.0,
        wind_north_mps=0.0,
    )
    assert solution is None
