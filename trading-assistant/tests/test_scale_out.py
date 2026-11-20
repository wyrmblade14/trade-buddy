"""Tests for the scale-out (``run_backtest(..., scale_out_pct=...)``): the engine and the text report.

Main case: tests/data/c.csv, cash 1000, short=1, long=2, close fills (the default). Signals (SMA 1/2): BUY on
bar 3, SELL on bar 6, BUY on bar 8; each fills on the next bar.

    bar  open  high   low  close
     0   10    10.5   9.5   10
     1    9.2   9.5   8.5    9
     2    8.3   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal
     4   10.8  11.5  10.5   11     BUY fills @ 11: int(1000 / 11) = 90 shares, 990, cash 10; entry 11 (entry bar)
     5   11    12    10.8   12     high 12: reaches 5 % (11.55) and 9 % (11.99), not 10 % (12.10)
     6   11.5  12     9.5   10     SELL signal, due on bar 7
     7    9.8  10.2   9.6   10     signal SELL of what is held @ 10
     8   10    11.5   9.9   11     BUY signal
     9   10.8  12.5  10.5   12     BUY fills @ 12
    10   12    12.4  11.8   12.2   last close 12.2

Without the option: BUY 90 @ 11, SELL 90 @ 10 (bar 7), BUY int(910 / 12) = 75 @ 12 (bar 9), cash 10;
    end 10 + 75 * 12.2 = 925.00.
With 5: level 11 * 1.05 = 11.55. Bar 5: 90 // 2 = 45 @ 11.55 = 519.75, cash 10 + 519.75 = 529.75.
    Bar 7: signal SELL 45 @ 10 = 450, cash 979.75. One round trip, 4 -> 7, 90 shares bought:
    pnl = 519.75 + 450 - 990 = -20.25. Bar 9: int(979.75 / 12) = 81 (972), cash 7.75;
    end 7.75 + 81 * 12.2 = 7.75 + 988.20 = 995.95. 4 trades.
With 9: level 11 * 1.09 = 11.99. 45 @ 11.99 = 539.55, cash 549.55; bar 7: + 450 = 999.55;
    pnl 539.55 + 450 - 990 = -0.45. Bar 9: int(999.55 / 12) = 83 (996), cash 3.55;
    end 3.55 + 83 * 12.2 = 3.55 + 1012.60 = 1016.15.
With 10: level 12.10; the highs while held (bar 5 12, bar 6 12, bar 7 10.2) stay below it; after the bar 9
    buy the level is 12 * 1.1 = 13.2 and bar 10's high is 12.4: as without it, 925.00.
With 5 and stop loss 10: stop 11 * 0.9 = 9.90. Bar 5: scale-out as above (low 10.8 > 9.90), cash 529.75;
    the entry stays 11 (the average cost of the 45 still held), so the stop stays 9.90. Bar 6: low 9.5 <= 9.90,
    open 11.5 above it: stop 45 @ 9.90 = 445.50, cash 975.25; pnl 519.75 + 445.50 - 990 = -24.75.
    Bar 9: int(975.25 / 12) = 81 (972), cash 3.25; end 3.25 + 988.20 = 991.45.

"Unchanged" is checked against tests/data/before_scale_out.json, recorded from the code as it was before the
scale-out was added (git HEAD 9ab3743, run from a separate worktree): 26 runs on c.csv and on the built-in
random_walk candles (750 bars, rebuilt from the seeded sample; the file holds a SHA-256 of them to show they are
the same bars), every setting the engine had then. Each run is compared exactly (floats as JSON keeps them).
For the c.csv runs the fills, round trips, per-bar records, counters, final values, statistics and report are
kept as they are and the export rows as a SHA-256 of their JSON; for the 750-bar runs the counters, final values
and number of fills are kept as they are and everything else as a SHA-256, to keep the file small.
"""

import hashlib
import json
import math
from pathlib import Path

import pytest

from trading_assistant.backtest import (
    export_columns,
    export_rows,
    format_result,
    format_stats,
    run_backtest,
)
from trading_assistant.data import load_candles
from trading_assistant.samples import sample_candles
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
NO_OPENS = {k: v for k, v in C.items() if k != "opens"}
BASE = dict(initial_cash=1000, short=1, long=2)


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason) for t in result.trades]


def trips(result):
    return [(r.entry_bar, r.exit_bar, r.shares, A(r.pnl)) for r in result.round_trips]


def with_bar(kwargs, t, open_, high, low, close):
    out = {k: list(v) for k, v in kwargs.items()}
    out["opens"][t], out["highs"][t], out["lows"][t], out["closes"][t] = open_, high, low, close
    return out


def bars(rows):
    """Candle kwargs from (open, high, low, close) rows."""
    return dict(
        opens=[r[0] for r in rows], highs=[r[1] for r in rows], lows=[r[2] for r in rows], closes=[r[3] for r in rows]
    )


WITHOUT = [(4, BUY, 90, 11.0, 10.0, "signal"), (7, SELL, 90, 10.0, 910.0, "signal"), (9, BUY, 75, 12.0, 10.0, "signal")]


# --- the c.csv cases ------------------------------------------------------------------------------------


def test_c_csv_without_the_option():
    r = run_backtest(**C, **BASE)
    assert fills(r) == WITHOUT
    assert r.final_equity == A(925.0)
    assert r.scale_out_pct is None
    assert r.n_scale_out_exits == 0


def test_c_csv_scale_out_5():
    r = run_backtest(**C, **BASE, scale_out_pct=5)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.55, 529.75, "scale_out"),
        (7, SELL, 45, 10.0, 979.75, "signal"),
        (9, BUY, 81, 12.0, 7.75, "signal"),
    ]
    assert r.n_trades == 4 and (r.n_buys, r.n_sells) == (2, 2)
    assert trips(r) == [(4, 7, 90, -20.25)]
    assert r.round_trips[0].outlay == A(990.0) and r.round_trips[0].proceeds == A(969.75)
    assert r.n_round_trips == 1 and r.n_winning_round_trips == 0
    assert r.n_scale_out_exits == 1
    assert (r.final_cash, r.final_position) == (A(7.75), 81)
    assert r.final_equity == A(995.95)
    assert r.scale_out_pct == 5.0


def test_c_csv_scale_out_9():
    r = run_backtest(**C, **BASE, scale_out_pct=9)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.99, 549.55, "scale_out"),
        (7, SELL, 45, 10.0, 999.55, "signal"),
        (9, BUY, 83, 12.0, 3.55, "signal"),
    ]
    assert trips(r) == [(4, 7, 90, -0.45)]
    assert r.final_equity == A(1016.15)


def test_c_csv_scale_out_10_is_never_reached():
    r = run_backtest(**C, **BASE, scale_out_pct=10)
    assert fills(r) == WITHOUT
    assert r.n_scale_out_exits == 0
    assert r.final_equity == A(925.0)


def test_c_csv_scale_out_5_with_stop_loss_10():
    r = run_backtest(**C, **BASE, scale_out_pct=5, stop_pct=10)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.55, 529.75, "scale_out"),
        (6, SELL, 45, 9.90, 975.25, "stop"),
        (9, BUY, 81, 12.0, 3.25, "signal"),
    ]
    assert trips(r) == [(4, 6, 90, -24.75)]
    assert r.final_equity == A(991.45)


# --- gaps -----------------------------------------------------------------------------------------------


def test_gap_through_the_level_sells_at_the_open():
    # Bar 5 opens at 11.80, above the level 11.55: 45 @ 11.80 = 531, cash 10 + 531 = 541.
    # Bar 7: 45 @ 10 = 450, cash 991; pnl 531 + 450 - 990 = -9.
    # Bar 9: int(991 / 12) = 82 (984), cash 7; end 7 + 82 * 12.2 = 7 + 1000.40 = 1007.40.
    gapped = with_bar(C, 5, 11.8, 12.0, 10.8, 12.0)
    r = run_backtest(**gapped, **BASE, scale_out_pct=5)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.8, 541.0, "scale_out"),
        (7, SELL, 45, 10.0, 991.0, "signal"),
        (9, BUY, 82, 12.0, 7.0, "signal"),
    ]
    assert trips(r) == [(4, 7, 90, -9.0)]
    assert r.final_equity == A(1007.40)


def test_without_opens_no_gap_can_be_seen_and_the_level_is_used():
    # Same bars, opens left out: the sale is at the level 11.55, as in the 5 % case (995.95).
    gapped = with_bar(C, 5, 11.8, 12.0, 10.8, 12.0)
    del gapped["opens"]
    r = run_backtest(**gapped, **BASE, scale_out_pct=5)
    assert fills(r)[1] == (5, SELL, 45, 11.55, 529.75, "scale_out")
    assert r.final_equity == A(995.95)


def test_open_exactly_at_the_level_is_a_gap():
    # Bar 5 opens at the level itself (11 * 1.05, computed as the engine does, so it is the same float).
    level = 11 * (1 + 5 / 100.0)
    gapped = with_bar(C, 5, level, 12.0, 10.8, 12.0)
    r = run_backtest(**gapped, **BASE, scale_out_pct=5)
    assert fills(r)[1] == (5, SELL, 45, 11.55, 529.75, "scale_out")


# --- share counts ---------------------------------------------------------------------------------------


def test_odd_share_count_rounds_half_down():
    # Cash 1001: int(1001 / 11) = 91 shares (1001), cash 0. Bar 5: 91 // 2 = 45 @ 11.55 = 519.75, cash 519.75,
    # 46 still held. Bar 7: 46 @ 10 = 460, cash 979.75; pnl 519.75 + 460 - 1001 = -21.25.
    # Bar 9: int(979.75 / 12) = 81 (972), cash 7.75; end 7.75 + 81 * 12.2 = 995.95.
    r = run_backtest(**C, initial_cash=1001, short=1, long=2, scale_out_pct=5)
    assert fills(r) == [
        (4, BUY, 91, 11.0, 0.0, "signal"),
        (5, SELL, 45, 11.55, 519.75, "scale_out"),
        (7, SELL, 46, 10.0, 979.75, "signal"),
        (9, BUY, 81, 12.0, 7.75, "signal"),
    ]
    assert trips(r) == [(4, 7, 91, -21.25)]
    assert r.final_equity == A(995.95)


def test_one_share_sells_nothing():
    # Cash 12: int(12 / 11) = 1 share, cash 1. Bar 5 reaches 11.55 but 1 // 2 = 0: no sale.
    # Bar 7: 1 @ 10, cash 11; bar 9: int(11 / 12) = 0, no buy. Same as without the option.
    kw = dict(initial_cash=12, short=1, long=2)
    r = run_backtest(**C, **kw, scale_out_pct=5)
    assert fills(r) == fills(run_backtest(**C, **kw))
    assert fills(r) == [(4, BUY, 1, 11.0, 1.0, "signal"), (7, SELL, 1, 10.0, 11.0, "signal")]
    assert r.n_scale_out_exits == 0
    assert r.final_equity == A(11.0)


# breakout window 1: BUY when the close is above the previous close, SELL when below, HOLD when equal.
BREAKOUT_1 = dict(strategy="breakout", strategy_params={"window": 1})

# 1 share, then a later buy makes 2, then the scale-out sells 1: the 1-share bar did not use it up.
ONE_SHARE_ROWS = [
    (9, 9, 9, 9),         # 0
    (10, 10, 10, 10),     # 1  BUY signal (10 > 9)
    (10, 10, 10, 10),     # 2  BUY fills @ 10; HOLD (10 = 10)
    (10, 12.5, 10, 12),   # 3  high 12.5 reaches 10 * 1.25 = 12.5, but 1 // 2 = 0; BUY signal (12 > 10)
    (12, 12, 12, 12),     # 4  BUY fills @ 12; HOLD (12 = 12)
    (12, 14, 12, 12),     # 5  high 14 reaches the new level 11 * 1.25 = 13.75: sells 1
    (12, 20, 12, 12),     # 6  high 20: no second scale-out
]


def test_one_share_does_not_use_it_up_and_a_later_buy_can_scale_out():
    # position_size 0.015. Bar 2: budget 0.015 * 1000 = 15, int(15 / 10) = 1 share, cash 990.
    # Bar 3: 1 // 2 = 0, nothing sold and not marked. Bar 4: budget 0.015 * (990 + 12) = 15.03,
    # int(15.03 / 12) = 1 share, cash 978; 2 held at an average cost of (10 + 12) / 2 = 11.
    # Bar 5: level 11 * 1.25 = 13.75 <= high 14: 2 // 2 = 1 @ 13.75, cash 991.75. Bar 6: high 20, already used.
    # End 991.75 + 1 * 12 = 1003.75.
    r = run_backtest(**bars(ONE_SHARE_ROWS), initial_cash=1000, position_size=0.015, scale_out_pct=25, **BREAKOUT_1)
    assert fills(r) == [
        (2, BUY, 1, 10.0, 990.0, "signal"),
        (4, BUY, 1, 12.0, 978.0, "signal"),
        (5, SELL, 1, 13.75, 991.75, "scale_out"),
    ]
    assert r.round_trips == []  # the scale-out completed none
    assert r.final_position == 1
    assert r.final_equity == A(1003.75)


# A later buy after the scale-out: once per position, and the entry is the average cost of the shares held.
LATER_BUY_ROWS = [
    (9, 9, 9, 9),             # 0
    (10, 10, 10, 10),         # 1  BUY signal
    (10, 10, 10, 10),         # 2  BUY fills @ 10; HOLD
    (10, 12.5, 10, 12),       # 3  level 10 * 1.25 = 12.5: scale-out; BUY signal (12 > 10)
    (12.5, 12.5, 12, 12.5),   # 4  BUY fills @ 12.5; BUY signal (12.5 > 12), but no cash is left for it
    (12.5, 14.5, 12.5, 12.5), # 5  high 14.5 is above the new level 11.25 * 1.25 = 14.0625: no second scale-out
    (12.5, 12.5, 8.8, 12.5),  # 6  low 8.8: reaches the stop 11.25 * 0.8 = 9.00
]


def test_later_buy_after_scale_out_averages_with_the_shares_held_and_cannot_scale_out_again():
    # Cash 1000, all in. Bar 2: 100 @ 10 = 1000, cash 0. Bar 3: 50 @ 12.50 = 625, cash 625, 50 held at 10.
    # Bar 4: int(625 / 12.5) = 50 @ 12.5 = 625, cash 0; held 100, cost 50 * 10 + 50 * 12.5 = 1125, entry 11.25.
    # (Averaged over every share bought it would be (1000 + 625) / 150 = 10.83 and the stop 8.67, not reached.)
    # Bar 5: pending BUY gets 0 shares (cash 0); the scale-out is used: no fill.
    # Bar 6: stop 20 %: 11.25 * 0.8 = 9.00 >= low 8.8: 100 @ 9.00 = 900, cash 900.
    # Round trip 2 -> 6, 150 bought, outlay 1625, proceeds 625 + 900 = 1525, pnl -100. End 900.
    r = run_backtest(**bars(LATER_BUY_ROWS), initial_cash=1000, scale_out_pct=25, stop_pct=20, **BREAKOUT_1)
    assert fills(r) == [
        (2, BUY, 100, 10.0, 0.0, "signal"),
        (3, SELL, 50, 12.5, 625.0, "scale_out"),
        (4, BUY, 50, 12.5, 0.0, "signal"),
        (6, SELL, 100, 9.0, 900.0, "stop"),
    ]
    assert trips(r) == [(2, 6, 150, -100.0)]
    (rt,) = r.round_trips
    assert (rt.outlay, rt.proceeds) == (A(1625.0), A(1525.0))
    assert r.n_scale_out_exits == 1
    assert r.final_equity == A(900.0)


def test_flag_resets_when_the_position_is_back_to_zero():
    # The 5 % run on c.csv, extended: after the bar 9 buy (81 @ 12) a new position can scale out again.
    # Bar 10 is changed to high 12.7 >= 12 * 1.05 = 12.60: 81 // 2 = 40 @ 12.60 = 504, cash 7.75 + 504 = 511.75.
    # End 511.75 + 41 * 12.2 = 511.75 + 500.20 = 1011.95.
    extended = with_bar(C, 10, 12.0, 12.7, 11.8, 12.2)
    r = run_backtest(**extended, **BASE, scale_out_pct=5)
    assert [(t.bar, t.shares, t.reason) for t in r.trades if t.reason == "scale_out"] == [(5, 45, "scale_out"), (10, 40, "scale_out")]
    assert fills(r)[-1] == (10, SELL, 40, 12.6, 511.75, "scale_out")
    assert r.n_round_trips == 1
    assert r.final_equity == A(1011.95)


# --- other fills on the same bar win --------------------------------------------------------------------


def test_target_on_the_same_bar_sells_everything_and_the_scale_out_is_skipped():
    # Target 8 %: 11 * 1.08 = 11.88; bar 5's high 12 reaches both: target 90 @ 11.88 = 1069.20, cash 1079.20.
    # pnl 1069.20 - 990 = 79.20. Bar 9: int(1079.20 / 12) = 89 (1068), cash 11.20;
    # end 11.20 + 89 * 12.2 = 11.20 + 1085.80 = 1097.00.
    r = run_backtest(**C, **BASE, scale_out_pct=5, take_profit_pct=8)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 90, 11.88, 1079.20, "target"),
        (9, BUY, 89, 12.0, 11.20, "signal"),
    ]
    assert r.n_scale_out_exits == 0
    assert trips(r) == [(4, 5, 90, 79.20)]
    assert r.final_equity == A(1097.0)


def test_scale_out_at_or_above_the_target_is_allowed_and_never_acts():
    # Target 5 % (11.55) and scale-out 9 % (11.99): the target always sells first. Same as the target alone.
    r = run_backtest(**C, **BASE, scale_out_pct=9, take_profit_pct=5)
    assert fills(r) == fills(run_backtest(**C, **BASE, take_profit_pct=5))
    assert r.n_scale_out_exits == 0
    r = run_backtest(**C, **BASE, scale_out_pct=5, take_profit_pct=5)
    assert fills(r) == fills(run_backtest(**C, **BASE, take_profit_pct=5))


# Bar 7 given a high of 12.5, above the 10 % level 12.10; the pending signal SELL is due on bar 7 too.
BAR7_HIGH = with_bar(C, 7, 9.8, 12.5, 9.6, 10.0)


def test_signal_sell_on_the_same_bar_sells_everything_and_the_scale_out_is_skipped():
    # Close fills: the signal SELL 90 @ 10 takes bar 7; no partial sale. As without the option: 925.00.
    r = run_backtest(**BAR7_HIGH, **BASE, scale_out_pct=10)
    assert fills(r) == WITHOUT
    assert r.n_scale_out_exits == 0
    assert r.final_equity == A(925.0)


def test_signal_sell_at_the_open_on_the_same_bar_wins_too():
    # Open fills. Bar 4: int(1000 / 10.8) = 92 @ 10.80 = 993.60, cash 6.40. 15 %: level 10.8 * 1.15 = 12.42,
    # above the highs of bars 5 and 6 (12) and below bar 7's 12.5. (10 % would be 11.88 and sell on bar 5.)
    # Bar 7: the signal SELL fills first at the open, 92 @ 9.80 = 901.60, cash 908.00. No scale-out.
    r = run_backtest(**BAR7_HIGH, **BASE, fill="open", scale_out_pct=15)
    assert fills(r)[:2] == [(4, BUY, 92, 10.8, 6.4, "signal"), (7, SELL, 92, 9.8, 908.0, "signal")]
    assert r.n_scale_out_exits == 0


def test_min_hold_does_not_hold_it_back_and_a_dropped_signal_sell_leaves_the_bar_to_it():
    # min_hold 5: the bar 7 SELL (7 - 4 = 3 < 5) is dropped and counted, so the scale-out takes bar 7:
    # 45 @ 12.10 = 544.50, cash 554.50. Bar 9: int(554.50 / 12) = 46 (552), cash 2.50; 91 held.
    # End 2.50 + 91 * 12.2 = 2.50 + 1110.20 = 1112.70. No round trip is completed.
    r = run_backtest(**BAR7_HIGH, **BASE, scale_out_pct=10, min_hold=5)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (7, SELL, 45, 12.1, 554.5, "scale_out"),
        (9, BUY, 46, 12.0, 2.5, "signal"),
    ]
    assert r.min_hold_skipped_sells == 1
    assert r.round_trips == []
    assert r.final_equity == A(1112.70)


def test_signal_buy_on_the_same_bar_wins_and_moves_the_level():
    # breakout window 1 on c.csv's closes, position_size 0.5. Bar 4: budget 500, int(500 / 11) = 45 @ 11 = 495,
    # cash 505. Bar 5: the level 11.55 is reached (high 12) but a pending BUY fills at the close first:
    # budget 0.5 * (505 + 45 * 12) = 522.50, capped by the cash 505: int(505 / 12) = 42 @ 12 = 504, cash 1.
    # Now 87 held at (495 + 504) / 87 = 11.4828; level 11.4828 * 1.05 = 12.0569. Bar 6's high 12 is above the
    # old level 11.55 but below the new one: no scale-out. So the run is the same as without the option.
    r = run_backtest(**C, initial_cash=1000, position_size=0.5, scale_out_pct=5, **BREAKOUT_1)
    assert fills(r)[:2] == [(4, BUY, 45, 11.0, 505.0, "signal"), (5, BUY, 42, 12.0, 1.0, "signal")]
    assert r.n_scale_out_exits == 0
    assert fills(r) == fills(run_backtest(**C, initial_cash=1000, position_size=0.5, **BREAKOUT_1))


def test_scale_out_makes_the_time_exit_wait():
    # max_hold 1, close fills. Bar 5 (time due: 5 - 4 = 1): the scale-out 45 @ 11.55 takes the bar, cash 529.75.
    # Bar 6: time exit 45 @ close 10 = 450, cash 979.75; pnl 519.75 + 450 - 990 = -20.25.
    # Bar 9: 81 @ 12, cash 7.75. Bar 10: time exit 81 @ 12.2 = 988.20, cash 995.95 (level 12.6 > high 12.4).
    r = run_backtest(**C, **BASE, scale_out_pct=5, max_hold=1)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.55, 529.75, "scale_out"),
        (6, SELL, 45, 10.0, 979.75, "time"),
        (9, BUY, 81, 12.0, 7.75, "signal"),
        (10, SELL, 81, 12.2, 995.95, "time"),
    ]
    assert trips(r) == [(4, 6, 90, -20.25), (9, 10, 81, 16.20)]  # 988.20 - 972
    assert r.final_equity == A(995.95)


def test_time_exit_at_the_open_beats_it():
    # Open fills, max_hold 1. Bar 4: 92 @ 10.80, cash 6.40. Bar 5: the time exit sells at the open,
    # 92 @ 11 = 1012, cash 1018.40, before the bar's high (12) can reach the level 10.8 * 1.05 = 11.34.
    r = run_backtest(**C, **BASE, fill="open", scale_out_pct=5, max_hold=1)
    assert fills(r)[:2] == [(4, BUY, 92, 10.8, 6.4, "signal"), (5, SELL, 92, 11.0, 1018.4, "time")]
    assert r.n_scale_out_exits == 0


# --- costs ----------------------------------------------------------------------------------------------


def test_fees_apply_to_the_partial_sale_and_go_into_the_round_trip():
    # Fee 1 per trade. Bar 4: int((1000 - 1) / 11) = 90, 990 + 1 = 991, cash 9.
    # Bar 5: 45 @ 11.55 = 519.75 - 1 = 518.75, cash 527.75. Bar 7: 45 @ 10 = 450 - 1 = 449, cash 976.75.
    # Round trip: outlay 991, proceeds 518.75 + 449 = 967.75, pnl -23.25.
    # Bar 9: int((976.75 - 1) / 12) = 81, 972 + 1 = 973, cash 3.75; end 3.75 + 988.20 = 991.95. Costs 4.
    r = run_backtest(**C, **BASE, fee=1.0, scale_out_pct=5)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 9.0, "signal"),
        (5, SELL, 45, 11.55, 527.75, "scale_out"),
        (7, SELL, 45, 10.0, 976.75, "signal"),
        (9, BUY, 81, 12.0, 3.75, "signal"),
    ]
    assert [t.cost for t in r.trades] == [A(1.0)] * 4
    (rt,) = r.round_trips
    assert (rt.outlay, rt.proceeds, rt.pnl) == (A(991.0), A(967.75), A(-23.25))
    assert r.total_costs == A(4.0)
    assert r.final_equity == A(991.95)


def test_slippage_applies_to_the_partial_sale():
    # Slippage 1 %. Bar 4: buy @ 11 * 1.01 = 11.11, int(1000 / 11.11) = 90 (999.90), cash 0.10.
    # Bar 5: level 11.11 * 1.05 = 11.6655 <= high 12; sold @ 11.6655 * 0.99 = 11.548845: 45 * 11.548845 = 519.698025,
    # cash 519.798025. Bar 7: 45 @ 9.90 = 445.50, cash 965.298025.
    # Bar 9: buy @ 12.12, int(965.298025 / 12.12) = 79 (957.48), cash 7.818025; end 7.818025 + 963.80 = 971.618025.
    r = run_backtest(**C, **BASE, slippage_pct=1, scale_out_pct=5)
    assert fills(r) == [
        (4, BUY, 90, 11.11, 0.10, "signal"),
        (5, SELL, 45, 11.548845, 519.798025, "scale_out"),
        (7, SELL, 45, 9.9, 965.298025, "signal"),
        (9, BUY, 79, 12.12, 7.818025, "signal"),
    ]
    assert r.final_equity == A(971.618025)


# Prices near 1 with a fee of 10: the first tries of the partial sale are refused by the fees.
FEE_ROWS = [
    (0.9, 0.9, 0.9, 0.9),  # 0
    (1, 1, 1, 1),          # 1  BUY signal
    (1, 1, 1, 1),          # 2  BUY fills @ 1: int((14 - 10) / 1) = 4 shares, 4 + 10 = 14, cash 0; HOLD
    (1, 1.3, 1, 1),        # 3  level 1.25 <= high 1.3: 2 @ 1.25 = 2.50 - 10 fee: cash -7.50, refused
    (6, 6, 6, 6),          # 4  opens at 6 >= 1.25: 2 @ 6 = 12 - 10 = 2, cash 2; BUY signal (6 > 1)
    (6, 6, 6, 6),          # 5  BUY: int((2 - 10) / 6) -> 0 shares, no fill
]


def test_a_sale_the_fees_refuse_does_not_use_it_up_and_is_tried_again():
    # End 2 + 2 * 6 = 14. Costs 10 + 10 = 20.
    r = run_backtest(**bars(FEE_ROWS), initial_cash=14, fee=10.0, scale_out_pct=25, **BREAKOUT_1)
    assert fills(r) == [(2, BUY, 4, 1.0, 0.0, "signal"), (4, SELL, 2, 6.0, 2.0, "scale_out")]
    assert r.final_position == 2
    assert r.final_equity == A(14.0)


# --- round trips and the losing streak ------------------------------------------------------------------


def test_the_partial_sale_is_not_a_round_trip_and_not_a_streak_step():
    # 9 % alone: one round trip 4 -> 7 with pnl -0.45 (a loss). max_losses 1 halts on bar 7, the bar of the sale
    # that completes the round trip, not bar 5 (the partial sale). The bar 9 buy is dropped; end 999.55.
    r = run_backtest(**C, **BASE, scale_out_pct=9, max_losses=1)
    assert [t.reason for t in r.trades] == ["signal", "scale_out", "signal"]
    assert trips(r) == [(4, 7, 90, -0.45)]
    assert r.loss_halt_bar == 7
    assert r.loss_skipped_buys == 1
    assert r.final_equity == A(999.55)


def test_the_round_trip_is_judged_on_all_its_sales_together():
    # 9 % and stop 5: stop 11 * 0.95 = 10.45. Bar 5: 45 @ 11.99 = 539.55, cash 549.55 (low 10.8 > 10.45).
    # Bar 6: low 9.5: stop 45 @ 10.45 = 470.25, cash 1019.80. The rest alone lost 45 * (10.45 - 11) = -24.75, but
    # the round trip made 539.55 + 470.25 - 990 = +19.80: a win, so max_losses 1 does not halt.
    # Bar 9: int(1019.80 / 12) = 84 (1008), cash 11.80; end 11.80 + 84 * 12.2 = 11.80 + 1024.80 = 1036.60.
    r = run_backtest(**C, **BASE, scale_out_pct=9, stop_pct=5, max_losses=1)
    assert fills(r) == [
        (4, BUY, 90, 11.0, 10.0, "signal"),
        (5, SELL, 45, 11.99, 549.55, "scale_out"),
        (6, SELL, 45, 10.45, 1019.80, "stop"),
        (9, BUY, 84, 12.0, 11.80, "signal"),
    ]
    assert trips(r) == [(4, 6, 90, 19.80)]
    assert r.n_winning_round_trips == 1
    assert r.loss_halt_bar is None
    assert r.final_equity == A(1036.60)


def test_breakeven_after_a_partial_sale_is_still_at_the_entry():
    # 5 % scale-out and 5 % breakeven: bar 5 sells 45 @ 11.55 (cash 529.75) and arms the breakeven stop at 11
    # (the entry is unchanged by the partial sale). Bar 6: low 9.5 <= 11, open 11.5: 45 @ 11 = 495, cash 1024.75;
    # pnl 519.75 + 495 - 990 = +24.75. Bar 9: int(1024.75 / 12) = 85 (1020), cash 4.75;
    # end 4.75 + 85 * 12.2 = 4.75 + 1037 = 1041.75.
    r = run_backtest(**C, **BASE, scale_out_pct=5, breakeven_pct=5)
    assert fills(r)[1:3] == [(5, SELL, 45, 11.55, 529.75, "scale_out"), (6, SELL, 45, 11.0, 1024.75, "breakeven")]
    assert trips(r) == [(4, 6, 90, 24.75)]
    assert r.final_equity == A(1041.75)


def test_it_starts_no_cooldown():
    # Cooldown 4 with a breakeven stop that never arms (50 %): if the bar 5 scale-out started a cooldown it would
    # block bars 6 to 9 and drop the bar 9 buy. It does not: the same fills as the 5 % run.
    r = run_backtest(**C, **BASE, scale_out_pct=5, breakeven_pct=50, cooldown=4)
    assert fills(r) == fills(run_backtest(**C, **BASE, scale_out_pct=5))
    assert r.cooldown_skipped_buys == 0


# --- input checks ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -0.5, math.nan])
def test_scale_out_pct_must_be_positive(bad):
    with pytest.raises(ValueError, match="scale_out_pct must be positive"):
        run_backtest(**C, **BASE, scale_out_pct=bad)


def test_scale_out_needs_highs_and_lows():
    with pytest.raises(ValueError, match="a scale-out needs the high and low of every bar"):
        run_backtest(closes=C["closes"], **BASE, scale_out_pct=5)


def test_the_other_missing_candle_messages_are_unchanged():
    with pytest.raises(ValueError, match="a breakeven stop needs the high and low of every bar"):
        run_backtest(closes=C["closes"], **BASE, breakeven_pct=5, scale_out_pct=5)
    with pytest.raises(ValueError, match="a stop loss or take profit needs the high and low of every bar"):
        run_backtest(closes=C["closes"], **BASE, stop_pct=5, scale_out_pct=5)


# --- the text report and the export ---------------------------------------------------------------------


def test_report_has_the_scale_out_line_and_the_fill_reasons():
    r = run_backtest(**C, **BASE, scale_out_pct=5)
    lines = format_result(r, 1, 2)
    assert lines[3:8] == [
        "  Fills (bar index is 0-based):",
        "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal",
        "    #2   bar 5     SELL       45 @      11.55  value       519.75  cost     0.00  cash       529.75  scale_out",
        "    #3   bar 7     SELL       45 @      10.00  value       450.00  cost     0.00  cash       979.75  signal",
        "    #4   bar 9     BUY        81 @      12.00  value       972.00  cost     0.00  cash         7.75  signal",
    ]
    assert lines[2] == "  Trades:      4 (2 buy, 2 sell)"
    assert (
        "  Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the "
        "average entry; 1 partial sell, not counted as round trips"
    ) in lines
    assert "  Round trips: 1 completed, 0 made money (0%)" in lines
    assert not any(line.startswith("  Exits:") for line in lines)  # no stop or target: no "Exits:" line
    assert lines[-1] == "  Return:      -0.41%"


def test_report_line_sits_after_the_exits_line_and_counts_in_the_plural():
    extended = with_bar(C, 10, 12.0, 12.7, 11.8, 12.2)
    lines = format_result(run_backtest(**extended, **BASE, scale_out_pct=5, stop_pct=10), 1, 2)
    i = next(i for i, line in enumerate(lines) if line.startswith("  Exits:"))
    assert lines[i] == "  Exits:       stop 10.00% below entry"
    assert lines[i + 1].startswith("  Scale out:   ") and lines[i + 1].endswith("; 2 partial sells, not counted as round trips")


def test_report_with_zero_partial_sells():
    lines = format_result(run_backtest(**C, **BASE, scale_out_pct=10), 1, 2)
    assert any(line.endswith("; 0 partial sells, not counted as round trips") for line in lines)


def test_export_has_the_reason_column():
    r = run_backtest(**C, **BASE, scale_out_pct=5)
    assert export_columns(r)[-1] == "reason"
    rows = export_rows(r)
    assert rows[5][4:7] == ["SELL", "45", "11.55"] and rows[5][-1] == "scale_out"
    assert rows[5][10] == "45"  # position after the partial sale
    assert [row[-1] for row in rows] == ["", "", "", "", "signal", "scale_out", "", "signal", "", "signal", ""]


# --- runs without the option are unchanged --------------------------------------------------------------


BEFORE = json.loads((DATA / "before_scale_out.json").read_text())
WALK = candle_kwargs(sample_candles("random_walk"))
INPUTS = {"c": C, "c_closes": {"closes": C["closes"]}, "w": WALK}


def _digest(value):
    """SHA-256 of the value as compact JSON (floats as repr), as the file was recorded."""
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def _record(r, short_data):
    """The parts of a result the recorded file holds, built the way it was recorded (see the module docstring)."""
    fills = [[t.bar, t.side, t.shares, t.price, t.cash_after, t.cost, t.reason] for t in r.trades]
    trips = [[x.entry_bar, x.exit_bar, x.shares, x.outlay, x.proceeds] for x in r.round_trips]
    daily = [[d.cash, d.position, d.equity, d.signal] for d in r.daily]
    report = format_result(r, r.strategy_params.get("short", 1), r.strategy_params.get("long", 2)) + format_stats(r)
    keep = (lambda v: v) if short_data else _digest
    out = {
        "n_fills": len(fills),
        "fills": keep(fills),
        "round_trips": keep(trips),
        "daily": keep(daily),
        "counters": [r.risk_skipped_buys, r.cooldown_skipped_buys, r.min_hold_skipped_sells, r.drawdown_halt_bar,
                     r.drawdown_skipped_buys, r.loss_halt_bar, r.loss_skipped_buys],
        "final": [r.final_cash, r.final_position, r.final_equity, r.total_costs],
        "stats": r.stats if short_data else _digest(r.stats),
        "report": keep(report),
        "export_columns": export_columns(r),
        "export_rows": _digest(export_rows(r)),
    }
    return json.loads(json.dumps(out))  # tuples to lists, as the file has them


def test_the_recorded_file_has_every_case_and_the_same_750_bars():
    assert len(BEFORE["cases"]) == 26
    assert {case["data"] for case in BEFORE["cases"].values()} == {"c", "c_closes", "w"}
    # The 750-bar runs use the built-in random_walk sample; if the sample changes, the recording no longer applies.
    assert _digest(WALK) == BEFORE["inputs_sha256"]["w"]


@pytest.mark.parametrize("name", sorted(BEFORE["cases"]))
@pytest.mark.parametrize("passed", ["left out", "None"])
def test_runs_without_the_option_are_exactly_as_before(name, passed):
    case = BEFORE["cases"][name]
    extra = {} if passed == "left out" else {"scale_out_pct": None}
    result = run_backtest(**INPUTS[case["data"]], **case["base"], **case["settings"], **extra)
    # Exact: the same floats, not just close ones.
    assert _record(result, case["data"] != "w") == case["result"]
    assert result.scale_out_pct is None
    assert "Scale out" not in "\n".join(format_result(result, 1, 2))
