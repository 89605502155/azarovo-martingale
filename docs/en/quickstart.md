# Quick start

[Русская версия](../ru/quickstart.md)

This guide runs the three building blocks of the article in a few lines: the
monitoring interval, the growth detector, and the joint scheduler. All examples
are executed by the test suite.

## 1. The monitoring interval

A VM has a free memory reserve `R` of 512 MiB. Its memory use changes by at most
`c = 20` MiB per second (assumption A1). How long can the VM be left unobserved so
that the reserve is exhausted with probability at most `delta = 0.01`?

```python
from azarovo_martingale import monitoring_interval

interval = monitoring_interval(512, c=20.0, delta=0.01)
print(interval)  # 71 seconds
```

If the reserve is no larger than `c`, the function returns `0`: the memory must be
redistributed at once.

```python
print(monitoring_interval(15, c=20.0, delta=0.01))  # 0
```

## 2. A growth detector

The detector plays a betting game against "the use does not grow". An alarm means
the capital has reached `1/alpha`. Ville's inequality makes the false-alarm
probability at most `alpha`, however often the detector is updated.

```python
from azarovo_martingale import GrowthDetector

det = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
steps = 0
while not det.update(30.0):  # a steady rise of 30 MiB per second
    steps += 1
print(steps + 1)  # 18: the alarm at the 18th second
```

## 3. The joint scheduler

The scheduler combines the interval and the detector, as in Fig. 3 of the article.
A `decision` tells you the next interval, whether to redistribute, and whether the
detector alarmed.

```python
from azarovo_martingale import MonitoringScheduler

sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
decision = sched.step(dx=0.0, reserve=512.0)  # the use changed by 0 MiB
print(decision.interval, decision.redistribute)  # 71 False
decision = sched.step(dx=0.0, reserve=15.0)  # the reserve is below c
print(decision.redistribute)  # True
```

## 4. A streaming monitor

`VmMonitor` takes readings as they come. The first reading sets the baseline; the
`due` method says when the VM should be read next.

```python
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0)
vm.record_measurement(0.0, used=2048.0, free=1352.0)
print(vm.next_check_time)  # 1.0
vm.record_measurement(1.0, used=2049.0, free=1351.0)
print(vm.interval, vm.due(100.0))  # 495 False
```

Without `c`, the monitor estimates it from the first `warmup` increments (that is, `warmup + 1` readings; the default is `warmup = 50`) and uses the
conservative `n_min` until then. See [the API](api.md).

## 5. From the command line

```sh
azarovo-martingale interval 512 20   # prints 71
azarovo-martingale analyze log.csv --out results/run1
```

See [the command-line tool](cli.md) and [the log format](log-format.md).
