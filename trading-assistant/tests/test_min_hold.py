"""Minimum holding time in the engine (``run_backtest(..., min_hold=N)``), hand-worked.

The main case is a close-only series traded by the SMA 1/2 crossover with
1000 cash (the same closes as ``tests/data/c.csv``):

    bar    0   1   2   3   4   5   6   7   8   9   10
    close  10  9   8   9   11  12  10  10  11  12  12.2
    signal -   -   -   BUY -   -   SELL -  BUY -   -

Without a minimum holding time: buy 90 @ 11 on bar 4 (cash 10), sell 90 @ 10
on bar 7 (cash 910), buy 75 @ 12 on bar 9 (cash 10), end 10 + 75 x 12.2 = 925.

The position opens on bar 4, so the signal sell due on bar 7 comes 3 bars
after it:

* ``min_hold=3``: 7 - 4 = 3 is not below 3, so it fills; same as without it.
* ``min_hold=4``: 3 is below 4, so it is skipped (1 counted). 90 shares stay
  held; bar 9's buy finds 10 cash, not enough for one share at 12. 1 trade,
  end 10 + 90 x 12.2 = 1108.
* ``min_hold=4, max_hold=2``: the time exit sells 90 @ 10 on bar 6 (cash
  910); bar 7's SELL finds nothing held, so nothing is skipped; bar 9 buys
  75 @ 12. End 925, 0 skipped.
"""

import json
from pathlib import Path

import pytest

from trading_assistant.backtest import export_columns, export_rows, format_result, run_backtest
from trading_assistant.data import load_candles

DATA = Path(__file__).resolve().parent / "data"
A = pytest.approx

CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]
HAND = dict(initial_cash=1000, short=1, long=2)


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), t.reason) for t in result.trades]


def candle_kwargs(candles):
    return {
        "closes": [c.close for c in candles],
        "opens": [c.open for c in candles],
        "highs": [c.high for c in candles],
        "lows": [c.low for c in candles],
    }


C = candle_kwargs(load_candles(DATA / "c.csv"))


# ----------------------------------------------------------------- the hand case (closes only)


def test_without_min_hold_ends_at_925():
    result = run_backtest(CLOSES, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"),
        (7, "SELL", 90, 10, "signal"),
        (9, "BUY", 75, 12, "signal"),
    ]
    assert result.final_equity == A(925.00)
    assert result.min_hold == 0
    assert result.min_hold_skipped_sells == 0


def test_min_hold_3_is_the_same_as_without_it():
    result = run_backtest(CLOSES, min_hold=3, **HAND)
    assert fills(result) == fills(run_backtest(CLOSES, **HAND))
    assert result.final_equity == A(925.00)
    assert result.min_hold_skipped_sells == 0


def test_min_hold_4_skips_the_bar_7_sell():
    result = run_backtest(CLOSES, min_hold=4, **HAND)
    # Bar 7's sell is skipped; bar 9's buy has 10 cash and a share costs 12, so it buys nothing.
    assert fills(result) == [(4, "BUY", 90, 11, "signal")]
    assert result.n_trades == 1
    assert result.final_position == 90
    assert result.final_cash == A(10.00)
    assert result.final_equity == A(1108.00)
    assert result.min_hold_skipped_sells == 1


def test_min_hold_4_with_max_hold_2_the_time_exit_sells_first():
    result = run_backtest(CLOSES, min_hold=4, max_hold=2, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"),
        (6, "SELL", 90, 10, "time"),
        (9, "BUY", 75, 12, "signal"),
    ]
    assert result.final_equity == A(925.00)
    # Bar 7's SELL finds nothing held: it would not have filled, so it is not counted.
    assert result.min_hold_skipped_sells == 0


def test_min_hold_1_never_skips_anything():
    # A signal sell can never be due on the bar its position was opened, so 1 is accepted and does nothing.
    result = run_backtest(CLOSES, min_hold=1, **HAND)
    assert fills(result) == fills(run_backtest(CLOSES, **HAND))
    assert result.min_hold_skipped_sells == 0


def test_a_skipped_sell_is_dropped_not_delayed():
    # min_hold=4 allows a signal sell from bar 8 on, but bar 7's SELL is gone: nothing sells on bar 8 or later.
    result = run_backtest(CLOSES, min_hold=4, **HAND)
    assert all(t.side == "BUY" for t in result.trades)


# ----------------------------------------------------------------- a later buy does not reset the count


BREAKOUT = dict(initial_cash=1000, strategy="breakout", strategy_params={"window": 1}, position_size=0.5)
# Breakout with window 1: BUY on bars 1 and 2 (a close above the previous one), SELL on bar 3.
# Close fills: BUY 41 @ 12 on bar 2 (cash 508); BUY int(0.5 x (508 + 41 x 11) / 11) = 43 @ 11 on bar 3
# (cash 35); the SELL is due on bar 4.
UP_THEN_DOWN = [10, 11, 12, 11, 11, 11]


def test_a_later_buy_does_not_reset_the_count():
    # Counted from the first buy (bar 2), the sell on bar 4 is 2 bars in: min_hold=2 lets it fill.
    # Had the buy on bar 3 restarted the count it would be 1 bar in, and skipped.
    result = run_backtest(UP_THEN_DOWN, min_hold=2, **BREAKOUT)
    assert fills(result) == [
        (2, "BUY", 41, 12, "signal"),
        (3, "BUY", 43, 11, "signal"),
        (4, "SELL", 84, 11, "signal"),
    ]
    assert result.min_hold_skipped_sells == 0
    assert result.round_trips[0].entry_bar == 2


def test_a_later_buy_the_window_still_holds_the_sell_back():
    # The same sell with min_hold=3 is inside the window (4 - 2 = 2 < 3) and is skipped.
    result = run_backtest(UP_THEN_DOWN, min_hold=3, **BREAKOUT)
    assert [t.side for t in result.trades] == ["BUY", "BUY"]
    assert result.final_position == 84
    assert result.min_hold_skipped_sells == 1


# ----------------------------------------------------------------- the other exits still sell inside the window


def test_a_stop_still_fires_inside_the_hold_window():
    # c.csv: entry 11 on bar 4, 5% stop at 10.45; bar 6's low 9.5 reaches it. Bar 6 is 2 bars in, well inside
    # a 4-bar window, and the stop sells there exactly as without min_hold.
    without = run_backtest(**C, **HAND, stop_pct=5)
    result = run_backtest(**C, **HAND, stop_pct=5, min_hold=4)
    assert fills(result)[1] == (6, "SELL", 90, 10.45, "stop")
    assert fills(result) == fills(without)
    assert result.final_equity == A(without.final_equity)
    assert result.min_hold_skipped_sells == 0


@pytest.mark.parametrize(
    "exit_settings, sale",
    [
        (dict(stop_pct=5), (6, "SELL", 90, 10.45, "stop")),
        (dict(take_profit_pct=5), (5, "SELL", 90, 11.55, "target")),
        (dict(trail_pct=10), (6, "SELL", 90, 10.8, "trail")),
        (dict(atr_stop=True, atr_period=2, atr_mult=1), (6, "SELL", 90, 9.5625, "atr")),
        (dict(breakeven_pct=5), (6, "SELL", 90, 11.0, "breakeven")),
        (dict(max_hold=2), (6, "SELL", 90, 10.0, "time")),
    ],
)
def test_every_other_exit_still_sells_inside_the_window(exit_settings, sale):
    # Entry on bar 4; a 6-bar window runs to bar 9. Each exit sells on bar 5 or 6 exactly as without min_hold.
    without = run_backtest(**C, **HAND, **exit_settings)
    result = run_backtest(**C, **HAND, **exit_settings, min_hold=6)
    assert fills(result)[1] == sale
    assert fills(result) == fills(without)
    assert result.min_hold_skipped_sells == 0


def test_a_skipped_sell_leaves_the_bar_free_for_the_drawdown_sale():
    # Bar 6 closes at 10 + 90 x 10 = 910, 16.5% below the 1090 peak: the run halts. Without min_hold the
    # signal sell takes bar 7; with it that sell is skipped and the drawdown sale sells on bar 7 instead.
    without = run_backtest(CLOSES, **HAND, max_drawdown_limit_pct=5)
    result = run_backtest(CLOSES, **HAND, max_drawdown_limit_pct=5, min_hold=6)
    assert fills(without)[1] == (7, "SELL", 90, 10, "signal")
    assert fills(result)[1] == (7, "SELL", 90, 10, "drawdown")
    assert result.drawdown_halt_bar == 6
    assert result.min_hold_skipped_sells == 1


# ----------------------------------------------------------------- which sells are counted


def _stop_on_bar_7():
    """Flat candles whose bar 7 dips to 9.5: a 10% stop below the entry 11 (9.9) is first reached on bar 7."""
    lows = list(CLOSES)
    lows[7] = 9.5
    return dict(highs=CLOSES, lows=lows, stop_pct=10)


def test_close_fills_a_stop_on_the_due_bar_leaves_no_sell_to_count():
    # The bar's range comes before its close: the stop sells on bar 7 first, so the signal sell would never
    # have filled and is not counted.
    result = run_backtest(CLOSES, **HAND, **_stop_on_bar_7(), min_hold=4)
    assert fills(result)[1] == (7, "SELL", 90, 9.9, "stop")
    assert fills(result) == fills(run_backtest(CLOSES, **HAND, **_stop_on_bar_7()))
    assert result.min_hold_skipped_sells == 0


def test_open_fills_the_signal_sell_comes_first_so_it_is_counted():
    # Opens equal to the closes. Without min_hold the signal sells at bar 7's open (10) before the stop is
    # looked at. With min_hold=4 it is skipped and counted, and then the stop sells later in the bar at 9.9.
    settings = dict(fill="open", opens=CLOSES, **_stop_on_bar_7())
    assert fills(run_backtest(CLOSES, **HAND, **settings))[1] == (7, "SELL", 90, 10, "signal")
    result = run_backtest(CLOSES, **HAND, **settings, min_hold=4)
    assert fills(result)[1] == (7, "SELL", 90, 9.9, "stop")
    assert result.min_hold_skipped_sells == 1


def test_open_fills_a_skipped_sell():
    # Opens equal to the closes: the same fills as the close-only case, so bar 7's sell is skipped.
    result = run_backtest(CLOSES, **HAND, fill="open", opens=CLOSES, min_hold=4)
    assert fills(result) == [(4, "BUY", 90, 11, "signal")]
    assert result.min_hold_skipped_sells == 1


def test_a_sell_the_fees_would_refuse_is_still_counted():
    # Fee 495 per trade: BUY 45 @ 11 = 495 + 495, cash 10. Bar 7's sell would give 10 + 450 - 495 < 0, so
    # it never fills. The minimum holding time is checked before the fees: it is skipped and counted.
    without = run_backtest(CLOSES, **HAND, fee=495)
    result = run_backtest(CLOSES, **HAND, fee=495, min_hold=4)
    assert fills(without) == fills(result) == [(4, "BUY", 45, 11, "signal")]
    assert without.min_hold_skipped_sells == 0
    assert result.min_hold_skipped_sells == 1


# ----------------------------------------------------------------- settings


@pytest.mark.parametrize("bad", [-1, 1.5, "2", True, None])
def test_min_hold_must_be_a_whole_number_of_at_least_0(bad):
    with pytest.raises(ValueError, match="min_hold must be a whole number of at least 0"):
        run_backtest(CLOSES, min_hold=bad, **HAND)


def test_min_hold_needs_no_highs_or_lows():
    # Closes only: no highs, lows or opens are asked for.
    assert run_backtest(CLOSES, min_hold=4, **HAND).min_hold_skipped_sells == 1


# ----------------------------------------------------------------- runs without min_hold are unchanged

# Fills, end equity, the whole text report and the export of runs with every other setting, recorded from the
# code as it was before the minimum holding time was added (git HEAD, run in a separate worktree).
BEFORE = json.loads((DATA / "c_before_min_hold.json").read_text())
CLOSES_ONLY = {"closes": C["closes"]}
CASES = {
    "plain": (CLOSES_ONLY, {}),
    "costs": (CLOSES_ONLY, dict(fee=1.0, fee_pct=0.1, slippage_pct=0.5, position_size=0.5)),
    "breakout": (CLOSES_ONLY, dict(strategy="breakout", strategy_params={"window": 1}, position_size=0.5)),
    "open": (C, dict(fill="open")),
    "stop": (C, dict(stop_pct=5)),
    "target": (C, dict(take_profit_pct=5)),
    "trail": (C, dict(trail_pct=10)),
    "atr": (C, dict(atr_stop=True, atr_period=2, atr_mult=1)),
    "breakeven": (C, dict(breakeven_pct=5)),
    "stop_cooldown": (C, dict(stop_pct=5, cooldown=3)),
    "open_trail": (C, dict(fill="open", trail_pct=10)),
    "max_hold_dd": (CLOSES_ONLY, dict(max_hold=2, max_drawdown_limit_pct=5)),
}


def _check_against_before(name, result):
    expected = BEFORE[name]
    assert [[t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason] for t in result.trades] == expected[
        "fills"
    ]
    assert result.final_equity == A(expected["equity"])
    assert format_result(result, 1, 2) == expected["report"]
    assert export_columns(result) == expected["export_columns"]
    assert export_rows(result) == expected["export_rows"]


def test_the_recorded_cases_are_all_checked():
    assert set(CASES) == set(BEFORE)


@pytest.mark.parametrize("name", sorted(CASES))
def test_runs_without_min_hold_are_unchanged(name):
    data, settings = CASES[name]
    result = run_backtest(**data, **HAND, **settings)
    _check_against_before(name, result)
    assert result.min_hold == 0
    assert "Min hold" not in "\n".join(format_result(result, 1, 2))


@pytest.mark.parametrize("name", sorted(CASES))
def test_min_hold_0_is_the_same_as_leaving_it_out(name):
    data, settings = CASES[name]
    _check_against_before(name, run_backtest(**data, **HAND, **settings, min_hold=0))


# ----------------------------------------------------------------- the text report


def test_report_with_min_hold_only():
    result = run_backtest(CLOSES, min_hold=4, **HAND)
    lines = format_result(result, 1, 2)
    assert "  Min hold:    4 bars after a position's first buy before a signal sell can fill; 1 signal sell skipped" in (
        lines
    )
    # No fill is made by it, so the fills carry no reason and there is no "Exits:" line.
    assert not any(line.rstrip().endswith("signal") for line in lines if line.startswith("    #"))
    assert not any("Exits:" in line for line in lines)
    assert "reason" not in export_columns(result)


def test_report_plural_and_singular():
    line = next(l for l in format_result(run_backtest(CLOSES, min_hold=1, **HAND), 1, 2) if "Min hold" in l)
    assert line == "  Min hold:    1 bar after a position's first buy before a signal sell can fill; 0 signal sells skipped"


def test_report_min_hold_comes_before_max_hold():
    lines = format_result(run_backtest(CLOSES, min_hold=4, max_hold=2, **HAND), 1, 2)
    labels = [line.split(":")[0].strip() for line in lines]
    assert labels.index("Min hold") + 1 == labels.index("Max hold")
