"""The scheduler follows Fig. 3; the estimate of c and the streaming monitors."""

import json
import math

import pytest

from azarovo_martingale import (
    Decision,
    FleetMonitor,
    MonitoringScheduler,
    VmMonitor,
    estimate_c,
    exceedance_share,
)


def test_scheduler_follows_figure_3() -> None:
    s = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01, lam=0.5, n_min=1, n_max=600)
    assert s.interval == 1
    assert s.step(dx=0.0, reserve=512.0) == Decision(71, redistribute=False, alarm=False)
    assert s.step(dx=0.0, reserve=15.0) == Decision(1, redistribute=True, alarm=False)


def test_scheduler_alarm_on_growth() -> None:
    s = MonitoringScheduler(c=50.0, n_max=None)
    decisions = [s.step(dx=30.0, reserve=10_000.0, n_elapsed=1) for _ in range(18)]
    assert decisions[-1].alarm
    assert decisions[-1].redistribute
    assert not any(d.alarm for d in decisions[:-1])
    assert s.detector.to_dict()["log_capital"] == 0.0


def test_cusum_scheduler_reacts_after_long_calm_period() -> None:
    ville = MonitoringScheduler(c=50.0, n_max=None)
    cusum = MonitoringScheduler(c=50.0, n_max=None, kind="cusum", cusum_threshold=1e5)
    for s in (ville, cusum):
        for _ in range(600):
            s.step(dx=-10.0, reserve=10_000.0, n_elapsed=1)
    steps: dict[str, int] = {}
    for name, s in (("ville", ville), ("cusum", cusum)):
        k = 1
        while not s.step(dx=30.0, reserve=10_000.0, n_elapsed=1).alarm:
            k += 1
        steps[name] = k
    assert steps["cusum"] == math.ceil(math.log(1e5) / math.log(1.3))
    assert steps["ville"] > steps["cusum"]


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="kind"):
        MonitoringScheduler(c=50.0, kind="other")  # type: ignore[arg-type]


def test_subgaussian_and_mixture_schedulers_run() -> None:
    for kind in ("subgaussian", "mixture"):
        s = MonitoringScheduler(c=50.0, kind=kind, n_max=None)  # type: ignore[arg-type]
        assert s.step(dx=1000.0, reserve=1e4, n_elapsed=40).interval > 0


def test_scheduler_state_round_trip_continues_identically() -> None:
    a = MonitoringScheduler(c=20.0, kind="mixture")
    for dx, r in ((5.0, 800.0), (-3.0, 780.0), (9.0, 760.0)):
        a.step(dx, r, n_elapsed=4)
    b = MonitoringScheduler.from_dict(json.loads(json.dumps(a.to_dict())))
    for dx, r in ((12.0, 740.0), (30.0, 700.0)):
        assert a.step(dx, r, 4) == b.step(dx, r, 4)


def test_estimate_c() -> None:
    assert estimate_c([10, -40, 25], margin=1.0) == 40
    assert estimate_c([10, -40, 25], margin=1.5) == 60
    assert estimate_c([10, -40, 60], steps=[1, 1, 2], margin=1.0) == 40
    assert estimate_c(range(1, 101), quantile=0.9, margin=1.0) == 90
    with pytest.raises(ValueError, match="zero"):
        estimate_c([0, 0])
    with pytest.raises(ValueError, match="empty"):
        estimate_c([])
    with pytest.raises(ValueError, match="same length"):
        estimate_c([1, 2], steps=[1])


def test_exceedance_share() -> None:
    assert exceedance_share([10, -40, 25], None, 20.0) == pytest.approx(2 / 3)


def test_vm_monitor_calibrates_then_schedules() -> None:
    vm = VmMonitor("vm-1", warmup=5, c_margin=1.0)
    assert vm.record_measurement(0.0, 1000.0, 500.0).calibrated is False
    decisions = [
        vm.record_measurement(float(t), 1000.0 + 2.0 * (t % 2), 500.0) for t in range(1, 6)
    ]
    assert decisions[-1].calibrated is True
    assert vm.calibrated
    assert vm.c == pytest.approx(2.0)
    assert vm.checks == 1


def test_vm_monitor_due_and_time_order() -> None:
    vm = VmMonitor("vm-1", c=20.0)
    assert vm.due(0.0)
    vm.record_measurement(0.0, 2048.0, 1352.0)
    assert vm.next_check_time == 1.0
    vm.record_measurement(1.0, 2049.0, 1351.0)
    assert vm.interval == 495
    assert vm.due(496.0)
    assert not vm.due(100.0)
    with pytest.raises(ValueError, match="increase"):
        vm.record_measurement(1.0, 2049.0, 1351.0)
    with pytest.raises(ValueError, match="finite"):
        vm.record_measurement(2.0, math.nan, 1351.0)


def test_vm_monitor_counts_alarms_and_redistributions() -> None:
    vm = VmMonitor("vm-1", c=50.0, n_max=None)
    vm.record_measurement(0.0, 0.0, 10_000.0)
    for t in range(1, 40):
        vm.record_measurement(float(t), 30.0 * t, 10_000.0)
    assert vm.alarms >= 1
    assert vm.redistributions == vm.alarms


def test_vm_monitor_state_round_trip() -> None:
    vm = VmMonitor("vm-1", warmup=4, c_margin=1.2)
    for t in range(6):
        vm.record_measurement(float(t), 1000.0 + 3.0 * t, 900.0)
    data = json.loads(json.dumps(vm.to_dict()))
    restored = VmMonitor.from_dict(data)
    assert restored.to_dict() == vm.to_dict()
    assert restored.record_measurement(6.0, 1024.0, 900.0) == vm.record_measurement(
        6.0, 1024.0, 900.0
    )


def test_fleet_splits_risk_between_vms() -> None:
    fleet = FleetMonitor(n_vms=4, delta=0.04, alpha=0.04, c=20.0)
    fleet.add("a")
    assert fleet.monitor("a").to_dict()["options"]["delta"] == pytest.approx(0.01)
    with pytest.raises(ValueError, match="already"):
        fleet.add("a")


def test_fleet_auto_registers_and_schedules() -> None:
    fleet = FleetMonitor(c=20.0)
    fleet.record_measurement("vm-1", 0.0, 1000.0, 500.0)
    fleet.record_measurement("vm-2", 0.0, 1000.0, 15.0)
    assert fleet.names == ["vm-1", "vm-2"]
    assert fleet.due(0.5) == []
    assert set(fleet.due(1.0)) == {"vm-1", "vm-2"}
    assert "vm-1" in fleet
    assert len(fleet) == 2
    d = fleet.record_measurement("vm-2", 1.0, 1000.0, 15.0)
    assert d.redistribute


def test_fleet_state_round_trip() -> None:
    fleet = FleetMonitor(n_vms=2, c=20.0, delta=0.02)
    fleet.record_measurement("vm-1", 0.0, 100.0, 512.0)
    restored = FleetMonitor.from_dict(json.loads(json.dumps(fleet.to_dict())))
    assert restored.to_dict() == fleet.to_dict()
    with pytest.raises(KeyError):
        restored.monitor("missing")


def test_scheduler_and_monitor_pass_mixture_weights_through():
    sched = MonitoringScheduler(c=20.0, kind="mixture", lams=(0.2, 0.8), weights=(0.0, 1.0))
    assert sched.detector.weights == (0.0, 1.0)
    vm = VmMonitor("vm", c=20.0, kind="mixture", lams=(0.2, 0.8), weights=(0.25, 0.75))
    vm.record_measurement(0.0, used=1000.0, free=500.0)
    vm.record_measurement(1.0, used=1001.0, free=500.0)
    restored = VmMonitor.from_dict(vm.to_dict())
    assert restored.to_dict() == vm.to_dict()
