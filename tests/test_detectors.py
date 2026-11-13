"""Detectors: the examples of section 3 of the article and the guarantees of Ville's inequality."""

import math
import random
from collections.abc import Callable
from typing import Any

import pytest

from azarovo_martingale import (
    CusumGrowthDetector,
    GrowthDetector,
    MixtureGrowthDetector,
    SubGaussianGrowthDetector,
)


def _alarms(det: GrowthDetector, dxs: list[float], n: float = 1.0) -> list[int]:
    out = []
    for k, dx in enumerate(dxs, start=1):
        if det.update(dx, n):
            out.append(k)
            det.reset()
    return out


def test_example_of_section_3_3() -> None:
    det = GrowthDetector(c=50, lam=0.5, alpha=0.01)
    for dx in (10, -20, 5, -10):
        assert not det.update(dx)
    assert det.capital == pytest.approx(1.1 * 0.8 * 1.05 * 0.9)


def test_steady_growth_alarms_after_18_steps() -> None:
    assert _alarms(GrowthDetector(c=50, lam=0.5, alpha=0.01), [30.0] * 40) == [18, 36]


def test_capital_stays_positive_on_huge_drop() -> None:
    det = GrowthDetector(c=50, lam=0.5)
    det.update(-1e9)
    assert det.capital == pytest.approx(0.5)


def test_normalisation_by_interval_length() -> None:
    a, b = GrowthDetector(c=50), GrowthDetector(c=50)
    a.update(60.0, n=2)
    b.update(30.0)
    assert a.log_capital == pytest.approx(b.log_capital)


def test_no_underflow_in_long_calm_period() -> None:
    det = GrowthDetector(c=50, lam=0.5)
    for _ in range(50_000):
        det.update(-50.0)
    assert math.isfinite(det.log_capital)
    assert det.log_capital < -1000
    det.reset()
    assert det.capital == 1.0


def test_non_finite_increment_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        GrowthDetector(c=50).update(float("nan"))


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="lam"):
        GrowthDetector(c=50, lam=1.0)
    with pytest.raises(ValueError, match="alpha"):
        GrowthDetector(c=50, alpha=0.0)


def test_false_alarm_rate_is_below_alpha() -> None:
    """Ville's inequality: the capital of a fair game rarely reaches 1 / alpha."""
    rng = random.Random(12345)
    runs, steps, alpha = 1000, 200, 0.1
    alarms = 0
    for _ in range(runs):
        det = GrowthDetector(c=1.0, lam=0.5, alpha=alpha)
        for _ in range(steps):
            if det.update(rng.choice((-1.0, 1.0))):
                alarms += 1
                break
    assert alarms / runs <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / runs)


def test_cusum_floor_and_detection() -> None:
    det = CusumGrowthDetector(c=50, lam=0.5, threshold=1e5)
    for _ in range(2_000):
        assert not det.update(-50.0)
    assert det.statistic == pytest.approx(0.5)
    steps = 1
    while not det.update(30.0):
        steps += 1
    assert steps == math.ceil(math.log(1e5) / math.log(1.3))


def test_cusum_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="threshold"):
        CusumGrowthDetector(c=50, threshold=1.0)


def test_subgaussian_false_alarm_rate_with_varying_intervals() -> None:
    """Ville's guarantee holds when the interval changes from check to check."""
    rng = random.Random(7)
    runs, checks, alpha = 600, 40, 0.1
    alarms = 0
    for _ in range(runs):
        det = SubGaussianGrowthDetector(c=1.0, alpha=alpha)
        for _ in range(checks):
            n = rng.randint(1, 40)
            dx = 2 * rng.getrandbits(n).bit_count() - n  # sum of n fair +-1 steps
            if det.update(dx, n):
                alarms += 1
                break
    assert alarms / runs <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / runs)


def test_subgaussian_needs_few_long_checks() -> None:
    n = 40

    def checks_to_alarm(det: GrowthDetector | SubGaussianGrowthDetector) -> int:
        k = 1
        while not det.update(25.0 * n, n):
            k += 1
        return k

    assert checks_to_alarm(SubGaussianGrowthDetector(c=50.0, alpha=0.01)) <= 2
    assert checks_to_alarm(GrowthDetector(c=50.0, lam=0.5, alpha=0.01)) >= 15


def test_subgaussian_rejects_bad_scales() -> None:
    with pytest.raises(ValueError, match="lams"):
        SubGaussianGrowthDetector(c=50.0, lams=(0.0, 1.0))


def test_mixture_false_alarm_rate_is_below_alpha() -> None:
    """Addition: the mixture over a grid of bets keeps Ville's guarantee without tuning."""
    rng = random.Random(99)
    runs, steps, alpha = 800, 200, 0.1
    alarms = 0
    for _ in range(runs):
        det = MixtureGrowthDetector(c=1.0, alpha=alpha)
        for _ in range(steps):
            if det.update(rng.choice((-1.0, 1.0))):
                alarms += 1
                break
    assert alarms / runs <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / runs)


def test_mixture_detects_growth_without_choosing_lam() -> None:
    fast = _alarms(MixtureGrowthDetector(c=50.0), [30.0] * 60)
    slow = _alarms(MixtureGrowthDetector(c=50.0), [5.0] * 400)
    assert fast
    assert fast[0] < 25
    assert slow
    assert slow[0] > fast[0]


def test_mixture_capital_is_average_of_bets() -> None:
    det = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8))
    det.update(25.0)  # Y = 0.5: the bets multiply the capital by 1.1 and by 1.4
    assert det.capital == pytest.approx((1.1 + 1.4) / 2)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: GrowthDetector(c=50.0),
        lambda: CusumGrowthDetector(c=50.0),
        lambda: SubGaussianGrowthDetector(c=50.0),
        lambda: MixtureGrowthDetector(c=50.0),
    ],
    ids=["ville", "cusum", "subgaussian", "mixture"],
)
def test_state_round_trips_through_dict(factory: Callable[[], Any]) -> None:
    det = factory()
    for dx in (3.0, -7.0, 12.0):
        det.update(dx)
    restored = type(det).from_dict(det.to_dict())
    assert restored.to_dict() == det.to_dict()


def test_mixture_grid_is_a_constructor_parameter():
    det = MixtureGrowthDetector(c=50.0, lams=(0.0, 0.5))
    assert det.lams == (0.0, 0.5)
    assert det.weights == (0.5, 0.5)
    assert len(det.logs) == 2


@pytest.mark.parametrize(
    ("lams", "error"),
    [
        ((), ValueError),
        ((1.0,), ValueError),
        ((-0.1, 0.5), ValueError),
        ((0.2, float("nan")), ValueError),
        (("0.5",), TypeError),
        ((True,), TypeError),
        (None, TypeError),
    ],
)
def test_mixture_grid_is_validated(lams, error):
    with pytest.raises(error):
        MixtureGrowthDetector(c=50.0, lams=lams)


@pytest.mark.parametrize(
    ("weights", "error"),
    [
        ((0.5,), ValueError),  # wrong length
        ((0.6, 0.6), ValueError),  # sums to 1.2
        ((0.2, 0.3), ValueError),  # sums to 0.5
        ((1.5, -0.5), ValueError),  # negative
        ((0.5, float("nan")), ValueError),
        (("0.5", 0.5), TypeError),
        ((True, 0.0), TypeError),
    ],
)
def test_mixture_weights_are_validated(weights, error):
    with pytest.raises(error):
        MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8), weights=weights)


def test_mixture_weights_are_optional_and_uniform_by_default():
    det = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.4, 0.8))
    assert det.weights == pytest.approx((1 / 3, 1 / 3, 1 / 3))


def test_weighted_capital_is_the_weighted_average_of_bets():
    det = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8), weights=(0.25, 0.75))
    det.update(25.0)  # Y = 0.5: the bets give 1.1 and 1.4
    assert det.capital == pytest.approx(0.25 * 1.1 + 0.75 * 1.4)


def test_weight_on_one_bet_equals_that_single_bet():
    mixed = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8), weights=(0.0, 1.0))
    single = GrowthDetector(c=50.0, lam=0.8)
    for dx in (30.0, -10.0, 5.0, 30.0):
        mixed.update(dx)
        single.update(dx)
    assert mixed.log_capital == pytest.approx(single.log_capital)


@pytest.mark.parametrize("weights", [(0.5, 0.5), (0.9, 0.1), (0.1, 0.9)])
def test_weighted_mixture_keeps_the_false_alarm_bound(weights):
    # Ville's inequality holds for every convex combination; the rate is checked
    # on several seeds rather than on the one that would happen to pass.
    alpha = 0.05
    runs = 300
    for seed in (1, 2, 3):
        rng = random.Random(seed)
        false = 0
        for _ in range(runs):
            det = MixtureGrowthDetector(c=1.0, alpha=alpha, lams=(0.1, 0.9), weights=weights)
            if any(det.update(rng.choice((-1.0, 1.0))) for _ in range(200)):
                false += 1
        assert false / runs <= alpha + 0.05


def test_weights_round_trip_through_dict():
    det = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8), weights=(0.25, 0.75))
    det.update(10.0)
    restored = MixtureGrowthDetector.from_dict(det.to_dict())
    assert restored.weights == (0.25, 0.75)
    assert restored.log_capital == pytest.approx(det.log_capital)


def test_weighted_mixture_is_finite_after_long_calm_period():
    det = MixtureGrowthDetector(c=50.0, lams=(0.0, 0.9), weights=(1.0, 0.0))
    for _ in range(5_000):
        det.update(-50.0)
    assert math.isfinite(det.log_capital)


@pytest.mark.parametrize(
    "make",
    [
        lambda clip: GrowthDetector(c=50.0, lam=0.5, clip=clip),
        lambda clip: CusumGrowthDetector(c=50.0, lam=0.5, clip=clip),
        lambda clip: MixtureGrowthDetector(c=50.0, clip=clip),
    ],
    ids=["ville", "cusum", "mixture"],
)
def test_clip_true_bounds_a_violation_of_a1(make: Callable[[bool], Any]) -> None:
    # A jump of 3c violates A1. With clipping the capital stays positive and finite.
    det = make(True)
    det.update(150.0)  # no exception: the normalised change is clipped to +1
    state = getattr(det, "log_capital", None)
    if state is None:
        state = det.log_statistic  # type: ignore[attr-defined]
    assert math.isfinite(state)


@pytest.mark.parametrize(
    "make",
    [
        lambda clip: GrowthDetector(c=50.0, lam=0.5, clip=clip),
        lambda clip: CusumGrowthDetector(c=50.0, lam=0.5, clip=clip),
        lambda clip: MixtureGrowthDetector(c=50.0, clip=clip),
    ],
    ids=["ville", "cusum", "mixture"],
)
def test_clip_false_refuses_a_violation_of_a1(make: Callable[[bool], Any]) -> None:
    det = make(False)
    with pytest.raises(ValueError, match="A1"):
        det.update(150.0)
    # Inside A1 the two settings coincide.
    assert make(False).update(30.0) == make(True).update(30.0)


def test_clip_false_is_identical_to_clip_true_under_a1() -> None:
    dxs = [10.0, -20.0, 5.0, -10.0, 30.0, 49.0]
    on, off = GrowthDetector(c=50.0, clip=True), GrowthDetector(c=50.0, clip=False)
    for dx in dxs:
        assert on.update(dx) == off.update(dx)
    assert on.log_capital == pytest.approx(off.log_capital)


def test_clip_false_subgaussian_refuses_a_jump_above_n_c() -> None:
    det = SubGaussianGrowthDetector(c=50.0, clip=False)
    with pytest.raises(ValueError, match="A1"):
        det.update(51.0)
    assert SubGaussianGrowthDetector(c=50.0, clip=True).update(51.0) is False


def test_clip_is_kept_by_the_state_round_trip() -> None:
    det = GrowthDetector(c=50.0, clip=False)
    assert GrowthDetector.from_dict(det.to_dict()).clip is False
    old_state = {"c": 50.0, "lam": 0.5, "alpha": 0.01, "log_capital": 0.0}
    assert GrowthDetector.from_dict(old_state).clip is True
