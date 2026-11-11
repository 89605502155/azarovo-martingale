# azarovo-martingale

[![PyPI](https://img.shields.io/pypi/v/azarovo-martingale.svg)](https://pypi.org/project/azarovo-martingale/)
[![Python](https://img.shields.io/pypi/pyversions/azarovo-martingale.svg)](https://pypi.org/project/azarovo-martingale/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/89605502155/azarovo-martingale/blob/main/LICENSE)

**Martingale choice of the monitoring interval for virtual machine memory, with growth detectors that stay valid at any check moment.**

azarovo-martingale decides two things for a virtual machine (VM) under adaptive
memory management. First, how long the VM may be left unobserved, so that its
free memory reserve `R` is exhausted with probability at most `delta`. The
interval comes from the Azuma–Hoeffding inequality, formulas (7)–(9). Second,
whether the memory use has started to grow. A betting test (a test martingale)
watches for growth, and by Ville's inequality the probability of a false alarm
is at most `alpha` however often the test is looked at and however the check
moments were chosen. The two are combined in a scheduler that says when to
check the VM next and when to redistribute its memory.

The library is standard-library only at run time. It is meant to live inside a
control loop of a hypervisor. NumPy and matplotlib are needed only for the trace
plots (`azarovo-martingale[plot]`).

Русская версия: [README.ru.md](https://github.com/89605502155/azarovo-martingale/blob/main/README.ru.md).
Documentation: [English](https://github.com/89605502155/azarovo-martingale/tree/main/docs/en) ·
[Русский](https://github.com/89605502155/azarovo-martingale/tree/main/docs/ru) ·
[Changelog](https://github.com/89605502155/azarovo-martingale/blob/main/CHANGELOG.md) ·
[Issues](https://github.com/89605502155/azarovo-martingale/issues)

The library accompanies the article «Martingale approach to the choice of the
monitoring interval in the adaptive memory management of KVM virtual machines»
by Andrey Ferubko, Bryansk State Engineering-Technological University (BGITU)
(Брянский государственный инженерно-технологический университет). Its theory is
in [docs/en/theory.md](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/theory.md).

## Installation

```sh
pip install azarovo-martingale
# with the plots of the log analysis
pip install "azarovo-martingale[plot]"
# or, with uv
uv add azarovo-martingale
```

Requires Python 3.11 or newer.

## Quick start

```python
from azarovo_martingale import GrowthDetector, MonitoringScheduler, monitoring_interval

# Formula (9): free reserve 512 MiB, changes of at most 20 MiB per second, risk 1 %.
print(monitoring_interval(512, c=20.0, delta=0.01))  # 71 seconds

# Formulas (11)-(12): a steady rise of 30 MiB/s is detected after 18 seconds.
det = GrowthDetector(c=50.0, lam=0.5, alpha=0.01)
print(next(k for k in range(1, 100) if det.update(30.0)))  # 18

# Figure 3 of the article: one step of the joint scheduler.
sched = MonitoringScheduler(c=20.0, delta=0.01, alpha=0.01)
decision = sched.step(dx=0.0, reserve=512.0)
print(decision.interval, decision.redistribute)  # 71 False
```

A streaming monitor of several VMs, with state that survives a restart:

```python
from azarovo_martingale import FleetMonitor

fleet = FleetMonitor(n_vms=2, delta=0.02, alpha=0.02, c=20.0)  # risk shared by 2 VMs
decision = fleet.update("vm-1", t=0.0, used=2048.0, free=1352.0)
print(fleet.due(60.0))  # ['vm-1'] once its interval has passed
```

The command-line tool:

```sh
azarovo-martingale interval 512 20          # prints 71
azarovo-martingale detect log.csv --c 20    # growth alarms per VM
azarovo-martingale analyze log.csv --out results/run1 --plot
```

## What it computes

| Object | Article | What it does |
|---|---|---|
| `monitoring_interval(reserve, c, delta, n_max)` | formulas (7)–(9) | interval to the next check with risk `delta` |
| `azuma_bound`, `max_rise_bound` | formula (5), section 1.4 | the Azuma–Hoeffding bounds themselves |
| `GrowthDetector` | formulas (11), (12) | betting test for the start of growth, alarm at `1/alpha` |
| `CusumGrowthDetector` | formula (14) | CUSUM-type statistic, no delay after long calm periods |
| `MonitoringScheduler` | Fig. 3, steps 3–6 | the joint algorithm: detector, redistribution, interval |
| `estimate_c` | assumption A1 | the largest change per step from data, with quantile and margin |
| `VmMonitor`, `FleetMonitor` | Fig. 3 for streams | `update(t, used, free)` per VM, shared risk over a fleet |
| `read_log`, `analyse_log`, `render_markdown` | assumptions A1, A2, formula (6) | checks on a log, detectors, policy replay |

### Additions beyond the article

These are marked in the docstrings and in the reports.

* **`MixtureGrowthDetector`** (new). A uniform mixture of betting tests over a
  fixed grid of fractions `lam` (0.1 … 0.9). It needs no choice of `lam`, and it
  keeps Ville's guarantee because an average of test martingales is again one.
  On the synthetic examples it detects a fast rise after about 14 steps and a
  slow one after about 70, against 18 and 95 for the single bet with `lam = 0.5`
  (`examples/04_mixture_detector.py`).
* **`SubGaussianGrowthDetector`**. The variant from the earlier code of the
  author, built on the Azuma–Hoeffding bound of section 1.4. It is not in the
  text of the article, and it needs fewer checks at long intervals.

## How it differs from related tools

Change-point packages on PyPI, such as ocpdet, changepoint-online, cusum and
pydetect, implement CUSUM, EWMA and related tests for a series sampled at a fixed
rate. azarovo-martingale addresses a different problem, and the differences are
these.

* **It chooses when to sample next.** The interval comes from a risk bound on the
  reserve (formulas (7)–(9)), and the scheduler redistributes memory when a
  reserve is too small. The comparison tools take the samples as given.
* **Its false-alarm guarantee holds at any stopping time.** The detectors are test
  martingales, so by Ville's inequality the probability of a false alarm is at
  most `alpha` for any number of looks and for check moments chosen from the
  past. Threshold rules of fixed-sample tests lose this guarantee under repeated
  looks and adaptive, irregular sampling.
* **It works in log-capital.** Products of many factors underflow after hours of
  calm use; the detectors keep `ln K` and stay sensitive.
* **It is a per-VM streaming API with state.** `VmMonitor.update(t, used, free)`,
  a `FleetMonitor` for many VMs, and `to_dict`/`from_dict` for restarts.
* **It has a log analysis for real data.** `azarovo-martingale analyze` checks the
  assumptions of the guarantee on a log, measures false alarms and delays, and
  replays the policies without feedback.

The comparison is made from the descriptions of those packages in the author's
survey; it is not a benchmark. Compare the tools on your own data before you
choose.

## Log format

A CSV file with a header and one row per sample of one VM. Columns `time`,
`vm`, `used_mb` are required; `free_mb` (the reserve `R`) and `phase` (`growth`
marks a growth period) are optional. The delimiter (comma, semicolon or tab) is
detected, and a decimal comma is accepted. See
[docs/en/log-format.md](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/log-format.md).

## Documentation

* [Quick start](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/quickstart.md)
* [Theory in plain words](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/theory.md)
* [API](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/api.md)
* [Command-line tool](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/cli.md)
* [Log format](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/log-format.md)
* [Publishing](https://github.com/89605502155/azarovo-martingale/blob/main/docs/en/publishing.md)

Examples are in [examples/](https://github.com/89605502155/azarovo-martingale/tree/main/examples).
Heavy Monte Carlo studies are in [experiments/](https://github.com/89605502155/azarovo-martingale/tree/main/experiments) and are not run in CI.

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pytest -m slow     # the Monte Carlo tests, optional
scripts/install_hooks.sh  # the commit-message hook, once per clone
```

Commit subjects have at most 8 characters and no body; `scripts/check_commit_msg.py`
enforces it in the hook and in CI.

## Citation

See [CITATION.cff](https://github.com/89605502155/azarovo-martingale/blob/main/CITATION.cff).
Andrey Ferubko, Bryansk State Engineering-Technological University (BGITU), 2026.

## License

MIT. Copyright (c) 2026 Andrey Ferubko.
