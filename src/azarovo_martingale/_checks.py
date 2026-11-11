"""Argument checks shared by the modules of the package."""

from __future__ import annotations

import math


def check_positive(name: str, value: float) -> None:
    """Require a positive finite number."""
    if not (value > 0 and math.isfinite(value)):
        msg = f"{name} must be a positive finite number, got {value!r}"
        raise ValueError(msg)


def check_level(name: str, value: float) -> None:
    """Require a risk level strictly between 0 and 1."""
    if not 0.0 < value < 1.0:
        msg = f"{name} must lie in the open interval (0, 1), got {value!r}"
        raise ValueError(msg)


def check_bet(name: str, value: float) -> None:
    """Require a betting fraction in [0, 1)."""
    if not 0.0 <= value < 1.0:
        msg = f"{name} must lie in [0, 1), got {value!r}"
        raise ValueError(msg)


def check_bets(name: str, values: tuple[float, ...]) -> None:
    """Require a non-empty collection of betting fractions in (0, 1)."""
    if not values or any(not 0.0 < x < 1.0 for x in values):
        msg = f"{name} must be a non-empty sequence of numbers in (0, 1), got {values!r}"
        raise ValueError(msg)
