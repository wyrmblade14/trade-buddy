"""The trailing stop (``trail_pct``) in the result, the report and the export.

8-bar series, cash 500, short=1, long=2 (see test_trailing_stop.py):

    bar  open  high   low  close
     0   10    10.5   9.5   10
     1    9.5   9.5   8.5    9
     2    8.5   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal
     4   10.8  11.5  10.5   11     BUY 45 @ 11, cash 5
     5   11.5  13    11.2   12
     6   11.0  12.5  10.2   10     trail 10 %: level 13 * 0.9 = 11.7 -> SELL 45 @ 11.70, cash 531.50
     7    9     9     7.5    8

The expected text in the "unchanged" tests below was captured from the code
before trail_pct was added to the result and the report.
"""

import io

from trading_assistant.backtest import (
    EXPORT_COLUMNS,
    export_columns,
    export_rows,
    format_result,
    run_backtest,
    write_export,
)

CLOSES = [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13.0, 12.5, 9.0]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 10.2, 7.5]
OPENS = [10.0, 9.5, 8.5, 8.8, 10.8, 11.5, 11.0, 9.0]
BASE = dict(initial_cash=500, short=1, long=2)
HL = dict(highs=HIGHS, lows=LOWS)
DATES = [f"d{i}" for i in range(8)]


def exits_line(result):
    (line,) = [l for l in format_result(result, 1, 2) if l.startswith("  Exits:")]
    return line


def export_text(result):
    f = io.StringIO()
    write_export(result, f, dates=DATES)
    return f.getvalue()


# --------------------------------------------------------------------------- result


def test_result_records_trail_pct():
    r = run_backtest(CLOSES, trail_pct=10, **HL, **BASE)
    assert r.trail_pct == 10.0 and isinstance(r.trail_pct, float)
    assert r.stop_pct is None and r.take_profit_pct is None
    assert r.has_exits


def test_result_without_trail_pct():
    r = run_backtest(CLOSES, **BASE)
    assert r.trail_pct is None and not r.has_exits
    assert run_backtest(CLOSES, stop_pct=10, **HL, **BASE).trail_pct is None


# --------------------------------------------------------------------------- report


def test_report_trail_alone():
    r = run_backtest(CLOSES, trail_pct=10, **HL, **BASE)
    lines = format_result(r, 1, 2)
    assert "  Exits:       trail 10.00% below the highest high since entry" in lines
    assert (
        "    #2   bar 6     SELL       45 @      11.70  value       526.50  cost     0.00  cash       531.50  trail"
        in lines
    )
    assert lines[4].endswith("  signal")  # the buy also shows its reason


def test_report_trail_with_stop():
    r = run_backtest(CLOSES, trail_pct=10, stop_pct=5, **HL, **BASE)
    assert exits_line(r) == (
        "  Exits:       stop 5.00% below entry, trail 10.00% below the highest high since entry"
        " (the higher of stop and trail is used)"
    )


def test_report_trail_with_target():
    r = run_backtest(CLOSES, trail_pct=10, take_profit_pct=20, **HL, **BASE)
    assert exits_line(r) == (
        "  Exits:       trail 10.00% below the highest high since entry, target 20.00% above entry"
        " (trail wins if a bar touches both)"
    )


def test_report_trail_with_stop_and_target():
    r = run_backtest(CLOSES, trail_pct=10, stop_pct=5, take_profit_pct=20, **HL, **BASE)
    assert exits_line(r) == (
        "  Exits:       stop 5.00% below entry, trail 10.00% below the highest high since entry,"
        " target 20.00% above entry"
        " (the higher of stop and trail is used; it wins if a bar also touches the target)"
    )


def test_report_trail_pct_two_decimals():
    r = run_backtest(CLOSES, trail_pct=7.5, **HL, **BASE)
    assert exits_line(r) == "  Exits:       trail 7.50% below the highest high since entry"


# --------------------------------------------------------------------------- export


def test_export_header_has_reason_for_trail_alone():
    r = run_backtest(CLOSES, trail_pct=10, **HL, **BASE)
    assert export_columns(r) == EXPORT_COLUMNS + ["reason"]
    rows = export_rows(r, DATES)
    assert all(len(row) == len(EXPORT_COLUMNS) + 1 for row in rows)
    assert [row[-1] for row in rows] == ["", "", "", "", "signal", "", "trail", ""]
    assert export_text(r).splitlines()[7] == (
        "6,d6,10.00,SELL,SELL,45,11.70,526.50,0.00,531.50,0,531.50,-2.48,500.00,trail"
    )


# --------------------------------------------------------------------------- unchanged without trail_pct

PLAIN_REPORT = [
    "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting",
    "  Start cash:  500.00",
    "  Trades:      2 (1 buy, 1 sell)",
    "  Fills (bar index is 0-based):",
    "    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash         5.00",
    "    #2   bar 7     SELL       45 @       8.00  value       360.00  cost     0.00  cash       365.00",
    "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)",
    "  Round trips: 1 completed, 0 made money (0%)",
    "  Comparison              Strategy    Buy & hold",
    "    End equity              365.00        400.00",
    "    Return                 -27.00%       -20.00%",
    "    Max drawdown           -33.03%       -33.33%",
    "    Trades                       2             1",
    "    Costs paid                0.00          0.00",
    "  End cash:    365.00",
    "  End shares:  0 @ 8.00",
    "  End equity:  365.00",
    "  Return:      -27.00%",
]

PLAIN_EXPORT = """\
bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity\r
0,d0,10.00,HOLD,,,,,,500.00,0,500.00,0.00,500.00\r
1,d1,9.00,HOLD,,,,,,500.00,0,500.00,0.00,450.00\r
2,d2,8.00,HOLD,,,,,,500.00,0,500.00,0.00,400.00\r
3,d3,9.00,BUY,,,,,,500.00,0,500.00,0.00,450.00\r
4,d4,11.00,HOLD,BUY,45,11.00,495.00,0.00,5.00,45,500.00,0.00,550.00\r
5,d5,12.00,HOLD,,,,,,5.00,45,545.00,0.00,600.00\r
6,d6,10.00,SELL,,,,,,5.00,45,455.00,-16.51,500.00\r
7,d7,8.00,HOLD,SELL,45,8.00,360.00,0.00,365.00,0,365.00,-33.03,400.00\r
"""

STOP_TARGET_EXITS_LINE = (
    "  Exits:       stop 10.00% below entry, target 15.00% above entry (stop wins if a bar touches both)"
)

STOP_TARGET_EXPORT = """\
bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\r
0,d0,10.00,HOLD,,,,,,500.00,0,500.00,0.00,500.00,\r
1,d1,9.00,HOLD,,,,,,500.00,0,500.00,0.00,450.00,\r
2,d2,8.00,HOLD,,,,,,500.00,0,500.00,0.00,400.00,\r
3,d3,9.00,BUY,,,,,,500.00,0,500.00,0.00,450.00,\r
4,d4,11.00,HOLD,BUY,45,11.00,495.00,0.00,5.00,45,500.00,0.00,550.00,signal\r
5,d5,12.00,HOLD,SELL,45,12.65,569.25,0.00,574.25,0,574.25,0.00,600.00,target\r
6,d6,10.00,SELL,,,,,,574.25,0,574.25,0.00,500.00,\r
7,d7,8.00,HOLD,,,,,,574.25,0,574.25,0.00,400.00,\r
"""


def test_no_trail_report_and_export_unchanged():
    for r in (
        run_backtest(CLOSES, **BASE),
        run_backtest(CLOSES, trail_pct=None, **BASE),
        run_backtest(CLOSES, trail_pct=None, opens=OPENS, **HL, **BASE),  # candles alone add no exits
    ):
        assert format_result(r, 1, 2) == PLAIN_REPORT
        assert export_text(r) == PLAIN_EXPORT
        assert export_columns(r) == EXPORT_COLUMNS


def test_no_trail_stop_and_target_report_and_export_unchanged():
    r = run_backtest(CLOSES, stop_pct=10, take_profit_pct=15, opens=OPENS, **HL, **BASE)
    assert exits_line(r) == STOP_TARGET_EXITS_LINE
    assert export_text(r) == STOP_TARGET_EXPORT
