"""Command-line tool: ``azarovo-martingale <command> ...``.

Commands
--------
interval  the monitoring interval (7)-(9) for a reserve R and a bound c
detect    growth alarms of a detector on a monitoring log, for a given c
analyze   the full analysis of a monitoring log, written to a folder

Run ``azarovo-martingale <command> --help`` for the options. See ``docs/en/cli.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .analysis import AnalysisOptions, analyse_log, render_markdown, report_to_dict
from .detectors import (
    DEFAULT_BETS,
    CusumGrowthDetector,
    GrowthDetector,
    GrowthTest,
    MixtureGrowthDetector,
)
from .interval import monitoring_interval
from .logs import read_log

BETS_HELP = "mixture bet fractions in [0, 1), comma-separated (default 0.1,...,0.9)"
WEIGHTS_HELP = (
    "mixture weights, one per bet, comma-separated; normalised to sum 1 (default uniform)"
)


def _float_list(text: str) -> tuple[float, ...]:
    """Parse ``0.1,0.2,0.5`` into a tuple of floats (an argparse type)."""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as exc:
        msg = f"expected comma-separated numbers, got {text!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if not values:
        msg = "expected at least one number"
        raise argparse.ArgumentTypeError(msg)
    return values


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="azarovo-martingale",
        description="Martingale choice of the monitoring interval for VM memory.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("interval", help="monitoring interval (7)-(9) for R and c")
    p.add_argument("reserve", type=float, help="free memory reserve R, MiB")
    p.add_argument("c", type=float, help="largest change per base step, MiB")
    p.add_argument("--delta", type=float, default=0.01, help="admissible risk (default 0.01)")
    p.add_argument("--n-max", type=int, default=600, help="upper bound, steps (default 600)")

    p = sub.add_parser("detect", help="growth alarms of a detector on a monitoring log")
    p.add_argument("log", type=Path, help="CSV monitoring log")
    p.add_argument("--c", type=float, required=True, help="largest change per step, MiB")
    p.add_argument("--vm", default=None, help="VM name (default: every VM)")
    p.add_argument(
        "--detector",
        choices=("ville", "cusum", "mixture"),
        default="ville",
        help="ville = (11)-(12), cusum = (14), mixture = addition (default ville)",
    )
    p.add_argument("--lam", type=float, default=0.5, help="betting fraction (default 0.5)")
    p.add_argument("--alpha", type=float, default=0.01, help="false-alarm level (default 0.01)")
    p.add_argument("--cusum-threshold", type=float, default=1e5, help="level of (14)")
    p.add_argument("--step", type=float, default=1.0, help="base step, s (default 1)")
    p.add_argument("--sep", default=None, help="column delimiter (default: detected)")
    p.add_argument("--bets", type=_float_list, default=None, help=BETS_HELP)
    p.add_argument("--weights", type=_float_list, default=None, help=WEIGHTS_HELP)

    p = sub.add_parser("analyze", help="full analysis of a monitoring log")
    p.add_argument("log", type=Path, help="CSV monitoring log")
    p.add_argument(
        "--out", type=Path, default=None, help="output folder (default: results/<log name>)"
    )
    p.add_argument("--sep", default=None, help="column delimiter (default: detected)")
    p.add_argument("--step", type=float, default=1.0, help="base step, s (default 1)")
    p.add_argument("--delta", type=float, default=0.01, help="admissible risk (default 0.01)")
    p.add_argument("--alpha", type=float, default=0.01, help="false-alarm level (default 0.01)")
    p.add_argument("--lam", type=float, default=0.5, help="betting fraction (default 0.5)")
    p.add_argument("--n-min", type=int, default=1, help="interval after a redistribution")
    p.add_argument("--n-max", type=int, default=600, help="largest interval, steps (default 600)")
    p.add_argument("--fixed", default="1,5,10", help="fixed intervals to compare, steps")
    p.add_argument(
        "--c", type=float, default=None, help="use this c for the whole log (default: estimated)"
    )
    p.add_argument(
        "--train-frac",
        type=float,
        default=0.5,
        help="share of the log used to estimate c; 0 uses all (default 0.5)",
    )
    p.add_argument(
        "--c-quantile",
        type=float,
        default=1.0,
        help="quantile of the rates for c (1 = maximum, default)",
    )
    p.add_argument("--c-margin", type=float, default=1.2, help="safety margin for c (default 1.2)")
    p.add_argument(
        "--reserve",
        type=float,
        default=None,
        help="constant reserve, MiB, if the log has no free_mb column",
    )
    p.add_argument("--cusum-threshold", type=float, default=1e5, help="level of (14)")
    p.add_argument(
        "--grace",
        type=float,
        default=60.0,
        help="seconds after a growth period that still count as detection",
    )
    p.add_argument(
        "--split-risk", action="store_true", help="share delta and alpha evenly between the VMs"
    )
    p.add_argument("--plot", action="store_true", help="draw a trace per VM (needs the plot extra)")
    p.add_argument("--bets", type=_float_list, default=None, help=BETS_HELP)
    p.add_argument("--weights", type=_float_list, default=None, help=WEIGHTS_HELP)
    p.add_argument("--json", action="store_true", help="print the JSON report instead of Markdown")
    return parser


def _cmd_interval(args: argparse.Namespace) -> int:
    n = monitoring_interval(args.reserve, args.c, args.delta, args.n_max)
    print(n)
    return 0


def _make_detector(args: argparse.Namespace, c: float) -> GrowthTest:
    if args.detector == "cusum":
        return CusumGrowthDetector(c, args.lam, args.cusum_threshold)
    if args.detector == "mixture":
        bets = DEFAULT_BETS if args.bets is None else args.bets
        return MixtureGrowthDetector(c, args.alpha, bets, args.weights)
    return GrowthDetector(c, args.lam, args.alpha)


def _cmd_detect(args: argparse.Namespace) -> int:
    log = read_log(args.log, sep=args.sep)
    names = [args.vm] if args.vm is not None else sorted(log.vms)
    for name in names:
        if name not in log.vms:
            print(f"no VM {name!r} in the log", file=sys.stderr)
            return 2
        vm = log.vms[name]
        det = _make_detector(args, args.c)
        for k in range(1, len(vm)):
            dx = vm.used[k] - vm.used[k - 1]
            n = (vm.time[k] - vm.time[k - 1]) / args.step
            if det.update(dx, n):
                print(f"{name}\t{vm.time[k]:g}")
                det.reset()
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    fixed = tuple(int(x) for x in str(args.fixed).split(",") if x.strip())
    options = AnalysisOptions(
        step=args.step,
        delta=args.delta,
        alpha=args.alpha,
        lam=args.lam,
        n_min=args.n_min,
        n_max=args.n_max,
        fixed=fixed,
        c=args.c,
        train_frac=args.train_frac,
        c_quantile=args.c_quantile,
        c_margin=args.c_margin,
        reserve=args.reserve,
        cusum_threshold=args.cusum_threshold,
        grace=args.grace,
        split_risk=args.split_risk,
        bets=DEFAULT_BETS if args.bets is None else args.bets,
        weights=args.weights,
    )
    log = read_log(args.log, sep=args.sep)
    if not log.vms:
        print("the log has no samples", file=sys.stderr)
        return 2
    if not log.has_free and args.reserve is None:
        print("the log has no free_mb column: give --reserve, e.g. --reserve 512", file=sys.stderr)
        return 2
    reports = analyse_log(log, options)
    out_dir = args.out if args.out is not None else Path("results") / args.log.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(reports, options, log_name=args.log.name, has_phase=log.has_phase)
    (out_dir / "summary.md").write_text(markdown + "\n", encoding="utf-8")
    payload = report_to_dict(reports, options)
    (out_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.plot:
        from .plot import plot_trace

        for rep in reports:
            if rep.skipped is None:
                plot_trace(out_dir / f"trace_{_safe(rep.vm)}.png", log.vms[rep.vm], rep)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else markdown)
    print(f"Results saved to {out_dir}")
    return 0


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name) or "vm"


def _check_mixture_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Check ``--bets`` and ``--weights`` and normalise the weights, or exit with status 2."""
    if args.command == "detect" and args.detector != "mixture":
        if args.bets is not None or args.weights is not None:
            parser.error("--bets and --weights apply only to --detector mixture")
        return
    if args.command not in ("detect", "analyze") or args.weights is None:
        return
    bets = DEFAULT_BETS if args.bets is None else args.bets
    if len(args.weights) != len(bets):
        parser.error(
            f"--weights needs one value per bet: {len(args.weights)} weights for {len(bets)} bets"
        )
    total = math.fsum(args.weights)
    if not (math.isfinite(total) and total > 0.0):
        parser.error("--weights must have a positive sum")
    args.weights = tuple(w / total for w in args.weights)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line tool and return the exit status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    _check_mixture_args(parser, args)
    handlers = {"interval": _cmd_interval, "detect": _cmd_detect, "analyze": _cmd_analyze}
    try:
        return handlers[args.command](args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
