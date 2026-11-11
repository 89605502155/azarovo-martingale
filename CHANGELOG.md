# Changelog

All notable changes of azarovo-martingale are documented here. The project follows
[Semantic Versioning](https://semver.org). Russian summary: the same entries
apply; the documentation is in `docs/ru/`.

## 0.1.0 — 2026-11-11

First release: the methods of the article on the martingale choice of the
monitoring interval of KVM virtual machines (A. Ferubko, BGITU).

* Monitoring interval from the Azuma–Hoeffding inequality with risk `delta`
  (`monitoring_interval`, formulas (7)–(9); `azuma_bound` and `max_rise_bound`
  for formula (5)).
* Growth detectors as test martingales with Ville's guarantee: `GrowthDetector`
  (formulas (11), (12)) and `CusumGrowthDetector` (formula (14)), in log-capital.
* `MonitoringScheduler`, the joint algorithm of Fig. 3 (steps 3–6), with the
  decision as a `Decision` object.
* `estimate_c` for assumption A1, with a quantile and a safety margin, and
  `exceedance_share` to check it on data.
* Streaming monitors: `VmMonitor` (`update(t, used, free)`, `due`, calibration of
  `c` from the first readings) and `FleetMonitor` (several VMs, risk shared by
  Boole's inequality), with JSON-serialisable state for restarts.
* Log analysis: `read_log` (CSV with detected delimiter and decimal comma),
  `analyse_log` (checks of A1 and A2, the guarantee (6), detectors with false
  alarms and delays, replay of the policies), `render_markdown` and `report_to_dict`.
* Command-line tool `azarovo-martingale` with `interval`, `detect` and `analyze`.
* Additions beyond the article, marked as such: `MixtureGrowthDetector` (a mixture
  of bets over a grid of fractions, no tuned `lam`) and `SubGaussianGrowthDetector`
  (sub-Gaussian bets, the variant of the earlier code).
* Optional trace plots (`azarovo-martingale[plot]`).
* Documentation in English and Russian, five examples, tests (fast; Monte Carlo
  tests are marked `slow`).
