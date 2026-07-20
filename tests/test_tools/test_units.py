"""Units and dimensional analysis — exact conversions, dimensional guards."""

from __future__ import annotations

import math

from olivia.tools import units


def test_metric_conversions_and_prefixes():
    assert units.convert(1, "km", "m") == 1000.0
    assert units.convert(2500, "g", "kg") == 2.5
    assert math.isclose(units.convert(5, "mg", "g"), 0.005, rel_tol=1e-9)
    assert math.isclose(units.convert(5, "ft", "cm"), 152.4, rel_tol=1e-9)


def test_compound_unit_conversion():
    assert math.isclose(units.convert(60, "mph", "m/s"), 26.8224, rel_tol=1e-9)
    assert math.isclose(units.convert(1, "km/h", "m/s"), 1000 / 3600, rel_tol=1e-9)


def test_energy_conversion_across_named_units():
    assert math.isclose(units.convert(1, "cal", "J"), 4.184, rel_tol=1e-12)
    assert math.isclose(units.convert(1, "kWh", "J"), 3.6e6, rel_tol=1e-9)


def test_temperature_is_affine():
    assert units.convert(100, "celsius", "fahrenheit") == 212.0
    assert units.convert(32, "fahrenheit", "celsius") == 0.0
    assert units.convert(0, "celsius", "K") == 273.15


def test_incompatible_dimensions_return_none():
    assert units.convert(1, "m", "s") is None
    assert units.convert(1, "kg", "J") is None
    assert units.convert(1, "not_a_unit", "m") is None


def test_parse_unit_reduces_to_si_dimension():
    factor, dim = units.parse_unit("N")
    assert factor == 1.0
    assert dim == (1, 1, -2, 0, 0, 0, 0)  # m·kg·s^-2
    assert units.parse_unit("furlong") is None


def test_dimensional_analysis_names_quantities():
    assert units.dimensional_analysis("N")["quantity"] == "force"
    assert units.dimensional_analysis("km/h")["quantity"] == "velocity"
    assert units.dimensional_analysis("J")["quantity"] == "energy"
    assert units.dimensional_analysis("Pa")["quantity"] == "pressure"


def test_convert_units_tool_shape():
    ok = units.convert_units(1, "km", "m")
    assert ok["ok"] and ok["value"] == 1000.0
    bad = units.convert_units(1, "m", "kg")
    assert bad["ok"] is False and "incompatible" in bad["error"]
