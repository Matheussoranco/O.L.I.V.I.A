"""Tests for general deterministic units, chemistry, and physics solvers (#11).

All fixtures below are disjoint from the held-out ``symbolic_solving.json`` eval dataset,
exercising general domain laws, unit conversions, IUPAC rules, and abstention on ambiguous inputs.
"""

from __future__ import annotations

import math

import pytest

from olivia.llm.client import NullClient
from olivia.study.solver import solve_problem
from olivia.tools import chemistry, units


def _solve(problem: str):
    return solve_problem(problem, client=NullClient())


# ── Units: aliases, temperature shorthand disambiguation & natural language ──


def test_units_coulomb_preserved_while_temperature_pairs_work():
    # Bare 'C' in parse_unit stays Coulomb; C <-> A*s still uses charge dimension.
    parsed = units.parse_unit("C")
    assert parsed is not None
    assert parsed[1] == (0, 0, 1, 1, 0, 0, 0)
    assert math.isclose(units.convert(1.0, "C", "A*s") or 0.0, 1.0, rel_tol=1e-9)

    # Shorthand temperature pairs resolve cleanly.
    f_val = units.convert(100.0, "C", "F")
    c_val = units.convert(32.0, "F", "C")
    k_val = units.convert(0.0, "C", "K")
    assert f_val is not None and math.isclose(f_val, 212.0, rel_tol=1e-9)
    assert c_val is not None and math.isclose(c_val, 0.0, abs_tol=1e-9)
    assert k_val is not None and math.isclose(k_val, 273.15, rel_tol=1e-9)


def test_units_natural_language_queries_and_abstention():
    sol = _solve("How many kilometres are in 10 miles?")
    assert sol.method == "units"
    assert math.isclose(float(sol.final_answer.split()[0]), 16.0934, rel_tol=1e-3)

    sol2 = _solve("A parcel weighs 2.5 kg of books. How many pounds is that?")
    assert sol2.method == "units"
    assert math.isclose(float(sol2.final_answer.split()[0]), 5.51156, rel_tol=1e-3)

    # Incompatible dimensions must abstain cleanly (never fabricate a conversion).
    bad = _solve("How many litres are in 5 kg?")
    assert bad.method == "none"


# ── Chemistry: percent composition, oxidation states, moles & combustion ─────


def test_chemistry_percent_composition():
    res = chemistry.percent_composition("CO2", "carbon")
    assert res["ok"]
    assert math.isclose(res["percent"], 27.29, abs_tol=0.1)

    sol = _solve("What is the percent composition by mass of nitrogen in NH3?")
    assert sol.method == "chemistry"
    assert math.isclose(float(sol.final_answer.rstrip("%")), 82.24, abs_tol=0.2)

    missing = chemistry.percent_composition("H2O", "carbon")
    assert missing["ok"] is False


@pytest.mark.parametrize(
    ("formula", "element", "expected"),
    [
        ("KMnO4", "manganese", "+7"),
        ("K2Cr2O7", "Cr", "+6"),
        ("H2O2", "oxygen", "-1"),
        ("NaH", "hydrogen", "-1"),
        ("O2", "oxygen", "0"),
        ("HNO3", "nitrogen", "+5"),
    ],
)
def test_chemistry_oxidation_states(formula: str, element: str, expected: str):
    res = chemistry.oxidation_state(formula, element)
    assert res["ok"]
    assert res["formatted"] == expected

    sol = _solve(f"What is the oxidation state of {element} in {formula}?")
    assert sol.method == "chemistry"
    assert sol.final_answer == expected


def test_chemistry_oxidation_state_abstains_when_ambiguous():
    # Two unknown transition metals (Fe and Cr) without further structural info.
    res = chemistry.oxidation_state("FeCr2O4", "Cr")
    assert res["ok"] is False
    sol = _solve("What is the oxidation state of chromium in FeCr2O4?")
    assert sol.method == "none"


def test_chemistry_moles_and_mass_conversions():
    sol_moles = _solve("How many moles are in 2 kg of CO2?")
    assert sol_moles.method == "chemistry"
    assert math.isclose(float(sol_moles.final_answer.split()[0]), 45.44, rel_tol=1e-2)

    sol_mass = _solve("What mass of glucose contains 0.25 mol?")
    assert sol_mass.method == "chemistry"
    assert math.isclose(float(sol_mass.final_answer.split()[0]), 45.04, rel_tol=1e-2)

    sol_mass2 = _solve("How many grams are in 3 mol of NH3?")
    assert sol_mass2.method == "chemistry"
    assert math.isclose(float(sol_mass2.final_answer.split()[0]), 51.09, rel_tol=1e-2)


def test_chemistry_combustion_stoichiometry_and_abstention():
    # C3H8 + 5 O2 -> 3 CO2 + 4 H2O: 44.097 g C3H8 (~1 mol) -> 4 mol H2O (~72.06 g)
    sol = _solve("How many grams of H2O are produced by completely burning 44.1 g of C3H8?")
    assert sol.method == "chemistry"
    assert math.isclose(float(sol.final_answer.split()[0]), 72.06, rel_tol=0.01)

    # C2H5OH + 3 O2 -> 2 CO2 + 3 H2O: 23.035 g (~0.5 mol) -> 1 mol CO2 (~44.01 g)
    sol2 = _solve("How many grams of CO2 are produced by completely burning 23 g of C2H5OH?")
    assert sol2.method == "chemistry"
    assert math.isclose(float(sol2.final_answer.split()[0]), 43.94, rel_tol=0.01)

    # Non-CHO inorganic fuel must abstain cleanly.
    bad = _solve("How many grams of SO2 are produced by completely burning 10 g of FeS2?")
    assert bad.method == "none"


# ── Physics: kinematics, free fall, KE, Newton's 2nd law, photons, pendulum ─


def test_physics_kinematics_and_free_fall():
    sol_v = _solve(
        "A train accelerates from 10 m/s at 2 m/s^2 for 6 s. What is its final velocity?"
    )
    assert sol_v.method == "physics"
    assert math.isclose(float(sol_v.final_answer.split()[0]), 22.0, rel_tol=1e-3)

    sol_d = _solve("A car accelerates from rest at 4 m/s^2 for 5 s. How far does it travel?")
    assert sol_d.method == "physics"
    assert math.isclose(float(sol_d.final_answer.split()[0]), 50.0, rel_tol=1e-3)

    sol_fall = _solve(
        "A stone is dropped and falls for 3 seconds. How far does it fall, in metres?"
    )
    assert sol_fall.method == "physics"
    assert math.isclose(float(sol_fall.final_answer.split()[0]), 44.13, rel_tol=0.01)

    sol_fall_v = _solve("A stone is dropped and falls for 3 seconds. What is its velocity?")
    assert sol_fall_v.method == "physics"
    assert math.isclose(float(sol_fall_v.final_answer.split()[0]), 29.42, rel_tol=0.01)


def test_physics_free_fall_respects_initial_velocity_or_abstains():
    # Lead review regression: nonzero initial velocity must not silently fall back to v = g*t.
    down_v = _solve(
        "A ball is thrown downward at 10 m/s in free fall for 2 s. What is its velocity?"
    )
    assert down_v.method == "physics"
    assert math.isclose(float(down_v.final_answer.split()[0]), 29.6133, rel_tol=1e-3)

    down_d = _solve(
        "A ball with initial velocity 10 m/s downward falls for 2 s. How far does it fall?"
    )
    assert down_d.method == "physics"
    assert math.isclose(float(down_d.final_answer.split()[0]), 39.6133, rel_tol=1e-3)

    # Ambiguous or upward initial speed in free fall abstains instead of ignoring v0.
    assert (
        _solve("An object with initial speed 10 m/s falls for 2 s. What is its velocity?").method
        == "none"
    )
    assert (
        _solve(
            "An object thrown upward at 10 m/s in free fall for 2 s. What is its velocity?"
        ).method
        == "none"
    )


def test_physics_kinematics_same_givens_distinguishes_displacement_vs_velocity():
    # Lead review regression: initial velocity in givens must not hijack displacement queries.
    disp = _solve(
        "An object with initial velocity 3 m/s accelerates at 2 m/s^2 for 4 s. "
        "What is its displacement?"
    )
    assert disp.method == "physics"
    assert disp.final_answer == "28 m"

    vel = _solve(
        "An object with initial velocity 3 m/s accelerates at 2 m/s^2 for 4 s. "
        "What is its final velocity?"
    )
    assert vel.method == "physics"
    assert vel.final_answer == "11 m/s"


@pytest.mark.parametrize(
    ("problem", "expected"),
    [
        ("A car decelerates from 20 m/s at 4 m/s^2 for 3 s. Final velocity?", "8 m/s"),
        ("A car brakes from 20 m/s at 4 m/s^2 for 3 s. What is its final speed?", "8 m/s"),
        ("A car slows down from 20 m/s at 4 m/s^2 for 3 s. What is its final velocity?", "8 m/s"),
        ("A car decelerates from 20 m/s at 4 m/s^2 for 5 s. Final velocity?", "0 m/s"),
        ("A car accelerates from 20 m/s at -4 m/s^2 for 3 s. Final velocity?", "8 m/s"),
    ],
)
def test_physics_kinematics_deceleration_and_negative_acceleration(problem: str, expected: str):
    sol = _solve(problem)
    assert sol.method == "physics"
    assert sol.final_answer == expected


def test_physics_kinematics_deceleration_past_stop_abstains():
    sol = _solve("A car decelerates from 20 m/s at 4 m/s^2 for 6 s. Final velocity?")
    assert sol.method == "none"


def test_physics_energy_force_photon_pendulum():
    sol_ke = _solve("What is the kinetic energy of a 1000 g object moving at 10 m/s?")
    assert sol_ke.method == "physics"
    assert math.isclose(float(sol_ke.final_answer.split()[0]), 50.0, rel_tol=1e-3)

    sol_f = _solve("How much force is needed to accelerate a 500 g mass at 4 m/s^2?")
    assert sol_f.method == "physics"
    assert math.isclose(float(sol_f.final_answer.split()[0]), 2.0, rel_tol=1e-3)

    sol_a = _solve("What acceleration does a 30 N force produce on a 6 kg mass?")
    assert sol_a.method == "physics"
    assert math.isclose(float(sol_a.final_answer.split()[0]), 5.0, rel_tol=1e-3)

    sol_ph = _solve("What is the energy in eV of a photon with wavelength 500 nm?")
    assert sol_ph.method == "physics"
    assert math.isclose(float(sol_ph.final_answer.split()[0]), 2.4797, rel_tol=0.01)

    sol_pend = _solve("What is the period of a simple pendulum of length 400 cm, in seconds?")
    assert sol_pend.method == "physics"
    assert math.isclose(float(sol_pend.final_answer.split()[0]), 4.013, rel_tol=0.01)


def test_physics_abstains_on_ambiguous_or_unsupported_problems():
    assert _solve("Explain how quantum entanglement works.").method == "none"
    assert _solve("What is the wavelength of a photon with energy -5 eV?").method == "none"
