"""Manual paper-trade journal kept in a CSV file you name.

Usage:
    python -m trading_assistant.journal FILE add --date D --symbol S --side buy|sell
        --qty Q --price P [--fee F] [--note TEXT]
    python -m trading_assistant.journal FILE list [--symbol S]
    python -m trading_assistant.journal FILE summary [--mark SYMBOL=PRICE ...]

File format: a header ``date,symbol,side,qty,price,fee,note`` and one trade per
row. ``date`` is YYYY-MM-DD, ``symbol`` is stored upper-case, ``side`` is buy or
sell, ``qty`` is a positive whole number, ``price`` is positive, ``fee`` is zero
or more (default 0). Rows are replayed in file order.

Accounting: FIFO lots. A buy's fee is added to the cost of its shares (spread
evenly over them); a sell's fee is deducted from its proceeds. Realized P&L is
proceeds minus the cost of the shares sold, oldest lots first. Average cost is
the cost (fees included) of the open shares divided by their number. Unrealized
P&L is open quantity times the mark price minus the open cost. Selling more than
the open quantity (no shorting) is an error.

This only records trades made on paper. It does not connect to anything.

Exit codes:
    0  success
    1  data problem (file missing/unreadable or with a bad row, reported with its
       line number; an `add` that would sell more than the open quantity, which
       leaves the file unchanged)
    2  usage problem (bad option value, a missing command)

This is a research aid. It is not financial advice.
"""

import argparse
import csv
import datetime
import math
import os
import re
import sys

from .cli import DISCLAIMER

HEADER = ["date", "symbol", "side", "qty", "price", "fee", "note"]


def parse_trade(fields, line_no=None):
    """Validate one row (a list of 7 strings); return a trade dict.

    Keys: date, symbol (upper-case), side, qty (int), price, fee (floats), note.
    Raises ValueError; the message starts with ``line N:`` when ``line_no`` is given.
    """
    prefix = f"line {line_no}: " if line_no is not None else ""
    if len(fields) != len(HEADER):
        raise ValueError(f"{prefix}expected {len(HEADER)} columns, found {len(fields)}")
    date, symbol, side, qty, price, fee, note = [f.strip() for f in fields[:6]] + [fields[6]]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"{prefix}bad date {date!r}; use YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError(f"{prefix}bad date {date!r}; not a real calendar date") from None
    if not symbol or re.search(r"\s", symbol):
        raise ValueError(f"{prefix}bad symbol {symbol!r}; it must be one word")
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"{prefix}bad side {side!r}; use buy or sell")
    if not re.fullmatch(r"\d+", qty) or int(qty) < 1:
        raise ValueError(f"{prefix}bad qty {qty!r}; use a positive whole number")
    price_v = _number(price, f"{prefix}bad price {price!r}; use a positive number")
    if price_v <= 0:
        raise ValueError(f"{prefix}bad price {price!r}; use a positive number")
    fee_v = 0.0 if fee == "" else _number(fee, f"{prefix}bad fee {fee!r}; use zero or a positive number")
    if fee_v < 0:
        raise ValueError(f"{prefix}bad fee {fee!r}; use zero or a positive number")
    return {
        "date": date,
        "symbol": symbol.upper(),
        "side": side,
        "qty": int(qty),
        "price": price_v,
        "fee": fee_v,
        "note": note,
    }


def _number(text, message):
    try:
        value = float(text)
    except ValueError:
        raise ValueError(message) from None
    if not math.isfinite(value):
        raise ValueError(message)
    return value


class Ledger:
    """FIFO lots per symbol plus realized P&L, built by applying trades in order."""

    def __init__(self):
        self.lots = {}  # symbol -> list of [qty_left, cost_per_share], oldest first
        self.realized = {}  # symbol -> realized P&L

    def open_qty(self, symbol):
        return sum(q for q, _ in self.lots.get(symbol, []))

    def apply(self, trade):
        """Apply one trade. Raises ValueError if a sell exceeds the open quantity."""
        sym, qty = trade["symbol"], trade["qty"]
        lots = self.lots.setdefault(sym, [])
        self.realized.setdefault(sym, 0.0)
        if trade["side"] == "buy":
            lots.append([qty, (qty * trade["price"] + trade["fee"]) / qty])
            return
        held = self.open_qty(sym)
        if qty > held:
            raise ValueError(f"cannot sell {qty} {sym}: only {held} open (no shorting)")
        cost = 0.0
        need = qty
        while need:
            lot = lots[0]
            take = min(need, lot[0])
            cost += take * lot[1]
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                lots.pop(0)
        self.realized[sym] += qty * trade["price"] - trade["fee"] - cost

    def position(self, symbol):
        """``(open_qty, open_cost)`` for a symbol; cost includes buy fees."""
        lots = self.lots.get(symbol, [])
        return sum(q for q, _ in lots), sum(q * c for q, c in lots)


def read_journal(path):
    """Read and replay a journal file; return ``(trades, ledger)``.

    Raises OSError if it cannot be opened and ValueError (``line N: ...``) for a
    bad header, a bad row, or a sell larger than the open quantity. An empty
    file counts as a journal with no trades.
    """
    trades = []
    ledger = Ledger()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        seen_header = False
        for row in reader:
            if not row:
                continue
            if not seen_header:
                if [c.strip().lower() for c in row] != HEADER:
                    raise ValueError(f"line {reader.line_num}: header must be {','.join(HEADER)}")
                seen_header = True
                continue
            trade = parse_trade(row, reader.line_num)
            try:
                ledger.apply(trade)
            except ValueError as exc:
                raise ValueError(f"line {reader.line_num}: {exc}") from None
            trades.append(trade)
    return trades, ledger


def append_trade(path, trade):
    """Append ``trade`` to ``path``, creating the file with a header if needed."""
    needs_header = not os.path.exists(path) or os.path.getsize(path) == 0
    needs_newline = False
    if not needs_header:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b"\n", b"\r")
    with open(path, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        writer = csv.writer(f, lineterminator="\n")
        if needs_header:
            writer.writerow(HEADER)
        writer.writerow(
            [
                trade["date"],
                trade["symbol"],
                trade["side"],
                trade["qty"],
                repr(trade["price"]),
                repr(trade["fee"]),
                trade["note"],
            ]
        )


def summarize(ledger, marks=None):
    """Per-symbol rows and totals from a ledger.

    Each row: symbol, open_qty, avg_cost (None if flat), realized, mark (or None)
    and unrealized (None unless the position is open and has a mark). Totals:
    realized, unrealized (marked positions only) and unmarked (open symbols
    without a mark).
    """
    marks = marks or {}
    rows = []
    total_realized = total_unrealized = 0.0
    unmarked = 0
    for sym in sorted(ledger.lots):
        qty, cost = ledger.position(sym)
        mark = marks.get(sym)
        unreal = None
        if qty and mark is not None:
            unreal = qty * mark - cost
            total_unrealized += unreal
        elif qty:
            unmarked += 1
        total_realized += ledger.realized[sym]
        rows.append(
            {
                "symbol": sym,
                "open_qty": qty,
                "avg_cost": cost / qty if qty else None,
                "realized": ledger.realized[sym],
                "mark": mark,
                "unrealized": unreal,
            }
        )
    return rows, {"realized": total_realized, "unrealized": total_unrealized, "unmarked": unmarked}


def _positive_int(text):
    if not re.fullmatch(r"\d+", text) or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive whole number")
    return int(text)


def _positive_float(text):
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number")
    return value


def _fee(text):
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not zero or a positive number")
    return value


def _date(text):
    try:
        parse_trade([text, "X", "buy", "1", "1", "0", ""])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    return text


def _mark(text):
    sym, sep, price = text.partition("=")
    if not sep or not sym.strip():
        raise argparse.ArgumentTypeError(f"{text!r} is not SYMBOL=PRICE")
    return sym.strip().upper(), _positive_float(price)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.journal",
        description="Record and summarize paper trades in a CSV journal.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("journal_path", metavar="FILE", help="journal CSV file")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{add,list,summary}")

    add = sub.add_parser("add", help="append a trade (creates the file if missing)")
    add.add_argument("--date", required=True, type=_date, metavar="YYYY-MM-DD")
    add.add_argument("--symbol", required=True)
    add.add_argument("--side", required=True, choices=["buy", "sell"])
    add.add_argument("--qty", required=True, type=_positive_int)
    add.add_argument("--price", required=True, type=_positive_float)
    add.add_argument("--fee", type=_fee, default=0.0, help="fee for this trade (default: 0)")
    add.add_argument("--note", default="")

    lst = sub.add_parser("list", help="print the trades")
    lst.add_argument("--symbol", default=None, help="only this symbol")

    summ = sub.add_parser("summary", help="positions and P&L per symbol")
    summ.add_argument("--mark", action="append", type=_mark, default=[], metavar="SYMBOL=PRICE")
    return parser


def _validate_add(parser, args):
    if not args.symbol.strip() or re.search(r"\s", args.symbol.strip()):
        parser.error("--symbol must be one word")
    if "\n" in args.note or "\r" in args.note:
        parser.error("--note must be a single line")


def format_trades(trades):
    lines = [f"{'Date':<10s} {'Symbol':<8s} {'Side':<4s} {'Qty':>6s} {'Price':>12s} {'Fee':>9s}  Note"]
    for t in trades:
        lines.append(
            f"{t['date']:<10s} {t['symbol']:<8s} {t['side']:<4s} {t['qty']:>6d} {t['price']:>12.4f} {t['fee']:>9.2f}  {t['note']}"
        )
    return lines


def format_summary(rows, totals):
    lines = [f"{'Symbol':<8s} {'Open qty':>8s} {'Avg cost':>12s} {'Realized':>12s} {'Mark':>12s} {'Unrealized':>12s}"]
    for r in rows:
        avg = "n/a" if r["avg_cost"] is None else f"{r['avg_cost']:.4f}"
        mark = "n/a" if r["mark"] is None or not r["open_qty"] else f"{r['mark']:.4f}"
        unreal = "n/a" if r["unrealized"] is None else f"{r['unrealized']:+.2f}"
        lines.append(
            f"{r['symbol']:<8s} {r['open_qty']:>8d} {avg:>12s} {r['realized']:>+12.2f} {mark:>12s} {unreal:>12s}"
        )
    line = f"Total realized {totals['realized']:+.2f}, unrealized {totals['unrealized']:+.2f}"
    if totals["unmarked"]:
        line += f" (excludes {totals['unmarked']} open symbol(s) without a mark)"
    lines.append(line)
    return lines


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "add":
        _validate_add(parser, args)

    path = args.journal_path
    try:
        if args.command == "add" and not os.path.exists(path):
            trades, ledger = [], Ledger()
        else:
            trades, ledger = read_journal(path)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
        detail = f"{path}: {exc}" if isinstance(exc, ValueError) else f"cannot read {path}: {getattr(exc, 'strerror', None) or exc}"
        print(f"Error: {detail}", file=sys.stderr)
        return 1

    if args.command == "add":
        trade = {
            "date": args.date,
            "symbol": args.symbol.strip().upper(),
            "side": args.side,
            "qty": args.qty,
            "price": args.price,
            "fee": args.fee,
            "note": args.note,
        }
        try:
            ledger.apply(trade)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        try:
            append_trade(path, trade)
        except OSError as exc:
            print(f"Error: cannot write {path}: {exc.strerror or exc}", file=sys.stderr)
            return 1
        print(f"Added: {trade['date']} {trade['side']} {trade['qty']} {trade['symbol']} @ {trade['price']:.4f}")
        return 0

    if args.command == "list":
        shown = trades
        if args.symbol:
            shown = [t for t in trades if t["symbol"] == args.symbol.strip().upper()]
        for line in format_trades(shown):
            print(line)
        print(f"{len(shown)} trade(s)")
        print(DISCLAIMER)
        return 0

    marks = dict(args.mark)
    for sym in sorted(set(marks) - set(ledger.lots)):
        print(f"Note: --mark {sym} ignored; no trades for that symbol", file=sys.stderr)
    rows, totals = summarize(ledger, marks)
    for line in format_summary(rows, totals):
        print(line)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
