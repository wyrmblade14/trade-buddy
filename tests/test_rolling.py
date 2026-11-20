"""Tests for trading_assistant.rolling."""

import math

import pytest

from trading_assistant.rolling import (
    rolling_max_drawdown_pct,
    rolling_return_pct,
    rolling_sharpe,
    rolling_volatility_pct,
)

# Per-bar returns: +10%, -10%, 0%, +10%.
EQUITY = [100.0, 110.0, 99.0, 99.0, 108.9]


def test_rolling_return_window_2():
    # Bar 2: 99 / 100 - 1 = -1%. Bar 3: 99 / 110 - 1 = -10%. Bar 4: 108.9 / 99 - 1 = +10%.
    out = rolling_return_pct(EQUITY, 2)
    assert out[:2] == [None, None]
    assert out[2:] == pytest.approx([-1.0, -10.0, 10.0])


def test_rolling_return_window_1_is_per_bar_return():
    out = rolling_return_pct(EQUITY, 1)
    assert out[0] is None
    assert out[1:] == pytest.approx([10.0, -10.0, 0.0, 10.0])


def test_rolling_volatility_hand_checked():
    # Bar 2: returns +0.1, -0.1; mean 0; sample variance (0.01 + 0.01) / 1 = 0.02.
    out = rolling_volatility_pct(EQUITY, 2)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(math.sqrt(0.02) * math.sqrt(252) * 100)
    # Bar 3: returns -0.1, 0; mean -0.05; variance (0.0025 + 0.0025) / 1 = 0.005.
    assert out[3] == pytest.approx(math.sqrt(0.005) * math.sqrt(252) * 100)


def test_rolling_sharpe_hand_checked():
    out = rolling_sharpe(EQUITY, 2)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(0.0)  # mean return 0
    # Bar 3: mean -0.05 over std sqrt(0.005), annualised.
    assert out[3] == pytest.approx(-0.05 / math.sqrt(0.005) * math.sqrt(252))
    # Bar 4: returns 0, +0.1: mean 0.05, same std, so the mirror image.
    assert out[4] == pytest.approx(0.05 / math.sqrt(0.005) * math.sqrt(252))


def test_rolling_max_drawdown_hand_checked():
    out = rolling_max_drawdown_pct(EQUITY, 2)
    assert out[:2] == [None, None]
    # Bar 2 sees [100, 110, 99]: 99 / 110 - 1 = -10%. Bar 3 sees [110, 99, 99]: -10%.
    # Bar 4 sees [99, 99, 108.9]: never below a peak.
    assert out[2:] == pytest.approx([-10.0, -10.0, 0.0])


def test_flat_curve():
    flat = [100.0] * 6
    assert rolling_return_pct(flat, 3)[3:] == [0.0, 0.0, 0.0]
    assert rolling_volatility_pct(flat, 3)[3:] == [0.0, 0.0, 0.0]
    assert rolling_sharpe(flat, 3) == [None] * 6  # zero volatility: undefined
    assert rolling_max_drawdown_pct(flat, 3)[3:] == [0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    "fn", [rolling_return_pct, rolling_volatility_pct, rolling_sharpe, rolling_max_drawdown_pct]
)
def test_output_is_same_length_with_warm_up_none(fn):
    out = fn(EQUITY, 3)
    assert len(out) == len(EQUITY)
    assert out[:3] == [None, None, None]
    assert all(v is not None for v in out[3:]) or fn is rolling_sharpe


@pytest.mark.parametrize(
    "fn", [rolling_return_pct, rolling_volatility_pct, rolling_sharpe, rolling_max_drawdown_pct]
)
def test_window_longer_than_curve_is_all_none(fn):
    assert fn(EQUITY, 10) == [None] * 5
    assert fn([], 2) == []


def test_non_positive_divisor_gives_none():
    out = rolling_return_pct([0.0, 5.0, 6.0], 1)
    assert out == [None, None, pytest.approx(20.0)]


@pytest.mark.parametrize(
    "fn, window",
    [
        (rolling_return_pct, 0),
        (rolling_max_drawdown_pct, 0),
        (rolling_volatility_pct, 1),
        (rolling_sharpe, 1),
        (rolling_return_pct, 2.5),
        (rolling_return_pct, True),
    ],
)
def test_bad_window_raises(fn, window):
    with pytest.raises(ValueError, match="window"):
        fn(EQUITY, window)
