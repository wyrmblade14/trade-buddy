"""Tests for trading_assistant.portfolio.format_portfolio.

The expected text is written out by hand; the disclaimer is taken from
cli.DISCLAIMER rather than retyped.
"""

from trading_assistant.cli import DISCLAIMER
from trading_assistant.portfolio import format_portfolio, run_portfolio, summarize

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
A_CLOSES = [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0]
B_CLOSES = [20.0, 20.0, 19.0, 21.0, 22.0, 20.0, 18.0, 17.0]

# Figures of the 8-bar example, worked out in test_portfolio_summary.py:
# return -22.3 %, drawdown -224/1001 = -22.377 %, buy & hold -17.5 %,
# A -27 % (B&H -20 %), B -17.6 % (B&H -15 %), worst drawdown A -33.03 %.
TITLE = "Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.00 + 0.00%, on the dates every file shares"
HEADER = "Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold"
NOTE = "Note: dates not shared by every file were dropped (see Bars lost); nothing was filled in."


def _text(tables, **kwargs):
    return format_portfolio(summarize(run_portfolio(tables, cash=1000, short=1, long=2, **kwargs)))


def test_8_bar_example():
    text = _text({"A": (DATES, A_CLOSES), "B": (DATES, B_CLOSES)})
    assert text.split("\n") == [
        TITLE,
        "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
        "Cash: 1,000.00  Final equity: 777.00",
        "Return: -22.30%  Max drawdown: -22.38%  Buy & hold (equal weight): -17.50%",
        HEADER,
        "A               8          0  -27.00%       2   -20.00%",
        "B               8          0  -17.60%       2   -15.00%",
        "Worst single-symbol drawdown: -33.03% (A)",
        DISCLAIMER,
    ]
    assert NOTE not in text  # nothing was lost, so no note
    assert not text.endswith("\n")


def test_note_shows_when_bars_were_lost():
    # B has two dates A lacks; they are dropped, every figure stays the same,
    # B's row shows 2 bars lost and the note appears.
    tables = {
        "A": (DATES, A_CLOSES),
        "B": (["2025-12-31"] + DATES + ["2026-01-14"], [99.0] + B_CLOSES + [99.0]),
    }
    assert _text(tables).split("\n") == [
        TITLE,
        "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
        "Cash: 1,000.00  Final equity: 777.00",
        "Return: -22.30%  Max drawdown: -22.38%  Buy & hold (equal weight): -17.50%",
        HEADER,
        "A               8          0  -27.00%       2   -20.00%",
        "B               8          2  -17.60%       2   -15.00%",
        "Worst single-symbol drawdown: -33.03% (A)",
        NOTE,
        DISCLAIMER,
    ]


def test_tiny_negative_values_show_as_plus_zero():
    # Fixed fee 0.01, 500 each, short 1, long 2.
    # A: 10 9 8 9 9 9 9 9 -> BUY on bar 3, filled bar 4 @ 9:
    #    (500 - 0.01) / 9 -> 55 shares, cash 500 - 495 - 0.01 = 4.99,
    #    equity 499.99 to the end (9 = 9 is no cross) -> -0.002 %, 1 trade.
    #    Buy & hold: 49 @ 10 (50 would need 500.01), cash 9.99,
    #    final 9.99 + 49 * 9 = 450.99 -> -9.802 %.
    # B: 20 every bar -> never crosses, 0 trades, +0 %.
    #    Buy & hold: 24 @ 20 (25 would need 500.01), cash 19.99,
    #    final 19.99 + 480 = 499.99 -> -0.002 %.
    # Portfolio: 999.99 -> -0.001 %; drawdown 1000 -> 999.99 = -0.001 %;
    # buy & hold 450.99 + 499.99 = 950.98 -> -4.902 %; worst drawdown A -0.002 %.
    tables = {
        "A": (DATES, [10.0, 9.0, 8.0, 9.0, 9.0, 9.0, 9.0, 9.0]),
        "B": (DATES, [20.0] * 8),
    }
    text = _text(tables, fee=0.01)
    assert text.split("\n") == [
        "Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.01 + 0.00%, on the dates every file shares",
        "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
        "Cash: 1,000.00  Final equity: 999.99",
        "Return: +0.00%  Max drawdown: +0.00%  Buy & hold (equal weight): -4.90%",
        "Symbol  Bars used  Bars lost  Return  Trades  Buy&Hold",
        "A               8          0  +0.00%       1    -9.80%",
        "B               8          0  +0.00%       0    +0.00%",
        "Worst single-symbol drawdown: +0.00% (A)",
        DISCLAIMER,
    ]
    assert "-0.00" not in text


def test_symbol_column_is_as_wide_as_the_longest_name():
    # 21-character name: the symbol column is 21 wide, then the usual 2 spaces.
    name = "VERY_LONG_SYMBOL_NAME"
    text = _text({name: (DATES, A_CLOSES), "B": (DATES, B_CLOSES)})
    lines = text.split("\n")
    assert lines[4:8] == [
        "Symbol                 Bars used  Bars lost   Return  Trades  Buy&Hold",
        "VERY_LONG_SYMBOL_NAME          8          0  -27.00%       2   -20.00%",
        "B                              8          0  -17.60%       2   -15.00%",
        "Worst single-symbol drawdown: -33.03% (VERY_LONG_SYMBOL_NAME)",
    ]
    assert len(lines[4]) == len(lines[5]) == len(lines[6])
