"""Drawdown halt in the engine and the text report (``run_backtest(..., max_drawdown_limit_pct=PCT)``).

Every number is worked out by hand in the comments.
"""

import pytest

from trading_assistant.backtest import export_columns, format_result, run_backtest

# The 11-bar closes.csv of docs/cli.md. SMA 1/2, cash 1000, no option:
# BUY 90 @ 11 on bar 4 (cash 10), SELL 90 @ 10 on bar 7, BUY 75 @ 12 on bar 9, end 10 + 75 x 12.2 = 925.
# Account value at the closes: 1000 x 4, 1000, 1090 (bar 5, the peak), 910 (bar 6), 910, 910, 910, 925.
# Bar 6 is (910 - 1090) / 1090 = 16.51 % below the peak, the deepest fall of the run.
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]

# SMA 1/3, cash 1000. Signals (close against the mean of the last 3 closes, crossing):
# bar 4: 11 > (10 + 10 + 11) / 3 = 10.33 after 10 <= 10 -> BUY; bars 5-8 HOLD
# (20 > 13.67, 32 > 21, 28 > 26.67, 30 = 30 is not below); bar 9: 25 < 27.67 -> SELL;
# bar 10: 35 > 30 after 25 <= 27.67 -> BUY.
# Bar 5 buys 1000 / 20 = 50 shares, cash 0. Account value 50 x close:
# bar 5 1000, bar 6 1600 (peak), bar 7 1400, bar 8 1500, bar 9 1250.
# Bar 7: (1400 - 1600) / 1600 = -12.5 % exactly; bar 9: (1250 - 1600) / 1600 = -21.875 %.
RALLY = [10, 10, 10, 10, 11, 20, 32, 28, 30, 25, 35, 36]


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.reason) for t in result.trades]


def drawdown_line(result, short, long):
    return [line for line in format_result(result, short, long) if line.startswith("  Drawdown:")]


def test_16_percent_halts_on_bar_6_and_the_signal_sell_keeps_its_label():
    result = run_backtest(CLOSES, initial_cash=1000, short=1, long=2, max_drawdown_limit_pct=16)
    # Bar 6 closes 16.51 % below the peak: halt. Bar 7's sale is the signal's (SELL on bar 6), so it stays "signal".
    # The BUY from bar 8 is due on bar 9, after the halt: skipped. Cash 910 to the end.
    assert result.drawdown_halt_bar == 6
    assert fills(result) == [(4, "BUY", 90, 11, "signal"), (7, "SELL", 90, 10, "signal")]
    assert result.drawdown_skipped_buys == 1
    assert result.cooldown_skipped_buys == 0 and result.risk_skipped_buys == 0
    assert result.final_equity == pytest.approx(910.0)
    lines = format_result(result, 1, 2)
    assert "  Trades:      2 (1 buy, 1 sell)" in lines
    assert "  End equity:  910.00" in lines
    assert drawdown_line(result, 1, 2) == [
        "  Drawdown:    halt at 16.00% below the peak account value at a close; "
        "triggered at bar 6, no buy fills after it; 1 buy skipped"
    ]


def test_17_percent_never_halts_and_trades_as_without_it():
    plain = run_backtest(CLOSES, initial_cash=1000, short=1, long=2)
    result = run_backtest(CLOSES, initial_cash=1000, short=1, long=2, max_drawdown_limit_pct=17)
    # The deepest fall is 16.51 %, under 17 %.
    assert result.drawdown_halt_bar is None
    assert result.daily == plain.daily
    assert result.final_equity == pytest.approx(925.0)
    assert drawdown_line(result, 1, 2) == [
        "  Drawdown:    halt at 17.00% below the peak account value at a close; not triggered; 0 buys skipped"
    ]


def test_without_the_option_the_result_and_report_are_as_before():
    result = run_backtest(CLOSES, initial_cash=1000, short=1, long=2)
    assert (result.max_drawdown_limit_pct, result.drawdown_halt_bar, result.drawdown_skipped_buys) == (None, None, 0)
    assert not result.has_exits
    assert "reason" not in export_columns(result)
    # The report as the code printed it before the option existed, line for line.
    assert format_result(result, 1, 2) == [
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting",
        "  Start cash:  1,000.00",
        "  Trades:      3 (2 buy, 1 sell)",
        "  Fills (bar index is 0-based):",
        "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00",
        "    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00",
        "    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00",
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)",
        "  Round trips: 1 completed, 0 made money (0%)",
        "  Comparison              Strategy    Buy & hold",
        "    End equity              925.00      1,220.00",
        "    Return                  -7.50%       +22.00%",
        "    Max drawdown           -16.51%       -20.00%",
        "    Trades                       3             1",
        "    Costs paid                0.00          0.00",
        "  End cash:    10.00",
        "  End shares:  75 @ 12.20",
        "  End equity:  925.00",
        "  Return:      -7.50%",
    ]


def test_the_drawdown_sells_the_position_itself():
    result = run_backtest(RALLY, initial_cash=1000, short=1, long=3, max_drawdown_limit_pct=12.5)
    # Bar 7 is exactly 12.5 % below the peak: "or more", so it halts. Bar 8 has no other fill (its pending
    # signal is HOLD), so the drawdown sells the 50 shares at bar 8's close: 50 x 30 = 1500.
    # The BUY from bar 10 is due on bar 11: skipped. End 1500.
    assert result.drawdown_halt_bar == 7
    assert fills(result) == [(5, "BUY", 50, 20, "signal"), (8, "SELL", 50, 30, "drawdown")]
    assert result.drawdown_skipped_buys == 1
    assert result.final_equity == pytest.approx(1500.0)
    lines = format_result(result, 1, 3)
    assert "    #2   bar 8     SELL       50 @      30.00  value     1,500.00  cost     0.00  cash     1,500.00  drawdown" in lines
    assert "  Round trips: 1 completed, 1 made money (100%)" in lines  # 1500 - 1000 = +500

    # Just above 12.5 %: bar 7 does not halt, bar 9 (-21.875 %) does. Its SELL signal sells on bar 10 at 35
    # ("signal"), and the BUY from bar 10, due on bar 11, is skipped. End 50 x 35 = 1750.
    later = run_backtest(RALLY, initial_cash=1000, short=1, long=3, max_drawdown_limit_pct=12.6)
    assert later.drawdown_halt_bar == 9
    assert fills(later) == [(5, "BUY", 50, 20, "signal"), (10, "SELL", 50, 35, "signal")]
    assert later.drawdown_skipped_buys == 1
    assert later.final_equity == pytest.approx(1750.0)


def test_a_stop_on_the_bar_goes_first_with_close_fills_and_the_drawdown_sells_at_the_open_with_open_fills():
    # Candles equal to the closes except bar 8: open 29, low 17. A 10 % stop is at 20 x 0.9 = 18.
    opens = list(RALLY)
    opens[8] = 29
    lows = list(RALLY)
    lows[8] = 17
    candles = dict(opens=opens, highs=list(RALLY), lows=lows, stop_pct=10, max_drawdown_limit_pct=12.5)
    # Halt at bar 7 either way (the account is marked at the closes).
    # Close fills: bar 8's low 17 reaches the stop during the bar, before the close: 50 x 18 = 900, "stop".
    close = run_backtest(RALLY, initial_cash=1000, short=1, long=3, **candles)
    assert close.drawdown_halt_bar == 7
    assert fills(close)[-1] == (8, "SELL", 50, 18, "stop")
    assert close.final_equity == pytest.approx(900.0)
    # Open fills: bar 5 buys 50 at its open 20. On bar 8 the open (29) is above the stop, so the drawdown
    # sells at the open first: 50 x 29 = 1450, "drawdown". The low reached later does not matter.
    opened = run_backtest(RALLY, initial_cash=1000, short=1, long=3, fill="open", **candles)
    assert opened.drawdown_halt_bar == 7
    assert fills(opened) == [(5, "BUY", 50, 20, "signal"), (8, "SELL", 50, 29, "drawdown")]
    assert opened.drawdown_skipped_buys == 1
    assert opened.final_equity == pytest.approx(1450.0)


def test_the_drawdown_sale_starts_no_cooldown_and_a_halted_buy_is_counted_once():
    # Drawdown sale on bar 8 with a 3-bar cooldown set (the 50 % stop, at 10, is never reached).
    # The skipped BUY due on bar 11 counts as a drawdown skip only.
    result = run_backtest(RALLY, initial_cash=1000, short=1, long=3, stop_pct=50, highs=list(RALLY),
                          lows=list(RALLY), cooldown=3, max_drawdown_limit_pct=12.5)
    assert fills(result)[-1] == (8, "SELL", 50, 30, "drawdown")
    assert (result.drawdown_skipped_buys, result.cooldown_skipped_buys) == (1, 0)
    assert "  Cooldown:    3 bars after a stop, trail or atr exit; 0 buys skipped" in format_result(result, 1, 3)

    # A stop that does start a cooldown: bar 8's low 17 sells at 18, cash 900, so the close is
    # (900 - 1600) / 1600 = 43.75 % below the peak and a 40 % halt triggers on bar 8 (bar 7 was only 12.5 %).
    # The cooldown blocks bars 9-13 and the halt bars 9 on: the bar 11 BUY is in both, counted as drawdown only.
    lows = list(RALLY)
    lows[8] = 17
    settings = dict(initial_cash=1000, short=1, long=3, stop_pct=10, highs=list(RALLY), lows=lows, cooldown=5)
    alone = run_backtest(RALLY, **settings)
    assert alone.cooldown_skipped_buys == 1  # without the halt the buy is a cooldown skip
    both = run_backtest(RALLY, max_drawdown_limit_pct=40, **settings)
    assert both.drawdown_halt_bar == 8
    assert (both.drawdown_skipped_buys, both.cooldown_skipped_buys) == (1, 0)


def test_a_drawdown_sale_the_fees_refuse_is_tried_again_on_the_next_bar():
    # Fee 100 per trade. Bar 5 buys (1000 - 100) / 20 = 45 shares: 900 + 100 fee, cash 0, value 900.
    # Bar 6 closes at 2: 45 x 2 = 90, 91 % below the 1000 peak: halt (limit 50). Its SELL signal and the
    # drawdown sale on bar 7 both need 45 x 2 - 100 = -10: refused. Bar 8 (pending HOLD) sells 45 x 3 = 135,
    # less the 100 fee: cash 35.
    result = run_backtest([10, 10, 10, 10, 11, 20, 2, 2, 3], initial_cash=1000, short=1, long=3, fee=100,
                          max_drawdown_limit_pct=50)
    assert result.drawdown_halt_bar == 6
    assert fills(result) == [(5, "BUY", 45, 20, "signal"), (8, "SELL", 45, 3, "drawdown")]
    assert result.final_cash == pytest.approx(35.0)


@pytest.mark.parametrize("bad", [0, -1, 100, 150])
def test_the_limit_must_be_above_0_and_below_100(bad):
    with pytest.raises(ValueError, match="max_drawdown_limit_pct must be between 0 and 100"):
        run_backtest(CLOSES, short=1, long=2, max_drawdown_limit_pct=bad)


def test_decimal_limits_near_the_ends_are_accepted():
    for pct in (0.01, 99.99):
        assert run_backtest(CLOSES, short=1, long=2, max_drawdown_limit_pct=pct).max_drawdown_limit_pct == pct
