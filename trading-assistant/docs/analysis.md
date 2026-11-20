# Analysis tools

Three tools that look at an equity curve (one account value per bar) from
different angles. They are research aids: they never place orders and are not
financial advice. Standard library only.

The examples use a sample file:

```
python -m trading_assistant.samples random_walk prices.csv
```

## Drawdowns

Question: how bad were the falls, how long did they last, and did the account
get back?

```
python -m trading_assistant.drawdowns prices.csv --top 3
python -m trading_assistant.drawdowns prices.csv --of buyhold
python -m trading_assistant.drawdowns prices.csv --strategy breakout --param window=30
```

Options: `--top N` (default 5), `--of strategy|buyhold` (default `strategy`),
and the backtest options `--short`, `--long`, `--strategy`, `--param`,
`--cash`, `--fee`, `--fee-pct`. `--short` and `--long` apply to `sma_cross`
only; use `--param` for other strategies. These tools have no fill, slippage
or exit options: the backtest fills at the next close, and `--of buyhold`
buys at the first close (the main command's buy and hold also pays the fill
price and slippage you choose there; see
[cli.md](cli.md#buy-and-hold-comparison)).

Reading the table, deepest first:

- **Peak**: the bar where the account last stood at its high.
- **Trough**: the lowest bar before it got back to the peak.
- **Recovered**: the first bar at or above the peak value, or `not recovered`
  if the curve was still below the peak at the last bar.
- **Depth**: trough against peak, in percent (negative).
- **Down**: bars from peak to trough. **Recovery**: bars from trough to
  recovery (`-` if not recovered).

Dates come from the `date` column; without one the table shows bar numbers.
As a library: `drawdown_periods(equity, dates=None)` lists every episode in
time order and `top_drawdowns(equity, dates=None, n=5)` returns the deepest.

Limits: depth is measured on closing values only. An unrecovered drawdown has
no final length; it may get deeper after the data ends.

## Monte Carlo bootstrap

Question: if the same per-bar returns had arrived in a different order, what
range of outcomes was possible?

```
python -m trading_assistant.montecarlo prices.csv --paths 500 --seed 7
```

Options: `--paths N` (default 1000), `--seed S` (default 0), and the same
backtest options as above. The backtest's per-bar returns are drawn with
replacement into N new paths as long as the original. The report gives the
5th, 25th, 50th, 75th and 95th percentiles of each path's final return and of
its max drawdown, plus the percent of paths that end with a loss. The same
seed always gives the same numbers; change the seed to see how much the answer
moves.

How to read it: the historical result is printed above the table. If it sits
near the 95th percentile, the actual order of returns was unusually kind. The
5th-percentile drawdown is a rough guide to how bad a bad run of luck could be.

Limits: a bootstrap assumes returns are independent and does not predict the
future. Real returns cluster (calm and wild periods) and strategies react to
trends, so shuffling them removes structure. Paths only reuse returns that
already happened; they cannot show a worse day than any in the data.

## Rolling statistics (library only)

Question: did performance stay steady, or was it driven by one stretch?

```python
from trading_assistant.rolling import (
    rolling_return_pct, rolling_volatility_pct, rolling_sharpe, rolling_max_drawdown_pct)

rolling_sharpe(equity, window=60)
```

Each function takes an equity curve and a `window` and returns a list the same
length as the curve. Entry `i` covers the `window` per-bar returns ending at
bar `i` (the values `equity[i - window .. i]`), so the first `window` entries
are `None`. An entry is also `None` where the value is undefined, for example
the Sharpe ratio of a flat window. Volatility and Sharpe are annualised with
252 bars per year, risk-free rate 0, and need a window of at least 2.

Limits: short windows are noisy, especially the Sharpe ratio; a window of a
few dozen bars says little on its own.

## Exit codes

For both commands: 0 success; 1 data problem (unreadable file, no `close`
column, bad number, no rows, non-positive price) with one `Error:` line on
stderr; 2 usage problem.
