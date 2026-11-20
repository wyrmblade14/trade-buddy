"""Tests for trading_assistant.metrics, with hand-computed values.

Main curve  E = [100, 110, 99, 108.9]
    returns: 110/100 - 1 = +0.1, 99/110 - 1 = -0.1, 108.9/99 - 1 = +0.1
    mean = 0.1 / 3 = 0.033333
    deviations: 0.066667, -0.133333, 0.066667; squares: 0.004444, 0.017778, 0.004444
    sum of squares = 0.026667
    sample variance = 0.026667 / 2 = 0.013333, sample std = 0.115470
    downside: min(r, 0)^2 = 0, 0.01, 0 -> mean 0.003333, downside dev = 0.057735
    total return = 108.9 / 100 - 1 = 8.9 %
"""

import math

import pytest

from trading_assistant.backtest import BacktestResult, RoundTrip, format_stats, run_backtest
from trading_assistant.metrics import (
    annualized_volatility_pct,
    average_loss,
    average_win,
    cagr_pct,
    exposure_pct,
    longest_drawdown_bars,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    total_return_pct,
)

E = [100.0, 110.0, 99.0, 108.9]
MEAN = 0.1 / 3
SAMPLE_STD = math.sqrt(0.08 / 3 / 2)  # sum of squares 0.08/3 = 0.026667, over n - 1 = 2
DOWNSIDE = math.sqrt(0.01 / 3)


def trip(pnl):
    return RoundTrip(entry_bar=0, exit_bar=1, shares=1, outlay=100.0, proceeds=100.0 + pnl)


# --------------------------------------------------------------------------- return


def test_total_return_pct():
    assert total_return_pct(E) == pytest.approx(8.9)  # 108.9 / 100 - 1
    assert total_return_pct([200.0, 150.0]) == pytest.approx(-25.0)  # 150 / 200 - 1


def test_total_return_pct_undefined():
    assert total_return_pct([]) is None
    assert total_return_pct([100.0]) is None
    assert total_return_pct([0.0, 5.0]) is None


def test_cagr_pct():
    # 4 bars = 3 periods; periods_per_year=3 -> 1 year -> (108.9/100)^1 - 1 = 8.9 %
    assert cagr_pct(E, periods_per_year=3) == pytest.approx(8.9)
    # periods_per_year=6 -> 0.5 year -> 1.089^2 - 1 = 18.5921 %
    assert cagr_pct(E, periods_per_year=6) == pytest.approx(18.5921)
    # a total loss is -100 %
    assert cagr_pct([100.0, 0.0], periods_per_year=1) == pytest.approx(-100.0)


def test_cagr_pct_undefined():
    assert cagr_pct([100.0]) is None
    assert cagr_pct([0.0, 10.0]) is None
    assert cagr_pct([100.0, -5.0]) is None


# --------------------------------------------------------------------------- volatility, ratios


def test_annualized_volatility_pct():
    # 0.115470 * sqrt(4) * 100 = 23.094 %
    assert annualized_volatility_pct(E, periods_per_year=4) == pytest.approx(SAMPLE_STD * 2 * 100)
    assert annualized_volatility_pct(E, periods_per_year=4) == pytest.approx(23.094, abs=1e-3)


def test_annualized_volatility_pct_undefined():
    assert annualized_volatility_pct([100.0, 110.0]) is None  # a single return has no sample std
    assert annualized_volatility_pct([]) is None
    assert annualized_volatility_pct([100.0, 0.0, 5.0]) is None  # return from a zero value


def test_sharpe_ratio():
    # 0.033333 / 0.115470 * sqrt(4) = 0.288675 * 2 = 0.57735
    assert sharpe_ratio(E, periods_per_year=4) == pytest.approx(MEAN / SAMPLE_STD * 2)
    assert sharpe_ratio(E, periods_per_year=4) == pytest.approx(0.57735, abs=1e-5)


def test_sharpe_ratio_undefined():
    assert sharpe_ratio([100.0, 110.0]) is None
    assert sharpe_ratio([100.0, 100.0, 100.0, 100.0]) is None  # zero volatility
    assert sharpe_ratio([100.0, 110.0, 121.0, 133.1]) is None  # constant +10 %: zero volatility


def test_sortino_ratio():
    # 0.033333 / 0.057735 * sqrt(4) = 0.57735 * 2 = 1.1547
    assert sortino_ratio(E, periods_per_year=4) == pytest.approx(MEAN / DOWNSIDE * 2)
    assert sortino_ratio(E, periods_per_year=4) == pytest.approx(1.1547, abs=1e-4)


def test_sortino_ratio_undefined():
    assert sortino_ratio([100.0, 110.0]) is None
    assert sortino_ratio([100.0, 105.0, 120.0]) is None  # no negative return


# --------------------------------------------------------------------------- exposure


def test_exposure_pct():
    # held on 3 of 5 bars -> 60 %
    assert exposure_pct([0, 0, 5, 5, 5]) == pytest.approx(60.0)
    assert exposure_pct([0, 0]) == 0.0
    assert exposure_pct([2, 2]) == 100.0


def test_exposure_pct_undefined():
    assert exposure_pct([]) is None


# --------------------------------------------------------------------------- round trips


def test_profit_factor_and_averages():
    trips = [trip(30.0), trip(-10.0), trip(10.0), trip(-20.0)]
    # gross profit 30 + 10 = 40, gross loss 10 + 20 = 30 -> 40 / 30
    assert profit_factor(trips) == pytest.approx(4 / 3)
    assert average_win(trips) == pytest.approx(20.0)  # (30 + 10) / 2
    assert average_loss(trips) == pytest.approx(-15.0)  # (-10 - 20) / 2


def test_profit_factor_all_losses_is_zero():
    assert profit_factor([trip(-5.0)]) == 0.0  # gross profit 0 / gross loss 5


def test_round_trip_stats_undefined():
    assert profit_factor([]) is None
    assert profit_factor([trip(10.0)]) is None  # no losing round trip
    assert average_win([]) is None
    assert average_win([trip(-1.0)]) is None
    assert average_loss([]) is None
    assert average_loss([trip(1.0)]) is None
    assert average_win([trip(0.0)]) is None  # break-even is neither a win nor a loss
    assert average_loss([trip(0.0)]) is None


# --------------------------------------------------------------------------- drawdown length


def test_longest_drawdown_bars():
    # peak 100 (bar 0); bars 1, 2 below it; bar 3 = 100 recovers (run 2)
    # bar 4 = 99 is below the peak 100 (run 1); bar 5 = 120 is a new peak
    assert longest_drawdown_bars([100, 90, 95, 100, 99, 120]) == 2
    # never falls below a peak
    assert longest_drawdown_bars([1, 2, 2, 3]) == 0
    # never recovers: bars 1..4 are all below 100
    assert longest_drawdown_bars([100, 90, 80, 90, 95]) == 4


def test_longest_drawdown_bars_undefined():
    assert longest_drawdown_bars([]) is None
    assert longest_drawdown_bars([100.0]) is None


# --------------------------------------------------------------------------- BacktestResult.stats


def test_backtest_result_stats_dict():
    # LOSS sample: equity 10000 x5, 10000, 10000, 5716, 5716, 5716 (see test_backtest_metrics.py)
    r = run_backtest([10, 10, 10, 10, 14, 14, 14, 8, 8, 8], short=2, long=3)
    st = r.stats
    assert st["total_return_pct"] == pytest.approx(-42.84)
    assert st["longest_drawdown_bars"] == 3  # bars 7, 8, 9 below the 10,000 peak
    assert st["exposure_pct"] == pytest.approx(30.0)  # held after bars 5, 6, 7 -> 3 of 10 bars
    assert st["profit_factor"] == 0.0  # gross profit 0 / gross loss 4,284
    assert st["average_win"] is None
    assert st["average_loss"] == pytest.approx(-4284.0)  # 5,712 - 9,996


def test_format_stats_uses_na_for_undefined_values():
    # one bar: nothing but exposure is defined
    r = BacktestResult(initial_cash=100.0, final_cash=100.0, final_position=0, final_price=10.0)
    lines = format_stats(r)
    assert lines[0] == "Risk and return"
    assert "  Sharpe ratio:       n/a" in lines
    assert "  Exposure:           n/a" in lines  # no bars recorded
    full = format_stats(run_backtest([10, 10, 10, 10, 14, 14, 14, 8, 8, 8], short=2, long=3))
    assert "  Total return:       -42.84%" in full
    assert "  Exposure:           30.00%" in full
    assert "  Profit factor:      0.00" in full
    assert "  Average win:        n/a" in full
    assert "  Longest drawdown:   3 bars" in full
