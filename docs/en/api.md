# API

[Русская версия](../ru/api.md)

The public names are importable from the package root. Units: memory in MiB, time
in seconds (or in any base step, see `step`).

## Interval

```python
from azarovo_martingale import azuma_bound, max_rise_bound, monitoring_interval

monitoring_interval(512, 20.0, 0.01)  # 71, formulas (7)-(9)
monitoring_interval(512, 20.0, 0.01, n_max=60)  # 60, capped
azuma_bound(71, 512, 20.0)  # 0.0099, formula (5) with t = R
max_rise_bound(100, 1.0, 0.01)  # about 30.3 c, section 1.4
```

`monitoring_interval(reserve, c, delta, n_max=None) -> int`. Returns `0` if
`reserve <= c`.

## Detectors

Each detector has `update(dx, n=1.0) -> bool` (`True` is an alarm), `reset()`,
`to_dict()` and the class method `from_dict(data)`.

```python
from azarovo_martingale import CusumGrowthDetector, GrowthDetector, MixtureGrowthDetector

single = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)  # formulas (11), (12)
single.update(30.0)
print(round(single.capital, 3))  # 1.3
cusum = CusumGrowthDetector(c=50.0, lam=0.5, threshold=1e5)  # formula (14)
mixture = MixtureGrowthDetector(c=50.0, alpha=0.01)  # addition: nine bets, no lam
mixture.update(-10.0)
restored = GrowthDetector.from_dict(single.to_dict())
print(restored.log_capital == single.log_capital)  # True
```

`n` is the length of the interval in base steps; `dx` is normalised to
`dx / (n c)` and clipped to [-1, 1]. Non-finite `dx` raises `ValueError`.

## Scheduler

```python
from azarovo_martingale import MonitoringScheduler

sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01, kind="ville")
decision = sched.step(dx=5.0, reserve=512.0, n_elapsed=1.0)
print(decision.interval, decision.redistribute, decision.alarm)
```

`kind` is `"ville"` (default), `"cusum"`, `"subgaussian"` or `"mixture"`.
`step(dx, reserve, n_elapsed=None) -> Decision` runs steps 3–6 of Fig. 3. The
`Decision` is a frozen dataclass with `interval`, `redistribute`, `alarm`, and
`calibrated`.

## Estimating c

```python
from azarovo_martingale import estimate_c, exceedance_share

deltas = [10.0, -40.0, 25.0]
c = estimate_c(deltas, margin=1.2)  # 1.2 * max |dx| / step
robust = estimate_c(deltas, quantile=0.67, margin=1.2)  # ignores the rarest jumps
print(round(c, 1), round(exceedance_share(deltas, None, c), 2))  # 48.0 0.0
```

`quantile = 1` is the maximum, the choice of the article. A smaller quantile is
robust to rare jumps; the guarantee (6) then no longer covers those jumps.

## One VM, streaming

```python
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0, delta=0.01, alpha=0.01, n_max=600)
vm.update(0.0, used=2048.0, free=1352.0)  # baseline
d = vm.update(1.0, used=2049.0, free=1351.0)
print(d.interval, vm.checks, vm.next_check_time)  # 495 1 496.0
```

Without `c`, pass `warmup` (default 50) readings; `c` is then estimated with
`c_quantile` and `c_margin`, and `Decision.calibrated` is `False` until then.
Readings must have increasing times.

## Several VMs

```python
from azarovo_martingale import FleetMonitor

fleet = FleetMonitor(n_vms=4, delta=0.04, alpha=0.04, c=20.0)  # each VM gets 0.01
fleet.add("vm-a")
fleet.update("vm-b", 0.0, used=1000.0, free=500.0)  # registers vm-b on first use
print(fleet.names, fleet.due(10.0))
```

`delta` and `alpha` are the fleet totals, split by `n_vms` (Boole's inequality).

## State for restarts

```python
import json
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0)
vm.update(0.0, used=2048.0, free=1352.0)
saved = json.dumps(vm.to_dict())  # JSON-serialisable
restored = VmMonitor.from_dict(json.loads(saved))
print(restored.next_check_time)  # 1.0
```

## Log analysis

```python
import tempfile
from pathlib import Path

from azarovo_martingale import AnalysisOptions, analyse_log, read_log, render_markdown

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "log.csv"
    rows = ["time,vm,used_mb,free_mb,phase"]
    for t in range(200):
        rows.append(f"{t},vm-a,{1000 + 2 * (t % 3)},{2000 - 2 * (t % 3)},calm")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = read_log(path)
    options = AnalysisOptions(fixed=(1, 5))
    reports = analyse_log(log, options)
    print(reports[0].vm, reports[0].skipped)  # vm-a None
    print(render_markdown(reports, options, log_name=path.name).splitlines()[0])
```

`analyse_log` returns one `VmReport` per VM with the checks of A1 and A2 (`a1_*`,
`a2_*`), the guarantee (`guarantee`), the detectors (`detector`), and the policy
replays (`replay`). `report_to_dict` gives JSON-ready data. `plot_trace` (in
`azarovo_martingale.plot`) needs the `plot` extra.

## Errors

Invalid parameters raise `ValueError` with a message that names the parameter. The
command-line tool turns them into exit status 2.
