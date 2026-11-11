"""Streaming monitoring of a small fleet, one reading at a time.

The memory use evolves every second; the monitor is read only when ``due`` says
so, as a controller would do. Only the readings are sparse.
"""

import random

from azarovo_martingale import FleetMonitor

rng = random.Random(42)
names = ["vm-1", "vm-2", "vm-3"]
fleet = FleetMonitor(n_vms=3, n_max=20, warmup=20, delta=0.03, alpha=0.03)
used = dict.fromkeys(names, 1500.0)
checks = dict.fromkeys(names, 0)
redistributions = 0
for t in range(1, 3601):
    for name in names:
        used[name] += rng.gauss(0.0, 5.0)
        if name == "vm-2" and 1200 < t <= 1500:  # a memory-hungry task: 8 MiB/s for 5 min
            used[name] += 8.0
    for name in names if t == 1 else fleet.due(float(t)):
        decision = fleet.record_measurement(name, float(t), used[name], free=6000.0 - used[name])
        checks[name] += 1
        redistributions += int(decision.redistribute)

for name in names:
    mon = fleet.monitor(name)
    c_text = "-" if mon.c is None else f"{mon.c:.1f}"
    print(f"{name}: checks {checks[name]}, alarms {mon.alarms}, c = {c_text} MiB per step")
print("total redistributions:", redistributions)
