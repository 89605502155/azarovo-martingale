"""Monte Carlo checks of the guarantees with many runs. Run them with: pytest -m slow"""

import math
import random

import pytest

from azarovo_martingale import GrowthDetector, MixtureGrowthDetector, monitoring_interval


@pytest.mark.slow
def test_exhaustion_share_is_below_delta() -> None:
    """Article, section 2.4: the exhaustion share stays below delta for a calm VM."""
    c, reserve, delta = 20.0, 512.0, 0.01
    n = monitoring_interval(reserve, c, delta)
    rng = random.Random(1)
    runs = 20_000
    hits = 0
    for _ in range(runs):
        x = 0.0
        for _ in range(n):
            x += c if rng.random() < 0.5 else -c
            if x >= reserve:
                hits += 1
                break
    assert hits / runs <= delta + 3 * math.sqrt(delta / runs)


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["ville", "mixture"])
def test_false_alarm_share_is_below_alpha(kind: str) -> None:
    rng = random.Random(2)
    alpha, runs, steps = 0.05, 4000, 400
    alarms = 0
    for _ in range(runs):
        det = (
            GrowthDetector(1.0, 0.5, alpha)
            if kind == "ville"
            else MixtureGrowthDetector(1.0, alpha)
        )
        for _ in range(steps):
            if det.update(1.0 if rng.random() < 0.5 else -1.0):
                alarms += 1
                break
    assert alarms / runs <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / runs)
