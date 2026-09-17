"""Typed errors shared across OLIVIA packages."""

from __future__ import annotations


class OliviaError(Exception):
    """Base class for all typed OLIVIA errors."""


class SolverParseError(OliviaError):
    """A matched solver intent whose expression failed to parse/evaluate."""

    def __init__(self, message: str, *, expression: str = "") -> None:
        super().__init__(message)
        self.expression = expression
