# Indicators and strategies

All indicators live in `src/trading_assistant/indicators.py`. Each takes a list
of closing prices (except `atr`, which takes highs, lows and closes) and
returns a list of the same length. Positions without
enough history are `None`. "Warm-up" below is the number of leading `None`
values. Windows must be whole numbers of at least 1 unless noted; anything else
raises `ValueError`.

Import them with `from trading_assistant.indicators import ...`.

## Moving averages

### sma(values, window)
Simple moving average: the mean of the last `window` closes.
Warm-up: `window - 1`.
`sma([1, 2, 3, 4, 5], 3)` gives `[None, None, 2.0, 3.0, 4.0]`.

### ema(values, window)
Exponential moving average. `alpha = 2 / (window + 1)`; seeded with the SMA of
the first `window` closes, then `ema = alpha * close + (1 - alpha) * previous`.
Warm-up: `window - 1`.
`ema([1, 2, 3, 4, 5], 3)[3]` is `3.0`.

### wma(values, window)
Weighted moving average with linear weights 1 (oldest) to `window` (newest),
divided by `window * (window + 1) / 2`.
Warm-up: `window - 1`.
`wma([1, 2, 3, 4, 5], 3)[2]` is `14 / 6`.

### dema(values, window)
Double exponential moving average: `2 * EMA - EMA(EMA)`.
Warm-up: `2 * (window - 1)`.
`dema([1, 2, 3, 4, 5, 6], 2)` gives `[None, None, 3.0, 4.0, 5.0, 6.0]`.

### tema(values, window)
Triple exponential moving average: `3 * E1 - 3 * E2 + E3`, where `E2 = EMA(E1)`
and `E3 = EMA(E2)`.
Warm-up: `3 * (window - 1)`.
`tema([1, 2, 3, 4, 5, 6], 2)[3]` is `4.0`.

### hull_ma(values, window)
Hull moving average: `WMA(2 * WMA(close, window // 2) - WMA(close, window), isqrt(window))`,
with the half window at least 1 and `isqrt` the integer square root.
Warm-up: `window - 1 + isqrt(window) - 1`.
`hull_ma(closes, 16)` has 3 + 15 = 18 leading `None` values.

### kama(values, window=10, fast=2, slow=30)
Kaufman adaptive moving average. `ER = |close - close[window bars ago]| / sum of
|one-bar changes| over the window` (0 if the sum is 0). The smoothing constant is
`sc = (ER * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1)) ** 2` and
`kama = previous + sc * (close - previous)`. Seeded with the close at index
`window - 1`. `fast` must be smaller than `slow`.
Warm-up: `window - 1`.
`kama(closes, window=10, fast=2, slow=30)`.

## Momentum and oscillators

### rsi(values, period=14)
Relative Strength Index with Wilder's smoothing: `100 - 100 / (1 + avg_gain / avg_loss)`,
100 when `avg_loss` is 0. The first averages are plain means of the first
`period` changes; later ones use `(previous * (period - 1) + new) / period`.
Warm-up: `period`.
`rsi(closes, 14)[-1]`.

### roc(values, window)
Rate of change in percent: `(close / close[window bars ago] - 1) * 100`.
Raises `ValueError` if the earlier close is 0.
Warm-up: `window`.
`roc([100, 110, 99, 121], 1)` gives `[None, 10.0, -10.0, 22.2...]`.

### momentum(values, window)
Price difference: `close - close[window bars ago]`.
Warm-up: `window`.
`momentum([1, 4, 9, 16, 25], 2)` gives `[None, None, 8, 12, 16]`.

### cmo(values, period=14)
Chande momentum oscillator, -100 to 100: `100 * (U - D) / (U + D)` where `U` and
`D` are the sums of up-moves and down-moves (positive) over the last `period`
changes; 0 if nothing changed.
Warm-up: `period`.
`cmo([10, 11, 10, 12, 12], 3)[3]` is `50.0`.

### trix(values, window)
Percent change of a triple-smoothed EMA: `(E3[i] / E3[i-1] - 1) * 100`, where
`E3` is the EMA of the EMA of the EMA of the closes.
Warm-up: `3 * (window - 1) + 1`.
`trix([1, 2, 3, 4, 5, 6], 2)[4]` is `40.0`.

### linreg_slope(values, window)
Least-squares slope of the last `window` closes against 0, 1, ..., `window - 1`
(price per bar). `window` must be at least 2.
Warm-up: `window - 1`.
`linreg_slope([1, 3, 2, 6], 3)` gives `[None, None, 0.5, 1.5]`.

## Dispersion

### rolling_std(values, window)
Population standard deviation (divide by `window`, not `window - 1`) of the
last `window` closes.
Warm-up: `window - 1`.
`rolling_std([2, 4, 4, 4, 5, 5, 7, 9], 8)[-1]` is `2.0`.

### zscore(values, window)
`(close - SMA) / rolling_std` over the same window; 0 when the standard
deviation is 0. `window` must be at least 2.
Warm-up: `window - 1`.
`zscore([1, 3, 3, 2], 2)` gives `[None, 1.0, 0.0, -1.0]`.

### atr(highs, lows, closes, period=14)
Wilder's average true range. The true range of bar 0 is `high - low`; from bar
1 on it is the largest of `high - low`, `|high - previous close|` and
`|low - previous close|`, so a gap past the previous close counts in full. The
first ATR, at index `period - 1`, is the plain mean of the first `period` true
ranges; after that `atr = (previous * (period - 1) + true range) / period`.
Fewer bars than `period` give all `None`. `period` must be a whole number of
at least 1; lists of different lengths or a high below its low raise
`ValueError`. Nothing else is checked (a close outside its bar's range, or a
non-positive price, is used as given).
Warm-up: `period - 1`.
`atr([10, 12, 11, 13, 12], [8, 10, 9, 10, 10], [9, 11, 10, 12, 11], 3)` gives
`[None, None, 7/3, 23/9, 64/27]` (true ranges 2, 3, 2, 3, 2).
The backtest's risk sizing (`--risk-pct`) and ATR stop (`--atr-stop`) use it; no
strategy, the combined score or the alerts rules use it.

## Trend and bands

### macd(values, fast=12, slow=26, signal=9)
Moving average convergence/divergence. Returns three lists: the MACD line
`EMA(fast) - EMA(slow)`, the signal line `EMA(signal)` of the MACD line
(seeded with the SMA of its first `signal` values) and the histogram
`MACD - signal`. `fast` must be smaller than `slow`.
Warm-up: `slow - 1` for the MACD line, `slow - 1 + signal - 1` for the signal
line and the histogram.
`macd([10, 12, 11, 14, 13, 15], 2, 3, 2)` has MACD line
`[None, None, 0, 0.5, 0.25, 11/24]` and histogram `[None, None, None, 0.25, 0, 5/72]`.

### bollinger_bands(values, window=20, num_std=2.0)
Returns three lists: lower, middle and upper band. The middle band is the SMA;
the bands are `num_std` rolling standard deviations below and above it, the
deviation divided by `window` (not `window - 1`, as `rolling_std`).
`num_std` must be a number of at least 0.
Warm-up: `window - 1`.
`bollinger_bands([2, 4, 6, 8, 7], 3, 2)` has middle `[None, None, 4, 6, 7]` and
upper band `4 + 2 * sqrt(8/3) = 7.266` at index 2.

## Crossover signal and its explanation

`signals.crossover_signal(closes, short=20, long=50)` is the report's
`Signal:` line. It looks at the last two bars only: BUY when the short SMA
was at or below the long SMA on the bar before and is above it on the last
bar, SELL when it was at or above and is now below, HOLD otherwise and
whenever there are fewer than `long + 1` closes. `short` must be smaller than
`long` (ValueError otherwise).

`signals.explain_crossover(closes, short=20, long=50)` is the `--explain`
sentence. It calls `crossover_signal` itself, so its first word is always
that decision, and it gives both SMAs on the last bar and the bar before
(`n/a` without enough history) with 2 decimals, or more when two different
values would print the same. A HOLD sentence never says "crossed".
`explain_crossover([10, 9, 8, 9], 1, 3)` is
`BUY because the 1-bar SMA crossed above the 3-bar SMA: 9.00 against 8.67 on the last bar, after 8.00 against 9.00 on the bar before.`
`signals.explain_crossover_data` returns the same as plain values for the
API: `explain_crossover_data([10, 9, 8], 1, 3)` is `{"decision": "HOLD",
"sentence": "HOLD because a crossover needs at least 4 bars and there are 3:
...", "last_bar": {"short": 8.0, "long": 9.0}, "previous_bar": {"short": 9.0,
"long": None}}`. Both raise ValueError for bad windows, as
`crossover_signal` does, and for a close that is not a finite number. See
[cli.md](cli.md#signal-explanation---explain).

## Combined score

`signals.combined_score(closes, short=20, long=50, rsi_period=14)` adds four
votes on the last bar, each +1, 0 or -1, into one score from -4 to 4, and
returns `(score, parts)` with the keys `crossover`, `rsi`, `macd` and
`bollinger`: the short SMA above (+1) or below (-1) the long SMA; the RSI under
30 (+1) or over 70 (-1); the MACD histogram (12 / 26 / 9) above (+1) or below
(-1) 0; the last close below the lower (+1) or above the upper (-1) Bollinger
band (20, 2). Ties and missing history count 0. `--scan` uses it; see
[cli.md](cli.md#python--m-trading_assistant---scan-folder-options).

## Strategies

A strategy is `(closes, t, **params) -> BUY | SELL | HOLD`. It reads only
`closes[0..t]`, and returns HOLD while it lacks the readings it needs. Orders
fill on the next bar's close in the backtest (or its open with `--fill open`;
see [cli.md](cli.md#fills-slippage-and-position-size) for fills, slippage,
position size, stops and targets, and [cli.md](cli.md#risk-sizing) for risk
sizing). Run one with
`--backtest --strategy NAME --param KEY=VALUE`, or on several files at once
with `python -m trading_assistant.portfolio FOLDER --strategy NAME --param KEY=VALUE`
(see [cli.md](cli.md#strategies-in-the-portfolio---strategy---param)).

| Name | Params (defaults) | BUY | SELL |
| --- | --- | --- | --- |
| `sma_cross` | `short=20`, `long=50` | short SMA crosses above long SMA (before: short <= long, now: short > long) | short SMA crosses below long SMA |
| `rsi_reversion` | `period=14`, `oversold=30`, `overbought=70` | RSI was below `oversold` and is now at or above it | RSI was above `overbought` and is now at or below it |
| `breakout` | `window=20` | close is above the highest of the previous `window` closes | close is below the lowest of the previous `window` closes |
| `ema_cross` | `short=12`, `long=26` | short EMA crosses above long EMA | short EMA crosses below long EMA |
| `momentum` | `window=20`, `threshold=0.0` | ROC was at or below `threshold` and is now above it | ROC was at or above `threshold` and is now below it |
| `zscore_reversion` | `window=20`, `entry=-2.0`, `exit=0.0` | z-score was below `entry` and is now at or above it | z-score was below `exit` and is now at or above it (wins if both apply) |
| `hull_trend` | `window=20` | Hull MA rises after not rising on the previous bar | Hull MA falls after not falling on the previous bar |

Parameter rules: windows are whole numbers of at least 1 (`zscore_reversion`
needs at least 2); `short < long` for the two crossover strategies;
`0 <= oversold < overbought <= 100`; `entry < exit`; `threshold`, `entry` and
`exit` are finite numbers.
