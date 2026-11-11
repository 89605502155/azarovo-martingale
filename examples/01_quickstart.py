"""Quickstart: the monitoring interval, one growth detector and the joint scheduler."""

from azarovo_martingale import GrowthDetector, MonitoringScheduler, monitoring_interval

# Formulas (7)-(9): a VM with 512 MiB of free memory and changes of at most 20 MiB per second.
print("interval for R = 512 MiB, c = 20 MiB/s:", monitoring_interval(512, 20, 0.01))

# Formulas (11)-(12): a steady rise of 30 MiB/s is detected after 18 seconds.
detector = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
steps = next(k for k in range(1, 100) if detector.update(30.0))
print("alarm after", steps, "steps of growth at 30 MiB/s")

# Figure 3: the scheduler chooses the next check from the reserve and the detector.
sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
calm = sched.step(dx=0.0, reserve=512.0)
low = sched.step(dx=0.0, reserve=15.0)
print("calm, reserve 512 MiB -> next check in", calm.interval, "s")
print("reserve 15 MiB (below c) -> redistribute:", low.redistribute)
