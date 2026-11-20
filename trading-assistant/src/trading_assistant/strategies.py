"""Trading strategies: each turns a close history into BUY / SELL / HOLD.

A strategy is a plain function ``(closes, t, **params) -> signal``. It may
read ``closes[0..t]`` only: a signal for bar ``t`` is what was knowable at
the close of bar ``t``, so nothing after ``t`` can leak in. During warm-up
(not enough history yet) every strategy returns HOLD.

``STRATEGIES`` maps a name to ``(function, default params, description)``.
``first_signal_bars(name, params)`` is the fewest closes with which a
strategy can give a BUY or SELL on the last of them; the portfolio needs one
more shared date than that, to fill the signal. ``check_param_value(name,
key, value)`` checks one parameter value on its own (for parameter grids).
This is a research aid. It places no orders and it is not financial advice.
"""

import math

from .indicators import ema, hull_ma, roc, rsi, zscore
from .signals import BUY, HOLD, SELL


def sma_cross(closes, t, short=20, long=50):
    """BUY when the short SMA crosses above the long SMA on bar ``t``, SELL on the reverse.

    This is the backtest's original rule, delegated to ``signal_at`` (and so
    to ``crossover_signal``) so the results are identical; ``short >= long``
    raises ValueError there.
    """
    from .backtest import signal_at  # imported here: backtest imports this module

    return signal_at(closes, t, short=short, long=long)


def rsi_reversion(closes, t, period=14, oversold=30, overbought=70):
    """BUY when RSI crosses up through ``oversold`` on bar ``t``, SELL when it crosses down through ``overbought``.

    BUY: RSI on bar ``t - 1`` is below ``oversold`` and RSI on bar ``t`` is
    ``oversold`` or higher. SELL: RSI on bar ``t - 1`` is above ``overbought``
    and RSI on bar ``t`` is ``overbought`` or lower. Anything else, including
    bars without two RSI readings yet, is HOLD.
    """
    _check_rsi_reversion(period, oversold, overbought)
    if t < 1:
        return HOLD
    # RSI at bar t depends only on closes[0..t]; slice so that is explicit.
    readings = rsi(closes[: t + 1], period)
    prev, cur = readings[t - 1], readings[t]
    if prev is None or cur is None:
        return HOLD
    if prev < oversold and cur >= oversold:
        return BUY
    if prev > overbought and cur <= overbought:
        return SELL
    return HOLD


def breakout(closes, t, window=20):
    """BUY when ``closes[t]`` is above the highest of the previous ``window`` closes, SELL when below the lowest.

    The previous closes are ``closes[t - window:t]``; bar ``t`` itself is not
    part of the range. Equal to the high or low is HOLD, as is any bar with
    fewer than ``window`` earlier closes.
    """
    _check_breakout(window)
    if t < window:
        return HOLD
    prior = closes[t - window : t]
    if closes[t] > max(prior):
        return BUY
    if closes[t] < min(prior):
        return SELL
    return HOLD


def ema_cross(closes, t, short=12, long=26):
    """BUY when the short EMA crosses above the long EMA on bar ``t``, SELL on the reverse.

    BUY: short EMA <= long EMA on bar ``t - 1`` and short EMA > long EMA on
    bar ``t``. SELL: short >= long before and short < long now. Bars without
    two readings of the long EMA are HOLD. ``short >= long`` raises ValueError.
    """
    _check_ema_cross(short, long)
    if t < 1:
        return HOLD
    prefix = closes[: t + 1]
    fast = ema(prefix, short)
    slow = ema(prefix, long)
    if slow[t - 1] is None:
        return HOLD
    if fast[t - 1] <= slow[t - 1] and fast[t] > slow[t]:
        return BUY
    if fast[t - 1] >= slow[t - 1] and fast[t] < slow[t]:
        return SELL
    return HOLD


def momentum(closes, t, window=20, threshold=0.0):
    """BUY when the rate of change crosses up through ``threshold`` on bar ``t``, SELL when it crosses down.

    The rate of change is in percent over ``window`` bars. BUY: ROC on bar
    ``t - 1`` is ``threshold`` or lower and ROC on bar ``t`` is above it.
    SELL: ROC before is ``threshold`` or higher and ROC now is below it.
    Bars without two ROC readings are HOLD.
    """
    _check_momentum(window, threshold)
    if t < 1:
        return HOLD
    readings = roc(closes[: t + 1], window)
    prev, cur = readings[t - 1], readings[t]
    if prev is None or cur is None:
        return HOLD
    if prev <= threshold and cur > threshold:
        return BUY
    if prev >= threshold and cur < threshold:
        return SELL
    return HOLD


def zscore_reversion(closes, t, window=20, entry=-2.0, exit=0.0):
    """BUY when the z-score crosses up through ``entry`` on bar ``t``, SELL when it crosses up through ``exit``.

    The z-score is ``(close - SMA) / population std`` over ``window`` closes.
    BUY: z on bar ``t - 1`` is below ``entry`` and z on bar ``t`` is ``entry``
    or higher. SELL: z before is below ``exit`` and z now is ``exit`` or
    higher. If one move satisfies both, SELL wins (the price is already back
    at the mean). Bars without two readings are HOLD. ``entry >= exit``
    raises ValueError.
    """
    _check_zscore_reversion(window, entry, exit)
    if t < 1:
        return HOLD
    readings = zscore(closes[: t + 1], window)
    prev, cur = readings[t - 1], readings[t]
    if prev is None or cur is None:
        return HOLD
    if prev < exit <= cur:
        return SELL
    if prev < entry <= cur:
        return BUY
    return HOLD


def hull_trend(closes, t, window=20):
    """BUY when the Hull MA turns up on bar ``t``, SELL when it turns down.

    Turns up: the Hull MA rose on bar ``t`` after not rising on bar ``t - 1``
    (flat or falling). Turns down: it fell on bar ``t`` after not falling on
    bar ``t - 1``. Bars without three Hull MA readings are HOLD.
    """
    _check_hull_trend(window)
    if t < 2:
        return HOLD
    hull = hull_ma(closes[: t + 1], window)
    a, b, c = hull[t - 2], hull[t - 1], hull[t]
    if a is None or b is None or c is None:
        return HOLD
    if c > b and b <= a:
        return BUY
    if c < b and b >= a:
        return SELL
    return HOLD


def _check_window(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a whole number of at least 1, got {value!r}")


def _check_sma_cross(short, long):
    _check_window("short window", short)
    _check_window("long window", long)
    if short >= long:
        raise ValueError("short window must be smaller than long window")


def _check_rsi_reversion(period, oversold, overbought):
    _check_window("period", period)
    if not 0 <= oversold < overbought <= 100:
        raise ValueError(
            f"thresholds must satisfy 0 <= oversold < overbought <= 100, "
            f"got oversold={oversold}, overbought={overbought}"
        )


def _check_breakout(window):
    _check_window("window", window)


def _check_ema_cross(short, long):
    _check_sma_cross(short, long)


def _check_number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")


def _check_momentum(window, threshold):
    _check_window("window", window)
    _check_number("threshold", threshold)


def _check_zscore_reversion(window, entry, exit):
    _check_window("window", window)
    if window < 2:
        raise ValueError(f"window must be at least 2 for a z-score, got {window!r}")
    _check_number("entry", entry)
    _check_number("exit", exit)
    if entry >= exit:
        raise ValueError(f"entry must be smaller than exit, got entry={entry}, exit={exit}")


def _check_hull_trend(window):
    _check_window("window", window)


STRATEGIES = {
    "sma_cross": (
        sma_cross,
        {"short": 20, "long": 50},
        "BUY when the short SMA crosses above the long SMA, SELL on the reverse",
    ),
    "rsi_reversion": (
        rsi_reversion,
        {"period": 14, "oversold": 30, "overbought": 70},
        "BUY when RSI crosses up through oversold, SELL when it crosses down through overbought",
    ),
    "breakout": (
        breakout,
        {"window": 20},
        "BUY above the highest of the previous window closes, SELL below the lowest",
    ),
    "ema_cross": (
        ema_cross,
        {"short": 12, "long": 26},
        "BUY when the short EMA crosses above the long EMA, SELL on the reverse",
    ),
    "momentum": (
        momentum,
        {"window": 20, "threshold": 0.0},
        "BUY when the rate of change crosses up through the threshold, SELL when it crosses down",
    ),
    "zscore_reversion": (
        zscore_reversion,
        {"window": 20, "entry": -2.0, "exit": 0.0},
        "BUY when the z-score crosses up through entry, SELL when it crosses up through exit",
    ),
    "hull_trend": (
        hull_trend,
        {"window": 20},
        "BUY when the Hull MA turns up, SELL when it turns down",
    ),
}


def strategy_names():
    """Names of the registered strategies, in registry order."""
    return list(STRATEGIES)


def describe_strategies():
    """One line per strategy: name, default params and description."""
    lines = []
    for name, (_, defaults, description) in STRATEGIES.items():
        params = ", ".join(f"{k}={v}" for k, v in defaults.items())
        lines.append(f"{name} ({params}): {description}")
    return lines


def get_strategy(name):
    """Return ``(function, default params, description)`` for ``name``.

    Raises ValueError naming the valid choices for an unknown name.
    """
    if name not in STRATEGIES:
        raise ValueError(
            f"unknown strategy {name!r}; choose from: {', '.join(strategy_names())}"
        )
    function, defaults, description = STRATEGIES[name]
    return function, dict(defaults), description


def first_signal_bars(name, params):
    """The fewest closes with which strategy ``name`` can give a BUY or SELL on the last of them.

    ``params`` are the full, checked parameters (as from ``resolve_params``).
    With fewer closes every bar is warm-up and the signal is always HOLD;
    with this many, the last bar can signal (the prices decide whether it
    does). A backtest needs one bar more to fill that signal.

    * ``sma_cross``, ``ema_cross``: ``long + 1`` (a long average on the
      bar before and on the bar itself);
    * ``breakout``: ``window + 1`` (``window`` earlier closes);
    * ``zscore_reversion``: ``window + 1`` (two z-scores; the first is on
      bar ``window - 1``);
    * ``rsi_reversion``: ``period + 2`` (two RSI readings; the first is on
      bar ``period``);
    * ``momentum``: ``window + 2`` (two rates of change; the first is on bar
      ``window``);
    * ``hull_trend``: ``window + isqrt(window) + 1`` (three Hull readings;
      the first is on bar ``window + isqrt(window) - 2``).

    Raises ValueError for an unknown strategy.
    """
    get_strategy(name)
    if name in ("sma_cross", "ema_cross"):
        return params["long"] + 1
    if name in ("breakout", "zscore_reversion"):
        return params["window"] + 1
    if name == "rsi_reversion":
        return params["period"] + 2
    if name == "momentum":
        return params["window"] + 2
    if name == "hull_trend":
        return params["window"] + math.isqrt(params["window"]) + 1
    raise ValueError(f"no warm-up rule for strategy {name!r}")  # a registered strategy without a rule here


def check_param_value(name, key, value):
    """Raise ValueError when ``value`` can never be strategy ``name``'s parameter ``key``, whatever the others are.

    The checks that need one value only: windows (``short``, ``long``,
    ``window``, ``period``) are whole numbers of at least 1 (a z-score window
    at least 2), ``oversold`` and ``overbought`` are numbers from 0 to 100, and
    ``threshold``, ``entry`` and ``exit`` are finite numbers. Rules between two
    parameters (``short < long``, ``oversold < overbought``, ``entry < exit``)
    are left to ``resolve_params``. The messages are ``resolve_params``'s where
    it has one. Also raises ValueError for an unknown strategy or parameter.
    Used to check every value of a parameter grid before its combinations.
    """
    _, defaults, _ = get_strategy(name)
    if key not in defaults:
        raise ValueError(f"unknown parameter {key!r} for strategy {name!r}; choose from: {', '.join(defaults)}")
    if key in ("short", "long"):
        _check_window(f"{key} window", value)
    elif key in ("window", "period"):
        _check_window(key, value)
        if name == "zscore_reversion" and value < 2:
            raise ValueError(f"window must be at least 2 for a z-score, got {value!r}")
    else:
        _check_number(key, value)
        if key in ("oversold", "overbought") and not 0 <= value <= 100:
            raise ValueError(f"{key} must be from 0 to 100, got {value!r}")


def resolve_params(name, overrides=None):
    """Defaults for ``name`` updated with ``overrides``, validated.

    Raises ValueError for an unknown strategy, an unknown parameter name, or
    a value that breaks the strategy's rules (windows at least 1,
    ``short < long``, ``0 <= oversold < overbought <= 100``).
    """
    _, params, _ = get_strategy(name)
    for key, value in (overrides or {}).items():
        if key not in params:
            raise ValueError(
                f"unknown parameter {key!r} for strategy {name!r}; "
                f"choose from: {', '.join(params)}"
            )
        params[key] = value
    if name == "sma_cross":
        _check_sma_cross(params["short"], params["long"])
    elif name == "rsi_reversion":
        _check_rsi_reversion(params["period"], params["oversold"], params["overbought"])
    elif name == "breakout":
        _check_breakout(params["window"])
    elif name == "ema_cross":
        _check_ema_cross(params["short"], params["long"])
    elif name == "momentum":
        _check_momentum(params["window"], params["threshold"])
    elif name == "zscore_reversion":
        _check_zscore_reversion(params["window"], params["entry"], params["exit"])
    elif name == "hull_trend":
        _check_hull_trend(params["window"])
    return params
