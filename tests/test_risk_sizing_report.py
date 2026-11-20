"""Risk sizing on the result and in the report (risk_pct, atr_mult, atr_period, risk_skipped_buys)."""

import io

from trading_assistant.backtest import format_result, format_stats, run_backtest, write_export
from trading_assistant.signals import BUY

CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13, 12.5, 9]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 9.8, 7.5]
OPENS = [10, 9.2, 8.3, 8.8, 10.8, 12.2, 11.5, 8.6]

RISK_LINE_3 = (
    "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
    "(this only sets the number of shares; no stop is placed)"
)
SKIPPED_NOTE = "(risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)"

# Captured from backtest.py BEFORE risk sizing reached the result and the report.
OLD_PLAIN_REPORT = (
    "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
    "  Start cash:  1,000.00\n"
    "  Trades:      2 (1 buy, 1 sell)\n"
    "  Fills (bar index is 0-based):\n"
    "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n"
    "    #2   bar 7     SELL       90 @       8.00  value       720.00  cost     0.00  cash       730.00\n"
    "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
    "  Round trips: 1 completed, 0 made money (0%)\n"
    "  Comparison              Strategy    Buy & hold\n"
    "    End equity              730.00        800.00\n"
    "    Return                 -27.00%       -20.00%\n"
    "    Max drawdown           -33.03%       -33.33%\n"
    "    Trades                       2             1\n"
    "    Costs paid                0.00          0.00\n"
    "  End cash:    730.00\n"
    "  End shares:  0 @ 8.00\n"
    "  End equity:  730.00\n"
    "  Return:      -27.00%"
)
OLD_PLAIN_STATS = (
    "Risk and return\n"
    "  Total return:       -27.00%\n"
    "  CAGR:               -100.00%\n"
    "  Volatility (ann.):  163.76%\n"
    "  Sharpe ratio:       -6.00\n"
    "  Sortino ratio:      -6.36\n"
    "  Exposure:           37.50%\n"
    "  Profit factor:      0.00\n"
    "  Average win:        n/a\n"
    "  Average loss:       -270.00\n"
    "  Longest drawdown:   2 bars"
)
OLD_PLAIN_EXPORT = (
    "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity\r\n"
    "0,,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00\r\n"
    "1,,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00\r\n"
    "2,,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00\r\n"
    "3,,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00\r\n"
    "4,,11.00,HOLD,BUY,90,11.00,990.00,0.00,10.00,90,1000.00,0.00,1100.00\r\n"
    "5,,12.00,HOLD,,,,,,10.00,90,1090.00,0.00,1200.00\r\n"
    "6,,10.00,SELL,,,,,,10.00,90,910.00,-16.51,1000.00\r\n"
    "7,,8.00,HOLD,SELL,90,8.00,720.00,0.00,730.00,0,730.00,-33.03,800.00\r\n"
    ""
)
OLD_FULL_REPORT = (
    "Backtest: SMA 1/2 crossover, next-bar open fills, whole shares, no shorting\n"
    "  Start cash:  1,000.00\n"
    "  Trades:      2 (1 buy, 1 sell)\n"
    "  Fills (bar index is 0-based):\n"
    "    #1   bar 4     BUY        45 @      10.85  value       488.43  cost     1.49  cash       510.08  signal\n"
    "    #2   bar 6     SELL       45 @      11.44  value       514.91  cost     1.51  cash     1,023.48  trail\n"
    "  Costs:       3.00 paid (fee 1.00 per trade + 0.10% of value)\n"
    "  Slippage:    0.50% (buys fill higher, sells lower, before fees)\n"
    "  Sizing:      each buy at most 50% of account value (costs and slippage included)\n"
    "  Exits:       stop 5.00% below entry, trail 8.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)\n"
    "  Round trips: 1 completed, 1 made money (100%)\n"
    "  Comparison              Strategy    Buy & hold\n"
    "    End equity            1,023.48        795.06\n"
    "    Return                  +2.35%       -20.49%\n"
    "    Max drawdown            -2.53%       -33.25%\n"
    "    Trades                       2             1\n"
    "    Costs paid                3.00          1.99\n"
    "  End cash:    1,023.48\n"
    "  End shares:  0 @ 8.00\n"
    "  End equity:  1,023.48\n"
    "  Return:      +2.35%"
)
OLD_FULL_EXPORT = (
    "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\r\n"
    "0,d0,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,993.06,\r\n"
    "1,d1,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,894.06,\r\n"
    "2,d2,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,795.06,\r\n"
    "3,d3,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,894.06,\r\n"
    "4,d4,11.00,HOLD,BUY,45,10.85,488.43,1.49,510.08,45,1005.08,0.00,1092.06,signal\r\n"
    "5,d5,12.00,HOLD,,,,,,510.08,45,1050.08,0.00,1191.06,\r\n"
    "6,d6,10.00,SELL,SELL,45,11.44,514.91,1.51,1023.48,0,1023.48,-2.53,993.06,trail\r\n"
    "7,d7,8.00,HOLD,,,,,,1023.48,0,1023.48,-2.53,795.06,\r\n"
    ""
)


def run(**kwargs):
    base = dict(initial_cash=1000, short=1, long=2, highs=HIGHS, lows=LOWS)
    base.update(kwargs)
    return run_backtest(CLOSES, **base)


def report(result):
    return "\n".join(format_result(result, 1, 2))


def export(result, dates=None):
    buf = io.StringIO()
    write_export(result, buf, dates)
    return buf.getvalue()


# --- hand case: cash 1000, risk 2, atr_mult 2, atr_period 3 -----------------
# BUY signal on bar 3, ATR(3) there = 25/18; stop 2 * 25/18 = 2.7778;
# 20 / 2.7778 = 7.2 -> 7 shares, bought bar 4 @ 11, sold bar 7 @ 8.


def test_hand_case_result_fields():
    result = run(risk_pct=2, atr_mult=2, atr_period=3)
    assert result.risk_pct == 2.0
    assert result.atr_mult == 2.0
    assert result.atr_period == 3
    assert result.risk_skipped_buys == 0
    assert [t.shares for t in result.trades] == [7, 7]


def test_hand_case_report():
    lines = format_result(run(risk_pct=2, atr_mult=2, atr_period=3), 1, 2)
    assert lines == [
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting",
        "  Start cash:  1,000.00",
        "  Trades:      2 (1 buy, 1 sell)",
        "  Fills (bar index is 0-based):",
        "    #1   bar 4     BUY         7 @      11.00  value        77.00  cost     0.00  cash       923.00",
        "    #2   bar 7     SELL        7 @       8.00  value        56.00  cost     0.00  cash       979.00",
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)",
        RISK_LINE_3,
        "  Round trips: 1 completed, 0 made money (0%)",
        "  Comparison              Strategy    Buy & hold",
        "    End equity              979.00        800.00",
        "    Return                  -2.10%       -20.00%",
        "    Max drawdown            -2.78%       -33.33%",
        "    Trades                       2             1",
        "    Costs paid                0.00          0.00",
        "  End cash:    979.00",
        "  End shares:  0 @ 8.00",
        "  End equity:  979.00",
        "  Return:      -2.10%",
    ]


def test_risk_line_does_not_claim_a_loss_limit():
    # The hand case itself loses 2.10%, more than the 2% "at risk": nothing may promise a cap.
    text = report(run(risk_pct=2, atr_mult=2, atr_period=3)).lower()
    assert "no stop is placed" in text
    assert "only sets the number of shares" in text
    for phrase in ("limit", "capped", "max loss", "maximum loss", "at most 2", "cannot lose"):
        assert phrase not in text


def test_risk_line_sits_after_position_size_line():
    lines = format_result(run(risk_pct=2, atr_mult=2, atr_period=3, position_size=0.5), 1, 2)
    i = lines.index("  Sizing:      each buy at most 50% of account value (costs and slippage included)")
    assert lines[i + 1] == RISK_LINE_3


# --- period 5 case: BUY signal on bar 3, first ATR(5) on bar 4 -> 1 skipped -----


def test_period_5_case_skips_one_buy():
    result = run(risk_pct=2, atr_mult=2, atr_period=5)
    assert result.daily[3].signal == BUY
    assert result.trades == []
    assert result.final_cash == 1000
    assert result.risk_skipped_buys == 1
    assert (result.risk_pct, result.atr_mult, result.atr_period) == (2.0, 2.0, 5)


def test_period_5_case_report_has_one_skipped_note():
    lines = format_result(run(risk_pct=2, atr_mult=2, atr_period=5), 1, 2)
    i = lines.index(
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(5) "
        "(this only sets the number of shares; no stop is placed)"
    )
    assert lines[i + 1] == "  Skipped:     1 buy " + SKIPPED_NOTE
    assert sum(line.startswith("  Skipped:") for line in lines) == 1


def test_no_skipped_note_when_nothing_skipped():
    assert "Skipped:" not in report(run(risk_pct=2, atr_mult=2, atr_period=3))


def test_skipped_note_plural_and_risk_under_one_share_counts():
    # Two more bars give a second BUY signal on bar 8. With 0.1% risk (1.00) and
    # ATR(3) well above 0.5 on both signal bars, each buy is under 1 share.
    result = run_backtest(
        CLOSES + [9, 11], 1000, short=1, long=2, highs=HIGHS + [9.5, 11.5], lows=LOWS + [8, 10.5],
        risk_pct=0.1, atr_mult=2, atr_period=3,
    )
    assert [d.signal for d in result.daily].count(BUY) == 2
    assert result.trades == []
    assert result.risk_skipped_buys == 2
    assert "  Skipped:     2 buys " + SKIPPED_NOTE in format_result(result, 1, 2)


def test_buy_skipped_only_for_cash_is_not_counted():
    # A 1000 fee leaves no cash for a single share; the risk rule alone would buy 7.
    result = run(risk_pct=2, atr_mult=2, atr_period=3, fee=1000)
    assert result.trades == []
    assert result.risk_skipped_buys == 0
    assert "Skipped:" not in report(result)


def test_buy_skipped_only_for_position_size_is_not_counted():
    # position_size 0.005 -> at most 5.00 to spend, under one share @ 11.
    result = run(risk_pct=2, atr_mult=2, atr_period=3, position_size=0.005)
    assert result.trades == []
    assert result.risk_skipped_buys == 0


def test_zero_atr_on_signal_bar_is_skipped_and_counted():
    # atr_period 1: the ATR is that bar's true range. Bar 3 is flat (high = low =
    # close = previous close = 9), so its ATR is 0, and SMA 1/3 gives BUY there.
    # This used to raise ZeroDivisionError.
    closes = [12, 8, 9, 9, 10]
    result = run_backtest(closes, 1000, short=1, long=3, highs=closes, lows=closes, risk_pct=2, atr_period=1)
    assert result.daily[3].signal == BUY
    assert result.trades == []
    assert result.risk_skipped_buys == 1
    assert "  Skipped:     1 buy " + SKIPPED_NOTE in format_result(result, 1, 3)


def test_tiny_stop_distance_does_not_overflow():
    # 2 * 1e-320 * ATR is a tiny subnormal; 20 / it is inf. This used to raise
    # OverflowError. The buy is simply capped by the cash: 90 shares, not skipped.
    result = run(risk_pct=2, atr_mult=1e-320, atr_period=3)
    assert result.trades[0].shares == 90
    assert result.risk_skipped_buys == 0


# --- without risk_pct: exactly as before ------------------------------------


def test_without_risk_pct_new_fields_are_off():
    result = run()
    assert result.risk_pct is None
    assert result.atr_mult is None
    assert result.atr_period is None
    assert result.risk_skipped_buys == 0


def test_without_risk_pct_atr_settings_are_not_recorded():
    result = run(atr_mult=3, atr_period=5)
    assert (result.risk_pct, result.atr_mult, result.atr_period, result.risk_skipped_buys) == (None, None, None, 0)


def test_without_risk_pct_report_stats_export_exactly_as_before():
    result = run()
    assert report(result) == OLD_PLAIN_REPORT
    assert "\n".join(format_stats(result)) == OLD_PLAIN_STATS
    assert export(result) == OLD_PLAIN_EXPORT


def test_without_risk_pct_full_settings_report_and_export_exactly_as_before():
    # Every other optional report line in use: costs, slippage, sizing, all exits, open fills.
    result = run(
        fee=1, fee_pct=0.1, slippage_pct=0.5, position_size=0.5, stop_pct=5,
        take_profit_pct=20, trail_pct=8, opens=OPENS, fill="open",
    )
    assert report(result) == OLD_FULL_REPORT
    assert export(result, [f"d{i}" for i in range(8)]) == OLD_FULL_EXPORT


def test_export_is_unchanged_by_risk_sizing_columns():
    # Risk sizing adds no export columns; only the trades it causes differ.
    with_risk = export(run(risk_pct=2, atr_mult=2, atr_period=3))
    assert with_risk.splitlines()[0] == OLD_PLAIN_EXPORT.splitlines()[0]
