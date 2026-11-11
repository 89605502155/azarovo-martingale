"""Analysis of a monitoring log: checks of A1 and A2, the guarantee (6), and the policies.

A small synthetic log is written to a temporary folder and analysed.
"""

import random
import tempfile
from pathlib import Path

from azarovo_martingale import AnalysisOptions, analyse_log, read_log, render_markdown

rng = random.Random(7)
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "demo.csv"
    lines = ["time,vm,used_mb,free_mb,phase"]
    for vm, slope in (("vm-a", 0.0), ("vm-b", 0.0)):
        used = 2000.0
        for t in range(1200):
            growth = 700 <= t < 760 and vm == "vm-b"
            used += rng.gauss(25.0 if growth else slope, 8.0)
            phase = "growth" if growth else "calm"
            lines.append(f"{t},{vm},{used:.1f},{4000 - used:.1f},{phase}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log = read_log(path)
    options = AnalysisOptions(fixed=(1, 5))
    reports = analyse_log(log, options)
    text = render_markdown(reports, options, log_name=path.name, has_phase=log.has_phase)

print("\n".join(text.splitlines()[:14]))
for rep in reports:
    print(f"{rep.vm}: c = {rep.c:.1f} MiB per step, exhausted share = {rep.guarantee.share:.4f}")
