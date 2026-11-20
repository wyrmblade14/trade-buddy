"""Risk and return statistics over an equity curve and its round trips.

An equity curve is a list of floats, one account value per bar. Per-bar
returns are ``equity[i] / equity[i - 1] - 1``. Risk-free rate is 0. Every
function returns None where the value is undefined, as its docstring says;
none of them raise for short or degenerate input.
"""

import math

# Standard deviations at or below this are treated as zero (float noise).
_EPSILON = 1e-12


def _returns(equity):
    """Per-bar returns, or None if any value that is divided by is not positive."""
    out = []
    for prev, cur in zip(equity, equity[1:]):
        if not prev > 0:
            return None
        out.append(cur / prev - 1.0)
    return out


def _mean(values):
    return sum(values) / len(values)


def _sample_std(values):
    """Sample standard deviation (divides by n - 1). Needs at least 2 values."""
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def total_return_pct(equity):
    """Percent change from the first to the last value.

    None for fewer than 2 bars or a first value that is not positive.
    """
    if len(equity) < 2 or not equity[0] > 0:
        return None
    return (equity[-1] / equity[0] - 1.0) * 100.0


def cagr_pct(equity, periods_per_year=252):
    """Compound annual growth rate in percent.

    ``years = (len(equity) - 1) / periods_per_year`` and the rate is
    ``(last / first) ** (1 / years) - 1``. None for fewer than 2 bars, a first
    value that is not positive, or a last value that is negative.
    """
    if len(equity) < 2 or not equity[0] > 0 or equity[-1] < 0:
        return None
    years = (len(equity) - 1) / periods_per_year
    return ((equity[-1] / equity[0]) ** (1.0 / years) - 1.0) * 100.0


def annualized_volatility_pct(equity, periods_per_year=252):
    """Sample standard deviation (n - 1) of per-bar returns times sqrt(periods_per_year), in percent.

    None when there are fewer than 2 returns (fewer than 3 bars) or a return
    is undefined because an earlier value was not positive.
    """
    returns = _returns(equity)
    if returns is None or len(returns) < 2:
        return None
    return _sample_std(returns) * math.sqrt(periods_per_year) * 100.0


def sharpe_ratio(equity, periods_per_year=252):
    """Mean per-bar return over their sample standard deviation (n - 1), times sqrt(periods_per_year).

    Risk-free rate 0. None when there are fewer than 2 returns, a return is
    undefined, or the volatility is zero.
    """
    returns = _returns(equity)
    if returns is None or len(returns) < 2:
        return None
    std = _sample_std(returns)
    if std <= _EPSILON:
        return None
    return _mean(returns) / std * math.sqrt(periods_per_year)


def sortino_ratio(equity, periods_per_year=252):
    """Mean per-bar return over the downside deviation, times sqrt(periods_per_year).

    Risk-free rate 0, target 0. Downside deviation is
    ``sqrt(mean(min(r, 0) ** 2))`` over all returns (population form, divides
    by n). None when there are fewer than 2 returns, a return is undefined,
    or no return is negative.
    """
    returns = _returns(equity)
    if returns is None or len(returns) < 2:
        return None
    downside = math.sqrt(_mean([min(r, 0.0) ** 2 for r in returns]))
    if downside <= _EPSILON:
        return None
    return _mean(returns) / downside * math.sqrt(periods_per_year)


def exposure_pct(positions):
    """Percent of bars on which a position was held (``positions`` is the share count per bar).

    None for an empty list.
    """
    if not positions:
        return None
    return sum(1 for p in positions if p > 0) / len(positions) * 100.0


def profit_factor(round_trips):
    """Gross profit divided by gross loss over the round trips' ``pnl``.

    None when there are no losing round trips (including no round trips at
    all), since the ratio is then undefined.
    """
    loss = -sum(r.pnl for r in round_trips if r.pnl < 0)
    if loss <= 0:
        return None
    return sum(r.pnl for r in round_trips if r.pnl > 0) / loss


def average_win(round_trips):
    """Mean ``pnl`` of the round trips that made money. None if there are none."""
    wins = [r.pnl for r in round_trips if r.pnl > 0]
    return _mean(wins) if wins else None


def average_loss(round_trips):
    """Mean ``pnl`` of the round trips that lost money (a negative number). None if there are none."""
    losses = [r.pnl for r in round_trips if r.pnl < 0]
    return _mean(losses) if losses else None


def longest_drawdown_bars(equity):
    """Longest run of consecutive bars spent below the previous peak.

    A bar is in drawdown while its value is below the highest value so far;
    reaching that value again ends the run. 0 if the curve never falls
    below a peak. None for fewer than 2 bars.
    """
    if len(equity) < 2:
        return None
    longest = run = 0
    peak = equity[0]
    for value in equity[1:]:
        if value >= peak:
            peak = value
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    return longest
