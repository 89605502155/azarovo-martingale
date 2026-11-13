# Changelog

All notable changes of azarovo-martingale are documented here. The project follows
[Semantic Versioning](https://semver.org). Russian summary: the same entries
apply; the documentation is in `docs/ru/`.

## [0.0.1] — 2026-11-11 (revised 2026-11-14, same version)

* Calibration of `c` (`VmMonitor`, `FleetMonitor`, `analyse_log`) uses only increments over
  exactly one base step. Earlier versions divided the change over an interval by its length,
  which underestimates the largest one-step change that A1 bounds.
* Option `clip` (default `True`) of the growth detectors, `MonitoringScheduler`, `VmMonitor`
  and `FleetMonitor`: with `clip=False` a change violating A1 raises `ValueError`.
* `VmMonitor.calibration_samples`: number of one-step increments in the calibration window.
* Log analysis: the one-step check of A1 (share of rates above `c`, largest rate) uses
  one-step increments only.

First release: the methods of the article on the martingale choice of the
monitoring interval of KVM virtual machines (A. Ferubko and O. Kazakov, BGITU).

* Monitoring interval from the Azuma–Hoeffding inequality with risk `delta`
  (`monitoring_interval`, formulas (7)–(9); `azuma_bound` and `max_rise_bound`
  for formula (5)).
* Growth detectors as test martingales with Ville's guarantee: `GrowthDetector`
  (formulas (11), (12)) and `CusumGrowthDetector` (formula (14)), in log-capital.
* `MonitoringScheduler`, the joint algorithm of Fig. 3 (steps 3–6), with the
  decision as a `Decision` object.
* `estimate_c` for assumption A1, with a quantile and a safety margin, and
  `exceedance_share` to check it on data.
* Streaming monitors: `VmMonitor` (`record_measurement(t, used, free)`, `due`, calibration of
  `c` from the first readings) and `FleetMonitor` (several VMs, risk shared by
  Boole's inequality), with JSON-serialisable state for restarts.
* Log analysis: `read_log` (CSV with detected delimiter and decimal comma),
  `analyse_log` (checks of A1 and A2, the guarantee (6), detectors with false
  alarms and delays, replay of the policies), `render_markdown` and `report_to_dict`.
* Command-line tool `azarovo-martingale` with `interval`, `detect` and `analyze`.
* Options `--bets` and `--weights` of the mixture detector in `detect` and `analyze`
  (comma-separated; weights normalised to sum 1; `AnalysisOptions.bets` and `weights`).
* `record_measurement(t, used, free)` on `VmMonitor` and `record_measurement(vm, t, used, free)`
  on `FleetMonitor` record one measurement and return the `Decision`.
* `validate_measurement(t, used, free, last_t=None)`: the one check of incoming data.
  Non-real values (booleans, strings, `None`) raise `TypeError`; NaN, infinity,
  negative values and non-increasing time raise `ValueError`. Used by the monitors.
* Additions beyond the article, marked as such: `MixtureGrowthDetector` (a weighted
  mixture of bets over a grid of fractions, no tuned `lam`; the grid `lams` and the
  weights are constructor parameters, the weights sum to 1; the scheduler and
  `VmMonitor` take `weights` too) and `SubGaussianGrowthDetector` (sub-Gaussian
  bets, the variant of the earlier code).
* Optional trace plots (`azarovo-martingale[plot]`).
* The calibration window of `VmMonitor` and `FleetMonitor` is the parameter `warmup`
  (default 50 increments, at least 2; `warmup + 1` readings are needed). The article
  and the demo notebook set it to 20 explicitly.
* Documentation in English and Russian, five examples, tests (fast; Monte Carlo
  tests are marked `slow`).
