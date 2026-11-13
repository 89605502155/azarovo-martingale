"""Replay of monitoring logs with a given calibration window ``warmup``.

One row per VM and log: the time of the calibration (the ``warmup``-th increment),
the estimated ``c``, the number of checks, alarms and redistributions, and the
number of alarms that fall in a period marked ``growth`` (column ``phase``).
The replay feeds the monitor only at the moments it asks for (``due``), as a
controller does. Used for the planned series with windows 20 and 50 (the article,
section 5). Without the ``free_mb`` column pass ``--reserve``.

Usage (from the repository root):
    .venv/bin/python experiments/window_series.py LOG.csv [LOG2.csv ...] --warmup 20 --out OUT.csv
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from azarovo_martingale import VmMonitor, read_log


def replay(
    path: Path, warmup: int, delta: float, alpha: float, reserve: float | None
) -> list[dict]:
    log = read_log(path)
    if not log.has_free and reserve is None:
        msg = f"{path}: no free_mb column, pass --reserve"
        raise SystemExit(msg)
    rows = []
    for name, vm in log.vms.items():
        mon = VmMonitor(name, warmup=warmup, delta=delta, alpha=alpha)
        calibrated_at = None
        growth_alarms = 0
        for i, (t, used) in enumerate(zip(vm.time, vm.used, strict=True)):
            if not mon.due(t):
                continue
            free = vm.free[i] if log.has_free else float(reserve)
            if math.isnan(free):
                free = float(reserve)
            free = max(free, 0.0)  # an exhausted reserve is logged as negative, it is zero here
            decision = mon.record_measurement(t, used, free)
            if decision.calibrated and calibrated_at is None:
                calibrated_at = t
            if decision.alarm and vm.growth[i]:
                growth_alarms += 1
        rows.append(
            {
                "log": str(path),
                "vm": name,
                "warmup": warmup,
                "samples": len(vm),
                "calibration_time_s": "" if calibrated_at is None else calibrated_at,
                "c": "" if mon.c is None else f"{mon.c:.6g}",
                "checks": mon.checks,
                "alarms": mon.alarms,
                "alarms_in_growth": growth_alarms,
                "redistributions": mon.redistributions,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("logs", nargs="+", type=Path, help="monitoring logs (CSV)")
    parser.add_argument("--warmup", type=int, default=50, help="calibration window (default 50)")
    parser.add_argument("--delta", type=float, default=0.01)
    parser.add_argument("--alpha", type=float, default=0.01)
    parser.add_argument("--reserve", type=float, default=None, help="reserve, MiB, without free_mb")
    parser.add_argument("--out", type=Path, required=True, help="output CSV")
    args = parser.parse_args()
    rows: list[dict] = []
    for path in args.logs:
        rows.extend(replay(path, args.warmup, args.delta, args.alpha, args.reserve))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"warmup={args.warmup}: {len(rows)} rows written to {args.out}")


if __name__ == "__main__":
    main()
