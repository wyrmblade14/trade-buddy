"""Maximum holding time in the engine (``run_backtest(..., max_hold=N)``), hand-worked.

The main case is a close-only series traded by the SMA 1/2 crossover with
1000 cash:

    bar    0   1   2   3   4   5   6   7   8   9   10
    close  10  9   8   9   11  12  10  10  11  12  12.2
    signal -   -   -   BUY -   -   SELL -  BUY -   -

Without a maximum holding time: buy 90 @ 11 on bar 4 (cash 10), sell 90 @ 10
on bar 7 (cash 910), buy 75 @ 12 on bar 9 (cash 10), end 10 + 75 x 12.2 = 925.
"""

import pytest

from trading_assistant.backtest import export_columns, export_rows, format_result, run_backtest

CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]
HAND = dict(initial_cash=1000, short=1, long=2)


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.reason) for t in result.trades]


# ----------------------------------------------------------------- the hand case (closes only)


def test_without_max_hold_ends_at_925():
    result = run_backtest(CLOSES, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"),
        (7, "SELL", 90, 10, "signal"),
        (9, "BUY", 75, 12, "signal"),
    ]
    assert result.final_equity == pytest.approx(925.00)
    assert result.max_hold == 0


def test_max_hold_1_sells_on_bars_5_and_10():
    # Bought on bar 4, sold on bar 5 at its close 12: cash 10 + 90 x 12 = 1090. The SELL signal
    # of bar 6 finds nothing to sell. Buy 90 @ 12 on bar 9 (cash 10), sold on bar 10 at 12.2.
    result = run_backtest(CLOSES, max_hold=1, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"),
        (5, "SELL", 90, 12, "time"),
        (9, "BUY", 90, 12, "signal"),
        (10, "SELL", 90, 12.2, "time"),
    ]
    assert result.n_trades == 4
    assert result.n_time_exits == 2
    assert result.final_position == 0
    assert result.final_equity == pytest.approx(1108.00)


def test_max_hold_2_sells_on_bar_6():
    # Sold on bar 6 at its close 10 (cash 910); bar 7's SELL finds nothing; buy 75 @ 12 on bar 9,
    # held only one bar by the end: 10 + 75 x 12.2 = 925.
    result = run_backtest(CLOSES, max_hold=2, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"),
        (6, "SELL", 90, 10, "time"),
        (9, "BUY", 75, 12, "signal"),
    ]
    assert result.final_equity == pytest.approx(925.00)


def test_max_hold_3_gives_way_to_the_signal_sell_on_bar_7():
    # Due on bar 7, but the SELL signal fills there: it wins and is labelled signal.
    plain = run_backtest(CLOSES, **HAND)
    result = run_backtest(CLOSES, max_hold=3, **HAND)
    assert fills(result) == fills(plain)
    assert result.trades[1].bar == 7 and result.trades[1].reason == "signal"
    assert result.n_time_exits == 0
    assert result.final_equity == pytest.approx(925.00)
    assert result.equity_curve == plain.equity_curve


def test_a_long_max_hold_never_fires_and_leaves_the_end_position():
    result = run_backtest(CLOSES, max_hold=50, **HAND)
    assert fills(result) == fills(run_backtest(CLOSES, **HAND))
    assert result.final_position == 75  # not force-liquidated at the end


def test_slippage_and_fees_apply_to_a_time_exit():
    result = run_backtest(CLOSES, max_hold=1, slippage_pct=1.0, fee=1.0, **HAND)
    sell = result.trades[1]
    assert (sell.bar, sell.reason) == (5, "time")
    assert sell.price == pytest.approx(12 * 0.99)
    assert sell.cost == pytest.approx(1.0)


# ----------------------------------------------------------------- which fill a bar gets


def test_a_stop_on_the_due_bar_wins_with_close_fills():
    # Flat candles (high = low = close). Entry 11 on bar 4, stop 5% below = 10.45; bar 6's low of 10
    # reaches it. max_hold=2 is due on bar 6 too, but the stop fills there first.
    stop_only = run_backtest(CLOSES, highs=CLOSES, lows=CLOSES, stop_pct=5, **HAND)
    both = run_backtest(CLOSES, highs=CLOSES, lows=CLOSES, stop_pct=5, max_hold=2, **HAND)
    assert both.trades[1].bar == 6 and both.trades[1].reason == "stop"
    assert both.trades[1].price == pytest.approx(10.45)
    assert fills(both) == fills(stop_only)


BREAKOUT = dict(initial_cash=1000, strategy="breakout", strategy_params={"window": 1}, position_size=0.5)
RISING = [10, 11, 12, 12, 12, 12]  # BUY signals on bars 1 and 2: buys fill on bars 2 and 3


def test_a_buy_on_the_due_bar_makes_the_time_exit_wait():
    # First buy on bar 2, so max_hold=1 is due on bar 3; a second buy fills there, so the
    # time exit waits for bar 4, the next bar without a fill.
    result = run_backtest(RISING, max_hold=1, **BREAKOUT)
    assert fills(result) == [
        (2, "BUY", 41, 12, "signal"),
        (3, "BUY", 41, 12, "signal"),
        (4, "SELL", 82, 12, "time"),
    ]


def test_the_clock_runs_from_the_first_buy():
    # max_hold=2 from the first buy (bar 2) is due on bar 4; the buy on bar 3 does not
    # restart it (which would give bar 5).
    result = run_backtest(RISING, max_hold=2, **BREAKOUT)
    assert fills(result)[-1] == (4, "SELL", 82, 12, "time")
    assert result.round_trips[0].entry_bar == 2 and result.round_trips[0].exit_bar == 4


# ----------------------------------------------------------------- open fills


def candles(bar5_open):
    """The hand closes as candles; buy at bar 4's open (10) and a bar 5 whose low (9) reaches a 5% stop (9.5)."""
    opens, highs, lows = list(CLOSES), list(CLOSES), list(CLOSES)
    opens[4], highs[4], lows[4] = 10, 11, 10
    opens[5], highs[5], lows[5] = bar5_open, max(12.5, bar5_open), 9
    return dict(fill="open", opens=opens, highs=highs, lows=lows, stop_pct=5, **HAND)


def test_open_fills_time_exit_at_the_open_beats_a_stop_reached_later_in_the_bar():
    # Bought 100 @ 10 at bar 4's open. Bar 5 opens at 12 and only later falls to 9, through the 9.5 stop.
    assert fills(run_backtest(CLOSES, **candles(12)))[1] == (5, "SELL", 100, 9.5, "stop")
    # With max_hold=1 it is sold at bar 5's open, 12, before the low is reached (cash 1200).
    # Bar 8's BUY fills at bar 9's open (12): 100 shares; sold at bar 10's open, 12.2.
    result = run_backtest(CLOSES, max_hold=1, **candles(12))
    assert fills(result) == [
        (4, "BUY", 100, 10, "signal"),
        (5, "SELL", 100, 12, "time"),
        (9, "BUY", 100, 12, "signal"),
        (10, "SELL", 100, 12.2, "time"),
    ]
    assert result.final_equity == pytest.approx(1220.00)


def test_open_fills_a_gap_through_the_stop_at_the_open_wins_and_starts_a_cooldown():
    # Bar 5 opens at 9, below the 9.5 stop: the stop sells at the open, labelled stop, not time.
    result = run_backtest(CLOSES, max_hold=1, **candles(9))
    assert fills(result)[1] == (5, "SELL", 100, 9, "stop")
    # That stop starts the cooldown: bars 6 to 10 take no buy, so bar 9's buy is dropped.
    cooled = run_backtest(CLOSES, max_hold=1, cooldown=5, **candles(9))
    assert fills(cooled) == [(4, "BUY", 100, 10, "signal"), (5, "SELL", 100, 9, "stop")]
    assert cooled.cooldown_skipped_buys == 1


# ----------------------------------------------------------------- no cooldown from a time exit


def test_a_time_exit_starts_no_cooldown():
    # A 50% stop that is never reached turns the cooldown on. The time exit on bar 5 starts none,
    # so bar 9's buy (inside bars 6..10) still fills, exactly as without the stop and cooldown.
    flat = dict(highs=CLOSES, lows=CLOSES, stop_pct=50)
    result = run_backtest(CLOSES, max_hold=1, cooldown=5, **flat, **HAND)
    assert fills(result) == fills(run_backtest(CLOSES, max_hold=1, **HAND))
    assert result.cooldown_skipped_buys == 0
    assert result.final_equity == pytest.approx(1108.00)


def test_open_fills_a_time_exit_starts_no_cooldown():
    result = run_backtest(CLOSES, max_hold=1, cooldown=5, **candles(12))
    assert (9, "BUY", 100, 12, "signal") in fills(result)
    assert result.cooldown_skipped_buys == 0


# ----------------------------------------------------------------- settings


@pytest.mark.parametrize("bad", [-1, 1.5, "2", True, None])
def test_max_hold_must_be_a_whole_number_of_at_least_0(bad):
    with pytest.raises(ValueError, match="max_hold must be a whole number of at least 0"):
        run_backtest(CLOSES, max_hold=bad, **HAND)


def test_max_hold_needs_no_highs_or_lows():
    # Closes only: no highs, lows or opens are asked for.
    assert run_backtest(CLOSES, max_hold=1, **HAND).n_time_exits == 2


# ----------------------------------------------------------------- runs without max_hold are unchanged


SETTINGS = [
    {},
    dict(fee=1.0, fee_pct=0.1, slippage_pct=0.5, position_size=0.5),
    dict(strategy="breakout", strategy_params={"window": 2}),
    dict(highs=CLOSES, lows=CLOSES, stop_pct=5),
    dict(highs=CLOSES, lows=CLOSES, take_profit_pct=5, trail_pct=5, stop_pct=8, cooldown=2),
    dict(fill="open", opens=CLOSES),
]


def _everything(result):
    return (
        fills(result),
        result.equity_curve,
        result.final_equity,
        result.round_trips,
        result.cooldown_skipped_buys,
        result.risk_skipped_buys,
        result.has_exits,
        format_result(result, 1, 2),
        export_columns(result),
        export_rows(result),
    )


@pytest.mark.parametrize("settings", SETTINGS)
def test_max_hold_0_is_the_same_as_leaving_it_out(settings):
    assert _everything(run_backtest(CLOSES, max_hold=0, **settings, **HAND)) == _everything(
        run_backtest(CLOSES, **settings, **HAND)
    )


def test_without_max_hold_the_report_and_export_are_unchanged():
    result = run_backtest(CLOSES, **HAND)
    lines = format_result(result, 1, 2)
    assert not any("Max hold" in line for line in lines)
    assert not any("Exits:" in line for line in lines)
    assert "reason" not in export_columns(result)
    assert not lines[4].rstrip().endswith("signal")  # no reason on the fill lines


# ----------------------------------------------------------------- the text report


def test_report_with_max_hold_only():
    lines = format_result(run_backtest(CLOSES, max_hold=1, **HAND), 1, 2)
    assert "  Max hold:    1 bar after a position's first buy, then sold at the bar's fill price; 2 time exits" in lines
    assert not any(line.startswith("  Exits:") for line in lines)  # no price exit in use
    fill_lines = [line for line in lines if line.startswith("    #")]
    assert [line.split()[-1] for line in fill_lines] == ["signal", "time", "signal", "time"]


def test_report_plural_and_singular():
    lines = format_result(run_backtest(CLOSES, max_hold=2, **HAND), 1, 2)
    assert "  Max hold:    2 bars after a position's first buy, then sold at the bar's fill price; 1 time exit" in lines
    lines = format_result(run_backtest(CLOSES, max_hold=3, **HAND), 1, 2)
    assert "  Max hold:    3 bars after a position's first buy, then sold at the bar's fill price; 0 time exits" in lines


def test_report_with_a_stop_and_a_cooldown_keeps_their_lines_in_order():
    result = run_backtest(CLOSES, highs=CLOSES, lows=CLOSES, stop_pct=50, cooldown=5, max_hold=1, **HAND)
    lines = format_result(result, 1, 2)
    labels = [line.split(":")[0].strip() for line in lines if line.startswith("  ") and ":" in line]
    assert labels.index("Exits") < labels.index("Cooldown") < labels.index("Max hold") < labels.index("Round trips")


def test_export_has_the_reason_column_with_max_hold():
    result = run_backtest(CLOSES, max_hold=1, **HAND)
    assert export_columns(result)[-1] == "reason"
    reasons = [row[-1] for row in export_rows(result)]
    assert reasons == ["", "", "", "", "signal", "time", "", "", "", "signal", "time"]
