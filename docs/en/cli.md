# Command-line tool

[Русская версия](../ru/cli.md)

The tool is installed as `azarovo-martingale`. Each command has `--help`.

```sh
azarovo-martingale --version
```

## `interval`: the monitoring interval

```sh
azarovo-martingale interval 512 20               # prints 71
azarovo-martingale interval 512 20 --delta 0.05  # a larger risk, a longer interval
azarovo-martingale interval 512 20 --n-max 60    # capped at 60 steps
```

Arguments: the free reserve `R` in MiB, and `c` in MiB per step. The output is the
interval in base steps, `0` if `R <= c`.

## `detect`: growth alarms on a log

```sh
azarovo-martingale detect log.csv --c 20                   # formula (11), (12)
azarovo-martingale detect log.csv --c 20 --vm vm-01        # one VM
azarovo-martingale detect log.csv --c 20 --detector cusum  # formula (14)
azarovo-martingale detect log.csv --c 20 --detector mixture
azarovo-martingale detect log.csv --c 20 --detector mixture --bets 0.05,0.1,0.2 --weights 1,1,2
```

The output is one line per alarm: `vm-name<TAB>time`. The detector is run over the
whole log with a restart after each alarm. `--c` is required, because the detector
needs the bound on the change per step (see `analyze` to estimate it).

With `--detector mixture`, `--bets` sets the grid of bet fractions and `--weights`
the weight of each bet in the mixture, both comma-separated. The defaults are the
bets 0.1, …, 0.9 with equal weights. The weights are normalised to sum 1, so
`1,1,2` means `0.25,0.25,0.5`. There must be one weight per bet. The options are
refused with the other detectors, and `analyze` takes the same two options.

## `analyze`: the full analysis of a log

```sh
azarovo-martingale analyze log.csv --out results/run1
azarovo-martingale analyze log.csv --out results/run1 --plot   # needs the plot extra
azarovo-martingale analyze log.csv --json                     # JSON to stdout
azarovo-martingale analyze log.csv --reserve 512              # no free_mb column
```

It writes `summary.md` and `summary.json` to the output folder (default
`results/<log name>`), prints the Markdown report, and with `--plot` writes one
`trace_<vm>.png` per VM. The options:

| Option | Default | Meaning |
|---|---|---|
| `--delta` | 0.01 | admissible risk of exhausting the reserve |
| `--alpha` | 0.01 | admissible false-alarm probability |
| `--lam` | 0.5 | betting fraction of formula (11) |
| `--n-min`, `--n-max` | 1, 600 | interval after a redistribution and its upper bound, steps |
| `--fixed` | 1,5,10 | fixed intervals to compare, steps, comma-separated |
| `--c` | estimated | use this `c` for the whole log |
| `--train-frac` | 0.5 | share of the log used to estimate `c`; 0 uses the whole log |
| `--c-quantile`, `--c-margin` | 1, 1.2 | quantile of the rates and safety margin for `c` |
| `--reserve` | none | constant reserve in MiB if the log has no `free_mb` column |
| `--cusum-threshold` | 1e5 | level of formula (14) |
| `--grace` | 60 | seconds after a growth period that still count as a detection |
| `--step` | 1 | base step in seconds |
| `--split-risk` | off | share `delta` and `alpha` evenly between the VMs |
| `--bets` | 0.1,…,0.9 | mixture detector: bet fractions in `[0, 1)`, comma-separated |
| `--weights` | equal | mixture detector: one weight per bet, normalised to sum 1 |
| `--sep` | detected | column delimiter |
| `--plot` | off | draw a trace per VM |
| `--json` | off | print JSON instead of Markdown |

## Exit status

`0` on success. `2` for an error in the arguments or the data, with a message on
standard error.
