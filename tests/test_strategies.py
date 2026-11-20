"""Tests for trading_assistant.strategies and the strategy option of run_backtest.

Hand-worked examples.

SMA     short=2, long=3 (see test_backtest.py)
    [10, 10, 10, 10, 14]  t=4: sma2 12 > sma3 11.33 after 10 <= 10  -> BUY
    [10, 10, 10, 10, 6]   t=4: sma2 8 < sma3 8.67 after 10 >= 10    -> SELL

RSI     period=2, oversold=30, overbought=70
    closes = [10, 9, 8, 9, 10, 11, 10, 9, 8, 9]
    t=2: avg gain 0, avg loss 1                          -> RSI 0
    t=3: gain (0*1 + 1)/2 = 0.5,   loss (1*1 + 0)/2 = 0.5   -> rs 1     -> RSI 50
    t=4: gain (0.5 + 1)/2 = 0.75,  loss 0.5/2 = 0.25         -> rs 3     -> RSI 75
    t=5: gain (0.75 + 1)/2 = 0.875, loss 0.25/2 = 0.125      -> rs 7     -> RSI 87.5
    t=6: gain 0.875/2 = 0.4375, loss (0.125 + 1)/2 = 0.5625  -> RSI 43.75
    t=7: gain 0.21875, loss 0.78125                          -> RSI 21.875
    t=8: gain 0.109375, loss 0.890625                        -> RSI 10.9375
    t=9: gain (0.109375 + 1)/2 = 0.5546875, loss 0.4453125   -> RSI 55.47
    t=3: 0 < 30 and 50 >= 30                -> BUY
    t=6: 87.5 > 70 and 43.75 <= 70          -> SELL
    t=9: 10.94 < 30 and 55.47 >= 30         -> BUY (final bar, never filled)
    t=2: no previous RSI (warm-up)          -> HOLD
    t=5: 75 > 70 but 87.5 > 70 still        -> HOLD
    Backtest, 10,000 cash: BUY fills bar 4 @ 10 -> 1,000 sh, cash 0.
    SELL fills bar 7 @ 9 -> 9,000. Return -10.00 %.
    Round trip: entry 4, exit 7, outlay 10,000, proceeds 9,000, pnl -1,000.

BREAKOUT window=2
    closes = [10, 10, 11, 12, 9, 8, 8]
    t=2: 11 > max(10, 10) = 10   -> BUY
    t=3: 12 > max(10, 11) = 11   -> BUY
    t=4: 9 < min(11, 12) = 11    -> SELL
    t=5: 8 < min(12, 9) = 9      -> SELL
    t=6: 8 == min(9, 8)          -> HOLD
    t=0, t=1: fewer than 2 earlier closes -> HOLD
    Backtest, 10,000 cash: the BUY from t=2 fills bar 3 @ 12 -> 833 sh (9,996), cash 4.
    The BUY from t=3 fills bar 4 @ 9 but 4 cash buys nothing -> skipped.
    The SELL from t=4 fills bar 5 @ 8 -> 6,664, cash 6,668.
    The SELL from t=5 fills bar 6 with nothing held -> skipped.
    End equity 6,668 -> -33.32 %. Round trip: entry 3, exit 5, pnl 6,664 - 9,996 = -3,332.
"""

import pytest

from trading_assistant.backtest import format_result, run_backtest
from trading_assistant.signals import BUY, HOLD, SELL
from trading_assistant.strategies import (
    STRATEGIES,
    breakout,
    describe_strategies,
    get_strategy,
    resolve_params,
    rsi_reversion,
    sma_cross,
    strategy_names,
)

RSI_CLOSES = [10, 9, 8, 9, 10, 11, 10, 9, 8, 9]
BREAK_CLOSES = [10, 10, 11, 12, 9, 8, 8]
LOSS = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]


# --------------------------------------------------------------------------- sma_cross


def test_sma_cross_buy_sell_hold():
    assert sma_cross([10, 10, 10, 10, 14], 4, short=2, long=3) == BUY
    assert sma_cross([10, 10, 10, 10, 6], 4, short=2, long=3) == SELL
    assert sma_cross([10, 10, 10, 10, 14], 3, short=2, long=3) == HOLD


def test_sma_cross_defaults_are_20_50():
    assert STRATEGIES["sma_cross"][1] == {"short": 20, "long": 50}


# --------------------------------------------------------------------------- rsi_reversion


def test_rsi_reversion_buy_sell_hold():
    kw = dict(period=2, oversold=30, overbought=70)
    assert rsi_reversion(RSI_CLOSES, 3, **kw) == BUY
    assert rsi_reversion(RSI_CLOSES, 6, **kw) == SELL
    assert rsi_reversion(RSI_CLOSES, 9, **kw) == BUY
    assert rsi_reversion(RSI_CLOSES, 5, **kw) == HOLD
    assert rsi_reversion(RSI_CLOSES, 7, **kw) == HOLD


def test_rsi_reversion_holds_during_warm_up():
    kw = dict(period=2, oversold=30, overbought=70)
    assert [rsi_reversion(RSI_CLOSES, t, **kw) for t in range(3)] == [HOLD] * 3


def test_rsi_reversion_threshold_touch_counts_as_cross_up():
    # RSI 50 on the bar after RSI 0: oversold=50 means 50 >= 50 is a cross up.
    assert rsi_reversion(RSI_CLOSES, 3, period=2, oversold=50, overbought=70) == BUY
    # oversold=51: 50 < 51, so RSI never rose through the level.
    assert rsi_reversion(RSI_CLOSES, 3, period=2, oversold=51, overbought=70) == HOLD


# --------------------------------------------------------------------------- breakout


def test_breakout_buy_sell_hold():
    assert [breakout(BREAK_CLOSES, t, window=2) for t in range(7)] == [
        HOLD, HOLD, BUY, BUY, SELL, SELL, HOLD,
    ]


def test_breakout_equal_to_high_is_hold():
    assert breakout([10, 12, 12], 2, window=2) == HOLD


def test_breakout_default_window_20():
    assert STRATEGIES["breakout"][1] == {"window": 20}
    closes = [10.0] * 20 + [11.0]
    assert breakout(closes, 19) == HOLD
    assert breakout(closes, 20) == BUY


# --------------------------------------------------------------------------- no look-ahead


@pytest.mark.parametrize(
    "fn, closes, kw",
    [
        (sma_cross, LOSS, dict(short=2, long=3)),
        (rsi_reversion, RSI_CLOSES, dict(period=2, oversold=30, overbought=70)),
        (breakout, BREAK_CLOSES, dict(window=2)),
    ],
)
def test_signal_ignores_later_closes(fn, closes, kw):
    for t in range(len(closes)):
        altered = closes[: t + 1] + [1000.0 * (i + 1) for i in range(len(closes) - t - 1)]
        assert fn(closes, t, **kw) == fn(altered, t, **kw)
        assert fn(closes, t, **kw) == fn(closes[: t + 1], t, **kw)


# --------------------------------------------------------------------------- registry


def test_registry_names_and_descriptions():
    # The original three keep their order; later strategies are appended.
    assert strategy_names()[:3] == ["sma_cross", "rsi_reversion", "breakout"]
    lines = describe_strategies()
    assert len(lines) == len(strategy_names())
    assert lines[0].startswith("sma_cross (short=20, long=50): ")
    assert lines[2].startswith("breakout (window=20): ")


def test_get_strategy_returns_function_defaults_and_description():
    fn, defaults, description = get_strategy("rsi_reversion")
    assert fn is rsi_reversion
    assert defaults == {"period": 14, "oversold": 30, "overbought": 70}
    assert description
    defaults["period"] = 99  # a copy: the registry is unchanged
    assert get_strategy("rsi_reversion")[1]["period"] == 14


def test_get_strategy_unknown_name_names_choices():
    with pytest.raises(ValueError, match="unknown strategy 'macd'.*sma_cross, rsi_reversion, breakout"):
        get_strategy("macd")


@pytest.mark.parametrize(
    "name, overrides, message",
    [
        ("sma_cross", {"short": 5, "long": 5}, "short window must be smaller than long window"),
        ("sma_cross", {"short": 0, "long": 5}, "short window must be a whole number of at least 1"),
        ("rsi_reversion", {"period": 0}, "period must be a whole number of at least 1"),
        ("rsi_reversion", {"oversold": 70, "overbought": 70}, "0 <= oversold < overbought <= 100"),
        ("rsi_reversion", {"oversold": -1}, "0 <= oversold < overbought <= 100"),
        ("rsi_reversion", {"overbought": 101}, "0 <= oversold < overbought <= 100"),
        ("breakout", {"window": 0}, "window must be a whole number of at least 1"),
        ("breakout", {"period": 5}, "unknown parameter 'period' for strategy 'breakout'"),
    ],
)
def test_resolve_params_rejects_bad_params(name, overrides, message):
    with pytest.raises(ValueError, match=message):
        resolve_params(name, overrides)


def test_resolve_params_merges_over_defaults():
    assert resolve_params("rsi_reversion", {"period": 5}) == {"period": 5, "oversold": 30, "overbought": 70}
    assert resolve_params("breakout") == {"window": 20}


def test_strategy_functions_reject_bad_params_directly():
    with pytest.raises(ValueError):
        breakout(BREAK_CLOSES, 3, window=0)
    with pytest.raises(ValueError):
        rsi_reversion(RSI_CLOSES, 3, period=2, oversold=80, overbought=20)
    with pytest.raises(ValueError):
        sma_cross(LOSS, 5, short=3, long=2)


# --------------------------------------------------------------------------- run_backtest


def test_default_strategy_equals_explicit_sma_cross():
    for kw in (dict(short=2, long=3), dict(short=2, long=3, fee=5, fee_pct=1), {}):
        base = run_backtest(LOSS, **kw)
        explicit = run_backtest(LOSS, strategy="sma_cross", **kw)
        assert base == explicit
        assert base.strategy == "sma_cross"
    r = run_backtest(LOSS, short=2, long=3)
    assert r.strategy_params == {"short": 2, "long": 3}
    assert format_result(r, 2, 3)[0] == (
        "Backtest: SMA 2/3 crossover, next-bar fills, whole shares, no shorting"
    )


def test_strategy_params_override_short_and_long():
    via_params = run_backtest(LOSS, strategy_params={"short": 2, "long": 3})
    via_args = run_backtest(LOSS, short=2, long=3)
    assert via_params == via_args
    mixed = run_backtest(LOSS, short=2, long=9, strategy_params={"long": 3})
    assert mixed.strategy_params == {"short": 2, "long": 3}
    assert mixed == via_args


def test_backtest_rejects_bad_strategy_and_params():
    with pytest.raises(ValueError, match="unknown strategy"):
        run_backtest(LOSS, strategy="nope")
    with pytest.raises(ValueError, match="short window must be smaller"):
        run_backtest(LOSS, strategy_params={"short": 5, "long": 4})
    with pytest.raises(ValueError, match="window must be a whole number"):
        run_backtest(LOSS, strategy="breakout", strategy_params={"window": 0})


def test_rsi_reversion_backtest_hand_worked():
    r = run_backtest(
        RSI_CLOSES,
        strategy="rsi_reversion",
        strategy_params={"period": 2, "oversold": 30, "overbought": 70},
    )
    assert [(t.bar, t.side, t.shares, t.price) for t in r.trades] == [
        (4, BUY, 1000, 10),
        (7, SELL, 1000, 9),
    ]
    assert [d.signal for d in r.daily] == [
        HOLD, HOLD, HOLD, BUY, HOLD, HOLD, SELL, HOLD, HOLD, BUY,
    ]
    assert r.final_cash == 9000 and r.final_position == 0
    assert r.return_pct == pytest.approx(-10.0)
    assert len(r.round_trips) == 1
    rt = r.round_trips[0]
    assert (rt.entry_bar, rt.exit_bar, rt.outlay, rt.proceeds, rt.pnl) == (4, 7, 10000, 9000, -1000)
    assert r.strategy == "rsi_reversion"
    assert r.strategy_params == {"period": 2, "oversold": 30, "overbought": 70}


def test_breakout_backtest_hand_worked():
    r = run_backtest(BREAK_CLOSES, strategy="breakout", strategy_params={"window": 2})
    assert [(t.bar, t.side, t.shares, t.price) for t in r.trades] == [
        (3, BUY, 833, 12),
        (5, SELL, 833, 8),
    ]
    assert r.final_cash == 6668 and r.final_position == 0
    assert r.return_pct == pytest.approx(-33.32)
    rt = r.round_trips[0]
    assert (rt.entry_bar, rt.exit_bar, rt.pnl) == (3, 5, -3332)
    assert r.strategy_params == {"window": 2}


def test_format_result_first_line_names_other_strategies():
    r = run_backtest(BREAK_CLOSES, strategy="breakout", strategy_params={"window": 2})
    assert format_result(r, 20, 50)[0] == (
        "Backtest: breakout (window=2), next-bar fills, whole shares, no shorting"
    )
    r = run_backtest(RSI_CLOSES, strategy="rsi_reversion", strategy_params={"period": 2})
    assert format_result(r, 20, 50)[0] == (
        "Backtest: rsi_reversion (period=2, oversold=30, overbought=70), "
        "next-bar fills, whole shares, no shorting"
    )
