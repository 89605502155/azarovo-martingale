"""The monitoring interval reproduces Table 1 and the examples of the article."""

import math

import pytest

from azarovo_martingale import azuma_bound, max_rise_bound, monitoring_interval

# Table 1 of the article: (c, R) -> n* at delta = 0.01
TABLE_1 = {
    (10, 256): 71, (10, 512): 284, (10, 1024): 1138, (10, 2048): 4553,
    (20, 256): 17, (20, 512): 71, (20, 1024): 284, (20, 2048): 1138,
    (50, 256): 5, (50, 512): 11, (50, 1024): 45, (50, 2048): 182,
    (100, 256): 2, (100, 512): 5, (100, 1024): 11, (100, 2048): 45,
}  # fmt: skip


@pytest.mark.parametrize(("key", "expected"), sorted(TABLE_1.items()))
def test_table_1(key: tuple[int, int], expected: int) -> None:
    c, reserve = key
    assert monitoring_interval(reserve, c, 0.01) == expected


def test_example_of_section_2_3() -> None:
    assert monitoring_interval(512, 20, 0.01) == 71
    assert math.ceil(512 / 20) - 1 == 25  # the deterministic bound n_0


@pytest.mark.parametrize("reserve", [-100.0, 0.0, 10.0, 20.0, float("nan")])
def test_small_reserve_means_redistribute_now(reserve: float) -> None:
    assert monitoring_interval(reserve, 20, 0.01) == 0


def test_n_max_caps_interval() -> None:
    assert monitoring_interval(2048, 10, 0.01, n_max=600) == 600


def test_interval_grows_with_reserve() -> None:
    values = [monitoring_interval(r, 20, 0.01) for r in range(21, 3000, 7)]
    assert values == sorted(values)


def test_risk_is_a_guarantee_for_the_chosen_interval() -> None:
    n = monitoring_interval(512, 20, 0.01)
    assert azuma_bound(n, 512, 20) <= 0.01


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="c must"):
        monitoring_interval(512, 0, 0.01)
    with pytest.raises(ValueError, match="delta"):
        monitoring_interval(512, 20, 1.5)
    with pytest.raises(ValueError, match="n_max"):
        monitoring_interval(512, 20, 0.01, n_max=-1)


def test_azuma_bound_of_the_article() -> None:
    assert azuma_bound(71, 512, 20) < 0.01
    assert azuma_bound(100, 0.0, 20) == pytest.approx(1.0)


def test_max_rise_bound_of_the_article() -> None:
    # about 30 c for n = 100 and delta = 0.01, against 100 c in the worst case
    assert max_rise_bound(100, 1.0, 0.01) == pytest.approx(30.35, abs=0.01)
    with pytest.raises(ValueError, match="delta"):
        max_rise_bound(100, 1.0, 0.0)
