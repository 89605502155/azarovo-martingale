# Быстрый старт

[English version](../en/quickstart.md)

Это руководство показывает три основных элемента статьи в нескольких строках:
интервал мониторинга, детектор роста и совместный планировщик. Все примеры
выполняются тестами пакета.

## 1. Интервал мониторинга

Свободный запас памяти ВМ `R` равен 512 МБ. Потребление памяти меняется не более
чем на `c = 20` МБ в секунду (допущение А1). Как долго можно не проверять ВМ, чтобы
запас исчерпался с вероятностью не выше `delta = 0,01`?

```python
from azarovo_martingale import monitoring_interval

interval = monitoring_interval(512, c=20.0, delta=0.01)
print(interval)  # 71 секунда
```

Если запас не больше `c`, функция возвращает `0`: память нужно перераспределить
немедленно.

```python
print(monitoring_interval(15, c=20.0, delta=0.01))  # 0
```

## 2. Детектор роста

Детектор играет в ставки против гипотезы «потребление не растёт». Тревога означает,
что капитал достиг `1/alpha`. Неравенство Вилля делает вероятность ложной тревоги не
больше `alpha`, сколько бы раз детектор ни обновлялся.

```python
from azarovo_martingale import GrowthDetector

det = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
steps = 0
while not det.update(30.0):  # устойчивый рост 30 МБ в секунду
    steps += 1
print(steps + 1)  # 18: тревога на 18-й секунде
```

## 3. Совместный планировщик

Планировщик объединяет интервал и детектор, как на рисунке 3 статьи. Результат
`decision` говорит о следующем интервале, о необходимости перераспределения и о том,
сработал ли детектор.

```python
from azarovo_martingale import MonitoringScheduler

sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
decision = sched.step(dx=0.0, reserve=512.0)  # потребление не изменилось
print(decision.interval, decision.redistribute)  # 71 False
decision = sched.step(dx=0.0, reserve=15.0)  # запас меньше c
print(decision.redistribute)  # True
```

## 4. Потоковый монитор

`VmMonitor` принимает показания по мере поступления. Первое показание задаёт
отправную точку; метод `due` говорит, когда ВМ следует снять показания в следующий раз.

```python
from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-01", c=20.0)
vm.record_measurement(0.0, used=2048.0, free=1352.0)
print(vm.next_check_time)  # 1.0
vm.record_measurement(1.0, used=2049.0, free=1351.0)
print(vm.interval, vm.due(100.0))  # 495 False
```

Без `c` монитор оценивает её по первым `warmup` приращениям (то есть по `warmup + 1` показаниям; по умолчанию `warmup = 50`) и до тех пор использует
консервативный `n_min`. См. [API](api.md).

## 5. Из командной строки

```sh
azarovo-martingale interval 512 20   # выводит 71
azarovo-martingale analyze log.csv --out results/run1
```

См. [командную строку](cli.md) и [формат журнала](log-format.md).
