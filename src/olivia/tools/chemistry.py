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


def molar_mass(formula: str) -> dict:
    """Molar mass (g/mol) with a per-element breakdown; ``ok`` False on parse error."""
    counts = parse_formula(formula)
    if not counts:
        return {"ok": False, "error": f"could not parse formula '{formula}'"}
    total = 0.0
    breakdown = []
    for element, count in counts.items():
        mass = ELEMENTS[element][1] * count
        total += mass
        breakdown.append({"element": element, "count": count, "mass": round(mass, 4)})
    for item in breakdown:
        item["percent"] = round(100 * item["mass"] / total, 2) if total else 0.0
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
    normalised = equation.replace("→", "->").replace("⟶", "->").replace("⇌", "->")
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

    elements = sorted({el for counts in parsed for el in counts})
    rows: list[list[Fraction]] = []
    for element in elements:
        row: list[Fraction] = []
        for j, counts in enumerate(parsed):
            sign = 1 if j < len(reactants) else -1
            row.append(Fraction(sign * counts.get(element, 0)))
        rows.append(row)

    vector = _null_vector(rows, len(species))
    if vector is None:
        return {"ok": False, "error": "equation is not uniquely balanceable"}

    denom_lcm = 1
    for value in vector:
        denom_lcm = _lcm(denom_lcm, value.denominator)
    integers = [int(value * denom_lcm) for value in vector]
    divisor = 0
    for value in integers:
        divisor = math.gcd(divisor, abs(value))
    if divisor:
        integers = [value // divisor for value in integers]
    if all(value <= 0 for value in integers):
        integers = [-value for value in integers]
    if any(value <= 0 for value in integers):
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
