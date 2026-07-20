"""Chemistry — formula parsing, molar mass, and exact equation balancing."""

from __future__ import annotations

import math

from olivia.tools import chemistry


def test_periodic_table_is_complete():
    assert len(chemistry.ELEMENTS) == 118
    assert chemistry.ELEMENTS["H"][0] == 1
    assert chemistry.ELEMENTS["Og"][0] == 118


def test_parse_formula_handles_groups_and_hydrates():
    assert chemistry.parse_formula("H2O") == {"H": 2, "O": 1}
    assert chemistry.parse_formula("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}
    assert chemistry.parse_formula("Fe2(SO4)3") == {"Fe": 2, "S": 3, "O": 12}
    # Hydrate via both the middle dot and the ASCII period.
    assert chemistry.parse_formula("CuSO4·5H2O") == {"Cu": 1, "S": 1, "O": 9, "H": 10}
    assert chemistry.parse_formula("CuSO4.5H2O") == chemistry.parse_formula("CuSO4·5H2O")


def test_parse_formula_rejects_nonsense():
    assert chemistry.parse_formula("water") is None
    assert chemistry.parse_formula("Xx2") is None
    assert chemistry.parse_formula("Ca(OH2") is None  # unbalanced paren


def test_molar_mass_and_breakdown():
    result = chemistry.molar_mass("H2O")
    assert result["ok"]
    assert math.isclose(result["molar_mass"], 18.015, abs_tol=0.01)
    assert result["unit"] == "g/mol"
    oxygen = next(b for b in result["breakdown"] if b["element"] == "O")
    assert math.isclose(oxygen["percent"], 88.8, abs_tol=0.3)


def test_molar_mass_sulfuric_acid():
    assert math.isclose(chemistry.molar_mass("H2SO4")["molar_mass"], 98.07, abs_tol=0.02)


def test_molar_mass_invalid_formula():
    assert chemistry.molar_mass("nonsense!")["ok"] is False


def test_balance_water_synthesis():
    result = chemistry.balance_equation("H2 + O2 -> H2O")
    assert result["ok"]
    assert result["coefficients"] == [2, 1, 2]
    assert result["balanced"] == "2 H2 + O2 -> 2 H2O"


def test_balance_combustion_and_equals_separator():
    result = chemistry.balance_equation("C3H8 + O2 = CO2 + H2O")
    assert result["ok"]
    assert result["coefficients"] == [1, 5, 3, 4]


def test_balance_reports_failure_cleanly():
    assert chemistry.balance_equation("H2 + O2")["ok"] is False  # no arrow
    assert chemistry.balance_equation("Na -> Cl")["ok"] is False  # unbalanceable
