"""Hand-worked tests for atr (Wilder's average true range)."""

import pytest

from trading_assistant.indicators import atr


def test_manual_case_period_3():
    highs = [10, 12, 11, 13, 12]
    lows = [8, 10, 9, 10, 10]
    closes = [9, 11, 10, 12, 11]
    # True ranges:
    #   bar 0: 10 - 8                                   = 2
    #   bar 1: max(12-10, |12-9|,  |10-9|)  = max(2,3,1) = 3
    #   bar 2: max(11-9,  |11-11|, |9-11|)  = max(2,0,2) = 2
    #   bar 3: max(13-10, |13-10|, |10-10|) = max(3,3,0) = 3
    #   bar 4: max(12-10, |12-12|, |10-12|) = max(2,0,2) = 2
    # ATR[2] = (2 + 3 + 2) / 3          = 7/3
    # ATR[3] = (7/3 * 2 + 3) / 3        = 23/9
    # ATR[4] = (23/9 * 2 + 2) / 3       = 64/27
    out = atr(highs, lows, closes, 3)
    assert len(out) == 5
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(7 / 3)
    assert out[3] == pytest.approx(23 / 9)
    assert out[4] == pytest.approx(64 / 27)


def test_gap_uses_previous_close_outside_bar_range():
    # Bar 1 gaps up: previous close 9 is below its low 13.
    # Bar 2 gaps down: previous close 14 is above its high 8.
    # Every bar's high - low is only 2, so the gaps must drive the result.
    highs = [10, 15, 8]
    lows = [8, 13, 6]
    closes = [9, 14, 7]
    # True ranges:
    #   bar 0: 10 - 8                              = 2
    #   bar 1: max(15-13, |15-9|,  |13-9|) = max(2,6,4) = 6
    #   bar 2: max(8-6,   |8-14|,  |6-14|) = max(2,6,8) = 8
    # ATR[1] = (2 + 6) / 2     = 4
    # ATR[2] = (4 * 1 + 8) / 2 = 6
    out = atr(highs, lows, closes, 2)
    assert out[0] is None
    assert out[1] == pytest.approx(4.0)
    assert out[2] == pytest.approx(6.0)


def test_fewer_bars_than_period_is_all_none():
    assert atr([10, 12], [8, 10], [9, 11], 3) == [None, None]


def test_empty_input_is_empty():
    assert atr([], [], [], 3) == []


def test_exactly_period_bars_gives_one_value():
    out = atr([10, 12, 11], [8, 10, 9], [9, 11, 10], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(7 / 3)


def test_default_period_is_14():
    n = 15
    out = atr([11.0] * n, [10.0] * n, [10.5] * n)
    assert out[:13] == [None] * 13
    assert out[13] == pytest.approx(1.0)
    assert out[14] == pytest.approx(1.0)


@pytest.mark.parametrize("period", [0, -1, 1.5, "3", None, True])
def test_bad_period_raises(period):
    with pytest.raises(ValueError):
        atr([10, 12, 11], [8, 10, 9], [9, 11, 10], period)


@pytest.mark.parametrize(
    "highs, lows, closes",
    [
        ([10, 12], [8, 10, 9], [9, 11, 10]),
        ([10, 12, 11], [8, 10], [9, 11, 10]),
        ([10, 12, 11], [8, 10, 9], [9, 11]),
    ],
)
def test_different_lengths_raise(highs, lows, closes):
    with pytest.raises(ValueError):
        atr(highs, lows, closes, 2)


def test_high_below_low_raises():
    with pytest.raises(ValueError):
        atr([10, 9, 11], [8, 10, 9], [9, 9.5, 10], 2)


def test_high_below_low_raises_even_with_too_few_bars():
    with pytest.raises(ValueError):
        atr([9], [10], [9.5], 3)
