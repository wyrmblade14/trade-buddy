"""ATR risk-based position sizing in run_backtest (risk_pct, atr_mult, atr_period)."""

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.signals import BUY, SELL

CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]
HIGHS = [10.5, 9.5, 8.5, 9.5, 11.5, 13, 12.5, 9]
LOWS = [9.5, 8.5, 7.5, 8.5, 10.5, 11.2, 9.8, 7.5]

# SMA 1/2 crossover: BUY signal on bar 3 (fills bar 4 @ 11),
# SELL signal on bar 6 (fills bar 7 @ 8).
#
# True ranges: 1, 1.5, 1.5, 1.5, 2.5, 2, 2.7, 2.5
# ATR(3): bar 2 = (1 + 1.5 + 1.5) / 3          = 4/3
#         bar 3 = (4/3 * 2 + 1.5) / 3          = 25/18  ~ 1.3889  <- signal bar
#         bar 4 = (25/18 * 2 + 2.5) / 3        = 95/54  ~ 1.7593  <- fill bar
#
# Risk   = 2% of 1000 (all cash at the fill)   = 20
# Stop   = 2 * 25/18                           = 50/18 ~ 2.7778
# Shares = floor(20 / 2.7778) = floor(7.2)     = 7
# (The fill bar's ATR would give floor(20 / 3.5185) = 5.)


def run(**kwargs):
    base = dict(initial_cash=1000, short=1, long=2, highs=HIGHS, lows=LOWS)
    base.update(kwargs)
    return run_backtest(CLOSES, **base)


def test_manual_case_buys_seven_shares():
    result = run(risk_pct=2, atr_mult=2, atr_period=3)
    buy, sell = result.trades
    assert (buy.bar, buy.side, buy.shares, buy.price) == (4, BUY, 7, 11)
    assert buy.cash_after == pytest.approx(1000 - 7 * 11)
    assert (sell.bar, sell.side, sell.shares, sell.price) == (7, SELL, 7, 8.0)
    assert result.final_cash == pytest.approx(1000 - 77 + 56)
    assert result.final_position == 0


def test_uses_signal_bar_atr_not_fill_bar_atr():
    # Blow up the fill bar's (bar 4) range. Its ATR would change a lot, but
    # sizing must only look at bar 3, so the buy is still 7 shares.
    highs = list(HIGHS)
    lows = list(LOWS)
    highs[4], lows[4] = 60.0, 1.0
    result = run(risk_pct=2, atr_mult=2, atr_period=3, highs=highs, lows=lows)
    assert result.trades[0].bar == 4
    assert result.trades[0].shares == 7


def test_without_risk_pct_same_data_buys_all_in():
    result = run()
    buy, sell = result.trades
    assert (buy.bar, buy.side, buy.shares, buy.price) == (4, BUY, 90, 11)
    assert (sell.bar, sell.side, sell.shares, sell.price) == (7, SELL, 90, 8.0)


def test_without_risk_pct_atr_settings_change_nothing():
    plain = run_backtest(CLOSES, 1000, short=1, long=2)
    tuned = run_backtest(CLOSES, 1000, short=1, long=2, atr_mult=5, atr_period=2)
    assert tuned.trades == plain.trades
    assert tuned.daily == plain.daily


def test_risk_size_is_capped_by_cash():
    # 100% risk -> 1000 / 2.7778 = 360 shares wanted, but cash buys only 90.
    result = run(risk_pct=100, atr_mult=2, atr_period=3)
    assert result.trades[0].shares == 90


def test_smaller_of_risk_size_and_position_size_wins():
    # position_size 0.5 -> at most 500 / 11 = 45 shares; risk sizing wants 7.
    assert run(risk_pct=2, atr_mult=2, atr_period=3, position_size=0.5).trades[0].shares == 7
    # position_size 0.05 -> at most 50 / 11 = 4 shares, below the risk size of 7.
    assert run(risk_pct=2, atr_mult=2, atr_period=3, position_size=0.05).trades[0].shares == 4


def test_risk_too_small_for_one_share_skips_buy():
    # 0.1% of 1000 = 1; 1 / 2.7778 = 0.36 -> 0 shares, so nothing is bought.
    result = run(risk_pct=0.1, atr_mult=2, atr_period=3)
    assert result.trades == []
    assert result.final_cash == 1000


@pytest.mark.parametrize("risk_pct", [0, -1, 100.5])
def test_bad_risk_pct_raises(risk_pct):
    with pytest.raises(ValueError, match="risk_pct"):
        run(risk_pct=risk_pct, atr_period=3)


def test_risk_pct_100_is_allowed():
    run(risk_pct=100, atr_period=3)


@pytest.mark.parametrize("atr_mult", [0, -2])
def test_bad_atr_mult_raises(atr_mult):
    with pytest.raises(ValueError, match="atr_mult"):
        run(risk_pct=2, atr_mult=atr_mult, atr_period=3)


@pytest.mark.parametrize("atr_period", [0, -1, 1.5, True, "3"])
def test_bad_atr_period_raises(atr_period):
    with pytest.raises(ValueError, match="atr_period"):
        run(risk_pct=2, atr_period=atr_period)


@pytest.mark.parametrize(
    "highs, lows",
    [(None, LOWS), (HIGHS, None), (None, None)],
)
def test_missing_highs_or_lows_raises(highs, lows):
    with pytest.raises(ValueError, match="high and low"):
        run(risk_pct=2, atr_period=3, highs=highs, lows=lows)


def test_highs_lows_wrong_length_raises():
    with pytest.raises(ValueError):
        run(risk_pct=2, atr_period=3, highs=HIGHS[:-1])


def test_high_below_low_raises():
    highs = list(HIGHS)
    highs[2] = 7.0  # below that bar's low of 7.5
    with pytest.raises(ValueError):
        run(risk_pct=2, atr_period=3, highs=highs)


def test_buy_signal_before_atr_exists_is_skipped():
    # atr_period 5: the first ATR is on bar 4, but the BUY signal is on bar 3.
    # The buy is skipped; the later SELL signal (bar 6) has nothing to sell.
    result = run(risk_pct=2, atr_mult=2, atr_period=5)
    assert result.daily[3].signal == BUY
    assert result.trades == []
    assert result.final_position == 0
    assert result.final_cash == 1000
    assert all(d.cash == 1000 for d in result.daily)


def test_later_buy_once_atr_exists_is_sized_normally():
    # Same data plus two bars, so a second BUY comes after the ATR exists.
    #   bar 8: close 9,  high 9.5,  low 8    (close 9 crosses above SMA2 8.5 -> BUY)
    #   bar 9: close 11, high 11.5, low 10.5 (the BUY fills here @ 11)
    # The bar 3 BUY is skipped (no ATR yet) and the bar 6 SELL has nothing to sell.
    #
    # True ranges: 1, 1.5, 1.5, 1.5, 2.5, 2, 2.7, 2.5,
    #   bar 8: max(9.5-8, |9.5-8|, |8-8|)         = 1.5
    #   bar 9: max(11.5-10.5, |11.5-9|, |10.5-9|) = 2.5
    # ATR(5): bar 4 = (1 + 1.5 + 1.5 + 1.5 + 2.5) / 5 = 1.6
    #         bar 5 = (1.6    * 4 + 2  ) / 5          = 1.68
    #         bar 6 = (1.68   * 4 + 2.7) / 5          = 1.884
    #         bar 7 = (1.884  * 4 + 2.5) / 5          = 2.0072
    #         bar 8 = (2.0072 * 4 + 1.5) / 5          = 1.90576   <- signal bar
    #         bar 9 = (1.90576 * 4 + 2.5) / 5         = 2.024608  <- fill bar
    # Risk   = 2% of 1000 (still all cash)  = 20
    # Stop   = 2 * 1.90576                  = 3.81152
    # Shares = floor(20 / 3.81152) = floor(5.247) = 5
    # (The fill bar's ATR would give floor(20 / 4.049216) = floor(4.939) = 4.)
    closes = CLOSES + [9, 11]
    highs = HIGHS + [9.5, 11.5]
    lows = LOWS + [8, 10.5]
    result = run_backtest(
        closes, 1000, short=1, long=2, highs=highs, lows=lows,
        risk_pct=2, atr_mult=2, atr_period=5,
    )
    assert result.daily[3].signal == BUY
    assert result.daily[8].signal == BUY
    (buy,) = result.trades
    assert (buy.bar, buy.side, buy.shares, buy.price) == (9, BUY, 5, 11)
    assert buy.cash_after == pytest.approx(1000 - 5 * 11)
    assert result.final_position == 5
