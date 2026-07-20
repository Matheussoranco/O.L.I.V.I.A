"""Physics constants — lookup by symbol, name, and natural-language alias."""

from __future__ import annotations

from olivia.tools import physics


def test_lookup_by_alias_phrase():
    result = physics.physical_constant("what is the speed of light")
    assert result["ok"]
    assert result["symbol"] == "c"
    assert result["value"] == 299792458.0
    assert result["unit"] == "m/s"


def test_lookup_by_exact_symbol():
    assert physics.physical_constant("N_A")["value"] == 6.02214076e23
    assert physics.physical_constant("G")["symbol"] == "G"


def test_lookup_common_constants():
    assert physics.physical_constant("Planck constant")["value"] == 6.62607015e-34
    assert physics.physical_constant("boltzmann constant")["symbol"] == "k_B"
    assert physics.physical_constant("universal gas constant")["symbol"] == "R"


def test_most_specific_alias_wins():
    # "reduced Planck constant" must not be shadowed by "Planck constant".
    assert physics.physical_constant("reduced planck constant")["symbol"] == "hbar"


def test_unknown_constant_reports_failure():
    result = physics.physical_constant("the meaning of life")
    assert result["ok"] is False
    assert "no known physical constant" in result["error"]
