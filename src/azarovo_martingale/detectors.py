"""Anytime-valid detectors of the start of memory growth.

Each detector plays a betting game against the hypothesis "the memory use does
not grow": under that hypothesis its capital is a non-negative supermartingale
that starts at 1. By Ville's inequality (formula (4) of the article) the
probability that the capital ever reaches ``1/alpha`` is at most ``alpha``,
however many times the detector is looked at and however the check moments
were chosen. This is the guarantee that a fixed-sample test does not give.

The capital is stored as its logarithm. A plain product underflows to zero
after hours of calm operation, and the detector would then stop reacting.

Detectors
---------
GrowthDetector
    Formulas (11) and (12) of the article: one bet with fraction ``lam``.
CusumGrowthDetector
    Formula (14): a CUSUM-type statistic that does not fall below ``1 - lam``.
    Its guarantee is on the mean time to a false alarm, not on a probability.
SubGaussianGrowthDetector
    Addition: several sub-Gaussian bets averaged, from the earlier code of the
    author; section 1.4 of the article (Azuma–Hoeffding) is its basis.
MixtureGrowthDetector
    Addition beyond the article: a uniform mixture of bets over a fixed grid of
    fractions. It needs no choice of ``lam`` and keeps the guarantee of Ville.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, Self

from ._checks import check_bet, check_bets, check_level, check_positive

__all__ = [
    "DEFAULT_BETS",
    "CusumGrowthDetector",
    "GrowthDetector",
    "GrowthTest",
    "MixtureGrowthDetector",
    "SubGaussianGrowthDetector",
]

DEFAULT_BETS: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
"""Grid of bet fractions of :class:`MixtureGrowthDetector` (the addition of this package)."""

_DEFAULT_SUBGAUSSIAN_LAMS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0)


class GrowthTest(Protocol):
    """Interface shared by the detectors, as used by the scheduler."""

    def update(self, dx: float, n: float = 1.0) -> bool:
        """Take in the change ``dx`` over ``n`` base steps; ``True`` means an alarm."""
        ...

    def reset(self) -> None:
        """Restart the detector."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the state as JSON-serialisable values."""
        ...


def _normalised(dx: float, n: float, c: float) -> float:
    """Return ``Y = dx / (n c)`` clipped to [-1, 1] (assumption A1, normalisation of (11))."""
    check_positive("n", n)
    if not math.isfinite(dx):
        msg = f"dx must be finite, got {dx!r}"
        raise ValueError(msg)
    return max(-1.0, min(1.0, dx / (n * c)))


def _log_mean_exp(values: Sequence[float]) -> float:
    """Return ``log(mean(exp(v)))`` computed without overflow."""
    top = max(values)
    return top + math.log(sum(math.exp(v - top) for v in values) / len(values))


@dataclass
class GrowthDetector:
    """Detector of the start of memory growth by a betting test, formulas (11) and (12).

    The imaginary player stakes the fraction ``lam`` of the capital on the growth
    of the memory use. Each update multiplies the capital by ``1 + lam Y``, where
    ``Y = dx / (n c)`` (formula (11)). The alarm is raised when ``K >= 1/alpha``
    (formula (12)). Under assumption A2 the false-alarm probability is at most
    ``alpha`` however often the detector is updated (Ville's inequality (4)).

    Parameters
    ----------
    c : float
        Largest change of the use over one base step, MiB (assumption A1).
    lam : float, default 0.5
        Fraction of the capital staked on each step, in [0, 1). It may be changed
        between updates, but only from data already seen.
    alpha : float, default 0.01
        Admissible probability of a false alarm.
    log_capital : float, default 0.0
        Logarithm of the capital; 0 means ``K = 1``.

    Notes
    -----
    The increment is clipped to [-1, 1] after normalisation. So the capital stays
    positive and a rare jump larger than ``n c`` cannot make it negative.

    Examples
    --------
    >>> det = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
    >>> for dx in (10.0, -20.0, 5.0, -10.0):
    ...     _ = det.update(dx)
    >>> round(det.capital, 2)
    0.83
    >>> alarms = []
    >>> det = GrowthDetector(c=50.0)
    >>> for step in range(1, 40):
    ...     if det.update(30.0):
    ...         alarms.append(step)
    ...         det.reset()
    >>> alarms
    [18, 36]
    """

    c: float
    lam: float = 0.5
    alpha: float = 0.01
    log_capital: float = 0.0

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("c", self.c)
        check_bet("lam", self.lam)
        check_level("alpha", self.alpha)

    @property
    def capital(self) -> float:
        """Current capital ``K``."""
        return math.exp(self.log_capital)

    @property
    def threshold(self) -> float:
        """Alarm level ``1 / alpha``."""
        return 1.0 / self.alpha

    def update(self, dx: float, n: float = 1.0) -> bool:
        """Take in the change ``dx`` of the use over ``n`` base steps.

        Returns ``True`` if the capital reached ``1 / alpha`` (an alarm).
        """
        y = _normalised(dx, n, self.c)
        self.log_capital += math.log1p(self.lam * y)
        return self.log_capital >= -math.log(self.alpha)

    def reset(self) -> None:
        """Restart with ``K = 1``."""
        self.log_capital = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the state as a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the detector from :meth:`to_dict` output."""
        return cls(**data)


@dataclass
class CusumGrowthDetector:
    """CUSUM-type modification of the detector, formula (14).

    The statistic is ``C_n = max(C_{n-1}, 1) (1 + lam Y_n)``. It never falls below
    ``1 - lam``, so after a long calm period a rise is seen without the delay of
    climbing from the bottom. The guarantee is different from (12): the mean time
    to a false alarm is at least ``threshold`` base steps, not a probability.

    Parameters
    ----------
    c : float
        Largest change of the use over one base step, MiB.
    lam : float, default 0.5
        Fraction of the statistic staked on each step, in [0, 1).
    threshold : float, default 1e5
        Alarm level ``A``. With a step of 1 s, ``1e5`` allows about one false alarm
        per 28 hours on average.
    log_statistic : float, default 0.0
        Logarithm of the statistic ``C``.

    Examples
    --------
    >>> det = CusumGrowthDetector(c=50.0, lam=0.5, threshold=1e5)
    >>> for _ in range(1000):
    ...     _ = det.update(-50.0)
    >>> round(det.statistic, 3)
    0.5
    """

    c: float
    lam: float = 0.5
    threshold: float = 1e5
    log_statistic: float = 0.0

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("c", self.c)
        check_bet("lam", self.lam)
        if not (math.isfinite(self.threshold) and self.threshold > 1.0):
            msg = f"threshold must be a finite number above 1, got {self.threshold!r}"
            raise ValueError(msg)

    @property
    def statistic(self) -> float:
        """Current value of the statistic ``C``."""
        return math.exp(self.log_statistic)

    def update(self, dx: float, n: float = 1.0) -> bool:
        """Take in the change ``dx`` over ``n`` base steps. ``True`` means an alarm."""
        y = _normalised(dx, n, self.c)
        self.log_statistic = max(self.log_statistic, 0.0) + math.log1p(self.lam * y)
        return self.log_statistic >= math.log(self.threshold)

    def reset(self) -> None:
        """Restart with ``C = 1``."""
        self.log_statistic = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the state as a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the detector from :meth:`to_dict` output."""
        return cls(**data)


@dataclass
class SubGaussianGrowthDetector:
    """Addition: a detector with sub-Gaussian bets averaged over several scales.

    Not in the text of the article; it is the variant of the earlier code of the
    author, built on the Azuma–Hoeffding bound of section 1.4. For each ``lam`` in
    ``lams`` the capital changes as ``K_lam <- K_lam exp(lam z - lam^2 / 2)``, with
    ``z = dx / (c sqrt(n))``. By Hoeffding's lemma each factor is a supermartingale, and
    so is their average.
    A single update moves the capital by an amount that grows with ``sqrt(n)``,
    so long intervals need fewer checks to raise an alarm than formula (11).

    Parameters
    ----------
    c : float
        Largest change of the use over one base step, MiB.
    alpha : float, default 0.01
        Admissible probability of a false alarm.
    lams : tuple of float, default (0.25, 0.5, 1, 2, 4)
        Positive scale parameters of the bets.
    logs : list of float, optional
        Logarithms of the capitals of the bets; zeros at the start.
    """

    c: float
    alpha: float = 0.01
    lams: tuple[float, ...] = _DEFAULT_SUBGAUSSIAN_LAMS
    logs: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("c", self.c)
        check_level("alpha", self.alpha)
        self.lams = tuple(self.lams)
        if not self.lams or any(not (x > 0 and math.isfinite(x)) for x in self.lams):
            msg = f"lams must be positive finite numbers, got {self.lams!r}"
            raise ValueError(msg)
        if not self.logs:
            self.logs = [0.0] * len(self.lams)
        if len(self.logs) != len(self.lams):
            msg = "logs and lams must have the same length"
            raise ValueError(msg)

    @property
    def log_capital(self) -> float:
        """Logarithm of the average capital ``K``."""
        return _log_mean_exp(self.logs)

    @property
    def capital(self) -> float:
        """Current average capital ``K``."""
        return math.exp(self.log_capital)

    def update(self, dx: float, n: float = 1.0) -> bool:
        """Take in the change ``dx`` over ``n`` base steps. ``True`` means an alarm."""
        check_positive("n", n)
        if not math.isfinite(dx):
            msg = f"dx must be finite, got {dx!r}"
            raise ValueError(msg)
        bound = n * self.c
        z = max(-bound, min(bound, dx)) / (self.c * math.sqrt(n))
        self.logs = [
            x + lam * z - 0.5 * lam * lam for x, lam in zip(self.logs, self.lams, strict=True)
        ]
        return self.log_capital >= -math.log(self.alpha)

    def reset(self) -> None:
        """Restart with all capitals equal to 1."""
        self.logs = [0.0] * len(self.lams)

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the state as a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the detector from :meth:`to_dict` output."""
        return cls(**data)


@dataclass
class MixtureGrowthDetector:
    """Addition beyond the article: a mixture of betting tests with no tuned fraction.

    The capital is the uniform average over a fixed grid of bet fractions
    ``lams`` of the products ``prod (1 + lam_j Y_k)``, as in formula (11). Each
    product is a non-negative supermartingale with initial value 1 under the
    hypothesis of formulas (10), and an average of such supermartingales is one
    too. So Ville's inequality (4) applies to the mixture without any choice of
    ``lam``, and the false-alarm probability stays at most ``alpha``.

    The price of not choosing is a penalty of ``log(len(lams))`` in the log
    capital, about 2.2 for the default nine bets. The gain is that the detector
    tracks the unknown speed of growth: for slow growth the large bets lose, for
    fast growth the small ones do, and the mixture is never far from the better.

    Parameters
    ----------
    c : float
        Largest change of the use over one base step, MiB.
    alpha : float, default 0.01
        Admissible probability of a false alarm.
    lams : tuple of float, default DEFAULT_BETS
        Grid of bet fractions, each in (0, 1).
    logs : list of float, optional
        Logarithms of the capitals of the single bets; zeros at the start.

    Examples
    --------
    >>> det = MixtureGrowthDetector(c=50.0)
    >>> alarms = []
    >>> for step in range(1, 60):
    ...     if det.update(30.0):
    ...         alarms.append(step)
    ...         det.reset()
    >>> alarms[0] < 25
    True
    """

    c: float
    alpha: float = 0.01
    lams: tuple[float, ...] = DEFAULT_BETS
    logs: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("c", self.c)
        check_level("alpha", self.alpha)
        self.lams = tuple(self.lams)
        check_bets("lams", self.lams)
        if not self.logs:
            self.logs = [0.0] * len(self.lams)
        if len(self.logs) != len(self.lams):
            msg = "logs and lams must have the same length"
            raise ValueError(msg)

    @property
    def log_capital(self) -> float:
        """Logarithm of the mixture capital ``K``."""
        return _log_mean_exp(self.logs)

    @property
    def capital(self) -> float:
        """Current mixture capital ``K``."""
        return math.exp(self.log_capital)

    def update(self, dx: float, n: float = 1.0) -> bool:
        """Take in the change ``dx`` over ``n`` base steps. ``True`` means an alarm."""
        y = _normalised(dx, n, self.c)
        self.logs = [x + math.log1p(lam * y) for x, lam in zip(self.logs, self.lams, strict=True)]
        return self.log_capital >= -math.log(self.alpha)

    def reset(self) -> None:
        """Restart with all capitals equal to 1."""
        self.logs = [0.0] * len(self.lams)

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the state as a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the detector from :meth:`to_dict` output."""
        return cls(**data)
