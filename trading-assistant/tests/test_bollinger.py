"""Hand-worked tests for Bollinger bands.

Expected values were worked out by hand (shown in the comments) and are
written to 3 decimal places. The deviation is the population form: the sum of
squared deviations is divided by the window size, not by one less.
"""

import pytest

from trading_assistant.indicators import bollinger_bands


def assert_3dp(actual, expected):
    """None must line up exactly; numbers must match when rounded to 3 decimals."""
    assert len(actual) == len(expected)
    for i, (a, e) in enumerate(zip(actual, expected)):
        if e is None:
            assert a is None, f"index {i}: expected None, got {a!r}"
        else:
            assert a is not None, f"index {i}: expected {e}, got None"
            assert round(a, 3) == pytest.approx(e, abs=1e-9), f"index {i}: {a!r} != {e}"


def test_bollinger_hand_worked_window_3():
    # window 3, 2 deviations, on [2, 4, 6, 8, 7]
    #
    # idx2 [2, 4, 6]: mean 4, deviations -2, 0, 2, squares 4 + 0 + 4 = 8,
    #      variance 8/3, std sqrt(8/3) = 1.63299, 2*std = 3.26599
    #      upper 4 + 3.26599 = 7.266, lower 4 - 3.26599 = 0.734
    #      (dividing by 2 instead would give std 2 and bands 0 / 8)
    # idx3 [4, 6, 8]: mean 6, same spread -> upper 9.266, lower 2.734
    # idx4 [6, 8, 7]: mean 7, deviations -1, 1, 0, squares 2, variance 2/3,
    #      std sqrt(2/3) = 0.81650, 2*std = 1.63299
    #      upper 8.633, lower 5.367
    lower, middle, upper = bollinger_bands([2, 4, 6, 8, 7], window=3, num_std=2)
    assert_3dp(middle, [None, None, 4.0, 6.0, 7.0])
    assert_3dp(upper, [None, None, 7.266, 9.266, 8.633])
    assert_3dp(lower, [None, None, 0.734, 2.734, 5.367])


def test_bollinger_hand_worked_window_4_fractional_width():
    # window 4, 1.5 deviations, on [1, 3, 5, 7, 11]
    #
    # idx3 [1, 3, 5, 7]: mean 4, deviations -3, -1, 1, 3, squares 9 + 1 + 1 + 9 = 20,
    #      variance 20/4 = 5, std sqrt(5) = 2.23607, 1.5*std = 3.35410
    #      upper 7.354, lower 0.646
    # idx4 [3, 5, 7, 11]: mean 6.5, deviations -3.5, -1.5, 0.5, 4.5,
    #      squares 12.25 + 2.25 + 0.25 + 20.25 = 35, variance 35/4 = 8.75,
    #      std sqrt(8.75) = 2.95804, 1.5*std = 4.43706
    #      upper 10.937, lower 2.063
    lower, middle, upper = bollinger_bands([1, 3, 5, 7, 11], window=4, num_std=1.5)
    assert_3dp(middle, [None, None, None, 4.0, 6.5])
    assert_3dp(upper, [None, None, None, 7.354, 10.937])
    assert_3dp(lower, [None, None, None, 0.646, 2.063])


def test_bollinger_defaults_window_20_two_deviations():
    # 22 closes alternating 9, 11. Every 20-close window holds ten 9s and ten 11s:
    # mean 10, every deviation is +-1, variance 20/20 = 1, std 1.
    # Bands 10 -+ 2*1 = 8 and 12, first at index 19.
    # (dividing by 19 would give std sqrt(20/19) = 1.026 and bands 7.948 / 12.052)
    closes = [9.0, 11.0] * 11
    lower, middle, upper = bollinger_bands(closes)
    assert_3dp(middle, [None] * 19 + [10.0] * 3)
    assert_3dp(upper, [None] * 19 + [12.0] * 3)
    assert_3dp(lower, [None] * 19 + [8.0] * 3)


def test_bollinger_flat_series_bands_collapse_onto_middle():
    lower, middle, upper = bollinger_bands([5.0] * 4, window=3)
    assert_3dp(lower, [None, None, 5.0, 5.0])
    assert_3dp(middle, [None, None, 5.0, 5.0])
    assert_3dp(upper, [None, None, 5.0, 5.0])


def test_bollinger_zero_width_and_window_one():
    # 0 deviations: both bands sit on the SMA of [1, 5] (3) and [5, 3] (4)
    lower, middle, upper = bollinger_bands([1, 5, 3], window=2, num_std=0)
    assert_3dp(lower, [None, 3.0, 4.0])
    assert_3dp(upper, [None, 3.0, 4.0])
    # window 1: each close is its own mean with no spread
    lower, middle, upper = bollinger_bands([3, 1, 2], window=1)
    assert_3dp(lower, [3.0, 1.0, 2.0])
    assert_3dp(middle, [3.0, 1.0, 2.0])
    assert_3dp(upper, [3.0, 1.0, 2.0])


def test_bollinger_not_enough_history():
    # 19 closes is one short of the default 20-close window
    lower, middle, upper = bollinger_bands([float(i) for i in range(19)])
    assert lower == middle == upper == [None] * 19
    lower, middle, upper = bollinger_bands([1.0, 2.0], window=3)
    assert lower == middle == upper == [None, None]


def test_bollinger_empty_input():
    assert bollinger_bands([]) == ([], [], [])


def test_bollinger_outputs_match_input_length():
    values = [float(i % 7 + 1) for i in range(40)]
    for out in bollinger_bands(values):
        assert len(out) == len(values)
    for out in bollinger_bands(values, window=5, num_std=1):
        assert len(out) == len(values)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window": 0},
        {"window": 2.5},
        {"window": True},
        {"num_std": -1},
        {"num_std": "2"},
        {"num_std": True},
        {"num_std": float("nan")},
    ],
)
def test_bollinger_bad_parameters_raise(kwargs):
    with pytest.raises(ValueError, match="must"):
        bollinger_bands([1.0, 2.0, 3.0], **kwargs)
