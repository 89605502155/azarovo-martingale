# azarovo-martingale

[![PyPI](https://img.shields.io/pypi/v/azarovo-martingale.svg)](https://pypi.org/project/azarovo-martingale/)
[![Python](https://img.shields.io/pypi/pyversions/azarovo-martingale.svg)](https://pypi.org/project/azarovo-martingale/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/89605502155/azarovo-martingale/blob/main/LICENSE)

**Мартингальный выбор интервала мониторинга памяти виртуальных машин с детекторами роста, которые остаются верными в любой момент проверки.**

azarovo-martingale решает две задачи для виртуальной машины (ВМ) в адаптивной
системе управления памятью. Первая: как долго можно не проверять ВМ, чтобы её
свободный запас памяти `R` исчерпался с вероятностью не выше `delta`. Интервал
получается из неравенства Азумы–Хёфдинга, формулы (7)–(9). Вторая: не начался
ли рост потребления памяти. Тест мартингала (проверка гипотезы ставками) следит
за ростом, а по неравенству Вилля вероятность ложной тревоги не превышает `alpha`,
сколько бы раз тест ни проверялся и как бы ни выбирались моменты проверок.
Оба метода объединены в планировщике, который говорит, когда проверить ВМ в
следующий раз и когда перераспределить её память.

В рабочем режиме библиотека использует только стандартную библиотеку Python. Её
предназначение — работать внутри цикла управления гипервизора. NumPy и matplotlib
нужны только для графиков журнала (`azarovo-martingale[plot]`).

English version: [README.md](https://github.com/89605502155/azarovo-martingale/blob/main/README.md).
Документация: [English](https://github.com/89605502155/azarovo-martingale/tree/main/docs/en) ·
[Русский](https://github.com/89605502155/azarovo-martingale/tree/main/docs/ru) ·
[Changelog](https://github.com/89605502155/azarovo-martingale/blob/main/CHANGELOG.md) ·
[Issues](https://github.com/89605502155/azarovo-martingale/issues)

Библиотека сопровождает статью «Мартингальный подход к выбору интервала
мониторинга в адаптивной системе управления памятью виртуальных машин KVM»
Андрея Ферубко и Олега Казакова, Брянский государственный инженерно-технологический университет
(BGITU). Теория изложена в
[docs/ru/theory.md](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/theory.md).

## Установка

```sh
pip install azarovo-martingale
# с графиками журнала
pip install "azarovo-martingale[plot]"
# или с uv
uv add azarovo-martingale
```

Нужен Python 3.11 или новее.

## Быстрый старт

```python
from azarovo_martingale import GrowthDetector, MonitoringScheduler, monitoring_interval

# Формула (9): свободный запас 512 МБ, приращения не более 20 МБ в секунду, риск 1 %.
print(monitoring_interval(512, c=20.0, delta=0.01))  # 71 секунда

# Формулы (11)-(12): устойчивый рост 30 МБ/с обнаруживается через 18 секунд.
det = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
print(next(k for k in range(1, 100) if det.update(30.0)))  # 18

# Рисунок 3 статьи: один шаг совместного планировщика.
sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
decision = sched.step(dx=0.0, reserve=512.0)
print(decision.interval, decision.redistribute)  # 71 False
```

Потоковый монитор нескольких ВМ, состояние которого переживает перезапуск:

```python
from azarovo_martingale import FleetMonitor

fleet = FleetMonitor(n_vms=2, delta=0.02, alpha=0.02, c=20.0)  # риск делят 2 ВМ
decision = fleet.record_measurement("vm-1", t=0.0, used=2048.0, free=1352.0)
print(fleet.due(60.0))  # ['vm-1'], когда интервал ВМ истёк
```

Командная строка:

```sh
azarovo-martingale interval 512 20          # выводит 71
azarovo-martingale detect log.csv --c 20    # тревоги роста по ВМ
azarovo-martingale analyze log.csv --out results/run1 --plot
```

## Что вычисляется

| Объект | Статья | Что делает |
|---|---|---|
| `monitoring_interval(reserve, c, delta, n_max)` | формулы (7)–(9) | интервал до следующей проверки при риске `delta` |
| `azuma_bound`, `max_rise_bound` | формула (5), п. 1.4 | сами границы Азумы–Хёфдинга |
| `GrowthDetector` | формулы (11), (12) | проверка ставками на начало роста, тревога при `1/alpha` |
| `CusumGrowthDetector` | формула (14) | статистика типа CUSUM, без задержки после долгого покоя |
| `MonitoringScheduler` | рис. 3, этапы 3–6 | совместный алгоритм: детектор, перераспределение, интервал |
| `estimate_c` | допущение А1 | наибольшее приращение за шаг по данным, с квантилем и запасом |
| `VmMonitor`, `FleetMonitor` | рис. 3 для потоков | `record_measurement(t, used, free)` для ВМ, общий риск на парк |
| `read_log`, `analyse_log`, `render_markdown` | допущения А1, А2, формула (6) | проверки по журналу, детекторы, воспроизведение политик |

### Дополнения сверх статьи

Они отмечены в документации и в отчётах.

* **`MixtureGrowthDetector`** (новое). Равновзвешенная смесь проверок ставками по
  фиксированной сетке долей `lam` (по умолчанию от 0,1 до 0,9; сетка `lams` и веса
  `weights` — параметры конструктора). Не нужно выбирать `lam`, а
  гарантия Вилля сохраняется, потому что среднее мартингалов снова является
  мартингалом. На синтетических примерах быстрый рост обнаруживается примерно за
  14 шагов, медленный — примерно за 70; одиночная ставка с `lam = 0,5` даёт 18 и 95
  (`examples/04_mixture_detector.py`).
* **`SubGaussianGrowthDetector`**. Вариант из более раннего кода автора, основанный
  на границе Азумы–Хёфдинга из п. 1.4. В тексте статьи его нет. На длинных
  интервалах нужно меньше проверок.

## Чем отличается от родственных инструментов

Пакеты для обнаружения разладки на PyPI, например ocpdet, changepoint-online, cusum
и pydetect, реализуют CUSUM, EWMA и родственные критерии для ряда, снятого с
фиксированной частотой. azarovo-martingale решает другую задачу, и отличия такие.

* **Он выбирает, когда снимать показания в следующий раз.** Интервал получается
  из границы риска запаса памяти (формулы (7)–(9)), а планировщик перераспределяет
  память, когда запас мал. Сравниваемые инструменты принимают отсчёты как данные.
* **Гарантия ложных тревог верна в любой момент остановки.** Детекторы —
  тестовые мартингалы, поэтому по неравенству Вилля вероятность ложной тревоги не
  превышает `alpha` при любом числе проверок и при моментах, выбранных по прошлому.
  Пороговые правила классических тестов при повторных проверках и нерегулярной
  выборке эту гарантию теряют.
* **Он работает с логарифмом капитала.** Произведение многих множителей обращается
  в ноль после нескольких часов покоя; детекторы хранят `ln K` и остаются чувствительными.
* **Это потоковый API по ВМ с состоянием.** `VmMonitor.record_measurement(t, used, free)`,
  `FleetMonitor` для парка ВМ, а также `to_dict`/`from_dict` для перезапуска.
* **Есть анализ журналов реальных данных.** `azarovo-martingale analyze` проверяет
  допущения гарантии по журналу, считает ложные тревоги и задержки и воспроизводит
  политики без обратной связи.

Сравнение сделано по описаниям этих пакетов из обзора автора; это не бенчмарк.
Сравните инструменты на своих данных, прежде чем выбирать.

## Формат журнала

CSV-файл с заголовком и строкой на каждый отсчёт одной ВМ. Обязательны столбцы
`time`, `vm`, `used_mb`; `free_mb` (запас `R`) и `phase` (`growth` отмечает
участок роста) необязательны. Разделитель (запятая, точка с запятой или табуляция)
определяется автоматически, десятичная запятая допускается. См.
[docs/ru/log-format.md](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/log-format.md).

## Документация

* [Быстрый старт](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/quickstart.md)
* [Теория простыми словами](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/theory.md)
* [API](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/api.md)
* [Командная строка](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/cli.md)
* [Формат журнала](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/log-format.md)
* [Публикация](https://github.com/89605502155/azarovo-martingale/blob/main/docs/ru/publishing.md)

Примеры — в папке [examples/](https://github.com/89605502155/azarovo-martingale/tree/main/examples).
Тяжёлые имитационные исследования — в [experiments/](https://github.com/89605502155/azarovo-martingale/tree/main/experiments), по умолчанию они не запускаются.

## Разработка

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pytest -m slow     # имитационные тесты, по желанию
scripts/install_hooks.sh  # хук сообщений коммитов, один раз в каждом клоне
```

Заголовок коммита не длиннее 8 символов и без тела; `scripts/check_commit_msg.py`
проверяет это в локальном хуке.

## Авторы

- Андрей Ферубко (Andrey Ferubko), Брянский государственный инженерно-технологический университет (БГИТУ),
  [ORCID 0009-0006-5625-137X](https://orcid.org/0009-0006-5625-137X), ferubko1999@yandex.ru
- Олег Казаков (Oleg Kazakov), Брянский государственный инженерно-технологический университет (БГИТУ),
  [ORCID 0000-0001-9665-8138](https://orcid.org/0000-0001-9665-8138), kazakov@bgitu.ru

## Цитирование

См. [CITATION.cff](https://github.com/89605502155/azarovo-martingale/blob/main/CITATION.cff).
Андрей Ферубко и Олег Казаков, Брянский государственный инженерно-технологический университет (BGITU), 2026.

## Лицензия

MIT. Copyright (c) 2026 Andrey Ferubko, Oleg Kazakov.
