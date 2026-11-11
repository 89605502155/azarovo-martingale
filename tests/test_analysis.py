"""Log reading, the analysis of a log, and its outputs."""

import json
import random
from pathlib import Path

import pytest

from azarovo_martingale import (
    AnalysisOptions,
    MonitoringLog,
    VmLog,
    analyse_log,
    read_log,
    render_markdown,
    report_to_dict,
)
from azarovo_martingale.analysis import _RangeMax, _segments


def _write(tmp_path: Path, text: str, name: str = "log.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_read_log_semicolon_and_decimal_comma(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "time;vm;used_mb;free_mb;phase\n"
        "0;a;100,5;900;calm\n1;a;101,0;899,5;growth\n1;a;150;800;calm\n"
        "0;b;10;20;calm\n",
    )
    log = read_log(path)
    assert log.has_free
    assert log.has_phase
    assert log.vms["a"].time == [0.0, 1.0]
    assert log.vms["a"].duplicates == 1
    assert log.vms["a"].used[0] == pytest.approx(100.5)
    assert log.vms["a"].growth == [False, True]


def test_read_log_comma_file_without_optional_columns(tmp_path: Path) -> None:
    path = _write(tmp_path, "time,vm,used_mb\n2,x,5\n1,x,4\n")
    log = read_log(path)
    assert not log.has_free
    assert not log.has_phase
    assert log.vms["x"].time == [1.0, 2.0]
    assert log.vms["x"].growth == [False, False]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("time,vm\n1,a\n", "missing columns used_mb"),
        ("time,vm,used_mb\n1,a,notanumber\n", "line 2"),
    ],
)
def test_read_log_errors(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        read_log(_write(tmp_path, text))


def test_range_max_matches_bruteforce() -> None:
    rng = random.Random(0)
    a = [rng.gauss(0, 1) for _ in range(257)]
    rm = _RangeMax(a)
    for _ in range(500):
        lo = rng.randrange(257)
        hi = min(lo + rng.randrange(80), 256)
        assert rm.query(lo, hi) == max(a[lo : hi + 1])


def test_segments() -> None:
    assert _segments([False, False, True, True, True, False]) == [
        (0, 2, False),
        (2, 5, True),
        (5, 6, False),
    ]
    assert _segments([]) == []


def _synthetic_log(n: int = 1500, seed: int = 1) -> MonitoringLog:
    rng = random.Random(seed)
    vm = VmLog("vm-x")
    used = 1000.0
    for t in range(n):
        growth = 900 <= t < 960
        used += max(-40.0, min(40.0, rng.gauss(25.0 if growth else 0.0, 10.0)))
        vm.time.append(float(t))
        vm.used.append(used)
        vm.free.append(3000.0 - used)
        vm.growth.append(growth)
    return MonitoringLog({"vm-x": vm}, has_free=True, has_phase=True)


def test_replay_counts_exhaustion() -> None:
    from azarovo_martingale.analysis import _FixedPolicy, _replay

    time = [float(t) for t in range(101)]
    used = [0.0] * 50 + [600.0] * 51
    free = [500.0] * 101
    rep = _replay(time, used, free, _FixedPolicy(10), 1.0)
    assert rep.checks == 10
    assert rep.exhausted == 1


def test_analysis_of_a_synthetic_log() -> None:
    log = _synthetic_log()
    options = AnalysisOptions(fixed=(1, 5))
    (report,) = analyse_log(log, options)
    assert report.skipped is None
    assert report.c > 0
    assert report.test_samples > 0
    assert report.guarantee is not None
    assert report.guarantee.starts > 0
    assert report.detector is not None
    assert report.detector.growth_segments
    delay = report.detector.growth_segments[0].delay_s["ville_restart"]
    assert delay is not None
    assert delay < 120
    kinds = [rp.kind for rp in report.replay]
    assert kinds == ["ville", "cusum", "subgaussian", "mixture", "fixed-1", "fixed-5"]


def test_short_and_fixed_c_logs() -> None:
    short = MonitoringLog(
        {"s": VmLog("s", [0.0, 1.0], [1.0, 2.0], [9.0, 9.0], [False] * 2)}, True, True
    )
    (rep,) = analyse_log(short, AnalysisOptions())
    assert rep.skipped is not None
    assert "fewer" in rep.skipped
    (rep,) = analyse_log(_synthetic_log(200), AnalysisOptions(c=40.0, train_frac=0.0))
    assert rep.c == 40.0
    assert rep.c_source.startswith("given")


def test_missing_reserve_is_an_error() -> None:
    log = _synthetic_log(100)
    log.has_free = False
    with pytest.raises(ValueError, match="free_mb"):
        analyse_log(log, AnalysisOptions())
    (rep,) = analyse_log(log, AnalysisOptions(reserve=800.0))
    assert rep.skipped is None


def test_split_risk_shares_delta() -> None:
    log = _synthetic_log(120)
    other = _synthetic_log(120, seed=2).vms["vm-x"]
    other.name = "vm-y"
    log.vms["vm-y"] = other
    reports = analyse_log(log, AnalysisOptions(split_risk=True))
    assert all(r.delta == pytest.approx(0.005) for r in reports)


def test_markdown_and_json_outputs() -> None:
    log = _synthetic_log(400)
    options = AnalysisOptions(fixed=(1,))
    reports = analyse_log(log, options)
    text = render_markdown(reports, options, log_name="synthetic.csv", has_phase=True)
    assert "# Analysis of the monitoring log synthetic.csv" in text
    assert "### Guarantee (6) for the interval (9)" in text
    assert "mixture of bets (addition)" in text
    data = json.loads(json.dumps(report_to_dict(reports, options), allow_nan=False))
    assert data["vms"][0]["vm"] == "vm-x"
    assert "check_times" not in data["vms"][0]["replay"][0]
    assert data["options"]["delta"] == pytest.approx(0.01)
