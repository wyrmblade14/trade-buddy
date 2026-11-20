"""Turn price history into a BUY / SELL / HOLD suggestion, and say why.

This is a research aid. It does not place orders and it is not financial advice.
"""

import math

from .indicators import bollinger_bands, macd, rsi, sma

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"


def crossover_signal(closes, short=20, long=50):
    """BUY when the short SMA crosses above the long SMA, SELL on the reverse.

    Only the most recent bar is checked for a cross. Anything else is HOLD.
    """
    if short >= long:
        raise ValueError("short window must be smaller than long window")
    if len(closes) < long + 1:
        return HOLD

    short_ma = sma(closes, short)
    long_ma = sma(closes, long)
    prev_short, prev_long = short_ma[-2], long_ma[-2]
    cur_short, cur_long = short_ma[-1], long_ma[-1]

    if prev_short <= prev_long and cur_short > cur_long:
        return BUY
    if prev_short >= prev_long and cur_short < cur_long:
        return SELL
    return HOLD


def explain_crossover(closes, short=20, long=50):
    """One sentence explaining the ``crossover_signal`` decision for ``closes``.

    The decision is taken from ``crossover_signal`` itself (same closes and
    windows) and is the sentence's first word. The sentence gives the short
    and long SMA on the last bar and on the bar before (``n/a`` where there is
    not enough history yet) and says why. A HOLD sentence never says
    "crossed". Each bar's pair is printed with 2 decimals, or with as many more
    as it takes to tell the two apart when they differ but look the same at 2.
    Raises ValueError like ``crossover_signal`` for bad windows, and for a
    close that is not a finite number.
    """
    return _explain(closes, short, long)[1]


def explain_crossover_data(closes, short=20, long=50):
    """``explain_crossover`` as plain values, for a JSON reply.

    Returns ``{"decision", "sentence", "last_bar", "previous_bar"}``: the
    ``crossover_signal`` decision, the ``explain_crossover`` sentence, and the
    short and long SMA (unrounded; None where there is not enough history) on
    the last bar and on the bar before, each as ``{"short": ..., "long": ...}``.
    All four come from one computation, so they always agree.
    """
    signal, sentence, last, before = _explain(closes, short, long)
    return {
        "decision": signal,
        "sentence": sentence,
        "last_bar": {"short": last[0], "long": last[1]},
        "previous_bar": {"short": before[0], "long": before[1]},
    }


def _explain(closes, short, long):
    """``(decision, sentence, (short, long) on the last bar, (short, long) on the bar before)``."""
    signal = crossover_signal(closes, short=short, long=long)
    if not all(math.isfinite(c) for c in closes):
        raise ValueError("closes must be finite numbers")
    short_ma, long_ma = sma(closes, short), sma(closes, long)
    cur_short, cur_long = _at(short_ma, -1), _at(long_ma, -1)
    prev_short, prev_long = _at(short_ma, -2), _at(long_ma, -2)
    last = _pair(cur_short, cur_long)
    before = _pair(prev_short, prev_long)
    names = f"the {short}-bar SMA", f"the {long}-bar SMA"

    if signal == BUY:
        sentence = f"BUY because {names[0]} crossed above {names[1]}: {last} on the last bar, after {before} on the bar before."
    elif signal == SELL:
        sentence = f"SELL because {names[0]} crossed below {names[1]}: {last} on the last bar, after {before} on the bar before."
    elif len(closes) < long + 1:
        have = "there is 1" if len(closes) == 1 else f"there are {len(closes)}"
        sentence = (
            f"HOLD because a crossover needs at least {long + 1} bars and {have}: "
            f"{last} on the last bar and {before} on the bar before."
        )
    else:
        # A HOLD with enough bars: the rule in crossover_signal means a short SMA
        # above (below) the long one on the last bar was already above (below) it.
        if cur_short > cur_long:
            why = f"{names[0]} stayed above {names[1]}, so there is no new crossover"
        elif cur_short < cur_long:
            why = f"{names[0]} stayed below {names[1]}, so there is no new crossover"
        else:
            why = f"{names[0]} ended level with {names[1]}, so there is no crossover"
        sentence = f"HOLD because {why}: {last} on the last bar and {before} on the bar before."
    return signal, sentence, (cur_short, cur_long), (prev_short, prev_long)


def _at(series, index):
    """``series[index]``, or None when the series is too short."""
    return series[index] if len(series) >= abs(index) else None


def _pair(short_value, long_value):
    """``"S against L"`` with 2 decimals, more if needed to tell different values apart; None prints as n/a."""
    if short_value is None or long_value is None:
        return f"{_fixed(short_value, 2)} against {_fixed(long_value, 2)}"
    decimals = 2
    while short_value != long_value and float(_fixed(short_value, decimals)) == float(_fixed(long_value, decimals)):
        decimals += 1
    return f"{_fixed(short_value, decimals)} against {_fixed(long_value, decimals)}"


def _fixed(value, decimals):
    return "n/a" if value is None else f"{value:.{decimals}f}"


def rsi_filter(closes, period=14, overbought=70, oversold=30):
    """Return the latest RSI reading and a label: overbought, oversold or neutral."""
    latest = rsi(closes, period)[-1]
    if latest is None:
        return None, "neutral"
    if latest >= overbought:
        return latest, "overbought"
    if latest <= oversold:
        return latest, "oversold"
    return latest, "neutral"


def combined_score(closes, short=20, long=50, rsi_period=14):
    """Add up four indicator votes on the last bar into one score from -4 to 4.

    Each part is +1, 0 or -1, and the score is their sum:

    * Crossover: +1 when the short simple moving average is above the long
      one on the last bar, -1 when it is below, 0 when they are equal.
    * RSI: +1 when the RSI (``rsi_period`` bars) is under 30, -1 when it is
      over 70, 0 otherwise (exactly 30 or 70 counts as 0).
    * MACD: +1 when the MACD histogram (default 12 / 26 / 9) is above 0 on the
      last bar, -1 when it is below 0, 0 when it is exactly 0.
    * Bollinger: +1 when the last close is below the lower band (default 20
      bars, 2 deviations), -1 when it is above the upper band, 0 otherwise
      (a close exactly on a band counts as 0).

    A part whose indicator has no value on the last bar yet (not enough
    history) counts as 0.

    Returns ``(score, parts)`` where ``parts`` is a dict with the keys
    ``"crossover"``, ``"rsi"``, ``"macd"`` and ``"bollinger"`` holding each
    part's contribution.
    """
    if short >= long:
        raise ValueError("short window must be smaller than long window")

    short_ma = _last(sma(closes, short))
    long_ma = _last(sma(closes, long))
    if short_ma is None or long_ma is None:
        crossover_part = 0
    else:
        crossover_part = _sign(short_ma - long_ma)

    latest_rsi = _last(rsi(closes, rsi_period))
    if latest_rsi is not None and latest_rsi < 30:
        rsi_part = 1
    elif latest_rsi is not None and latest_rsi > 70:
        rsi_part = -1
    else:
        rsi_part = 0

    histogram = _last(macd(closes)[2])
    macd_part = 0 if histogram is None else _sign(histogram)

    lower, _, upper = bollinger_bands(closes)
    lower, upper = _last(lower), _last(upper)
    if lower is not None and closes[-1] < lower:
        bollinger_part = 1
    elif upper is not None and closes[-1] > upper:
        bollinger_part = -1
    else:
        bollinger_part = 0

    parts = {
        "crossover": crossover_part,
        "rsi": rsi_part,
        "macd": macd_part,
        "bollinger": bollinger_part,
    }
    return sum(parts.values()), parts


def _last(series):
    return series[-1] if series else None


def _sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0
