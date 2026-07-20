"""Units and dimensional analysis — deterministic, offline, SI-based.

Every quantity is reduced to a factor over the seven SI base dimensions
(m, kg, s, A, K, mol, cd), so conversions are exact ratios and dimensional
compatibility is a tuple comparison.  Temperature is affine (°C/°F have an
offset) and is handled separately from the multiplicative unit algebra.

This is a hard-science foundation for the physics/chemistry study paths: no
network, no LLM, no third-party dependency.
"""

from __future__ import annotations

import re

Dimension = tuple[int, ...]

_DIM_LABELS = ("m", "kg", "s", "A", "K", "mol", "cd")
_DIMLESS: Dimension = (0, 0, 0, 0, 0, 0, 0)

# Friendly names for common composite dimensions.
_NAMED_DIMENSIONS: dict[Dimension, str] = {
    (0, 0, 0, 0, 0, 0, 0): "dimensionless",
    (1, 0, 0, 0, 0, 0, 0): "length",
    (0, 1, 0, 0, 0, 0, 0): "mass",
    (0, 0, 1, 0, 0, 0, 0): "time",
    (0, 0, 0, 1, 0, 0, 0): "current",
    (0, 0, 0, 0, 1, 0, 0): "temperature",
    (0, 0, 0, 0, 0, 1, 0): "amount",
    (0, 0, 0, 0, 0, 0, 1): "luminous intensity",
    (2, 0, 0, 0, 0, 0, 0): "area",
    (3, 0, 0, 0, 0, 0, 0): "volume",
    (1, 0, -1, 0, 0, 0, 0): "velocity",
    (1, 0, -2, 0, 0, 0, 0): "acceleration",
    (1, 1, -2, 0, 0, 0, 0): "force",
    (2, 1, -2, 0, 0, 0, 0): "energy",
    (2, 1, -3, 0, 0, 0, 0): "power",
    (-1, 1, -2, 0, 0, 0, 0): "pressure",
    (0, 0, 1, 1, 0, 0, 0): "charge",
    (2, 1, -3, -1, 0, 0, 0): "voltage",
    (0, 0, -1, 0, 0, 0, 0): "frequency",
}

# Base and named units → (factor to SI, dimension).  "Unprefixed" forms only;
# metric prefixes are applied by _resolve() to any unit in _PREFIXABLE.
_UNITS: dict[str, tuple[float, Dimension]] = {
    # SI base (mass is stored as gram so prefixes give kg = k+g).
    "m": (1.0, (1, 0, 0, 0, 0, 0, 0)),
    "g": (1e-3, (0, 1, 0, 0, 0, 0, 0)),
    "s": (1.0, (0, 0, 1, 0, 0, 0, 0)),
    "A": (1.0, (0, 0, 0, 1, 0, 0, 0)),
    "K": (1.0, (0, 0, 0, 0, 1, 0, 0)),
    "mol": (1.0, (0, 0, 0, 0, 0, 1, 0)),
    "cd": (1.0, (0, 0, 0, 0, 0, 0, 1)),
    # SI derived.
    "N": (1.0, (1, 1, -2, 0, 0, 0, 0)),
    "J": (1.0, (2, 1, -2, 0, 0, 0, 0)),
    "W": (1.0, (2, 1, -3, 0, 0, 0, 0)),
    "Pa": (1.0, (-1, 1, -2, 0, 0, 0, 0)),
    "C": (1.0, (0, 0, 1, 1, 0, 0, 0)),
    "V": (1.0, (2, 1, -3, -1, 0, 0, 0)),
    "ohm": (1.0, (2, 1, -3, -2, 0, 0, 0)),
    "Ω": (1.0, (2, 1, -3, -2, 0, 0, 0)),
    "Hz": (1.0, (0, 0, -1, 0, 0, 0, 0)),
    "L": (1e-3, (3, 0, 0, 0, 0, 0, 0)),
    # Time.
    "min": (60.0, (0, 0, 1, 0, 0, 0, 0)),
    "h": (3600.0, (0, 0, 1, 0, 0, 0, 0)),
    "hr": (3600.0, (0, 0, 1, 0, 0, 0, 0)),
    "day": (86400.0, (0, 0, 1, 0, 0, 0, 0)),
    "yr": (31557600.0, (0, 0, 1, 0, 0, 0, 0)),
    # Length (imperial / astronomical).
    "in": (0.0254, (1, 0, 0, 0, 0, 0, 0)),
    "inch": (0.0254, (1, 0, 0, 0, 0, 0, 0)),
    "ft": (0.3048, (1, 0, 0, 0, 0, 0, 0)),
    "foot": (0.3048, (1, 0, 0, 0, 0, 0, 0)),
    "yd": (0.9144, (1, 0, 0, 0, 0, 0, 0)),
    "mi": (1609.344, (1, 0, 0, 0, 0, 0, 0)),
    "mile": (1609.344, (1, 0, 0, 0, 0, 0, 0)),
    "angstrom": (1e-10, (1, 0, 0, 0, 0, 0, 0)),
    "au": (1.495978707e11, (1, 0, 0, 0, 0, 0, 0)),
    "ly": (9.4607304725808e15, (1, 0, 0, 0, 0, 0, 0)),
    # Mass.
    "t": (1e3, (0, 1, 0, 0, 0, 0, 0)),
    "lb": (0.45359237, (0, 1, 0, 0, 0, 0, 0)),
    "oz": (0.028349523125, (0, 1, 0, 0, 0, 0, 0)),
    "amu": (1.66053906660e-27, (0, 1, 0, 0, 0, 0, 0)),
    "u": (1.66053906660e-27, (0, 1, 0, 0, 0, 0, 0)),
    # Energy / pressure / velocity.
    "eV": (1.602176634e-19, (2, 1, -2, 0, 0, 0, 0)),
    "cal": (4.184, (2, 1, -2, 0, 0, 0, 0)),
    "Wh": (3600.0, (2, 1, -2, 0, 0, 0, 0)),
    "bar": (1e5, (-1, 1, -2, 0, 0, 0, 0)),
    "atm": (101325.0, (-1, 1, -2, 0, 0, 0, 0)),
    "mmHg": (133.322387415, (-1, 1, -2, 0, 0, 0, 0)),
    "torr": (133.322387415, (-1, 1, -2, 0, 0, 0, 0)),
    "psi": (6894.757293168, (-1, 1, -2, 0, 0, 0, 0)),
    "mph": (0.44704, (1, 0, -1, 0, 0, 0, 0)),
    "knot": (0.514444, (1, 0, -1, 0, 0, 0, 0)),
}

_PREFIXES: dict[str, float] = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6,
    "k": 1e3, "h": 1e2, "da": 1e1, "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6,
    "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
    "z": 1e-21, "y": 1e-24,
}

_PREFIXABLE = {
    "m", "g", "s", "A", "K", "mol", "cd", "N", "J", "W", "Pa", "C", "V",
    "ohm", "Ω", "Hz", "L", "eV", "cal", "Wh",
}

_TOKEN_RE = re.compile(r"([*/])?([A-Za-zµμΩ]+)(?:\^(-?\d+))?")
# Temperature words that are unambiguous (bare "C"/"F" stay coulomb/farad).
_TEMP_UNITS = {"k", "kelvin", "°c", "celsius", "degc", "°f", "fahrenheit", "degf"}


def _resolve(token: str) -> tuple[float, Dimension] | None:
    """A single unit token → (factor, dim), applying a metric prefix if needed."""
    if token in _UNITS:
        return _UNITS[token]
    for plen in (2, 1):  # 'da' (deca) before single-character prefixes
        prefix, rest = token[:plen], token[plen:]
        if prefix in _PREFIXES and rest in _UNITS and rest in _PREFIXABLE:
            factor, dim = _UNITS[rest]
            return _PREFIXES[prefix] * factor, dim
    return None


def parse_unit(unit_str: str) -> tuple[float, Dimension] | None:
    """Parse a compound unit ('kg*m/s^2', 'km/h', 'mmHg') → (factor, dim)."""
    text = unit_str.strip().replace("**", "^").replace("·", "*").replace("×", "*")
    text = text.replace(" ", "")
    if not text:
        return None
    factor = 1.0
    dim = [0, 0, 0, 0, 0, 0, 0]
    cursor = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() != cursor:  # an unparseable gap between tokens
            return None
        cursor = match.end()
        op, name, exp = match.groups()
        exponent = int(exp) if exp else 1
        if op == "/":
            exponent = -exponent
        resolved = _resolve(name)
        if resolved is None:
            return None
        unit_factor, unit_dim = resolved
        factor *= unit_factor**exponent
        for i in range(7):
            dim[i] += unit_dim[i] * exponent
    if cursor != len(text):
        return None
    return factor, tuple(dim)


def _is_temperature(unit: str) -> bool:
    return unit.strip().lower() in _TEMP_UNITS


def _to_kelvin(value: float, unit: str) -> float | None:
    key = unit.strip().lower()
    if key in ("k", "kelvin"):
        return value
    if key in ("°c", "celsius", "degc"):
        return value + 273.15
    if key in ("°f", "fahrenheit", "degf"):
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    return None


def _from_kelvin(value: float, unit: str) -> float | None:
    key = unit.strip().lower()
    if key in ("k", "kelvin"):
        return value
    if key in ("°c", "celsius", "degc"):
        return value - 273.15
    if key in ("°f", "fahrenheit", "degf"):
        return (value - 273.15) * 9.0 / 5.0 + 32.0
    return None


def convert(value: float, from_unit: str, to_unit: str) -> float | None:
    """Convert ``value`` from one unit to another; ``None`` if incompatible."""
    if _is_temperature(from_unit) and _is_temperature(to_unit):
        kelvin = _to_kelvin(value, from_unit)
        return _from_kelvin(kelvin, to_unit) if kelvin is not None else None
    source = parse_unit(from_unit)
    target = parse_unit(to_unit)
    if source is None or target is None or source[1] != target[1]:
        return None
    return value * source[0] / target[0]


def to_si(value: float, unit: str) -> tuple[float, Dimension] | None:
    """Reduce a quantity to its SI value and dimension."""
    parsed = parse_unit(unit)
    if parsed is None:
        return None
    return value * parsed[0], parsed[1]


def format_dimension(dim: Dimension) -> str:
    """Render a dimension tuple as 'm·kg·s^-2' (base-unit product form)."""
    parts = [
        label if exp == 1 else f"{label}^{exp}"
        for label, exp in zip(_DIM_LABELS, dim, strict=False)
        if exp
    ]
    return "·".join(parts) or "1"


def dimension_name(dim: Dimension) -> str:
    """A friendly physical-quantity name, or the base-unit product otherwise."""
    return _NAMED_DIMENSIONS.get(tuple(dim), format_dimension(dim))


# ---------------------------------------------------------------------------
# Tool functions (dict-returning, registry-friendly)
# ---------------------------------------------------------------------------


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert a quantity, returning a structured result (never raising)."""
    result = convert(value, from_unit, to_unit)
    if result is None:
        return {
            "ok": False,
            "error": f"cannot convert '{from_unit}' to '{to_unit}' "
            "(unknown or dimensionally incompatible units)",
        }
    return {
        "ok": True,
        "value": result,
        "from": {"value": value, "unit": from_unit},
        "to": {"value": result, "unit": to_unit},
    }


def dimensional_analysis(unit: str) -> dict:
    """Break a unit down to its SI factor, base dimensions, and quantity name."""
    parsed = parse_unit(unit)
    if parsed is None:
        return {"ok": False, "error": f"could not parse unit '{unit}'"}
    factor, dim = parsed
    return {
        "ok": True,
        "unit": unit,
        "si_factor": factor,
        "dimension": format_dimension(dim),
        "quantity": dimension_name(dim),
    }


def register_tools(registry) -> None:
    from olivia.tools.registry import Tool

    registry.register(
        Tool(
            name="convert_units",
            description=(
                "Convert a physical quantity between units (SI, imperial, "
                "temperature). Returns the converted value or an error."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "from_unit": {"type": "string"},
                    "to_unit": {"type": "string"},
                },
                "required": ["value", "from_unit", "to_unit"],
            },
            fn=convert_units,
            risk=1,
        )
    )
    registry.register(
        Tool(
            name="dimensional_analysis",
            description=(
                "Reduce a unit to its SI factor and base dimensions "
                "(e.g. 'N' → kg·m·s^-2, force)."
            ),
            parameters={
                "type": "object",
                "properties": {"unit": {"type": "string"}},
                "required": ["unit"],
            },
            fn=dimensional_analysis,
            risk=1,
        )
    )
