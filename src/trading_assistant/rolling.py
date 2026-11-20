"""Rolling statistics over an equity curve.

An equity curve is a list of floats, one account value per bar. Each function
takes a ``window`` of bars and returns a list the same length as the input.
Entry ``i`` describes the ``window`` bars ending at bar ``i``: the window's
returns are ``equity[j] / equity[j - 1] - 1`` for ``j`` in ``i - window + 1 .. i``,
which needs the ``window + 1`` values ``equity[i - window .. i]``. The first
``window`` entries are therefore None (warm-up), and so is any entry whose
value is undefined (a non-positive value to divide by, or zero volatility
for the Sharpe ratio). Annualising uses 252 bars per year, risk-free rate 0.

Library functions only. Each raises ValueError for a window that is not a
whole number of at least the stated minimum.
"""

from .backtest import max_drawdown_pct
from .metrics import annualized_volatility_pct, sharpe_ratio


def _check_window(window, minimum):
    if isinstance(window, bool) or not isinstance(window, int) or window < minimum:
        raise ValueError(f"window must be a whole number of at least {minimum}, got {window!r}")


def _rolling(equity, window, fn):
    out = [None] * len(equity)
    for i in range(window, len(equity)):
        out[i] = fn(equity[i - window : i + 1])
    return out


def rolling_return_pct(equity, window):
    """Percent change over the last ``window`` bars: ``(equity[i] / equity[i - window] - 1) * 100``.

    ``window`` is at least 1. None during warm-up or when ``equity[i - window]`` is not positive.
    """
    _check_window(window, 1)
    return _rolling(equity, window, lambda w: (w[-1] / w[0] - 1.0) * 100.0 if w[0] > 0 else None)


def rolling_volatility_pct(equity, window, periods_per_year=252):
    """Annualised volatility in percent of the last ``window`` per-bar returns (sample std, n - 1).

    ``window`` is at least 2. None during warm-up or where a return is undefined.
    """
    _check_window(window, 2)
    return _rolling(equity, window, lambda w: annualized_volatility_pct(w, periods_per_year))


def rolling_sharpe(equity, window, periods_per_year=252):
    """Annualised Sharpe ratio of the last ``window`` per-bar returns (risk-free rate 0).

    ``window`` is at least 2. None during warm-up, where a return is undefined,
    or where the window's volatility is zero.
    """
    _check_window(window, 2)
    return _rolling(equity, window, lambda w: sharpe_ratio(w, periods_per_year))


def rolling_max_drawdown_pct(equity, window):
    """Worst peak-to-trough fall (<= 0, in percent) inside the ``window + 1`` values ending at each bar.

    ``window`` is at least 1. None during warm-up. 0.0 for a window that never falls.
    """
    _check_window(window, 1)
    return _rolling(equity, window, max_drawdown_pct)
