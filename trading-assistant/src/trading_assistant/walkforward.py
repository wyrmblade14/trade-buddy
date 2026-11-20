"""Walk-forward windows: split a price history into rolling train/test blocks.

Choosing parameters on a whole file and reporting results on that same file
overstates how well they work. Walk-forward analysis instead picks parameters
on a train block and measures them on the test block that comes right after
it, which the choice never saw, then rolls both blocks forward and repeats.

``split_window`` computes the bar ranges. Each window is a tuple
``(train_start, train_end, test_start, test_end)`` of bar indexes with the ends
excluded, like Python slices, so ``closes[train_start:train_end]`` is the train
block and ``closes[test_start:test_end]`` the test block.

``walk_forward`` runs the whole procedure for the SMA crossover: in each
window it picks the best (short, long) pair with ``sweep.sweep`` on the train
closes only, then backtests that pair with ``backtest.run_backtest`` on the
test closes only. With ``warmup=True`` the test backtest's moving averages
are first warmed up on the bars just before the test block; it still trades
and is scored on the test closes only. ``walk_forward(..., strategy=NAME,
grid={KEY: [values]}, params={KEY: value})`` does the same for any strategy
in ``trading_assistant.strategies``, choosing among every combination of the
grid with ``sweep.sweep_grid``.

Usage:
    python -m trading_assistant.walkforward prices.csv --short 5,10,20 --long 20,50,100
        --train 250 --test 60 [--step N] [--cash 10000] [--fee 0] [--fee-pct 0]
        [--warmup] [--json] [--csv OUT]
    python -m trading_assistant.walkforward prices.csv --strategy NAME [--grid KEY=LIST ...]
        [--param KEY=VALUE ...] --train 250 --test 60 [the same other options]

--strategy NAME walks forward any strategy of ``trading_assistant.strategies``
instead of SMA crossover pairs. --grid KEY=LIST (repeatable, one per
parameter) lists values of one parameter to try: every combination is
backtested on each train block and the best (highest return, then smaller
drawdown, then smaller parameter values in the registry's parameter order)
is run on the test block. --param KEY=VALUE (repeatable) fixes a parameter to
one value (a list is refused: that is --grid's job); parameters in neither
keep their defaults. --short and --long cannot be combined with any of the
three (sma_cross's windows are then --grid short=... --grid long=...), and
--grid/--param need --strategy. In a list, equal values count once (0 and 0.0
are one value, kept as the whole number 0). With --strategy the text has a
Params column (every parameter of the chosen set, ``window=3,threshold=0.5``;
whole values as whole numbers, ``entry=-2``, see ``param_value_text``)
instead of Pair, --json starts with ``"strategy": NAME`` (before ``warmup``)
and each window has a ``params`` object instead of ``short`` and ``long``, and
the --csv file has one ``param_KEY`` column per parameter instead of
``short`` and ``long``. With --warmup the test run is warmed up on the
``first_signal_bars - 1`` bars before the block. Without the three options
every output is exactly as before they existed, except --help (the usage line
is unchanged; --st still means --step).

--short and --long are comma lists of positive integers, as in
``trading_assistant.sweep``. --train and --test are the bars in each train and
test block; --step (default: --test) is how far each window moves. The output
is ``format_walk_forward``: one row per window, the summary figures, notes
where the figures need care, the overfit line and the disclaimer.

--warmup (a switch, off by default) warms each test backtest's moving
averages up on the chosen pair's ``long`` bars just before its test block
(fewer near the start of the data, back to bar 0); the pair is still chosen
on the train bars only, and the test run still trades and is scored on the
test bars only (see ``walk_forward``). The header line and the no-trades note
then say so, and --json gets a ``"warmup": true`` field (see below); the --csv
file does not change shape, so it cannot show that warm-up was on. Without it
the output is exactly as before, except --help, which lists and describes
--warmup, and the usage line printed with usage errors, which lists
[--warmup].

--json prints one JSON object instead of the text, and nothing else:
``{"windows": [...], "summary": {...}, "overfit_warning": ..., "disclaimer": ...}``,
the ``walk_forward`` rows and the ``summarize`` dict as they are (unrounded
numbers, bar ends excluded), then the overfit line and the disclaimer as fields.
With --warmup the object starts with one more field, ``"warmup": true``, before
``windows``: ``{"warmup": true, "windows": [...], ...}``. It is there only with
--warmup (never ``"warmup": false``); without it the object is exactly as above.
--csv OUT also writes one row per window to OUT (columns ``CSV_HEADER``, bar
ends excluded, percentages to 4 decimals); the normal output is still printed,
with a "Wrote N rows to OUT" line before the overfit line (not with --json,
whose output stays one JSON object). A --csv file that is the input file, or
that cannot be written, is an error and nothing is printed on stdout.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows, non-positive price, too few bars for one train + test window,
       --csv not writable or the same file as the input)
    2  usage problem (a bad window list, no pair with short < long,
       --train/--test/--step < 1, --cash <= 0, negative --fee,
       --fee-pct outside [0, 100), empty --csv name, a value after
       --warmup such as --warmup 5; with --strategy: --short or --long with
       any of --strategy/--grid/--param, --grid or --param without
       --strategy, an unknown strategy or parameter, a malformed --grid or
       --param, a list given to --param, a key given twice or in both, any
       bad value in a list, no combination that passes the strategy's checks)

It does not place orders and it is not financial advice.
"""

import argparse
import csv
import json
import os
import sys

from . import backtest as _backtest
from . import sweep as _sweep
from .backtest import DEFAULT_CASH
from .cli import DISCLAIMER, check_costs, load_price_table, parse_param
from .strategies import first_signal_bars, get_strategy, strategy_names
from .sweep import OVERFIT_WARNING, _int_list


def _check_count(name, value, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a whole number of at least {minimum}, got {value!r}")


def split_window(n, train, test, step=None):
    """Rolling walk-forward windows over ``n`` bars.

    Returns a list of ``(train_start, train_end, test_start, test_end)`` tuples,
    ends excluded. The first train block starts at bar 0 and each test block
    starts exactly where its train block ends, so a test block never overlaps
    the bars its parameters were chosen on. Each next window starts ``step``
    bars later (``step`` defaults to ``test``). Only full windows are returned:
    one whose test block would run past bar ``n`` is dropped, so the result is
    empty when ``n < train + test``.

    ``n`` is a whole number of at least 0; ``train``, ``test`` and ``step``
    (when given) are whole numbers of at least 1. Anything else raises ValueError.

    Example: ``split_window(12, 5, 3)`` is ``[(0, 5, 5, 8), (3, 8, 8, 11)]``;
    the next window, ``(6, 11, 11, 14)``, would end past bar 12 and is dropped.
    """
    _check_count("n", n, 0)
    _check_count("train", train, 1)
    _check_count("test", test, 1)
    if step is None:
        step = test
    _check_count("step", step, 1)

    windows = []
    start = 0
    while start + train + test <= n:
        windows.append((start, start + train, start + train, start + train + test))
        start += step
    return windows


def walk_forward(
    closes, shorts, longs, train, test, step=None, cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0, warmup=False,
    strategy=None, grid=None, params=None,
):
    """Walk-forward test of the SMA crossover (or of ``strategy``) over ``closes``; one dict per window.

    With ``strategy`` None (the default) it is the SMA crossover over the
    ``shorts`` x ``longs`` pairs, exactly as described below. With a strategy
    name, ``shorts`` and ``longs`` must be None and each window chooses among
    the parameter sets of ``sweep.grid_combinations(strategy, grid, params)``
    instead (see ``_walk_forward_strategy``; the rows then have ``params``
    where they have ``short`` and ``long``).

    The windows come from ``split_window(len(closes), train, test, step)``. In
    each window ``sweep.sweep`` is run on ``closes[train_start:train_end]``
    only, with ``shorts``, ``longs``, ``cash``, ``fee`` and ``fee_pct``, and its
    first (best) row is the chosen pair. Pairs that tie on train return are
    settled by the sweep's own order (smaller train drawdown, then smaller
    short, then smaller long), never by anything from the test block.
    That pair is then backtested with
    ``backtest.run_backtest`` on ``closes[test_start:test_end]`` only, with the
    same cash and fees, so the choice never sees a test bar. The test backtest
    starts flat with fresh cash, and without ``warmup`` its moving averages
    warm up inside the test block, so a test block shorter than ``long + 2``
    bars cannot trade.

    With ``warmup=True`` the pair is chosen exactly as above, on the train
    closes only, so it is the same pair as without it. The test backtest then
    also gets the ``long`` bars just before ``test_start``
    (``closes[test_start - long:test_start]``, the chosen pair's ``long``) as
    ``run_backtest``'s ``warmup_closes``: its moving averages are already
    warmed up on the first test bar. Those bars only feed the signal. The
    backtest still starts flat with fresh cash on the first test bar, only
    signals on test bars count (a crossing on the last bar before the block
    is not acted on, so the first fill can come on ``test_start + 1``), and
    every figure in the row is measured on the test block alone. The
    warm-up bars are the last ``long`` bars of the train block when ``long``
    is at most ``train``; a larger chosen ``long`` reaches back before the
    train block (still only bars before the test block). When fewer than
    ``long`` bars come before the block (only when ``test_start < long``,
    which needs ``train`` smaller than the chosen ``long``), whatever bars
    there are, back to bar 0, are used, so that window is only partly warmed
    up.
    ``warmup`` must be True or False; False (the default) changes nothing.

    Each dict has the keys ``window`` (1, 2, 3, ... in order), ``train_start``,
    ``train_end``, ``test_start``, ``test_end`` (bar indexes into ``closes``,
    ends excluded), ``short``, ``long`` (the chosen pair),
    ``train_return_pct`` (the chosen pair's return on the train block),
    ``test_return_pct``, ``test_max_drawdown_pct`` (<= 0), ``test_trades``
    (number of fills in the test block) and ``buy_hold_return_pct`` (buying
    on the first test bar and holding to the last, with the same cash and
    fees, from ``backtest.run_buy_and_hold``).

    Raises ValueError when ``closes`` is too short for a single window, plus
    whatever ``split_window``, ``sweep.sweep`` and ``backtest.run_backtest``
    raise, unchanged (bar numbers in their messages count from the start of
    the block they were given).
    """
    if not isinstance(warmup, bool):
        raise ValueError(f"warmup must be True or False, got {warmup!r}")
    if strategy is not None:
        if shorts is not None or longs is not None:
            raise ValueError("shorts and longs only apply without a strategy; give its parameters in grid or params")
        return _walk_forward_strategy(closes, strategy, grid, params, train, test, step, cash, fee, fee_pct, warmup)
    if grid is not None or params is not None:
        raise ValueError("grid and params need a strategy")
    windows = _windows(closes, train, test, step)
    results = []
    for number, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        best = _sweep.sweep(closes[train_start:train_end], shorts, longs, cash=cash, fee=fee, fee_pct=fee_pct)[0]
        options = {}  # without warm-up the test backtest is called exactly as before the option existed
        if warmup:
            # The chosen long's bars just before the block, or as many as there are back to bar 0.
            options["warmup_closes"] = closes[max(0, test_start - best["long"]) : test_start]
        result = _backtest.run_backtest(
            closes[test_start:test_end],
            initial_cash=cash,
            short=best["short"],
            long=best["long"],
            fee=fee,
            fee_pct=fee_pct,
            **options,
        )
        results.append(
            {
                "window": number,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "short": best["short"],
                "long": best["long"],
                "train_return_pct": best["return_pct"],
                "test_return_pct": result.return_pct,
                "test_max_drawdown_pct": result.max_drawdown_pct,
                "test_trades": result.n_trades,
                "buy_hold_return_pct": _backtest.run_buy_and_hold(
                    closes[test_start:test_end], initial_cash=cash, fee=fee, fee_pct=fee_pct
                ).return_pct,
            }
        )
    return results


def _windows(closes, train, test, step):
    windows = split_window(len(closes), train, test, step)
    if not windows:
        raise ValueError(
            f"not enough prices for a walk-forward window: {len(closes)} bars, need at least train + test = {train + test}"
        )
    return windows


def _walk_forward_strategy(closes, strategy, grid, params, train, test, step, cash, fee, fee_pct, warmup):
    """``walk_forward`` for a named strategy and a grid of its parameters.

    The parameter sets are checked first (``sweep.grid_combinations``; a bad
    grid is reported before the windows are). In each window
    ``sweep.sweep_grid`` is run on the train closes only; its first row is the
    chosen set: highest train return, then smaller train drawdown, then
    smaller parameter values in the registry's parameter order, never anything
    from the test block. That set is backtested on the test closes only, with
    the same cash and fees.

    With ``warmup`` the test backtest also gets the
    ``strategies.first_signal_bars(strategy, chosen) - 1`` closes just before
    the test block (fewer near the start of the data, back to bar 0) as
    ``warmup_closes``: with them the first test bar can already signal. For
    ``sma_cross`` that is ``long`` bars, as without a strategy. As there, they
    only feed the signal; everything is counted on the test block alone.

    The rows have the keys of ``walk_forward``'s rows, with ``params`` (the
    chosen full parameter dict) in place of ``short`` and ``long``.
    """
    _sweep.grid_combinations(strategy, grid, params)
    windows = _windows(closes, train, test, step)
    results = []
    for number, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        best = _sweep.sweep_grid(
            closes[train_start:train_end], strategy, grid, params, cash=cash, fee=fee, fee_pct=fee_pct
        )[0]
        options = {}
        if warmup:
            bars = first_signal_bars(strategy, best["params"]) - 1
            options["warmup_closes"] = closes[max(0, test_start - bars) : test_start]
        result = _backtest.run_backtest(
            closes[test_start:test_end],
            initial_cash=cash,
            fee=fee,
            fee_pct=fee_pct,
            strategy=strategy,
            strategy_params=dict(best["params"]),
            **options,
        )
        results.append(
            {
                "window": number,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "params": dict(best["params"]),
                "train_return_pct": best["return_pct"],
                "test_return_pct": result.return_pct,
                "test_max_drawdown_pct": result.max_drawdown_pct,
                "test_trades": result.n_trades,
                "buy_hold_return_pct": _backtest.run_buy_and_hold(
                    closes[test_start:test_end], initial_cash=cash, fee=fee, fee_pct=fee_pct
                ).return_pct,
            }
        )
    return results


def _compound_pct(returns_pct):
    growth = 1.0
    for r in returns_pct:
        growth *= 1.0 + r / 100.0
    return (growth - 1.0) * 100.0


def summarize(windows):
    """One summary dict for the list ``walk_forward`` returns.

    Keys:

    * ``windows``: number of windows.
    * ``compound_test_return_pct``: the test returns chained one after the
      other, ``(prod(1 + r / 100) - 1) * 100``, as if the money from each test
      block went into the next.
    * ``compound_buy_hold_return_pct``: the same for ``buy_hold_return_pct``.
    * ``windows_beating_buy_hold``: windows whose test return is strictly
      higher than their buy-and-hold return (a tie does not count).
    * ``mean_test_return_pct``: plain average of the test returns.
    * ``windows_without_trades``: windows with ``test_trades == 0``.
    * ``test_blocks_contiguous``: True when every test block starts exactly
      where the one before it ended (always True for a single window); False
      when any test block overlaps the one before it or leaves a gap.

    The compounded figures only make sense when ``test_blocks_contiguous`` is True.

    Chaining only makes sense when the test blocks neither overlap nor leave
    gaps, i.e. ``step == test`` (the default); with a smaller step some bars
    are counted more than once, with a larger one some are skipped. Each test
    block starts flat, so this is not the same as one backtest over all the
    test bars.

    Raises ValueError for an empty list.
    """
    if not windows:
        raise ValueError("no walk-forward windows to summarize")
    test_returns = [w["test_return_pct"] for w in windows]
    return {
        "windows": len(windows),
        "compound_test_return_pct": _compound_pct(test_returns),
        "compound_buy_hold_return_pct": _compound_pct(w["buy_hold_return_pct"] for w in windows),
        "windows_beating_buy_hold": sum(1 for w in windows if w["test_return_pct"] > w["buy_hold_return_pct"]),
        "mean_test_return_pct": sum(test_returns) / len(test_returns),
        "windows_without_trades": sum(1 for w in windows if w["test_trades"] == 0),
        "test_blocks_contiguous": all(b["test_start"] == a["test_end"] for a, b in zip(windows, windows[1:])),
    }


def _bars(start, end):
    """Bars ``start`` to ``end - 1``, both included, as text."""
    return f"{start}-{end - 1}"


HEADER_RUN = "then run on the test bars after them"
HEADER_RUN_WARMUP = (
    "then traded and scored on the test bars after them, with its moving averages warmed up"
    " on up to long bars just before each test block"
)
NO_TRADES_REASON = "no crossover, or fewer than long + 2 test bars to warm up"
NO_TRADES_REASON_WARMUP = (
    "no BUY crossover on a test bar before its last, or, near the start of the data,"
    " fewer than long bars before the block to warm up"
)
# The same places with --strategy (``strategy`` given to format_walk_forward).
HEADER_RUN_WARMUP_STRATEGY = (
    "then traded and scored on the test bars after them, with its signal warmed up on the bars just before"
    " each test block, so that it can signal on the first test bar"
)
NO_TRADES_REASON_STRATEGY = "no BUY signal on a test bar before its last, or too few test bars for a first signal"
NO_TRADES_REASON_WARMUP_STRATEGY = (
    "no BUY signal on a test bar before its last, or, near the start of the data,"
    " too few bars before the block to warm up"
)


def param_value_text(value):
    """One parameter value as the Params cell shows it: a whole value as a whole number (``0.0`` is ``0``, ``-2.0``
    is ``-2``), anything else as Python prints it (``0.5``, ``1e-05``).

    A grid already counts 0 and 0.0 as one value, and a JSON reader (the web page) cannot tell them apart, so
    the text does not either; the page's ``wfNum`` follows the same rule. --json and --csv keep the value as it is.
    """
    number = float(value)
    if number.is_integer() and abs(number) < 1e16:
        return str(int(number))
    return repr(number)


def params_text(params):
    """A parameter dict as one cell: ``window=3`` or ``window=3,threshold=0.5`` (no spaces)."""
    return ",".join(f"{key}={param_value_text(value)}" for key, value in params.items())


def format_walk_forward(windows, summary, warmup=False, strategy=None):
    """Text to print for ``walk_forward`` results and their ``summarize`` dict.

    A header line, one aligned row per window (window number, train bars, test
    bars, chosen pair, train return, test return, buy-and-hold return, test
    trades; bar ranges are shown with both ends included), the summary
    figures, a note when the test blocks are not contiguous (the compounded
    figures then mean little), a note when some windows made no test trades,
    then ``sweep.OVERFIT_WARNING`` and ``cli.DISCLAIMER``. Returns one string
    of lines joined by newlines, without a trailing newline.

    ``warmup`` says the rows came from ``walk_forward(..., warmup=True)``: the
    header line then ends with ``HEADER_RUN_WARMUP`` instead of
    ``HEADER_RUN`` and the no-trades note gives ``NO_TRADES_REASON_WARMUP``
    instead of ``NO_TRADES_REASON``. Nothing else changes.

    ``strategy`` (a name) says the rows came from ``walk_forward(...,
    strategy=NAME)``: the header line says "each NAME parameter set" instead of
    "each SMA crossover pair" (and ends with ``HEADER_RUN_WARMUP_STRATEGY``
    with ``warmup``), the ``Pair`` column is a ``Params`` column holding every
    parameter of the chosen set (``params_text``; as wide as its longest cell,
    at least 7), and the no-trades note gives ``NO_TRADES_REASON_STRATEGY``
    (or ``NO_TRADES_REASON_WARMUP_STRATEGY``) and ends "about the parameters".
    Without it (None, the default) the text is exactly as before.
    """
    n = summary["windows"]
    if strategy is None:
        chose = "each SMA crossover pair"
        run = HEADER_RUN_WARMUP if warmup else HEADER_RUN
        label, cells = "Pair", [f"{w['short']}/{w['long']}" for w in windows]
        reason, about = (NO_TRADES_REASON_WARMUP if warmup else NO_TRADES_REASON), "the pair"
    else:
        chose = f"each {strategy} parameter set"
        run = HEADER_RUN_WARMUP_STRATEGY if warmup else HEADER_RUN
        label, cells = "Params", [params_text(w["params"]) for w in windows]
        reason = NO_TRADES_REASON_WARMUP_STRATEGY if warmup else NO_TRADES_REASON_STRATEGY
        about = "the parameters"
    # The pair column is 7 wide as it always was (a longer pair just overflows it); the Params column grows.
    width = 7 if strategy is None else max([7] + [len(cell) for cell in cells])
    lines = [f"Walk-forward: {n} window{'' if n == 1 else 's'}; {chose} was chosen on its train bars only, {run}"]
    lines.append(
        f"{'Window':>6s} {'Train bars':>11s} {'Test bars':>11s} {label:>{width}s}"
        f" {'Train':>9s} {'Test':>9s} {'Buy&Hold':>9s} {'Trades':>6s}"
    )
    for w, cell in zip(windows, cells):
        lines.append(
            f"{w['window']:>6d} {_bars(w['train_start'], w['train_end']):>11s}"
            f" {_bars(w['test_start'], w['test_end']):>11s}"
            f" {cell:>{width}s} {w['train_return_pct']:>+8.2f}% {w['test_return_pct']:>+8.2f}%"
            f" {w['buy_hold_return_pct']:>+8.2f}% {w['test_trades']:>6d}"
        )
    lines.append(f"Test return, compounded over the windows: {summary['compound_test_return_pct']:+.2f}%")
    lines.append(f"Buy & hold, compounded over the windows:  {summary['compound_buy_hold_return_pct']:+.2f}%")
    lines.append(f"Mean test return per window: {summary['mean_test_return_pct']:+.2f}%")
    lines.append(f"Windows beating buy & hold: {summary['windows_beating_buy_hold']} of {n}")
    lines.append(f"Windows without test trades: {summary['windows_without_trades']} of {n}")
    if not summary["test_blocks_contiguous"]:
        lines.append(
            "Note: the test blocks overlap or leave gaps (step is not equal to test), so the compounded"
            " figures do not describe one continuous stretch of prices."
        )
    if summary["windows_without_trades"]:
        lines.append(
            f"Note: {summary['windows_without_trades']} of {n} windows made no trades in the test block"
            f" ({reason}); their 0.00% says nothing about {about}."
        )
    lines.append(OVERFIT_WARNING)
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def check_settings(shorts, longs, train, test, step=None):
    """Raise ValueError (with the command line's message) for window settings that cannot run.

    Shared by the command line (as usage errors) and the web server.
    """
    if not any(s < l for s in shorts for l in longs):
        raise ValueError("no (short, long) pair with short < long; make some --short value smaller than a --long value")
    check_blocks(train, test, step)


def check_blocks(train, test, step=None):
    """Raise ValueError (the command line's message) for a ``train``, ``test`` or ``step`` below 1."""
    for name, value in (("train", train), ("test", test), ("step", step)):
        if value is not None and value < 1:
            raise ValueError(f"--{name} must be at least 1")


def _number(option, key, text):
    """One number of a --grid list: a whole number when it reads as one, else a finite float."""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        value = float(text)
    except ValueError:
        value = None
    if value is None or value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{option} {key} needs a comma list of finite numbers, got {text!r}")
    return value


def parse_grid_item(text):
    """``KEY=LIST`` (one --grid) as ``(key, [numbers])``; ValueError with a one-line message otherwise."""
    key, sep, raw = text.partition("=")
    key, raw = key.strip(), raw.strip()
    if not sep or not key or not raw:
        raise ValueError(f"--grid must look like KEY=LIST, got {text!r}")
    return key, [_number("--grid", key, part.strip()) for part in raw.split(",")]


def parse_param_item(text):
    """``KEY=VALUE`` (one --param) as ``(key, number)``; a list is refused (that is --grid's job)."""
    key, sep, raw = text.partition("=")
    key, raw = key.strip(), raw.strip()
    if not sep or not key or not raw:
        raise ValueError(f"--param must look like KEY=VALUE, got {text!r}")
    if "," in raw:
        raise ValueError(f"--param {key} takes one value, got {raw!r}; give a list of values with --grid {key}={raw}")
    return parse_param(text)  # the main command's --param: its numbers and messages ("needs a number", ...)


def check_strategy_options(strategy, grid_items, param_items, short_given=False, long_given=False):
    """Check --strategy, --grid and --param; return ``(grid, params)`` dicts for ``walk_forward``.

    ``parse_strategy_options`` followed by ``sweep.grid_combinations`` (whose
    result is dropped; the web server calls the two itself, to limit the
    number of combinations first).

    ``grid_items`` and ``param_items`` are the option texts (or None). In
    this order, each a ValueError with a one-line message (exit 2 on the
    command line):

    * ``--short``/``--long`` together with any of the three, whatever the
      strategy (``sma_cross``'s windows are then given with ``--grid``);
    * ``--grid`` or ``--param`` without ``--strategy``;
    * a malformed ``--grid`` (``KEY=LIST`` of numbers) or ``--param``
      (``KEY=VALUE``, one number: a list is refused), or the same key twice
      in either;
    * a key in both ``--grid`` and ``--param``;
    * anything ``sweep.grid_combinations`` refuses: an unknown strategy or
      parameter, any bad value in a list, or no combination that passes
      the strategy's checks.
    """
    grid, params = parse_strategy_options(strategy, grid_items, param_items, short_given, long_given)
    if strategy is not None:
        _sweep.grid_combinations(strategy, grid, params)
    return grid, params


def parse_strategy_options(strategy, grid_items, param_items, short_given=False, long_given=False):
    """Every check of ``check_strategy_options`` up to, not including, ``sweep.grid_combinations``.

    Returns ``(None, None)`` when none of the three options was given.
    """
    if strategy is None and not grid_items and not param_items:
        return None, None
    for key, given in (("short", short_given), ("long", long_given)):
        if given:
            raise ValueError(
                f"--{key} cannot be combined with --strategy, --grid or --param; give sma_cross's windows"
                " as --strategy sma_cross --grid short=LIST --grid long=LIST"
            )
    if strategy is None:
        raise ValueError(f"{'--grid' if grid_items else '--param'} needs --strategy")
    grid, params = {}, {}
    for items, parse, target, option in (
        (grid_items, parse_grid_item, grid, "--grid"), (param_items, parse_param_item, params, "--param")
    ):
        for text in items or []:
            key, value = parse(text)
            if key in target:
                raise ValueError(f"{option} {key} given more than once")
            target[key] = value
    for key in grid:
        if key in params:
            raise ValueError(f"{key} is in both --grid and --param; give only one")
    return grid, params


def run_walk_forward(
    closes, shorts, longs, train, test, step=None, cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0, warmup=False,
    strategy=None, grid=None, params=None,
):
    """Check every price, then ``walk_forward`` and ``summarize``; returns ``(rows, summary)``.

    Every bar is checked first (``backtest``'s own input check), so a bad price
    is reported with its bar number in ``closes``, even if no window uses it.
    Raises ValueError as those functions do. Shared by the command line and
    the web server, so both give the same numbers and the same messages.
    ``warmup`` is passed on to ``walk_forward`` (False, the default, changes nothing),
    and so are ``strategy``, ``grid`` and ``params`` when a strategy is given
    (without one the call is exactly as before they existed).
    """
    _backtest._validate_inputs(closes, cash, fee, fee_pct)
    extra = {} if strategy is None else {"strategy": strategy, "grid": grid, "params": params}
    rows = walk_forward(
        closes, shorts, longs, train, test, step=step, cash=cash, fee=fee, fee_pct=fee_pct, warmup=warmup, **extra
    )
    return rows, summarize(rows)


def json_data(rows, summary, warmup=False, strategy=None):
    """The ``--json`` object (also the web reply) for ``walk_forward`` rows and their ``summarize`` dict.

    Like the main command line's ``--json``, the object carries the text's
    closing lines as fields: ``overfit_warning`` (``sweep.OVERFIT_WARNING``)
    and, last, ``disclaimer`` (``cli.DISCLAIMER``).

    ``warmup=True`` (the rows came from ``walk_forward(..., warmup=True)``)
    puts ``"warmup": true`` first, before ``windows``: it says how every number
    after it was made, as the text's header line does. With ``warmup`` False
    (the default) the key is left out and the object is exactly as before.

    ``strategy`` (a name; the rows came from ``walk_forward(...,
    strategy=NAME)``, so each has a ``params`` dict instead of ``short`` and
    ``long``) puts ``"strategy": NAME`` first, before ``warmup``. Without it
    (None, the default) there is no ``strategy`` key.
    """
    data = {"strategy": strategy} if strategy is not None else {}
    if warmup:
        data["warmup"] = True
    data.update({"windows": rows, "summary": summary, "overfit_warning": OVERFIT_WARNING, "disclaimer": DISCLAIMER})
    return data


CSV_HEADER = (
    "window",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "short",
    "long",
    "train_return_pct",
    "test_return_pct",
    "test_max_drawdown_pct",
    "test_trades",
    "buy_hold_return_pct",
)


def csv_header(strategy=None):
    """The --csv columns: ``CSV_HEADER``, or with a strategy ``param_KEY`` columns (its parameters in registry
    order) in place of ``short`` and ``long``."""
    if strategy is None:
        return CSV_HEADER
    keys = tuple(f"param_{key}" for key in get_strategy(strategy)[1])
    at = CSV_HEADER.index("short")
    return CSV_HEADER[:at] + keys + CSV_HEADER[at + 2 :]


def write_csv(rows, path, strategy=None):
    """Write one line per ``walk_forward`` row to ``path``; returns the number of rows. Raises OSError.

    Columns are ``CSV_HEADER``: whole numbers as they are, percentages to 4
    decimals (as in ``sweep.write_csv``). Bar ends are excluded, as in the rows.
    With ``strategy`` the columns are ``csv_header(strategy)``: one
    ``param_KEY`` column per parameter, holding the chosen value as Python
    prints it (``3``, ``0.5``, ``-2.0``). Without it the file is exactly as before.
    """
    header = csv_header(strategy)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        for r in rows:
            writer.writerow(
                [
                    r["params"][k[len("param_"):]] if k.startswith("param_")
                    else f"{r[k]:.4f}" if k.endswith("_pct") else r[k]
                    for k in header
                ]
            )
    return len(rows)


class _StrategySeen:
    """Whether --strategy, --grid or --param has been read in the current parse (one per parser)."""

    def __init__(self):
        self.seen = False


class _SmaWindowList(argparse.Action):
    """--short/--long: stored as usual, and required only while none of --strategy/--grid/--param is given.

    argparse reads ``required`` after every argument is read, so without those
    options a missing --short is reported exactly as before (with any other
    missing argument, in the same message); with them --short and --long are
    not required (``validate_args`` then refuses them if they were given).
    """

    def __init__(self, *args, seen, **kwargs):
        self.seen = seen
        super().__init__(*args, **kwargs)

    @property
    def required(self):
        return not self.seen.seen

    @required.setter
    def required(self, value):  # argparse.Action.__init__ sets it; the property decides
        pass

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


class _StrategyOption(argparse.Action):
    """--strategy (stored) and --grid/--param (appended), marking that one of them was given."""

    def __init__(self, *args, seen, append=False, **kwargs):
        self.seen = seen
        self.append = append
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        self.seen.seen = True
        if self.append:
            values = [*(getattr(namespace, self.dest, None) or []), values]
        setattr(namespace, self.dest, values)


def build_parser():
    """The parser. Its usage line is the one from before --strategy, --grid and --param (they are in --help)."""
    parser = argparse.ArgumentParser(
        prog="trading_assistant.walkforward",
        description="Walk-forward test of the SMA crossover (or of --strategy): pick the best window pair (or"
        " parameter set) on each train block, then run it on the test block that follows.",
        epilog=DISCLAIMER,
    )
    seen = _StrategySeen()
    parser.add_argument("csv_path", help="CSV file with a 'close' column")
    windows = [
        parser.add_argument(
            "--short", type=_int_list, metavar="LIST", action=_SmaWindowList, seen=seen,
            help="short windows, e.g. 5,10,20",
        ),
        parser.add_argument(
            "--long", type=_int_list, metavar="LIST", action=_SmaWindowList, seen=seen,
            help="long windows, e.g. 20,50,100",
        ),
    ]
    parser.add_argument("--train", type=int, required=True, metavar="N", help="bars in each train block")
    parser.add_argument("--test", type=int, required=True, metavar="N", help="bars in each test block")
    parser.add_argument(
        "--step", type=int, default=None, metavar="N", help="bars each window moves on (default: --test)"
    )
    # Hidden exact alias: "--st" meant --step (argparse abbreviation) before --strategy existed, and an exact
    # option string wins over the now-ambiguous prefix. Its errors still say --step.
    step_alias = parser.add_argument("--st", dest="step", type=int, default=None, metavar="N", help=argparse.SUPPRESS)
    step_alias.option_strings = ["--step"]
    parser.add_argument(
        "--cash", type=float, default=None, metavar="AMOUNT", help=f"starting cash (default: {DEFAULT_CASH:,.0f})"
    )
    parser.add_argument("--fee", type=float, default=None, metavar="AMOUNT", help="fixed cost per trade (default: 0)")
    parser.add_argument(
        "--fee-pct", type=float, default=None, metavar="PCT", help="percent of traded value per trade (default: 0)"
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="warm the moving averages up on the chosen pair's long bars before each test block"
        " (trades and scores still only inside the test block)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print one JSON object with the windows and the summary instead of text"
    )
    parser.add_argument("--csv", default=None, metavar="OUT", help="also write one row per window to OUT as CSV")
    unlisted = [
        parser.add_argument(
            "--strategy", choices=strategy_names(), default=None, metavar="NAME", action=_StrategyOption, seen=seen,
            help=f"walk-forward this strategy instead of SMA crossover pairs, one of: {', '.join(strategy_names())};"
            " --short and --long cannot be used with it, --grid or --param (with --warmup its signal is warmed up"
            " on the bars its first signal needs)",
        ),
        parser.add_argument(
            "--grid", dest="grid_items", default=None, metavar="KEY=LIST", action=_StrategyOption, seen=seen,
            append=True,
            help="values of one --strategy parameter to try on each train block, e.g. window=10,20,30 (repeatable;"
            " every combination is tried)",
        ),
        parser.add_argument(
            "--param", dest="param_items", default=None, metavar="KEY=VALUE", action=_StrategyOption, seen=seen,
            append=True,
            help="one fixed value for a --strategy parameter, e.g. threshold=0.5 (repeatable); parameters in"
            " neither --grid nor --param keep their defaults",
        ),
    ]
    # Keep the usage line (printed with --help and with every usage error) exactly as it was before --strategy,
    # --grid and --param existed: --short and --long shown as required, the three new options left out.
    helps = [action.help for action in unlisted]
    for action in unlisted:
        action.help = argparse.SUPPRESS
    assert all(action.required for action in windows)
    parser.usage = parser.format_usage()[len("usage: ") :].rstrip("\n").replace("%", "%%")
    for action, text in zip(unlisted, helps):
        action.help = text
    return parser


def validate_args(parser, args):
    """Turn rule violations into usage errors (exit 2) and fill in defaults.

    Without --strategy, --grid and --param the checks and messages are the
    ones from before they existed. With any of them, ``check_strategy_options``
    comes first (its messages), then the train, test and step checks, the costs
    and the --csv name; ``args.grid`` and ``args.params`` are set to the dicts
    for ``walk_forward`` (None without a strategy).
    """
    args.grid, args.params = None, None
    if args.strategy is None and args.grid_items is None and args.param_items is None:
        try:
            check_settings(args.short, args.long, args.train, args.test, args.step)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        try:
            args.grid, args.params = check_strategy_options(
                args.strategy, args.grid_items, args.param_items, args.short is not None, args.long is not None
            )
            check_blocks(args.train, args.test, args.step)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        check_costs(args.cash, args.fee, args.fee_pct)
    except ValueError as exc:
        parser.error(str(exc))
    if args.csv is not None and not args.csv.strip():
        parser.error("--csv needs a file name")
    if args.cash is None:
        args.cash = DEFAULT_CASH
    if args.fee is None:
        args.fee = 0.0
    if args.fee_pct is None:
        args.fee_pct = 0.0
    return args


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

    # Without --strategy the run, and every output below, is exactly as before it existed.
    strategy = {} if args.strategy is None else {"strategy": args.strategy, "grid": args.grid, "params": args.params}
    try:
        rows, summary = run_walk_forward(
            closes,
            args.short,
            args.long,
            args.train,
            args.test,
            step=args.step,
            cash=args.cash,
            fee=args.fee,
            fee_pct=args.fee_pct,
            warmup=args.warmup,
            **strategy,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    written = None
    if args.csv is not None:
        try:
            written = write_csv(rows, args.csv, strategy=args.strategy)
        except OSError as exc:
            print(f"Error: cannot write {args.csv}: {exc.strerror or exc}", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(json_data(rows, summary, warmup=args.warmup, strategy=args.strategy), indent=2, allow_nan=False))
        return 0

    text = format_walk_forward(rows, summary, warmup=args.warmup, strategy=args.strategy)
    if written is not None:
        lines = text.split("\n")
        lines.insert(len(lines) - 2, f"Wrote {written} rows to {args.csv}")  # before the overfit line, as in sweep
        text = "\n".join(lines)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
