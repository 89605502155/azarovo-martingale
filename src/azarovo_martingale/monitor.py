"""Streaming monitors: one VM (:class:`VmMonitor`) and a fleet (:class:`FleetMonitor`).

A monitor is fed at the moments it asks for: the caller reads the VM when
:meth:`VmMonitor.due` says so, and passes the reading to :meth:`VmMonitor.update`,
which returns the next interval. The state can be saved with ``to_dict`` and
restored with ``from_dict``, so a controller that restarts resumes the detector
and does not lose its calibration.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self

from ._checks import check_level, check_positive
from .estimate import estimate_c
from .scheduler import Decision, DetectorKind, MonitoringScheduler
from .validation import validate_measurement

__all__ = ["FleetMonitor", "VmMonitor"]


@dataclass
class _Counts:
    checks: int = 0
    alarms: int = 0
    redistributions: int = 0


class VmMonitor:
    """Streaming monitor of one virtual machine, the algorithm of Fig. 3.

    Units: memory in MiB, time in seconds (or any base step, see ``step``).

    Parameters
    ----------
    name : str
        Identifier of the VM.
    c : float, optional
        Known bound of the change per base step, MiB. If omitted, ``c`` is
        estimated from the first ``warmup`` checks. Until then the interval is the
        conservative ``n_min`` and :attr:`Decision.calibrated` is ``False``.
    delta, alpha, lam, n_min, n_max, kind, cusum_threshold, lams :
        Parameters of :class:`~azarovo_martingale.MonitoringScheduler`.
    step : float, default 1.0
        Length of a base step, in the unit of the timestamps.
    warmup : int, default 50
        Number of increments used to estimate ``c``; at least 2.
    c_quantile, c_margin : float
        Parameters of :func:`~azarovo_martingale.estimate_c`.

    Examples
    --------
    >>> vm = VmMonitor("vm-01", c=20.0)
    >>> _ = vm.record_measurement(0.0, used=2048.0, free=1352.0)
    >>> decision = vm.record_measurement(1.0, used=2049.0, free=1351.0)
    >>> decision.interval
    495
    >>> vm.next_check_time, vm.due(100.0), vm.due(496.0)
    (496.0, False, True)
    """

    def __init__(
        self,
        name: str,
        *,
        c: float | None = None,
        delta: float = 0.01,
        alpha: float = 0.01,
        lam: float = 0.5,
        n_min: int = 1,
        n_max: int | None = 600,
        kind: DetectorKind = "ville",
        cusum_threshold: float = 1e5,
        lams: tuple[float, ...] | None = None,
        weights: tuple[float, ...] | None = None,
        step: float = 1.0,
        warmup: int = 50,
        c_quantile: float = 1.0,
        c_margin: float = 1.2,
    ) -> None:
        check_positive("step", step)
        if warmup < 2:
            msg = f"warmup must be at least 2, got {warmup!r}"
            raise ValueError(msg)
        self.name = name
        self._options: dict[str, Any] = {
            "c": c,
            "delta": delta,
            "alpha": alpha,
            "lam": lam,
            "n_min": n_min,
            "n_max": n_max,
            "kind": kind,
            "cusum_threshold": cusum_threshold,
            "lams": None if lams is None else list(lams),
            "weights": None if weights is None else list(weights),
            "step": step,
            "warmup": warmup,
            "c_quantile": c_quantile,
            "c_margin": c_margin,
        }
        self._scheduler: MonitoringScheduler | None = None
        self._last_t: float | None = None
        self._last_used: float | None = None
        self._calibration: list[tuple[float, float]] = []
        self._counts = _Counts()
        if c is not None:
            self._scheduler = self._make_scheduler(c)

    # ------------------------------------------------------------------ state
    def _make_scheduler(self, c: float) -> MonitoringScheduler:
        o = self._options
        lams = None if o["lams"] is None else tuple(o["lams"])
        weights = None if o["weights"] is None else tuple(o["weights"])
        return MonitoringScheduler(
            c=c,
            delta=o["delta"],
            alpha=o["alpha"],
            lam=o["lam"],
            n_min=o["n_min"],
            n_max=o["n_max"],
            kind=o["kind"],
            cusum_threshold=o["cusum_threshold"],
            lams=lams,
            weights=weights,
        )

    @property
    def calibrated(self) -> bool:
        """``True`` once ``c`` is known and the detector is running."""
        return self._scheduler is not None

    @property
    def c(self) -> float | None:
        """The bound ``c`` in use, or ``None`` before calibration."""
        return None if self._scheduler is None else self._scheduler.c

    @property
    def interval(self) -> int:
        """Interval to the next check, base steps."""
        if self._scheduler is None:
            return int(self._options["n_min"])
        return self._scheduler.interval

    @property
    def next_check_time(self) -> float | None:
        """Timestamp of the next check, or ``None`` before the first reading."""
        if self._last_t is None:
            return None
        return self._last_t + self.interval * float(self._options["step"])

    @property
    def checks(self) -> int:
        """Number of checks that were processed after the first reading."""
        return self._counts.checks

    @property
    def alarms(self) -> int:
        """Number of growth alarms raised so far."""
        return self._counts.alarms

    @property
    def redistributions(self) -> int:
        """Number of redistributions requested so far."""
        return self._counts.redistributions

    def due(self, t: float) -> bool:
        """Return ``True`` if the VM should be read at time ``t``."""
        nxt = self.next_check_time
        return nxt is None or t >= nxt

    # ----------------------------------------------------------------- update
    def record_measurement(self, t: float, used: float, free: float) -> Decision:
        """Record one measurement of the VM and return the scheduling decision.

        The decision gives the next polling interval, whether to redistribute
        the memory, and whether the growth detector raised an alarm. The first
        measurement only sets the baseline and returns ``n_min``.

        Parameters
        ----------
        t : float
            Time of the measurement; must be later than the previous one.
        used : float
            Memory used by the VM, MiB.
        free : float
            Free memory reserve ``R`` of the VM, MiB.

        Returns
        -------
        Decision
            Next interval, redistribution flag and alarm flag.

        Raises
        ------
        TypeError
            If a value is not a real number (see :func:`validate_measurement`).
        ValueError
            If a value is NaN, infinite or negative, or the time does not increase.
        """
        t, used, free = validate_measurement(t, used, free, self._last_t)
        if self._last_t is None or self._last_used is None:
            self._last_t, self._last_used = t, used
            return Decision(
                self.interval, redistribute=False, alarm=False, calibrated=self.calibrated
            )
        step = float(self._options["step"])
        n_elapsed = (t - self._last_t) / step
        dx = used - self._last_used
        self._last_t, self._last_used = t, used

        if self._scheduler is None:
            return self._calibrate_or_wait(dx, n_elapsed)
        decision = self._scheduler.step(dx, free, n_elapsed)
        self._record(decision)
        return decision

    def _calibrate_or_wait(self, dx: float, n_elapsed: float) -> Decision:
        """Collect increments until ``c`` can be estimated, then start the scheduler."""
        o = self._options
        window = self._calibration
        window.append((dx, n_elapsed))
        del window[: -int(o["warmup"])]
        waiting = Decision(self.interval, redistribute=False, alarm=False, calibrated=False)
        if len(window) < int(o["warmup"]):
            return waiting
        try:
            c = estimate_c(
                [d for d, _ in window],
                [s for _, s in window],
                quantile=float(o["c_quantile"]),
                margin=float(o["c_margin"]),
            )
        except ValueError:
            return waiting  # every increment was zero so far: keep collecting
        self._scheduler = self._make_scheduler(c)
        self._calibration = []
        self._counts.checks += 1
        return Decision(self.interval, redistribute=False, alarm=False, calibrated=True)

    def _record(self, decision: Decision) -> None:
        self._counts.checks += 1
        if decision.alarm:
            self._counts.alarms += 1
        if decision.redistribute:
            self._counts.redistributions += 1

    # ------------------------------------------------------------- persistence
    def to_dict(self) -> dict[str, Any]:
        """Return the options and the full state as JSON-serialisable values."""
        return {
            "name": self.name,
            "options": dict(self._options),
            "last_t": self._last_t,
            "last_used": self._last_used,
            "calibration": [list(pair) for pair in self._calibration],
            "scheduler": None if self._scheduler is None else self._scheduler.to_dict(),
            "counts": {
                "checks": self._counts.checks,
                "alarms": self._counts.alarms,
                "redistributions": self._counts.redistributions,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the monitor from :meth:`to_dict` output."""
        opts = dict(data["options"])
        mon = cls(data["name"], **opts)
        mon._last_t = data["last_t"]
        mon._last_used = data["last_used"]
        mon._calibration = [(float(d), float(s)) for d, s in data["calibration"]]
        if data["scheduler"] is not None:
            mon._scheduler = MonitoringScheduler.from_dict(data["scheduler"])
        counts = data["counts"]
        mon._counts = _Counts(counts["checks"], counts["alarms"], counts["redistributions"])
        return mon


class FleetMonitor:
    """Monitor of several VMs with a shared risk budget.

    Each VM gets its own ``c``, detector and interval. If ``n_vms`` machines share
    the risk, each one uses ``delta / n_vms`` and ``alpha / n_vms``. By Boole's
    inequality the probability that any VM exhausts its reserve before its next
    check is then at most ``delta`` (section 4 of the article).

    Parameters
    ----------
    n_vms : int, default 1
        Number of VMs over which ``delta`` and ``alpha`` are shared.
    **options
        Options of :class:`VmMonitor`; ``delta`` and ``alpha`` are the fleet
        totals and are divided by ``n_vms``.

    Examples
    --------
    >>> fleet = FleetMonitor(n_vms=2, c=20.0)
    >>> _ = fleet.record_measurement("vm-1", 0.0, used=1000.0, free=500.0)
    >>> fleet.monitor("vm-1").calibrated
    True
    >>> round(fleet.monitor("vm-1").next_check_time)
    1
    """

    def __init__(self, *, n_vms: int = 1, **options: Any) -> None:
        if n_vms < 1:
            msg = f"n_vms must be at least 1, got {n_vms!r}"
            raise ValueError(msg)
        delta = float(options.pop("delta", 0.01))
        alpha = float(options.pop("alpha", 0.01))
        check_level("delta", delta)
        check_level("alpha", alpha)
        self._n_vms = n_vms
        self._fleet_delta = delta
        self._fleet_alpha = alpha
        self._options: dict[str, Any] = options
        self._monitors: dict[str, VmMonitor] = {}

    @property
    def names(self) -> list[str]:
        """Identifiers of the monitored VMs, in the order of addition."""
        return list(self._monitors)

    def __len__(self) -> int:
        """Return the number of monitored VMs."""
        return len(self._monitors)

    def __iter__(self) -> Iterator[str]:
        """Return an iterator over the VM names."""
        return iter(self._monitors)

    def __contains__(self, name: object) -> bool:
        """Return whether a VM is monitored."""
        return name in self._monitors

    def _vm_options(self, c: float | None) -> dict[str, Any]:
        opts = dict(self._options)
        opts["delta"] = self._fleet_delta / self._n_vms
        opts["alpha"] = self._fleet_alpha / self._n_vms
        opts["c"] = c if c is not None else opts.get("c")
        return opts

    def add(self, name: str, c: float | None = None) -> VmMonitor:
        """Register a VM. Raises ``ValueError`` if it is already known."""
        if name in self._monitors:
            msg = f"VM {name!r} is already monitored"
            raise ValueError(msg)
        mon = VmMonitor(name, **self._vm_options(c))
        self._monitors[name] = mon
        return mon

    def monitor(self, name: str) -> VmMonitor:
        """Return the monitor of a VM. Raises ``KeyError`` for an unknown name."""
        return self._monitors[name]

    def record_measurement(self, vm: str, t: float, used: float, free: float) -> Decision:
        """Record one measurement of VM ``vm``, registering the VM on its first measurement."""
        mon = self._monitors.get(vm)
        if mon is None:
            validate_measurement(t, used, free)  # refuse a bad first reading before registering
            mon = self.add(vm)
        return mon.record_measurement(t, used, free)

    def due(self, t: float) -> list[str]:
        """Return the names of the VMs that should be read at time ``t``."""
        return [name for name, mon in self._monitors.items() if mon.due(t)]

    def to_dict(self) -> dict[str, Any]:
        """Return the fleet options and the state of every VM as JSON-serialisable values."""
        return {
            "n_vms": self._n_vms,
            "delta": self._fleet_delta,
            "alpha": self._fleet_alpha,
            "options": dict(self._options),
            "vms": [mon.to_dict() for mon in self._monitors.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Rebuild the fleet from :meth:`to_dict` output."""
        fleet = cls(
            n_vms=int(data["n_vms"]),
            delta=float(data["delta"]),
            alpha=float(data["alpha"]),
            **data["options"],
        )
        for item in data["vms"]:
            mon = VmMonitor.from_dict(item)
            fleet._monitors[mon.name] = mon
        return fleet
