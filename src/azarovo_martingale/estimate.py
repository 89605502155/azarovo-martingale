"""Estimation of the largest change ``c`` of the memory use from a monitoring log.

Assumption A1 of the article requires a bound ``c`` on the change of the use over
one base step. The sample maximum with a safety margin is the bound used by the
article. A quantile below 1 is a robust alternative: a few rare jumps then do not
set ``c``, but the guarantee of formula (6) no longer covers those jumps.

The estimate is meaningful only for changes over one base step. A change over ``k``
steps can be far below the largest single-step change, because the steps cancel,
so the monitors and the log analysis pass one-step pairs only. An estimated ``c``
satisfies A1 only if the sample is representative: no guarantee is proved for it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from ._checks import check_positive

__all__ = ["estimate_c", "exceedance_share"]


def _rates(deltas: Iterable[float], steps: Iterable[float] | None) -> list[float]:
    """Return the absolute rates ``|dx| / step`` of the increments."""
    d = list(deltas)
    if not d:
        msg = "the list of increments is empty"
        raise ValueError(msg)
    s = [1.0] * len(d) if steps is None else list(steps)
    if len(s) != len(d):
        msg = "deltas and steps must have the same length"
        raise ValueError(msg)
    for st in s:
        check_positive("step", st)
    return sorted(abs(x) / st for x, st in zip(d, s, strict=True))


def estimate_c(
    deltas: Iterable[float],
    steps: Iterable[float] | None = None,
    *,
    quantile: float = 1.0,
    margin: float = 1.2,
) -> float:
    """Estimate ``c`` as ``margin`` times a quantile of the rates ``|dx| / step``.

    Parameters
    ----------
    deltas : iterable of float
        Changes of the memory use between neighbouring samples, MiB.
    steps : iterable of float, optional
        Length of each interval in base steps; all ones by default.
    quantile : float, default 1.0
        Level of the quantile of the rates. ``1`` is the maximum, the choice of
        the article. Below 1 the estimate ignores the largest ``1 - quantile``
        share of the rates, which makes it robust to rare jumps.
    margin : float, default 1.2
        Safety factor, at least 1.

    Returns
    -------
    float
        ``margin`` times the chosen quantile of the rates, MiB per base step.

    Raises
    ------
    ValueError
        If the input is empty, the lengths differ, the arguments are out of
        range, or every increment is zero (then ``c`` cannot be estimated).

    Examples
    --------
    >>> estimate_c([10, -40, 25], margin=1.0)
    40.0
    >>> estimate_c([10, -40, 25], margin=1.5)
    60.0
    >>> estimate_c([10, -40, 60], steps=[1, 1, 2], margin=1.0)
    40.0
    >>> estimate_c(range(1, 101), quantile=0.9, margin=1.0)
    90.0
    """
    if not 0.0 < quantile <= 1.0:
        msg = f"quantile must lie in (0, 1], got {quantile!r}"
        raise ValueError(msg)
    if not margin >= 1.0:
        msg = f"margin cannot be below 1, got {margin!r}"
        raise ValueError(msg)
    rates = _rates(deltas, steps)
    k = max(0, math.ceil(quantile * len(rates)) - 1)
    value = margin * rates[k]
    if not value > 0:
        msg = "all increments are zero: c cannot be estimated"
        raise ValueError(msg)
    return float(value)


def exceedance_share(
    deltas: Sequence[float] | Iterable[float],
    steps: Sequence[float] | Iterable[float] | None,
    c: float,
) -> float:
    """Return the share of increments whose rate ``|dx| / step`` exceeds ``c``.

    This is the check of assumption A1 on data: a share near zero supports the
    guarantee of formula (6).

    Examples
    --------
    >>> exceedance_share([10, -40, 25], None, 20.0)
    0.6666666666666666
    """
    check_positive("c", c)
    rates = _rates(deltas, steps)
    return sum(1 for r in rates if r > c) / len(rates)
