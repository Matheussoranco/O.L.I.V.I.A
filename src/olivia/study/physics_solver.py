"""Deterministic introductory physics solver using CODATA constants and SI unit conversion.

Covers constant-acceleration kinematics, free fall under standard gravity, kinetic energy,
Newton's second law, photon energy–wavelength–frequency relations, and simple pendulums.
Abstains cleanly (returns ``None``) whenever required quantities are missing or ambiguous.
"""

from __future__ import annotations

import math
import re

from olivia.core.records import SolutionStep, WorkedSolution
from olivia.tools.physics import physical_constant
from olivia.tools.units import convert, parse_unit

_VAL_UNIT_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
    r"(m/s\^2|m/s²|m/s|km/h|mph|cm/s|ft/s|"
    r"kilograms?|grams?|milligrams?|pounds?|lbs|kg|mg|g|lb|"
    r"seconds?|minutes?|hours?|secs?|mins?|hrs?|ms|s|min|h|"
    r"kilometres?|kilometers?|centimetres?|centimeters?|millimetres?|millimeters?|"
    r"nanometres?|nanometers?|micrometres?|micrometers?|metres?|meters?|miles?|feet|foot|inches?|km|cm|mm|nm|um|m|ft|in|"
    r"newtons?|kilonewtons?|kN|N|"
    r"kilojoules?|joules?|electronvolts?|keV|MeV|eV|kJ|J|cal|kcal|"
    r"hertz|kHz|MHz|GHz|Hz)\b",
    re.IGNORECASE,
)

_TARGET_UNIT_RE = re.compile(
    r"\bin\s+(nanometres?|nanometers?|micrometres?|micrometers?|angstroms?|"
    r"centimetres?|centimeters?|millimetres?|millimeters?|kilometres?|kilometers?|"
    r"metres?|meters?|feet|miles?|seconds?|minutes?|hours?|milliseconds?|"
    r"joules?|kilojoules?|electronvolts?|newtons?|kilonewtons?|"
    r"m/s|km/h|mph|nm|um|cm|mm|km|m|s|ms|min|h|J|kJ|eV|N|kN)\b",
    re.IGNORECASE,
)

_DIM_LENGTH = (1, 0, 0, 0, 0, 0, 0)
_DIM_MASS = (0, 1, 0, 0, 0, 0, 0)
_DIM_TIME = (0, 0, 1, 0, 0, 0, 0)
_DIM_VELOCITY = (1, 0, -1, 0, 0, 0, 0)
_DIM_ACCEL = (1, 0, -2, 0, 0, 0, 0)
_DIM_FORCE = (1, 1, -2, 0, 0, 0, 0)
_DIM_ENERGY = (2, 1, -2, 0, 0, 0, 0)
_DIM_FREQ = (0, 0, -1, 0, 0, 0, 0)


def _const(symbol: str) -> float:
    res = physical_constant(symbol)
    assert res["ok"]
    return float(res["value"])


def _step(steps: list[SolutionStep], description: str, result: str = "") -> None:
    steps.append(SolutionStep(n=len(steps) + 1, description=description, result=result))


def _canonical_unit_token(raw: str) -> str:
    cleaned = raw.strip().replace("²", "^2")
    # Preserve exact case for eV, kJ, J, N, kN, Hz, etc.
    lower_map = {
        "ev": "eV",
        "kev": "keV",
        "mev": "MeV",
        "kj": "kJ",
        "j": "J",
        "kn": "kN",
        "n": "N",
        "hz": "Hz",
        "khz": "kHz",
        "mhz": "MHz",
        "ghz": "GHz",
    }
    return lower_map.get(cleaned.lower(), cleaned)


def _extract_quantities(text: str) -> dict[tuple[int, ...], list[tuple[float, float, str]]]:
    """Return {si_dimension: [(si_value, raw_value, raw_unit), ...]}."""
    found: dict[tuple[int, ...], list[tuple[float, float, str]]] = {}
    for match in _VAL_UNIT_RE.finditer(text):
        raw_val = float(match.group(1))
        raw_unit = _canonical_unit_token(match.group(2))
        parsed = parse_unit(raw_unit)
        if parsed is None:
            continue
        factor, dim = parsed
        found.setdefault(dim, []).append((raw_val * factor, raw_val, raw_unit))
    return found


def _requested_unit(text: str, expected_dim: tuple[int, ...], default_unit: str) -> str:
    for match in _TARGET_UNIT_RE.finditer(text):
        tok = _canonical_unit_token(match.group(1))
        parsed = parse_unit(tok)
        if parsed is not None and parsed[1] == expected_dim:
            return tok
    return default_unit


def _fmt(value: float) -> str:
    if value.is_integer() and abs(value) < 1e12:
        return str(int(value))
    return f"{value:.4g}"


def _solve_photon(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if "photon" not in low:
        return None
    h = _const("h")
    c = _const("c")
    # Energy -> wavelength
    if "wavelength" in low and _DIM_ENERGY in qty:
        e_j, raw_val, raw_unit = qty[_DIM_ENERGY][0]
        if e_j <= 0:
            return None
        lam_m = h * c / e_j
        target = _requested_unit(problem, _DIM_LENGTH, "m")
        out = convert(lam_m, "m", target)
        if out is None:
            return None
        steps: list[SolutionStep] = []
        _step(steps, f"Convert photon energy {raw_val:g} {raw_unit} to joules", f"{e_j:.6g} J")
        _step(steps, "Apply λ = h·c / E with CODATA h and c", f"{lam_m:.6g} m")
        if target != "m":
            _step(steps, f"Convert wavelength to {target}", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    # Wavelength -> energy
    if "energy" in low and _DIM_LENGTH in qty:
        lam_m, raw_val, raw_unit = qty[_DIM_LENGTH][0]
        if lam_m <= 0:
            return None
        e_j = h * c / lam_m
        target = _requested_unit(problem, _DIM_ENERGY, "J")
        out = convert(e_j, "J", target)
        if out is None:
            return None
        steps = []
        _step(steps, f"Convert wavelength {raw_val:g} {raw_unit} to metres", f"{lam_m:.6g} m")
        _step(steps, "Apply E = h·c / λ with CODATA h and c", f"{e_j:.6g} J")
        if target != "J":
            _step(steps, f"Convert energy to {target}", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    # Frequency -> energy
    if "energy" in low and _DIM_FREQ in qty:
        freq_hz, raw_val, raw_unit = qty[_DIM_FREQ][0]
        if freq_hz <= 0:
            return None
        e_j = h * freq_hz
        target = _requested_unit(problem, _DIM_ENERGY, "J")
        out = convert(e_j, "J", target)
        if out is None:
            return None
        steps = []
        _step(steps, f"Apply E = h·f for f = {raw_val:g} {raw_unit}", f"{e_j:.6g} J")
        if target != "J":
            _step(steps, f"Convert energy to {target}", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    return None


def _solve_pendulum(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if "pendulum" not in low or "period" not in low:
        return None
    if _DIM_LENGTH not in qty:
        return None
    length_m, raw_val, raw_unit = qty[_DIM_LENGTH][0]
    if length_m <= 0:
        return None
    g = _const("g")
    period_s = 2.0 * math.pi * math.sqrt(length_m / g)
    target = _requested_unit(problem, _DIM_TIME, "s")
    out = convert(period_s, "s", target)
    if out is None:
        return None
    steps: list[SolutionStep] = []
    _step(
        steps,
        f"Simple pendulum length L = {raw_val:g} {raw_unit} ({length_m:g} m)",
        f"g = {g} m/s^2",
    )
    _step(steps, "Apply T = 2π·√(L / g)", f"{_fmt(out)} {target}")
    return WorkedSolution(
        problem=problem,
        subject="physics",
        steps=steps,
        final_answer=f"{_fmt(out)} {target}",
        method="physics",
        confidence=0.95,
    )


def _solve_kinetic_energy(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if "kinetic energy" not in low:
        return None
    if _DIM_MASS not in qty or _DIM_VELOCITY not in qty:
        return None
    m_kg, m_raw, m_unit = qty[_DIM_MASS][0]
    v_ms, v_raw, v_unit = qty[_DIM_VELOCITY][0]
    if m_kg < 0:
        return None
    ke_j = 0.5 * m_kg * v_ms * v_ms
    target = _requested_unit(problem, _DIM_ENERGY, "J")
    out = convert(ke_j, "J", target)
    if out is None:
        return None
    steps: list[SolutionStep] = []
    _step(
        steps,
        f"Given m = {m_raw:g} {m_unit} ({m_kg:g} kg), v = {v_raw:g} {v_unit} ({v_ms:g} m/s)",
        "",
    )
    _step(steps, "Apply KE = ½·m·v²", f"{_fmt(out)} {target}")
    return WorkedSolution(
        problem=problem,
        subject="physics",
        steps=steps,
        final_answer=f"{_fmt(out)} {target}",
        method="physics",
        confidence=0.95,
    )


def _solve_newtons_second_law(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if "force" in low and _DIM_MASS in qty and _DIM_ACCEL in qty:
        m_kg, m_raw, m_unit = qty[_DIM_MASS][0]
        a_ms2, a_raw, a_unit = qty[_DIM_ACCEL][0]
        force_n = m_kg * a_ms2
        target = _requested_unit(problem, _DIM_FORCE, "N")
        out = convert(force_n, "N", target)
        if out is None:
            return None
        steps: list[SolutionStep] = []
        _step(steps, f"Given m = {m_raw:g} {m_unit} ({m_kg:g} kg), a = {a_raw:g} {a_unit}", "")
        _step(steps, "Apply Newton's second law F = m·a", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    if "acceleration" in low and _DIM_FORCE in qty and _DIM_MASS in qty:
        f_n, f_raw, f_unit = qty[_DIM_FORCE][0]
        m_kg, m_raw, m_unit = qty[_DIM_MASS][0]
        if m_kg <= 0:
            return None
        a_ms2 = f_n / m_kg
        steps = []
        _step(steps, f"Given F = {f_raw:g} {f_unit}, m = {m_raw:g} {m_unit}", "")
        _step(steps, "Apply Newton's second law a = F / m", f"{_fmt(a_ms2)} m/s^2")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(a_ms2)} m/s^2",
            method="physics",
            confidence=0.95,
        )
    return None


def _solve_free_fall(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if not any(
        kw in low for kw in ("dropped", "free fall", "free-fall", "falls for", "falling for")
    ):
        return None
    if _DIM_TIME not in qty:
        return None
    t_s, t_raw, t_unit = qty[_DIM_TIME][0]
    if t_s < 0:
        return None
    g = _const("g")
    asks_distance = any(kw in low for kw in ("how far", "distance", "height", "fall"))
    asks_velocity = any(kw in low for kw in ("velocity", "speed", "fast"))
    if asks_velocity and not ("how far" in low or "distance" in low):
        v_ms = g * t_s
        target = _requested_unit(problem, _DIM_VELOCITY, "m/s")
        out = convert(v_ms, "m/s", target)
        if out is None:
            return None
        steps: list[SolutionStep] = []
        _step(
            steps, f"Free fall from rest for t = {t_raw:g} {t_unit} ({t_s:g} s)", f"g = {g} m/s^2"
        )
        _step(steps, "Apply v = g·t", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    if asks_distance:
        d_m = 0.5 * g * t_s * t_s
        target = _requested_unit(problem, _DIM_LENGTH, "m")
        out = convert(d_m, "m", target)
        if out is None:
            return None
        steps = []
        _step(
            steps, f"Free fall from rest for t = {t_raw:g} {t_unit} ({t_s:g} s)", f"g = {g} m/s^2"
        )
        _step(steps, "Apply d = ½·g·t²", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    return None


def _solve_kinematics(
    problem: str, qty: dict[tuple[int, ...], list[tuple[float, float, str]]]
) -> WorkedSolution | None:
    low = problem.lower()
    if _DIM_ACCEL not in qty or _DIM_TIME not in qty:
        return None
    a_ms2, a_raw, a_unit = qty[_DIM_ACCEL][0]
    t_s, t_raw, t_unit = qty[_DIM_TIME][0]
    if "from rest" in low:
        v0 = 0.0
    elif _DIM_VELOCITY in qty:
        v0 = qty[_DIM_VELOCITY][0][0]
    else:
        return None

    if any(kw in low for kw in ("final velocity", "final speed", "velocity", "speed")):
        v_ms = v0 + a_ms2 * t_s
        target = _requested_unit(problem, _DIM_VELOCITY, "m/s")
        out = convert(v_ms, "m/s", target)
        if out is None:
            return None
        steps: list[SolutionStep] = []
        _step(steps, f"Given v₀ = {v0:g} m/s, a = {a_raw:g} {a_unit}, t = {t_raw:g} {t_unit}", "")
        _step(steps, "Apply v = v₀ + a·t", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    if any(kw in low for kw in ("how far", "distance", "displacement")):
        d_m = v0 * t_s + 0.5 * a_ms2 * t_s * t_s
        target = _requested_unit(problem, _DIM_LENGTH, "m")
        out = convert(d_m, "m", target)
        if out is None:
            return None
        steps = []
        _step(steps, f"Given v₀ = {v0:g} m/s, a = {a_raw:g} {a_unit}, t = {t_raw:g} {t_unit}", "")
        _step(steps, "Apply d = v₀·t + ½·a·t²", f"{_fmt(out)} {target}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=f"{_fmt(out)} {target}",
            method="physics",
            confidence=0.95,
        )
    return None


def solve_physics_problem(problem: str) -> WorkedSolution | None:
    """Try deterministic introductory physics solvers; return ``None`` if no rule applies."""
    qty = _extract_quantities(problem)
    if not qty:
        return None
    for fn in (
        _solve_photon,
        _solve_pendulum,
        _solve_kinetic_energy,
        _solve_newtons_second_law,
        _solve_free_fall,
        _solve_kinematics,
    ):
        solution = fn(problem, qty)
        if solution is not None:
            return solution
    return None


__all__ = ["solve_physics_problem"]
