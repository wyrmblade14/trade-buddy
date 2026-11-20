"""The cooldown in run_backtest (``cooldown=N``): no buy fills for N bars after a stop exit.

After a ``stop``, ``trail`` or ``atr`` exit on bar t, no buy can fill on bars
t + 1 .. t + N. A buy due then is dropped (not delayed) and counted in
``cooldown_skipped_buys``, even one that would have got 0 shares anyway. A
``target`` or ``signal`` sell starts no cooldown. ``cooldown=0`` (the default)
is off.

Hand case, cash 1000, SMA 1/2 crossover (BUY signals on bars 3 and 8, SELL on bar 6):

    bar  open  high   low   close
     0   10    10.5   9.5   10
     1    9.2   9.5   8.5    9
     2    8.3   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal
     4   10.8  11.5  10.5   11     BUY fills @ 11 (close): 90 shares, cash 10
     5   11    12    10.8   12
     6   11.5  12     9.5   10     stop 10 %: level 9.90, low 9.5 -> SELL 90 @ 9.90, cash 901
     7    9.8  10.2   9.6   10
     8   10    11.5   9.9   11     BUY signal
     9   10.8  12.5  10.5   12     BUY fills @ 12: 75 shares, cash 1
    10   12    12.4  11.8   12.2   end equity 1 + 75 x 12.2 = 916

cooldown 3: the stop on bar 6 blocks bars 7, 8, 9 -> the bar 9 buy is skipped, end 901.
cooldown 2: blocks bars 7, 8 only -> the bar 9 buy fills, end 916.

No cooldown from other sells:
    take profit 5 % (target 11.55, bar 5 high 12) -> SELL 90 @ 11.55 on bar 5, cash 1049.50;
        a cooldown of 4 would block bars 6..9; instead bar 9 buys 87 @ 12 -> end 1066.90.
    signal sell (stop 50 %, level 5.50, never reached) -> SELL 90 @ 10 on bar 7, cash 910;
        a cooldown of 3 would block bars 8..10; instead bar 9 buys 75 @ 12 -> end 925.

Other stops start it too:
    trail 10 %: peak 12 (bar 5 high) -> level 10.80; bar 6 -> SELL 90 @ 10.80, cash 982;
        no cooldown: bar 9 buys 81 @ 12 -> end 998.20; cooldown 3 -> end 982.
    ATR stop, atr_mult 1, atr_period 1: ATR(1) on bar 3 = 1.5 -> level 9.50;
        bar 6 -> SELL 90 @ 9.50, cash 865; no cooldown: bar 9 buys 72 @ 12 -> end 879.40;
        cooldown 3 -> end 865.
Open fills, stop 10 %: BUY 92 @ 10.8 (bar 4 open), cash 6.40, level 9.72; bar 6 -> SELL 92 @ 9.72,
    cash 900.64; no cooldown: bar 9 buys 83 @ 10.8 (its open) -> end 1016.84; cooldown 3 -> 900.64.
"""

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.samples import sample_candles
from trading_assistant.signals import BUY, SELL

OPENS = [10, 9.2, 8.3, 8.8, 10.8, 11, 11.5, 9.8, 10, 10.8, 12]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 12, 12, 10.2, 11.5, 12.5, 12.4]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 10.8, 9.5, 9.6, 9.9, 10.5, 11.8]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]

A = pytest.approx


def run(**kwargs):
    kwargs.setdefault("stop_pct", 10)
    return run_backtest(
        CLOSES, initial_cash=1000, short=1, long=2, opens=OPENS, highs=HIGHS, lows=LOWS, **kwargs
    )


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), t.reason) for t in result.trades]


STOP_THEN_BUY = [(4, BUY, 90, A(11), "signal"), (6, SELL, 90, A(9.9), "stop"), (9, BUY, 75, A(12), "signal")]


# --------------------------------------------------------------------------- the hand case


def test_without_cooldown_stop_sells_on_bar_6_and_buys_again_on_bar_9():
    result = run()
    assert fills(result) == STOP_THEN_BUY
    assert result.final_cash == A(1)
    assert result.final_equity == A(916)
    assert result.cooldown == 0
    assert result.cooldown_skipped_buys == 0


def test_cooldown_3_skips_the_bar_9_buy_and_counts_it():
    result = run(cooldown=3)
    assert fills(result) == STOP_THEN_BUY[:2]
    assert result.final_cash == A(901)
    assert result.final_position == 0
    assert result.final_equity == A(901)
    assert result.cooldown == 3
    assert result.cooldown_skipped_buys == 1
    assert result.risk_skipped_buys == 0


def test_cooldown_2_ends_before_bar_9_so_the_buy_fills():
    result = run(cooldown=2)
    assert fills(result) == STOP_THEN_BUY
    assert result.final_equity == A(916)
    assert result.cooldown == 2
    assert result.cooldown_skipped_buys == 0


def test_a_skipped_buy_is_dropped_not_delayed():
    # The crossover signals BUY only on bar 8; once bar 9's fill is dropped nothing buys on bar 10.
    result = run(cooldown=3)
    assert [d.trade for d in result.daily[7:]] == [None, None, None, None]
    assert [d.position for d in result.daily[6:]] == [0] * 5


def test_a_cooldown_longer_than_the_data_is_fine():
    result = run(cooldown=1000)
    assert fills(result) == STOP_THEN_BUY[:2]
    assert result.cooldown_skipped_buys == 1


# --------------------------------------------------------------------------- which sells start one


@pytest.mark.parametrize("cooldown", [0, 4, 10])
def test_a_take_profit_sell_starts_no_cooldown(cooldown):
    result = run(take_profit_pct=5, cooldown=cooldown)
    assert fills(result) == [
        (4, BUY, 90, A(11), "signal"),
        (5, SELL, 90, A(11.55), "target"),
        (9, BUY, 87, A(12), "signal"),  # bar 9 is within 4 bars of the bar 5 target sell
    ]
    assert result.final_equity == A(1066.9)
    assert result.cooldown_skipped_buys == 0


@pytest.mark.parametrize("cooldown", [0, 3, 10])
def test_a_signal_sell_starts_no_cooldown(cooldown):
    result = run(stop_pct=50, cooldown=cooldown)  # a stop is on, but never reached
    assert fills(result) == [
        (4, BUY, 90, A(11), "signal"),
        (7, SELL, 90, A(10), "signal"),
        (9, BUY, 75, A(12), "signal"),  # bar 9 is within 3 bars of the bar 7 signal sell
    ]
    assert result.final_equity == A(925)
    assert result.cooldown_skipped_buys == 0


@pytest.mark.parametrize("cooldown, equity, skipped", [(0, 998.2, 0), (2, 998.2, 0), (3, 982, 1)])
def test_a_trailing_stop_sell_starts_a_cooldown(cooldown, equity, skipped):
    result = run(stop_pct=None, trail_pct=10, cooldown=cooldown)
    assert fills(result)[:2] == [(4, BUY, 90, A(11), "signal"), (6, SELL, 90, A(10.8), "trail")]
    assert len(result.trades) == 3 - skipped
    assert result.final_equity == A(equity)
    assert result.cooldown_skipped_buys == skipped


@pytest.mark.parametrize("cooldown, equity, skipped", [(0, 879.4, 0), (2, 879.4, 0), (3, 865, 1)])
def test_an_atr_stop_sell_starts_a_cooldown(cooldown, equity, skipped):
    result = run(stop_pct=None, atr_stop=True, atr_mult=1, atr_period=1, cooldown=cooldown)
    assert fills(result)[:2] == [(4, BUY, 90, A(11), "signal"), (6, SELL, 90, A(9.5), "atr")]
    assert len(result.trades) == 3 - skipped
    assert result.final_equity == A(equity)
    assert result.cooldown_skipped_buys == skipped
    assert result.risk_skipped_buys == 0


@pytest.mark.parametrize("cooldown, equity, skipped", [(0, 1016.84, 0), (2, 1016.84, 0), (3, 900.64, 1)])
def test_open_fills_count_the_bars_the_same_way(cooldown, equity, skipped):
    result = run(fill="open", cooldown=cooldown)
    assert fills(result)[:2] == [(4, BUY, 92, A(10.8), "signal"), (6, SELL, 92, A(9.72), "stop")]
    assert len(result.trades) == 3 - skipped
    assert result.final_equity == A(equity)
    assert result.cooldown_skipped_buys == skipped


# --------------------------------------------------------------------------- counting


@pytest.mark.parametrize("cooldown, skipped, last_buy", [(0, 0, (9, 75, 12)), (3, 1, (10, 73, 12.2)), (4, 2, None)])
def test_every_blocked_buy_is_counted(cooldown, skipped, last_buy):
    # breakout(window=1) signals BUY on every close above the one before: bars 8, 9 and 10 here,
    # so buys are due on bars 9 and 10. Cooldown 3 blocks bar 9 only, cooldown 4 both.
    result = run(strategy="breakout", strategy_params={"window": 1}, cooldown=cooldown)
    assert fills(result)[:2] == STOP_THEN_BUY[:2]
    assert result.cooldown_skipped_buys == skipped
    if last_buy is None:
        assert len(result.trades) == 2
    else:
        bar, shares, price = last_buy
        assert fills(result)[2:] == [(bar, BUY, shares, A(price), "signal")]


def test_a_blocked_buy_that_would_get_no_shares_counts_as_cooldown_not_risk():
    # risk_pct 0.16 with ATR(1) x 1: bar 4 risks 1.60 over 1.5 -> 1 share; the stop sells it at 9.50
    # (cash 998.50). Bar 9 would risk 1.5976 over 1.6 (ATR(1) on bar 8) -> 0 shares.
    kwargs = dict(stop_pct=None, atr_stop=True, atr_mult=1, atr_period=1, risk_pct=0.16)
    off = run(**kwargs)
    assert fills(off) == [(4, BUY, 1, A(11), "signal"), (6, SELL, 1, A(9.5), "atr")]
    assert (off.risk_skipped_buys, off.cooldown_skipped_buys) == (1, 0)
    on = run(cooldown=3, **kwargs)
    assert fills(on) == fills(off)
    assert (on.risk_skipped_buys, on.cooldown_skipped_buys) == (0, 1)  # counted once, as cooldown


# --------------------------------------------------------------------------- off by default


def _sample_args():
    candles = sample_candles("random_walk")
    return dict(
        closes=[c.close for c in candles],
        opens=[c.open for c in candles],
        highs=[c.high for c in candles],
        lows=[c.low for c in candles],
    )


OFF_SETTINGS = [
    {},
    {"stop_pct": 5},
    {"stop_pct": 3, "take_profit_pct": 6, "fill": "open", "slippage_pct": 0.1},
    {"trail_pct": 4, "position_size": 0.5, "fee": 1, "fee_pct": 0.1},
    {"atr_stop": True, "risk_pct": 1, "atr_mult": 1.5, "atr_period": 10},
    {"stop_pct": 2, "trail_pct": 3, "atr_stop": True, "strategy": "breakout"},
]


@pytest.mark.parametrize("settings", OFF_SETTINGS)
def test_cooldown_0_is_the_same_as_leaving_it_out(settings):
    args = _sample_args()
    default = run_backtest(short=5, long=20, **args, **settings)
    zero = run_backtest(short=5, long=20, cooldown=0, **args, **settings)
    assert default == zero
    assert default.cooldown == 0
    assert default.cooldown_skipped_buys == 0


def test_the_sample_has_stop_exits_that_a_cooldown_changes():
    # Guards the test above: on these settings the exits happen, and a cooldown does change things.
    args = _sample_args()
    off = run_backtest(strategy="breakout", stop_pct=2, **args)
    on = run_backtest(strategy="breakout", stop_pct=2, cooldown=5, **args)
    assert any(t.reason == "stop" for t in off.trades)
    assert on.cooldown_skipped_buys > 0
    assert on.trades != off.trades


# --------------------------------------------------------------------------- bad values


@pytest.mark.parametrize("bad", [-1, 1.5, 2.0, True, False, "3", None])
def test_cooldown_must_be_a_whole_number_of_at_least_0(bad):
    with pytest.raises(ValueError, match="cooldown must be a whole number of at least 0"):
        run(cooldown=bad)
