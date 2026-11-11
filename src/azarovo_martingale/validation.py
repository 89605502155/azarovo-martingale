"""Validation of one measurement of a VM before it enters a monitor.

:func:`validate_measurement` is the single public check of incoming data. It is
used by :meth:`~azarovo_martingale.VmMonitor.record_measurement`, so a bad
reading is refused before any state changes.
"""

from __future__ import annotations

import math
import numbers

__all__ = ["validate_measurement"]


def _real(label: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        msg = f"{label} must be a real number, got {type(value).__name__} {value!r}"
        raise TypeError(msg)
    number = float(value)
    if not math.isfinite(number):
        msg = f"{label} must be finite, got {number!r}"
        raise ValueError(msg)
    return number


def validate_measurement(
    t: object,
    used: object,
    free: object,
    last_t: float | None = None,
) -> tuple[float, float, float]:
    """Check one reading ``(t, used, free)`` of a VM and return it as floats.

    Parameters
    ----------
    t : real number
        Time of the reading, seconds (or the base unit of the monitor). Must be
        finite, non-negative, and later than ``last_t`` when that is given.
    used : real number
        Memory used by the VM, MiB. Finite and non-negative.
    free : real number
        Free memory reserve of the VM, MiB. Finite and non-negative.
    last_t : float, optional
        Time of the previous accepted reading; ``None`` for the first one.

    Returns
    -------
    tuple of float
        ``(t, used, free)`` as floats.

    Raises
    ------
    TypeError
        If a value is not a real number: a bool, a string, ``None``, a complex
        number, and similar are refused.
    ValueError
        If a value is NaN or infinite, negative, or if ``t`` does not increase.

    Examples
    --------
    >>> validate_measurement(1, 2048, 1352.5)
    (1.0, 2048.0, 1352.5)
    >>> validate_measurement("1", 2048, 1352.5)
    Traceback (most recent call last):
    ...
    TypeError: t must be a real number, got str '1'
    """
    time = _real("t", t)
    used_mib = _real("used", used)
    free_mib = _real("free", free)
    if time < 0.0:
        msg = f"t must be non-negative, got {time!r}"
        raise ValueError(msg)
    if used_mib < 0.0:
        msg = f"used must be non-negative, got {used_mib!r}"
        raise ValueError(msg)
    if free_mib < 0.0:
        msg = f"free must be non-negative, got {free_mib!r}"
        raise ValueError(msg)
    if last_t is not None and time <= last_t:
        msg = f"time must increase: {time!r} after {last_t!r}"
        raise ValueError(msg)
    return time, used_mib, free_mib
