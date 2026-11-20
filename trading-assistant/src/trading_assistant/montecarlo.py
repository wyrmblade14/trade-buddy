"""Seeded bootstrap of a strategy's per-bar returns.

Usage:
    python -m trading_assistant.montecarlo prices.csv [--paths N] [--seed S]
        [--short S] [--long L] [--strategy NAME] [--param KEY=VALUE]
        [--cash 10000] [--fee 0] [--fee-pct 0]

The backtest's per-bar returns are resampled with replacement into N new
paths of the same length. The report gives percentiles of the final return
and of the max drawdown across those paths, and the share of paths that lose
money. The same seed always gives the same report.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows, fewer than 2 bars, non-positive price)
    2  usage problem (--paths < 1, bad --seed, --cash <= 0, negative --fee,
       --fee-pct outside [0, 100), unknown strategy, malformed or unknown --param)

A bootstrap assumes returns are independent and does not predict the future.
This is a research aid. It does not place orders and it is not financial advice.
"""

import argparse
import random
import sys

from .cli import DISCLAIMER, load_price_table
from .drawdowns import add_backtest_options, backtest_from_args, validate_backtest_args

PERCENTILES = (5, 25, 50, 75, 95)
DEFAULT_PATHS = 1000
DEFAULT_SEED = 0
BOOTSTRAP_NOTE = "A bootstrap assumes returns are independent and does not predict the future."


def returns_from_equity(equity):
    """Per-bar returns ``equity[i] / equity[i - 1] - 1``. Raises ValueError if a divisor is not positive."""
    out = []
    for prev, cur in zip(equity, equity[1:]):
        if not prev > 0:
            raise ValueError("equity must be positive to compute returns")
        out.append(cur / prev - 1.0)
    return out


def percentile(sorted_values, q):
    """The ``q``-th percentile (0-100) of an ascending list, by linear interpolation between ranks.

    Rank is ``q / 100 * (n - 1)``. Raises ValueError for an empty list.
    """
    if not sorted_values:
        raise ValueError("no values to take a percentile of")
    rank = q / 100.0 * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (rank - lo)


def bootstrap_returns(per_bar_returns, n_paths=DEFAULT_PATHS, seed=DEFAULT_SEED, horizon=None):
    """Resample ``per_bar_returns`` with replacement into ``n_paths`` paths of ``horizon`` bars.

    ``horizon`` defaults to ``len(per_bar_returns)``. Each path starts at 1.0
    and multiplies by ``1 + r`` for each drawn return. Uses
    ``random.Random(seed)`` only, so the same arguments give the same result.
    Returns a dict:

    - ``n_paths``, ``horizon``, ``seed``;
    - ``final_return_pct``: ``{5: ..., 25: ..., 50: ..., 75: ..., 95: ...}``,
      percentiles of ``(final - 1) * 100`` across paths;
    - ``max_drawdown_pct``: the same percentiles of each path's worst
      peak-to-trough fall (<= 0, the start of 1.0 counts as a peak);
    - ``prob_loss_pct``: percent of paths that end below 1.0.

    Raises ValueError for no returns, ``n_paths < 1``, ``horizon < 1``, or a
    return of -100% or worse.
    """
    returns = list(per_bar_returns)
    if not returns:
        raise ValueError("need at least one return to bootstrap")
    if n_paths < 1:
        raise ValueError("n_paths must be at least 1")
    if horizon is None:
        horizon = len(returns)
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if any(not r > -1.0 for r in returns):
        raise ValueError("a return of -100% or worse cannot be bootstrapped")

    rng = random.Random(seed)
    n = len(returns)
    finals = []
    drawdowns = []
    for _ in range(n_paths):
        value = peak = 1.0
        worst = 0.0
        for _ in range(horizon):
            value *= 1.0 + returns[rng.randrange(n)]
            if value > peak:
                peak = value
            drop = (value - peak) / peak * 100.0
            if drop < worst:
                worst = drop
        finals.append((value - 1.0) * 100.0)
        drawdowns.append(worst)

    losses = sum(1 for f in finals if f < 0)
    finals.sort()
    drawdowns.sort()
    return {
        "n_paths": n_paths,
        "horizon": horizon,
        "seed": seed,
        "final_return_pct": {q: percentile(finals, q) for q in PERCENTILES},
        "max_drawdown_pct": {q: percentile(drawdowns, q) for q in PERCENTILES},
        "prob_loss_pct": losses / n_paths * 100.0,
    }


def format_report(summary):
    """Report lines for a ``bootstrap_returns`` summary."""
    lines = [
        f"Bootstrap: {summary['n_paths']} paths of {summary['horizon']} bars, seed {summary['seed']}",
        f"{'Percentile':>10s} {'Final return':>13s} {'Max drawdown':>13s}",
    ]
    for q in PERCENTILES:
        lines.append(
            f"{q:>10d} {summary['final_return_pct'][q]:>+12.2f}% {summary['max_drawdown_pct'][q]:>12.2f}%"
        )
    lines.append(f"Probability of a loss: {summary['prob_loss_pct']:.1f}% of paths end below the start")
    return lines


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.montecarlo",
        description="Bootstrap a backtest's per-bar returns into many possible paths.",
        epilog=DISCLAIMER,
    )
    add_backtest_options(parser)
    parser.add_argument("--paths", type=int, default=DEFAULT_PATHS, metavar="N", help="paths to draw (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, metavar="S", help="random seed (default: %(default)s)")
    return parser


def validate_args(parser, args):
    """Turn rule violations into usage errors (exit 2) and fill in defaults."""
    if args.paths < 1:
        parser.error("--paths must be at least 1")
    return validate_backtest_args(parser, args)


def main(argv=None):
    parser = build_parser()
    args = validate_args(parser, parser.parse_args(argv))

    try:
        _, closes = load_price_table(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not closes:
        print("No price rows found.", file=sys.stderr)
        return 1
    if len(closes) < 2:
        print("Error: a bootstrap needs at least 2 price rows", file=sys.stderr)
        return 1

    try:
        result = backtest_from_args(closes, args)
        summary = bootstrap_returns(returns_from_equity(result.equity_curve), n_paths=args.paths, seed=args.seed)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Strategy {result.strategy}, start cash {args.cash:,.2f}; historical return {result.return_pct:+.2f}%, "
          f"max drawdown {result.max_drawdown_pct:.2f}%")
    for line in format_report(summary):
        print(line)
    print(BOOTSTRAP_NOTE)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
