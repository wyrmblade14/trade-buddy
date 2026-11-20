"""Parameter sweep: backtest every (short, long) SMA window pair on one price file.

Usage:
    python -m trading_assistant.sweep prices.csv --short 5,10,20 --long 20,50,100
        [--cash 10000] [--fee 0] [--fee-pct 0] [--top N] [--csv OUT]

--short and --long are comma lists of positive integers. Every pair with
short < long is backtested (other pairs are skipped). Rows are sorted by
return, best first; ties go to the smaller drawdown, then the smaller short
window, then the smaller long window. The table (limited by --top) is followed
by buy-and-hold for comparison; --csv writes every row.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows, non-positive price, --csv not writable or the same file as the input)
    2  usage problem (a bad window list, no pair with short < long, --cash <= 0,
       negative --fee, --fee-pct outside [0, 100), --top < 1, empty --csv name)

``grid_combinations`` and ``sweep_grid`` do the same for any strategy in
``trading_assistant.strategies`` and a grid of its parameters (used by the
walk-forward test; the command above still sweeps the SMA crossover only).

Best in-sample parameters overfit. This is a research aid. It does not place
orders and it is not financial advice.
"""

import argparse
import csv
import itertools
import math
import os
import sys

from .backtest import run_backtest, run_buy_and_hold
from .cli import DEFAULT_CASH, DISCLAIMER, check_costs, load_price_table
from .strategies import check_param_value, get_strategy, resolve_params

OVERFIT_WARNING = "Best in-sample parameters overfit; check them on data they were not chosen on."

CSV_HEADER = ("short", "long", "return_pct", "max_drawdown_pct", "trades", "round_trips", "win_rate_pct")


def sweep(closes, shorts, longs, cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0):
    """Backtest every ``(short, long)`` pair with ``short < long``; return sorted rows.

    Each row is a dict with keys short, long, return_pct, max_drawdown_pct
    (<= 0, as in the backtest), trades, round_trips and win_rate_pct (percent of
    round trips that made money, None if there were none). Duplicate values in
    ``shorts`` or ``longs`` are tried once. Rows are sorted by return
    descending, then smaller drawdown, then smaller short, then smaller long.
    Raises ValueError if no pair has short < long, plus anything
    ``run_backtest`` raises for bad prices or settings.
    """
    pairs = [(s, l) for s in sorted(set(shorts)) for l in sorted(set(longs)) if s < l]
    if not pairs:
        raise ValueError("no (short, long) pair with short < long to test")
    rows = []
    for s, l in pairs:
        result = run_backtest(closes, initial_cash=cash, short=s, long=l, fee=fee, fee_pct=fee_pct)
        n_rt = result.n_round_trips
        rows.append(
            {
                "short": s,
                "long": l,
                "return_pct": result.return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "trades": result.n_trades,
                "round_trips": n_rt,
                "win_rate_pct": result.n_winning_round_trips / n_rt * 100.0 if n_rt else None,
            }
        )
    rows.sort(key=lambda r: (-r["return_pct"], -r["max_drawdown_pct"], r["short"], r["long"]))
    return rows


class GridTooLarge(ValueError):
    """``grid_combinations`` with ``max_combinations``: the lists make more combinations than that."""

    def __init__(self, count, limit):
        super().__init__(f"{count:,} parameter combinations; the limit is {limit:,}")
        self.count = count
        self.limit = limit


def grid_combinations(strategy, grid=None, params=None, max_combinations=None):
    """Every parameter set of ``strategy`` to try: a list of full parameter dicts, in grid order.

    ``grid`` maps a parameter name to a list of values to try; ``params`` maps a
    parameter name to one fixed value. Parameters in neither keep the
    strategy's default. Each list is tried once per distinct value, smallest
    first, so the order and repeats of the values do not matter. Values that
    compare equal are one value: ``[0, 0.0]`` (or ``[0.0, -0.0, 0]``) is tried
    once, as the whole number ``0``; ``[0.0, -0.0]`` is ``0.0`` and ``[0.0]`` stays ``0.0``.

    The combinations are every pick of one value per parameter, in the
    registry's parameter order (``strategies.STRATEGIES``): the first
    parameter changes slowest. Each dict is what ``resolve_params`` returns,
    keys in that same order.

    Raises ValueError (a settings problem, never a data problem) for an
    unknown strategy or parameter, a parameter both in ``grid`` and
    ``params``, an empty list, any single value ``check_param_value``
    refuses (one bad value in a list is enough), or when no combination
    passes ``resolve_params``. Combinations that only break a rule between two
    parameters (``short < long``, ``oversold < overbought``, ``entry < exit``)
    are skipped, as ``sweep`` skips pairs with short >= long.

    ``max_combinations`` (default None: no limit) raises ``GridTooLarge``
    when the lists make more combinations than that (counted before any is
    built or checked against the rules between parameters), after every
    check of a single value.
    """
    get_strategy(strategy)
    grid = dict(grid or {})
    params = dict(params or {})
    for key in grid:
        if key in params:
            raise ValueError(f"{key} is both in the grid and a fixed parameter; give only one")
    for key, value in params.items():
        check_param_value(strategy, key, value)
    values = {}
    for key, listed in grid.items():
        listed = list(listed)
        if not listed:
            raise ValueError(f"the grid for {key} needs at least one value")
        for value in listed:
            check_param_value(strategy, key, value)
        # Equal values count once (0, 0.0 and -0.0 too). Of equal values the whole number is kept, then 0.0
        # over -0.0, so the order they were given in never matters.
        distinct = []
        for value in sorted(listed, key=lambda v: (v, isinstance(v, float), math.copysign(1.0, v) < 0)):
            if not distinct or value != distinct[-1]:
                distinct.append(value)
        values[key] = distinct
    _, defaults, _ = get_strategy(strategy)
    choices = [values[key] if key in values else [params.get(key, default)] for key, default in defaults.items()]
    if max_combinations is not None:
        count = math.prod(len(c) for c in choices)
        if count > max_combinations:
            raise GridTooLarge(count, max_combinations)
    combos, first_error = [], None
    for picked in itertools.product(*choices):
        try:
            combos.append(resolve_params(strategy, dict(zip(defaults, picked))))
        except ValueError as exc:
            if first_error is None:
                first_error = exc
    if not combos:
        raise ValueError(f"no parameter combination for {strategy} passes its checks: {first_error}")
    return combos


def sweep_grid(closes, strategy, grid=None, params=None, cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0):
    """Backtest ``strategy`` with every combination of ``grid_combinations(strategy, grid, params)``; sorted rows.

    Each row is a dict with keys params (the full parameter dict), return_pct,
    max_drawdown_pct (<= 0), trades, round_trips and win_rate_pct (None
    without round trips), as in ``sweep``. Rows are sorted by return
    descending, then smaller drawdown, then the parameter values in the
    registry's parameter order, smaller first (for ``sma_cross``: smaller
    short, then smaller long, which is ``sweep``'s order). No two rows have the
    same parameters, so the order is complete. Raises ValueError as
    ``grid_combinations`` and ``run_backtest`` do.
    """
    combos = grid_combinations(strategy, grid, params)
    rows = []
    for combo in combos:
        result = run_backtest(
            closes, initial_cash=cash, fee=fee, fee_pct=fee_pct, strategy=strategy, strategy_params=dict(combo)
        )
        n_rt = result.n_round_trips
        rows.append(
            {
                "params": dict(combo),
                "return_pct": result.return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "trades": result.n_trades,
                "round_trips": n_rt,
                "win_rate_pct": result.n_winning_round_trips / n_rt * 100.0 if n_rt else None,
            }
        )
    keys = list(get_strategy(strategy)[1])
    rows.sort(key=lambda r: (-r["return_pct"], -r["max_drawdown_pct"], *(r["params"][k] for k in keys)))
    return rows


def _int_list(text):
    try:
        values = [int(part) for part in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a comma list of positive integers like 5,10,20") from None
    if not values or any(v < 1 for v in values):
        raise argparse.ArgumentTypeError(f"{text!r} is not a comma list of positive integers like 5,10,20")
    return values


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.sweep",
        description="Backtest the SMA crossover over many window pairs.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("csv_path", help="CSV file with a 'close' column")
    parser.add_argument("--short", type=_int_list, required=True, metavar="LIST", help="short windows, e.g. 5,10,20")
    parser.add_argument("--long", type=_int_list, required=True, metavar="LIST", help="long windows, e.g. 20,50,100")
    parser.add_argument(
        "--cash", type=float, default=None, metavar="AMOUNT", help=f"starting cash (default: {DEFAULT_CASH:,.0f})"
    )
    parser.add_argument("--fee", type=float, default=None, metavar="AMOUNT", help="fixed cost per trade (default: 0)")
    parser.add_argument(
        "--fee-pct", type=float, default=None, metavar="PCT", help="percent of traded value per trade (default: 0)"
    )
    parser.add_argument("--top", type=int, default=None, metavar="N", help="show only the best N rows")
    parser.add_argument("--csv", default=None, metavar="OUT", help="write every row to OUT as CSV")
    return parser


def validate_args(parser, args):
    """Turn rule violations into usage errors (exit 2) and fill in defaults."""
    if not any(s < l for s in args.short for l in args.long):
        parser.error("no (short, long) pair with short < long; make some --short value smaller than a --long value")
    try:
        check_costs(args.cash, args.fee, args.fee_pct)
    except ValueError as exc:
        parser.error(str(exc))
    if args.top is not None and args.top < 1:
        parser.error("--top must be at least 1")
    if args.csv is not None and not args.csv.strip():
        parser.error("--csv needs a file name")
    if args.cash is None:
        args.cash = DEFAULT_CASH
    if args.fee is None:
        args.fee = 0.0
    if args.fee_pct is None:
        args.fee_pct = 0.0
    return args


def format_table(rows):
    """Aligned table lines for ``rows``."""
    lines = [f"{'Short':>5s} {'Long':>5s} {'Return':>9s} {'Max DD':>9s} {'Trades':>6s} {'RoundTrips':>10s} {'Win rate':>8s}"]
    for r in rows:
        win = "n/a" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.0f}%"
        lines.append(
            f"{r['short']:>5d} {r['long']:>5d} {r['return_pct']:>+8.2f}% {r['max_drawdown_pct']:>8.2f}%"
            f" {r['trades']:>6d} {r['round_trips']:>10d} {win:>8s}"
        )
    return lines


def write_csv(rows, path):
    """Write every row to ``path``; returns the number of rows. Raises OSError."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for r in rows:
            win = "" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.2f}"
            writer.writerow(
                [
                    r["short"],
                    r["long"],
                    f"{r['return_pct']:.4f}",
                    f"{r['max_drawdown_pct']:.4f}",
                    r["trades"],
                    r["round_trips"],
                    win,
                ]
            )
    return len(rows)


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

    if args.csv is not None and os.path.realpath(args.csv) == os.path.realpath(args.csv_path):
        print(f"Error: --csv refuses to overwrite the input file {args.csv_path}", file=sys.stderr)
        return 1

    try:
        rows = sweep(closes, args.short, args.long, cash=args.cash, fee=args.fee, fee_pct=args.fee_pct)
        bench = run_buy_and_hold(closes, initial_cash=args.cash, fee=args.fee, fee_pct=args.fee_pct)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    lines = [f"Sweep: {len(rows)} SMA crossover pairs on {len(closes)} bars, start cash {args.cash:,.2f}"]
    shown = rows if args.top is None else rows[: args.top]
    lines += format_table(shown)
    if len(shown) < len(rows):
        lines.append(f"(showing the best {len(shown)} of {len(rows)})")
    lines.append(f"Buy & hold: {bench.return_pct:+.2f}% return, {bench.max_drawdown_pct:.2f}% max drawdown")

    if args.csv is not None:
        try:
            n = write_csv(rows, args.csv)
        except OSError as exc:
            print(f"Error: cannot write {args.csv}: {exc.strerror or exc}", file=sys.stderr)
            return 1
        lines.append(f"Wrote {n} rows to {args.csv}")

    for line in lines:
        print(line)
    print(OVERFIT_WARNING)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
