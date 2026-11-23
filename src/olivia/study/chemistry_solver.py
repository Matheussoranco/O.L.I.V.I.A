"""Deterministic chemistry word-problem solver.

Covers stoichiometry, moles, percent composition, and oxidation states.

Uses IUPAC atomic weights, exact rational equation balancing, and SI unit conversion
from ``olivia.tools.chemistry`` and ``olivia.tools.units``. Abstains cleanly (returns
``None``) whenever a problem is ambiguous or outside supported rules.
"""

from __future__ import annotations

import re

from olivia.core.records import SolutionStep, WorkedSolution
from olivia.tools.chemistry import (
    ELEMENTS,
    balance_equation,
    molar_mass,
    oxidation_state,
    parse_formula,
    percent_composition,
    resolve_element,
    resolve_formula,
)
from olivia.tools.units import convert

_NUM = r"(\d+(?:\.\d+)?)"
_MASS_UNIT = r"(kg|mg|ug|µg|g|grams?|kilograms?|milligrams?|lb|lbs|pounds?|oz|ounces?)"
_SPECIES = r"([A-Za-z][A-Za-z0-9()\[\]{}·.\s-]{0,30}?)"

# Percent composition by mass:
# "What is the percent composition by mass of oxygen in H2O?"
# "Mass percent of carbon in C6H12O6"
_PERCENT_COMP_RE = re.compile(
    r"(?:percent(?:age)?\s+composition(?:\s+by\s+mass)?|mass\s+percent(?:age)?|percent(?:age)?(?:\s+by\s+mass)?)"
    r"\s+of\s+([A-Za-z]+)\s+in\s+([A-Za-z0-9()\[\]{}·.\s-]+?)\s*[.?]?\s*$",
    re.IGNORECASE,
)

# Oxidation state / oxidation number:
# "What is the oxidation state of sulfur in H2SO4?"
_OX_STATE_RE = re.compile(
    r"oxidation\s+(?:state|number)\s+of\s+([A-Za-z]+)\s+in\s+([A-Za-z0-9()\[\]{}·.\s-]+?)\s*[.?]?\s*$",
    re.IGNORECASE,
)

# Mass -> moles:
# "How many moles are in 36 g of water?"
# "Convert 58.44 g of NaCl to moles"
_MASS_TO_MOLES_RE = re.compile(
    rf"(?:how\s+many\s+moles?\s+(?:are\s+)?(?:there\s+)?in|moles?\s+(?:are\s+)?in|convert)\s+"
    rf"{_NUM}\s*{_MASS_UNIT}\s+of\s+{_SPECIES}"
    rf"(?:\s+(?:to|into)\s+moles?)?\s*[.?]?\s*$",
    re.IGNORECASE,
)

# Moles -> mass:
# "What mass of NaCl contains 0.5 mol?"
# "How many grams are in 2 mol of H2O?"
_MOLES_TO_MASS_1_RE = re.compile(
    rf"(?:what\s+(?:is\s+the\s+)?mass(?:\s+in\s+{_MASS_UNIT})?\s+of|mass\s+of)\s+"
    rf"{_SPECIES}\s+(?:contains?|is\s+in|in|for|corresponds\s+to)\s+"
    rf"{_NUM}\s*(?:moles?|mol)\s*[.?]?\s*$",
    re.IGNORECASE,
)
_MOLES_TO_MASS_2_RE = re.compile(
    rf"(?:how\s+many\s+{_MASS_UNIT}\s+(?:of\s+{_SPECIES}\s+)?(?:are\s+)?in|"
    rf"(?:what\s+is\s+the\s+)?mass\s+of)\s+"
    rf"{_NUM}\s*(?:moles?|mol)\s+of\s+{_SPECIES}\s*[.?]?\s*$",
    re.IGNORECASE,
)

# Complete combustion mass-to-mass stoichiometry:
# "How many grams of CO2 are produced by completely burning 10 g of CH4?"
# "What mass of H2O is formed from burning 5 g of C3H8?"
_COMBUSTION_RE = re.compile(
    rf"(?:how\s+many\s+{_MASS_UNIT}|what\s+mass(?:\s+in\s+{_MASS_UNIT})?)\s+of\s+"
    rf"([A-Za-z0-9()\[\]{{}}]+)\s+(?:are|is)\s+(?:produced|formed|generated)\s+"
    rf"(?:by|from|when)\s+(?:completely\s+)?(?:burning|combusting|the\s+(?:complete\s+)?combustion\s+of)\s+"
    rf"{_NUM}\s*{_MASS_UNIT}\s+of\s+([A-Za-z0-9()\[\]{{}}\s]+?)\s*[.?]?\s*$",
    re.IGNORECASE,
)


def _step(steps: list[SolutionStep], description: str, result: str = "") -> None:
    steps.append(SolutionStep(n=len(steps) + 1, description=description, result=result))


def _to_grams(value: float, unit: str) -> float | None:
    return convert(value, unit, "g")


def _from_grams(grams: float, unit: str) -> float | None:
    return convert(grams, "g", unit)


def _solve_percent_composition(problem: str) -> WorkedSolution | None:
    match = _PERCENT_COMP_RE.search(problem)
    if not match:
        return None
    el_raw, formula_raw = match.group(1).strip(), match.group(2).strip()
    res = percent_composition(formula_raw, el_raw)
    if not res["ok"]:
        return None
    el = res["element"]
    formula = res["formula"]
    weight = ELEMENTS[el][1]
    steps: list[SolutionStep] = []
    _step(steps, f"Molar mass of {formula}", f"{res['molar_mass']:g} g/mol")
    _step(
        steps,
        f"Mass of {el} in 1 mol {formula}: {res['count']} × {weight:g} g/mol",
        f"{res['element_mass']:g} g/mol",
    )
    _step(
        steps,
        f"Percent by mass: ({res['element_mass']:g} / {res['molar_mass']:g}) × 100%",
        f"{res['percent']:.2f}%",
    )
    return WorkedSolution(
        problem=problem,
        subject="chemistry",
        steps=steps,
        final_answer=f"{res['percent']:.2f}%",
        method="chemistry",
        confidence=0.95,
    )


def _solve_oxidation_state(problem: str) -> WorkedSolution | None:
    match = _OX_STATE_RE.search(problem)
    if not match:
        return None
    el_raw, formula_raw = match.group(1).strip(), match.group(2).strip()
    res = oxidation_state(formula_raw, el_raw)
    if not res["ok"]:
        return None
    formula = res["formula"]
    el = res["element"]
    counts = parse_formula(formula)
    assert counts is not None
    steps: list[SolutionStep] = []
    if res["known"]:
        rules = ", ".join(f"{k} = {v:+d}" for k, v in sorted(res["known"].items()))
        _step(steps, f"Assign standard IUPAC oxidation numbers in {formula}", rules)
        terms = [f"{counts[k]}({v:+d})" for k, v in sorted(res["known"].items())]
        target_term = f"{counts[el]}·x" if counts[el] > 1 else "x"
        _step(
            steps,
            f"Neutral compound charge balance ({el} = x)",
            f"{' + '.join(terms)} + {target_term} = {res['charge']}",
        )
    _step(steps, f"Solve for the oxidation state of {el}", f"{el} = {res['formatted']}")
    return WorkedSolution(
        problem=problem,
        subject="chemistry",
        steps=steps,
        final_answer=res["formatted"],
        method="chemistry",
        confidence=0.95,
    )


def _solve_mass_to_moles(problem: str) -> WorkedSolution | None:
    match = _MASS_TO_MOLES_RE.search(problem)
    if not match:
        return None
    mass_val = float(match.group(1))
    unit_raw = match.group(2).strip()
    species_raw = match.group(3).strip()
    formula = resolve_formula(species_raw)
    if formula is None:
        return None
    grams = _to_grams(mass_val, unit_raw)
    if grams is None:
        return None
    mm = molar_mass(formula)
    if not mm["ok"]:
        return None
    moles = grams / mm["molar_mass"]
    steps: list[SolutionStep] = []
    _step(steps, f"Molar mass of {formula}", f"{mm['molar_mass']:g} g/mol")
    if unit_raw.lower() not in ("g", "gram", "grams"):
        _step(steps, f"Convert {mass_val:g} {unit_raw} to grams", f"{grams:g} g")
    _step(steps, f"n = m / M = {grams:g} / {mm['molar_mass']:g}", f"{moles:.4g} mol")
    return WorkedSolution(
        problem=problem,
        subject="chemistry",
        steps=steps,
        final_answer=f"{moles:.4g} mol",
        method="chemistry",
        confidence=0.95,
    )


def _solve_moles_to_mass(problem: str) -> WorkedSolution | None:
    target_unit = "g"
    m1 = _MOLES_TO_MASS_1_RE.search(problem)
    if m1:
        if m1.group(1):
            target_unit = m1.group(1).strip()
        species_raw = m1.group(2).strip()
        moles = float(m1.group(3))
    else:
        m2 = _MOLES_TO_MASS_2_RE.search(problem)
        if not m2:
            return None
        if m2.group(1):
            target_unit = m2.group(1).strip()
        moles = float(m2.group(3))
        species_raw = m2.group(4).strip()
    formula = resolve_formula(species_raw)
    if formula is None:
        return None
    mm = molar_mass(formula)
    if not mm["ok"]:
        return None
    grams = moles * mm["molar_mass"]
    converted = _from_grams(grams, target_unit)
    if converted is None:
        return None
    display_unit = "g" if target_unit.lower() in ("g", "gram", "grams") else target_unit
    steps: list[SolutionStep] = []
    _step(steps, f"Molar mass of {formula}", f"{mm['molar_mass']:g} g/mol")
    _step(steps, f"m = n × M = {moles:g} × {mm['molar_mass']:g}", f"{grams:.4g} g")
    if display_unit != "g":
        _step(steps, f"Convert to {display_unit}", f"{converted:.4g} {display_unit}")
    return WorkedSolution(
        problem=problem,
        subject="chemistry",
        steps=steps,
        final_answer=f"{converted:.4g} {display_unit}",
        method="chemistry",
        confidence=0.95,
    )


def _solve_combustion_stoichiometry(problem: str) -> WorkedSolution | None:
    match = _COMBUSTION_RE.search(problem)
    if not match:
        return None
    out_unit = (match.group(1) or match.group(2) or "g").strip()
    target_raw = match.group(3).strip()
    given_val = float(match.group(4))
    given_unit = match.group(5).strip()
    fuel_raw = match.group(6).strip()

    fuel = resolve_formula(fuel_raw)
    target = resolve_formula(target_raw)
    if fuel is None or target is None:
        return None
    fuel_counts = parse_formula(fuel)
    if not fuel_counts or not set(fuel_counts).issubset({"C", "H", "O"}):
        return None
    if target not in {"CO2", "H2O", "O2"}:
        return None

    products = []
    if "C" in fuel_counts:
        products.append("CO2")
    if "H" in fuel_counts:
        products.append("H2O")
    if target not in products and target != "O2":
        return None

    eq = f"{fuel} + O2 -> {' + '.join(products)}"
    bal = balance_equation(eq)
    if not bal["ok"]:
        return None

    species_list: list[str] = bal["reactants"] + bal["products"]
    coeffs = dict(zip(species_list, bal["coefficients"], strict=False))
    if fuel not in coeffs or target not in coeffs:
        return None

    given_g = _to_grams(given_val, given_unit)
    if given_g is None:
        return None
    mm_fuel = molar_mass(fuel)
    mm_target = molar_mass(target)
    if not mm_fuel["ok"] or not mm_target["ok"]:
        return None

    n_fuel = given_g / mm_fuel["molar_mass"]
    n_target = n_fuel * (coeffs[target] / coeffs[fuel])
    mass_target_g = n_target * mm_target["molar_mass"]
    out_val = _from_grams(mass_target_g, out_unit)
    if out_val is None:
        return None
    display_unit = "g" if out_unit.lower() in ("g", "gram", "grams") else out_unit

    steps: list[SolutionStep] = []
    _step(steps, "Balance the complete combustion equation", bal["balanced"])
    _step(
        steps,
        f"Moles of {fuel}: {given_g:g} g / {mm_fuel['molar_mass']:g} g/mol",
        f"{n_fuel:.5g} mol",
    )
    _step(
        steps,
        f"Stoichiometric ratio ({coeffs[target]} mol {target} / {coeffs[fuel]} mol {fuel})",
        f"{n_target:.5g} mol {target}",
    )
    _step(
        steps,
        f"Mass of {target}: {n_target:.5g} mol × {mm_target['molar_mass']:g} g/mol",
        f"{out_val:.4g} {display_unit}",
    )
    return WorkedSolution(
        problem=problem,
        subject="chemistry",
        steps=steps,
        final_answer=f"{out_val:.4g} {display_unit}",
        method="chemistry",
        confidence=0.95,
    )


def solve_chemistry_problem(problem: str) -> WorkedSolution | None:
    """Try deterministic chemistry problem solvers; return ``None`` if no rule applies."""
    for fn in (
        _solve_percent_composition,
        _solve_oxidation_state,
        _solve_combustion_stoichiometry,
        _solve_mass_to_moles,
        _solve_moles_to_mass,
    ):
        solution = fn(problem)
        if solution is not None:
            return solution
    return None


__all__ = ["resolve_element", "solve_chemistry_problem"]
