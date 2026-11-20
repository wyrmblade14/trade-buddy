"""Drawdown episodes: every peak-to-trough-to-recovery fall in an equity curve.

Usage:
    python -m trading_assistant.drawdowns prices.csv [--top N] [--of buyhold|strategy]
        [--short S] [--long L] [--strategy NAME] [--param KEY=VALUE]
        [--cash 10000] [--fee 0] [--fee-pct 0]

The curve is the account value per bar of a backtest (``--of strategy``, the
default) or of buy-and-hold (``--of buyhold``). The table lists the deepest
episodes first (default 5). The backtest options match the main command;
--short and --long apply to the SMA crossover only.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows, non-positive price)
    2  usage problem (--top < 1, --cash <= 0, negative --fee, --fee-pct outside
       [0, 100), unknown strategy, malformed or unknown --param, bad windows)

Past drawdowns say nothing certain about future ones. This is a research aid.
It does not place orders and it is not financial advice.
"""

import argparse
import sys

from .backtest import run_backtest
from .cli import DEFAULT_CASH, DISCLAIMER, check_costs, load_price_table, parse_param
from .strategies import resolve_params, strategy_names

DEFAULT_STRATEGY = "sma_cross"
DEFAULT_TOP = 5


def drawdown_periods(equity, dates=None):
    """Every drawdown episode in ``equity``, in time order.

    An episode starts at a peak (the latest bar whose value is the highest so
    far), runs while the value stays below that peak, and ends at the first
    bar whose value is at or above the peak. Each episode is a dict:

    - ``peak_bar``, ``peak_date``: the bar of the peak;
    - ``trough_bar``, ``trough_date``: the lowest bar of the episode (the first
      one if the low repeats);
    - ``recovery_bar``, ``recovery_date``: the first bar back at the peak value,
      or None if the curve never got back;
    - ``depth_pct``: ``(trough / peak - 1) * 100``, a negative number;
    - ``length_bars``: ``trough_bar - peak_bar``;
    - ``recovery_bars``: ``recovery_bar - trough_bar``, or None if not recovered.

    ``dates`` is optional; when given it must have one entry per bar, and the
    ``*_date`` values come from it (otherwise they are None). A peak that is
    zero or negative cannot be measured and starts no episode. An empty or
    never-falling curve gives an empty list. Raises ValueError if ``dates``
    and ``equity`` differ in length.
    """
    if dates is not None and len(dates) != len(equity):
        raise ValueError(f"got {len(dates)} dates for {len(equity)} equity values")

    def date_at(bar):
        return None if dates is None or bar is None else dates[bar]

    def close(peak_bar, trough_bar, recovery_bar):
        return {
            "peak_bar": peak_bar,
            "peak_date": date_at(peak_bar),
            "trough_bar": trough_bar,
            "trough_date": date_at(trough_bar),
            "recovery_bar": recovery_bar,
            "recovery_date": date_at(recovery_bar),
            "depth_pct": (equity[trough_bar] / equity[peak_bar] - 1.0) * 100.0,
            "length_bars": trough_bar - peak_bar,
            "recovery_bars": None if recovery_bar is None else recovery_bar - trough_bar,
        }

    episodes = []
    peak_bar = None
    trough_bar = None  # set while an episode is open
    for i, value in enumerate(equity):
        if peak_bar is None or value >= equity[peak_bar]:
            if trough_bar is not None:
                episodes.append(close(peak_bar, trough_bar, i))
                trough_bar = None
            peak_bar = i
        elif equity[peak_bar] > 0:
            if trough_bar is None or value < equity[trough_bar]:
                trough_bar = i
    if trough_bar is not None:
        episodes.append(close(peak_bar, trough_bar, None))
    return episodes


def top_drawdowns(equity, dates=None, n=5):
    """The ``n`` deepest episodes of ``drawdown_periods``, deepest first.

    Ties in depth go to the earlier peak. Raises ValueError if ``n < 1``.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    episodes = drawdown_periods(equity, dates)
    episodes.sort(key=lambda e: (e["depth_pct"], e["peak_bar"]))
    return episodes[:n]


# ---------------------------------------------------------------- shared CLI
# montecarlo.py reuses these so both commands take the same backtest options.


def add_backtest_options(parser):
    """Add the csv_path argument and the backtest options to ``parser``."""
    parser.add_argument("csv_path", help="CSV file with a 'close' column")
    parser.add_argument("--short", type=int, default=None, help="short SMA window (sma_cross only, default: 20)")
    parser.add_argument("--long", type=int, default=None, help="long SMA window (sma_cross only, default: 50)")
    parser.add_argument(
        "--strategy", choices=strategy_names(), default=None, help=f"rule to backtest (default: {DEFAULT_STRATEGY})"
    )
    parser.add_argument(
        "--param", action="append", default=None, metavar="KEY=VALUE", help="override a strategy parameter (repeatable)"
    )
    parser.add_argument(
        "--cash", type=float, default=None, metavar="AMOUNT", help=f"starting cash (default: {DEFAULT_CASH:,.0f})"
    )
    parser.add_argument("--fee", type=float, default=None, metavar="AMOUNT", help="fixed cost per trade (default: 0)")
    parser.add_argument(
        "--fee-pct", type=float, default=None, metavar="PCT", help="percent of traded value per trade (default: 0)"
    )


def validate_backtest_args(parser, args):
    """Turn bad backtest options into usage errors (exit 2) and fill in defaults.

    Sets ``args.strategy_params`` to the validated overrides, built from
    --short, --long and --param.
    """
    try:
        check_costs(args.cash, args.fee, args.fee_pct)
    except ValueError as exc:
        parser.error(str(exc))
    if args.strategy is None:
        args.strategy = DEFAULT_STRATEGY
    overrides = {}
    try:
        for text in args.param or []:
            key, value = parse_param(text)
            if key in overrides:
                raise ValueError(f"--param {key} given more than once")
            overrides[key] = value
        for key in ("short", "long"):
            given = getattr(args, key)
            if given is None:
                continue
            if args.strategy != "sma_cross":
                raise ValueError(f"--{key} only applies to the sma_cross strategy; use --param")
            if key in overrides and overrides[key] != given:
                raise ValueError(f"--param {key}={overrides[key]} contradicts --{key} {given}; give only one")
            overrides[key] = given
        resolve_params(args.strategy, overrides)
    except ValueError as exc:
        parser.error(str(exc))
    args.strategy_params = overrides
    if args.cash is None:
        args.cash = DEFAULT_CASH
    if args.fee is None:
        args.fee = 0.0
    if args.fee_pct is None:
        args.fee_pct = 0.0
    return args


def backtest_from_args(closes, args):
    """Run the backtest the options describe. Raises ValueError as ``run_backtest`` does."""
    return run_backtest(
        closes,
        initial_cash=args.cash,
        fee=args.fee,
        fee_pct=args.fee_pct,
        strategy=args.strategy,
        strategy_params=args.strategy_params,
    )


# ---------------------------------------------------------------------- CLI


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.drawdowns",
        description="List the deepest drawdown episodes of a backtest or of buy-and-hold.",
        epilog=DISCLAIMER,
    )
    add_backtest_options(parser)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, metavar="N", help="episodes to show (default: %(default)s)")
    parser.add_argument(
        "--of", choices=("buyhold", "strategy"), default="strategy", help="which curve to measure (default: %(default)s)"
    )
    return parser


def validate_args(parser, args):
    """Turn rule violations into usage errors (exit 2) and fill in defaults."""
    if args.top < 1:
        parser.error("--top must be at least 1")
    return validate_backtest_args(parser, args)


def _where(bar, date):
    return f"bar {bar}" if date is None else date


def format_table(episodes):
    """Aligned table lines for ``episodes`` (dicts from ``drawdown_periods``)."""
    rows = [("#", "Peak", "Trough", "Recovered", "Depth", "Down", "Recovery")]
    for k, e in enumerate(episodes, 1):
        recovered = "not recovered" if e["recovery_bar"] is None else _where(e["recovery_bar"], e["recovery_date"])
        back = "-" if e["recovery_bars"] is None else f"{e['recovery_bars']} bars"
        rows.append(
            (
                str(k),
                _where(e["peak_bar"], e["peak_date"]),
                _where(e["trough_bar"], e["trough_date"]),
                recovered,
                f"{e['depth_pct']:.2f}%",
                f"{e['length_bars']} bars",
                back,
            )
        )
    widths = [max(len(r[c]) for r in rows) for c in range(7)]
    return [
        "  ".join(cell.ljust(w) if c in (1, 2, 3) else cell.rjust(w) for c, (cell, w) in enumerate(zip(r, widths))).rstrip()
        for r in rows
    ]


def main(argv=None):
    parser = build_parser()
    args = validate_args(parser, parser.parse_args(argv))

    try:
        dates, closes = load_price_table(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not closes:
        print("No price rows found.", file=sys.stderr)
        return 1

    try:
        result = backtest_from_args(closes, args)
        curve = result.equity_curve if args.of == "strategy" else result.benchmark.equity_curve
        all_episodes = drawdown_periods(curve, dates)
        shown = top_drawdowns(curve, dates, args.top)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    label = f"strategy {result.strategy}" if args.of == "strategy" else "buy and hold"
    print(f"Drawdowns of {label} on {len(closes)} bars, start cash {args.cash:,.2f}")
    if not shown:
        print("No drawdowns: the curve never fell below an earlier peak.")
    else:
        for line in format_table(shown):
            print(line)
        if len(shown) < len(all_episodes):
            print(f"(showing the deepest {len(shown)} of {len(all_episodes)})")
        if any(e["recovery_bar"] is None for e in shown):
            print("A drawdown that is not recovered was still open at the last bar.")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
