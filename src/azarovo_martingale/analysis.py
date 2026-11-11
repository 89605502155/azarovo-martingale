"""Analysis of a monitoring log.

Checks of assumptions A1 and A2, the guarantee (6), the detectors, and a replay of
the monitoring policies.

The analysis answers the questions the article leaves to real data. Does the
largest change ``c`` hold (A1)? Is the calm use free of drift (A2)? Does the
interval (9) keep the exhaustion risk below ``delta`` (6)? How many false alarms
and how long a delay does each detector have? And how do the policies compare
in the number of checks and the number of exhausted intervals?

The replay does not feed back the effect of redistribution on the later data.
"""

from __future__ import annotations

import math
from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any, ClassVar, cast

from ._checks import check_bet, check_level, check_positive
from .detectors import (
    CusumGrowthDetector,
    GrowthDetector,
    GrowthTest,
    MixtureGrowthDetector,
)
from .estimate import estimate_c
from .interval import monitoring_interval
from .logs import MonitoringLog, VmLog
from .scheduler import DetectorKind, MonitoringScheduler

__all__ = [
    "AnalysisOptions",
    "DetectorSummary",
    "GrowthSegment",
    "GuaranteeCheck",
    "PolicyReplay",
    "VmReport",
    "analyse_log",
    "render_markdown",
    "report_to_dict",
]

MIN_SAMPLES = 20
"""Logs of a VM with fewer samples are skipped."""


@dataclass(frozen=True)
class AnalysisOptions:
    """Options of :func:`analyse_log`. Names follow the command-line options of the CLI.

    Parameters
    ----------
    step : float, default 1.0
        Base step in the unit of the timestamps (seconds in the article).
    delta, alpha, lam : float
        Risk, false-alarm level and betting fraction, as in :class:`MonitoringScheduler`.
    n_min, n_max : int, n_max may be None
        Interval after a redistribution and upper bound of the interval, base steps.
    fixed : tuple of int
        Fixed intervals to compare with, base steps.
    c : float, optional
        Fixed ``c``; if given, the whole log is tested with it.
    train_frac : float, default 0.5
        Share of the beginning of each log used to estimate ``c``; 0 uses the whole log.
    c_quantile, c_margin : float
        Parameters of :func:`~azarovo_martingale.estimate_c`.
    reserve : float, optional
        Constant reserve in MiB, used when the log has no ``free_mb`` column.
    cusum_threshold : float
        Level of the CUSUM-type detector (14).
    grace : float, default 60.0
        Seconds after the end of a growth period during which an alarm still counts
        as a detection rather than a false alarm.
    split_risk : bool
        Share ``delta`` and ``alpha`` evenly between the VMs (Boole's inequality).
    """

    step: float = 1.0
    delta: float = 0.01
    alpha: float = 0.01
    lam: float = 0.5
    n_min: int = 1
    n_max: int | None = 600
    fixed: tuple[int, ...] = (1, 5, 10)
    c: float | None = None
    train_frac: float = 0.5
    c_quantile: float = 1.0
    c_margin: float = 1.2
    reserve: float | None = None
    cusum_threshold: float = 1e5
    grace: float = 60.0
    split_risk: bool = False

    def __post_init__(self) -> None:
        """Check the parameters."""
        check_positive("step", self.step)
        check_level("delta", self.delta)
        check_level("alpha", self.alpha)
        check_bet("lam", self.lam)
        if self.n_min < 1 or (self.n_max is not None and self.n_max < self.n_min):
            msg = "n_min must be at least 1 and n_max at least n_min"
            raise ValueError(msg)
        if any(n < 1 for n in self.fixed):
            msg = "fixed intervals must be at least 1 base step"
            raise ValueError(msg)
        if not 0.0 <= self.train_frac < 1.0:
            msg = "train_frac must lie in [0, 1)"
            raise ValueError(msg)
        if not self.cusum_threshold > 1.0:
            msg = "cusum_threshold must be above 1"
            raise ValueError(msg)
        if not 0.0 < self.c_quantile <= 1.0 or not self.c_margin >= 1.0:
            msg = "c_quantile must lie in (0, 1] and c_margin must be at least 1"
            raise ValueError(msg)


# ------------------------------------------------------------------ results
@dataclass
class GuaranteeCheck:
    """Empirical check of the guarantee (6) for the interval (9).

    Attributes
    ----------
    starts : int
        Starting moments whose window lies in the test part and in calm use.
    small_reserve : int
        Samples with ``R <= c``, where the memory must be redistributed at once.
    mean_interval_s : float
        Mean interval (9) over the counted starts, in seconds.
    exhausted : int
        Windows in which the use rose by ``R`` or more.
    share : float
        ``exhausted / starts``; it should not exceed ``delta``.
    """

    starts: int
    small_reserve: int
    mean_interval_s: float
    exhausted: int
    share: float


@dataclass
class GrowthSegment:
    """Detection of one labelled growth period.

    ``delay_s`` maps a detector name to the seconds from the onset to its first
    alarm within the period and the grace time, or ``None`` if there was none.
    """

    start_s: float
    duration_s: float
    rise_mb: float
    delay_s: dict[str, float | None]


@dataclass
class DetectorSummary:
    """Behaviour of the detectors on the test part of a log.

    ``alarms`` counts the alarms of a continuous run with restarts only after an
    alarm. The false-alarm figures are present only when the log has a ``phase``
    column. ``cusum_bound_per_hour`` is the calibration target ``3600 / (A step)``.
    """

    hours: float
    alarms: dict[str, int]
    cusum_bound_per_hour: float
    calm_hours: float | None = None
    false_alarms: dict[str, int] | None = None
    false_alarms_per_hour: dict[str, float | None] | None = None
    calm_segments: int | None = None
    calm_segments_with_alarm: int | None = None
    growth_segments: list[GrowthSegment] = field(default_factory=list)


@dataclass
class PolicyReplay:
    """Replay of one monitoring policy on the test part of a log.

    ``kind`` identifies the policy (``ville``, ``cusum``, ``subgaussian``,
    ``mixture`` or ``fixed-<n>``). ``redistributions`` is ``None`` for fixed policies.
    """

    kind: str
    policy: str
    checks: int
    checks_per_hour: float
    mean_interval_s: float
    exhausted: int
    share: float
    redistributions: int | None
    redistribution_times: list[float]
    check_times: list[float]


@dataclass
class VmReport:
    """Analysis of one VM. A VM with too few samples has only ``skipped`` set."""

    vm: str
    skipped: str | None = None
    samples: int = 0
    test_samples: int = 0
    duplicates: int = 0
    delta: float = math.nan
    alpha: float = math.nan
    c: float = math.nan
    c_source: str = ""
    test_start: float = math.nan
    test_end: float = math.nan
    a1_share_above_c: float = math.nan
    a1_max_rate: float = math.nan
    a2_mean_calm_rate: float = math.nan
    a2_lag1_autocorr: float = math.nan
    guarantee: GuaranteeCheck | None = None
    detector: DetectorSummary | None = None
    replay: list[PolicyReplay] = field(default_factory=list)


# ------------------------------------------------------------ helpers
class _RangeMax:
    """Maximum over a range of an array, O(1) per query after O(N log N) preparation."""

    def __init__(self, a: Sequence[float]) -> None:
        self.levels: list[array[float]] = [array("d", a)]
        k = 1
        while (1 << k) <= len(a):
            prev = self.levels[-1]
            half = 1 << (k - 1)
            self.levels.append(array("d", map(max, prev[:-half], prev[half:])))
            k += 1

    def query(self, lo: int, hi: int) -> float:
        """Return the maximum of ``a[lo..hi]``, both ends included."""
        k = (hi - lo + 1).bit_length() - 1
        lev = self.levels[k]
        return max(lev[lo], lev[hi - (1 << k) + 1])


def _segments(flags: Sequence[bool]) -> list[tuple[int, int, bool]]:
    """Split flags into runs of equal value as ``(start, end, flag)``; ``end`` is excluded."""
    out: list[tuple[int, int, bool]] = []
    if not flags:
        return out
    start = 0
    for k in range(1, len(flags) + 1):
        if k == len(flags) or flags[k] != flags[start]:
            out.append((start, k, bool(flags[start])))
            start = k
    return out


def _run(
    time: Sequence[float],
    used: Sequence[float],
    det: GrowthTest,
    step: float,
    start: int,
    stop: int,
) -> list[int]:
    """Alarms of a detector over samples ``start .. stop-1``, restarted after each alarm."""
    det.reset()
    alarms: list[int] = []
    for k in range(start + 1, stop):
        if det.update(used[k] - used[k - 1], (time[k] - time[k - 1]) / step):
            alarms.append(k)
            det.reset()
    return alarms


def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n < 3:
        return math.nan
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0.0 or syy == 0.0:
        return math.nan
    return sxy / math.sqrt(sxx * syy)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else math.nan


# ----------------------------------------------------------- the guarantee (6)
def _check_guarantee(
    time: Sequence[float],
    used: Sequence[float],
    free: Sequence[float],
    growth: Sequence[bool] | None,
    c: float,
    o: AnalysisOptions,
) -> GuaranteeCheck:
    """Empirical check of (6) for the interval (9).

    For each sample ``i`` the interval ``n_i`` is computed from the reserve ``R_i``,
    and the window ``(t_i, t_i + n_i step]`` is inspected: did the use rise by
    ``R_i`` or more? Only windows inside the log and inside calm use are counted.
    Windows overlap, so the share is a point estimate without a confidence interval.
    """
    n_samples = len(time)
    intervals = [monitoring_interval(r, c, o.delta, o.n_max) for r in free]
    growth_prefix = [0] * (n_samples + 1)
    if growth is not None:
        for k, g in enumerate(growth):
            growth_prefix[k + 1] = growth_prefix[k] + int(g)
    rmax = _RangeMax(used)
    starts = exhausted = 0
    interval_sum = 0.0
    for i, n in enumerate(intervals):
        if n <= 0:
            continue
        end = time[i] + n * o.step
        if end > time[-1]:
            continue
        j = bisect_right(time, end + 1e-9 * o.step) - 1
        if j <= i:
            continue
        if growth is not None and growth_prefix[j + 1] - growth_prefix[i] != 0:
            continue
        starts += 1
        interval_sum += n * o.step
        if rmax.query(i + 1, j) - used[i] >= free[i]:
            exhausted += 1
    small = sum(1 for n in intervals if n == 0)
    return GuaranteeCheck(
        starts=starts,
        small_reserve=small,
        mean_interval_s=interval_sum / starts if starts else math.nan,
        exhausted=exhausted,
        share=exhausted / starts if starts else math.nan,
    )


# ------------------------------------------------------------ detectors
_DETECTOR_NAMES = ("ville", "cusum", "mixture")


def _make_detector(name: str, c: float, o: AnalysisOptions) -> GrowthTest:
    if name == "ville":
        return GrowthDetector(c, o.lam, o.alpha)
    if name == "cusum":
        return CusumGrowthDetector(c, o.lam, o.cusum_threshold)
    return MixtureGrowthDetector(c, o.alpha)


def _evaluate_detectors(
    time: Sequence[float],
    used: Sequence[float],
    growth: Sequence[bool] | None,
    c: float,
    o: AnalysisOptions,
) -> DetectorSummary:
    """Alarms, false alarms and delays of the detectors on the test part."""
    n_samples = len(time)
    hours = (time[-1] - time[0]) / 3600.0
    cusum_bound = 3600.0 / (o.cusum_threshold * o.step)
    cont = {
        name: _run(time, used, _make_detector(name, c, o), o.step, 0, n_samples)
        for name in _DETECTOR_NAMES
    }
    alarms = {name: len(cont[name]) for name in _DETECTOR_NAMES}
    if growth is None:
        return DetectorSummary(hours=hours, alarms=alarms, cusum_bound_per_hour=cusum_bound)

    segs = _segments(growth)
    protected = list(growth)  # samples within the grace time after a growth period
    for _a, b, is_growth in segs:
        if is_growth:
            t_end = time[b - 1]
            lo = bisect_right(time, t_end)
            hi = bisect_right(time, t_end + o.grace)
            for k in range(lo, hi):
                protected[k] = True
    calm = [not p for p in protected]
    calm_hours = sum(time[k] - time[k - 1] for k in range(1, n_samples) if calm[k]) / 3600.0

    def in_calm(alarm_list: list[int]) -> int:
        return sum(1 for k in alarm_list if calm[k])

    growth_rows: list[GrowthSegment] = []
    for a, b, is_growth in segs:
        if not is_growth:
            continue
        onset = max(a - 1, 0)
        stop = bisect_right(time, time[b - 1] + o.grace)
        own = _run(time, used, _make_detector("ville", c, o), o.step, onset, stop)
        delays: dict[str, float | None] = {}
        candidates = {
            "ville_continuous": cont["ville"],
            "cusum": cont["cusum"],
            "mixture": cont["mixture"],
        }
        for label, al in candidates.items():
            hit = next((k for k in al if a <= k < stop), None)
            delays[label] = None if hit is None else float(time[hit] - time[onset])
        delays["ville_restart"] = None if not own else float(time[own[0]] - time[onset])
        growth_rows.append(
            GrowthSegment(
                start_s=float(time[onset]),
                duration_s=float(time[b - 1] - time[onset]),
                rise_mb=float(used[b - 1] - used[onset]),
                delay_s=delays,
            )
        )

    calm_segs = [(a, b) for a, b, flag in _segments(calm) if flag]
    with_alarm = sum(
        1
        for a, b in calm_segs
        if _run(time, used, _make_detector("ville", c, o), o.step, max(a - 1, 0), b)
    )
    false_alarms = {name: in_calm(cont[name]) for name in _DETECTOR_NAMES}
    per_hour: dict[str, float | None] = {
        name: (false_alarms[name] / calm_hours if calm_hours > 0 else None)
        for name in _DETECTOR_NAMES
    }
    return DetectorSummary(
        hours=hours,
        alarms=alarms,
        cusum_bound_per_hour=cusum_bound,
        calm_hours=calm_hours,
        false_alarms=false_alarms,
        false_alarms_per_hour=per_hour,
        calm_segments=len(calm_segs),
        calm_segments_with_alarm=with_alarm,
        growth_segments=growth_rows,
    )


# ------------------------------------------------------------- policies
class _SchedulerPolicy:
    """The joint algorithm of Fig. 3 with one of the detectors."""

    _LABELS: ClassVar[dict[str, str]] = {
        "ville": "martingale (Fig. 3)",
        "cusum": "martingale, detector (14)",
        "subgaussian": "martingale, sub-Gaussian bets (addition)",
        "mixture": "martingale, mixture of bets (addition)",
    }

    def __init__(self, c: float, kind: str, o: AnalysisOptions) -> None:
        self.kind = kind
        self.label = self._LABELS[kind]
        self.sched = MonitoringScheduler(
            c=c,
            delta=o.delta,
            alpha=o.alpha,
            lam=o.lam,
            n_min=o.n_min,
            n_max=o.n_max,
            kind=cast("DetectorKind", kind),
            cusum_threshold=o.cusum_threshold,
        )

    def first(self) -> int:
        return self.sched.interval

    def next(self, dx: float, n_elapsed: float, reserve: float) -> tuple[int, bool]:
        decision = self.sched.step(dx, reserve, n_elapsed)
        return decision.interval, decision.redistribute


class _FixedPolicy:
    """A fixed interval in base steps."""

    def __init__(self, n: int) -> None:
        self.kind = f"fixed-{n}"
        self.label = f"fixed, {n} step(s)"
        self._n = n

    def first(self) -> int:
        return self._n

    def next(self, dx: float, n_elapsed: float, reserve: float) -> tuple[int, bool]:
        del dx, n_elapsed, reserve
        return self._n, False


def _replay(
    time: Sequence[float],
    used: Sequence[float],
    free: Sequence[float],
    policy: _SchedulerPolicy | _FixedPolicy,
    step: float,
) -> PolicyReplay:
    """Replay a policy on the logged data, without feedback from redistribution."""
    n_samples = len(time)
    i = 0
    n = policy.first()
    checks = exhausted = redistributions = 0
    elapsed = 0.0
    check_times: list[float] = []
    redistribution_times: list[float] = []
    while True:
        j = bisect_left(time, time[i] + n * step - 1e-9 * step)
        if j >= n_samples:
            break
        j = max(j, i + 1)
        if max(used[i + 1 : j + 1]) - used[i] >= free[i]:
            exhausted += 1
        n_elapsed = (time[j] - time[i]) / step
        next_n, flag = policy.next(used[j] - used[i], n_elapsed, free[j])
        n = max(int(next_n), 1)
        checks += 1
        elapsed += n_elapsed
        check_times.append(float(time[j]))
        if flag:
            redistributions += 1
            redistribution_times.append(float(time[j]))
        i = j
    hours = elapsed * step / 3600.0
    is_scheduler = isinstance(policy, _SchedulerPolicy)
    return PolicyReplay(
        kind=policy.kind,
        policy=policy.label,
        checks=checks,
        checks_per_hour=checks / hours if hours > 0 else math.nan,
        mean_interval_s=elapsed * step / checks if checks else math.nan,
        exhausted=exhausted,
        share=exhausted / checks if checks else math.nan,
        redistributions=redistributions if is_scheduler else None,
        redistribution_times=redistribution_times,
        check_times=check_times,
    )


# -------------------------------------------------------------- per VM
def _analyse_vm(vm: VmLog, o: AnalysisOptions, has_free: bool, has_phase: bool) -> VmReport:
    report = VmReport(
        vm=vm.name, samples=len(vm), duplicates=vm.duplicates, delta=o.delta, alpha=o.alpha
    )
    if len(vm) < MIN_SAMPLES:
        report.skipped = f"fewer than {MIN_SAMPLES} samples"
        return report
    if has_free:
        free_all = list(vm.free)
    elif o.reserve is not None:
        free_all = [float(o.reserve)] * len(vm)
    else:
        msg = "the log has no free_mb column: give a constant reserve"
        raise ValueError(msg)
    if any(math.isnan(x) for x in free_all):
        report.skipped = "empty values in free_mb"
        return report

    time_all, used_all = vm.time, vm.used
    if o.c is not None:
        c, c_source, i0 = float(o.c), "given by --c", 0
    elif o.train_frac > 0:
        t_split = time_all[0] + o.train_frac * (time_all[-1] - time_all[0])
        i0 = bisect_left(time_all, t_split)
        if i0 < 3 or len(time_all) - i0 < MIN_SAMPLES:
            report.skipped = "log too short for the train_frac split"
            return report
        c_source = f"estimated from the first {o.train_frac:.0%} of the log"
    else:
        i0 = 0
        c_source = "estimated from the whole log, checked on the same data"
    if o.c is None:
        stop = i0 if o.train_frac > 0 else len(time_all)
        steps_ = [(time_all[k] - time_all[k - 1]) / o.step for k in range(1, stop)]
        deltas = [used_all[k] - used_all[k - 1] for k in range(1, stop)]
        try:
            c = estimate_c(deltas, steps_, quantile=o.c_quantile, margin=o.c_margin)
        except ValueError as exc:
            report.skipped = f"c cannot be estimated: {exc}"
            return report

    time, used, free = time_all[i0:], used_all[i0:], free_all[i0:]
    growth = list(vm.growth[i0:]) if has_phase else None
    n_test = len(time)
    rates = [
        (used[k + 1] - used[k]) / ((time[k + 1] - time[k]) / o.step) for k in range(n_test - 1)
    ]
    calm_inc = [True] * len(rates) if growth is None else [not g for g in growth[1:]]
    calm_rates = [r for r, ok in zip(rates, calm_inc, strict=True) if ok]
    both = [calm_inc[k] and calm_inc[k + 1] for k in range(len(rates) - 1)]
    xs = [rates[k] for k in range(len(rates) - 1) if both[k]]
    ys = [rates[k + 1] for k in range(len(rates) - 1) if both[k]]

    report.test_samples = n_test
    report.c = float(c)
    report.c_source = c_source
    report.test_start = float(time[0])
    report.test_end = float(time[-1])
    report.a1_share_above_c = sum(1 for r in rates if abs(r) > c) / len(rates)
    report.a1_max_rate = max(abs(r) for r in rates)
    report.a2_mean_calm_rate = _mean(calm_rates)
    report.a2_lag1_autocorr = _pearson(xs, ys)
    report.guarantee = _check_guarantee(time, used, free, growth, c, o)
    report.detector = _evaluate_detectors(time, used, growth, c, o)
    policies: list[_SchedulerPolicy | _FixedPolicy] = [
        _SchedulerPolicy(c, kind, o) for kind in ("ville", "cusum", "subgaussian", "mixture")
    ]
    policies += [_FixedPolicy(n) for n in o.fixed]
    report.replay = [_replay(time, used, free, p, o.step) for p in policies]
    return report


def analyse_log(log: MonitoringLog, options: AnalysisOptions | None = None) -> list[VmReport]:
    """Analyse every VM of a monitoring log.

    Parameters
    ----------
    log : MonitoringLog
        The parsed log, see :func:`~azarovo_martingale.read_log`.
    options : AnalysisOptions, optional
        Analysis options; defaults are those of the article.

    Returns
    -------
    list of VmReport
        One report per VM, sorted by name. With ``split_risk`` the reports carry the
        shared ``delta`` and ``alpha``.

    Examples
    --------
    >>> from azarovo_martingale import MonitoringLog, VmLog
    >>> vm = VmLog(
    ...     "vm-1",
    ...     time=[float(t) for t in range(30)],
    ...     used=[1000.0 + 2.0 * (t % 3) for t in range(30)],
    ...     free=[500.0] * 30,
    ...     growth=[False] * 30,
    ... )
    >>> reports = analyse_log(
    ...     MonitoringLog({"vm-1": vm}, has_free=True, has_phase=True),
    ...     AnalysisOptions(c=10.0, train_frac=0.0),
    ... )
    >>> reports[0].vm, reports[0].skipped
    ('vm-1', None)
    """
    o = AnalysisOptions() if options is None else options
    if o.split_risk and len(log.vms) > 1:
        m = len(log.vms)
        o = replace(o, delta=o.delta / m, alpha=o.alpha / m)
    return [_analyse_vm(log.vms[name], o, log.has_free, log.has_phase) for name in sorted(log.vms)]


# -------------------------------------------------------------- output
def _fmt(x: float | None, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{digits}f}"


def _pct(x: float | None, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{100.0 * x:.{digits}f}"


def render_markdown(
    reports: Sequence[VmReport],
    options: AnalysisOptions,
    *,
    log_name: str = "log",
    has_phase: bool = True,
) -> str:
    """Return the analysis as a Markdown report with one section per VM."""
    lines = [f"# Analysis of the monitoring log {log_name}", ""]
    lines.append(
        f"Parameters: base step {options.step:g} s, delta = {options.delta:g}, "
        f"alpha = {options.alpha:g}, lam = {options.lam:g}, n_min = {options.n_min}, "
        f"n_max = {options.n_max}."
    )
    if options.c is None:
        lines.append(
            f"Estimate of c: quantile {options.c_quantile:g} of the rates |dx| per step, "
            f"safety margin {options.c_margin:g}."
        )
    if options.split_risk:
        lines.append(
            "Risks delta and alpha are shared evenly between the VMs (Boole's inequality)."
        )
    if not has_phase:
        lines.append(
            "The log has no phase column: false alarms and detection delays are not estimated."
        )
    lines += [
        "",
        (
            "How to read. The share of exhausted windows should not exceed delta. The share of "
            "calm segments with an alarm of detector (11), (12) should not exceed alpha. The "
            "false alarms per hour of the detector (14) should stay below 3600/(A step). If "
            "they do not, check assumptions A1 and A2: the share of increments above c, the "
            "mean increment and its autocorrelation in calm use. The sub-Gaussian and mixture "
            "policies are additions, not in the text of the article."
        ),
        "",
    ]
    totals: dict[str, list[int]] = {}
    for rep in reports:
        lines.append(f"## VM {rep.vm}")
        lines.append("")
        if rep.skipped is not None:
            lines += [f"Skipped: {rep.skipped}.", ""]
            continue
        lines.append(
            f"Samples: {rep.samples}, in the test part: {rep.test_samples} "
            f"(from {_fmt(rep.test_start, 0)} to {_fmt(rep.test_end, 0)} s). "
            f"c = {_fmt(rep.c)} MiB per step ({rep.c_source})."
        )
        if rep.duplicates:
            lines.append(f"Dropped samples with a repeated time: {rep.duplicates}.")
        lines.append("")
        lines.append(
            f"Assumption A1: the rate |dx| exceeds c for {_pct(rep.a1_share_above_c)} % of "
            f"the increments; the largest rate is {_fmt(rep.a1_max_rate)} MiB per step."
        )
        lines.append(
            f"Assumption A2: the mean increment in calm use is "
            f"{_fmt(rep.a2_mean_calm_rate, 3)} MiB per step, the lag-1 autocorrelation of "
            f"the increments is {_fmt(rep.a2_lag1_autocorr, 3)}."
        )
        lines.append("")
        gu = rep.guarantee
        if gu is not None:
            lines += [
                "### Guarantee (6) for the interval (9)",
                "",
                "| Starts | Mean interval, s | Exhausted windows | Share, % | delta, % |",
                "|---|---|---|---|---|",
                (
                    f"| {gu.starts} | {_fmt(gu.mean_interval_s)} | {gu.exhausted} | "
                    f"{_pct(gu.share, 3)} | {_pct(options.delta)} |"
                ),
                "",
            ]
            if gu.small_reserve:
                lines += [
                    f"Samples with R <= c (redistribute at once): {gu.small_reserve}.",
                    "",
                ]
        det = rep.detector
        if det is not None:
            lines += ["### Growth detectors", ""]
            lines.append(
                f"Alarms in continuous operation, restarted after each alarm, over "
                f"{_fmt(det.hours, 2)} h: detector (11), (12) - {det.alarms['ville']}, "
                f"detector (14) with threshold {options.cusum_threshold:g} - "
                f"{det.alarms['cusum']}, mixture of bets (addition) - {det.alarms['mixture']}."
            )
            if det.calm_hours is not None and det.false_alarms is not None:
                per = det.false_alarms_per_hour or {}
                lines.append(
                    f"False alarms in calm use ({_fmt(det.calm_hours, 2)} h): detector "
                    f"(11), (12) - {det.false_alarms['ville']} "
                    f"({_fmt(per.get('ville'), 2)} per hour), detector (14) - "
                    f"{det.false_alarms['cusum']} ({_fmt(per.get('cusum'), 2)} per hour, "
                    f"target at most {_fmt(det.cusum_bound_per_hour, 3)} per hour), mixture "
                    f"(addition) - {det.false_alarms['mixture']} "
                    f"({_fmt(per.get('mixture'), 2)} per hour)."
                )
                n_segments = det.calm_segments or 0
                with_alarm = det.calm_segments_with_alarm or 0
                share = with_alarm / n_segments if n_segments else math.nan
                lines.append(
                    f"Calm segments: {det.calm_segments}, of them with an alarm of detector "
                    f"(11), (12) started with K = 1: {det.calm_segments_with_alarm} "
                    f"({_pct(share)} %, alpha = {_pct(options.alpha)} %)."
                )
            if det.growth_segments:
                lines += [
                    "",
                    "Detection delay of growth, s:",
                    "",
                    (
                        "| Onset, s | Duration, s | Rise, MiB | (11), (12) continuous | "
                        "(11), (12) from K = 1 | (14) continuous | mixture (addition) |"
                    ),
                    "|---|---|---|---|---|---|---|",
                ]
                for row in det.growth_segments:
                    d = row.delay_s
                    lines.append(
                        f"| {_fmt(row.start_s, 0)} | {_fmt(row.duration_s, 0)} | "
                        f"{_fmt(row.rise_mb, 0)} | {_fmt(d.get('ville_continuous'), 0)} | "
                        f"{_fmt(d.get('ville_restart'), 0)} | {_fmt(d.get('cusum'), 0)} | "
                        f"{_fmt(d.get('mixture'), 0)} |"
                    )
                lines.append("")
                lines.append(
                    "A dash means that the growth was not detected within the period and "
                    f"{options.grace:g} s after it."
                )
        lines += [
            "",
            "### Comparison of monitoring policies",
            "",
            (
                "Replay of the log without feedback: the effect of redistribution on the data "
                "is not modelled."
            ),
            "",
            (
                "| Policy | Checks | Checks per hour | Mean interval, s | Exhausted intervals | "
                "Share, % | Redistributions |"
            ),
            "|---|---|---|---|---|---|---|",
        ]
        for rp in rep.replay:
            lines.append(
                f"| {rp.policy} | {rp.checks} | {_fmt(rp.checks_per_hour)} | "
                f"{_fmt(rp.mean_interval_s)} | {rp.exhausted} | {_pct(rp.share)} | "
                f"{_fmt(rp.redistributions) if rp.redistributions is not None else '-'} |"
            )
            tot = totals.setdefault(rp.policy, [0, 0])
            tot[0] += rp.checks
            tot[1] += rp.exhausted
        lines.append("")
    done = [r for r in reports if r.skipped is None]
    if len(done) > 1 and totals:
        lines += [
            "## Total over all VMs",
            "",
            "| Policy | Checks | Exhausted intervals | Share, % |",
            "|---|---|---|---|",
        ]
        for name, (checks, exhausted) in totals.items():
            share = exhausted / checks if checks else math.nan
            lines.append(f"| {name} | {checks} | {exhausted} | {_pct(share)} |")
        lines.append("")
    return "\n".join(lines)


def _json_safe(obj: Any) -> Any:
    """Replace NaN and infinity by ``None`` so that the output is valid JSON."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def report_to_dict(reports: Sequence[VmReport], options: AnalysisOptions) -> dict[str, Any]:
    """Return the options and the reports as JSON-serialisable data, without check times."""
    vms = []
    for rep in reports:
        data = asdict(rep)
        for rp in data["replay"]:
            rp.pop("check_times", None)
        vms.append(data)
    result: dict[str, Any] = _json_safe({"options": asdict(options), "vms": vms})
    return result
