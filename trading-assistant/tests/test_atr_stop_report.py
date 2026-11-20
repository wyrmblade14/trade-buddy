"""The ATR stop (``atr_stop``) on the result, in the report and in the export.

Same hand case as test_atr_stop.py (2026-01-01 to 2026-01-08, cash 1000, SMA 1/2,
atr_mult 2, atr_period 3): BUY 90 @ 11 on bar 4, level 11 - 2 * 25/18 = 8.2222,
bar 7 low 7.5 -> SELL 90 @ 8.2222 = 740, cash 750, reason atr.
With risk_pct 2: 7 shares @ 11, sold @ 8.2222 on bar 7, cash 980.56.
"""

import io

from trading_assistant.backtest import (
    EXPORT_COLUMNS,
    export_columns,
    format_result,
    run_backtest,
    write_export,
)

DATES = [f"2026-01-0{i}" for i in range(1, 9)]
OPENS = [10, 9.2, 8.3, 8.8, 10.8, 12.2, 11.5, 8.6]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13, 12.5, 9]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 9.8, 7.5]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]

ATR_PART = "atr 2 x ATR(3) below entry"


def run(**kwargs):
    base = dict(initial_cash=1000, short=1, long=2, highs=HIGHS, lows=LOWS)
    base.update(kwargs)
    return run_backtest(CLOSES, **base)


def exits_line(result):
    (line,) = [l for l in format_result(result, 1, 2) if l.startswith("  Exits:")]
    return line


def export_text(result):
    buf = io.StringIO()
    write_export(result, buf, DATES)
    return buf.getvalue()


# --------------------------------------------------------------------------- result fields


def test_result_records_the_atr_stop_and_its_settings():
    r = run(atr_stop=True, atr_mult=2, atr_period=3)
    assert r.atr_stop is True and r.has_exits
    assert (r.atr_mult, r.atr_period) == (2.0, 3) and isinstance(r.atr_mult, float)
    assert r.risk_pct is None and r.risk_skipped_buys == 0
    assert r.stop_pct is None and r.trail_pct is None and r.take_profit_pct is None


def test_result_without_the_atr_stop():
    r = run(atr_mult=2, atr_period=3)
    assert r.atr_stop is False and not r.has_exits
    assert (r.atr_mult, r.atr_period) == (None, None)


def test_result_with_both_records_the_shared_settings():
    r = run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=3)
    assert (r.risk_pct, r.atr_stop, r.atr_mult, r.atr_period) == (2.0, True, 2.0, 3)


def test_skipped_buys_are_counted_on_the_result():
    assert run(atr_stop=True, atr_mult=2, atr_period=5).risk_skipped_buys == 1


# --------------------------------------------------------------------------- report


def test_hand_case_report():
    assert format_result(run(atr_stop=True, atr_mult=2, atr_period=3), 1, 2) == [
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting",
        "  Start cash:  1,000.00",
        "  Trades:      2 (1 buy, 1 sell)",
        "  Fills (bar index is 0-based):",
        "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal",
        "    #2   bar 7     SELL       90 @       8.22  value       740.00  cost     0.00  cash       750.00  atr",
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)",
        "  Exits:       atr 2 x ATR(3) below entry",
        "  Round trips: 1 completed, 0 made money (0%)",
        "  Comparison              Strategy    Buy & hold",
        "    End equity              750.00        800.00",
        "    Return                 -25.00%       -20.00%",
        "    Max drawdown           -31.19%       -33.33%",
        "    Trades                       2             1",
        "    Costs paid                0.00          0.00",
        "  End cash:    750.00",
        "  End shares:  0 @ 8.00",
        "  End equity:  750.00",
        "  Return:      -25.00%",
    ]


def test_hand_case_report_with_risk_pct():
    assert format_result(run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=3), 1, 2) == [
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting",
        "  Start cash:  1,000.00",
        "  Trades:      2 (1 buy, 1 sell)",
        "  Fills (bar index is 0-based):",
        "    #1   bar 4     BUY         7 @      11.00  value        77.00  cost     0.00  cash       923.00  signal",
        "    #2   bar 7     SELL        7 @       8.22  value        57.56  cost     0.00  cash       980.56  atr",
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)",
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
        "(the ATR stop sells at this distance, as of the buy that opened the position, below the average entry price; a gap, slippage, fees or a later buy can lose more)",
        "  Exits:       atr 2 x ATR(3) below entry",
        "  Round trips: 1 completed, 0 made money (0%)",
        "  Comparison              Strategy    Buy & hold",
        "    End equity              980.56        800.00",
        "    Return                  -1.94%       -20.00%",
        "    Max drawdown            -2.63%       -33.33%",
        "    Trades                       2             1",
        "    Costs paid                0.00          0.00",
        "  End cash:    980.56",
        "  End shares:  0 @ 8.00",
        "  End equity:  980.56",
        "  Return:      -1.94%",
    ]


def test_risk_line_with_the_atr_stop_does_not_say_no_stop_is_placed():
    text = "\n".join(format_result(run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=3), 1, 2)).lower()
    assert "no stop is placed" not in text and "only sets the number of shares" not in text
    for phrase in ("limit", "capped", "max loss", "maximum loss", "at most 2", "cannot lose"):
        assert phrase not in text


def test_risk_line_without_the_atr_stop_is_unchanged():
    lines = format_result(run(risk_pct=2, atr_mult=2, atr_period=3), 1, 2)
    assert (
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
        "(this only sets the number of shares; no stop is placed)"
    ) in lines
    assert not any(line.startswith("  Exits:") for line in lines)


def test_atr_multiplier_uses_g_format():
    assert exits_line(run(atr_stop=True, atr_mult=1.5, atr_period=3)) == "  Exits:       atr 1.5 x ATR(3) below entry"


def test_exits_line_next_to_the_other_exits():
    cases = [
        (dict(stop_pct=5),
         f"stop 5.00% below entry, {ATR_PART} (the higher of stop and atr is used, stop on a tie)"),
        (dict(trail_pct=10),
         f"trail 10.00% below the highest high since entry, {ATR_PART} (the higher of trail and atr is used, trail on a tie)"),
        (dict(take_profit_pct=20),
         f"{ATR_PART}, target 20.00% above entry (atr wins if a bar touches both)"),
        (dict(stop_pct=5, trail_pct=10),
         f"stop 5.00% below entry, trail 10.00% below the highest high since entry, {ATR_PART}"
         " (the highest of stop, trail and atr is used, in that order on a tie)"),
        (dict(stop_pct=5, take_profit_pct=20),
         f"stop 5.00% below entry, {ATR_PART}, target 20.00% above entry"
         " (the higher of stop and atr is used, stop on a tie; it wins if a bar also touches the target)"),
        (dict(trail_pct=10, take_profit_pct=20),
         f"trail 10.00% below the highest high since entry, {ATR_PART}, target 20.00% above entry"
         " (the higher of trail and atr is used, trail on a tie; it wins if a bar also touches the target)"),
        (dict(stop_pct=5, trail_pct=10, take_profit_pct=20),
         f"stop 5.00% below entry, trail 10.00% below the highest high since entry, {ATR_PART}, target 20.00% above entry"
         " (the highest of stop, trail and atr is used, in that order on a tie; it wins if a bar also touches the target)"),
    ]
    for kwargs, expected in cases:
        assert exits_line(run(atr_stop=True, atr_mult=2, atr_period=3, **kwargs)) == "  Exits:       " + expected


def test_skipped_line_for_the_atr_stop_alone():
    lines = format_result(run(atr_stop=True, atr_mult=2, atr_period=5), 1, 2)
    i = lines.index("  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)")
    assert lines[i + 1 : i + 3] == [
        "  Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)",
        "  Exits:       atr 2 x ATR(5) below entry",
    ]


def test_skipped_line_plural():
    # A second BUY signal on bar 8, both before any usable ATR(9).
    r = run_backtest(
        CLOSES + [9, 11], 1000, short=1, long=2, highs=HIGHS + [9.5, 11.5], lows=LOWS + [8, 10.5],
        atr_stop=True, atr_period=10,
    )
    assert r.risk_skipped_buys == 2
    assert "  Skipped:     2 buys (ATR stop: no usable ATR on the signal bar)" in format_result(r, 1, 2)


def test_with_risk_pct_one_skipped_line_in_the_risk_wording():
    lines = format_result(run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=5), 1, 2)
    skipped = [line for line in lines if line.startswith("  Skipped:")]
    assert skipped == [
        "  Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)"
    ]


def test_no_skipped_line_when_nothing_skipped():
    assert not any("Skipped" in line for line in format_result(run(atr_stop=True, atr_period=3), 1, 2))


# --------------------------------------------------------------------------- export


def test_export_has_the_reason_column_with_atr():
    r = run(atr_stop=True, atr_mult=2, atr_period=3)
    assert export_columns(r) == EXPORT_COLUMNS + ["reason"]
    assert export_text(r) == (
        "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\r\n"
        "0,2026-01-01,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00,\r\n"
        "1,2026-01-02,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00,\r\n"
        "2,2026-01-03,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00,\r\n"
        "3,2026-01-04,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00,\r\n"
        "4,2026-01-05,11.00,HOLD,BUY,90,11.00,990.00,0.00,10.00,90,1000.00,0.00,1100.00,signal\r\n"
        "5,2026-01-06,12.00,HOLD,,,,,,10.00,90,1090.00,0.00,1200.00,\r\n"
        "6,2026-01-07,10.00,SELL,,,,,,10.00,90,910.00,-16.51,1000.00,\r\n"
        "7,2026-01-08,8.00,HOLD,SELL,90,8.22,740.00,0.00,750.00,0,750.00,-31.19,800.00,atr\r\n"
    )


def test_without_the_atr_stop_report_and_export_are_the_same():
    for kwargs in (dict(), dict(opens=OPENS, stop_pct=5, trail_pct=8, take_profit_pct=20), dict(risk_pct=2, atr_period=3)):
        plain, off = run(**kwargs), run(atr_stop=False, **kwargs)
        assert format_result(off, 1, 2) == format_result(plain, 1, 2)
        assert export_text(off) == export_text(plain)
