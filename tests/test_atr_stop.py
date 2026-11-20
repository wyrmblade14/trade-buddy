"""The ATR stop in run_backtest (``atr_stop=True`` with ``atr_mult`` and ``atr_period``).

Hand case, 2026-01-01 to 2026-01-08, volume 1000 on every bar, cash 1000,
SMA 1/2 crossover (BUY signal on bar 3, SELL signal on bar 6):

    bar  date        open  high   low  close
     0   2026-01-01  10    10.5   9.5   10
     1   2026-01-02   9.2   9.5   8.5    9
     2   2026-01-03   8.3   8.5   7.5    8
     3   2026-01-04   8.8   9.5   8.5    9     BUY signal
     4   2026-01-05  10.8  11.5  10.5   11     BUY fills @ 11 (close)
     5   2026-01-06  12.2  13    11.2   12
     6   2026-01-07  11.5  12.5   9.8   10     SELL signal
     7   2026-01-08   8.6   9     7.5    8

True ranges: 1, 1.5, 1.5, 1.5, 2.5, 2, 2.7, 2.5
ATR(3) on the signal bar 3 = (4/3 * 2 + 1.5) / 3 = 25/18 ~ 1.3889 (as in test_risk_sizing.py)

atr_mult 2: distance 50/18 ~ 2.7778, level 11 - 50/18 = 74/9 ~ 8.2222.
    Without risk sizing: BUY int(1000 / 11) = 90 @ 11, cash 10.
    Bar 5 low 11.2 and bar 6 low 9.8 stay above 8.2222; bar 7 low 7.5 reaches it
    -> SELL 90 @ 74/9 = 740, cash 750, reason atr. The signal sell due at bar 7's
    close (@ 8, cash 730) is cancelled.
    With the opens: bar 7 opens at 8.6 > 8.2222, no gap -> the same fill at the level.
    With risk_pct 2: 20 / (50/18) = 7.2 -> 7 shares @ 11, cash 923; bar 7 -> SELL 7 @ 74/9
    = 57.5556, cash 980.5556. The loss is 19.44, under the 20 at risk (without the ATR
    stop the same 7 shares sell at 8 and lose 21, see test_risk_sizing.py).
atr_mult 1: distance 25/18, level 11 - 25/18 = 173/18 ~ 9.6111.
    Without the opens: bar 7 low 7.5 -> SELL 90 @ 173/18 = 865, cash 875.
    With the opens: bar 7 opens at 8.6 <= 9.6111 (a gap) -> SELL 90 @ 8.60 = 774, cash 784.
Open fills (atr_mult 2): BUY at bar 4's open 10.8 -> int(1000 / 10.8) = 92, 993.60, cash 6.40;
    level 10.8 - 50/18 ~ 8.0222. Bar 7's open comes first: the signal SELL 92 @ 8.6 = 791.20,
    cash 797.60 (bar 7's low is never checked against the level).
Slippage 1 % (atr_mult 2): BUY @ 11.11 -> 90 shares, cash 0.10; level 11.11 - 50/18 ~ 8.3322;
    bar 7 -> SELL @ 8.3322 * 0.99.
atr_period 5: the first ATR(5) is on bar 4, after the signal bar 3 -> the buy is skipped and
    counted in risk_skipped_buys; the SELL signal then has nothing to sell.

Levels next to the ATR stop (atr_mult 2, level 8.2222, all reached on bar 7):
    stop 20 %  -> 8.80  > 8.2222 -> stop @ 8.80, cash 802
    stop 30 %  -> 7.70  < 8.2222 -> atr @ 8.2222, cash 750
    trail 30 % -> 13 * 0.7 = 9.10 (bar 5's high 13) > 8.2222 -> trail @ 9.10, cash 829
    trail 40 % -> 13 * 0.6 = 7.80 < 8.2222 -> atr, cash 750
    target 15 % -> 12.65, reached by bar 5's high 13 before any stop -> target @ 12.65, cash 1148.50
Ties, with atr_period 1 (ATR(1) on bar 3 = its true range 1.5):
    atr_mult 1.1 -> level 11 - 1.65 = 9.35 = 11 * 0.85, the 15 % stop: bar 7 -> stop (stop first)
    atr_mult 0.4 -> level 11 - 0.6 = 10.4 = 13 * 0.8, the 20 % trail on bar 6: low 9.8 -> trail
"""

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.signals import BUY, SELL

OPENS = [10, 9.2, 8.3, 8.8, 10.8, 12.2, 11.5, 8.6]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13, 12.5, 9]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 9.8, 7.5]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]

A = pytest.approx
LEVEL_2 = 11 - 2 * 25 / 18  # 74/9 ~ 8.2222
LEVEL_1 = 11 - 25 / 18  # 173/18 ~ 9.6111
ENTRY = (4, BUY, 90, 11.0, 10.0, "signal")


def run(**kwargs):
    base = dict(initial_cash=1000, short=1, long=2, highs=HIGHS, lows=LOWS)
    base.update(kwargs)
    return run_backtest(CLOSES, **base)


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), A(t.cash_after), t.reason) for t in result.trades]


# --------------------------------------------------------------------------- hand case, without risk_pct


def test_hand_case_sells_at_the_atr_level():
    r = run(atr_stop=True, atr_mult=2, atr_period=3)
    assert fills(r) == [ENTRY, (7, SELL, 90, LEVEL_2, 750.0, "atr")]
    assert LEVEL_2 == A(74 / 9)
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.shares) == (4, 7, 90)
    assert rt.outlay == A(990.0) and rt.proceeds == A(740.0)
    assert r.final_cash == A(750.0) and r.final_position == 0
    assert r.risk_skipped_buys == 0


def test_hand_case_without_the_atr_stop_sells_on_the_signal():
    r = run(atr_mult=2, atr_period=3)
    assert fills(r) == [ENTRY, (7, SELL, 90, 8.0, 730.0, "signal")]


def test_the_atr_stop_cancels_that_bars_signal_sell():
    r = run(atr_stop=True, atr_mult=2, atr_period=3)
    assert r.daily[6].signal == SELL
    assert len(r.trades) == 2 and r.daily[7].trade is r.trades[1] and r.trades[1].reason == "atr"


def test_uses_the_signal_bar_atr_not_the_fill_bar_atr():
    # Blow up the fill bar's (bar 4) range: its ATR would change a lot, but the distance only looks at bar 3.
    highs, lows = list(HIGHS), list(LOWS)
    highs[4], lows[4] = 60.0, 1.0
    r = run(atr_stop=True, atr_mult=2, atr_period=3, highs=highs, lows=lows)
    assert fills(r) == [ENTRY, (7, SELL, 90, LEVEL_2, 750.0, "atr")]


def test_the_level_is_fixed_per_trade_although_the_atr_keeps_moving():
    # ATR(3) rises after bar 3 (1.76, 1.84, 2.13 on bars 4-6). A level worked out from bar 6's
    # ATR would be 11 - 2 * 2.126 = 6.75 and bar 7 (low 7.5) would not sell.
    r = run(atr_stop=True, atr_mult=2, atr_period=3)
    assert r.trades[1].price == A(LEVEL_2)


def test_touch_without_a_gap_fills_at_the_level_with_opens():
    r = run(atr_stop=True, atr_mult=2, atr_period=3, opens=OPENS)
    assert fills(r) == [ENTRY, (7, SELL, 90, LEVEL_2, 750.0, "atr")]


def test_gap_below_the_level_fills_at_the_open():
    assert fills(run(atr_stop=True, atr_mult=1, atr_period=3)) == [ENTRY, (7, SELL, 90, LEVEL_1, 875.0, "atr")]
    r = run(atr_stop=True, atr_mult=1, atr_period=3, opens=OPENS)
    assert fills(r) == [ENTRY, (7, SELL, 90, 8.6, 784.0, "atr")]


def test_open_fills_the_signal_sell_at_the_open_comes_first():
    r = run(atr_stop=True, atr_mult=2, atr_period=3, fill="open", opens=OPENS)
    assert fills(r) == [(4, BUY, 92, 10.8, 6.4, "signal"), (7, SELL, 92, 8.6, 797.6, "signal")]


def test_the_level_is_measured_from_the_price_paid_including_slippage():
    r = run(atr_stop=True, atr_mult=2, atr_period=3, slippage_pct=1)
    buy, sell = r.trades
    assert (buy.shares, buy.price, buy.cash_after) == (90, A(11.11), A(0.1))
    assert sell.reason == "atr" and sell.bar == 7
    assert sell.price == A((11.11 - 50 / 18) * 0.99)


def test_exit_is_not_checked_on_the_entry_bar():
    lows = list(LOWS)
    lows[4] = 1.0  # the buy is at bar 4's close, so bar 4's range is ignored
    r = run(atr_stop=True, atr_mult=2, atr_period=3, lows=lows)
    assert [(t.bar, t.reason) for t in r.trades] == [(4, "signal"), (7, "atr")]


# --------------------------------------------------------------------------- hand case, with risk_pct


def test_with_risk_pct_sizes_and_stops_at_the_same_distance():
    r = run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=3)
    assert fills(r) == [(4, BUY, 7, 11.0, 923.0, "signal"), (7, SELL, 7, LEVEL_2, 923 + 7 * 74 / 9, "atr")]
    (rt,) = r.round_trips
    assert -rt.pnl == A(7 * 50 / 18)  # 19.44 lost: the 7 shares times the distance
    assert -rt.pnl <= 20  # within the 2 % of 1000 at risk (no gap, slippage or fees here)


def test_risk_pct_alone_still_places_no_stop():
    r = run(risk_pct=2, atr_mult=2, atr_period=3)
    assert fills(r) == [(4, BUY, 7, 11.0, 923.0, "signal"), (7, SELL, 7, 8.0, 979.0, "signal")]


# --------------------------------------------------------------------------- no usable ATR: skipped and counted


def test_buy_signal_before_the_atr_exists_is_skipped_and_counted():
    r = run(atr_stop=True, atr_mult=2, atr_period=5)
    assert r.daily[3].signal == BUY
    assert r.trades == [] and r.final_cash == 1000 and r.final_position == 0
    assert r.risk_skipped_buys == 1


def test_with_risk_pct_a_skipped_buy_is_counted_once():
    r = run(risk_pct=2, atr_stop=True, atr_mult=2, atr_period=5)
    assert r.trades == [] and r.risk_skipped_buys == 1


def test_zero_atr_on_the_signal_bar_is_skipped_and_counted():
    # atr_period 1: the ATR is that bar's true range. Bar 3 is flat (high = low = close =
    # previous close = 9), so its ATR is 0; SMA 1/3 gives BUY there.
    closes = [12, 8, 9, 9, 10]
    r = run_backtest(closes, 1000, short=1, long=3, highs=closes, lows=closes, atr_stop=True, atr_period=1)
    assert r.daily[3].signal == BUY
    assert r.trades == [] and r.risk_skipped_buys == 1


def test_later_buy_once_the_atr_exists_is_bought_and_stopped():
    # Two more bars (as in test_risk_sizing.py): the bar 3 BUY is skipped (no ATR(5) yet),
    # the bar 8 BUY fills on bar 9 @ 11 with ATR(5) on bar 8 = 1.90576.
    r = run_backtest(
        CLOSES + [9, 11], 1000, short=1, long=2, highs=HIGHS + [9.5, 11.5], lows=LOWS + [8, 10.5],
        atr_stop=True, atr_mult=2, atr_period=5,
    )
    assert r.risk_skipped_buys == 1
    assert fills(r) == [(9, BUY, 90, 11.0, 10.0, "signal")]


# --------------------------------------------------------------------------- next to the other exits


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(stop_pct=20), (7, SELL, 90, 8.8, 802.0, "stop")),
        (dict(stop_pct=30), (7, SELL, 90, LEVEL_2, 750.0, "atr")),
        (dict(trail_pct=30), (7, SELL, 90, 9.1, 829.0, "trail")),
        (dict(trail_pct=40), (7, SELL, 90, LEVEL_2, 750.0, "atr")),
        (dict(stop_pct=30, trail_pct=40), (7, SELL, 90, LEVEL_2, 750.0, "atr")),
        (dict(take_profit_pct=15), (5, SELL, 90, 12.65, 1148.5, "target")),
    ],
    ids=["stop higher", "atr above stop", "trail higher", "atr above trail", "atr above both", "target first"],
)
def test_the_highest_stop_level_is_used(kwargs, expected):
    r = run(atr_stop=True, atr_mult=2, atr_period=3, **kwargs)
    assert fills(r) == [ENTRY, expected]


def test_tie_with_the_stop_is_a_stop():
    assert 11 - 1.1 * 1.5 == 11 * (1 - 15 / 100.0)  # really the same level
    r = run(atr_stop=True, atr_mult=1.1, atr_period=1, stop_pct=15)
    assert fills(r) == [ENTRY, (7, SELL, 90, 9.35, 10 + 90 * 9.35, "stop")]


def test_tie_with_the_trail_is_a_trail():
    assert 11 - 0.4 * 1.5 == 13 * (1 - 20 / 100.0)  # really the same level on bar 6
    r = run(atr_stop=True, atr_mult=0.4, atr_period=1, trail_pct=20)
    assert fills(r) == [ENTRY, (6, SELL, 90, 10.4, 10 + 90 * 10.4, "trail")]


def test_bar_touching_the_atr_level_and_the_target_is_an_atr_stop():
    # atr_mult 1: level 9.6111; target 15 %: 12.65. Bar 5 lowered to 9.5 touches both (high 13).
    lows = list(LOWS)
    lows[5] = 9.5
    r = run(atr_stop=True, atr_mult=1, atr_period=3, take_profit_pct=15, lows=lows)
    assert fills(r) == [ENTRY, (5, SELL, 90, LEVEL_1, 875.0, "atr")]


# --------------------------------------------------------------------------- a later buy into the same position
#
# Cash 1200, breakout window 1 (BUY when the close is above the previous close, SELL
# when below), position_size 0.5, atr_mult 1, atr_period 1 (the ATR is the bar's true range):
#
#     bar  high   low  close  TR   signal
#      0   10.5   9.5  10     1
#      1   11.5  10.5  11     1.5  BUY
#      2   14    11    12     3    BUY   BUY fills @ 12: 600 / 12 = 50 shares, cash 600.
#                                        Distance = ATR of bar 1 = 1.5, kept for the position.
#      3   15.5  13    15     3.5  BUY   level 12 - 1.5 = 10.5, low 13 -> hold.
#                                        BUY fills @ 15: budget 0.5 * (600 + 50 * 15) = 675,
#                                        capped by the cash 600 -> 40 shares, cash 0.
#                                        90 shares, average entry 1200 / 90 = 13.3333.
#      4   14.5  11.5  12     3.5  SELL  level 13.3333 - 1.5 = 11.8333; low 11.5 reaches it
#                                        -> SELL 90 @ 11.8333 = 1065, cash 1065, reason atr.
#      5   12.5  11.8  12
#
# Other readings would hold on bar 4: a level fixed at the first entry (12 - 1.5 = 10.5),
# or a distance from the second buy's signal bar (13.3333 - 3 = 10.3333).

ADD_CLOSES = [10, 11, 12, 15, 12, 12]
ADD_HIGHS = [10.5, 11.5, 14, 15.5, 14.5, 12.5]
ADD_LOWS = [9.5, 10.5, 11, 13, 11.5, 11.8]
ADD = dict(
    initial_cash=1200, strategy="breakout", strategy_params={"window": 1}, position_size=0.5,
    highs=ADD_HIGHS, lows=ADD_LOWS, atr_mult=1, atr_period=1,
)


def test_later_buy_keeps_the_first_distance_from_the_new_average_entry():
    r = run_backtest(ADD_CLOSES, atr_stop=True, **ADD)
    assert [d.signal for d in r.daily][1:5] == [BUY, BUY, BUY, SELL]
    assert fills(r) == [
        (2, BUY, 50, 12.0, 600.0, "signal"),
        (3, BUY, 40, 15.0, 0.0, "signal"),
        (4, SELL, 90, 1200 / 90 - 1.5, 1065.0, "atr"),
    ]
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.shares) == (2, 4, 90)
    assert rt.outlay == A(1200.0) and rt.proceeds == A(1065.0)
    assert r.risk_skipped_buys == 0


def test_later_buy_without_the_atr_stop_holds_to_the_signal():
    r = run_backtest(ADD_CLOSES, **ADD)
    assert fills(r)[-1] == (5, SELL, 90, 12.0, 1080.0, "signal")


# --------------------------------------------------------------------------- errors and unchanged runs


def test_atr_stop_needs_highs_and_lows():
    for kwargs in (dict(highs=None), dict(lows=None), dict(highs=None, lows=None)):
        with pytest.raises(ValueError) as excinfo:
            run(atr_stop=True, atr_period=3, **kwargs)
        assert str(excinfo.value) == "an ATR stop needs the high and low of every bar"


def test_atr_stop_with_a_trailing_stop_keeps_the_trailing_message():
    with pytest.raises(ValueError) as excinfo:
        run(atr_stop=True, trail_pct=10, highs=None, lows=None)
    assert str(excinfo.value) == "a trailing stop needs the high and low of every bar"


def test_atr_stop_highs_lows_wrong_length():
    with pytest.raises(ValueError) as excinfo:
        run(atr_stop=True, highs=HIGHS[:-1])
    assert str(excinfo.value) == "7 highs and 8 lows but 8 closes"


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_atr_stop_must_be_true_or_false(value):
    with pytest.raises(ValueError, match="atr_stop must be True or False"):
        run(atr_stop=value, atr_period=3)


@pytest.mark.parametrize("kwargs", [dict(atr_mult=0), dict(atr_mult=-1), dict(atr_period=0), dict(atr_period=1.5)])
def test_bad_atr_settings_raise_with_the_atr_stop(kwargs):
    with pytest.raises(ValueError, match="atr_mult|atr_period"):
        run(atr_stop=True, **kwargs)


def test_the_atr_is_only_worked_out_when_the_atr_stop_or_risk_sizing_is_on():
    # A high below its low: the exits alone never check candle shape, but the ATR does.
    lows = list(LOWS)
    lows[2] = 9.0  # above bar 2's high of 8.5
    run(stop_pct=10, trail_pct=10, take_profit_pct=20, lows=lows)  # no error
    with pytest.raises(ValueError, match="high 8.5 is below low 9.0 at index 2"):
        run(atr_stop=True, lows=lows)


def test_atr_stop_false_changes_nothing():
    for kwargs in (dict(), dict(stop_pct=10, trail_pct=8, take_profit_pct=20, opens=OPENS), dict(risk_pct=2, atr_period=3)):
        assert run(atr_stop=False, **kwargs) == run(**kwargs)


# --------------------------------------------------------------------------- with risk_pct: a later buy can lose more than the risk
#
# What the docs say for both options: the buy that opens a position is sized on the distance the stop
# sells at, but a later buy is sized on its own signal bar's ATR while the stop keeps the first distance,
# so the position can lose more than the risks added up even with no gap, slippage or fee.
#
# Cash 10000, breakout window 1, risk 2 %, atr_mult 1, atr_period 1 (the ATR is the bar's true range):
#
#     bar  open  high   low  close  TR    signal
#      0   10    10.5   9.5  10     1
#      1   10.5  13    10    11     3     BUY  (distance 3 for the buy that opens the position)
#      2   11.5  12.2  11.2  12     1.2   BUY  BUY fills @ 12: risk 200 / 3 = 66 shares, cash 9208; level 12 - 3 = 9
#      3   12    12.3  11.7  12                BUY fills @ 12: risk 2 % of 10000 = 200 / 1.2 = 166 shares (its own
#                                              signal bar's ATR), cash 7216; 232 shares, average 12, level still 12 - 3 = 9
#      4   10    10.2   8.9   9.5              opens at 10 (above 9, no gap), low 8.9 -> SELL 232 @ 9.00, reason atr
#
# Loss 232 x 3 = 696 = 6.96 % of the account, against 200 + 200 = 400 at risk (2 % per buy).

LATER_CLOSES = [10, 11, 12, 12, 9.5]
LATER_OPENS = [10, 10.5, 11.5, 12, 10]
LATER_HIGHS = [10.5, 13, 12.2, 12.3, 10.2]
LATER_LOWS = [9.5, 10, 11.2, 11.7, 8.9]


def test_with_risk_pct_a_later_buy_can_lose_more_than_the_risk_without_a_gap():
    r = run_backtest(
        LATER_CLOSES, 10000, strategy="breakout", strategy_params={"window": 1}, opens=LATER_OPENS,
        highs=LATER_HIGHS, lows=LATER_LOWS, risk_pct=2, atr_stop=True, atr_mult=1, atr_period=1,
    )
    assert fills(r) == [
        (2, BUY, 66, 12.0, 9208.0, "signal"),
        (3, BUY, 166, 12.0, 7216.0, "signal"),
        (4, SELL, 232, 9.0, 9304.0, "atr"),
    ]
    assert LATER_OPENS[4] > 9.0  # no gap: the bar opened above the level
    (rt,) = r.round_trips
    assert -rt.pnl == A(696.0)
    assert -rt.pnl > 200 + 200  # more than the 2 % risked on each of the two buys
