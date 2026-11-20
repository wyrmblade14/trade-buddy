"""Tests for the breakeven stop (``run_backtest(..., breakeven_pct=...)``).

Main case: tests/data/c.csv, cash 1000, short=1, long=2, close fills (the default):

    bar  open  high   low  close
     0   10    10.5   9.5   10
     1    9.2   9.5   8.5    9
     2    8.3   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal
     4   10.8  11.5  10.5   11     BUY fills @ 11: int(1000 / 11) = 90 shares, 990, cash 10; entry 11 (entry bar)
     5   11    12    10.8   12     high 12: arms at 5 % (11.55) and 9 % (11.99), not at 10 % (12.10)
     6   11.5  12     9.5   10     armed: opens 11.5 above 11, low 9.5 <= 11 -> SELL 90 @ 11.00, cash 1000
                                   (also a SELL signal, due on bar 7)
     7    9.8  10.2   9.6   10     without the stop: signal SELL 90 @ 10.00, cash 910
     8   10    11.5   9.9   11     BUY signal
     9   10.8  12.5  10.5   12     BUY fills @ 12
    10   12    12.4  11.8   12.2   last close 12.2

Without the option: BUY 90 @ 11 (bar 4), SELL 90 @ 10 (bar 7, signal), BUY int(910 / 12) = 75 @ 12
    (bar 9), cash 10; end 10 + 75 * 12.2 = 925.00.
With 5 or 9: SELL 90 @ 11.00 on bar 6 (breakeven), cash 1000; BUY int(1000 / 12) = 83 @ 12 = 996 on bar 9,
    cash 4; 3 trades; end 4 + 83 * 12.2 = 1016.60 (marked at the last close, 12.2).
With 10: bar 5's high 12 is below 12.10 and bar 6's high 12 too: same fills as without it.
With 5 and cooldown 3: the breakeven sale on bar 6 blocks bars 7-9, so the bar 9 buy is skipped:
    2 trades, end 1000.00.
"""

import json
from pathlib import Path

import pytest

from trading_assistant.backtest import format_result, run_backtest
from trading_assistant.data import load_candles
from trading_assistant.signals import BUY, SELL

DATA = Path(__file__).resolve().parent / "data"
A = pytest.approx


def candle_kwargs(candles):
    return dict(
        closes=[c.close for c in candles],
        opens=[c.open for c in candles],
        highs=[c.high for c in candles],
        lows=[c.low for c in candles],
    )


C = candle_kwargs(load_candles(DATA / "c.csv"))
BASE = dict(initial_cash=1000, short=1, long=2)


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason) for t in result.trades]


WITHOUT = [(4, BUY, 90, 11.0, 10.0, "signal"), (7, SELL, 90, 10.0, 910.0, "signal"), (9, BUY, 75, 12.0, 10.0, "signal")]
BREAKEVEN = [(4, BUY, 90, 11.0, 10.0, "signal"), (6, SELL, 90, 11.0, 1000.0, "breakeven"), (9, BUY, 83, 12.0, 4.0, "signal")]


# --- the c.csv case --------------------------------------------------------------------------------------


def test_c_csv_without_the_option():
    r = run_backtest(**C, **BASE)
    assert fills(r) == WITHOUT
    assert r.final_equity == A(925.0)
    assert r.breakeven_pct is None


@pytest.mark.parametrize("pct", [5, 9])
def test_c_csv_breakeven_sells_at_entry_on_bar_6(pct):
    r = run_backtest(**C, **BASE, breakeven_pct=pct)
    assert fills(r) == BREAKEVEN
    assert r.n_trades == 3
    assert r.final_cash == A(4.0) and r.final_position == 83
    assert r.final_equity == A(4 + 83 * 12.2) == A(1016.6)
    assert r.breakeven_pct == pct
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.pnl) == (4, 6, A(0.0))


def test_c_csv_breakeven_10_is_never_armed():
    r = run_backtest(**C, **BASE, breakeven_pct=10)
    assert fills(r) == WITHOUT
    assert r.trades[1].reason == "signal" and r.trades[1].bar == 7
    assert r.final_equity == A(925.0)


def test_c_csv_breakeven_starts_a_cooldown():
    r = run_backtest(**C, **BASE, breakeven_pct=5, cooldown=3)
    assert fills(r) == BREAKEVEN[:2]
    assert r.n_trades == 2
    assert r.cooldown_skipped_buys == 1
    assert r.final_equity == A(1000.0)


def test_c_csv_arming_bar_does_not_sell_and_the_stop_acts_only_on_later_bars():
    # Bar 5 arms the stop (high 12) but its low 10.8 is below the entry 11: it must not sell on bar 5.
    r = run_backtest(**C, **BASE, breakeven_pct=5)
    assert [t.bar for t in r.trades if t.side == SELL] == [6]


# --- gaps ----------------------------------------------------------------------------------------------


def with_bar(kwargs, t, open_, high, low, close):
    out = {k: list(v) for k, v in kwargs.items()}
    out["opens"][t], out["highs"][t], out["lows"][t], out["closes"][t] = open_, high, low, close
    return out


def test_gap_through_the_level_sells_at_the_open():
    # Bar 6 opens at 10.5, below the armed level 11: SELL 90 @ 10.50 = 945, cash 955.
    gapped = with_bar(C, 6, 10.5, 12.0, 9.5, 10.0)
    r = run_backtest(**gapped, **BASE, breakeven_pct=5)
    assert fills(r)[1] == (6, SELL, 90, 10.5, 955.0, "breakeven")


def test_gap_needs_the_opens_without_them_the_level_is_used():
    gapped = with_bar(C, 6, 10.5, 12.0, 9.5, 10.0)
    del gapped["opens"]
    r = run_backtest(**gapped, **BASE, breakeven_pct=5)
    assert fills(r)[1] == (6, SELL, 90, 11.0, 1000.0, "breakeven")


def test_open_exactly_at_the_level_sells_at_the_level():
    at_level = with_bar(C, 6, 11.0, 12.0, 9.5, 10.0)
    r = run_backtest(**at_level, **BASE, breakeven_pct=5)
    assert fills(r)[1] == (6, SELL, 90, 11.0, 1000.0, "breakeven")


# --- the entry bar's high never counts -----------------------------------------------------------------

# c.csv with bars 5 and 6 lowered: bar 5 open 11, high 11.2, low 11, close 11.2; bar 6 open 11, high 11.2,
# low 9.5, close 10 (signals unchanged: bar 6 is still a SELL signal, filled on bar 7). The entry bar 4 has
# high 11.5; no later high before the sale on bar 7 is above 11.2.
LOW_BAR_5 = with_bar(with_bar(C, 5, 11.0, 11.2, 11.0, 11.2), 6, 11.0, 11.2, 9.5, 10.0)


@pytest.mark.parametrize(
    "fill, entry",
    [
        ("close", 11.0),  # 4 %: trigger 11.44, entry bar high 11.5 would reach it, bar 5's 11.2 does not
        ("open", 10.8),  # 4 %: trigger 11.232, same
    ],
)
def test_entry_bar_high_does_not_arm_in_either_fill_mode(fill, entry):
    r = run_backtest(**LOW_BAR_5, **BASE, fill=fill, breakeven_pct=4)
    assert r.trades[0].price == A(entry)
    assert "breakeven" not in [t.reason for t in r.trades]
    assert (r.trades[1].bar, r.trades[1].reason) == (7, "signal")


@pytest.mark.parametrize("fill, entry", [("close", 11.0), ("open", 10.8)])
def test_a_later_bar_with_a_high_at_the_trigger_arms_it(fill, entry):
    # Control for the test above: a trigger bar 5's high 11.2 reaches (1 %: 11.11 / 10.908) does arm it.
    r = run_backtest(**LOW_BAR_5, **BASE, fill=fill, breakeven_pct=1)
    assert (r.trades[1].bar, r.trades[1].price, r.trades[1].reason) == (6, A(entry), "breakeven")


def test_a_high_exactly_at_the_trigger_arms_it():
    # Entry 10, 10 %: trigger 10 * 1.1 = 11.000000000000002 in floats, so use 25 %: 12.5 exactly.
    closes = [9.0, 10.0, 10.0, 10.0, 10.0]
    kwargs = dict(
        closes=closes,
        opens=[9.0, 9.0, 10.0, 10.0, 10.0],
        highs=[9.0, 10.0, 10.0, 12.5, 10.0],
        lows=[9.0, 9.0, 10.0, 10.0, 9.0],
    )
    r = run_backtest(**kwargs, initial_cash=1000, strategy="breakout", strategy_params={"window": 1}, breakeven_pct=25)
    assert fills(r) == [(2, BUY, 100, 10.0, 0.0, "signal"), (4, SELL, 100, 10.0, 1000.0, "breakeven")]
    r = run_backtest(**kwargs, initial_cash=1000, strategy="breakout", strategy_params={"window": 1}, breakeven_pct=25.01)
    assert [t.reason for t in r.trades] == ["signal"]


# --- an extra buy into the position moves the average -----------------------------------------------------

# breakout with window 1 (BUY on a higher close, SELL on a lower one), cash 1000, position_size 0.5.
PYRAMID = dict(initial_cash=1000, strategy="breakout", strategy_params={"window": 1}, position_size=0.5)


def test_armed_stop_stays_armed_and_follows_the_new_average():
    """
    bar  open  high   low  close
     0    9     9     9      9
     1    9    10     9     10     BUY signal
     2    9.8  10.1   9.7   10     BUY 50 @ 10 (half of 1000), cash 500; entry bar
     3   10    10.6  10.1   10.4   high 10.6 >= 10.5 (5 %): armed; BUY signal
     4   10.4  10.5  10.3   10.4   armed level 10, low 10.3 above it; BUY int(500 / 10.4) = 48 @ 10.4 = 499.2,
                                   cash 0.8; average (500 + 499.2) / 98 = 10.1959
     5   10.4  10.5  10.1   10.4   low 10.1 reaches the new average (not the old level 10): SELL 98 @ 10.1959
    No high after bar 4 reaches 1.05 x the new average (10.706), so the sale shows the stop stayed armed.
    """
    kwargs = dict(
        closes=[9.0, 10.0, 10.0, 10.4, 10.4, 10.4],
        opens=[9.0, 9.0, 9.8, 10.0, 10.4, 10.4],
        highs=[9.0, 10.0, 10.1, 10.6, 10.5, 10.5],
        lows=[9.0, 9.0, 9.7, 10.1, 10.3, 10.1],
    )
    r = run_backtest(**kwargs, **PYRAMID, breakeven_pct=5)
    average = (500 + 48 * 10.4) / 98
    assert fills(r) == [
        (2, BUY, 50, 10.0, 500.0, "signal"),
        (4, BUY, 48, 10.4, 0.8, "signal"),
        (5, SELL, 98, average, 1000.0, "breakeven"),
    ]
    (rt,) = r.round_trips
    assert rt.pnl == A(0.0)


def test_unarmed_stop_measures_from_the_new_average():
    """
    bar  open  high   low  close
     0    9     9     9      9
     1    9    10     9     10     BUY signal
     2    9.8  10     9.7   10     BUY 50 @ 10, cash 500; entry bar
     3   10    10.5  10     10.5   high 10.5, under 11 (10 %); BUY signal
     4   10.5  10.5  10.5   10.5   BUY int(500 / 10.5) = 47 @ 10.5 = 493.5, cash 6.5;
                                   average (500 + 493.5) / 97 = 10.2423, trigger 11.2665
     5   10.6  11.1  10.5   10.5   high 11.1: above 11 (the first entry's trigger) but under 11.2665: not armed
     6   10.6  10.7  10.0   10.5   low 10.0 below the average: no sale, the stop is not armed
     7   10.6  11.3  10.5   10.5   high 11.3 >= 11.2665: armed
     8   10.5  10.6  10.2   10.3   low 10.2 reaches the average: SELL 97 @ 10.2423 = 993.5, cash 1000
    """
    kwargs = dict(
        closes=[9.0, 10.0, 10.0, 10.5, 10.5, 10.5, 10.5, 10.5, 10.3],
        opens=[9.0, 9.0, 9.8, 10.0, 10.5, 10.6, 10.6, 10.6, 10.5],
        highs=[9.0, 10.0, 10.0, 10.5, 10.5, 11.1, 10.7, 11.3, 10.6],
        lows=[9.0, 9.0, 9.7, 10.0, 10.5, 10.5, 10.0, 10.5, 10.2],
    )
    r = run_backtest(**kwargs, **PYRAMID, breakeven_pct=10)
    average = (500 + 47 * 10.5) / 97
    assert fills(r) == [
        (2, BUY, 50, 10.0, 500.0, "signal"),
        (4, BUY, 47, 10.5, 6.5, "signal"),
        (8, SELL, 97, average, 1000.0, "breakeven"),
    ]


# --- ties and other stops ------------------------------------------------------------------------------

# breakout window 1, cash 1000: BUY 100 @ 10 on bar 2; bar 3's high 20 arms the breakeven stop (any % up to
# 100) and makes the trail's peak 20; bar 4's low 9 reaches both levels.
TIE = dict(
    closes=[9.0, 10.0, 10.0, 20.0, 15.0],
    opens=[9.0, 9.0, 10.0, 10.0, 15.0],
    highs=[9.0, 10.0, 10.0, 20.0, 16.0],
    lows=[9.0, 9.0, 10.0, 10.0, 9.0],
)
TIE_RUN = dict(initial_cash=1000, strategy="breakout", strategy_params={"window": 1})


def test_tie_with_the_trailing_stop_goes_to_trail():
    # trail 50 %: 20 * 0.5 = 10.0, exactly the entry price.
    r = run_backtest(**TIE, **TIE_RUN, trail_pct=50, breakeven_pct=5)
    assert fills(r)[1] == (4, SELL, 100, 10.0, 1000.0, "trail")


def test_breakeven_above_the_trailing_stop_wins():
    # trail 60 %: 20 * 0.4 = 8, below the breakeven level 10.
    r = run_backtest(**TIE, **TIE_RUN, trail_pct=60, breakeven_pct=5)
    assert fills(r)[1] == (4, SELL, 100, 10.0, 1000.0, "breakeven")


def test_trailing_stop_above_breakeven_wins():
    # trail 20 %: 20 * 0.8 = 16; bar 4 opens at 15, below it -> trail at the open.
    r = run_backtest(**TIE, **TIE_RUN, trail_pct=20, breakeven_pct=5)
    assert fills(r)[1] == (4, SELL, 100, 15.0, 1500.0, "trail")


def test_breakeven_replaces_a_lower_stop_loss_once_armed():
    r = run_backtest(**C, **BASE, stop_pct=5, breakeven_pct=5)
    assert fills(r)[1] == (6, SELL, 90, 11.0, 1000.0, "breakeven")


def test_breakeven_at_or_above_the_target_never_acts():
    # Target 5 % (11.55) is reached by bar 5's high 12, the same bar that would arm the stop.
    r = run_backtest(**C, **BASE, take_profit_pct=5, breakeven_pct=5)
    assert fills(r)[1] == (5, SELL, 90, 11.55, 1049.5, "target")
    assert "breakeven" not in [t.reason for t in r.trades]


def test_breakeven_stop_pays_slippage_and_fees():
    # Slippage 1 %: BUY @ 11.11 -> 90 shares (999.9), cash 0.1; trigger 11.6655, bar 5's high 12 arms it;
    # bar 6 sells at 11.11 * 0.99 = 10.9989: the "breakeven" sale loses the costs.
    r = run_backtest(**C, **BASE, slippage_pct=1, breakeven_pct=5)
    sell = r.trades[1]
    assert (sell.bar, sell.reason) == (6, "breakeven")
    assert sell.price == A(11.11 * 0.99)
    assert r.round_trips[0].pnl < 0


# --- checks ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_breakeven_must_be_positive(bad):
    with pytest.raises(ValueError, match="breakeven_pct must be positive"):
        run_backtest(**C, **BASE, breakeven_pct=bad)


def test_large_breakeven_is_allowed():
    r = run_backtest(**C, **BASE, breakeven_pct=500)
    assert fills(r) == WITHOUT


def test_breakeven_needs_highs_and_lows():
    with pytest.raises(ValueError, match="a breakeven stop needs the high and low of every bar"):
        run_backtest(C["closes"], **BASE, breakeven_pct=5)


# --- text report ----------------------------------------------------------------------------------------


def exits_line(result):
    (line,) = [x for x in format_result(result, 1, 2) if x.startswith("  Exits:")]
    return line


def test_report_shows_breakeven_fills_and_exits_line():
    r = run_backtest(**C, **BASE, breakeven_pct=5)
    lines = format_result(r, 1, 2)
    assert any(x.startswith("    #2   bar 6     SELL") and x.endswith("  breakeven") for x in lines)
    assert exits_line(r) == "  Exits:       breakeven at entry once a later high is 5.00% above it"


@pytest.mark.parametrize(
    "kwargs, note",
    [
        (dict(take_profit_pct=20), " (breakeven wins if a bar touches both)"),
        (dict(stop_pct=5), " (the higher of stop and breakeven is used, stop on a tie)"),
        (dict(trail_pct=10), " (the higher of trail and breakeven is used, trail on a tie)"),
        (
            dict(trail_pct=10, take_profit_pct=20),
            " (the higher of trail and breakeven is used, trail on a tie; it wins if a bar also touches the target)",
        ),
        (
            dict(stop_pct=5, trail_pct=10, atr_stop=True, atr_period=2),
            " (the highest of stop, trail, atr and breakeven is used, in that order on a tie)",
        ),
    ],
)
def test_report_exits_note_with_other_exits(kwargs, note):
    r = run_backtest(**C, **BASE, breakeven_pct=5, **kwargs)
    assert exits_line(r).endswith(note)


def test_report_cooldown_line_names_breakeven():
    r = run_backtest(**C, **BASE, breakeven_pct=5, cooldown=3)
    assert "  Cooldown:    3 bars after a stop, trail, atr or breakeven exit; 1 buy skipped" in format_result(r, 1, 2)


# --- runs without the option are unchanged ----------------------------------------------------------------

# Fills, end equity and the whole text report of c.csv runs with the other exits, recorded from the code
# as it was before the breakeven stop was added.
BEFORE = json.loads((DATA / "c_before_breakeven.json").read_text())
CASES = {
    "plain": {},
    "stop": dict(stop_pct=5),
    "target": dict(take_profit_pct=5),
    "trail": dict(trail_pct=10),
    "atr": dict(atr_stop=True, atr_period=2, atr_mult=1),
    "all_stops": dict(stop_pct=5, trail_pct=10, atr_stop=True, atr_period=2, atr_mult=1, take_profit_pct=20),
    "stop_cooldown": dict(stop_pct=5, cooldown=3),
    "open_trail": dict(fill="open", trail_pct=10),
    "max_hold_dd": dict(max_hold=2, max_drawdown_limit_pct=5),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_runs_without_breakeven_are_unchanged(name):
    assert set(CASES) == set(BEFORE)
    r = run_backtest(**C, **BASE, **CASES[name])
    expected = BEFORE[name]
    assert [[t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason] for t in r.trades] == expected["fills"]
    assert r.final_equity == A(expected["equity"])
    assert format_result(r, 1, 2) == expected["report"]
    assert r.breakeven_pct is None
    assert "breakeven" not in "\n".join(format_result(r, 1, 2))


@pytest.mark.parametrize(
    "fill, kwargs, strategy_params, sale",
    [
        # Close fills, a lower-priced extra buy: BUY 41 @ 12 (bar 4), BUY 48 @ 9 (bar 5, after bar 5's target
        # check at 12.6); average (492 + 432) / 89 = 10.382, bar 5's high 11 >= 10.90 arms the stop; bar 6's
        # low 10.3 sells at the average. The target (10.90 from the new average) is never reached.
        ("close", dict(closes=[9, 9, 9, 10, 12, 9, 10.4, 10.4], highs=[9, 9, 9, 10, 12, 11, 10.5, 10.5],
                       lows=[9, 9, 9, 10, 12, 9, 10.3, 10.3]), {"window": 3}, (6, 89, 924 / 89)),
        # Open fills, a higher-priced extra buy: BUY 47 @ 10.5 at bar 4's open takes bar 4's one fill, so its
        # high 13 (above the target) is not checked; after bar 4 the average 10.2423 is armed; bar 5 opens at
        # 10.6 (below the target 10.75) and its low 10.0 sells at the average.
        ("open", dict(closes=[9, 10, 10, 10.2, 13, 10.5, 10.5], opens=[9, 9, 10, 10.1, 10.5, 10.6, 10.5],
                      highs=[9, 10, 10, 10.2, 13, 10.7, 10.5], lows=[9, 9, 10, 10.0, 10.5, 10.0, 10.5]),
         {"window": 1}, (5, 97, 993.5 / 97)),
    ],
)
def test_at_or_above_the_target_it_acts_only_after_a_later_buy(fill, kwargs, strategy_params, sale):
    # The exceptions to "at or above --take-profit it can never act" that the docs describe.
    run = dict(initial_cash=1000, position_size=0.5, strategy="breakout", strategy_params=strategy_params, fill=fill)
    r = run_backtest(**kwargs, **run, take_profit_pct=5, breakeven_pct=5)
    sell = r.trades[-1]
    assert (sell.bar, sell.side, sell.shares, sell.price, sell.reason) == (sale[0], SELL, sale[1], A(sale[2]), "breakeven")
    assert [t.side for t in r.trades[:-1]] == [BUY, BUY]
