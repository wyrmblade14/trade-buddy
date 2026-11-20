"""Hand-worked tests for the close-only indicators beyond sma, ema and rsi."""

import math

import pytest

from trading_assistant.indicators import (
    cmo,
    dema,
    hull_ma,
    kama,
    linreg_slope,
    momentum,
    roc,
    rolling_std,
    tema,
    trix,
    wma,
    zscore,
)


def approx_list(expected):
    return [None if v is None else pytest.approx(v) for v in expected]


def test_wma_linear_weights():
    # window 3, weights 1, 2, 3, divisor 6
    # [1,2,3]: (1 + 4 + 9) / 6 = 14/6; [2,3,4]: (2 + 6 + 12) / 6 = 20/6; [3,4,5]: (3 + 8 + 15) / 6 = 26/6
    assert wma([1, 2, 3, 4, 5], 3) == approx_list([None, None, 14 / 6, 20 / 6, 26 / 6])


def test_wma_window_one_is_identity_and_short_input_all_none():
    assert wma([4, 7], 1) == [4, 7]
    assert wma([1, 2], 3) == [None, None]


def test_dema_of_a_straight_line_is_the_line():
    # window 2, alpha 2/3, values 1..6
    # E1 = [-, 1.5, 2.5, 3.5, 4.5, 5.5]
    # E2 (EMA of E1, seeded (1.5 + 2.5) / 2 = 2.0 at index 2) = [-, -, 2, 3, 4, 5]
    # DEMA = 2*E1 - E2 = [-, -, 5-2, 7-3, 9-4, 11-5] = 3, 4, 5, 6
    assert dema([1, 2, 3, 4, 5, 6], 2) == approx_list([None, None, 3, 4, 5, 6])


def test_dema_warmup_count():
    out = dema([float(i) for i in range(1, 20)], 4)
    assert out.index(next(v for v in out if v is not None)) == 2 * (4 - 1)
    assert out[:6] == [None] * 6 and out[6] is not None


def test_tema_of_a_straight_line_is_the_line():
    # E1 = 1.5, 2.5, 3.5, 4.5, 5.5 (from index 1); E2 = 2, 3, 4, 5 (from index 2)
    # E3 seeded (2 + 3) / 2 = 2.5 at index 3, then 2/3*4 + 1/3*2.5 = 3.5, 4.5
    # TEMA = 3*E1 - 3*E2 + E3: 10.5 - 9 + 2.5 = 4; 13.5 - 12 + 3.5 = 5; 16.5 - 15 + 4.5 = 6
    assert tema([1, 2, 3, 4, 5, 6], 2) == approx_list([None, None, None, 4, 5, 6])


def test_tema_warmup_count():
    out = tema([float(i) for i in range(1, 30)], 4)
    assert out[:9] == [None] * 9 and out[9] is not None


def test_hull_ma_on_a_line_and_warmup():
    # window 4: half window 2, final window isqrt(4) = 2
    # on a line y = x: WMA2 = y - 1/3, WMA4 = y - 1, raw = 2*WMA2 - WMA4 = y + 1/3,
    # and the final WMA2 of raw = raw - 1/3 = y. First value at index 3 + 1 = 4.
    assert hull_ma([1, 2, 3, 4, 5, 6, 7, 8], 4) == approx_list([None] * 4 + [5, 6, 7, 8])


def test_hull_ma_kink():
    # [8,7,6,5,4,5]: window 4. raw3 = 14/3 (line, values 8,7,6,5), raw4 = 11/3 (7,6,5,4),
    # raw5: WMA2(4,5) = (4 + 10)/3 = 14/3, WMA4(6,5,4,5) = (6+10+12+20)/10 = 4.8,
    # raw5 = 28/3 - 4.8 = 68/15. Hull4 = (14/3 + 2*11/3)/3 = 4; Hull5 = (11/3 + 2*68/15)/3 = 191/45.
    out = hull_ma([8, 7, 6, 5, 4, 5], 4)
    assert out[3] is None
    assert out[4] == pytest.approx(4.0)
    assert out[5] == pytest.approx(191 / 45)


def test_hull_ma_window_one_is_the_closes():
    assert hull_ma([3, 1, 2], 1) == approx_list([3, 1, 2])


def test_roc_percent():
    # window 1: 110/100 - 1 = +10%; 99/110 - 1 = -10%; 121/99 - 1 = 22.222...%
    assert roc([100, 110, 99, 121], 1) == approx_list([None, 10, -10, (121 / 99 - 1) * 100])
    # window 2: 99/100 - 1 = -1%; 121/110 - 1 = +10%
    assert roc([100, 110, 99, 121], 2) == approx_list([None, None, -1, 10])


def test_roc_zero_divisor_raises():
    with pytest.raises(ValueError, match="zero"):
        roc([0, 1, 2], 1)


def test_momentum_difference():
    # window 2: 9-1, 16-4, 25-9
    assert momentum([1, 4, 9, 16, 25], 2) == [None, None, 8, 12, 16]


def test_rolling_std_is_population():
    # classic example: mean 5, squared deviations sum 32, 32/8 = 4, std 2 (sample std would be 2.138)
    out = rolling_std([2, 4, 4, 4, 5, 5, 7, 9], 8)
    assert out[:7] == [None] * 7
    assert out[7] == pytest.approx(2.0)
    # window 2: [1,3] mean 2, deviations 1, 1 -> sqrt(2/2) = 1
    assert rolling_std([1, 3, 5], 2) == approx_list([None, 1, 1])
    assert rolling_std([4, 9], 1) == [0.0, 0.0]


def test_zscore_values():
    # window 2 on [1,3,3,2]: [1,3] mean 2 std 1 -> +1; [3,3] std 0 -> 0; [3,2] mean 2.5 std 0.5 -> -1
    assert zscore([1, 3, 3, 2], 2) == approx_list([None, 1, 0, -1])
    # window 3 on [10,10,4]: mean 8, deviations 2, 2, -4, var 24/3 = 8, z = -4/sqrt(8)
    assert zscore([10, 10, 4], 3)[2] == pytest.approx(-4 / math.sqrt(8))


def test_cmo_values():
    # period 3 on [10,11,10,12,12]
    # index 3: changes +1, -1, +2 -> U 3, D 1 -> 100*(3-1)/(3+1) = 50
    # index 4: changes -1, +2, 0   -> U 2, D 1 -> 100*(2-1)/(2+1) = 33.33
    assert cmo([10, 11, 10, 12, 12], 3) == approx_list([None, None, None, 50, 100 / 3])


def test_cmo_extremes_and_flat():
    assert cmo([1, 2, 3, 4], 3)[3] == pytest.approx(100.0)
    assert cmo([4, 3, 2, 1], 3)[3] == pytest.approx(-100.0)
    assert cmo([5, 5, 5, 5], 3)[3] == 0.0


def test_trix_values_and_warmup():
    # window 2 on 1..6: E3 = 2.5 (index 3), 3.5, 4.5
    # TRIX index 4: (3.5/2.5 - 1)*100 = 40; index 5: (4.5/3.5 - 1)*100 = 28.571...
    out = trix([1, 2, 3, 4, 5, 6], 2)
    assert out == approx_list([None, None, None, None, 40, (4.5 / 3.5 - 1) * 100])


def test_kama_hand_worked():
    # window 2, fast 2 (2/3), slow 30 (2/31); seed = close at index 1 = 12
    # index 2: travel |14-10| = 4, path 2 + 2 = 4, ER 1, sc = (2/3)^2 = 4/9, KAMA = 12 + 4/9*2
    # index 3: travel |13-12| = 1, path 2 + 1 = 3, ER 1/3, sc = (1/3*(2/3 - 2/31) + 2/31)^2 = (74/279)^2
    k2 = 12 + 4 / 9 * 2
    k3 = k2 + (74 / 279) ** 2 * (13 - k2)
    assert kama([10, 12, 14, 13], 2, 2, 30) == approx_list([None, 12, k2, k3])


def test_kama_flat_series_and_defaults():
    # ER 0 -> sc = (2/31)^2, but a flat series never moves
    assert kama([5.0] * 12) == approx_list([None] * 9 + [5.0] * 3)
    # default window 10: first value at index 9
    out = kama([float(i) for i in range(15)])
    assert out[8] is None and out[9] == 9.0
    # a straight line has ER 1, so sc = (2/3)^2 and KAMA trails below the line
    assert out[10] == pytest.approx(9 + 4 / 9 * (10 - 9))


def test_kama_short_input():
    assert kama([1, 2], 5) == [None, None]


def test_linreg_slope_values():
    # window 3, x = -1, 0, 1 about the mean: slope = (y2 - y0) / 2
    # [1,3,2] -> 0.5; [3,2,6] -> 1.5
    assert linreg_slope([1, 3, 2, 6], 3) == approx_list([None, None, 0.5, 1.5])
    # window 2 is the one-bar difference
    assert linreg_slope([1, 4, 2], 2) == approx_list([None, 3, -2])
    # a perfect line of slope 2.5
    assert linreg_slope([0, 2.5, 5, 7.5], 4)[3] == pytest.approx(2.5)


@pytest.mark.parametrize(
    "call",
    [
        lambda: wma([1, 2, 3], 0),
        lambda: dema([1, 2, 3], 0),
        lambda: tema([1, 2, 3], -1),
        lambda: hull_ma([1, 2, 3], 0),
        lambda: roc([1, 2, 3], 0),
        lambda: momentum([1, 2, 3], 0),
        lambda: rolling_std([1, 2, 3], 0),
        lambda: zscore([1, 2, 3], 1),
        lambda: cmo([1, 2, 3], 0),
        lambda: trix([1, 2, 3], 0),
        lambda: kama([1, 2, 3], 0),
        lambda: kama([1, 2, 3], 2, 0, 30),
        lambda: kama([1, 2, 3], 2, 30, 30),
        lambda: kama([1, 2, 3], 2, 2, 1),
        lambda: linreg_slope([1, 2, 3], 1),
        lambda: wma([1, 2, 3], 2.5),
        lambda: wma([1, 2, 3], True),
    ],
)
def test_bad_windows_raise(call):
    with pytest.raises(ValueError, match="must"):
        call()


def test_outputs_match_input_length():
    values = [float(i % 7 + 1) for i in range(40)]
    for fn in (wma, dema, tema, hull_ma, roc, momentum, rolling_std, cmo, trix, linreg_slope, zscore):
        assert len(fn(values, 5)) == len(values)
        assert len(fn([], 5)) == 0
    assert len(kama(values)) == len(values)
