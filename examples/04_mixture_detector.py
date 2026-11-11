"""Addition: the mixture of bets needs no choice of the betting fraction.

It is compared with the single bet of formula (11) at two speeds of growth.
The mixture keeps the same false-alarm guarantee; it is not always the fastest.
"""

from azarovo_martingale import GrowthDetector, MixtureGrowthDetector


def delay(det: GrowthDetector | MixtureGrowthDetector, rise: float, c: float) -> int:
    det_ = det
    for k in range(1, 10_000):
        if det_.update(rise * c):
            return k
    return -1


c = 50.0
for label, rise in (("fast, 0.6 c per step", 0.6), ("slow, 0.1 c per step", 0.1)):
    single = delay(GrowthDetector(c, lam=0.5, alpha=0.01), rise, c)
    mixed = delay(MixtureGrowthDetector(c, alpha=0.01), rise, c)
    print(f"{label}: single bet lam = 0.5 -> {single} steps, mixture -> {mixed} steps")
