"""Argument checks shared by the modules of the package."""

from __future__ import annotations

import math
import numbers


def check_real(name: str, value: object) -> float:
    """Return ``value`` as a float if it is a real number (not a bool), else raise TypeError."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        msg = f"{name} must be a real number, got {type(value).__name__} {value!r}"
        raise TypeError(msg)
    return float(value)


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


def check_bets(name: str, values: tuple[float, ...]) -> tuple[float, ...]:
    """Require a non-empty sequence of betting fractions, each in [0, 1); return it as floats."""
    if not values:
        msg = f"{name} must be a non-empty sequence of betting fractions, got {values!r}"
        raise ValueError(msg)
    out = tuple(check_real(f"each of {name}", x) for x in values)
    if any(not 0.0 <= x < 1.0 for x in out):
        msg = f"each of {name} must lie in [0, 1), got {values!r}"
        raise ValueError(msg)
    return out


def check_weights(name: str, weights: tuple[float, ...], size: int) -> tuple[float, ...]:
    """Require one non-negative weight per bet, summing to 1; return them as floats."""
    if len(weights) != size:
        msg = f"{name} must have one weight per bet ({size}), got {weights!r}"
        raise ValueError(msg)
    out = tuple(check_real(f"each of {name}", w) for w in weights)
    if any(not (math.isfinite(w) and w >= 0.0) for w in out):
        msg = f"each of {name} must be finite and non-negative, got {weights!r}"
        raise ValueError(msg)
    if not math.isclose(math.fsum(out), 1.0, rel_tol=0.0, abs_tol=1e-9):
        msg = f"{name} must sum to 1, got sum {math.fsum(out)!r}"
        raise ValueError(msg)
    return out
