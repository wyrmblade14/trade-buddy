"""Line up the price histories of several symbols on their shared dates.

Usage from Python:

    dates, closes, lost = align_tables({
        "AAA": (["2026-01-02", "2026-01-05"], [10.0, 11.0]),
        "BBB": (["2026-01-05"], [20.0]),
    })
    # dates  == ["2026-01-05"]
    # closes == {"AAA": [11.0], "BBB": [20.0]}
    # lost   == {"AAA": 1, "BBB": 0}

Only dates that every symbol has are kept. Nothing is filled in, padded or
guessed: a date missing from one symbol is dropped for all of them. Dates are
matched as exact strings and put in order as text, which is date order for
the ``YYYY-MM-DD`` dates the rest of the tool uses.

``run_portfolio`` lines the symbols up with ``align_tables``, splits the cash
between them (equally, or by ``weights``) and runs the existing
``run_backtest`` (the SMA crossover, or the ``strategy`` given) on each
symbol's shared closes with its share of the cash. The portfolio equity on
each shared date is the sum of the symbols' account values.

``summarize`` turns a ``run_portfolio`` result into a plain dict: the date
range, the portfolio's return and maximum drawdown (taken from the summed
equity curve, never averaged from the symbols), the buy-and-hold return with
the same cash split, the worst single-symbol drawdown and one row per symbol.

``format_portfolio`` turns that dict into report text (it prints nothing).

Command line:

    python -m trading_assistant.portfolio FOLDER [--short 20] [--long 50]
        [--cash 10000] [--fee 0] [--fee-pct 0] [--json] [--csv OUT]
        [--strategy NAME] [--param KEY=VALUE ...]

Every ``.csv`` file directly inside FOLDER is one symbol (the file name
without ``.csv``), found with ``scan.price_files`` and read with the same
``data`` functions as ``--scan``. A file that cannot be read, holds a value
that is not a number or a close that is not positive, has no rows, has no
``date`` column or a blank date, or repeats another file's symbol is skipped
with a one-line reason; the rest carry on. Exit codes: 0 success; 1 a folder
problem (missing, not a folder, no ``.csv`` file), fewer than 2 usable files,
too few shared dates or a repeated date in a file (one ``Error:`` line on
stderr); 2 a usage problem (argparse). ``--json`` prints one JSON object
instead of the text (see ``json_data``); errors are reported exactly as
without it, with nothing on stdout. ``--csv OUT`` also writes the equity
curves (see ``write_csv``), with or without ``--json``, and leaves stdout as
it is. OUT is checked before any price is read: a missing folder, a folder, or
the same file as any ``.csv`` in FOLDER (skipped ones included, however the
path is spelled) is exit 1 and nothing is written. The file is only written
after a successful run, through a temporary file, so a failed run leaves no
CSV behind and never half-writes OUT.

``--weights A=60 B=40`` splits the cash by those percentages instead of
equally (see ``parse_weights``). Weights must cover exactly the files that are
used: a weight for a symbol with no file, a usable file without a weight, or a
bad weight is a usage problem (exit 2); a weight for a file that was skipped is
exit 1. Without ``--weights`` nothing in the output changes.

``--strategy NAME`` picks the rule every symbol trades (default ``sma_cross``)
and ``--param KEY=VALUE`` (repeatable, numbers only) changes one of its
parameters, with the main command's meaning, checks and messages (see
``check_strategy``): ``--param`` alone adjusts ``sma_cross``, whose windows are
``--short``/``--long``; ``--param short=`` that contradicts ``--short`` (or the
same for ``long``) is a usage problem, as are a malformed ``--param``, a key
the strategy does not have or a value it refuses. ``--short`` or ``--long``
with another strategy is a usage problem too. With another strategy the title
line names it and its parameters, ``summary`` has ``strategy`` and ``params``
instead of ``short`` and ``long``, and the ``--json`` object starts with
``title`` (the text's first line); the not-enough-dates error names the
strategy's real minimum. Without them, or with ``--strategy sma_cross``,
nothing in the output changes. Both are listed in ``--help`` but not in the
usage line.

The web page's ``POST /api/portfolio`` runs the same code on files sent in a
request body (``run_texts``): the same option checks
(``check_strategy_windows``, ``check_settings``, ``check_strategy``), the same
reading and skip reasons, the same run and the same ``--json`` object.

This is a research aid. It places no orders and it is not financial advice.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from .backtest import DEFAULT_CASH, BacktestResult, max_drawdown_pct, run_backtest
from .cli import DEFAULT_STRATEGY, DISCLAIMER, _Given, check_costs, check_windows, parse_param
from .data import decode_price_bytes, parse_price_text
from .scan import ScanError, ScanLimitError, _one_line, price_files
from .strategies import STRATEGIES, first_signal_bars, resolve_params, strategy_names

FOLDER_LABEL = "portfolio folder"  # names the folder in its error messages

DEFAULT_SHORT = 20
DEFAULT_LONG = 50


def align_tables(tables):
    """Return ``(dates, closes, lost)`` for the dates every symbol shares.

    ``tables`` maps each symbol to ``(dates, closes)``, one date per close.

    * ``dates`` is the list of dates present for every symbol, in ascending order;
    * ``closes`` maps each symbol to its closes on exactly those dates;
    * ``lost`` maps each symbol to how many of its bars were dropped.

    When the symbols share no date, ``dates`` is ``[]``, every symbol's
    closes are ``[]`` and every symbol has lost all of its bars. An empty
    ``tables`` gives ``([], {}, {})``.

    Raises ValueError, naming the symbol, when its dates are missing (None),
    its dates and closes differ in length, or a date appears twice (which
    close belongs to that date would be a guess).
    """
    by_date = {}
    for symbol, (dates, closes) in tables.items():
        if dates is None:
            raise ValueError(f"{symbol}: no dates; a date for every close is needed to line symbols up")
        if len(dates) != len(closes):
            raise ValueError(f"{symbol}: {len(dates)} dates but {len(closes)} closes")
        lookup = {}
        for date, close in zip(dates, closes):
            if date in lookup:
                raise ValueError(f"{symbol}: date {date!r} appears more than once")
            lookup[date] = close
        by_date[symbol] = lookup

    if not by_date:
        return [], {}, {}

    lookups = iter(by_date.values())
    shared = set(next(lookups))
    for lookup in lookups:
        shared &= lookup.keys()
    shared_dates = sorted(shared)

    aligned = {symbol: [lookup[date] for date in shared_dates] for symbol, lookup in by_date.items()}
    lost = {symbol: len(lookup) - len(shared_dates) for symbol, lookup in by_date.items()}
    return shared_dates, aligned, lost


@dataclass
class PortfolioResult:
    """The shared dates, one backtest per symbol, the summed account value per
    date, how many bars each symbol lost to the alignment and the settings run."""

    dates: List[str] = field(default_factory=list)
    results: Dict[str, BacktestResult] = field(default_factory=dict)
    equity: List[float] = field(default_factory=list)
    lost: Dict[str, int] = field(default_factory=dict)
    short: int = 20
    long: int = 50
    fee: float = 0.0
    fee_pct: float = 0.0
    weights: Optional[Dict[str, float]] = None  # percent per symbol, table order; None = equal split
    strategy: str = "sma_cross"
    # Another strategy's full parameters (short and long are then None); {} for sma_cross, whose
    # windows are short and long.
    strategy_params: Dict[str, float] = field(default_factory=dict)


def strategy_text(strategy, params):
    """``breakout (window=3)``: a strategy and its parameters as the ``--backtest`` report's title writes them."""
    return f"{strategy} ({', '.join(f'{k}={v}' for k, v in params.items())})"


def run_portfolio(tables, cash=DEFAULT_CASH, short=DEFAULT_SHORT, long=DEFAULT_LONG, fee=0.0, fee_pct=0.0,
                  weights=None, strategy="sma_cross", strategy_params=None):
    """Backtest a strategy (by default the SMA crossover) on every symbol over the dates they all share.

    ``tables`` is as for ``align_tables``. ``cash`` is split equally between
    the symbols, or, with ``weights`` (symbol to percent, as from
    ``parse_weights``, naming exactly the symbols of ``tables``), each symbol
    gets ``cash * weight / 100``; each symbol is run through ``run_backtest`` with its share,
    the ``short`` and ``long`` windows and the ``fee`` and ``fee_pct`` costs.
    Returns a ``PortfolioResult`` whose ``equity`` is, for each shared date,
    the sum of every symbol's account value on that date.

    ``strategy`` (a name from ``strategies``) is the rule every symbol trades
    and ``strategy_params`` (None, or a dict of numbers) overrides some of its
    parameters; the cash split, the costs and the buy-and-hold comparison do
    not depend on it. For ``sma_cross`` the overrides may only be ``short``
    and ``long``, which then replace the windows above; without overrides the
    run is exactly the SMA crossover run above. For any other strategy
    ``short`` and ``long`` are not used (the result's ``short`` and ``long``
    are None) and the result records the strategy and its full parameters.

    Raises ValueError (one line) when there are fewer than 2 symbols, or
    when too few dates are shared: for ``sma_cross`` fewer than ``long + 2``
    (``long + 1`` bars are needed for the first signal and one more bar to
    fill it); for another strategy fewer than ``strategies.first_signal_bars``
    plus 1, for the same reason. ``resolve_params`` raises ValueError for an
    unknown strategy or a parameter it refuses, and ``align_tables`` and
    ``run_backtest`` for their own input problems.
    """
    if len(tables) < 2:
        raise ValueError(f"a portfolio needs at least 2 symbols, got {len(tables)}")
    if strategy == "sma_cross":
        params = {}
        if strategy_params is not None:
            windows = resolve_params(strategy, {"short": short, "long": long, **strategy_params})
            short, long = windows["short"], windows["long"]
    else:
        params = resolve_params(strategy, strategy_params)
    dates, closes, lost = align_tables(tables)
    if strategy == "sma_cross":
        needed = long + 2
        if len(dates) < needed:
            raise ValueError(
                f"only {len(dates)} dates shared by all {len(tables)} symbols; "
                f"need at least {needed} (long window {long} + 2)"
            )
    else:
        first = first_signal_bars(strategy, params)
        if len(dates) < first + 1:
            raise ValueError(
                f"only {len(dates)} dates shared by all {len(tables)} symbols; "
                f"need at least {first + 1} for {strategy_text(strategy, params)}:"
                f" {first} for its first signal + 1 to fill it"
            )
        short = long = None

    if weights is None:
        shares = {symbol: cash / len(closes) for symbol in closes}
    else:
        if set(weights) != set(closes):
            raise ValueError(f"weights name {sorted(weights)} but the symbols are {sorted(closes)}")
        shares = {symbol: cash * float(weights[symbol]) / 100 for symbol in closes}
    if strategy == "sma_cross":
        results = {
            symbol: run_backtest(
                symbol_closes, initial_cash=shares[symbol], short=short, long=long, fee=fee, fee_pct=fee_pct
            )
            for symbol, symbol_closes in closes.items()
        }
    else:
        results = {
            symbol: run_backtest(
                symbol_closes, initial_cash=shares[symbol], fee=fee, fee_pct=fee_pct,
                strategy=strategy, strategy_params=params,
            )
            for symbol, symbol_closes in closes.items()
        }
    equity = [sum(values) for values in zip(*(result.equity_curve for result in results.values()))]
    return PortfolioResult(
        dates=dates,
        results=results,
        equity=equity,
        lost=lost,
        short=short,
        long=long,
        fee=float(fee),
        fee_pct=float(fee_pct),
        weights=None if weights is None else {symbol: float(weights[symbol]) for symbol in closes},
        strategy=strategy,
        strategy_params=dict(params),
    )


def summarize(result):
    """Summarize a ``PortfolioResult`` as a dict (no printing).

    Keys:

    * ``short``, ``long``, ``fee``, ``fee_pct``: the settings that were run;
      with a strategy other than ``sma_cross``, ``strategy`` (its name) and
      ``params`` (all its parameters) take the place of ``short`` and ``long``;
    * ``weights``: only when weights were given, symbol to percent in table order;
    * ``start_date``, ``end_date``: the first and last shared dates;
    * ``shared_dates``: how many dates every symbol shares (bars used);
    * ``initial_cash``, ``final_equity``: the summed starting cash and the
      summed account value on the last shared date;
    * ``return_pct``: the portfolio's return on the starting cash;
    * ``max_drawdown_pct``: ``backtest.max_drawdown_pct`` of the summed equity
      curve (<= 0), never an average of the symbols' drawdowns;
    * ``buy_hold_return_pct``: buy and hold with the same cash split (equal,
      or the weights), i.e. the symbols' buy-and-hold final equities added up
      and compared to the starting cash;
    * ``worst_symbol_drawdown``: ``{"symbol", "max_drawdown_pct"}`` for the
      symbol whose own equity curve fell furthest (on a tie, the first symbol
      in the portfolio's order);
    * ``symbols``: one dict per symbol, in the portfolio's order, with
      ``symbol``, ``bars_used``, ``bars_lost``, ``return_pct``, ``trades``
      (number of fills) and ``buy_hold_return_pct``.
    """
    results = result.results
    initial_cash = sum(r.initial_cash for r in results.values())
    final_equity = result.equity[-1]
    buy_hold_final = sum(r.benchmark.final_equity for r in results.values())

    worst_symbol = None
    worst_drawdown = None
    for symbol, r in results.items():
        drawdown = r.max_drawdown_pct
        if worst_drawdown is None or drawdown < worst_drawdown:
            worst_symbol, worst_drawdown = symbol, drawdown

    if result.strategy == "sma_cross":
        summary = {"short": result.short, "long": result.long}
    else:
        summary = {"strategy": result.strategy, "params": dict(result.strategy_params)}
    summary.update({
        "fee": result.fee,
        "fee_pct": result.fee_pct,
    })
    if result.weights is not None:
        summary["weights"] = dict(result.weights)
    summary.update({
        "start_date": result.dates[0],
        "end_date": result.dates[-1],
        "shared_dates": len(result.dates),
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "return_pct": (final_equity - initial_cash) / initial_cash * 100.0,
        "max_drawdown_pct": max_drawdown_pct(result.equity),
        "buy_hold_return_pct": (buy_hold_final - initial_cash) / initial_cash * 100.0,
        "worst_symbol_drawdown": {"symbol": worst_symbol, "max_drawdown_pct": worst_drawdown},
        "symbols": [
            {
                "symbol": symbol,
                "bars_used": len(r.daily),
                "bars_lost": result.lost[symbol],
                "return_pct": r.return_pct,
                "trades": r.n_trades,
                "buy_hold_return_pct": r.benchmark.return_pct,
            }
            for symbol, r in results.items()
        ],
    })
    return summary


def _pct(value):
    """A percentage with a sign and 2 decimals; a value that rounds to zero is ``+0.00%``, never ``-0.00%``."""
    text = f"{value:+.2f}"
    if text == "-0.00":
        text = "+0.00"
    return text + "%"


def _weight_text(percent):
    """A weight as a short percentage: 70.0 -> "70%", 33.5 -> "33.5%" (no sign: it is a share, not a change)."""
    text = repr(float(percent))
    return (text[:-2] if text.endswith(".0") else text) + "%"


def title_line(summary):
    """The report's first line for a ``summarize`` dict: symbols, cash split, rule, fees.

    The rule is ``SMA 20/50 crossover`` for the SMA crossover and, for another
    strategy, its name and parameters as ``strategy_text`` writes them.
    """
    n = len(summary["symbols"])
    weights = summary.get("weights")
    if weights is None:
        split = "cash split equally"
    else:
        split = "cash split by weight (" + ", ".join(f"{s} {_weight_text(w)}" for s, w in weights.items()) + ")"
    if "strategy" in summary:
        rule = strategy_text(summary["strategy"], summary["params"])
    else:
        rule = f"SMA {summary['short']}/{summary['long']} crossover"
    return (
        f"Portfolio: {n} symbol{'' if n == 1 else 's'}, {split}, {rule},"
        f" fee {summary['fee']:,.2f} + {summary['fee_pct']:.2f}%, on the dates every file shares"
    )


def format_portfolio(summary, skipped=None):
    """Report text for a ``summarize`` dict; returns one string and prints nothing.

    A title line (``title_line``: the SMA windows or the strategy, and the fees), the date range and number of shared dates, the starting
    cash and final equity, the portfolio's return, maximum drawdown (from the
    summed equity curve) and equal-weight buy-and-hold return, a table with
    one row per symbol (symbol, bars used, bars lost, return, trades, buy and
    hold; with weights a Weight column after the symbol), the worst single-symbol drawdown with its symbol, a note when any
    symbol lost bars, the skipped files when ``skipped`` (a list of
    ``(filename, reason)``) is not empty, and ``cli.DISCLAIMER``. Percentages have a sign and 2
    decimals. The symbol column is as wide as the longest name (at least as
    wide as its header). Lines are joined by newlines, with no trailing newline.
    """
    rows = summary["symbols"]
    weights = summary.get("weights")
    buy_hold = "equal weight" if weights is None else "same weights"
    lines = [
        title_line(summary),
        f"Dates: {summary['start_date']} to {summary['end_date']} ({summary['shared_dates']} shared dates)",
        f"Cash: {summary['initial_cash']:,.2f}  Final equity: {summary['final_equity']:,.2f}",
        f"Return: {_pct(summary['return_pct'])}  Max drawdown: {_pct(summary['max_drawdown_pct'])}"
        f"  Buy & hold ({buy_hold}): {_pct(summary['buy_hold_return_pct'])}",
    ]

    headers = ("Symbol",) + (("Weight",) if weights is not None else ()) + (
        "Bars used", "Bars lost", "Return", "Trades", "Buy&Hold")
    cells = [
        (
            row["symbol"],
            *((_weight_text(weights[row["symbol"]]),) if weights is not None else ()),
            str(row["bars_used"]),
            str(row["bars_lost"]),
            _pct(row["return_pct"]),
            str(row["trades"]),
            _pct(row["buy_hold_return_pct"]),
        )
        for row in rows
    ]
    widths = [max(len(text) for text in column) for column in zip(headers, *cells)]

    def table_line(values):
        symbol = values[0].ljust(widths[0])
        rest = (value.rjust(width) for value, width in zip(values[1:], widths[1:]))
        return "  ".join([symbol, *rest])

    lines.append(table_line(headers))
    lines.extend(table_line(values) for values in cells)

    worst = summary["worst_symbol_drawdown"]
    lines.append(f"Worst single-symbol drawdown: {_pct(worst['max_drawdown_pct'])} ({worst['symbol']})")
    if any(row["bars_lost"] for row in rows):
        lines.append("Note: dates not shared by every file were dropped (see Bars lost); nothing was filled in.")
    if skipped:
        lines.append(f"Skipped: {len(skipped)}")
        lines.extend(f"  {reason}" for _, reason in skipped)
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def read_folder(folder):
    """``(tables, skipped)`` for every ``.csv`` file directly inside ``folder``.

    ``tables`` maps each usable file's symbol to ``(dates, closes)``, ready for
    ``run_portfolio``; ``skipped`` lists ``(filename, reason)`` for every file
    that was not used, with a one-line reason. Files are found with
    ``scan.price_files`` (which raises ScanError for a missing folder, a path
    that is not a folder, or no ``.csv`` file) and read like ``--scan`` reads
    them, with ``data.decode_price_bytes`` and ``data.parse_price_text``.
    """
    return _read_files(price_files(folder, label=FOLDER_LABEL))


def _read_files(files):
    """``read_folder`` on the ``(symbol, filename, path)`` list from ``scan.price_files``."""
    return _read_entries([(symbol, name, lambda path=path: _read_disk(path)) for symbol, name, path in files])


def _read_disk(path):
    with open(path, "rb") as f:
        return decode_price_bytes(f.read())


def read_texts(files, label="the request", max_bars=None):
    """``(tables, skipped)`` for CSV texts held in memory: ``files`` maps a file name to its text.

    Never reads the disk: the names are only labels. They are treated like the
    names in a folder: only names ending in ``.csv`` (any capitalisation)
    count, in name order (so the order of ``files`` does not matter), and the
    symbol is the name without ``.csv``. Each text is read, checked and
    skipped exactly as a file in a folder would be. Raises ScanError when no
    name ends in ``.csv`` (``label`` stands in for the folder) and
    ScanLimitError when a file has more than ``max_bars`` rows.
    """
    entries = []
    for name in sorted(files):
        symbol, ext = os.path.splitext(name)
        if ext.lower() == ".csv":
            entries.append((symbol, name, lambda text=files[name]: text))
    if not entries:
        raise ScanError(f"no .csv files in {label}")
    return _read_entries(entries, max_bars=max_bars)


def _read_entries(entries, max_bars=None):
    """Read ``(symbol, filename, load)`` entries, ``load()`` returning the CSV text, into ``(tables, skipped)``."""
    tables = {}
    sources = {}
    skipped = []
    for symbol, name, load in entries:
        try:
            dates, closes = parse_price_text(load(), name)
        except OSError as exc:
            skipped.append((name, f"{name}: cannot read the file ({exc.strerror or exc})"))
            continue
        except ValueError as exc:
            skipped.append((name, _one_line(exc)))
            continue
        if max_bars is not None and len(closes) > max_bars:
            raise ScanLimitError(f"{name} has too many price rows ({len(closes):,}); the limit is {max_bars:,}")
        reason = _unusable(name, symbol, dates, closes, sources)
        if reason is not None:
            skipped.append((name, reason))
            continue
        tables[symbol] = (dates, closes)
        sources[symbol] = name
    return tables, skipped


def _unusable(name, symbol, dates, closes, sources):
    """The one-line reason a parsed file cannot join the portfolio, or None."""
    if not closes:
        return f"{name}: no price rows found"
    if dates is None:
        return f"{name}: no 'date' column; the portfolio lines files up by date"
    for row, (date, close) in enumerate(zip(dates, closes), start=1):
        if not date:
            return f"{name} data row {row}: blank date"
        if not close > 0:
            return f"{name} data row {row}: close must be positive, got {close:g}"
    if symbol in sources:
        return f"{name}: symbol {symbol} is already read from {sources[symbol]}"
    return None


_WEIGHT_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)")


def parse_weights(items):
    """``{symbol: Decimal percent}`` from ``["A=60", "B=40"]`` (``--weights`` or the web page's ``weights``).

    Each item is SYMBOL=PERCENT, split on the last ``=`` (so a file
    ``X=Y.csv`` is ``X=Y=50``); the symbol is the file name without ``.csv``.
    Percentages are plain decimal numbers, each above 0, and they must add up
    to exactly 100 as written (``33.3 33.3 33.4`` does, ``33.33`` three times
    does not). A symbol may be listed once. Raises ValueError with a one-line
    message otherwise.
    """
    weights = {}
    for item in items:
        symbol, sep, number = item.rpartition("=")
        if not sep or not symbol:
            raise ValueError(f"--weights: {item!r} is not SYMBOL=PERCENT (like A=60)")
        if not _WEIGHT_NUMBER.fullmatch(number):
            raise ValueError(f"--weights: the weight for {symbol} must be a number like 60 or 33.5, got {number!r}")
        percent = Decimal(number)
        if not percent > 0:
            raise ValueError(f"--weights: the weight for {symbol} must be above 0, got {number}")
        if symbol in weights:
            raise ValueError(f"--weights: {symbol} is listed more than once")
        weights[symbol] = percent
    total = sum(weights.values(), Decimal(0))
    if total != 100:
        raise ValueError(f"--weights must add up to 100, got {total}")
    return weights


class WeightsError(ValueError):
    """Weights that do not match the files: a usage problem (exit 2 in the command, 400 on the web page)."""


def _check_weights(weights, tables, skipped, label):
    """Raise WeightsError or PortfolioError unless ``weights`` name exactly the usable files."""
    skipped_by_symbol = {}
    for name, reason in skipped:
        skipped_by_symbol.setdefault(os.path.splitext(name)[0], (name, reason))
    unknown = [s for s in weights if s not in tables and s not in skipped_by_symbol]
    if unknown:
        raise WeightsError(f"--weights: no .csv file for {', '.join(unknown)} in {label}")
    missing = [s for s in tables if s not in weights]
    if missing:
        raise WeightsError(f"--weights: no weight for {', '.join(missing)}; every file that is used needs one")
    for symbol in weights:
        if symbol not in tables:
            name, reason = skipped_by_symbol[symbol]
            raise PortfolioError(f"{name} has a weight but was skipped: {reason}")


class PortfolioError(ValueError):
    """A problem with the files or the run; the message is the one line the command prints after ``Error:``."""


def run_files(tables, skipped, label, cash=DEFAULT_CASH, short=DEFAULT_SHORT, long=DEFAULT_LONG, fee=0.0, fee_pct=0.0,
              weights=None, strategy="sma_cross", strategy_params=None):
    """``run_portfolio`` on read files, after checking the weights and that at least 2 files can be used.

    ``label`` names where the files came from (the folder, or "the request").
    ``weights`` (from ``parse_weights``, or None) must name exactly the usable
    files: WeightsError for a symbol with no file or a usable file without a
    weight (checked first), PortfolioError for a weighted file that was
    skipped. Then PortfolioError, with a one-line message, for fewer than 2
    usable files and for anything ``run_portfolio`` refuses. ``strategy`` and
    ``strategy_params`` are passed on to ``run_portfolio``.
    """
    if weights is not None:
        _check_weights(weights, tables, skipped, label)
    if len(tables) < 2:
        found = len(tables) + len(skipped)
        raise PortfolioError(
            f"only {len(tables)} of the {found} .csv files in {label} could be used"
            f" ({len(skipped)} skipped); a portfolio needs at least 2"
        )
    try:
        return run_portfolio(
            tables, cash=cash, short=short, long=long, fee=fee, fee_pct=fee_pct, weights=weights,
            strategy=strategy, strategy_params=strategy_params,
        )
    except ValueError as exc:
        raise PortfolioError(_one_line(exc)) from None


def run_texts(files, short=DEFAULT_SHORT, long=DEFAULT_LONG, cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0,
              label="the request", max_bars=None, weights=None, strategy="sma_cross", strategy_params=None):
    """The ``--json`` object for CSV texts held in memory (the web page's ``POST /api/portfolio``).

    ``read_texts``, then ``run_files``, ``summarize`` and ``json_data``: the
    command's own steps. Settings must already be checked (``check_settings``,
    ``parse_weights``). Raises ScanError, ScanLimitError, WeightsError or PortfolioError.
    ``strategy`` and ``strategy_params`` are passed on to ``run_files``.
    """
    tables, skipped = read_texts(files, label=label, max_bars=max_bars)
    result = run_files(
        tables, skipped, label, cash=cash, short=short, long=long, fee=fee, fee_pct=fee_pct, weights=weights,
        strategy=strategy, strategy_params=strategy_params,
    )
    return json_data(summarize(result), skipped)


def csv_rows(result):
    """Header and rows for ``write_csv``: date, portfolio equity, then one equity per symbol.

    Symbols are in the table's order. Money has 2 decimals; every cell is
    rounded on its own, so the portfolio cell is the true summed equity to the
    cent, and can differ by a cent from the sum of the rounded symbol cells.
    """
    symbols = list(result.results)
    curves = [result.results[symbol].equity_curve for symbol in symbols]
    rows = [["date", "portfolio", *symbols]]
    for i, date in enumerate(result.dates):
        rows.append([date, f"{result.equity[i]:.2f}", *(f"{curve[i]:.2f}" for curve in curves)])
    return rows


def write_csv(result, path):
    """Write ``csv_rows(result)`` to ``path``; returns the number of date rows. Raises OSError.

    Written with the ``csv`` module (odd symbol names are quoted) to a
    temporary file in the same folder, then renamed over ``path``, so a
    failure never leaves a partial file behind.
    """
    rows = csv_rows(result)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(rows)
        os.chmod(tmp, 0o666 & ~_umask())  # mkstemp makes 0600; give OUT the mode open() would
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(rows) - 1


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _same_file(a, b):
    if os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b)):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False  # ``a`` does not exist yet, so it is not ``b``


def csv_target_problem(out, inputs):
    """A one-line reason ``out`` must not be written, or None.

    ``out`` must not be a folder, its folder must exist, and it must not be
    the same file as any of ``inputs`` (compared after resolving ``.``,
    ``..`` and symbolic links, and by file identity, which also catches hard
    links).
    """
    if os.path.isdir(out):
        return f"cannot write {out}: it is a folder"
    parent = os.path.dirname(out) or "."
    if not os.path.isdir(parent):
        return f"cannot write {out}: folder {parent} does not exist"
    for path in inputs:
        if _same_file(out, path):
            return f"--csv refuses to overwrite the input file {path}"
    return None


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.portfolio",
        description="Backtest the SMA crossover (or --strategy) on every .csv file in a folder, with the cash"
        " split equally (or by --weights), on the dates every file shares.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("folder", help="folder whose .csv files (with 'date' and 'close' columns) are the symbols")
    parser.add_argument(
        "--short", type=int, default=DEFAULT_SHORT, metavar="N", action=_Given,
        help=f"short SMA window (default: {DEFAULT_SHORT})",
    )
    # Hidden exact alias: "--s" meant --short (argparse abbreviation) before --strategy existed, and an
    # exact option string wins over the now-ambiguous prefix. Its errors still say --short.
    short_alias = parser.add_argument(
        "--s", dest="short", type=int, default=DEFAULT_SHORT, metavar="N", action=_Given, help=argparse.SUPPRESS
    )
    short_alias.option_strings = ["--short"]
    parser.add_argument(
        "--long", type=int, default=DEFAULT_LONG, metavar="N", action=_Given,
        help=f"long SMA window (default: {DEFAULT_LONG})",
    )
    parser.add_argument(
        "--cash", type=float, default=DEFAULT_CASH, metavar="AMOUNT",
        help=f"starting cash, split equally between the files or by --weights (default: {DEFAULT_CASH:,.0f})",
    )
    parser.add_argument("--fee", type=float, default=0.0, metavar="AMOUNT", help="fixed cost per trade (default: 0)")
    parser.add_argument(
        "--fee-pct", type=float, default=0.0, metavar="PCT", help="percent of traded value per trade (default: 0)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print one JSON object (summary, skipped files, disclaimer) instead of the text",
    )
    parser.add_argument(
        "--weights", nargs="+", action="extend", default=None, metavar="SYMBOL=PCT",
        help="split the cash by these percentages instead of equally, e.g. A=60 B=40: one per file used,"
        " each above 0, adding up to 100",
    )
    parser.add_argument(
        "--csv", default=None, metavar="OUT",
        help="also write one row per shared date to OUT: date, portfolio equity, then each symbol's equity",
    )
    strategy = parser.add_argument(
        "--strategy", choices=strategy_names(), default=None, metavar="NAME",
        help=f"rule every symbol trades (default: {DEFAULT_STRATEGY}), one of: {', '.join(strategy_names())};"
        " --short and --long only apply to sma_cross",
    )
    param = parser.add_argument(
        "--param", action="append", default=None, metavar="KEY=VALUE",
        help="override a parameter of the strategy, e.g. window=10 (repeatable); without --strategy it adjusts"
        " sma_cross",
    )
    # Keep the usage line (printed with --help and with every usage error) exactly as it was before
    # --strategy and --param existed; they are still listed, with their help, in --help.
    unlisted = (strategy, param)
    helps = [action.help for action in unlisted]
    for action in unlisted:
        action.help = argparse.SUPPRESS
    parser.usage = parser.format_usage()[len("usage: ") :].rstrip("\n").replace("%", "%%")
    for action, text in zip(unlisted, helps):
        action.help = text
    return parser


def check_settings(short, long, cash, fee, fee_pct):
    """Raise ValueError, with the command's message, for settings the portfolio refuses.

    ``nan`` and ``inf`` are refused first: argparse accepts them as floats and
    the shared ``cli.check_costs`` lets some of them through. Then the main
    CLI's window and cost checks, with its messages.
    """
    for flag, value in (("--cash", cash), ("--fee", fee), ("--fee-pct", fee_pct)):
        if not math.isfinite(value):
            raise ValueError(f"{flag} must be a finite number, got {value}")
    check_windows(short, long)
    check_costs(cash, fee, fee_pct)


def check_strategy_windows(strategy, short_given=False, long_given=False):
    """Raise ValueError when ``--short`` or ``--long`` was given with a strategy other than ``sma_cross``.

    Only ``sma_cross`` has those windows; another strategy's parameters are set with ``--param``.
    """
    if strategy == "sma_cross":
        return
    for key, given in (("short", short_given), ("long", long_given)):
        if given:
            raise ValueError(f"--{key} only applies to --strategy sma_cross; set {strategy}'s parameters with --param")


def check_strategy(strategy, items, short=DEFAULT_SHORT, long=DEFAULT_LONG, short_given=False, long_given=False):
    """The ``--param`` overrides (``{key: number}``, empty without ``--param``) for ``strategy``, checked.

    ``items`` are the ``--param`` texts (or None). The main command's checks,
    in its order and with its messages: each item is KEY=VALUE with a number
    (``cli.parse_param``), a key may be given once, for ``sma_cross`` a
    ``short`` or ``long`` that contradicts a given ``--short``/``--long`` is
    refused, and ``strategies.resolve_params`` must accept the overrides (the
    key exists, the value is allowed). Raises ValueError for an unknown
    strategy (argparse's choices catch it first on the command line).

    As in the main command, the overrides are checked against the strategy's
    defaults: ``--short 30 --param long=25`` passes here and is refused by
    the run (``short window must be smaller than long window``, exit 1).
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from: {', '.join(strategy_names())}")
    overrides = {}
    for text in items or []:
        key, value = parse_param(text)
        if key in overrides:
            raise ValueError(f"--param {key} given more than once")
        overrides[key] = value
    if strategy == "sma_cross":
        for key, top, given in (("short", short, short_given), ("long", long, long_given)):
            if key in overrides and given and overrides[key] != top:
                raise ValueError(f"--param {key}={overrides[key]} contradicts --{key} {top}; give only one")
    resolve_params(strategy, overrides)
    return overrides


def validate_args(parser, args):
    """Turn rule violations into usage errors (exit 2), with ``check_settings``'s and ``check_strategy``'s messages.

    Sets ``args.strategy`` (the default when not given) and
    ``args.strategy_params`` (the ``--param`` overrides, or None without them).
    """
    args.strategy = args.strategy or DEFAULT_STRATEGY
    short_given, long_given = getattr(args, "short_given", False), getattr(args, "long_given", False)
    try:
        check_strategy_windows(args.strategy, short_given, long_given)
        check_settings(args.short, args.long, args.cash, args.fee, args.fee_pct)
        overrides = check_strategy(args.strategy, args.param, args.short, args.long, short_given, long_given)
    except ValueError as exc:
        parser.error(str(exc))
    args.strategy_params = overrides or None
    if args.csv is not None and not args.csv.strip():
        parser.error("--csv needs a file name")
    if args.weights is not None:
        try:
            args.weights = parse_weights(args.weights)
        except ValueError as exc:
            parser.error(str(exc))
    return args


def json_data(summary, skipped):
    """The ``--json`` object: ``summary`` (the ``summarize`` dict as it is,
    numbers not rounded), ``skipped`` (a list of ``{"file", "reason"}``,
    empty when nothing was skipped) and ``disclaimer`` (``cli.DISCLAIMER``).

    With a strategy other than ``sma_cross`` it starts with ``title``, the
    text report's first line (``title_line``); otherwise there is no ``title``.
    """
    data = {"title": title_line(summary)} if "strategy" in summary else {}
    return {
        **data,
        "summary": summary,
        "skipped": [{"file": filename, "reason": reason} for filename, reason in skipped],
        "disclaimer": DISCLAIMER,
    }


def main(argv=None):
    parser = build_parser()
    args = validate_args(parser, parser.parse_args(argv))

    try:
        files = price_files(args.folder, label=FOLDER_LABEL)
    except ScanError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.csv is not None:
        problem = csv_target_problem(args.csv, [path for _, _, path in files])
        if problem is not None:
            print(f"Error: {problem}", file=sys.stderr)
            return 1
    tables, skipped = _read_files(files)
    try:
        result = run_files(
            tables, skipped, args.folder,
            cash=args.cash, short=args.short, long=args.long, fee=args.fee, fee_pct=args.fee_pct,
            weights=args.weights, strategy=args.strategy, strategy_params=args.strategy_params,
        )
    except WeightsError as exc:
        parser.error(str(exc))
    except PortfolioError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.csv is not None:
        try:
            write_csv(result, args.csv)
        except OSError as exc:
            print(f"Error: cannot write {args.csv}: {exc.strerror or exc}", file=sys.stderr)
            return 1

    summary = summarize(result)
    if args.json:
        print(json.dumps(json_data(summary, skipped), indent=2, allow_nan=False))
    else:
        print(format_portfolio(summary, skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
