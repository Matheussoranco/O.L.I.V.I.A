"""Physics — CODATA physical constants and natural-language lookup, offline.

A curated constant table with aliases so questions like "what is the speed of
light" or "value of Planck's constant" resolve deterministically, no LLM
required.  Values follow the 2018 CODATA set (SI, exact where defined).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Constant:
    """A named physical constant with its SI value and search aliases."""

    symbol: str
    name: str
    value: float
    unit: str
    aliases: tuple[str, ...] = ()


CONSTANTS: tuple[Constant, ...] = (
    Constant("c", "speed of light in vacuum", 299792458.0, "m/s",
             ("speed of light", "light speed", "lightspeed")),
    Constant("G", "Newtonian constant of gravitation", 6.67430e-11, "m^3 kg^-1 s^-2",
             ("gravitational constant", "gravitation constant", "big g")),
    Constant("h", "Planck constant", 6.62607015e-34, "J s",
             ("planck constant", "planck's constant")),
    Constant("hbar", "reduced Planck constant", 1.054571817e-34, "J s",
             ("reduced planck constant", "h-bar", "dirac constant")),
    Constant("e", "elementary charge", 1.602176634e-19, "C",
             ("elementary charge", "electron charge", "charge of electron")),
    Constant("k_B", "Boltzmann constant", 1.380649e-23, "J/K",
             ("boltzmann constant", "boltzmann")),
    Constant("N_A", "Avogadro constant", 6.02214076e23, "mol^-1",
             ("avogadro constant", "avogadro number", "avogadro's number", "avogadro")),
    Constant("R", "molar gas constant", 8.314462618, "J mol^-1 K^-1",
             ("gas constant", "universal gas constant", "ideal gas constant")),
    Constant("F", "Faraday constant", 96485.33212, "C/mol",
             ("faraday constant",)),
    Constant("sigma", "Stefan-Boltzmann constant", 5.670374419e-8, "W m^-2 K^-4",
             ("stefan-boltzmann constant", "stefan boltzmann constant")),
    Constant("epsilon_0", "vacuum electric permittivity", 8.8541878128e-12, "F/m",
             ("vacuum permittivity", "electric constant", "permittivity of free space")),
    Constant("mu_0", "vacuum magnetic permeability", 1.25663706212e-6, "N/A^2",
             ("vacuum permeability", "magnetic constant", "permeability of free space")),
    Constant("m_e", "electron mass", 9.1093837015e-31, "kg",
             ("electron mass", "mass of electron", "mass of an electron")),
    Constant("m_p", "proton mass", 1.67262192369e-27, "kg",
             ("proton mass", "mass of proton", "mass of a proton")),
    Constant("m_n", "neutron mass", 1.67492749804e-27, "kg",
             ("neutron mass", "mass of neutron")),
    Constant("g", "standard acceleration of gravity", 9.80665, "m/s^2",
             ("standard gravity", "acceleration due to gravity", "gravity acceleration")),
    Constant("alpha", "fine-structure constant", 7.2973525693e-3, "",
             ("fine structure constant", "fine-structure constant")),
    Constant("a_0", "Bohr radius", 5.29177210903e-11, "m",
             ("bohr radius",)),
    Constant("Ry", "Rydberg constant", 10973731.568160, "m^-1",
             ("rydberg constant",)),
    Constant("atm", "standard atmosphere", 101325.0, "Pa",
             ("standard atmosphere", "atmospheric pressure")),
)

# Case-sensitive: physics symbols distinguish G (gravitation) from g (gravity).
_BY_SYMBOL = {const.symbol: const for const in CONSTANTS}


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def physical_constant(query: str) -> dict:
    """Look up a constant by exact symbol, name, or alias phrase; ``ok`` False if unknown."""
    raw = query.strip()
    if raw in _BY_SYMBOL:  # exact, case-sensitive symbol match
        return _as_dict(_BY_SYMBOL[raw])

    text = _normalise(query)
    # Longest alias/name that appears as a phrase wins (most specific).
    best: Constant | None = None
    best_len = 0
    for const in CONSTANTS:
        for phrase in (const.name, *const.aliases):
            phrase_n = _normalise(phrase)
            if phrase_n and phrase_n in text and len(phrase_n) > best_len:
                best, best_len = const, len(phrase_n)
    if best is not None:
        return _as_dict(best)
    return {"ok": False, "error": f"no known physical constant matches '{query}'"}


def _as_dict(const: Constant) -> dict:
    return {
        "ok": True,
        "symbol": const.symbol,
        "name": const.name,
        "value": const.value,
        "unit": const.unit,
    }


def register_tools(registry) -> None:
    from olivia.tools.registry import Tool

    registry.register(
        Tool(
            name="physical_constant",
            description=(
                "Look up a physical constant by name or symbol (e.g. 'speed of "
                "light', 'Planck constant', 'N_A'). Returns value and SI unit."
            ),
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            fn=physical_constant,
            risk=1,
        )
    )
