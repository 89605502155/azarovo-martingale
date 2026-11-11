"""Trace plot of one VM for the log analysis. Needs the ``plot`` extra (matplotlib)."""

from __future__ import annotations

from bisect import bisect_left
from pathlib import Path

from .analysis import VmReport
from .logs import VmLog

__all__ = ["plot_trace"]


def plot_trace(path: str | Path, vm: VmLog, report: VmReport) -> Path:
    """Draw the memory use, the reserve, the growth periods and the checks of one VM.

    Parameters
    ----------
    path : str or Path
        Output image file; the format follows the suffix (``.png``, ``.pdf``, ...).
    vm : VmLog
        The samples of the VM from the log.
    report : VmReport
        Its analysis; the test part starts at ``report.test_start``.

    Returns
    -------
    Path
        The path that was written.

    Raises
    ------
    ImportError
        If matplotlib is not installed; install ``azarovo-martingale[plot]``.
    ValueError
        If the VM was skipped in the analysis and has no test part.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on the environment
        msg = "plots need matplotlib: install azarovo-martingale[plot]"
        raise ImportError(msg) from exc
    if report.skipped is not None or report.guarantee is None:
        msg = f"VM {vm.name} has no test part to plot"
        raise ValueError(msg)

    i0 = bisect_left(vm.time, report.test_start)
    t = vm.time[i0:]
    x0 = t[0]
    minutes = [(x - x0) / 60.0 for x in t]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(minutes, vm.used[i0:], color="#2a78d6", lw=1.0, label="memory use")
    ax.plot(minutes, vm.free[i0:], color="#898781", lw=1.0, label="reserve R")
    if vm.growth:
        growth = vm.growth[i0:]
        first = True
        k = 0
        while k < len(growth):
            if not growth[k]:
                k += 1
                continue
            a = k
            while k < len(growth) and growth[k]:
                k += 1
            lo = minutes[max(a - 1, 0)]
            hi = minutes[k - 1]
            ax.axvspan(
                lo,
                hi,
                color="#eb6834",
                alpha=0.18,
                lw=0,
                label="growth (phase column)" if first else None,
            )
            first = False
    by_kind = {rp.kind: rp for rp in report.replay}
    tr = ax.get_xaxis_transform()
    ville = by_kind.get("ville")
    if ville is not None:
        checks = [(x - x0) / 60.0 for x in ville.check_times]
        ax.vlines(checks, 0, 0.04, transform=tr, color="#52514e", lw=0.5, label="checks (Fig. 3)")
        if ville.redistribution_times:
            red = [(x - x0) / 60.0 for x in ville.redistribution_times]
            ax.vlines(
                red,
                0.5,
                1,
                transform=tr,
                color="#d03b3b",
                lw=0.8,
                ls="--",
                label="redistribution (Fig. 3)",
            )
    cusum = by_kind.get("cusum")
    if cusum is not None and cusum.redistribution_times:
        red = [(x - x0) / 60.0 for x in cusum.redistribution_times]
        ax.vlines(
            red, 0, 0.5, transform=tr, color="#7a3db8", lw=0.8, ls=":", label="redistribution (14)"
        )
    ax.set_xlabel("time from the start of the test part, min")
    ax.set_ylabel("MiB")
    ax.set_title(f"VM {vm.name}")
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False)
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out
