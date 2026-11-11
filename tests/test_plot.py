"""Plots need the plot extra; the test is skipped without matplotlib."""

from pathlib import Path

import pytest

from azarovo_martingale import AnalysisOptions, analyse_log, read_log

pytest.importorskip("matplotlib")


def test_plot_trace_writes_png(tmp_path: Path) -> None:
    from azarovo_martingale.plot import plot_trace

    rows = ["time,vm,used_mb,free_mb,phase"]
    used = 1000.0
    for t in range(300):
        growth = 150 <= t < 180
        used += 15.0 if growth else (-1.0 if t % 2 else 1.0)
        rows.append(f"{t},v,{used},{3000 - used},{'growth' if growth else 'calm'}")
    path = tmp_path / "log.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = read_log(path)
    options = AnalysisOptions(fixed=(5,))
    (report,) = analyse_log(log, options)
    out = plot_trace(tmp_path / "trace.png", log.vms["v"], report)
    assert out.exists()
    assert out.stat().st_size > 1000
