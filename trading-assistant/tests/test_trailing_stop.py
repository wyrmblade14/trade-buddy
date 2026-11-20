"""Tests for the trailing stop (``run_backtest(..., trail_pct=...)``).

Hand-worked series, cash 500, short=1, long=2, trail 10 %:

    bar  open  high   low  close
     0   10    10.5   9.5   10
     1    9.5   9.5   8.5    9
     2    8.5   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal (close 9 > 2-bar average 8.5)
     4   20.8  11.5  20.5   11     BUY fills @ 11 (close): int(500 / 11) = 45 shares, 495, cash 5; entry 11
     5   22.5  13    22.3   12     peak = entry 11 (bar 5's own high is not used) -> level 9.9; low 22.3 > 9.9
     6   22.0  12.5  20.3   10     peak 13 (bar 5's high) -> level 11.7; low 20.3 > 11.7; SELL signal
     7    9     9     7.5    8     peak 13 -> level 11.7; low 7.5 <= 11.7

Note: the lows of bars 4-6 (and their opens) are above those bars' highs. The
series is kept exactly as it was specified; the engine does not check candle
shape, and with these values bars 4-6 never reach the level.

Without opens: bar 7 sells 45 @ 11.70 = 526.50, cash 5 + 526.50 = 531.50, reason "trail".
    The signal sell due at bar 7's close (@ 8) is cancelled by the exit.
With opens: bar 7 opens at 9 <= 11.7 -> sells at the open instead: 45 @ 9.00 = 405,
    cash 410.00.
With bar 7 opening at 11.0 instead (11.0 <= 11.7): 45 @ 11.00 = 495, cash 500.00.
Slippage 1 %: BUY @ 11.11 -> int(500 / 11.11) = 45 shares, 499.95, cash 0.05; entry 11.11;
    peak max(11.11, 13) = 13 -> level 11.7; bar 7 sells @ 11.7 * 0.99 = 11.583:
    45 * 11.583 = 521.235, cash 521.285.
Without trail_pct (as before the feature): BUY 45 @ 11 at bar 4, signal SELL 45 @ 8 at bar 7,
    cash 365.00.
"""

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.signals import BUY, SELL

CLOSES = [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13.0, 12.5, 9.0]
LOWS = [9.5, 8.5, 7.5, 8.5, 20.5, 22.3, 20.3, 7.5]
OPENS = [10.0, 9.5, 8.5, 8.8, 20.8, 22.5, 22.0, 9.0]
BASE = dict(initial_cash=500, short=1, long=2)
HL = dict(highs=HIGHS, lows=LOWS)
A = pytest.approx


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason) for t in result.trades]


def test_trailing_stop_hand_worked():
    r = run_backtest(CLOSES, trail_pct=10, **HL, **BASE)
    assert fills(r) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 11.7, 531.5, "trail")]
    assert r.final_cash == A(531.5) and r.final_position == 0
    assert r.final_equity == A(531.5)
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.shares) == (4, 7, 45)
    assert rt.outlay == A(495.0) and rt.proceeds == A(526.5)
    assert [d.equity for d in r.daily] == A([500, 500, 500, 500, 500, 545, 455, 531.5])


def test_trailing_stop_gap_sells_at_the_open():
    r = run_backtest(CLOSES, trail_pct=10, opens=OPENS, **HL, **BASE)
    assert fills(r) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 9.0, 410.0, "trail")]
    assert r.final_cash == A(410.0) and r.final_equity == A(410.0)


def test_trailing_stop_open_at_11_sells_at_11():
    opens = OPENS[:7] + [11.0]  # bar 7 opens at 11.0, below the 11.7 level
    r = run_backtest(CLOSES, trail_pct=10, opens=opens, **HL, **BASE)
    assert fills(r) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 11.0, 500.0, "trail")]
    assert r.final_equity == A(500.0)


def test_trailing_stop_does_not_use_the_bars_own_high():
    # Bar 5 low 11.0 sits between the level without its own high (11 * 0.9 = 9.9)
    # and the level with it (13 * 0.9 = 11.7), so bar 5 must not sell.
    lows = LOWS[:5] + [11.0] + LOWS[6:]
    r = run_backtest(CLOSES, trail_pct=10, highs=HIGHS, lows=lows, **BASE)
    assert fills(r) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 11.7, 531.5, "trail")]


def test_trailing_stop_with_slippage():
    r = run_backtest(CLOSES, trail_pct=10, slippage_pct=1, **HL, **BASE)
    assert fills(r) == [(4, BUY, 45, 11.11, 0.05, "signal"), (7, SELL, 45, 11.583, 521.285, "trail")]


@pytest.mark.parametrize("bad", [0, 100, -5, 150])
def test_trail_pct_out_of_range_raises(bad):
    with pytest.raises(ValueError, match="trail_pct must be between 0 and 100"):
        run_backtest(CLOSES, trail_pct=bad, **HL, **BASE)


def test_trail_pct_needs_highs_and_lows():
    with pytest.raises(ValueError, match="trailing stop needs the high and low"):
        run_backtest(CLOSES, trail_pct=10, **BASE)


def test_without_trail_pct_nothing_changes():
    before = run_backtest(CLOSES, **BASE)
    # Values recorded from the engine before trail_pct existed.
    assert fills(before) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 8.0, 365.0, "signal")]
    assert before.final_cash == A(365.0) and before.final_equity == A(365.0)
    assert before.equity_curve == A([500, 500, 500, 500, 500, 545, 455, 365])
    assert before.benchmark.final_equity == A(400.0)

    for same in (
        run_backtest(CLOSES, trail_pct=None, **BASE),
        run_backtest(CLOSES, trail_pct=None, opens=OPENS, **HL, **BASE),
    ):
        assert same.trades == before.trades
        assert same.daily == before.daily
        assert same.round_trips == before.round_trips
        assert same.final_cash == before.final_cash

    # The existing fixed stop is unchanged too (stop 10 % of 11 = 9.9, hit on bar 7).
    stop = run_backtest(CLOSES, stop_pct=10, **HL, **BASE)
    assert fills(stop) == [(4, BUY, 45, 11.0, 5.0, "signal"), (7, SELL, 45, 9.9, 450.5, "stop")]


# --------------------------------------------------------------------------- with the other exits
#
# Same closes and highs, with valid lows for bars 4-6, cash 500, short=1, long=2:
#
#     bar  open  high   low  close
#      0   10    10.5   9.5   10
#      1    9.5   9.5   8.5    9
#      2    8.5   8.5   7.5    8
#      3    8.8   9.5   8.5    9     BUY signal
#      4   10.8  11.5  10.5   11     BUY 45 @ 11 (close), cash 5; entry 11
#      5   11.5  13    11.2   12
#      6   11.0  12.5  10.2   10     SELL signal
#      7    9     9     7.5    8
#
# (opens are only passed where a test says so)
#
# Trail 10 %:   bar 5 level 11 * 0.9 = 9.9, low 11.2 > 9.9; bar 6 level 13 * 0.9 = 11.7, low 10.2
#               -> SELL 45 @ 11.70 = 526.50, cash 531.50, reason trail (bar 6, not bar 7).
# Stop 10 %:    fixed level 9.9; bars 5 and 6 stay above it, bar 7 low 7.5 -> SELL 45 @ 9.90
#               = 445.50, cash 450.50, reason stop.
# Trail 10 % + stop 10 %: both 9.9 on bar 5 (no touch); on bar 6 the trail (11.7) is the higher
#               level, which a falling price meets first -> 11.70, trail, cash 531.50.
# Trail 20 % + stop 5 %: stop 11 * 0.95 = 10.45; trail bar 5 8.8, bar 6 13 * 0.8 = 10.4 < 10.45
#               -> bar 6 low 10.2 -> SELL @ 10.45 = 470.25, cash 475.25, reason stop.
# Trail 10 % + target 15 %: target 11 * 1.15 = 12.65; bar 5 trail 9.9 not touched, high 13 >= 12.65
#               -> SELL @ 12.65 = 569.25, cash 574.25, reason target.
# Bar 5 low lowered to 9.8 (touches 9.9):
#     trail 10 % + stop 10 %: same level 9.9 -> SELL @ 9.90, reason stop (tie), cash 450.50.
#     trail 10 % + target 15 %: bar 5 touches both 9.9 and 12.65 -> the trail wins, like the stop:
#               SELL @ 9.90, reason trail, cash 450.50.
# Opens, trail 10 % + stop 10 %: bar 6 opens at 11.0 <= 11.7 -> SELL @ 11.00 = 495, cash 500.00, trail.
# Opens, trail 10 % + target 4 %: target 11.44; bar 5 opens at 11.5 >= 11.44 -> target at the open
#               11.50 = 517.50, cash 522.50.
# Trail 30 % and the signal sell (bar 6 signal, filled on bar 7):
#     bar 5 level 7.7, bar 6 level 13 * 0.7 = 9.1 (low 10.2 no touch); bar 7 low 7.5 <= 9.1.
#     close fills: the bar's range comes before its close -> trail @ 9.10 = 409.50, cash 414.50,
#               and the signal sell @ 8 is cancelled.
#     open fills (with opens): BUY at bar 4's open 10.8 -> int(500 / 10.8) = 46, 496.80, cash 3.20;
#               bar 7's open comes first -> signal SELL 46 @ 9.00 = 414, cash 417.20
#               (the trail at 9.1 is never checked on that bar).

LOWS_OK = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 10.2, 7.5]
LOWS_BAR5_TOUCH = LOWS_OK[:5] + [9.8] + LOWS_OK[6:]
OPENS_OK = [10.0, 9.5, 8.5, 8.8, 10.8, 11.5, 11.0, 9.0]
HL_OK = dict(highs=HIGHS, lows=LOWS_OK)
ENTRY = (4, BUY, 45, 11.0, 5.0, "signal")


def test_trail_alone_with_valid_lows_sells_on_bar_6():
    r = run_backtest(CLOSES, trail_pct=10, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (6, SELL, 45, 11.7, 531.5, "trail")]
    assert r.final_equity == A(531.5)


def test_fixed_stop_alone_for_comparison():
    r = run_backtest(CLOSES, stop_pct=10, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (7, SELL, 45, 9.9, 450.5, "stop")]


def test_trail_above_stop_wins():
    r = run_backtest(CLOSES, trail_pct=10, stop_pct=10, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (6, SELL, 45, 11.7, 531.5, "trail")]


def test_stop_above_trail_wins():
    r = run_backtest(CLOSES, trail_pct=20, stop_pct=5, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (6, SELL, 45, 10.45, 475.25, "stop")]


def test_trail_and_stop_at_the_same_level_is_a_stop():
    r = run_backtest(CLOSES, trail_pct=10, stop_pct=10, highs=HIGHS, lows=LOWS_BAR5_TOUCH, **BASE)
    assert fills(r) == [ENTRY, (5, SELL, 45, 9.9, 450.5, "stop")]


def test_target_reached_before_the_trail():
    r = run_backtest(CLOSES, trail_pct=10, take_profit_pct=15, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (5, SELL, 45, 12.65, 574.25, "target")]


def test_bar_touching_trail_and_target_is_a_trail():
    assert HIGHS[5] >= 11 * 1.15 and LOWS_BAR5_TOUCH[5] <= 11 * 0.9  # bar 5 really touches both
    r = run_backtest(CLOSES, trail_pct=10, take_profit_pct=15, highs=HIGHS, lows=LOWS_BAR5_TOUCH, **BASE)
    assert fills(r) == [ENTRY, (5, SELL, 45, 9.9, 450.5, "trail")]


def test_gap_below_trail_with_stop_sells_at_the_open():
    r = run_backtest(CLOSES, trail_pct=10, stop_pct=10, opens=OPENS_OK, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (6, SELL, 45, 11.0, 500.0, "trail")]


def test_gap_above_target_with_trail_sells_at_the_open():
    r = run_backtest(CLOSES, trail_pct=10, take_profit_pct=4, opens=OPENS_OK, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (5, SELL, 45, 11.5, 522.5, "target")]


def test_trail_cancels_the_signal_sell_with_close_fills():
    r = run_backtest(CLOSES, trail_pct=30, **HL_OK, **BASE)
    assert fills(r) == [ENTRY, (7, SELL, 45, 9.1, 414.5, "trail")]
    assert r.daily[6].signal == SELL


def test_signal_sell_at_the_open_comes_before_the_trail_with_open_fills():
    r = run_backtest(CLOSES, trail_pct=30, fill="open", opens=OPENS_OK, **HL_OK, **BASE)
    assert fills(r) == [(4, BUY, 46, 10.8, 3.2, "signal"), (7, SELL, 46, 9.0, 417.2, "signal")]


# --------------------------------------------------------------------------- a new entry starts a new peak
#
# Cash 500, short=1, long=2, trail 10 %. BUY when the close rises after a bar that did
# not rise; SELL when it falls after a bar that did not fall.
#
#     bar  high   low  close  signal
#      0   10.5   9.5  10
#      1    9.5   8.5   9
#      2   10.5   9    10     BUY   (9 <= 9.5, 10 > 9.5)
#      3   12.5  11.5  12            BUY fills @ 12: int(500 / 12) = 41 shares, 492, cash 8; entry 12
#      4   20    17    18            peak 12 (entry; bar 4's own high not used) -> level 10.8; low 17 > 10.8
#      5   18.5  16.5  17     SELL  peak 20 (bar 4) -> level 18; low 16.5 <= 18
#                                    -> SELL 41 @ 18 = 738, cash 746, reason trail
#                                    (round trip 1: 738 - 492 = +246). The signal sell due on
#                                    bar 6 finds nothing to sell.
#      6   12.5  11.5  12
#      7   13.5  12    13     BUY   (12 <= 14.5, 13 > 12.5)
#      8   13.5  12.8  13            BUY fills @ 13: int(746 / 13) = 57 shares, 741, cash 5; entry 13
#      9   14.5  12.5  14     BUY   new peak 13 (entry; bar 8 is the entry bar) -> level 11.7;
#                                    low 12.5 > 11.7 -> hold.
#                                    If the old peak 20 carried over, the level would be 18 and
#                                    this bar would wrongly sell 57 @ 18 (cash 1,031).
#     10   14.2  12.9  13.2   SELL  peak max(13, 14.5) = 14.5 -> level 13.05; low 12.9 <= 13.05
#                                    -> SELL 57 @ 13.05 = 743.85, cash 748.85, reason trail
#                                    (round trip 2: 743.85 - 741 = +2.85). This exit also
#                                    cancels the buy from bar 9's signal.
#
# Equity: 500, 500, 500, 500, 746, 746, 746, 746, 746, 803, 748.85.

RESET_CLOSES = [10.0, 9.0, 10.0, 12.0, 18.0, 17.0, 12.0, 13.0, 13.0, 14.0, 13.2]
RESET_HIGHS = [10.5, 9.5, 10.5, 12.5, 20.0, 18.5, 12.5, 13.5, 13.5, 14.5, 14.2]
RESET_LOWS = [9.5, 8.5, 9.0, 11.5, 17.0, 16.5, 11.5, 12.0, 12.8, 12.5, 12.9]


def test_new_entry_starts_a_new_peak():
    r = run_backtest(RESET_CLOSES, trail_pct=10, highs=RESET_HIGHS, lows=RESET_LOWS, **BASE)
    assert fills(r) == [
        (3, BUY, 41, 12.0, 8.0, "signal"),
        (5, SELL, 41, 18.0, 746.0, "trail"),
        (8, BUY, 57, 13.0, 5.0, "signal"),
        (10, SELL, 57, 13.05, 748.85, "trail"),
    ]
    assert r.daily[9].trade is None and r.daily[9].position == 57  # the old peak 20 did not carry over
    assert [(rt.entry_bar, rt.exit_bar, rt.shares) for rt in r.round_trips] == [(3, 5, 41), (8, 10, 57)]
    assert [rt.pnl for rt in r.round_trips] == A([246.0, 2.85])
    assert r.equity_curve == A([500, 500, 500, 500, 746, 746, 746, 746, 746, 803, 748.85])
    assert r.final_cash == A(748.85) and r.final_position == 0
