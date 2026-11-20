"""Technical indicators over a list of closing prices.

Every function returns a list the same length as its input. Positions that
do not yet have enough history are None.
"""

import math


def sma(values, window):
    """Simple moving average."""
    _check_window(window)
    out = [None] * len(values)
    if len(values) < window:
        return out
    running = sum(values[:window])
    out[window - 1] = running / window
    for i in range(window, len(values)):
        running += values[i] - values[i - window]
        out[i] = running / window
    return out


def ema(values, window):
    """Exponential moving average, seeded with the first SMA value."""
    _check_window(window)
    out = [None] * len(values)
    if len(values) < window:
        return out
    alpha = 2 / (window + 1)
    out[window - 1] = sum(values[:window]) / window
    for i in range(window, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(values, period=14):
    """Relative Strength Index using Wilder's smoothing."""
    _check_window(period)
    out = [None] * len(values)
    if len(values) <= period:
        return out

    gains = []
    losses = []
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = _rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain, avg_loss):
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _check_window(window):
    if window < 1:
        raise ValueError("window must be at least 1")


def wma(values, window):
    """Weighted moving average with linear weights.

    The newest close in each window has weight ``window``, the one before it
    ``window - 1``, down to weight 1 for the oldest; the sum is divided by
    ``window * (window + 1) / 2``. The first ``window - 1`` values are None.
    """
    _check_int("window", window)
    out = [None] * len(values)
    divisor = window * (window + 1) / 2
    for i in range(window - 1, len(values)):
        total = 0.0
        for weight, value in enumerate(values[i - window + 1 : i + 1], start=1):
            total += weight * value
        out[i] = total / divisor
    return out


def dema(values, window):
    """Double exponential moving average: ``2 * EMA - EMA(EMA)``.

    The first ``2 * (window - 1)`` values are None.
    """
    _check_int("window", window)
    first = ema(values, window)
    second = _ema_of_series(first, window)
    return [None if b is None else 2 * a - b for a, b in zip(first, second)]


def tema(values, window):
    """Triple exponential moving average: ``3 * E1 - 3 * E2 + E3``.

    ``E1`` is the EMA of the closes, ``E2`` the EMA of ``E1`` and ``E3`` the
    EMA of ``E2``. The first ``3 * (window - 1)`` values are None.
    """
    _check_int("window", window)
    e1 = ema(values, window)
    e2 = _ema_of_series(e1, window)
    e3 = _ema_of_series(e2, window)
    return [None if c is None else 3 * a - 3 * b + c for a, b, c in zip(e1, e2, e3)]


def hull_ma(values, window):
    """Hull moving average.

    ``WMA(2 * WMA(values, window // 2) - WMA(values, window), isqrt(window))``
    where the half window is at least 1 and ``isqrt`` is the integer square
    root (floor). The first ``window - 1 + isqrt(window) - 1`` values are None.
    """
    _check_int("window", window)
    half = wma(values, max(1, window // 2))
    full = wma(values, window)
    raw = [None if f is None else 2 * h - f for h, f in zip(half, full)]
    return _wma_of_series(raw, math.isqrt(window))


def roc(values, window):
    """Rate of change in percent: ``(close / earlier close - 1) * 100``.

    The earlier close is the one ``window`` bars back.

    The first ``window`` values are None. Raises ValueError if a divisor close
    is zero.
    """
    _check_int("window", window)
    out = [None] * len(values)
    for i in range(window, len(values)):
        base = values[i - window]
        if base == 0:
            raise ValueError("rate of change is undefined when a close is zero")
        out[i] = (values[i] / base - 1) * 100
    return out


def momentum(values, window):
    """Price difference: the close minus the close ``window`` bars back.

    The first ``window`` values are None.
    """
    _check_int("window", window)
    out = [None] * len(values)
    for i in range(window, len(values)):
        out[i] = values[i] - values[i - window]
    return out


def rolling_std(values, window):
    """Rolling standard deviation over the last ``window`` closes.

    This is the population form (divide by ``window``, not ``window - 1``), so
    a window of 1 gives 0. The first ``window - 1`` values are None.
    """
    _check_int("window", window)
    out = [None] * len(values)
    for i in range(window - 1, len(values)):
        chunk = values[i - window + 1 : i + 1]
        mean = sum(chunk) / window
        out[i] = math.sqrt(sum((v - mean) ** 2 for v in chunk) / window)
    return out


def zscore(values, window):
    """Distance of the close from its SMA in rolling population standard deviations.

    ``(close - SMA) / rolling_std`` over the same window; 0.0 when the
    standard deviation is 0 (a flat window). ``window`` must be at least 2,
    since a single close is always its own mean. The first ``window - 1``
    values are None.
    """
    _check_int("window", window, minimum=2)
    means = sma(values, window)
    stds = rolling_std(values, window)
    return [
        None if m is None else (0.0 if s == 0 else (v - m) / s)
        for v, m, s in zip(values, means, stds)
    ]


def cmo(values, period=14):
    """Chande momentum oscillator, from -100 to 100.

    ``100 * (U - D) / (U + D)`` where ``U`` is the sum of the up-moves and
    ``D`` the sum of the down-moves (as a positive number) over the last
    ``period`` changes; 0.0 when no close changed. The first ``period`` values
    are None.
    """
    _check_int("period", period)
    out = [None] * len(values)
    for i in range(period, len(values)):
        up = down = 0.0
        for j in range(i - period + 1, i + 1):
            change = values[j] - values[j - 1]
            if change > 0:
                up += change
            else:
                down -= change
        out[i] = 0.0 if up + down == 0 else 100 * (up - down) / (up + down)
    return out


def trix(values, window):
    """TRIX: the one-bar percent change of a triple-smoothed EMA.

    ``(E3[i] / E3[i - 1] - 1) * 100`` where ``E3`` is the EMA of the EMA of the
    EMA of the closes. The first ``3 * (window - 1) + 1`` values are None.
    Raises ValueError if ``E3`` is zero.
    """
    _check_int("window", window)
    e3 = _ema_of_series(_ema_of_series(ema(values, window), window), window)
    out = [None] * len(values)
    for i in range(1, len(values)):
        if e3[i] is None or e3[i - 1] is None:
            continue
        if e3[i - 1] == 0:
            raise ValueError("TRIX is undefined when the smoothed average is zero")
        out[i] = (e3[i] / e3[i - 1] - 1) * 100
    return out


def kama(values, window=10, fast=2, slow=30):
    """Kaufman adaptive moving average.

    Efficiency ratio ``ER = |close - close[window bars ago]| / sum of the
    absolute one-bar changes over the window`` (0 when that sum is 0). The
    smoothing constant is ``(ER * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1)) ** 2``
    and ``KAMA = previous + constant * (close - previous)``. It is seeded with
    the close at index ``window - 1``, so the first ``window - 1`` values are
    None. ``fast`` must be smaller than ``slow``.
    """
    _check_int("window", window)
    _check_int("fast", fast)
    _check_int("slow", slow)
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")
    out = [None] * len(values)
    if len(values) < window:
        return out
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    out[window - 1] = float(values[window - 1])
    for i in range(window, len(values)):
        travel = abs(values[i] - values[i - window])
        path = sum(abs(values[j] - values[j - 1]) for j in range(i - window + 1, i + 1))
        er = 0.0 if path == 0 else travel / path
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        out[i] = out[i - 1] + sc * (values[i] - out[i - 1])
    return out


def linreg_slope(values, window):
    """Least-squares slope of the last ``window`` closes against 0, 1, ..., window - 1.

    Units are price per bar. ``window`` must be at least 2. The first
    ``window - 1`` values are None.
    """
    _check_int("window", window, minimum=2)
    out = [None] * len(values)
    x_mean = (window - 1) / 2
    x_var = sum((x - x_mean) ** 2 for x in range(window))
    for i in range(window - 1, len(values)):
        chunk = values[i - window + 1 : i + 1]
        y_mean = sum(chunk) / window
        cov = sum((x - x_mean) * (y - y_mean) for x, y in enumerate(chunk))
        out[i] = cov / x_var
    return out


def macd(values, fast=12, slow=26, signal=9):
    """Moving average convergence/divergence.

    Returns three lists, each the same length as ``values``:

    * ``macd_line = EMA(values, fast) - EMA(values, slow)``
    * ``signal_line = EMA(macd_line, signal)``, seeded like ``ema`` with the
      SMA of the first ``signal`` MACD values
    * ``histogram = macd_line - signal_line``

    The MACD line starts at index ``slow - 1``; the signal line and histogram
    start at index ``slow - 1 + signal - 1``. Earlier positions are None.
    ``fast`` must be smaller than ``slow``.
    """
    _check_int("fast", fast)
    _check_int("slow", slow)
    _check_int("signal", signal)
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line = [None if s is None else f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = _ema_of_series(macd_line, signal)
    histogram = [None if g is None else m - g for m, g in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def bollinger_bands(values, window=20, num_std=2.0):
    """Bollinger bands around a simple moving average.

    Returns three lists, each the same length as ``values``:

    * ``lower = SMA - num_std * rolling_std``
    * ``middle = SMA(values, window)``
    * ``upper = SMA + num_std * rolling_std``

    The deviation is the population form from ``rolling_std`` (divide by
    ``window``, not ``window - 1``). The first ``window - 1`` values are None.
    ``num_std`` must be a number of at least 0.
    """
    _check_int("window", window)
    if isinstance(num_std, bool) or not isinstance(num_std, (int, float)) or not num_std >= 0:
        raise ValueError(f"num_std must be a number of at least 0, got {num_std!r}")
    middle = sma(values, window)
    stds = rolling_std(values, window)
    lower = [None if m is None else m - num_std * s for m, s in zip(middle, stds)]
    upper = [None if m is None else m + num_std * s for m, s in zip(middle, stds)]
    return lower, middle, upper


def atr(highs, lows, closes, period=14):
    """Average true range using Wilder's smoothing.

    The true range of bar 0 is ``high - low``. From bar 1 on it is the largest
    of ``high - low``, ``|high - previous close|`` and ``|low - previous close|``.

    The first ATR value, at index ``period - 1``, is the plain average of the
    first ``period`` true ranges. After that each value is
    ``(previous ATR * (period - 1) + true range) / period``. Earlier positions
    are None, and if there are fewer bars than ``period`` every value is None.

    Raises ValueError if ``period`` is not a whole number of at least 1, if the
    three lists differ in length, or if any high is below its low.
    """
    _check_int("period", period)
    if not len(highs) == len(lows) == len(closes):
        raise ValueError(
            "highs, lows and closes must be the same length, got "
            f"{len(highs)}, {len(lows)} and {len(closes)}"
        )
    for i, (high, low) in enumerate(zip(highs, lows)):
        if high < low:
            raise ValueError(f"high {high!r} is below low {low!r} at index {i}")

    out = [None] * len(highs)
    if len(highs) < period:
        return out

    true_ranges = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        prev_close = closes[i - 1]
        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        )

    out[period - 1] = sum(true_ranges[:period]) / period
    for i in range(period, len(highs)):
        out[i] = (out[i - 1] * (period - 1) + true_ranges[i]) / period
    return out


def _check_int(name, value, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a whole number of at least {minimum}, got {value!r}")


def _defined_tail(series):
    """Index of the first non-None entry (len(series) if there is none)."""
    for i, value in enumerate(series):
        if value is not None:
            return i
    return len(series)


def _ema_of_series(series, window):
    """EMA of a series whose leading entries are None; the None prefix is kept."""
    start = _defined_tail(series)
    return [None] * start + ema(series[start:], window)


def _wma_of_series(series, window):
    start = _defined_tail(series)
    return [None] * start + wma(series[start:], window)
