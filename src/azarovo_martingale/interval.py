"""Monitoring interval from the Azuma-Hoeffding inequality.

Formulas (5) and (7)-(9) of the article.

A virtual machine (VM) is checked, then not observed for ``n`` base steps. The
question is how long ``n`` may be so that the free memory ``R`` is not exhausted
with probability above ``delta``. :func:`monitoring_interval` answers it.
"""

from __future__ import annotations

import math

from ._checks import check_level, check_positive

__all__ = ["azuma_bound", "max_rise_bound", "monitoring_interval"]


def monitoring_interval(
    reserve: float,
    c: float,
    delta: float,
    n_max: int | None = None,
) -> int:
    """Return the interval to the next check, in base steps, formulas (7)-(9).

    Parameters
    ----------
    reserve : float
        Free memory reserve of the VM at the check, MiB.
    c : float
        Largest change of the memory use over one base step, MiB (assumption A1).
    delta : float
        Admissible probability that the reserve is exhausted before the next check.
    n_max : int or None, optional
        Technical upper bound on the interval; ``None`` means no bound.

    Returns
    -------
    int
        The interval ``n*`` in base steps. ``0`` means ``R <= c``: the reserve does
        not cover even one step, so the memory must be redistributed now.

    Raises
    ------
    ValueError
        If ``c`` or ``delta`` is outside its range, or ``n_max`` is negative.

    Notes
    -----
    Guarantee. If the increments of the memory use are bounded by ``c`` and are
    not positive on average (assumptions A1 and A2), the probability that the
    use rises by ``R`` or more within the returned interval is at most ``delta``
    (inequality (6)). The bound is ``n_A`` from (7) or ``n_0`` from (8), whichever
    is larger, capped by ``n_max`` as in (9).

    Examples
    --------
    >>> monitoring_interval(512, 20, 0.01)
    71
    >>> monitoring_interval(512, 20, 0.01, n_max=60)
    60
    >>> monitoring_interval(15, 20, 0.01)
    0
    """
    check_positive("c", c)
    check_level("delta", delta)
    if n_max is not None and n_max < 0:
        msg = f"n_max cannot be negative, got {n_max!r}"
        raise ValueError(msg)
    if not reserve > c:  # also catches NaN
        return 0
    n_a = math.floor(reserve * reserve / (2.0 * c * c * math.log(1.0 / delta)))  # formula (7)
    n_0 = math.ceil(reserve / c) - 1  # formula (8)
    n = max(n_0, n_a)  # formula (9), before the cap
    if n_max is not None:
        n = min(n, n_max)
    return int(n)


def azuma_bound(n: float, reserve: float, c: float) -> float:
    """Return the Azuma-Hoeffding bound on the rise of the use, formula (5) with t = R.

    The probability that a supermartingale with increments bounded by ``c``
    rises by ``R`` or more within ``n`` steps is at most ``exp(-R^2 / (2 n c^2))``.

    Parameters
    ----------
    n : float
        Number of base steps, positive.
    reserve : float
        Rise level ``R``, MiB.
    c : float
        Bound of the increments, MiB per step, positive.

    Returns
    -------
    float
        The bound, between 0 and 1.

    Examples
    --------
    >>> round(azuma_bound(71, 512, 20), 4)
    0.0099
    """
    check_positive("n", n)
    check_positive("c", c)
    return math.exp(-(reserve * reserve) / (2.0 * n * c * c))


def max_rise_bound(n: float, c: float, delta: float) -> float:
    """Return the rise of the use not exceeded with probability ``1 - delta``.

    This is ``c * sqrt(2 n ln(1/delta))`` from the discussion of formula (5): for
    ``n = 100`` and ``delta = 0.01`` it is about ``30 c``, against ``100 c`` in the
    worst case.

    Examples
    --------
    >>> round(max_rise_bound(100, 1.0, 0.01), 1)
    30.3
    """
    check_positive("n", n)
    check_positive("c", c)
    check_level("delta", delta)
    return c * math.sqrt(2.0 * n * math.log(1.0 / delta))
