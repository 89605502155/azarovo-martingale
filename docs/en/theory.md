# Theory in plain words

[Русская версия](../ru/theory.md)

The package answers two questions for a virtual machine (VM) whose memory use
`x_n` changes over time: how long can it be left unobserved, and has its use
started to grow? The answers come from martingales, which are fair games. This
page explains the ideas; the derivations are in the article.

## 1. A fair game and a supermartingale

Imagine a player who bets on a coin. Every head pays one unit and every tail takes
one. On average the capital does not change: this is a martingale. A game that is
on average unfavourable is a supermartingale. Assume that the memory use does not
grow on average. Then the use behaves like a supermartingale: knowing the past,
its expected next change is not positive.

```text
E[x_n - x_{n-1} | past] <= 0          assumption A2, calm use
|x_n - x_{n-1}| <= c                  assumption A1, bounded change per step
```

## 2. The monitoring interval: how long can we wait?

The free reserve `R` is exhausted when the use rises by `R` within the interval.
For a supermartingale with bounded steps, the Azuma–Hoeffding inequality (5) says
that the rise stays small with high probability, and that a typical rise grows like
`c sqrt(n)`, not `c n`:

```text
P(rise by R or more within n steps) <= exp(-R^2 / (2 n c^2))        formula (5)
```

Solving for the largest `n` with this probability at most `delta` gives the
interval `n_A` of formula (7). The worst case, where every step rises by `c`,
gives the deterministic interval `n_0 = ceil(R / c) - 1` of formula (8). The
package takes the larger of the two, capped by `n_max`, as in formula (9).

| Reserve R, MiB | c, MiB/s | Interval, s (delta = 0.01) |
|---|---|---|
| 512 | 20 | 71 |
| 1024 | 20 | 284 |
| 512 | 50 | 11 |

If `R <= c`, the interval is `0`: one step can already exhaust the reserve.

## 3. Betting against growth

To notice that growth has started, the package bets against it. The imaginary
player stakes a fraction `lam` of the capital on each step's change, scaled to
[-1, 1] by `c`. If there is no growth, the capital cannot systematically increase.
If the use grows, the capital does.

```text
K_0 = 1,    K_n = K_{n-1} (1 + lam Y_n),    Y_n = change / (n c), clipped to [-1, 1]   formula (11)
alarm when K_n >= 1 / alpha                                                           formula (12)
```

Ville's inequality says that a non-negative supermartingale that starts at 1 ever
reaches `1/alpha` with probability at most `alpha`. This holds for any number of
looks, and for checks scheduled from the past. A fixed-sample test would lose this
guarantee when it is applied again and again. That is why the detector can be
read at irregular moments, as the scheduler needs.

The capital is kept as its logarithm `ln K`. A product of many factors underflows
to zero after hours of calm use, and the detector would then stop reacting.

## 4. The long calm period and the CUSUM variant

During a long calm period the capital of a single bet drifts towards zero, because
the bet loses on average. When growth starts, the detector must first climb out of
that hole, and the delay grows. Formula (14) fixes this with a CUSUM-type statistic
that never falls below `1 - lam`:

```text
C_n = max(C_{n-1}, 1) (1 + lam Y_n)                                                  formula (14)
```

The guarantee is different: the mean time to a false alarm is at least the
threshold `A`, not a probability. A threshold of `1e5` steps means about one false
alarm per 28 hours on average, for a step of one second.

## 5. Additions beyond the article

* **Mixture of bets** (`MixtureGrowthDetector`). Average the capitals of bets with
  several fractions `lam`, with equal weights. Each bet is a test martingale, and so
  is their average. The guarantee of Ville therefore holds, and no `lam` has to be
  chosen. The price is a penalty of about `log(9) = 2.2` in the log capital for nine
  bets.
* **Sub-Gaussian bets** (`SubGaussianGrowthDetector`). A variant of the earlier code
  built on the Azuma–Hoeffding bound. A single update moves the capital by an amount
  that grows with `sqrt(n)`, which helps when the checks are far apart.

## 6. Several VMs

If `m` VMs share the risk `delta`, give each VM the risk `delta / m`. By Boole's
inequality the probability that any VM exhausts its reserve before its next check
is then at most `delta`. `FleetMonitor(n_vms=m, delta=...)` does this.

## 7. What the guarantees need

The guarantees hold if assumptions A1 and A2 hold. Check them on the data with
`azarovo-martingale analyze`: the share of increments above `c`, the mean increment
in calm use, and its autocorrelation. A bound `c` that is too small makes the
interval too long; a drift in calm use makes the false-alarm rate higher than
`alpha`. The reports show both.

## References

The article: A. Ferubko, «Martingale approach to the choice of the monitoring
interval in the adaptive memory management of KVM virtual machines». The
inequalities: Ville (1939), Azuma (1967), Hoeffding (1963); the betting view of
Shafer and Vovk and of Ramdas et al. (2023).
