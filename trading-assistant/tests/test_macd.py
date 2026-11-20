"""Hand-worked tests for the MACD indicator.

Expected values were worked out by hand (as fractions, shown in the comments)
and are written to 4 decimal places.
"""

import pytest

from trading_assistant.indicators import macd


def assert_4dp(actual, expected):
    """None must line up exactly; numbers must match when rounded to 4 decimals."""
    assert len(actual) == len(expected)
    for i, (a, e) in enumerate(zip(actual, expected)):
        if e is None:
            assert a is None, f"index {i}: expected None, got {a!r}"
        else:
            assert a is not None, f"index {i}: expected {e}, got None"
            assert round(a, 4) == pytest.approx(e, abs=1e-9), f"index {i}: {a!r} != {e}"


def test_macd_hand_worked_rising_series():
    # fast 2 (alpha 2/3), slow 3 (alpha 1/2), signal 2 (alpha 2/3) on [10, 12, 11, 14, 13, 15]
    #
    # EMA2: idx1 seed (10 + 12)/2 = 11
    #       idx2 2/3*11 + 1/3*11 = 11
    #       idx3 2/3*14 + 1/3*11 = 39/3 = 13
    #       idx4 2/3*13 + 1/3*13 = 13
    #       idx5 2/3*15 + 1/3*13 = 43/3 = 14.3333
    # EMA3: idx2 seed (10 + 12 + 11)/3 = 11
    #       idx3 1/2*14 + 1/2*11 = 12.5
    #       idx4 1/2*13 + 1/2*12.5 = 12.75
    #       idx5 1/2*15 + 1/2*12.75 = 13.875
    # MACD: idx2 11 - 11 = 0, idx3 13 - 12.5 = 0.5, idx4 13 - 12.75 = 0.25,
    #       idx5 43/3 - 111/8 = 11/24 = 0.4583
    # Signal (EMA2 of MACD, first MACD at idx2):
    #       idx3 seed (0 + 0.5)/2 = 0.25
    #       idx4 2/3*0.25 + 1/3*0.25 = 0.25
    #       idx5 2/3*11/24 + 1/3*1/4 = 11/36 + 3/36 = 7/18 = 0.3889
    # Histogram: idx3 0.5 - 0.25 = 0.25, idx4 0.25 - 0.25 = 0, idx5 11/24 - 7/18 = 5/72 = 0.0694
    line, signal, hist = macd([10, 12, 11, 14, 13, 15], fast=2, slow=3, signal=2)
    assert_4dp(line, [None, None, 0.0, 0.5, 0.25, 0.4583])
    assert_4dp(signal, [None, None, None, 0.25, 0.25, 0.3889])
    assert_4dp(hist, [None, None, None, 0.25, 0.0, 0.0694])


def test_macd_hand_worked_falling_series_goes_negative():
    # fast 1 (EMA1 is the closes), slow 2 (alpha 2/3), signal 2 (alpha 2/3) on [20, 18, 19, 15, 16]
    #
    # EMA2: idx1 seed (20 + 18)/2 = 19
    #       idx2 2/3*19 + 1/3*19 = 19
    #       idx3 2/3*15 + 1/3*19 = 49/3 = 16.3333
    #       idx4 2/3*16 + 1/3*49/3 = 145/9 = 16.1111
    # MACD: idx1 18 - 19 = -1, idx2 19 - 19 = 0, idx3 15 - 49/3 = -4/3 = -1.3333,
    #       idx4 16 - 145/9 = -1/9 = -0.1111
    # Signal (EMA2 of MACD, first MACD at idx1):
    #       idx2 seed (-1 + 0)/2 = -0.5
    #       idx3 2/3*(-4/3) + 1/3*(-1/2) = -8/9 - 1/6 = -19/18 = -1.0556
    #       idx4 2/3*(-1/9) + 1/3*(-19/18) = -4/54 - 19/54 = -23/54 = -0.4259
    # Histogram: idx2 0 + 0.5 = 0.5, idx3 -4/3 + 19/18 = -5/18 = -0.2778,
    #            idx4 -1/9 + 23/54 = 17/54 = 0.3148
    line, signal, hist = macd([20, 18, 19, 15, 16], fast=1, slow=2, signal=2)
    assert_4dp(line, [None, -1.0, 0.0, -1.3333, -0.1111])
    assert_4dp(signal, [None, None, -0.5, -1.0556, -0.4259])
    assert_4dp(hist, [None, None, 0.5, -0.2778, 0.3148])


def test_macd_defaults_on_a_straight_line():
    # Defaults 12 / 26 / 9. On the line 0, 1, 2, ... the SMA seed of an N-EMA at
    # index N-1 is the mean (N-1)/2, i.e. the close minus (N-1)/2. That lag is also
    # the EMA's steady-state lag on a slope of 1 ((1 - alpha)/alpha = (N-1)/2),
    # so EMA_N[i] = i - (N-1)/2 at every defined index.
    # MACD = (i - 5.5) - (i - 12.5) = 7 from index 25 (first 26-EMA value).
    # Signal = EMA9 of a constant 7 = 7 from index 25 + 8 = 33; histogram = 0.
    n = 40
    line, signal, hist = macd([float(i) for i in range(n)])
    assert_4dp(line, [None] * 25 + [7.0] * (n - 25))
    assert_4dp(signal, [None] * 33 + [7.0] * (n - 33))
    assert_4dp(hist, [None] * 33 + [0.0] * (n - 33))


def test_macd_flat_series_is_zero():
    line, signal, hist = macd([50.0] * 35)
    assert_4dp(line, [None] * 25 + [0.0] * 10)
    assert_4dp(signal, [None] * 33 + [0.0] * 2)
    assert_4dp(hist, [None] * 33 + [0.0] * 2)


def test_macd_not_enough_history():
    # 25 closes: one short of the first 26-EMA value, so everything is None
    line, signal, hist = macd([float(i) for i in range(25)])
    assert line == signal == hist == [None] * 25
    # 33 closes: MACD line is defined from index 25, but 8 MACD values are one
    # short of the first 9-EMA signal value
    line, signal, hist = macd([float(i) for i in range(33)])
    assert line[24] is None and line[25] is not None
    assert signal == hist == [None] * 33


def test_macd_empty_input():
    assert macd([]) == ([], [], [])


def test_macd_outputs_match_input_length():
    values = [float(i % 7 + 1) for i in range(60)]
    for out in macd(values):
        assert len(out) == len(values)
    for out in macd(values, fast=3, slow=5, signal=4):
        assert len(out) == len(values)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fast": 0},
        {"slow": 0},
        {"signal": 0},
        {"fast": 2.5},
        {"signal": True},
        {"fast": 26, "slow": 26},
        {"fast": 30, "slow": 26},
    ],
)
def test_macd_bad_parameters_raise(kwargs):
    with pytest.raises(ValueError, match="must"):
        macd([1.0, 2.0, 3.0], **kwargs)
