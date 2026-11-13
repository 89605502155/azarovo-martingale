# API

[English version](../en/api.md)

Публичные имена импортируются из корня пакета. Единицы: память в МБ, время в секундах
(или в любом базовом шаге, см. `step`).

## Интервал

```python
from azarovo_martingale import azuma_bound, max_rise_bound, monitoring_interval

monitoring_interval(512, 20.0, 0.01)  # 71, формулы (7)-(9)
monitoring_interval(512, 20.0, 0.01, n_max=60)  # 60, с ограничением
azuma_bound(71, 512, 20.0)  # 0.0099, формула (5) при t = R
max_rise_bound(100, 1.0, 0.01)  # около 30,3 c, п. 1.4
```

`monitoring_interval(reserve, c, delta, n_max=None) -> int`. Возвращает `0`, если
`reserve <= c`.

## Детекторы

У каждого детектора есть `update(dx, n=1.0) -> bool` (`True` означает тревогу),
`reset()`, `to_dict()` и метод класса `from_dict(data)`.

```python
from azarovo_martingale import CusumGrowthDetector, GrowthDetector, MixtureGrowthDetector

single = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)  # формулы (11), (12)
single.update(30.0)
print(round(single.capital, 3))  # 1.3
cusum = CusumGrowthDetector(c=50.0, lam=0.5, threshold=1e5)  # формула (14)
mixture = MixtureGrowthDetector(c=50.0, alpha=0.01)  # дополнение: девять ставок, без lam
mixture.update(-10.0)
restored = GrowthDetector.from_dict(single.to_dict())
print(restored.log_capital == single.log_capital)  # True
```

`n` — длина интервала в базовых шагах; `dx` нормируется как `dx / (n c)` и
обрезается до [-1, 1]. Нечисловое или бесконечное `dx` вызывает `ValueError`.
Параметр `clip` (по умолчанию `True`) управляет обрезкой в детекторах, в
`MonitoringScheduler` и в `VmMonitor`. При выполнении допущения А1 он ничего не меняет.
Если А1 нарушено, обрезанный детектор остаётся определённым, но гарантии не даёт;
при `clip=False` обновление вызывает `ValueError`.

## Планировщик

```python
from azarovo_martingale import MonitoringScheduler

sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01, kind="ville")
decision = sched.step(dx=5.0, reserve=512.0, n_elapsed=1.0)
print(decision.interval, decision.redistribute, decision.alarm)
```

`kind` — `"ville"` (по умолчанию), `"cusum"`, `"subgaussian"` или `"mixture"`.
`step(dx, reserve, n_elapsed=None) -> Decision` выполняет этапы 3–6 рисунка 3.
`Decision` — замороженный датакласс с полями `interval`, `redistribute`, `alarm` и
`calibrated`.

## Оценка c

```python
from azarovo_martingale import estimate_c, exceedance_share

deltas = [10.0, -40.0, 25.0]
c = estimate_c(deltas, margin=1.2)  # 1,2 * max |dx| / шаг
robust = estimate_c(deltas, quantile=0.67, margin=1.2)  # устойчивее к редким скачкам
print(round(c, 1), round(exceedance_share(deltas, None, c), 2))  # 48.0 0.0
```

`quantile = 1` — максимум, выбор статьи. Меньший квантиль устойчивее к редким скачкам;
тогда гарантия (6) уже не покрывает эти скачки.
Передавайте только приращения за один базовый шаг: изменение за несколько шагов может
оказаться намного меньше максимального одношагового, потому что шаги компенсируют друг друга.
Оценка `c` удовлетворяет А1 только при репрезентативной выборке; для оценённой `c`
гарантия не доказана.

`MixtureGrowthDetector(c, alpha=0.01, lams=DEFAULT_BETS, weights=None)` принимает
сетку ставок `lams` (непустая, каждая ставка в [0, 1), по умолчанию от 0,1 до 0,9)
и необязательные `weights` (по одному неотрицательному весу на ставку, в сумме 1;
по умолчанию равные). Прочие значения дают `TypeError` (не вещественное число,
логические значения тоже) или `ValueError`.

```python
from azarovo_martingale import MixtureGrowthDetector

narrow = MixtureGrowthDetector(c=50.0, lams=(0.2, 0.8), weights=(0.75, 0.25))
```

## Одна ВМ, потоком

```python
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0, delta=0.01, alpha=0.01, n_max=600)
vm.record_measurement(0.0, used=2048.0, free=1352.0)  # отправная точка
d = vm.record_measurement(1.0, used=2049.0, free=1351.0)
print(d.interval, vm.checks, vm.next_check_time)  # 495 1 496.0
```

Без `c` окно калибровки задаёт `warmup` (по умолчанию 50): `c` оценивается по `warmup`
приращениям ровно за один базовый шаг, с `c_quantile` и `c_margin`, а `Decision.calibrated`
равно `False`, пока оценка не готова. Показание, пришедшее позже чем через один шаг после
предыдущего, в окно не попадает. Опрашивайте ВМ на каждом базовом шаге или задавайте `c`,
иначе монитор не откалибруется. `vm.calibration_samples` показывает, сколько одношаговых
приращений собрано. Времена показаний должны возрастать.

## Несколько ВМ

```python
from azarovo_martingale import FleetMonitor

fleet = FleetMonitor(n_vms=4, delta=0.04, alpha=0.04, c=20.0)  # каждой ВМ достаётся 0,01
fleet.add("vm-a")
fleet.record_measurement(
    "vm-b", 0.0, used=1000.0, free=500.0
)  # vm-b регистрируется при первом показании
print(fleet.names, fleet.due(10.0))
```

`delta` и `alpha` — общие для парка значения, делятся на `n_vms` (неравенство Буля).

## Состояние для перезапуска

```python
import json
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0)
vm.record_measurement(0.0, used=2048.0, free=1352.0)
saved = json.dumps(vm.to_dict())  # сериализуется в JSON
restored = VmMonitor.from_dict(json.loads(saved))
print(restored.next_check_time)  # 1.0
```

## Проверка показаний

`validate_measurement(t, used, free, last_t=None)` — единственная проверка входных
данных; `record_measurement` использует её до изменения состояния. Логические
значения, строки, `None` и прочие невещественные значения дают `TypeError`. NaN,
бесконечность, отрицательные значения и время, которое не возрастает, дают `ValueError`.

```python
from azarovo_martingale import validate_measurement

print(validate_measurement(1, 2048, 1352.5))  # (1.0, 2048.0, 1352.5)
```

## Анализ журнала

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

`analyse_log` возвращает по одному `VmReport` на ВМ с проверками А1 и А2 (`a1_*`,
`a2_*`), гарантией (`guarantee`), детекторами (`detector`) и воспроизведением политик
(`replay`). `report_to_dict` даёт данные, готовые к JSON. `plot_trace` (в модуле
`azarovo_martingale.plot`) требует дополнения `plot`.

## Ошибки

Недопустимые параметры вызывают `ValueError` с сообщением, которое называет параметр.
Командная строка превращает их в код выхода 2.
