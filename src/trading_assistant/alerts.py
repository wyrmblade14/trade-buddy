"""Price and indicator alerts: check a file of simple rules against the last bar.

Usage:
    python -m trading_assistant.alerts rules.txt prices.csv [--all]

Rules file: one rule per line; ``#`` starts a comment (to the end of the line);
blank lines are ignored. A rule is ``<expr> <op> <expr>`` where

    op    is one of  <  <=  >  >=  crosses_above  crosses_below
    expr  is a number (``105.5``, ``-3``), ``close``, or ``sma(N)``, ``ema(N)``
          or ``rsi(N)`` with N a positive whole number

Examples: ``rsi(14) < 30``, ``close crosses_above sma(50)``, ``close > 105.5``.
Rule text is read by a small tokenizer and parser; it is never evaluated as code.

Comparison operators look at the last bar. ``a crosses_above b`` fires when
``a <= b`` on the bar before the last and ``a > b`` on the last bar;
``crosses_below`` is the mirror (``a >= b`` before, ``a < b`` now). If an
indicator has no value yet on a bar that is needed (warm-up), the rule does not
fire and its reason is "not enough data".

By default only the fired rules are printed; ``--all`` prints every rule.

Exit codes:
    0  success, whether or not any rule fired
    1  data problem (rules or price file missing/unreadable, a bad rule with its
       line number, no rules, no `close` column, bad number, no rows)
    2  usage problem (missing arguments)

This is a research aid. It does not place orders and it is not financial advice.
"""

import argparse
import re
import sys

from .cli import DISCLAIMER, load_price_table
from .indicators import ema, rsi, sma

OPERATORS = ("<", "<=", ">", ">=", "crosses_above", "crosses_below")
INDICATORS = {"sma": sma, "ema": ema, "rsi": rsi}
NOT_ENOUGH_DATA = "not enough data"

# Number | word | two-character operator | one-character symbol. Anything else
# (including a stray character) is reported by tokenize().
_TOKEN = re.compile(r"\s*(?:(-?\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z_0-9]*)|(<=|>=)|(.))")


def tokenize(text, line_no=1):
    """Split one rule into tokens (strings); a ``#`` comment is dropped.

    Numbers may carry a leading minus. Raises ValueError, naming the line and
    the offending character, for anything that is not a number, a word, a
    parenthesis or a comparison symbol.
    """
    text = text.split("#", 1)[0]
    tokens = []
    pos = 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN.match(text, pos)
        number, word, pair, single = m.groups()
        token = number or word or pair or single
        if single is not None and single not in "<>()":
            raise ValueError(f"line {line_no}: unexpected character {single!r}")
        tokens.append(token)
        pos = m.end()
    return tokens


def _parse_expr(tokens, i, line_no):
    """Parse one expression starting at ``tokens[i]``; return ``(expr, next_i)``.

    An expression is ``("num", value)``, ``("close",)`` or ``("ind", name, n)``.
    """
    if i >= len(tokens):
        raise ValueError(f"line {line_no}: expected a value at the end of the rule")
    tok = tokens[i]
    if re.fullmatch(r"-?\d+(?:\.\d+)?", tok):
        return ("num", float(tok)), i + 1
    if tok == "close":
        return ("close",), i + 1
    if tok in INDICATORS:
        if i + 1 >= len(tokens) or tokens[i + 1] != "(":
            raise ValueError(f"line {line_no}: expected '(' after {tok!r}")
        if i + 2 >= len(tokens):
            raise ValueError(f"line {line_no}: expected a window after '{tok}('")
        arg = tokens[i + 2]
        if not re.fullmatch(r"\d+", arg) or int(arg) < 1:
            raise ValueError(f"line {line_no}: window must be a positive whole number, got {arg!r}")
        if i + 3 >= len(tokens) or tokens[i + 3] != ")":
            got = repr(tokens[i + 3]) if i + 3 < len(tokens) else "the end of the rule"
            raise ValueError(f"line {line_no}: expected ')' but found {got}")
        return ("ind", tok, int(arg)), i + 4
    raise ValueError(f"line {line_no}: unexpected token {tok!r}; expected a number, close, sma(N), ema(N) or rsi(N)")


def parse_rule(text, line_no=1):
    """Parse one rule line into ``(left, op, right)``; raises ValueError.

    Returns None for a blank or comment-only line.
    """
    tokens = tokenize(text, line_no)
    if not tokens:
        return None
    left, i = _parse_expr(tokens, 0, line_no)
    if i >= len(tokens):
        raise ValueError(f"line {line_no}: expected an operator after {tokens[-1]!r}")
    op = tokens[i]
    if op not in OPERATORS:
        raise ValueError(f"line {line_no}: unknown operator {op!r}; expected one of {', '.join(OPERATORS)}")
    right, i = _parse_expr(tokens, i + 1, line_no)
    if i < len(tokens):
        raise ValueError(f"line {line_no}: unexpected token {tokens[i]!r} after the rule")
    return left, op, right


def format_expr(expr):
    """The canonical text of a parsed expression, e.g. ``sma(50)`` or ``105.5``."""
    if expr[0] == "num":
        return f"{expr[1]:g}"
    if expr[0] == "close":
        return "close"
    return f"{expr[1]}({expr[2]})"


def parse_rules(text):
    """Parse a whole rules file; return a list of rule dicts.

    Each rule has keys ``line`` (1-based line number), ``text`` (canonical
    form, e.g. ``close crosses_above sma(50)``), ``left``, ``op`` and ``right``.
    Raises ValueError (message starts with ``line N:``) on the first bad line.
    """
    rules = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        parsed = parse_rule(raw, line_no)
        if parsed is None:
            continue
        left, op, right = parsed
        rules.append(
            {
                "line": line_no,
                "text": f"{format_expr(left)} {op} {format_expr(right)}",
                "left": left,
                "op": op,
                "right": right,
            }
        )
    return rules


def _series(expr, closes, cache):
    """Per-bar values of ``expr`` (None during warm-up); cached by expression."""
    if expr in cache:
        return cache[expr]
    if expr[0] == "num":
        values = [expr[1]] * len(closes)
    elif expr[0] == "close":
        values = list(closes)
    else:
        values = INDICATORS[expr[1]](closes, expr[2])
    cache[expr] = values
    return values


def evaluate(rules, closes):
    """Check every rule on the last bar of ``closes``.

    Returns one dict per rule, in order, with keys: ``line``, ``text``,
    ``fired`` (bool), ``reason`` (None, or "not enough data" when a needed
    value is missing), ``left`` and ``right`` (values on the last bar, or None),
    and ``prev_left`` and ``prev_right`` (values on the bar before, only
    looked up for the cross operators, else None).
    """
    cache = {}
    results = []
    n = len(closes)
    for rule in rules:
        op = rule["op"]
        lseries = _series(rule["left"], closes, cache)
        rseries = _series(rule["right"], closes, cache)
        is_cross = op.startswith("crosses")
        left = lseries[-1] if n >= 1 else None
        right = rseries[-1] if n >= 1 else None
        prev_left = lseries[-2] if is_cross and n >= 2 else None
        prev_right = rseries[-2] if is_cross and n >= 2 else None
        needed = [left, right] + ([prev_left, prev_right] if is_cross else [])
        fired = False
        reason = None
        if any(v is None for v in needed):
            reason = NOT_ENOUGH_DATA
        elif op == "<":
            fired = left < right
        elif op == "<=":
            fired = left <= right
        elif op == ">":
            fired = left > right
        elif op == ">=":
            fired = left >= right
        elif op == "crosses_above":
            fired = prev_left <= prev_right and left > right
        else:
            fired = prev_left >= prev_right and left < right
        results.append(
            {
                "line": rule["line"],
                "text": rule["text"],
                "fired": fired,
                "reason": reason,
                "left": left,
                "right": right,
                "prev_left": prev_left,
                "prev_right": prev_right,
            }
        )
    return results


def _fmt(value):
    return "n/a" if value is None else f"{value:.4f}"


def format_result(result):
    """One output line for a rule result."""
    status = "FIRED" if result["fired"] else "no"
    parts = [f"{status:<5s}  {result['text']}"]
    if result["reason"]:
        parts.append(f"({result['reason']})")
    else:
        detail = f"left={_fmt(result['left'])} right={_fmt(result['right'])}"
        if result["prev_left"] is not None:
            detail += f" prev_left={_fmt(result['prev_left'])} prev_right={_fmt(result['prev_right'])}"
        parts.append(f"({detail})")
    return "  ".join(parts)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.alerts",
        description="Check price and indicator alert rules against the last bar of a price file.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("rules_path", help="rules file, one rule per line")
    parser.add_argument("csv_path", help="CSV file with a 'close' column")
    parser.add_argument("--all", action="store_true", help="print every rule with its status, not only fired rules")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with open(args.rules_path, encoding="utf-8-sig") as f:
            rules = parse_rules(f.read())
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: cannot read {args.rules_path}: {getattr(exc, 'strerror', None) or exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {args.rules_path}: {exc}", file=sys.stderr)
        return 1
    if not rules:
        print(f"Error: {args.rules_path}: no rules found", file=sys.stderr)
        return 1

    try:
        _, closes = load_price_table(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not closes:
        print("No price rows found.", file=sys.stderr)
        return 1

    results = evaluate(rules, closes)
    fired = [r for r in results if r["fired"]]
    shown = results if args.all else fired
    print(f"Alerts: {len(fired)} of {len(results)} rules fired on the last of {len(closes)} bars (close {closes[-1]:.4f})")
    for r in shown:
        print(format_result(r))
    if not shown:
        print("No rules fired.")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
