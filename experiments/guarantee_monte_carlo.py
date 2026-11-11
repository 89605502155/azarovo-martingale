"""HEAVY (not run in this repository): Monte Carlo check of the guarantees, article E1.

Simulates a calm VM (increments +-c with mean zero), checks the exhaustion share
of the interval (9) against delta, and the false-alarm share of the detectors
against alpha, for several seeds and risk levels. The expected cost is an
estimate, not a measurement: tens of minutes on the laptop, memory under 200 MB.

Usage: python experiments/guarantee_monte_carlo.py --out out_guarantee --runs 20000
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from azarovo_martingale import GrowthDetector, MixtureGrowthDetector, monitoring_interval


def exhaustion_share(c: float, reserve: float, delta: float, runs: int, seed: int) -> float:
    rng = random.Random(seed)
    n = monitoring_interval(reserve, c, delta)
    hits = 0
    for _ in range(runs):
        x = 0.0
        exhausted = False
        for _ in range(n):
            x += c if rng.random() < 0.5 else -c
            if x >= reserve:
                exhausted = True
                break
        hits += exhausted
    return hits / runs


def false_alarm_share(c: float, alpha: float, runs: int, steps: int, seed: int, kind: str) -> float:
    rng = random.Random(seed)
    alarms = 0
    for _ in range(runs):
        det = GrowthDetector(c, 0.5, alpha) if kind == "ville" else MixtureGrowthDetector(c, alpha)
        for _ in range(steps):
            if det.update(c if rng.random() < 0.5 else -c):
                alarms += 1
                break
    return alarms / runs


def main() -> None:
    ap = argparse.ArgumentParser(description="Guarantees of the interval and the detectors")
    ap.add_argument("--runs", type=int, default=20_000)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--out", type=Path, default=Path("out_guarantee"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for delta in (0.05, 0.01):
        share = exhaustion_share(20.0, 512.0, delta, args.runs, seed=1)
        rows.append({"check": "interval (9)", "level": delta, "observed": share})
    for alpha in (0.05, 0.01):
        for kind in ("ville", "mixture"):
            share = false_alarm_share(1.0, alpha, args.runs // 10, args.steps, 2, kind)
            rows.append({"check": f"false alarms {kind}", "level": alpha, "observed": share})
    with (args.out / "guarantees.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["check", "level", "observed"])
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['check']:>24}  level {row['level']:<5}  observed {row['observed']:.4f}")


if __name__ == "__main__":
    main()
