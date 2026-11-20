"""Data summary for a price file.

Usage:
    python -m trading_assistant.summary prices.csv

Prints the number of rows, the first and last date, the minimum, maximum and
mean close, the largest one-bar rise and fall (percent change of the close from
the bar before, with the date of the bar), how many rows repeat an earlier
date, how many closes are zero or negative, and the annualised volatility of the
per-bar returns (sample standard deviation times sqrt(252)). Returns are only
taken from a previous close above zero. Without a `date` column the date lines
say "n/a" and bars are named by position (the first bar is bar 1).

It does not check for missing business days or market holidays.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows)
    2  usage problem (unparseable arguments)

This is a research aid. It does not place orders and it is not financial advice.
"""

import argparse
import math
import statistics
import sys

from .cli import DISCLAIMER, load_price_table

PERIODS_PER_YEAR = 252


def one_bar_changes(closes):
    """List of ``(bar, percent change)`` for bars whose previous close is above zero.

    ``bar`` is the 0-based index of the later bar.
    """
    return [(i, (closes[i] / closes[i - 1] - 1.0) * 100.0) for i in range(1, len(closes)) if closes[i - 1] > 0]


def summarise(dates, closes):
    """Return a dict of the summary numbers for ``closes`` (non-empty) and optional ``dates``.

    Keys: rows, first_date, last_date (None without dates), min_close, max_close,
    mean_close, rise and fall (``(bar, percent)`` or None when no bar rose /
    fell), repeated_dates (None without dates), non_positive, volatility_pct
    (None with fewer than 2 returns).
    """
    changes = one_bar_changes(closes)
    rises = [c for c in changes if c[1] > 0]
    falls = [c for c in changes if c[1] < 0]
    returns = [pct / 100.0 for _, pct in changes]
    vol = statistics.stdev(returns) * math.sqrt(PERIODS_PER_YEAR) * 100.0 if len(returns) >= 2 else None
    return {
        "rows": len(closes),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "min_close": min(closes),
        "max_close": max(closes),
        "mean_close": sum(closes) / len(closes),
        "rise": max(rises, key=lambda c: c[1]) if rises else None,
        "fall": min(falls, key=lambda c: c[1]) if falls else None,
        "repeated_dates": len(dates) - len(set(dates)) if dates else None,
        "non_positive": sum(1 for c in closes if c <= 0),
        "volatility_pct": vol,
    }


def format_summary(info, dates):
    """Lines of text for the dict from ``summarise``."""

    def move(entry):
        if entry is None:
            return "none"
        bar, pct = entry
        when = dates[bar] if dates else f"bar {bar + 1}"
        return f"{pct:+.2f}% on {when}"

    na = "n/a (no date column)"
    vol = "n/a (fewer than 2 returns)" if info["volatility_pct"] is None else f"{info['volatility_pct']:.2f}%"
    rows = [
        ("Rows:", info["rows"]),
        ("First date:", info["first_date"] if dates else na),
        ("Last date:", info["last_date"] if dates else na),
        ("Min close:", f"{info['min_close']:.2f}"),
        ("Max close:", f"{info['max_close']:.2f}"),
        ("Mean close:", f"{info['mean_close']:.2f}"),
        ("Largest rise:", move(info["rise"])),
        ("Largest fall:", move(info["fall"])),
        ("Repeated dates:", info["repeated_dates"] if dates else na),
        ("Non-positive:", info["non_positive"]),
        ("Volatility (ann.):", vol),
    ]
    return [f"{label:<19s}{value}" for label, value in rows]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.summary",
        description="Print a summary of a price file.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("csv_path", help="CSV file with a 'close' column")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        dates, closes = load_price_table(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not closes:
        print("No price rows found.", file=sys.stderr)
        return 1
    for line in format_summary(summarise(dates, closes), dates):
        print(line)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
