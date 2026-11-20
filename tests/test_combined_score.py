"""Hand-worked tests for combined_score with its default settings on 60-bar series.

Each series is built from flat runs, straight lines and one-bar jumps, so every
last-bar reading has a closed form worked out by hand in the comments:

* SMA20 / SMA50: arithmetic series sums.
* RSI 14 (Wilder): with r = 13/14, a run of k bars with no gain multiplies the
  average gain by r**k; the average loss stays 0 when there are no losses.
* EMA on a line of slope 1 seeded with an SMA sits exactly L = (N - 1) / 2
  below the line (the SMA seed already has that lag). So on the 100 + i
  ramps EMA12 = close - 5.5, EMA26 = close - 12.5, MACD line = 7, signal = 7.
  After the line changes course, the distance from the new steady state
  shrinks by a = 25/27 (EMA26), b = 11/13 (EMA12) and 0.8 (signal EMA9) per bar.
* Bollinger 20 / 2: population variance = mean of squares - square of mean,
  using 1^2 + ... + n^2 = n(n + 1)(2n + 1) / 6.

Powers such as a**10 and the square roots were evaluated with a calculator;
expected readings are written to 3 decimal places.
"""

import pytest

from trading_assistant.indicators import bollinger_bands, macd, rsi, sma
from trading_assistant.signals import combined_score


def readings(closes):
    """Last-bar values of every indicator the score looks at, rounded to 3 decimals."""
    lower, _, upper = bollinger_bands(closes)
    line, signal, hist = macd(closes)
    values = {
        "sma20": sma(closes, 20)[-1],
        "sma50": sma(closes, 50)[-1],
        "rsi": rsi(closes, 14)[-1],
        "macd_line": line[-1],
        "macd_signal": signal[-1],
        "macd_hist": hist[-1],
        "lower": lower[-1],
        "upper": upper[-1],
    }
    return {k: None if v is None else round(v, 3) for k, v in values.items()}


def check(closes, expected_readings, expected_parts):
    assert len(closes) == 60
    got = readings(closes)
    for key, value in expected_readings.items():
        assert got[key] == pytest.approx(value, abs=1e-9), f"{key}: {got[key]} != {value}"
    score, parts = combined_score(closes)
    assert parts == expected_parts
    assert score == sum(expected_parts.values())
    return score


def test_flat_then_jump_up():
    # 59 closes of 100, then 110.
    # SMA20 = (19*100 + 110)/20 = 100.5 > SMA50 = (49*100 + 110)/50 = 100.2   -> crossover +1
    # RSI: no losses at all, average loss 0 -> RSI 100 (over 70)              -> rsi -1
    # MACD: everything sits at 100 until the last bar, then
    #   EMA12 = 100 + 2/13*10, EMA26 = 100 + 2/27*10, line = 10*(2/13 - 2/27) = 280/351 = 0.798
    #   signal = 0.2*0.798 = 56/351 = 0.160, histogram = 224/351 = 0.638 > 0  -> macd +1
    # Bollinger: 19 x 100 and one 110, mean 100.5, deviations 19 x -0.5 and 9.5,
    #   variance (19*0.25 + 90.25)/20 = 4.75, std sqrt(4.75) = 2.179,
    #   bands 100.5 -+ 4.359 = 96.141 / 104.859; 110 > 104.859                 -> bollinger -1
    closes = [100.0] * 59 + [110.0]
    score = check(
        closes,
        {"sma20": 100.5, "sma50": 100.2, "rsi": 100.0, "macd_line": 0.798,
         "macd_signal": 0.160, "macd_hist": 0.638, "lower": 96.141, "upper": 104.859},
        {"crossover": 1, "rsi": -1, "macd": 1, "bollinger": -1},
    )
    assert score == 0


def test_flat_then_drop():
    # 59 closes of 100, then 90: the mirror image of the jump.
    # SMA20 99.5 < SMA50 99.8                                              -> crossover -1
    # RSI: no gains, average loss 10/14 > 0 -> RS 0 -> RSI 0 (under 30)      -> rsi +1
    # MACD: line -0.798, signal -0.160, histogram -0.638 < 0                 -> macd -1
    # Bollinger: mean 99.5, std 2.179, bands 95.141 / 103.859; 90 < 95.141   -> bollinger +1
    closes = [100.0] * 59 + [90.0]
    score = check(
        closes,
        {"sma20": 99.5, "sma50": 99.8, "rsi": 0.0, "macd_line": -0.798,
         "macd_signal": -0.160, "macd_hist": -0.638, "lower": 95.141, "upper": 103.859},
        {"crossover": -1, "rsi": 1, "macd": -1, "bollinger": 1},
    )
    assert score == 0


def test_rise_then_flat():
    # closes 100, 101, ..., 149 (50 bars), then 149 for 10 more bars.
    # SMA20: 140..149 (sum 1445) + 10 x 149 (1490) = 2935/20 = 146.75
    # SMA50: 110..149 (40 * 129.5 = 5180) + 1490 = 6670/50 = 133.4          -> crossover +1
    # RSI: average gain 1 after the ramp, then r**10 = 0.477; no losses -> 100 -> rsi -1
    # MACD: at index 49 EMA12 = 149 - 5.5, EMA26 = 149 - 12.5, line 7, signal 7.
    #   After k flat bars: line = 12.5*a**k - 5.5*b**k
    #   signal = 7*0.8**k + 0.2*(12.5*a*(a**k - 0.8**k)/(a - 0.8) - 5.5*b*(b**k - 0.8**k)/(b - 0.8))
    #   k = 10: line 4.755, signal 5.664, histogram -0.908 < 0              -> macd -1
    # Bollinger: 140..148 and 11 x 149, mean 146.75, squared deviations
    #   128.0625 + 11*5.0625 = 183.75, variance 9.1875, std 3.031,
    #   bands 140.688 / 152.812; 149 is inside                              -> bollinger 0
    closes = [100.0 + i for i in range(50)] + [149.0] * 10
    score = check(
        closes,
        {"sma20": 146.75, "sma50": 133.4, "rsi": 100.0, "macd_line": 4.755,
         "macd_signal": 5.664, "macd_hist": -0.908, "lower": 140.688, "upper": 152.812},
        {"crossover": 1, "rsi": -1, "macd": -1, "bollinger": 0},
    )
    assert score == -1


def rise_flat_jump():
    # closes 100..149 (50 bars), 149 for 9 bars, then 155.
    return [100.0 + i for i in range(50)] + [149.0] * 9 + [155.0]


def test_rise_flat_then_jump_scores_minus_two():
    # SMA20: 1445 + 9*149 + 155 = 2941/20 = 147.05
    # SMA50: 5180 + 1341 + 155 = 6676/50 = 133.52                           -> crossover +1
    # RSI: still no losses -> 100                                           -> rsi -1
    # MACD: the flat-run values for k = 10 plus the extra 6 on the last close:
    #   line = 4.755 + 6*28/351 (0.479) = 5.234, signal = 5.664 + 0.2*0.479 = 5.759,
    #   histogram = -0.908 + 0.8*0.479 = -0.526 < 0                          -> macd -1
    # Bollinger: sum of squares 140^2..148^2 = S(148) - S(139) = 186684,
    #   + 10*149^2 = 222010, + 155^2 = 24025 -> 432719/20 = 21635.95,
    #   variance 21635.95 - 147.05^2 = 12.2475, std 3.500,
    #   bands 140.051 / 154.049; 155 > 154.049                              -> bollinger -1
    score = check(
        rise_flat_jump(),
        {"sma20": 147.05, "sma50": 133.52, "rsi": 100.0, "macd_line": 5.234,
         "macd_signal": 5.759, "macd_hist": -0.526, "lower": 140.051, "upper": 154.049},
        {"crossover": 1, "rsi": -1, "macd": -1, "bollinger": -1},
    )
    assert score == -2


def test_mirror_of_rise_flat_jump_scores_plus_two():
    # closes 300 - x: averages and bands reflect about 150, the MACD values flip
    # sign, and with no gains at all the RSI is 0 instead of 100.
    # SMA20 300 - 147.05 = 152.95 < SMA50 300 - 133.52 = 166.48             -> crossover -1
    # RSI 0                                                                 -> rsi +1
    # MACD histogram +0.526                                                 -> macd +1
    # bands 300 - 154.049 = 145.951 / 300 - 140.051 = 159.949; 145 < 145.951 -> bollinger +1
    closes = [300.0 - c for c in rise_flat_jump()]
    score = check(
        closes,
        {"sma20": 152.95, "sma50": 166.48, "rsi": 0.0, "macd_line": -5.234,
         "macd_signal": -5.759, "macd_hist": 0.526, "lower": 145.951, "upper": 159.949},
        {"crossover": -1, "rsi": 1, "macd": 1, "bollinger": 1},
    )
    assert score == 2


def test_rise_then_one_bar_drop_rsi_in_the_middle():
    # closes 100..158 (59 bars), then 140 (19 below where the line would be).
    # SMA20: 140..158 (19 * 149 = 2831) + 140 = 2971/20 = 148.55
    # SMA50: 110..158 (49 * 134 = 6566) + 140 = 6706/50 = 134.12            -> crossover +1
    # RSI: average gain 1, loss 0 before the drop; then gain 13/14, loss 18/14,
    #   RSI = 100 * 13 / (13 + 18) = 41.935, between 30 and 70                -> rsi 0
    # MACD: the line would stay 7; the close is 19 below the line, so
    #   line = 7 - 19*28/351 = 5.484, signal = 7 - 0.2*19*28/351 = 6.697,
    #   histogram = -0.8*19*28/351 = -1.213 < 0                              -> macd -1
    # Bollinger: S(158) - S(139) = 422389, + 140^2 = 441989, /20 = 22099.45,
    #   variance 22099.45 - 148.55^2 = 32.3475, std 5.687,
    #   bands 137.175 / 159.925; 140 is inside                              -> bollinger 0
    closes = [100.0 + i for i in range(59)] + [140.0]
    score = check(
        closes,
        {"sma20": 148.55, "sma50": 134.12, "rsi": 41.935, "macd_line": 5.484,
         "macd_signal": 6.697, "macd_hist": -1.213, "lower": 137.175, "upper": 159.925},
        {"crossover": 1, "rsi": 0, "macd": -1, "bollinger": 0},
    )
    assert score == 0


def test_rise_then_long_fall_rsi_under_30():
    # closes 100..142 (43 bars), then 141 down to 125 (17 bars).
    # SMA20: 140 + 141 + 142 + (141..125: 17 * 133 = 2261) = 2684/20 = 134.2
    # SMA50: 110..142 (33 * 126 = 4158) + 2261 = 6419/50 = 128.38           -> crossover +1
    # RSI: 17 losses of 1 after the ramp; average gain r**17, average loss
    #   1 - r**17 (they always add up to 1), so RSI = 100 * r**17 = 28.370    -> rsi +1
    # MACD: on the falling line the steady state is close + L, and the EMA
    #   starts 2L below it, so EMA = close + L - 2L * (decay)**k.
    #   line = -7 - 11*b**k + 25*a**k
    #   signal = 7*0.8**k - 7*(1 - 0.8**k)
    #            + 0.2*(-11*b*(b**k - 0.8**k)/(b - 0.8) + 25*a*(a**k - 0.8**k)/(a - 0.8))
    #   k = 17: line -0.886, signal 0.975, histogram -1.861 < 0            -> macd -1
    # Bollinger: 140^2 + 141^2 + 142^2 = 59645, S(141) - S(124) = 301121,
    #   total 360766/20 = 18038.3, variance 18038.3 - 134.2^2 = 28.66,
    #   std 5.354, bands 123.493 / 144.907; 125 is inside                   -> bollinger 0
    closes = [100.0 + i for i in range(43)] + [141.0 - i for i in range(17)]
    assert closes[-1] == 125.0
    score = check(
        closes,
        {"sma20": 134.2, "sma50": 128.38, "rsi": 28.370, "macd_line": -0.886,
         "macd_signal": 0.975, "macd_hist": -1.861, "lower": 123.493, "upper": 144.907},
        {"crossover": 1, "rsi": 1, "macd": -1, "bollinger": 0},
    )
    assert score == 1


def test_flat_series_ties_count_as_zero():
    # 60 closes of 100: SMA20 = SMA50 = 100 (equal)                          -> crossover 0
    # MACD line, signal and histogram are exactly 0                          -> macd 0
    # Bollinger std 0, both bands 100, the close sits on them, not beyond    -> bollinger 0
    # RSI: the existing rsi() returns 100 whenever the average loss is 0,
    #   even with no gains either, so a flat series reads over 70            -> rsi -1
    score = check(
        [100.0] * 60,
        {"sma20": 100.0, "sma50": 100.0, "rsi": 100.0, "macd_line": 0.0,
         "macd_signal": 0.0, "macd_hist": 0.0, "lower": 100.0, "upper": 100.0},
        {"crossover": 0, "rsi": -1, "macd": 0, "bollinger": 0},
    )
    assert score == -1


def test_missing_history_counts_as_zero():
    # 48 closes of 100, then 110 (49 bars): one short of SMA50 -> crossover 0.
    # The others are the same as in the 60-bar jump test: RSI 100 -> -1,
    # histogram 224/351 = 0.638 -> +1, upper band 104.859 < 110 -> -1.
    score, parts = combined_score([100.0] * 48 + [110.0])
    assert parts == {"crossover": 0, "rsi": -1, "macd": 1, "bollinger": -1}
    assert score == -1
    # 10 bars: nothing has enough history yet
    assert combined_score([float(i) for i in range(10)]) == (
        0,
        {"crossover": 0, "rsi": 0, "macd": 0, "bollinger": 0},
    )
    assert combined_score([]) == (0, {"crossover": 0, "rsi": 0, "macd": 0, "bollinger": 0})


def test_short_must_be_less_than_long():
    with pytest.raises(ValueError, match="smaller"):
        combined_score([1.0] * 60, short=50, long=50)
