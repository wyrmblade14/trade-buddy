"""Tests for ema_cross, momentum, zscore_reversion and hull_trend.

Hand-worked examples (arithmetic in the comments of each test).
"""

import math

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.cli import main
from trading_assistant.signals import BUY, HOLD, SELL
from trading_assistant.strategies import (
    STRATEGIES,
    describe_strategies,
    ema_cross,
    hull_trend,
    momentum,
    resolve_params,
    strategy_names,
    zscore_reversion,
)


def signals(fn, closes, **params):
    return [fn(closes, t, **params) for t in range(len(closes))]


# ema_cross ---------------------------------------------------------------

def test_ema_cross_buy():
    # short=2 (alpha 2/3), long=3 (alpha 1/2); flat 10s then 14
    # t=4: short 2/3*14 + 1/3*10 = 12.667, long 0.5*14 + 0.5*10 = 12; before: 10 <= 10
    assert ema_cross([10, 10, 10, 10, 14], 4, short=2, long=3) == BUY


def test_ema_cross_sell():
    # t=4: short 2/3*6 + 10/3 = 7.333, long 0.5*6 + 0.5*10 = 8; before: 10 >= 10
    assert ema_cross([10, 10, 10, 10, 6], 4, short=2, long=3) == SELL


def test_ema_cross_hold_and_warm_up():
    flat = [10, 10, 10, 10, 10]
    assert signals(ema_cross, flat, short=2, long=3) == [HOLD] * 5
    # the long EMA first exists at t=2, so a cross needs t >= 3
    assert ema_cross([10, 10, 14], 2, short=2, long=3) == HOLD
    # already above and staying above is not a cross
    assert ema_cross([10, 10, 10, 10, 14, 14], 5, short=2, long=3) == HOLD


def test_ema_cross_defaults():
    assert STRATEGIES["ema_cross"][1] == {"short": 12, "long": 26}


# momentum ----------------------------------------------------------------

def test_momentum_buy_sell_hold():
    # window 2: ROC at t=2 is 0 for flat 10s; t=3 is 12/10 - 1 = +20%
    assert momentum([10, 10, 10, 12], 3, window=2) == BUY
    # t=3: 8/10 - 1 = -20% after 0
    assert momentum([10, 10, 10, 8], 3, window=2) == SELL
    # steadily rising: ROC 20% then 18.18%, never crosses 0
    assert momentum([10, 11, 12, 13], 3, window=2) == HOLD
    # warm-up: two ROC readings need t >= window + 1
    assert momentum([10, 10, 12], 2, window=2) == HOLD
    assert momentum([10, 10, 12], 0, window=2) == HOLD


def test_momentum_threshold():
    # ROC goes 0 -> 20; threshold 5 is crossed, threshold 20 is not (20 is not above 20)
    assert momentum([10, 10, 10, 12], 3, window=2, threshold=5.0) == BUY
    assert momentum([10, 10, 10, 12], 3, window=2, threshold=20.0) == HOLD
    # ROC 20 -> -25 crosses down through -10 and through 0
    assert momentum([10, 10, 12, 9], 3, window=2, threshold=-10.0) == HOLD  # ROC 0 -> -10 (not below)
    assert momentum([10, 12, 12, 9], 3, window=2, threshold=-10.0) == SELL  # ROC 20 -> -25


# zscore_reversion --------------------------------------------------------

ZS_BUY = [10, 10, 4, 6]
ZS_SELL = [10, 10, 4, 6, 9]


def test_zscore_reversion_buy():
    # window 3, entry -1, exit 0
    # t=2: [10,10,4] mean 8, var (4+4+16)/3 = 8, z = -4/sqrt(8) = -1.414
    # t=3: [10,4,6] mean 6.667, var (11.11+7.11+0.44)/3 = 6.222, z = -0.667/2.494 = -0.267
    # -1.414 < -1 <= -0.267, and the z-score stays below 0 -> BUY
    assert zscore_reversion(ZS_BUY, 3, window=3, entry=-1.0, exit=0.0) == BUY


def test_zscore_reversion_sell():
    # t=4: [4,6,9] mean 6.333, var (5.44+0.11+7.11)/3 = 4.222, z = 2.667/2.055 = +1.298
    # previous z -0.267 < 0 <= 1.298 -> SELL (and it was not below entry before)
    assert zscore_reversion(ZS_SELL, 4, window=3, entry=-1.0, exit=0.0) == SELL


def test_zscore_reversion_hold_and_warm_up():
    # a flat series has z = 0 every bar: never below exit, so no signal
    assert signals(zscore_reversion, [10] * 6, window=3, entry=-1.0, exit=0.0) == [HOLD] * 6
    # t=2 is the first z reading: no previous one
    assert zscore_reversion(ZS_BUY, 2, window=3, entry=-1.0, exit=0.0) == HOLD
    assert zscore_reversion(ZS_BUY, 0, window=3, entry=-1.0, exit=0.0) == HOLD


def test_zscore_reversion_sell_wins_when_both_levels_are_crossed():
    # window 3 on [10,10,4,10]: z goes -1.414 -> (10-8)/2.828 = +0.707, crossing entry -1 and exit 0
    assert zscore_reversion([10, 10, 4, 10], 3, window=3, entry=-1.0, exit=0.0) == SELL


def test_zscore_reversion_defaults():
    assert STRATEGIES["zscore_reversion"][1] == {"window": 20, "entry": -2.0, "exit": 0.0}


# hull_trend --------------------------------------------------------------

HULL_UP = [10, 9, 8, 7, 6, 5, 4, 5, 6]  # falls, then turns up at index 7
HULL_DOWN = [1, 2, 3, 4, 5, 6, 7, 6, 5]  # rises, then turns down at index 7


def test_hull_trend_buy():
    # window 4. On the falling line Hull = the close: 6, 5, 4 at indexes 4, 5, 6.
    # At index 7 the close is 5: Hull = (11/3 + 2*68/15)/3 = 191/45 = 4.244 > 4 after 5 > 4 (falling)
    assert hull_trend(HULL_UP, 7, window=4) == BUY


def test_hull_trend_sell():
    # mirror image (11 - close): Hull 5, 6, 7 then 11 - 191/45 = 6.756 < 7 after rising
    assert hull_trend(HULL_DOWN, 7, window=4) == SELL


def test_hull_trend_hold():
    # still falling at index 6 (6, 5, 4): not a turn up; still rising at index 6 for the mirror
    assert hull_trend(HULL_UP, 6, window=4) == HOLD
    assert hull_trend(HULL_DOWN, 6, window=4) == HOLD
    # a long straight line never turns
    assert signals(hull_trend, [float(i) for i in range(1, 15)], window=4)[6:] == [HOLD] * 8
    # warm-up: three Hull readings need index >= 6 for window 4
    assert all(s == HOLD for s in signals(hull_trend, HULL_UP, window=4)[:6])


def test_hull_trend_window_one_follows_the_closes():
    # Hull(1) = close: BUY when a rise follows a non-rise, SELL when a fall follows a non-fall
    assert signals(hull_trend, [3, 2, 4, 5, 4], window=1) == [HOLD, HOLD, BUY, HOLD, SELL]


# shared checks -----------------------------------------------------------

CASES = [
    (ema_cross, [10, 10, 10, 10, 14, 14, 6, 6, 9, 3, 12], {"short": 2, "long": 3}),
    (momentum, [10, 10, 10, 12, 12, 9, 9, 9, 13, 5], {"window": 2, "threshold": 0.0}),
    (zscore_reversion, [10, 10, 4, 6, 9, 12, 12, 3, 8, 9], {"window": 3, "entry": -1.0, "exit": 0.0}),
    (hull_trend, [10, 9, 8, 7, 6, 5, 4, 5, 6, 3, 9, 2], {"window": 4}),
]


@pytest.mark.parametrize("fn,closes,kw", CASES)
def test_no_look_ahead(fn, closes, kw):
    for t in range(len(closes)):
        base = fn(closes, t, **kw)
        for tail in (1, 1000, 0.5):
            altered = closes[: t + 1] + [tail] * (len(closes) - t - 1)
            assert fn(altered, t, **kw) == base
        assert fn(closes[: t + 1], t, **kw) == base


@pytest.mark.parametrize("fn,closes,kw", CASES)
def test_each_case_series_produces_a_buy_or_sell(fn, closes, kw):
    assert {BUY, SELL} & set(signals(fn, closes, **kw))


def test_registry_lists_all_seven():
    assert strategy_names() == [
        "sma_cross", "rsi_reversion", "breakout",
        "ema_cross", "momentum", "zscore_reversion", "hull_trend",
    ]
    lines = describe_strategies()
    assert "momentum (window=20, threshold=0.0): " in " ".join(lines)
    assert any(line.startswith("zscore_reversion (window=20, entry=-2.0, exit=0.0): ") for line in lines)


@pytest.mark.parametrize(
    "name,overrides",
    [
        ("ema_cross", {"short": 0}),
        ("ema_cross", {"short": 26, "long": 12}),
        ("ema_cross", {"short": 12, "long": 12}),
        ("ema_cross", {"long": 2.5}),
        ("momentum", {"window": 0}),
        ("momentum", {"threshold": float("nan")}),
        ("momentum", {"threshold": float("inf")}),
        ("momentum", {"threshold": "x"}),
        ("zscore_reversion", {"window": 1}),
        ("zscore_reversion", {"entry": 0.0, "exit": 0.0}),
        ("zscore_reversion", {"entry": 1.0, "exit": 0.0}),
        ("zscore_reversion", {"exit": float("nan")}),
        ("hull_trend", {"window": 0}),
        ("hull_trend", {"window": True}),
        ("hull_trend", {"bogus": 1}),
    ],
)
def test_bad_params_rejected(name, overrides):
    with pytest.raises(ValueError):
        resolve_params(name, overrides)


def test_functions_reject_bad_params_directly():
    with pytest.raises(ValueError):
        ema_cross([1, 2, 3], 2, short=5, long=3)
    with pytest.raises(ValueError):
        momentum([1, 2, 3], 2, window=0)
    with pytest.raises(ValueError):
        zscore_reversion([1, 2, 3], 2, window=3, entry=1.0, exit=-1.0)
    with pytest.raises(ValueError):
        hull_trend([1, 2, 3], 2, window=0)


def test_resolve_params_defaults():
    assert resolve_params("momentum") == {"window": 20, "threshold": 0.0}
    assert resolve_params("hull_trend", {"window": 9}) == {"window": 9}


# backtests ---------------------------------------------------------------

def trades_of(result):
    return [(t.bar, t.side, t.shares, t.price) for t in result.trades]


def test_ema_cross_backtest_hand_worked():
    # short=2, long=3, closes [10,10,10,10,14,14,6,6]
    # t=4: BUY (see above). t=5: short 13.556 > long 13 before and after -> HOLD.
    # t=6: short 2/3*6 + 1/3*13.556 = 8.519, long 0.5*6 + 0.5*13 = 9.5; 13.556 >= 13 before -> SELL
    # BUY fills bar 5 @ 14: 10,000 // 14 = 714 shares (9,996), cash 4.
    # SELL fills bar 7 @ 6: 714 * 6 = 4,284, cash 4,288. Return -57.12 %.
    r = run_backtest([10, 10, 10, 10, 14, 14, 6, 6], strategy="ema_cross", strategy_params={"short": 2, "long": 3})
    assert [d.signal for d in r.daily] == [HOLD] * 4 + [BUY, HOLD, SELL, HOLD]
    assert trades_of(r) == [(5, BUY, 714, 14), (7, SELL, 714, 6)]
    assert r.final_cash == 4288 and r.final_position == 0
    assert r.return_pct == pytest.approx(-57.12)
    assert r.strategy_params == {"short": 2, "long": 3}


def test_momentum_backtest_hand_worked():
    # window 2, threshold 0; ROC = [-, -, 0, +20, +20, -25, -25, 0]
    # t=3 BUY (0 -> 20), fills bar 4 @ 12: 833 shares (9,996), cash 4.
    # t=5 SELL (20 -> -25), fills bar 6 @ 9: 7,497, cash 7,501. Return -24.99 %.
    # t=7: ROC -25 -> 0 is not above 0 -> HOLD.
    r = run_backtest([10, 10, 10, 12, 12, 9, 9, 9], strategy="momentum", strategy_params={"window": 2})
    assert [d.signal for d in r.daily] == [HOLD, HOLD, HOLD, BUY, HOLD, SELL, HOLD, HOLD]
    assert trades_of(r) == [(4, BUY, 833, 12), (6, SELL, 833, 9)]
    assert r.final_cash == 7501
    assert r.return_pct == pytest.approx(-24.99)


def test_zscore_reversion_backtest_hand_worked():
    # window 3, entry -1, exit 0, closes [10,10,4,6,9,12,12]
    # t=3 BUY (z -1.414 -> -0.267), fills bar 4 @ 9: 1,111 shares (9,999), cash 1.
    # t=4 SELL (z -0.267 -> +1.298), fills bar 5 @ 12: 13,332, cash 13,333. Return +33.33 %.
    # t=5: [6,9,12] z = 3/sqrt(6) = 1.225; t=6: [9,12,12] z = 0.707: no cross -> HOLD.
    r = run_backtest(
        [10, 10, 4, 6, 9, 12, 12],
        strategy="zscore_reversion",
        strategy_params={"window": 3, "entry": -1.0, "exit": 0.0},
    )
    assert [d.signal for d in r.daily] == [HOLD, HOLD, HOLD, BUY, SELL, HOLD, HOLD]
    assert trades_of(r) == [(4, BUY, 1111, 9), (5, SELL, 1111, 12)]
    assert r.final_cash == 13333
    assert r.return_pct == pytest.approx(33.33)
    rt = r.round_trips[0]
    assert (rt.entry_bar, rt.exit_bar, rt.outlay, rt.proceeds) == (4, 5, 9999, 13332)


def test_hull_trend_backtest_hand_worked():
    # window 4 on [10,9,8,7,6,5,4,5,6,7]: BUY at t=7 (Hull turns up, see above),
    # fills bar 8 @ 6: 1,666 shares (9,996), cash 4. Hull keeps rising, no SELL.
    # End: 4 + 1,666 * 7 = 11,666 -> +16.66 %.
    r = run_backtest([10, 9, 8, 7, 6, 5, 4, 5, 6, 7], strategy="hull_trend", strategy_params={"window": 4})
    assert [d.signal for d in r.daily].count(BUY) == 1
    assert r.daily[7].signal == BUY and SELL not in [d.signal for d in r.daily]
    assert trades_of(r) == [(8, BUY, 1666, 6)]
    assert r.final_position == 1666
    assert r.return_pct == pytest.approx(16.66)


# command line ------------------------------------------------------------

def test_cli_accepts_ema_cross_backtest(tmp_path, capsys):
    closes = [10, 10, 10, 10, 14, 14, 6, 6]
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))
    code = main([str(csv_path), "--backtest", "--strategy", "ema_cross", "--param", "short=2", "--param", "long=3"])
    out = capsys.readouterr().out
    assert code in (0, None)
    assert "ema_cross" in out
    assert "-57.12" in out


@pytest.mark.parametrize("name", ["ema_cross", "momentum", "zscore_reversion", "hull_trend"])
def test_cli_accepts_new_strategy_names(name, tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("close\n" + "".join(f"{100 + 10 * math.sin(i / 3):.2f}\n" for i in range(80)))
    code = main([str(csv_path), "--backtest", "--strategy", name])
    assert code in (0, None)
    assert capsys.readouterr().out
