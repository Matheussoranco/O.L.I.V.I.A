"""Chemistry — periodic table, molar mass, and equation balancing, offline.

All deterministic: a formula parser that understands nested groups and
hydrates, molar mass from IUPAC standard atomic weights, and stoichiometric
balancing by exact rational nullspace (conservation of atoms).  No LLM, no
network — this is the symbolic backbone of O.L.I.V.I.A.'s chemistry answers.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Any

# symbol → (atomic number, standard atomic weight in g/mol).  Bracketed IUPAC
# values (no stable isotope) use a representative mass number.
ELEMENTS: dict[str, tuple[int, float]] = {
    "H": (1, 1.008),
    "He": (2, 4.002602),
    "Li": (3, 6.94),
    "Be": (4, 9.0121831),
    "B": (5, 10.81),
    "C": (6, 12.011),
    "N": (7, 14.007),
    "O": (8, 15.999),
    "F": (9, 18.998403163),
    "Ne": (10, 20.1797),
    "Na": (11, 22.98976928),
    "Mg": (12, 24.305),
    "Al": (13, 26.9815385),
    "Si": (14, 28.085),
    "P": (15, 30.973761998),
    "S": (16, 32.06),
    "Cl": (17, 35.45),
    "Ar": (18, 39.948),
    "K": (19, 39.0983),
    "Ca": (20, 40.078),
    "Sc": (21, 44.955908),
    "Ti": (22, 47.867),
    "V": (23, 50.9415),
    "Cr": (24, 51.9961),
    "Mn": (25, 54.938044),
    "Fe": (26, 55.845),
    "Co": (27, 58.933194),
    "Ni": (28, 58.6934),
    "Cu": (29, 63.546),
    "Zn": (30, 65.38),
    "Ga": (31, 69.723),
    "Ge": (32, 72.630),
    "As": (33, 74.921595),
    "Se": (34, 78.971),
    "Br": (35, 79.904),
    "Kr": (36, 83.798),
    "Rb": (37, 85.4678),
    "Sr": (38, 87.62),
    "Y": (39, 88.90584),
    "Zr": (40, 91.224),
    "Nb": (41, 92.90637),
    "Mo": (42, 95.95),
    "Tc": (43, 98.0),
    "Ru": (44, 101.07),
    "Rh": (45, 102.90550),
    "Pd": (46, 106.42),
    "Ag": (47, 107.8682),
    "Cd": (48, 112.414),
    "In": (49, 114.818),
    "Sn": (50, 118.710),
    "Sb": (51, 121.760),
    "Te": (52, 127.60),
    "I": (53, 126.90447),
    "Xe": (54, 131.293),
    "Cs": (55, 132.90545196),
    "Ba": (56, 137.327),
    "La": (57, 138.90547),
    "Ce": (58, 140.116),
    "Pr": (59, 140.90766),
    "Nd": (60, 144.242),
    "Pm": (61, 145.0),
    "Sm": (62, 150.36),
    "Eu": (63, 151.964),
    "Gd": (64, 157.25),
    "Tb": (65, 158.92535),
    "Dy": (66, 162.500),
    "Ho": (67, 164.93033),
    "Er": (68, 167.259),
    "Tm": (69, 168.93422),
    "Yb": (70, 173.045),
    "Lu": (71, 174.9668),
    "Hf": (72, 178.49),
    "Ta": (73, 180.94788),
    "W": (74, 183.84),
    "Re": (75, 186.207),
    "Os": (76, 190.23),
    "Ir": (77, 192.217),
    "Pt": (78, 195.084),
    "Au": (79, 196.966569),
    "Hg": (80, 200.592),
    "Tl": (81, 204.38),
    "Pb": (82, 207.2),
    "Bi": (83, 208.98040),
    "Po": (84, 209.0),
    "At": (85, 210.0),
    "Rn": (86, 222.0),
    "Fr": (87, 223.0),
    "Ra": (88, 226.0),
    "Ac": (89, 227.0),
    "Th": (90, 232.0377),
    "Pa": (91, 231.03588),
    "U": (92, 238.02891),
    "Np": (93, 237.0),
    "Pu": (94, 244.0),
    "Am": (95, 243.0),
    "Cm": (96, 247.0),
    "Bk": (97, 247.0),
    "Cf": (98, 251.0),
    "Es": (99, 252.0),
    "Fm": (100, 257.0),
    "Md": (101, 258.0),
    "No": (102, 259.0),
    "Lr": (103, 262.0),
    "Rf": (104, 267.0),
    "Db": (105, 268.0),
    "Sg": (106, 271.0),
    "Bh": (107, 274.0),
    "Hs": (108, 269.0),
    "Mt": (109, 278.0),
    "Ds": (110, 281.0),
    "Rg": (111, 282.0),
    "Cn": (112, 285.0),
    "Nh": (113, 286.0),
    "Fl": (114, 289.0),
    "Mc": (115, 290.0),
    "Lv": (116, 293.0),
    "Ts": (117, 294.0),
    "Og": (118, 294.0),
}

_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*)")


def _parse_group(text: str) -> dict[str, int] | None:
    """Parse a formula fragment with nested parentheses into element counts."""
    stack: list[dict[str, int]] = [{}]
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "(":
            stack.append({})
            i += 1
        elif char == ")":
            i += 1
            digits = re.match(r"\d+", text[i:])
            multiplier = int(digits.group()) if digits else 1
            i += len(digits.group()) if digits else 0
            group = stack.pop()
            if not stack:  # unbalanced ')'
                return None
            for element, count in group.items():
                stack[-1][element] = stack[-1].get(element, 0) + count * multiplier
        else:
            match = _ELEMENT_RE.match(text, i)
            if not match or not match.group(1):
                return None
            element = match.group(1)
            if element not in ELEMENTS:
                return None
            count = int(match.group(2)) if match.group(2) else 1
            stack[-1][element] = stack[-1].get(element, 0) + count
            i = match.end()
    if len(stack) != 1:  # unbalanced '('
        return None
    return stack[0]


def parse_formula(formula: str) -> dict[str, int] | None:
    """Formula → {element: count}, honouring groups and hydrates ('CuSO4·5H2O')."""
    text = formula.strip().replace(" ", "")
    text = text.replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
    if not text:
        return None
    total: dict[str, int] = {}
    for part in re.split(r"[·.*]", text):  # hydrate / addition compounds
        if not part:
            continue
        lead = re.match(r"^(\d+)(.+)$", part)
        if lead:
            multiplier, body = int(lead.group(1)), lead.group(2)
        else:
            multiplier, body = 1, part
        counts = _parse_group(body)
        if counts is None:
            return None
        for element, count in counts.items():
            total[element] = total.get(element, 0) + count * multiplier
    return total or None


def molar_mass(formula: str) -> dict[str, Any]:
    """Molar mass (g/mol) with a per-element breakdown; ``ok`` False on parse error."""
    counts = parse_formula(formula)
    if not counts:
        return {"ok": False, "error": f"could not parse formula '{formula}'"}
    total = 0.0
    raw_entries: list[tuple[str, int, float]] = []
    for element, count in counts.items():
        mass = ELEMENTS[element][1] * count
        total += mass
        raw_entries.append((element, count, round(mass, 4)))
    breakdown: list[dict[str, Any]] = [
        {
            "element": element,
            "count": count,
            "mass": rounded_mass,
            "percent": round(100 * rounded_mass / total, 2) if total else 0.0,
        }
        for element, count, rounded_mass in raw_entries
    ]
    return {
        "ok": True,
        "formula": formula,
        "molar_mass": round(total, 4),
        "unit": "g/mol",
        "breakdown": breakdown,
    }


def _strip_coefficient(species: str) -> str:
    return re.sub(r"^\s*\d+\s*", "", species.strip())


def _lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b) if a and b else max(a, b)


def _null_vector(rows: list[list[Fraction]], ncols: int) -> list[Fraction] | None:
    """One basis vector of the nullspace via exact RREF; None unless 1-dimensional."""
    mat = [row[:] for row in rows]
    pivot_cols: list[int] = []
    r = 0
    for c in range(ncols):
        pivot = next((i for i in range(r, len(mat)) if mat[i][c] != 0), None)
        if pivot is None:
            continue
        mat[r], mat[pivot] = mat[pivot], mat[r]
        inv = mat[r][c]
        mat[r] = [x / inv for x in mat[r]]
        for i in range(len(mat)):
            if i != r and mat[i][c] != 0:
                factor = mat[i][c]
                mat[i] = [a - factor * b for a, b in zip(mat[i], mat[r], strict=False)]
        pivot_cols.append(c)
        r += 1
        if r == len(mat):
            break
    free_cols = [c for c in range(ncols) if c not in pivot_cols]
    if len(free_cols) != 1:  # not uniquely balanceable
        return None
    free = free_cols[0]
    vector = [Fraction(0)] * ncols
    vector[free] = Fraction(1)
    for row_index, pivot_col in enumerate(pivot_cols):
        vector[pivot_col] = -mat[row_index][free]
    return vector


def balance_equation(equation: str) -> dict:
    """Balance a chemical equation ('H2 + O2 -> H2O') by conservation of atoms."""
    normalised = (
        equation.replace("→", "->").replace("⟶", "->").replace("⇌", "->").replace("⇋", "->")
    )
    for separator in ("->", "="):
        if separator in normalised:
            left, right = normalised.split(separator, 1)
            break
    else:
        return {"ok": False, "error": "no reaction arrow ('->' or '=') found"}

    reactants = [_strip_coefficient(s) for s in left.split("+") if s.strip()]
    products = [_strip_coefficient(s) for s in right.split("+") if s.strip()]
    species = reactants + products
    if len(species) < 2:
        return {"ok": False, "error": "need at least two species to balance"}

    parsed = [parse_formula(s) for s in species]
    if any(counts is None for counts in parsed):
        bad = species[parsed.index(None)]
        return {"ok": False, "error": f"could not parse species '{bad}'"}

    valid_parsed: list[dict[str, int]] = [c for c in parsed if c is not None]
    elements = sorted({el for counts in valid_parsed for el in counts})
    rows: list[list[Fraction]] = []
    for element in elements:
        row: list[Fraction] = []
        for j, counts in enumerate(valid_parsed):
            sign = 1 if j < len(reactants) else -1
            row.append(Fraction(sign * counts.get(element, 0)))
        rows.append(row)

    vector = _null_vector(rows, len(species))
    if vector is None:
        return {"ok": False, "error": "equation is not uniquely balanceable"}

    denom_lcm = 1
    for frac in vector:
        denom_lcm = _lcm(denom_lcm, frac.denominator)
    integers = [int(frac * denom_lcm) for frac in vector]
    divisor = 0
    for coeff in integers:
        divisor = math.gcd(divisor, abs(coeff))
    if divisor:
        integers = [coeff // divisor for coeff in integers]
    if all(coeff <= 0 for coeff in integers):
        integers = [-coeff for coeff in integers]
    if any(coeff <= 0 for coeff in integers):
        return {"ok": False, "error": "no positive integer solution (check the equation)"}

    coefficients = dict(zip(species, integers, strict=False))
    balanced = "{} -> {}".format(
        " + ".join(_format_term(coefficients[s], s) for s in reactants),
        " + ".join(_format_term(coefficients[s], s) for s in products),
    )
    return {
        "ok": True,
        "balanced": balanced,
        "coefficients": integers,
        "reactants": reactants,
        "products": products,
    }


def _format_term(coefficient: int, species: str) -> str:
    return species if coefficient == 1 else f"{coefficient} {species}"


# Common compound names → molecular formula (for natural-language chemistry queries).
COMMON_COMPOUNDS: dict[str, str] = {
    "water": "H2O",
    "methane": "CH4",
    "ethane": "C2H6",
    "propane": "C3H8",
    "butane": "C4H10",
    "ethanol": "C2H5OH",
    "methanol": "CH3OH",
    "glucose": "C6H12O6",
    "sucrose": "C12H22O11",
    "benzene": "C6H6",
    "ammonia": "NH3",
    "carbon dioxide": "CO2",
    "carbon monoxide": "CO",
    "sodium chloride": "NaCl",
    "table salt": "NaCl",
    "sulfuric acid": "H2SO4",
    "sulphuric acid": "H2SO4",
    "hydrochloric acid": "HCl",
    "nitric acid": "HNO3",
    "phosphoric acid": "H3PO4",
    "acetic acid": "CH3COOH",
    "sodium hydroxide": "NaOH",
    "potassium hydroxide": "KOH",
    "calcium carbonate": "CaCO3",
    "calcium hydroxide": "Ca(OH)2",
    "sodium bicarbonate": "NaHCO3",
    "baking soda": "NaHCO3",
    "hydrogen peroxide": "H2O2",
    "oxygen gas": "O2",
    "hydrogen gas": "H2",
    "nitrogen gas": "N2",
    "chlorine gas": "Cl2",
    "ozone": "O3",
    "rust": "Fe2O3",
    "iron oxide": "Fe2O3",
}

ELEMENT_NAMES: dict[str, str] = {
    "hydrogen": "H",
    "helium": "He",
    "lithium": "Li",
    "beryllium": "Be",
    "boron": "B",
    "carbon": "C",
    "nitrogen": "N",
    "oxygen": "O",
    "fluorine": "F",
    "neon": "Ne",
    "sodium": "Na",
    "magnesium": "Mg",
    "aluminum": "Al",
    "aluminium": "Al",
    "silicon": "Si",
    "phosphorus": "P",
    "sulfur": "S",
    "sulphur": "S",
    "chlorine": "Cl",
    "argon": "Ar",
    "potassium": "K",
    "calcium": "Ca",
    "titanium": "Ti",
    "chromium": "Cr",
    "manganese": "Mn",
    "iron": "Fe",
    "cobalt": "Co",
    "nickel": "Ni",
    "copper": "Cu",
    "zinc": "Zn",
    "bromine": "Br",
    "silver": "Ag",
    "tin": "Sn",
    "iodine": "I",
    "barium": "Ba",
    "platinum": "Pt",
    "gold": "Au",
    "mercury": "Hg",
    "lead": "Pb",
    "uranium": "U",
}

_ALKALI_METALS = {"Li", "Na", "K", "Rb", "Cs", "Fr"}
_ALKALINE_EARTH = {"Be", "Mg", "Ca", "Sr", "Ba", "Ra"}
_HALOGENS = {"Cl", "Br", "I"}


def resolve_formula(text: str) -> str | None:
    """Resolve a chemical formula or common compound name to a valid formula."""
    cleaned = text.strip().rstrip(".,?!;:")
    if not cleaned:
        return None
    low = cleaned.lower()
    if low in COMMON_COMPOUNDS:
        return COMMON_COMPOUNDS[low]
    if re.search(r"[A-Z]", cleaned) and parse_formula(cleaned):
        return cleaned
    return None


def resolve_element(text: str) -> str | None:
    """Resolve an element symbol or English name to its IUPAC symbol."""
    cleaned = text.strip().rstrip(".,?!;:")
    if cleaned in ELEMENTS:
        return cleaned
    return ELEMENT_NAMES.get(cleaned.lower())


def percent_composition(formula: str, element: str) -> dict[str, Any]:
    """Compute mass percentage of ``element`` in ``formula``."""
    resolved_formula = resolve_formula(formula)
    resolved_el = resolve_element(element)
    if resolved_formula is None:
        return {"ok": False, "error": f"could not parse formula '{formula}'"}
    if resolved_el is None:
        return {"ok": False, "error": f"unknown element '{element}'"}
    mm = molar_mass(resolved_formula)
    if not mm["ok"]:
        return mm
    counts = parse_formula(resolved_formula)
    assert counts is not None
    if resolved_el not in counts:
        return {
            "ok": False,
            "error": f"element '{resolved_el}' is not present in '{resolved_formula}'",
        }
    count = counts[resolved_el]
    atomic_mass = ELEMENTS[resolved_el][1]
    element_mass = count * atomic_mass
    total_mass = sum(ELEMENTS[el][1] * n for el, n in counts.items())
    pct = 100.0 * element_mass / total_mass
    return {
        "ok": True,
        "formula": resolved_formula,
        "element": resolved_el,
        "count": count,
        "element_mass": round(element_mass, 4),
        "molar_mass": round(total_mass, 4),
        "percent": round(pct, 2),
    }


def _known_oxidation_rules(counts: dict[str, int], target: str, charge: int) -> dict[str, int]:
    """Assign standard IUPAC oxidation numbers to every non-target element possible."""
    assigned: dict[str, int] = {}
    elements = set(counts)
    for el in elements:
        if el == target:
            continue
        if el == "F":
            assigned[el] = -1
        elif el in _ALKALI_METALS:
            assigned[el] = +1
        elif el in _ALKALINE_EARTH:
            assigned[el] = +2
        elif el == "Al":
            assigned[el] = +3
        elif el == "H":
            # Binary metal hydrides (e.g. NaH, CaH2) assign H = -1.
            others = elements - {"H"}
            if others and all(o in (_ALKALI_METALS | _ALKALINE_EARTH | {"Al"}) for o in others):
                assigned[el] = -1
            else:
                assigned[el] = +1
        elif el == "O":
            # Peroxide exceptions (H2O2, Na2O2, K2O2, BaO2) and OF2.
            if elements == {"O", "F"} and counts.get("F") == 2 and counts.get("O") == 1:
                assigned[el] = +2
            elif (
                charge == 0
                and len(elements) == 2
                and counts.get("O") == 2
                and any(
                    (o in _ALKALI_METALS | {"H"} and counts[o] == 2)
                    or (o in _ALKALINE_EARTH and counts[o] == 1)
                    for o in elements - {"O"}
                )
            ):
                assigned[el] = -1
            else:
                assigned[el] = -2
        elif el in _HALOGENS and "O" not in elements and "F" not in elements:
            assigned[el] = -1
    return assigned


def oxidation_state(formula: str, element: str, charge: int = 0) -> dict[str, Any]:
    """Determine the oxidation state of ``element`` in ``formula`` via IUPAC rules."""
    resolved_formula = resolve_formula(formula)
    resolved_el = resolve_element(element)
    if resolved_formula is None:
        return {"ok": False, "error": f"could not parse formula '{formula}'"}
    if resolved_el is None:
        return {"ok": False, "error": f"unknown element '{element}'"}
    counts = parse_formula(resolved_formula)
    if not counts or resolved_el not in counts:
        return {
            "ok": False,
            "error": f"element '{resolved_el}' is not present in '{resolved_formula}'",
        }
    if len(counts) == 1:
        val = Fraction(charge, counts[resolved_el])
        formatted = _format_ox(val)
        return {
            "ok": True,
            "formula": resolved_formula,
            "element": resolved_el,
            "oxidation_state": float(val),
            "formatted": formatted,
            "known": {},
            "charge": charge,
        }
    known = _known_oxidation_rules(counts, resolved_el, charge)
    unknowns = [el for el in counts if el != resolved_el and el not in known]
    if unknowns:
        return {
            "ok": False,
            "error": f"ambiguous oxidation state (multiple unknowns: {', '.join(unknowns)})",
        }
    known_sum = sum(counts[el] * ox for el, ox in known.items())
    val = Fraction(charge - known_sum, counts[resolved_el])
    return {
        "ok": True,
        "formula": resolved_formula,
        "element": resolved_el,
        "oxidation_state": float(val),
        "formatted": _format_ox(val),
        "known": known,
        "charge": charge,
    }


def _format_ox(val: Fraction) -> str:
    if val == 0:
        return "0"
    sign = "+" if val > 0 else ""
    if val.denominator == 1:
        return f"{sign}{val.numerator}"
    return f"{sign}{val.numerator}/{val.denominator}"


def register_tools(registry) -> None:
    from olivia.tools.registry import Tool

    registry.register(
        Tool(
            name="molar_mass",
            description=(
                "Compute the molar mass (g/mol) of a chemical formula, with a "
                "per-element breakdown. Understands groups and hydrates."
            ),
            parameters={
                "type": "object",
                "properties": {"formula": {"type": "string"}},
                "required": ["formula"],
            },
            fn=molar_mass,
            risk=1,
        )
    )
    registry.register(
        Tool(
            name="balance_equation",
            description=(
                "Balance a chemical equation (e.g. 'H2 + O2 -> H2O') by exact "
                "conservation of atoms."
            ),
            parameters={
                "type": "object",
                "properties": {"equation": {"type": "string"}},
                "required": ["equation"],
            },
            fn=balance_equation,
            risk=1,
        )
    )
