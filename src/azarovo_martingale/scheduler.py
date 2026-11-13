"""Joint choice of the monitoring moment, algorithm of Fig. 3 of the article.

The interval rule (formulas (7)-(9)) says how long a VM may be left unobserved
while its memory use stays calm. A growth detector watches whether that calm
holds. When it does not, or when the reserve is below one step, the memory is
redistributed and the interval drops to ``n_min``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Self, get_args

from ._checks import check_level, check_positive
from .detectors import (
    DEFAULT_BETS,
    CusumGrowthDetector,
    GrowthDetector,
    GrowthTest,
    MixtureGrowthDetector,
    SubGaussianGrowthDetector,
)
from .interval import monitoring_interval

__all__ = ["DETECTOR_KINDS", "Decision", "DetectorKind", "MonitoringScheduler"]

DetectorKind = Literal["ville", "cusum", "subgaussian", "mixture"]
"""Name of a detector of the scheduler: ``ville`` (11)-(12), ``cusum`` (14), and the additions."""

DETECTOR_KINDS: tuple[str, ...] = get_args(DetectorKind)


@dataclass(frozen=True)
class Decision:
    """Outcome of one step of the scheduler, steps 3-6 of Fig. 3.

    Attributes
    ----------
    interval : int
        Base steps to wait before the next check.
    redistribute : bool
        ``True`` if the memory of the VM must be redistributed now.
    alarm : bool
        ``True`` if the growth detector raised an alarm at this step.
    calibrated : bool
        ``False`` while the streaming monitor is still estimating ``c``; the
        interval is then the conservative ``n_min``. Always ``True`` for the
        scheduler itself.
    """

    interval: int
    redistribute: bool
    alarm: bool
    calibrated: bool = True


@dataclass
class MonitoringScheduler:
    """Joint algorithm of Fig. 3: the interval rule of (7)-(9) and a growth detector.

    Parameters
    ----------
    c : float
        Largest change of the use over one base step, MiB (assumption A1).
    delta : float, default 0.01
        Admissible risk that the reserve is exhausted before the next check.
    alpha : float, default 0.01
        Admissible false-alarm probability of the detector ``ville`` and the
        additions. Not used by ``cusum``.
    lam : float, default 0.5
        Betting fraction of the ``ville`` detector, formula (11).
    n_min : int, default 1
        Interval after a redistribution (step 5 of Fig. 3).
    n_max : int or None, default 600
        Technical upper bound on the interval in base steps.
    kind : {"ville", "cusum", "subgaussian", "mixture"}, default "ville"
        Detector of step 3. ``ville`` is formulas (11)-(12) as in Fig. 3; ``cusum``
        is formula (14); ``subgaussian`` and ``mixture`` are the additions.
    cusum_threshold : float, default 1e5
        Level ``A`` of the ``cusum`` detector.
    lams : tuple of float, optional
        Parameters of the ``subgaussian`` or ``mixture`` detector; defaults are
        those of the detector classes.
    weights : tuple of float, optional
        Weights of the bets of the ``mixture`` detector (non-negative, sum 1);
        uniform by default. Ignored by the other kinds.
    clip : bool, default True
        Clip the normalised change ``Y`` to [-1, 1] in the detector (see
        :class:`~azarovo_martingale.GrowthDetector`). Under A1 this changes nothing.

    Attributes
    ----------
    interval : int
        Interval chosen by the last step (``n_min`` at the start).
    detector : GrowthTest
        The growth detector in use.

    Examples
    --------
    >>> sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
    >>> sched.interval
    1
    >>> sched.step(dx=0.0, reserve=512.0).interval
    71
    >>> decision = sched.step(dx=0.0, reserve=15.0)
    >>> decision.interval, decision.redistribute
    (1, True)
    """

    c: float
    delta: float = 0.01
    alpha: float = 0.01
    lam: float = 0.5
    n_min: int = 1
    n_max: int | None = 600
    kind: DetectorKind = "ville"
    cusum_threshold: float = 1e5
    lams: tuple[float, ...] | None = None
    weights: tuple[float, ...] | None = None
    clip: bool = True
    detector: GrowthTest = field(init=False, repr=False)
    interval: int = field(init=False)

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("c", self.c)
        check_level("delta", self.delta)
        if self.n_min < 1:
            msg = f"n_min must be at least 1, got {self.n_min!r}"
            raise ValueError(msg)
        if self.n_max is not None and self.n_max < self.n_min:
            msg = "n_max must be at least n_min"
            raise ValueError(msg)
        self.detector = _build_detector(self)
        self.interval = self.n_min

    def step(self, dx: float, reserve: float, n_elapsed: float | None = None) -> Decision:
        """Run steps 3-6 of Fig. 3 for one check.

        Parameters
        ----------
        dx : float
            Change of the memory use over the elapsed interval, MiB.
        reserve : float
            Free memory reserve R now, MiB.
        n_elapsed : float, optional
            Length of the elapsed interval in base steps; defaults to the interval
            assigned at the previous step.

        Returns
        -------
        Decision
            The next interval, whether to redistribute, and whether the detector
            alarmed. A redistribution restarts the detector and sets the interval
            to ``n_min``.
        """
        n_prev = self.interval if n_elapsed is None else n_elapsed
        alarm = self.detector.update(dx, n_prev)  # step 3, normalisation Y = dx/(n c)
        if alarm or not reserve > self.c:  # step 4: K >= 1/alpha, or R <= c
            self.detector.reset()  # step 5
            self.interval = self.n_min
            return Decision(interval=self.interval, redistribute=True, alarm=alarm)
        self.interval = monitoring_interval(reserve, self.c, self.delta, self.n_max)  # step 6
        return Decision(interval=self.interval, redistribute=False, alarm=alarm)

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters and the full state as JSON-serialisable values."""
        return {
            "c": self.c,
            "delta": self.delta,
            "alpha": self.alpha,
            "lam": self.lam,
            "n_min": self.n_min,
            "n_max": self.n_max,
            "kind": self.kind,
            "cusum_threshold": self.cusum_threshold,
            "lams": None if self.lams is None else list(self.lams),
            "weights": None if self.weights is None else list(self.weights),
            "clip": self.clip,
            "interval": self.interval,
            "detector": self.detector.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the scheduler, including the detector state, from :meth:`to_dict`."""
        params = {k: v for k, v in data.items() if k not in {"interval", "detector"}}
        if params["lams"] is not None:
            params["lams"] = tuple(params["lams"])
        if params["weights"] is not None:
            params["weights"] = tuple(params["weights"])
        sched = cls(**params)
        sched.detector = _detector_from_dict(sched.kind, data["detector"])
        sched.interval = int(data["interval"])
        return sched


def _detector_from_dict(kind: str, data: dict[str, Any]) -> GrowthTest:
    """Rebuild the detector named ``kind`` from its saved state."""
    if kind == "ville":
        return GrowthDetector.from_dict(data)
    if kind == "cusum":
        return CusumGrowthDetector.from_dict(data)
    if kind == "subgaussian":
        return SubGaussianGrowthDetector.from_dict(data)
    if kind == "mixture":
        return MixtureGrowthDetector.from_dict(data)
    msg = f"unknown detector kind {kind!r}"
    raise ValueError(msg)


def _build_detector(sched: MonitoringScheduler) -> GrowthTest:
    """Create the detector named by ``sched.kind`` with the parameters of the scheduler."""
    kind: str = sched.kind
    if kind == "ville":
        return GrowthDetector(sched.c, sched.lam, sched.alpha, clip=sched.clip)
    if kind == "cusum":
        return CusumGrowthDetector(sched.c, sched.lam, sched.cusum_threshold, clip=sched.clip)
    if kind == "subgaussian":
        if sched.lams is None:
            return SubGaussianGrowthDetector(sched.c, sched.alpha, clip=sched.clip)
        return SubGaussianGrowthDetector(sched.c, sched.alpha, sched.lams, clip=sched.clip)
    if kind == "mixture":
        return MixtureGrowthDetector(
            sched.c, sched.alpha, sched.lams or DEFAULT_BETS, sched.weights, clip=sched.clip
        )
    msg = f"kind must be one of {', '.join(DETECTOR_KINDS)}, got {kind!r}"
    raise ValueError(msg)
