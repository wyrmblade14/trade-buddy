# Command line reference

Everything here is research and paper trading. No command places an order.
Standard library only. Run `-h` on any command for its short help.

Exit codes, for every command:

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | data problem: one `Error:` line on stderr, no traceback |
| 2 | usage problem: reported by the argument parser (usage line plus message) |

## `python -m trading_assistant PRICES.csv [options]`

`python -m trading_assistant.cli` is the same command. `PRICES.csv` needs a
header row with a `close` column; a `date` column (`YYYY-MM-DD`, oldest first)
is optional except for `--resample`. Header names ignore case and spaces.

Some options need a **candle file** instead: a header with `date`, `open`,
`high`, `low`, `close` and `volume` (any order, extra columns allowed), each
row checked strictly (prices positive, `low <= open, close <= high`, dates
ascending). `--candles`, `--fill open`, `--stop-loss`, `--take-profit`,
`--trailing-stop`, `--risk-pct`, `--atr-stop`, `--breakeven` and `--scale-out` read the file
that way (so do the config keys `fill = open`, `stop_loss`, `take_profit`,
`trailing_stop`, `risk_pct`, `atr_stop = yes`, `breakeven` and `scale_out`); none of them can be combined with `--resample` yet (exit 2).
`--cooldown` needs one of the stops, so it reads a candle file through it.
`--min-hold`, `--max-hold`, `--max-drawdown`, `--max-losses`, `--trade-list` and `--explain` need no candle file: they work on a
close-only file and with `--resample` (with `--fill open` the file is read as
a candle file for the fill). A file without those columns is a data problem (exit 1):

```
Error: closes.csv has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'
```

`python -m trading_assistant.samples random_walk candles.csv --candles` writes
a sample candle file to try them on.

The report shows the bar count, the last close, the SMA crossover signal and
the RSI. With `--explain` one sentence right under the signal says why it is
what it is (see [Signal explanation](#signal-explanation---explain)). With
`--backtest` it also trades a strategy over the whole file.

### Analysis options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--short N` | 20 | short SMA window |
| `--long N` | 50 | long SMA window; must be above `--short` |
| `--rsi-period N` | 14 | RSI lookback |
| `--resample weekly\|monthly` | off | reduce daily bars to the last close of each ISO week or calendar month first (needs a `date` column) |
| `--chart` | off | print a text chart of the closes after the report; with `--backtest` the fills are marked `B` and `S` |
| `--explain` | off | print one sentence right after the `Signal:` line saying why it is BUY, SELL or HOLD, with the short and long SMA on the last bar and the bar before (see [Signal explanation](#signal-explanation---explain)); a switch, takes no value; needs no `--backtest` and no candle file; cannot be combined with `--scan` |
| `--candles` | off | read the file as a candle file and analyse its closes (cannot be combined with `--resample` yet) |
| `--json` | off | print the report as one JSON object instead of text (see [JSON output](#json-output---json)); cannot be combined with `--chart` |
| `--config FILE` | none | read defaults from an INI file (see below) |

To score a whole folder of price files instead of one file, see
[`--scan FOLDER`](#python--m-trading_assistant---scan-folder-options) below;
`--min-score`, `--top` and `--report` belong to it.

### Signal explanation (`--explain`)

`--explain` prints one sentence on its own line right after the `Signal:`
line (before `RSI:`). It says what the signal is, gives the short and long SMA
on the last bar and on the bar before, and says why.

- **The decision** is the sentence's first word, and it is always the
  `Signal:` line's: both come from `signals.crossover_signal` on the same
  closes and the same `--short`/`--long` windows, so the sentence cannot
  contradict the line above it.
- **The numbers** are the `--short`-bar SMA against the `--long`-bar SMA,
  first on the last bar, then on the bar before (`n/a` where there are not
  enough bars for an average yet).
- **Why.** One of five kinds of sentence:

  | Signal | When | The sentence says |
  | --- | --- | --- |
  | BUY | the short SMA was at or below the long one on the bar before and is above it on the last bar | `crossed above` |
  | SELL | it was at or above and is now below | `crossed below` |
  | HOLD | it is above on the last bar and was already above on the bar before | `stayed above ..., so there is no new crossover` |
  | HOLD | it is below and was already below | `stayed below ..., so there is no new crossover` |
  | HOLD | the two are equal on the last bar | `ended level with ..., so there is no crossover` |
  | HOLD | fewer than `--long` + 1 bars (the signal looks at the last two bars of the long SMA) | `a crossover needs at least N bars and there are M` |

  A HOLD sentence never says "crossed".
- **Decimals.** Each bar's pair has 2 decimals, like the rest of the report.
  When the two averages differ but would print the same at 2 decimals, that
  pair gets as many more as it takes to tell them apart, so the printed
  numbers never look level when the signal says they crossed
  (`10.004 against 10.002`); averages that are exactly equal keep 2
  (`10.00 against 10.00`). The signal compares the exact numbers, so a
  difference that is only rounding in the arithmetic shows in full: the closes
  `0.2, 0.1, 1.1, 0.3, 0.1, 0.1, 0.1` with `--short 1 --long 3` are a BUY,
  `0.1000000000000001 against 0.1000000000000000 on the last bar`.

With the 11-bar `c.csv` of [Breakeven stop](#breakeven-stop) (closes 10, 9,
8, 9, 11, 12, 10, 10, 11, 12, 12.2) and `--short 1 --long 3`, the 1-bar SMA
is the close and the 3-bar SMA the mean of the last three closes:

```text
$ python -m trading_assistant c.csv --short 1 --long 3 --explain
Bars:    11
Last:    12.20
Signal:  HOLD
HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: 12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.
RSI:     n/a
Research aid only. Not financial advice.
```

The same file cut to its first rows:

| Rows | Signal | Sentence |
| --- | --- | --- |
| all 11 | HOLD | `HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: 12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.` ((11 + 12 + 12.2) / 3 = 11.73, (10 + 11 + 12) / 3 = 11.00) |
| first 4 | BUY | `BUY because the 1-bar SMA crossed above the 3-bar SMA: 9.00 against 8.67 on the last bar, after 8.00 against 9.00 on the bar before.` ((9 + 8 + 9) / 3 = 8.67, (10 + 9 + 8) / 3 = 9.00) |
| first 7 | SELL | `SELL because the 1-bar SMA crossed below the 3-bar SMA: 10.00 against 11.00 on the last bar, after 12.00 against 10.67 on the bar before.` ((11 + 12 + 10) / 3 = 11.00, (9 + 11 + 12) / 3 = 10.67) |
| first 3 | HOLD | `HOLD because a crossover needs at least 4 bars and there are 3: 8.00 against 9.00 on the last bar and 9.00 against n/a on the bar before.` (no 3-bar SMA before the third bar) |

With the default windows (20/50) the whole file is too short:
`HOLD because a crossover needs at least 51 bars and there are 11: n/a against n/a on the last bar and n/a against n/a on the bar before.`

- **It follows the `Signal:` line, not `--strategy`.** `--strategy` and
  `--param` change only the backtest, and so does a sma_cross
  `--param short=`/`--param long=`: `c.csv --backtest --param short=1
  --param long=3 --explain` trades SMA 1/3, but its `Signal:` line and its
  sentence are the default 20/50 ones (`needs at least 51 bars`). Give
  `--short`/`--long` (or the config keys `short`/`long`) to change the
  windows it explains. With `--backtest --strategy breakout` the sentence is
  the same as without `--backtest`.
- **`--resample`** explains the resampled bars, as the `Signal:` line does.
  `c.csv` as a close-only file with `--resample weekly` has two bars, the last
  closes of the weeks of January 1 and January 5 (9 and 12.2):
  `HOLD because a crossover needs at least 4 bars and there are 2: 12.20 against n/a on the last bar and 9.00 against n/a on the bar before.`
  (`--short 1 --long 3`).
- **No candle file.** It reads only the closes, so it works on a close-only
  file and with `--resample`; with `--candles` (or any option that reads a
  candle file) it explains the candle file's closes.
- **Nothing else changes.** Without `--explain` every output is exactly what
  it was before. With it the only difference is that one line: the rest of
  the report, `--backtest`, `--stats`, `--trade-list`, `--chart` and the
  `--export` file are the same.
- **`--json`** gets `explanation`, the same sentence, right after `signal`
  (a top-level key, before `rsi`, also with `--backtest`); without
  `--explain` the JSON is exactly what it was before:

  ```
  $ python -m trading_assistant c.csv --short 1 --long 3 --explain --json
  {
    "bars": 11,
    "last_close": 12.2,
    "signal": "HOLD",
    "explanation": "HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: 12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.",
    "rsi": null,
    "rsi_label": null,
    "disclaimer": "Research aid only. Not financial advice."
  }
  ```

- **Rules.** A switch, takes no value. It needs no `--backtest`. With
  `--scan` it is a usage error (`--explain cannot be combined with --scan`,
  exit 2). It is listed in `--help`, after `--chart`, but not in the usage
  line. `--expl` to `--explai` are short for it; `--e`, `--ex` and `--exp`
  still mean `--export`.

The flag, the config key, the API and the page:

| | Turned on by | What you get | With `--scan` / other commands |
| --- | --- | --- | --- |
| flag | `--explain` | the line after `Signal:`; with `--json` the `explanation` string | `--scan`: usage error (exit 2) |
| config file | `explain = yes` (the words `stats` takes); `no` leaves the flag as written, so `--explain` wins over `explain = no` | exactly the flag's output | `--scan`: ignored, no error (a word that is not yes/no is still the config error, exit 1) |
| `POST /api/backtest` | `"explain": true` (JSON `true` only, like `atr_stop`) | the line in `report`, and an `explanation` object: `decision`, `sentence`, `last_bar` and `previous_bar` (see [`POST /api/backtest`](#post-apibacktest)) | the API has no `--resample`, so it explains the closes as sent |
| web page | the **Explain signal** box | the sentence right under `Signal:` in the text report panel | |

The sweep, walk-forward, portfolio, Monte Carlo, drawdowns and summary
commands do not take it (`unrecognized arguments`, exit 2), and none of them
reads the config file. `POST /api/scan`, `/api/walkforward` and
`/api/portfolio` ignore an `explain` key, as any key they do not know.

### Backtest options

These need `--backtest`; using one without it is a usage error (exit 2).

| Flag | Default | Meaning |
| --- | --- | --- |
| `--backtest` | off | also simulate trading over the whole file |
| `--cash AMOUNT` | 10000 | starting cash; must be above 0 |
| `--fee AMOUNT` | 0 | fixed cost on every buy and sell; not negative |
| `--fee-pct PCT` | 0 | percent of traded value on every buy and sell, from 0 up to but not including 100 (`0.1` means 0.1%) |
| `--fill close\|open` | `close` | price of the next bar a signal is filled at; `open` reads a candle file |
| `--slippage PCT` | 0 | buys fill this percent higher and sells this percent lower than the fill price, before fees; from 0 up to but not including 100 |
| `--position-size FRACTION` | all the cash | each buy spends at most this fraction of the account value (costs and slippage included); above 0, at most 1 |
| `--stop-loss PCT` | off | sell the position when a bar reaches the entry price less `PCT` percent; between 0 and 100, both excluded; reads a candle file |
| `--take-profit PCT` | off | sell the position when a bar reaches the entry price plus `PCT` percent; above 0; reads a candle file |
| `--trailing-stop PCT` | off | sell the position when a bar's low reaches the highest high since entry less `PCT` percent (see [Trailing stop](#trailing-stop)); between 0 and 100, both excluded; reads a candle file |
| `--risk-pct PCT` | off | size each buy by risk: `PCT` percent of the account value divided by `--atr-mult` times the ATR (see [Risk sizing](#risk-sizing)); above 0, at most 100; reads a candle file. It only sets the number of shares and places no stop itself (`--atr-stop` does) |
| `--atr-mult N` | 2 | with `--risk-pct` and/or `--atr-stop`: the distance is `N` times the ATR; above 0. Without either it is a usage error |
| `--atr-period N` | 14 | with `--risk-pct` and/or `--atr-stop`: the number of bars in the ATR; a whole number of at least 1. Without either it is a usage error |
| `--atr-stop` | off | sell the position when a bar's low reaches the entry price less `--atr-mult` times the ATR (see [ATR stop](#atr-stop)); a switch, takes no value; reads a candle file |
| `--cooldown N` | off | after a sell by `--stop-loss`, `--trailing-stop`, `--atr-stop` or `--breakeven`, no buy can fill for the next `N` bars; a buy due then is dropped and counted (see [Cooldown](#cooldown)); a whole number of at least 1; needs one of those stops |
| `--min-hold N` | off | a signal sell due before the position has been held `N` bars (counted from the buy that opened it) is dropped and counted; the other exits still sell (see [Min hold](#min-hold)); a whole number of at least 1; needs no stop and no candle file |
| `--max-hold N` | off | sell the whole position `N` bars after the buy that opened it, at that bar's fill price (see [Max hold](#max-hold)); a whole number of at least 1; needs no stop and no candle file |
| `--max-drawdown PCT` | off | halt when the account value at a close is `PCT` percent or more below its highest value at a close so far: sell the position on the next bar and let no buy fill for the rest of the run (see [Max drawdown](#max-drawdown)); above 0 and below 100, decimals allowed; needs no stop and no candle file |
| `--breakeven PCT` | off | once the high of a bar after the entry bar is `PCT` percent or more above the entry price, a later bar whose low reaches the entry price sells the position there (see [Breakeven stop](#breakeven-stop)); above 0, decimals allowed, no upper limit, but not `inf`; reads a candle file; counts as a stop for `--cooldown` |
| `--max-losses N` | off | after `N` losing round trips in a row, no buy can fill for the rest of the run; each buy due then is dropped and counted (see [Max losses](#max-losses)); a whole number of at least 1; needs no stop and no candle file |
| `--scale-out PCT` | off | once per position, when the high of a bar after the entry bar reaches the entry price (the average cost of the shares held) plus `PCT` percent, sell half the shares held (rounded down); the rest stays open (see [Scale out](#scale-out)); above 0, decimals allowed, no upper limit, but not `inf`; reads a candle file; needs no other exit |
| `--add-on PCT` | off | while a position is held, buy more on the next bar after a close `PCT` percent or more above the latest buy's fill price (slippage included), sized like any buy (see [Add-ons](#add-ons)); above 0, decimals allowed, no upper limit, but not `inf`; needs no stop and no candle file |
| `--max-adds N` | 1 | with `--add-on`: the most add-on buys per position; a whole number of at least 1; without `--add-on` it is a usage error |
| `--strategy NAME` | `sma_cross` | rule to trade: `sma_cross`, `rsi_reversion`, `breakout`, `ema_cross`, `momentum`, `zscore_reversion` or `hull_trend`; the top `Signal:` line is always the SMA crossover |
| `--param KEY=VALUE` | none | change a strategy parameter; numbers only; repeatable |
| `--stats` | off | print the "Risk and return" block after the report |
| `--trade-list` | off | print one row per completed round trip, plus one for a position still held at the end, after the report (after the "Risk and return" block with `--stats`, before `--chart`); see [Trade list](#trade-list); a switch, takes no value; needs no candle file |
| `--export FILE` | none | write one CSV row per bar (account value, signal, fills) to `FILE`; refuses to overwrite the input |

Strategy parameters (defaults):

| Strategy | Parameters |
| --- | --- |
| `sma_cross` | `short=20`, `long=50` |
| `rsi_reversion` | `period=14`, `oversold=30`, `overbought=70` |
| `breakout` | `window=20` |
| `ema_cross` | `short=12`, `long=26` |
| `momentum` | `window=20`, `threshold=0.0` |
| `zscore_reversion` | `window=20`, `entry=-2.0`, `exit=0.0` |
| `hull_trend` | `window=20` |

The BUY and SELL rules for each are in [indicators.md](indicators.md#strategies).

For `sma_cross` the windows come from `--short`/`--long`. `--param short=` and
`--param long=` also work, but a value that contradicts an explicit `--short` or
`--long` is a usage error. Unknown keys, malformed `KEY=VALUE`, duplicates and
values the strategy rejects are usage errors too.

The portfolio command takes `--strategy` and `--param` too, with the same
meaning, checks and messages; see
[Strategies in the portfolio](#strategies-in-the-portfolio---strategy---param).
The walk-forward test takes `--strategy`, `--param` for one fixed value and
`--grid` for a list of values to try; see
[Strategies in the walk-forward](#strategies-in-the-walk-forward---strategy---grid---param).

### Fills, slippage and position size

A signal decided at the close of bar `t` is filled on bar `t + 1`: at its
close (`--fill close`, the default) or at its open (`--fill open`). Signals
always come from the closes, and the account is always valued at the close.

`--slippage PCT` makes every buy fill `PCT` percent above the fill price and
every sell `PCT` percent below it; fees are then worked out on that slipped
price, and the report shows the slipped price. `--position-size FRACTION` caps
each buy at that fraction of the account value (cash plus shares held, valued
at the fill price), costs and slippage included; without it a buy spends all
the cash. Whole shares only, no shorting.

### Stops, targets and gaps

`--stop-loss PCT` and `--take-profit PCT` sell the whole position while it is
held. The levels are measured from the entry price, which is the average price
paid for the open position (slippage included): the stop is `PCT` percent
below it, the target `PCT` percent above it. The bar the position was bought
on is not checked. Each bar after that is checked in this order:

1. **The bar opens at or beyond a level (a gap).** If it opens at or below the
   stop, the stop fills **at the open**; if it opens at or above the target,
   the target fills **at the open**. A real stop order resting overnight fills
   near the open, not at a level the price jumped over, so this is worse than
   the stop level on a gap down (and better than the target on a gap up).
   Because the open comes first, a bar that opens above the target is a target
   even if it later falls to the stop.
2. **The bar only touches a level during the bar.** Its low reaches the stop:
   the stop fills **at the stop level**. Its high reaches the target: the
   target fills **at the target level**. If one bar touches both, the stop
   wins (the order inside the bar is unknown, so the cautious answer is used).

A stop or target is a sell, so `--slippage` and the fees apply to it too, on
the open or level price. With close fills the bar's range is checked before
its close, so an exit cancels a signal fill due at that close; with open fills
a signal fill at the open comes first. Every fill records why it happened:
`signal`, `stop`, `target`, `trail`, `atr` or `breakeven` (last column of the
report's fill lines and a `reason` column in `--export`; both appear only when
a stop, target, trailing stop, ATR stop or breakeven stop is on, and also
with `--max-hold` (`time`) or `--max-drawdown` (`drawdown`); `--min-hold`
makes no fills, so it adds no reason).

Example: `candles.csv` below, open fills, a 10 % stop.

```
date,open,high,low,close,volume
2026-01-01,9,11,8,10,1000
2026-01-02,9,11,8,10,2000
2026-01-03,9,11,8,10,3000
2026-01-04,9,11,8,10,4000
2026-01-05,12,15,11,14,5000
2026-01-06,13,15,12.9,14,6000
2026-01-07,14,17,12,14,7000
2026-01-08,9,10,7.5,8,8000
2026-01-09,7,9,6.9,8,9000
2026-01-10,8,9,7.5,8,10000
```

```
$ python -m trading_assistant candles.csv --backtest --short 2 --long 3 --fill open --stop-loss 10
...
    #1   bar 5     BUY       769 @      13.00  value     9,997.00  cost     0.00  cash         3.00  signal
    #2   bar 7     SELL      769 @       9.00  value     6,921.00  cost     0.00  cash     6,924.00  stop
```

The entry is 13, so the stop level is 11.70. Bar 6 (low 12) does not reach it.
Bar 7 opens at 9, below the level, so the stop fills at the open, 9.00, not
at 11.70: 769 x 9 = 6,921 plus the 3 left over is 6,924.00 cash. A bar that
opened above 11.70 and only dipped to it would have filled at 11.70.

With close fills the same file shows a target and a bar that touches both
levels. The buy is 714 @ 14.00 (cash 4.00); bar 6 opens at 14 and reaches
both 12.60 (a 10 % stop) and 16.80 (a 20 % target):

```
$ python -m trading_assistant candles.csv --backtest --short 2 --long 3 --take-profit 20
    #2   bar 6     SELL      714 @      16.80  value    11,995.20  cost     0.00  cash    11,999.20  target
$ python -m trading_assistant candles.csv --backtest --short 2 --long 3 --stop-loss 10 --take-profit 20
    #2   bar 6     SELL      714 @      12.60  value     8,996.40  cost     0.00  cash     9,000.40  stop
  Exits:       stop 10.00% below entry, target 20.00% above entry (stop wins if a bar touches both)
```

### Trailing stop

`--trailing-stop PCT` sells the whole position when the price falls `PCT`
percent from the highest point it reached while held. On each bar after the
entry bar the level is

    highest high since entry x (1 - PCT / 100)

The highest high starts at the entry price (the average price paid, slippage
included) and then takes in the highs of the bars after the entry bar, up to
**the bar before the one being checked**. A bar's own high is never used: it
is not known whether the bar's high or its low came first, so its high cannot
raise the level that its own low is checked against. Then, as for the stop:

1. the bar **opens at or below the level** (a gap): sold **at the open**;
2. otherwise its **low reaches the level**: sold **at the level**.

Each new position starts a new highest high; nothing carries over from the
one before. The sell pays `--slippage` and the fees like any sell, and it is
recorded as `trail`.

Example: `candles8.csv`, cash 500, `--short 1 --long 2`.

```
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.5,9.5,8.5,9,1000
2026-01-03,8.5,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,11.5,13,11.2,12,1000
2026-01-07,12.0,12.5,10.0,10,1000
2026-01-08,9,9,7.5,8,1000
```

```
$ python -m trading_assistant candles8.csv --backtest --short 1 --long 2 --cash 500 --trailing-stop 10
...
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash         5.00  signal
    #2   bar 6     SELL       45 @      11.70  value       526.50  cost     0.00  cash       531.50  trail
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       trail 10.00% below the highest high since entry
...
  End equity:  531.50
```

The buy is at bar 4's close, 11. On bar 5 the highest high is still the
entry price, so the level is 11 x 0.9 = 9.90 (bar 5's own high of 13 does not
count yet); its low of 11.2 stays above. On bar 6 the highest high is 13 (bar
5), the level is 11.70, bar 6 opens at 12.0 above it and its low of 10.0
reaches it: 45 x 11.70 = 526.50 plus the 5.00 left over. The signal sell due
at bar 7 finds nothing to sell. On the same file:

| Run | Sold | End equity |
| --- | --- | --- |
| `--trailing-stop 10` | bar 6 @ 11.70, `trail` | 531.50 |
| `--stop-loss 10` (level 9.90) | bar 7 @ 9.00, `stop` (opens below the level) | 410.00 |
| `--trailing-stop 30` (level 13 x 0.7 = 9.10) | bar 7 @ 9.00, `trail` (opens below the level) | 410.00 |
| `--trailing-stop 10 --fill open` | buys 46 @ 10.80, bar 6 @ 11.70, `trail` | 541.40 |

**With the other exits.** The stop and the trailing stop are both levels
below the price, and a falling price meets the higher one first, so on each
bar the higher of the two is used (`stop` on a tie); with the ATR stop as well
the highest of the three is used (see [ATR stop](#atr-stop)). When a bar touches the
target and the stop or trailing stop, the stop or trailing stop wins, as
before. The report's `Exits:` line lists the exits that are on, with a note
when there are several:

```
  Exits:       trail 10.00% below the highest high since entry
  Exits:       stop 5.00% below entry, trail 10.00% below the highest high since entry (the higher of stop and trail is used)
  Exits:       trail 10.00% below the highest high since entry, target 20.00% above entry (trail wins if a bar touches both)
  Exits:       stop 5.00% below entry, trail 10.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)
```

**Not covered by the trailing stop (yet).** The sweep, the walk-forward test
and the portfolio command do not take it (they take no stop or target
either). The web page's **Exits** card lists only the stop loss and take
profit; a trailing stop shows in the trades table and in the text report
instead. `--help` describes `--trailing-stop`, but the usage line at the top
of `--help` and of a usage error does not list it (so that line stays exactly
as it was). In `--json`, `trailing_stop_pct` is there only when the trailing
stop is on, while `stop_loss_pct` and `take_profit_pct` are always there.
`tests/test_paths_agree.py` does not include it; its own tests compare the
flag, the config key, the API and the page.

### Risk sizing

`--risk-pct PCT` changes how many shares each buy gets, and nothing else:

    risk     = PCT % of the account value at the fill
    distance = atr_mult x ATR(atr_period) on the bar the buy signal came on
    shares   = risk / distance, rounded down to whole shares

- The ATR is Wilder's average true range (see
  [indicators.md](indicators.md#atrhighs-lows-closes-period14)) over
  `--atr-period` bars (default 14), taken on the **signal bar**, never on the
  bar the buy fills on, so no later price is used.
- The account value is the cash plus the shares held, valued at the fill
  bar's fill price (before slippage), as for `--position-size`.
- The share count is capped by the cash (whole shares, costs included) and by
  `--position-size` if given: the smaller size wins.
- **Risk sizing places no stop itself.** Without `--atr-stop` the distance
  is only used to work out the share count and nothing sells the position
  when the price falls by that distance. With `--atr-stop` the ATR stop sells
  at the distance of the buy that opened the position (see
  [ATR stop](#atr-stop)). Either way a loss can be larger than `PCT` % of the
  account: without the ATR stop because nothing sells at the distance, with it
  through a gap, slippage, fees or a later buy into the position. For an exit
  use `--stop-loss`, `--trailing-stop` or `--atr-stop`; risk sizing works next
  to them and to `--take-profit`, which decide the sells as before.
- A buy that risk sizing gives 0 shares is **skipped and counted**: when the
  signal bar has no ATR yet (the first `atr_period - 1` bars), when the ATR is
  0 (flat bars), or when the risk is less than one share. A buy skipped only
  for lack of cash or by `--position-size` is not counted.
- It needs `--backtest` and a candle file and cannot be combined with
  `--resample` yet, like `--stop-loss`. `--atr-mult` and `--atr-period` need
  `--risk-pct` or `--atr-stop` (a usage error otherwise, exit 2).

Example: `candles8.csv` from [Trailing stop](#trailing-stop), cash 1000,
`--short 1 --long 2`. The BUY signal is on bar 3. The true ranges of bars 0 to
3 are 1, 1.5, 1.5 and 1.5, so ATR(3) on bar 2 is 4/3 and on bar 3 is
(4/3 x 2 + 1.5) / 3 = 25/18 = 1.389. The distance is 2 x 1.389 = 2.778, the
risk 2 % of 1000 = 20, and 20 / 2.778 = 7.2 gives 7 shares:

```
$ python -m trading_assistant candles8.csv --backtest --short 1 --long 2 --cash 1000 --risk-pct 2 --atr-mult 2 --atr-period 3
...
    #1   bar 4     BUY         7 @      11.00  value        77.00  cost     0.00  cash       923.00
    #2   bar 7     SELL        7 @       8.00  value        56.00  cost     0.00  cash       979.00
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) (this only sets the number of shares; no stop is placed)
...
  End equity:  979.00
  Return:      -2.10%
```

The loss is 7 x (11 - 8) = 21.00, 2.10 % of the account: more than the 2 %
"at risk", because no stop was placed and the sell came from the next signal.
Bar 4's ATR (1.759) would have given 5 shares; it is not used, since the buy
fills on bar 4. On the same file:

| Run (cash 1000, `--short 1 --long 2`) | Buy | End equity |
| --- | --- | --- |
| no risk sizing | 90 @ 11.00 | 730.00 |
| `--risk-pct 2 --atr-period 3` | 7 @ 11.00 | 979.00 |
| `--risk-pct 4 --atr-period 3` | 14 @ 11.00 (40 / 2.778 = 14.4) | 958.00 |
| `--risk-pct 2 --atr-period 3 --atr-mult 1` | 14 @ 11.00 (20 / 1.389 = 14.4) | 958.00 |
| `--risk-pct 2 --atr-period 3 --position-size 0.05` | 4 @ 11.00 (at most 50 to spend) | 988.00 |
| `--risk-pct 100 --atr-period 3` | 90 @ 11.00 (360 wanted, the cash buys 90) | 730.00 |
| `--risk-pct 2 --atr-period 3 --trailing-stop 10` | 7 @ 11.00, sold bar 6 @ 11.70 (`trail`) | 1,004.90 |
| `--risk-pct 2 --atr-period 5` | none: no ATR(5) on bar 3 yet, skipped | 1,000.00 |
| `--risk-pct 0.1 --atr-period 3` | none: 1 / 2.778 = 0.36 share, skipped | 1,000.00 |

A skipped buy adds a line after `Risk sizing:`:

```
  Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)
```

**What is not checked.** Fees and slippage are not part of the risk amount.
The ATR uses the file's highs, lows and closes as they are; the candle file
check (prices positive, `low <= open, close <= high`) is the only check on
them. `--atr-mult inf` is accepted by the command and skips every buy (the
config file and `POST /api/backtest` refuse it as not a finite number); a
`--atr-period` longer than the file simply skips every buy. The `Risk sizing:`
line says what was asked for, not what was risked: a share count capped by the
cash or `--position-size` risks less.

**Not covered by risk sizing (yet).** The buy-and-hold comparison stays
all-in. The sweep, the walk-forward test, the portfolio command and the Monte
Carlo tool do not take it. `--export` has no risk columns (its fills change).
The web page shows it in the text report; its only card is the skipped-buy
count on the **Trades** card.
`tests/test_paths_agree.py` does not include it; its own tests compare the
library, the report, the flags, `--json`, the config keys, the API and the
page. `--help` describes the three options, but the usage line at the top of
`--help` and of a usage error does not list them (so that line stays exactly
as it was).

### ATR stop

`--atr-stop` (a switch) sells the whole position when the price falls a
multiple of the ATR below the entry price. On each bar after the entry bar
the level is

    entry price - atr_mult x ATR(atr_period) on the signal bar of the buy that opened the position

- It uses the same `--atr-mult` (default 2) and `--atr-period` (default 14)
  as risk sizing, and the ATR of the same bar: the **signal bar**, never the
  bar the buy fills on.
- The distance is **fixed when the position opens**; the ATR of later bars
  does not move it. The entry price is the average price paid (slippage
  included), as for `--stop-loss`, so a later buy into the same position
  moves the level with the new average price but keeps the first distance.
  Each new position takes a new distance.
- As for the stop: a bar that **opens at or below the level** (a gap) sells
  **at the open**; otherwise a bar whose **low reaches the level** sells **at
  the level**. The sell pays `--slippage` and the fees like any sell and is
  recorded as `atr`.
- A buy signal whose bar has **no ATR yet** (the first `atr_period - 1`
  bars) or an **ATR of 0** is **skipped and counted**, exactly like risk
  sizing's skipped buys; with both options a skipped buy is counted once.
- With `--stop-loss` and/or `--trailing-stop` the **highest** of the levels
  is used (a falling price meets it first); on a tie the stop wins, then the
  trail, then atr. It wins over `--take-profit` on a bar that touches both.
- With `--risk-pct` the buy that opens a position is sized on the same
  distance the ATR stop sells at, so without a gap, slippage or fees its loss
  at the stop is at most the risk. A later buy into the same position is sized
  on its own signal bar's ATR, while the stop keeps the first buy's distance
  from the new average price, so the position can then lose more than the
  risks added up. A gap, slippage or fees can lose more too.
- It needs `--backtest` and a candle file and cannot be combined with
  `--resample` yet, like `--stop-loss`.

Example: `candles8.csv` from [Trailing stop](#trailing-stop), cash 1000,
`--short 1 --long 2`. ATR(3) on the signal bar 3 is 25/18 = 1.389, so with
the default `--atr-mult 2` the level is 11 - 2.778 = 8.22. Bar 7 opens at 9
(above it) and its low 7.5 reaches it:

```
$ python -m trading_assistant candles8.csv --backtest --short 1 --long 2 --cash 1000 --atr-stop --atr-period 3
...
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 7     SELL       90 @       8.22  value       740.00  cost     0.00  cash       750.00  atr
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       atr 2 x ATR(3) below entry
...
  End equity:  750.00
```

| Run (cash 1000, `--short 1 --long 2`) | Exit | End equity |
| --- | --- | --- |
| no exit | bar 7 @ 8.00 (`signal`) | 730.00 |
| `--atr-stop --atr-period 3` | bar 7 @ 8.22 (`atr`) | 750.00 |
| `--atr-stop --atr-period 3 --atr-mult 1` | level 9.61; bar 7 opens at 9 below it: @ 9.00 (`atr`) | 820.00 |
| `--atr-stop --atr-period 3 --risk-pct 2` | 7 shares, bar 7 @ 8.22 (`atr`): a loss of 19.44, under the 20 at risk | 980.56 |
| `--atr-stop --atr-period 3 --trailing-stop 10` | the trail (11.70 on bar 6) is higher: bar 6 @ 11.70 (`trail`) | 1,063.00 |
| `--atr-stop --atr-period 5` | none: no ATR(5) on bar 3 yet, the buy is skipped | 1,000.00 |
| `--atr-stop` | none: no ATR(14) on 8 bars, the buy is skipped | 1,000.00 |

A skipped buy without `--risk-pct` adds a line before `Exits:`:

```
  Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)
```

With `--risk-pct` as well, the `Risk sizing:` line ends `(the ATR stop sells
at this distance, as of the buy that opened the position, below the average
entry price; a gap, slippage, fees or a later buy can lose more)` instead of
`(this only sets the number of shares; no stop is placed)`,
and a skipped buy uses risk sizing's `Skipped:` line.

In `--json` the backtest object gets `"atr_stop": true` (right after
`trailing_stop_pct`, or `take_profit_pct` without it), `atr_mult` and
`atr_period` (right after `position_size`, or after `risk_pct` with
`--risk-pct`) and `risk_skipped_buys` (right after `sells`); see
[JSON output](#json-output---json). A run without `--atr-stop` prints exactly
the JSON it printed before.

The config file key is `atr_stop = yes` (see [Config file](#config-file---config-file));
with it, or with `--atr-stop`, the file's `atr_mult` and `atr_period` are used.

`POST /api/backtest` takes it as `"atr_stop": true` (see
[`POST /api/backtest`](#post-apibacktest)), and the web page has an **ATR
stop** box (see [the web page](#python--m-trading_assistantweb)). `--help`
describes the option, but the usage line does not list it.

### Cooldown

`--cooldown N` keeps the strategy out of the market for `N` bars after a stop
has sold the position. When `--stop-loss`, `--trailing-stop`, `--atr-stop`
or `--breakeven` sells on bar `t` (the fill's reason is `stop`, `trail`, `atr`
or `breakeven`), no buy can fill on bars `t + 1` to `t + N`; the first buy can
fill on bar `t + N + 1`. `--breakeven` alone is enough for `--cooldown`,
although the error for `--cooldown` with no stop at all (and its `--help`
text) still names only `--stop-loss`, `--trailing-stop` and `--atr-stop`.

- **Which sells start it:** only `stop`, `trail`, `atr` and `breakeven` sells. A
  `--take-profit` sell (`target`) or a sell on the strategy's own signal
  (`signal`) starts no cooldown.
- **A buy due in the cooldown is dropped, not delayed.** It is not filled
  later when the cooldown ends. A strategy that signals BUY only on the bar
  of a crossing (`sma_cross`, `ema_cross`, ...) therefore stays out until its
  **next** BUY signal, however long after the cooldown that is. A strategy
  that keeps signalling BUY (such as `breakout`, on every close above the
  window's high) buys again on the first bar after the cooldown that a BUY
  is due on.
- **The exit bar.** A BUY signal on the exit bar's close is due on bar
  `t + 1`, the first blocked bar, so any `N` of 1 or more drops it. A buy that
  was due on the exit bar itself is never a cooldown skip: with close fills
  the exit comes first and cancels it (one fill per bar, as before); with
  `--fill open` the buy fills at the open, and then no exit is checked on
  that bar, so no cooldown starts there.
- **What is counted:** every buy due on a blocked bar, once, in
  `Cooldown: ... N buys skipped`, even one that would have got 0 shares
  anyway (for example risk sizing under one share). Such a buy is counted
  only as a cooldown skip, never also as a risk sizing skip. A BUY signal on
  the last bar has no bar to fill on and is never counted.
- `N` is a whole number of at least 1 (`--cooldown 0` or `--cooldown 1.5` is
  a usage error, exit 2). The option needs `--backtest` and one of
  `--stop-loss`, `--trailing-stop` or `--atr-stop`; without a stop it is the
  usage error
  `--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop`
  (`--take-profit` alone is not enough). A stop from the config file counts.
  Through the stop it needs a candle file and cannot be combined with
  `--resample` yet.

Example: `candles11.csv`, cash 1000, `--short 1 --long 2 --stop-loss 10`.
The crossover signals BUY on bars 3 and 8 and SELL on bar 6.

```
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
```

The buy of bar 4 (90 @ 11) is stopped out on bar 6 at 9.90 (cash 901). The
BUY signal of bar 8 is due on bar 9: with `--cooldown 2` (bars 7 and 8
blocked) it buys 75 @ 12; with `--cooldown 3` (bars 7 to 9 blocked) it is
dropped, and as the crossover gives no later BUY signal the run stays in cash:

```
$ python -m trading_assistant candles11.csv --backtest --short 1 --long 2 --cash 1000 --stop-loss 10 --cooldown 3
...
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 6     SELL       90 @       9.90  value       891.00  cost     0.00  cash       901.00  stop
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       stop 10.00% below entry
  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped
...
  End equity:  901.00
```

| Run (cash 1000, `--short 1 --long 2`) | What happens | Skipped | End equity |
| --- | --- | --- | --- |
| `--stop-loss 10` | stop on bar 6, buys 75 @ 12 on bar 9 | - | 916.00 |
| `--stop-loss 10 --cooldown 1` or `2` | bar 9 is after the cooldown: same fills | 0 | 916.00 |
| `--stop-loss 10 --cooldown 3` | the bar 9 buy is dropped | 1 | 901.00 |
| `--stop-loss 10 --cooldown 3 --fill open` | 92 @ 10.80, stop @ 9.72; the bar 9 buy is dropped | 1 | 900.64 |
| `--trailing-stop 10 --cooldown 3` | trail on bar 6 @ 10.80; the bar 9 buy is dropped | 1 | 982.00 |
| `--atr-stop --atr-mult 1 --atr-period 1 --cooldown 3` | atr on bar 6 @ 9.50; the bar 9 buy is dropped | 1 | 865.00 |
| `--stop-loss 10 --take-profit 5 --cooldown 4` | target on bar 5 @ 11.55: no cooldown, bar 9 buys 87 @ 12 | 0 | 1,066.90 |
| `--stop-loss 50 --cooldown 3` | signal sell on bar 7: no cooldown, bar 9 buys 75 @ 12 | 0 | 925.00 |
| `--stop-loss 10 --strategy breakout --param window=1 --cooldown 3` | after the stop, buys are due on bars 9 and 10 (BUY signals on bars 8 and 9; the one on bar 10, the last bar, never fills): bar 9's is dropped, bar 10 buys 73 @ 12.20 | 1 | 901.00 |
| same with `--cooldown 4` | the buys due on bars 9 and 10 are both dropped | 2 | 901.00 |
| `--atr-stop --atr-mult 1 --atr-period 1 --risk-pct 0.16 --cooldown 3` | 1 share; the bar 9 buy would get 0 shares and is counted as a cooldown skip only (no `Skipped:` line) | 1 | 998.50 |

The report's `Cooldown:` line comes right after `Exits:` and only with the
option; a run without it prints exactly what it printed before. In `--json`
the backtest object gets `cooldown_bars` right after the exit settings and
`cooldown_skipped_buys` right after `sells` (see
[JSON output](#json-output---json)):

```
    "stop_loss_pct": 10.0,
    "take_profit_pct": null,
    "cooldown_bars": 3,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "cooldown_skipped_buys": 1,
```

The config file key is `cooldown` (see [Config file](#config-file---config-file)),
`POST /api/backtest` takes `cooldown` (see [`POST /api/backtest`](#post-apibacktest)),
and the web page has a **Cooldown (bars)** field. `--export` has no cooldown
column; its rows show the fills as they happened. `--help` describes the
option, but the usage line does not list it.

### Min hold

`--min-hold N` keeps the strategy from selling a position too soon. When the
buy that opens a position fills on bar `e`, a signal sell due on a bar before
`e + N` is skipped; from bar `e + N` on, signal sells fill as usual. Only the
strategy's own sells are held back: `--stop-loss`, `--take-profit`,
`--trailing-stop`, `--atr-stop`, `--breakeven`, `--max-hold` and
`--max-drawdown` still sell inside the window.

- **The clock starts at the first buy**, as for `--max-hold`. A later buy into
  the same position (with `--position-size`, or a strategy that keeps
  signalling BUY such as `breakout`) does not restart it.
- **A skipped sell is dropped, not delayed.** It is not tried again when the
  window ends. A crossover strategy, which signals SELL only on the bar of the
  crossing, then holds until its next SELL signal or another exit; a strategy
  that keeps signalling (`breakout`) sells on its first SELL due at or after
  bar `e + N`.
- **A sell is counted only when it would otherwise have filled**: shares are
  held and nothing has sold them earlier on that bar. With close fills the
  bar's range comes first, so when a stop or target sells on that bar there is
  nothing left to skip and nothing is counted. With `--fill open` the signal
  comes first, at the open, so it is skipped and counted even if a stop then
  sells later in the same bar. It is counted before the fees are looked at, so
  a sell the fees would have refused is counted too.
- **The bar stays free.** A skipped sell makes no fill, so a `--max-hold` or
  `--max-drawdown` sale can still use that bar. After a drawdown halt this
  changes the fill's reason: where the signal sell would have filled
  (`signal`), the drawdown sale now sells the same shares on the same bar at
  the same price, recorded as `drawdown`.
- `--min-hold 1` is accepted but skips nothing: a signal sell is never due on
  the bar its position was bought. `--min-hold` at or above `--max-hold` is
  allowed; the time exit then sells first.
- It makes no fills of its own: the fills carry no extra reason, and
  `--export` gets no `reason` column and no extra rows because of it (a bar
  whose sell was skipped is a row without an action).
- `N` is a whole number of at least 1 (`--min-hold 0` is
  `--min-hold must be a whole number of at least 1, got 0` and
  `--min-hold 1.5` argparse's `argument --min-hold: invalid int value: '1.5'`,
  both exit 2). It needs `--backtest` but no stop, works on a close-only file
  and with `--resample` (`N` then counts the resampled bars), and cannot be
  combined with `--scan` (exit 2). `--min-h` is short for it; `--mi`, `--min`
  and `--min-` still mean `--min-score`.
- The sweep, walk-forward, portfolio, Monte Carlo and drawdowns commands do
  not take it (`unrecognized arguments: --min-hold 3`, exit 2).

Example: `closes.csv`, the closes of `candles11.csv` above (as in
[Max hold](#max-hold)), cash 1000, `--short 1 --long 2`. The buy fills on bar
4 and the strategy's SELL is due on bar 7, 3 bars later.

```
$ python -m trading_assistant closes.csv --backtest --short 1 --long 2 --cash 1000 --min-hold 4
...
  Trades:      1 (1 buy, 0 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Min hold:    4 bars after a position's first buy before a signal sell can fill; 1 signal sell skipped
...
  End equity:  1,108.00
```

| Run (cash 1000) | What happens | Skipped | End equity |
| --- | --- | --- | --- |
| `closes.csv --short 1 --long 2` | without the option: signal sell on bar 7, buys 75 @ 12 on bar 9 | - | 925.00 |
| `... --min-hold 1` | skips nothing: same as without | 0 | 925.00 |
| `... --min-hold 3` | bar 7 is 3 bars after the buy: the sell fills, same as without | 0 | 925.00 |
| `... --min-hold 4` | the bar 7 sell is skipped; the bar 9 buy finds 10.00 cash, not enough for one share at 12; 90 shares held | 1 | 1,108.00 |
| `... --min-hold 4 --max-hold 2` | the time exit sells 90 @ 10.00 on bar 6; bar 7's SELL finds nothing held, so it is not counted; buys 75 @ 12 on bar 9 | 0 | 925.00 |
| `... --min-hold 4 --fee 495` | buys 45 @ 11 (cash 10); the bar 7 sell would be refused by the fees (10 + 450 - 495 is below 0) but is counted first | 1 | 559.00 |
| `... --min-hold 6 --max-drawdown 5` | halt on bar 6; the bar 7 signal sell is skipped and the drawdown sale sells the 90 shares there @ 10.00 as `drawdown` (without `--min-hold`: `signal`) | 1 | 910.00 |
| `... --strategy breakout --param window=1 --position-size 0.5 --min-hold 3` | buys 45 @ 11 on bar 4 and 42 @ 12 on bar 5; the bar 7 sell is 3 bars after the first buy, so it fills (counted from bar 5 it would be skipped): same as without | 0 | 878.20 |
| same with `--min-hold 4` | the bar 7 sell is skipped; 87 shares held | 1 | 1,062.40 |
| `candles11.csv --short 1 --long 2 --stop-loss 10 --min-hold 6` | the stop sells on bar 6 @ 9.90, inside the window, as without the option | 0 | 916.00 |
| `candles11.csv --short 1 --long 2 --fill open --min-hold 4` | buys 92 @ 10.80; the sell due at bar 7's open is skipped | 1 | 1,128.80 |

Close fills against open fills: `dip.csv` is `closes.csv` as candles with
open, high and low equal to the close, except bar 7's low, 9.5. A 10 % stop
below the entry of 11 is 9.90, first reached on bar 7, the bar the signal sell
is due on.

| Run (cash 1000, `--short 1 --long 2 --stop-loss 10`) | What happens | Skipped | End equity |
| --- | --- | --- | --- |
| `dip.csv` | close fills: the stop sells 90 @ 9.90 during bar 7, before its close | - | 916.00 |
| `dip.csv --min-hold 4` | the same stop sale; the signal sell at the close never could have filled, so nothing is counted | 0 | 916.00 |
| `dip.csv --fill open` | the signal sells 90 @ 10.00 at bar 7's open, before the stop is looked at | - | 925.00 |
| `dip.csv --fill open --min-hold 4` | the signal sell at the open is skipped and counted; the stop then sells 90 @ 9.90 later in bar 7 | 1 | 916.00 |

Dropped, not delayed: `falls.csv` (`date,close`, closes 10, 11, 12, 11, 10,
9, 9) with `--strategy breakout --param window=1 --position-size 0.5`, cash
1000, buys 41 @ 12 on bar 2 and 43 @ 11 on bar 3, and its SELL signals are
due on bars 4, 5 and 6. Without the option it sells the 84 shares @ 10 on bar
4 (875.00). With `--min-hold 3` the bar 4 sell is skipped and the next one,
on bar 5, fills @ 9 (1 skipped, 791.00); with `--min-hold 4` the bar 4 and 5
sells are skipped and the bar 6 one fills @ 9 (2 skipped, 791.00).

The report's `Min hold:` line comes right before the `Max hold:` line (after
the `Cooldown:` line, or `Exits:`, or `Costs:` and the sizing lines), only
with the option; the fills show no reason because of it. A run without it
prints exactly what it printed before. In `--json` the backtest object gets
`min_hold_bars` right before `max_hold_bars` (or where that key would be) and
`min_hold_skipped_sells` right before `time_exits` (or where that key would
be); see [JSON output](#json-output---json):

```
    "take_profit_pct": null,
    "min_hold_bars": 4,
    "trades": 1,
    "buys": 1,
    "sells": 0,
    "min_hold_skipped_sells": 1,
```

The config file key is `min_hold` (see [Config file](#config-file---config-file)),
`POST /api/backtest` takes `min_hold` (see [`POST /api/backtest`](#post-apibacktest)),
and the web page has a **Min hold (bars)** field. `--help` describes the
option, but the usage line does not list it.

### Max hold

`--max-hold N` limits how long a position is held. When the buy that opens a
position fills on bar `e`, the whole position is sold on bar `e + N` at that
bar's fill price: its close, or its open with `--fill open`. Entry and exit
are both at the fill price, so the position is held exactly `N` bars in
either fill mode. The fill's reason is `time`.

- **The clock starts at the first buy.** A later buy into the same position
  (with `--position-size`, or a strategy that keeps signalling BUY such as
  `breakout`) does not restart it.
- **A bar that already has a fill keeps it.** If a signal buy or sell, a
  stop, trail, ATR stop or target sale, or (with close fills) a `--scale-out`
  partial sale fills on bar `e + N`, that fill
  happens and the time exit waits for the next bar without one (it sells on
  the first such bar). A signal sell on that bar is labelled `signal`.
- **Order within a bar.** With close fills: the bar's range first (stops and
  target), then the signal fill at the close, then a `--scale-out` partial
  sale, then the time exit at the
  close. With `--fill open`: the signal fill at the open first, then a gap
  through a stop or the target at the open (sold at the open as `stop`,
  `trail`, `atr`, `breakeven` or `target`), then the time exit at the open. A stop or
  target that is only reached later in the bar does not beat it.
- **No cooldown.** A time exit starts no `--cooldown` (only `stop`, `trail`,
  `atr` and `breakeven` sells do). After it the strategy can buy again on its next BUY
  signal: a crossover strategy waits for its next crossing, `breakout` may
  buy again on the next bar.
- Slippage and fees apply as to any sell. A sell the fees would make
  impossible is tried again on the next bar. A position still open at the end
  is not sold (as without the option).
- `N` is a whole number of at least 1 (`--max-hold 0` is
  `--max-hold must be a whole number of at least 1, got 0` and
  `--max-hold 1.5` argparse's `argument --max-hold: invalid int value: '1.5'`,
  both exit 2). It needs `--backtest` but no stop, works on a close-only file
  and with `--resample` (`N` then counts the resampled bars), and cannot be
  combined with `--scan` (exit 2).

Example: `closes.csv`, the closes of `candles11.csv` above without the other
columns, cash 1000, `--short 1 --long 2`. The crossover signals BUY on bars 3
and 8 and SELL on bar 6, so without the option it buys 90 @ 11 on bar 4,
sells on bar 7 and buys 75 @ 12 on bar 9 (end equity 925.00).

```
$ python -m trading_assistant closes.csv --backtest --short 1 --long 2 --cash 1000 --max-hold 1
...
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 5     SELL       90 @      12.00  value     1,080.00  cost     0.00  cash     1,090.00  time
    #3   bar 9     BUY        90 @      12.00  value     1,080.00  cost     0.00  cash        10.00  signal
    #4   bar 10    SELL       90 @      12.20  value     1,098.00  cost     0.00  cash     1,108.00  time
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Max hold:    1 bar after a position's first buy, then sold at the bar's fill price; 2 time exits
...
  End equity:  1,108.00
```

| Run (cash 1000, `--short 1 --long 2`) | What happens | Time exits | End equity |
| --- | --- | --- | --- |
| `closes.csv` | signal sell on bar 7, buys 75 @ 12 on bar 9 | - | 925.00 |
| `closes.csv --max-hold 1` | time exits on bar 5 @ 12.00 and bar 10 @ 12.20 | 2 | 1,108.00 |
| `closes.csv --max-hold 2` | time exit on bar 6 @ 10.00; bar 7's SELL finds nothing to sell | 1 | 925.00 |
| `closes.csv --max-hold 3` | due on bar 7, where the signal sell fills (`signal`): same as without | 0 | 925.00 |
| `closes.csv --max-hold 1 --slippage 1 --fee 1` | time exits @ 11.88 and 12.08 (1 % lower), 1.00 fee each | 2 | 1,060.88 |
| `closes.csv --max-hold 1 --strategy breakout --param window=1 --position-size 0.5` | buys on bars 4 and 5; due on bar 5, but the buy fills there, so the time exit is on bar 6 @ 10.00 for all 87 shares | 1 | 878.20 |
| `candles11.csv --max-hold 1 --fill open` | buys 92 @ 10.80, time exit at bar 5's open, 11.00; buys 94 @ 10.80, time exit at bar 10's open, 12.00 | 2 | 1,131.20 |
| `candles11.csv --max-hold 2 --stop-loss 10` | due on bar 6, where the stop fills @ 9.90 (`stop`) | 0 | 916.00 |
| `candles11.csv --max-hold 1 --stop-loss 10 --cooldown 3` | time exit on bar 5: no cooldown, so the bar 9 buy fills | 2 | 1,108.00 |

The report's `Max hold:` line comes after the `Cooldown:` line (or `Exits:`,
or `Costs:` and the sizing lines) and only with the option; with it the
fills also show their reason, even without a stop. A run without it prints
exactly what it printed before. In `--json` the backtest object gets
`max_hold_bars` right after the exit settings and `cooldown_bars`, and
`time_exits` right after the skipped-buy counts (see
[JSON output](#json-output---json)):

```
    "stop_loss_pct": null,
    "take_profit_pct": null,
    "max_hold_bars": 1,
    "trades": 4,
    "buys": 2,
    "sells": 2,
    "time_exits": 2,
```

`--export` gets the `reason` column with the option (as with a stop), with
`time` on the time exits' rows; without it the file is as before. The config
file key is `max_hold` (see [Config file](#config-file---config-file)),
`POST /api/backtest` takes `max_hold` (see [`POST /api/backtest`](#post-apibacktest)),
and the web page has a **Max hold (bars)** field. `--help` describes the
option, but the usage line does not list it.

### Max drawdown

`--max-drawdown PCT` halts a run that has lost `PCT` percent or more from its
best point. After every bar the account value at the close (cash plus the
shares at the close, after that bar's fill and its costs) is compared with
the highest account value at a close so far, the first bar's included. When
it is `PCT` percent or more below that peak, on bar `h`, the run halts; it is
checked until it triggers, once.

- **No more buys.** From bar `h + 1` to the end no buy can fill. A buy due
  then is dropped (not delayed) and counted, even one that would have got 0
  shares; it is then counted neither as a cooldown skip nor as a risk sizing
  skip. A strategy that keeps signalling (`breakout`) is counted on every bar
  it signals. A BUY signal on the last bar has no bar to fill on and is not
  counted.
- **The position is sold on the next bar.** A position still held is sold
  whole on bar `h + 1` at that bar's fill price (its close, or its open with
  `--fill open`), with slippage and fees. The fill's reason is `drawdown`.
- **Another sale on that bar goes first** and keeps its own reason, in the
  order `--max-hold` uses. With close fills: a stop, trailing stop, ATR stop
  or target reached during the bar, then the strategy's SELL at the close,
  then a `--scale-out` partial sale (the drawdown sale then waits for the
  next bar), then a `--max-hold` sale, then the drawdown sale. With `--fill open`: the
  strategy's SELL at the open, then a gap through a stop or target at the
  open, then a `--max-hold` sale, then the drawdown sale at the open; a stop
  or target reached only later in the bar does not beat it. A signal sell
  that `--min-hold` skips makes no fill, so the drawdown sale then takes that
  bar (see [Min hold](#min-hold)).
- **No cooldown.** The drawdown sale starts no `--cooldown` (only `stop`,
  `trail`, `atr` and `breakeven` sells do). A cooldown could change nothing here: the halt
  already blocks every later buy. A buy that falls both in a cooldown from an
  earlier stop and after the halt is counted once, as a drawdown skip.
- A sale the fees would make impossible (cash below zero) is tried again on
  each later bar; a position still held at the end is not sold, as without the
  option.
- **The same measure as the report.** The peak and the percentage are worked
  out exactly like the report's `Max drawdown` and the `drawdown_pct` column
  of `--export`, from the account value at the closes (a bar's low is not
  used). Up to bar `h` the run is the run without the option, so it halts
  exactly when that run's `Max drawdown` would first reach `PCT` percent:
  `closes.csv` in the example below has a `Max drawdown` of 16.514 %, so
  `--max-drawdown 16.51` halts and `--max-drawdown 16.52` does not. Costs
  count: on `rally.csv` below with `--fee 10` the buy is 49 @ 20 plus the fee,
  980 + 10, so the account value at that close is 990, 1 % below the starting
  1,000, and `--max-drawdown 1` halts on that bar.
- `PCT` is above 0 and below 100, decimals allowed (`--max-drawdown 0`,
  `100` or `-5` is `--max-drawdown must be above 0 and below 100, got 0`,
  `--max-drawdown ten` argparse's
  `argument --max-drawdown: invalid float value: 'ten'`, all exit 2). It needs
  `--backtest` but no stop, works on a close-only file and with `--resample`,
  and cannot be combined with `--scan` (exit 2).

Example: `closes.csv` (above), cash 1000, `--short 1 --long 2`. It buys 90 @ 11
on bar 4, so the account value is 1,090.00 on bar 5 (the peak) and 910.00 on
bar 6, (910 - 1,090) / 1,090 = 16.51 % below it.

```
$ python -m trading_assistant closes.csv --backtest --short 1 --long 2 --cash 1000 --max-drawdown 16
...
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Drawdown:    halt at 16.00% below the peak account value at a close; triggered at bar 6, no buy fills after it; 1 buy skipped
...
  End equity:  910.00
```

The halt is on bar 6; the SELL signal of bar 6 sells on bar 7 and keeps its
reason, `signal`, and the BUY signal of bar 8, due on bar 9, is skipped.

In `rally.csv` (`date,close`, closes 10, 10, 10, 10, 11, 20, 32, 28, 30, 25,
35, 36) with `--short 1 --long 3` the drawdown does the selling: the
crossover buys 50 @ 20 on bar 5 (cash 0), the account value is 1,600.00 on
bar 6 and 1,400.00 on bar 7, exactly 12.5 % below, and bar 8's pending signal
is HOLD, so `--max-drawdown 12.5` sells the 50 shares at bar 8's close, 30.00
(`drawdown`), and skips the BUY due on bar 11.

| Run (cash 1000) | What happens | Halt bar | Skipped | End equity |
| --- | --- | --- | --- | --- |
| `closes.csv --short 1 --long 2` | without the option | - | - | 925.00 |
| `... --max-drawdown 16` | halt on bar 6, signal sell on bar 7, bar 9 buy skipped | 6 | 1 | 910.00 |
| `... --max-drawdown 17` | never halts (16.51 % at worst): same as without | - | 0 | 925.00 |
| `rally.csv --short 1 --long 3` | without the option: signal sell on bar 10 @ 35, buys 48 @ 36 on bar 11 | - | - | 1,750.00 |
| `... --max-drawdown 12.5` | halt on bar 7 (exactly 12.5 %), `drawdown` sale on bar 8 @ 30.00 | 7 | 1 | 1,500.00 |
| `... --max-drawdown 12.6` | bar 7 is not enough; halt on bar 9 (21.875 %), signal sell on bar 10 @ 35 | 9 | 1 | 1,750.00 |
| `... --max-drawdown 12 --slippage 1 --fee 1` | buys 49 @ 20.20; halt on bar 7 (12.43 %); `drawdown` sale @ 29.70 (1 % lower), 1.00 fee | 7 | 1 | 1,463.50 |
| `... --max-drawdown 12.5 --max-hold 2` | the time exit sells on bar 7 @ 28 (`time`); that close is 12.5 % below: halt with nothing held | 7 | 1 | 1,400.00 |
| `candles11.csv --short 1 --long 2 --fill open --max-drawdown 16` | buys 92 @ 10.80; halt on bar 6; signal sell at bar 7's open, 9.80 | 6 | 1 | 908.00 |
| `candles11.csv --short 1 --long 2 --stop-loss 10 --max-drawdown 16` | the stop sells on bar 6 @ 9.90; that close is 17.34 % below: halt | 6 | 1 | 901.00 |
| `... --stop-loss 10 --cooldown 3 --max-drawdown 16` | as above; the bar 9 buy is in the cooldown too, but counted once, as a drawdown skip (`Cooldown: ... 0 buys skipped`) | 6 | 1 | 901.00 |

The report's `Drawdown:` line comes just before `Round trips:`, only with the
option; with it the fills also show their reason, even without a stop. A run
without it prints exactly what it printed before. In `--json` the backtest
object gets `max_drawdown_limit_pct` right after `max_hold_bars` (or the exit
settings), and `drawdown_halt_bar` and `drawdown_skipped_buys` right after
`time_exits` (or the other counts); see [JSON output](#json-output---json).
The name is not `max_drawdown_pct` because that key already holds the
drawdown the run actually had (the report's `Max drawdown`):

```
    "take_profit_pct": null,
    "max_drawdown_limit_pct": 16.0,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "drawdown_halt_bar": 6,
    "drawdown_skipped_buys": 1,
```

`drawdown_halt_bar` is `null` when the halt never triggered. `--export` gets
the `reason` column with the option, with `drawdown` on the drawdown sale's
row; it has no column for the halt or the skipped buys, and the existing
`drawdown_pct` column shows the percentage the halt compares (`-12.50` on
bar 7 of `rally.csv`). The config file key is `max_drawdown` (see
[Config file](#config-file---config-file)), `POST /api/backtest` takes
`max_drawdown` (see [`POST /api/backtest`](#post-apibacktest)), and the web
page has a **Max drawdown (%)** field. `--help` describes the option, but the
usage line does not list it. The three read a value differently at the edges;
see [Max drawdown values](#max-drawdown-values).

#### Max drawdown values

The flag, the config key and the API field all take `PCT` as a number above
0 and below 100, and give the flag's range message for one outside it. They
differ in what counts as a number:

| Value | `--max-drawdown` | `max_drawdown =` in a config file | `"max_drawdown"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `16`, `16.5`, `1e1` | used | used | used (a JSON number or a string) |
| `nan`, `inf` | exit 2, `--max-drawdown must be above 0 and below 100, got nan` | exit 1, `max_drawdown needs a finite number, got 'nan'` | 400, `max_drawdown must be a finite number` (also JSON `NaN`, `Infinity`) |
| `1,6` | exit 2, `invalid float value: '1,6'` | exit 1, `max_drawdown needs a number, got '1,6'` | **used as 16**: the API drops commas in number strings, as for every number field |
| `16,5` | exit 2, `invalid float value: '16,5'` | exit 1, `max_drawdown needs a number, got '16,5'` | 400, `--max-drawdown must be above 0 and below 100, got 165` |
| `16%`, `ten` | exit 2, `invalid float value` | exit 1, `needs a number` | 400, `max_drawdown must be a number, got '16%'` |
| `true` / `false` | - | exit 1, `needs a number` | 400, `max_drawdown must be a number` |
| `0`, `100`, `-5` | exit 2, the range message | exit 2, the range message | 400, the range message |

All three also take Python's number spellings such as `1_6` (16) and surrounding
spaces.

### Breakeven stop

`--breakeven PCT` moves a stop up to the entry price once the trade has gone
`PCT` percent in your favour.

- **Arming.** When a bar is over, its high is compared with the entry price
  (the average price paid) plus `PCT` percent. At or above it, the stop is
  armed and stays armed until the position is sold. The entry bar's own high
  never counts, with either `--fill`, and the bar that arms the stop is never
  sold by it: the stop first acts on the next bar.
- **Selling.** Once armed, a bar whose low reaches the entry price sells the
  whole position at the entry price, or at the bar's open if it opens at or
  below it (a gap, as for the other stops). The fill's reason is
  `breakeven`. The level is exactly the entry price, with no allowance for
  fees or slippage, so such a sale still loses the costs.
- **A later buy** into the position moves the average entry price: an armed
  stop stays armed and follows the new average, and an unarmed one measures
  `PCT` from the new average.
- **With the other exits.** It is a stop like `--stop-loss`,
  `--trailing-stop` and `--atr-stop`: the highest level in use is used (on a
  tie the stop, then the trail, then atr, then breakeven), and it wins over
  `--take-profit` on a bar that touches both. Once armed it is always above
  the stop loss and the ATR stop; only the trail can be higher.
- **With `--take-profit` at or below `PCT`** it is allowed, but it can never
  act: the bar whose high would arm it has also reached the target, which
  sells the position on that bar. The exception is a later buy into the
  position. With close fills, a lower-priced buy lowers the average after
  that bar's target check, so the stop can arm below the target and act
  later. With `--fill open`, any later buy (even a higher-priced one) fills
  at a bar's open and takes that bar's one fill, so its target check is
  skipped and the stop can arm on that bar.
- **Cooldown.** It counts as a stop for `--cooldown`: `--cooldown` may be
  used with `--breakeven` alone, a `breakeven` sale starts the cooldown, and a
  config file's `cooldown` is used with it (or with the `breakeven` key). The `--cooldown` error message
  and help still name only `--stop-loss`, `--trailing-stop` and `--atr-stop`.
- **Rules.** `PCT` is above 0 (decimals allowed, no upper limit); `0`, a
  negative number, `nan`, `inf` or a word is a usage error (exit 2; see
  [Breakeven values](#breakeven-values)). Unlike `--take-profit`, which
  takes `inf`, the flag refuses it, as the config key and the API do. It
  needs `--backtest` (exit 2 without), reads the file as a candle file (a
  close-only file is exit 1) and cannot be combined with
  `--resample` yet or with `--scan` (exit 2). It is listed in `--help` but
  not in the usage line. `--json` shows `breakeven_pct` and
  `breakeven_exits` (see [JSON output](#json-output---json)); `--export` gets
  the `reason` column, with `breakeven` on its sales. The config file key is
  `breakeven` (see [Config file](#config-file---config-file)), and
  `POST /api/backtest` takes `breakeven` (see
  [`POST /api/backtest`](#post-apibacktest)), and the web page has a
  **Breakeven (%)** field after **Trailing stop %** (greyed out for a
  close-only CSV; the Trades card then adds "N sold at breakeven").

The report's "Exits:" line shows it, and the "Cooldown:" line names it; a
run without `--breakeven` prints exactly what it printed before. With the
11-bar candle file below (the same bars as the [Cooldown](#cooldown) hand
file, different dates), `--short 1 --long 2 --cash 1000`: the BUY fills on
bar 4 at 11.00, bar 5's high 12 arms the stop at 5 % (11.55), and bar 6's
low 9.5 sells at 11.00. Without the option the SELL signal sells on bar 7 at
10.00 and the run ends at 925.00.

```csv
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,100
2026-01-02,9.2,9.5,8.5,9,100
2026-01-03,8.3,8.5,7.5,8,100
2026-01-04,8.8,9.5,8.5,9,100
2026-01-05,10.8,11.5,10.5,11,100
2026-01-06,11,12,10.8,12,100
2026-01-07,11.5,12,9.5,10,100
2026-01-08,9.8,10.2,9.6,10,100
2026-01-09,10,11.5,9.9,11,100
2026-01-10,10.8,12.5,10.5,12,100
2026-01-11,12,12.4,11.8,12.2,100
```

```text
$ python -m trading_assistant c.csv --backtest --short 1 --long 2 --cash 1000 --breakeven 5
...
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 6     SELL       90 @      11.00  value       990.00  cost     0.00  cash     1,000.00  breakeven
    #3   bar 9     BUY        83 @      12.00  value       996.00  cost     0.00  cash         4.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       breakeven at entry once a later high is 5.00% above it
...
  End equity:  1,016.60
```

`--breakeven 9` gives the same fills (trigger 11.99); `--breakeven 10`
(trigger 12.10) is never armed and the run is the same as without it, 925.00.
`--breakeven 5 --cooldown 3` blocks bars 7 to 9, so the bar 9 buy is skipped
and the run ends in cash at 1,000.00, with the line
`Cooldown:    3 bars after a stop, trail, atr or breakeven exit; 1 buy skipped`.

#### Breakeven values

The three ways to set it read a value the way they read their other number
settings, so they differ at the edges:

| Value | `--breakeven` | `breakeven =` in a config file | `"breakeven"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `5`, `0.5`, `1e1` | used | used | used (also as a string, `"5"`) |
| `0`, `-1` | exit 2, `--breakeven must be above 0, got 0` | exit 2, the same message | 400, the same message |
| `nan` | exit 2, `--breakeven must be above 0, got nan` | exit 1, `breakeven needs a finite number, got 'nan'` | 400, `breakeven must be a finite number` |
| `inf` | exit 2, `--breakeven must be a finite number, got inf` (unlike `--take-profit`, which takes `inf`) | exit 1, `breakeven needs a finite number, got 'inf'` | 400, `breakeven must be a finite number` (also `Infinity`) |
| `1,6` | exit 2, `invalid float value: '1,6'` | exit 1, `breakeven needs a number, got '1,6'` | **used as 16**: the API drops commas in number strings |
| `5%`, `ten` | exit 2, `invalid float value` | exit 1, `needs a number` | 400, `breakeven must be a number, got '5%'` |
| `true` / `false` | - | exit 1, `needs a number` | 400, `breakeven must be a number` |

### Max losses

`--max-losses N` stops buying after `N` losing round trips in a row.

- **What counts.** A round trip is the buy (or buys) that open a position and
  the sale that closes it. It loses when its profit after costs (the net
  proceeds less everything paid for the shares, fees and slippage included)
  is below 0. Every completed round trip counts, whatever sold it: the
  strategy's SELL, a stop, target, trailing stop, ATR stop or breakeven
  stop, a `--max-hold` sale (`time`) or a `--max-drawdown` sale
  (`drawdown`). A target sale can lose too, when the costs are larger than
  the gain. A position still held at the end is not a completed round trip.
- **What resets the count.** Any round trip that did not lose sets the count
  back to 0: a win, and also one at exactly 0.00. Costs count, so a round
  trip that sells at its buying price but pays a fee is a loss.
- **The halt.** When the count reaches `N` with the sale on bar `h`, the run
  halts, once. From bar `h + 1` to the end no buy can fill. A buy due then is
  dropped (not delayed) and counted, even one that would have got 0 shares. A
  strategy that keeps signalling (`breakout`) is counted on every bar it
  signals. A BUY signal on the last bar has no bar to fill on and is not
  counted.
- **Counted once.** A buy that the `--max-drawdown` halt also blocks is
  counted there only. A buy that also falls in a cooldown, or that risk
  sizing would have given 0 shares, is counted here only.
- **Nothing is sold.** Every round trip ends with the whole position sold (a
  `--scale-out` partial sale completes no round trip and does not count), so nothing is
  held when the halt starts, and unlike `--max-drawdown` it makes no sale of
  its own and adds no fill reason.
- **A sale the fees refuse** (cash would go below zero) completes no round
  trip, so it does not count; the position is kept, as without the option.
- `N` is a whole number of at least 1 (`--max-losses 0` or `-1` is
  `--max-losses must be a whole number of at least 1, got 0`,
  `--max-losses 2.5`, `2.0` or `abc` argparse's
  `argument --max-losses: invalid int value: '2.5'`, all exit 2). It needs
  `--backtest` (exit 2 without) but no stop, works on a close-only file and
  with `--resample`, and cannot be combined with `--scan` (exit 2). There is
  no value that turns it off; a large one never triggers, but the report
  still shows its line. `--max-l` to `--max-losse` are short for it (before
  0.15.0 they were unrecognized arguments).

Example: `losses.csv` (`date,close`, dates 2026-01-01 to 2026-01-17, closes
10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13), cash 1000,
`--short 1 --long 2`. Without the option it buys 90 @ 11 on bar 4 and sells
them @ 9 on bar 7 (a loss of 180.00), buys 82 @ 10 on bar 10 and sells them
@ 9 on bar 13 (a loss of 82.00), and buys 61 @ 12 on bar 15; it ends at
799.00.

```
$ python -m trading_assistant losses.csv --backtest --short 1 --long 2 --cash 1000 --max-losses 2
...
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00
    #2   bar 7     SELL       90 @       9.00  value       810.00  cost     0.00  cash       820.00
    #3   bar 10    BUY        82 @      10.00  value       820.00  cost     0.00  cash         0.00
    #4   bar 13    SELL       82 @       9.00  value       738.00  cost     0.00  cash       738.00
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Max losses:  halt after 2 losing round trips in a row; triggered at bar 13, no buy fills after it; 1 buy skipped
  Round trips: 2 completed, 0 made money (0%)
...
  End equity:  738.00
```

`reset.csv` has the closes 10, 9, 10, 10, 9, 8, 9, 10, 9, 12, 12, 11, 10, 11,
10, 8, 9, 10, 11: a loss (-200.00, sold on bar 5), a win (+160.00, bar 9), a
loss (-160.00, bar 12) and a loss (-160.00, bar 15), then a buy of 64 @ 10 on
bar 17; 704.00 without the option. `zero.csv` is `reset.csv` with the closes
of bars 9 and 10 at 10: a loss (-200.00), a round trip at exactly 0.00 (80
bought @ 10 on bar 7, sold @ 10 on bar 9) and a loss (-160.00, bar 12), then
a buy of 64 @ 10 on bar 14; 704.00 without the option. `c.csv` is the
candle file of [Breakeven stop](#breakeven-stop), and `dd.csv` has the
closes 10, 10, 10, 10, 11, 20, 19, 18.5, 15, 14, 16, 16, 17.

| Run (cash 1000, `--short 1 --long 2` unless shown) | What happens | Halt bar | Skipped | End equity |
| --- | --- | --- | --- | --- |
| `losses.csv` | without the option | - | - | 799.00 |
| `... --max-losses 1` | halt on bar 7; the buys due on bars 10 and 15 are skipped | 7 | 2 | 820.00 |
| `... --max-losses 2` | halt on bar 13; the buy due on bar 15 is skipped | 13 | 1 | 738.00 |
| `... --max-losses 3` | only two losses: the same as without | - | 0 | 799.00 |
| `... --max-losses 1 --fee 1` | as with 1, with a 1.00 fee on each fill | 7 | 2 | 818.00 |
| `... --max-losses 1 --max-hold 2` | the time exit sells 90 @ 10 on bar 6 (-90.00, `time`): halt | 6 | 2 | 910.00 |
| `... --max-losses 1 --strategy breakout --param window=1` | buys on bars 4 and 6, sells 91 @ 9 on bar 7 (-181.00): halt; the strategy keeps signalling, 5 buys skipped | 7 | 5 | 819.00 |
| `... --max-losses 1 --fee 495` | the fee refuses the sales on bars 7 and 13: no round trip, no halt; 45 shares held | - | 0 | 595.00 |
| first 15 closes of `losses.csv`, `--max-losses 2` | halt on bar 13; the BUY signal of bar 14 is on the last bar and is not counted | 13 | 0 | 738.00 |
| `reset.csv --max-losses 2` | the win resets the count (1, 0, 1, 2): halt on bar 15, not 12; the bar 17 buy is skipped | 15 | 1 | 640.00 |
| `zero.csv --max-losses 2` | the 0.00 round trip resets the count (1, 0, 1): never halts | - | 0 | 704.00 |
| `zero.csv --max-losses 2 --fee 1` | the same round trip now pays 2.00 in fees (-2.00): halt on bar 9 | 9 | 2 | 798.00 |
| `c.csv --stop-loss 10 --max-losses 1` | the stop sells 90 @ 9.90 on bar 6 (-99.00): halt; the bar 9 buy is skipped | 6 | 1 | 901.00 |
| `c.csv --stop-loss 10 --fill open --max-losses 1` | buys 92 @ 10.80; the stop sells @ 9.72 on bar 6 (-99.36) | 6 | 1 | 900.64 |
| `c.csv --take-profit 5 --fee 60 --max-losses 1` | the target sells 85 @ 11.55 on bar 5, but after the fees it loses (921.75 - 995.00 = -73.25) | 5 | 1 | 926.75 |
| `c.csv --stop-loss 10 --cooldown 3 --max-losses 1` | as with the stop; the bar 9 buy is in the cooldown too, but counted once, here (`Cooldown: ... 0 buys skipped`) | 6 | 1 | 901.00 |
| `dd.csv --short 1 --long 3 --max-drawdown 5 --max-losses 1` | drawdown halt on bar 6; the `drawdown` sale of 50 @ 18.50 on bar 7 (-75.00) completes the streak; the bar 11 buy is counted as a drawdown skip (`Max losses: ... 0 buys skipped`) | 7 | 0 | 925.00 |

The report's `Max losses:` line comes just before `Round trips:` (after the
`Drawdown:` line when that is there), only with the option; a run without it
prints exactly what it printed before. It adds no fill reason, so the fills
show a reason only when another option gives them one, and `--export` has the
same columns as without it (a bar whose buy was skipped is a row without an
action). In `--json` the backtest object gets `max_losses` right after
`max_drawdown_limit_pct` (or where that key would be), and `loss_halt_bar` and
`loss_skipped_buys` right after `drawdown_skipped_buys` (or where that key
would be), just before `fills`; see [JSON output](#json-output---json):

```
    "take_profit_pct": null,
    "max_losses": 2,
    "trades": 4,
    "buys": 2,
    "sells": 2,
    "loss_halt_bar": 13,
    "loss_skipped_buys": 1,
    "fills": [
```

`loss_halt_bar` is the bar of the sale that completed the streak, `null` when
it never did. The config file key is `max_losses` (see
[Config file](#config-file---config-file)), `POST /api/backtest` takes
`max_losses` (see [`POST /api/backtest`](#post-apibacktest)), and the web page
has a **Max losses** field. `--help` describes the option after `--breakeven`,
but the usage line does not list it. The sweep, walk-forward, portfolio,
Monte Carlo and drawdowns commands do not take it (`unrecognized arguments`,
exit 2).

#### Max losses values

The flag, the config key and the API field all take `N` as a whole number of
at least 1 and give the flag's message for one below it. They differ in what
counts as a whole number:

| Value | `--max-losses` | `max_losses =` in a config file | `"max_losses"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `2`, `+2` | used | used | used (a JSON number or a string, `"2"`, `" 2 "`) |
| `1_6` | used as 16 | used as 16 | `"1_6"` used as 16 |
| `2.0` | exit 2, `invalid int value: '2.0'` | exit 1, `max_losses needs a whole number, got '2.0'` | the JSON number `2.0` is used as 2; the string `"2.0"` is a 400, `max_losses must be a whole number, got '2.0'` |
| `2.5`, `abc`, `inf`, `1,6` | exit 2, `invalid int value: '2.5'` | exit 1, `max_losses needs a whole number, got '2.5'` | 400, `max_losses must be a whole number, got '2.5'` (the JSON number `2.5`: `got 2.5`; `Infinity`: `got inf`); unlike the number fields, commas are not dropped |
| `0`, `-1` | exit 2, `--max-losses must be a whole number of at least 1, got 0` | exit 2, the same message | 400, the same message |
| `true` / `false` | - | exit 1, `max_losses needs a whole number, got 'true'` | 400, `max_losses must be a whole number` |

The API reads `null`, `""` or a missing key as off. This is exactly how
`max_hold` and `min_hold` are read on each path.

### Scale out

`--scale-out PCT` takes half of a winning position off once and lets the rest
run.

- **When.** On a bar after the entry bar whose high reaches the entry price
  plus `PCT` percent, half the shares held (rounded down) are sold at that
  level, or at the bar's open if it opens at or above it (a gap, as for the
  target). The fill's reason is `scale_out`. The entry bar's own high never
  counts.
- **Once per position.** It sells at most once per position: a later buy into
  the position adds shares but cannot make it scale out again, and the next
  position (after the rest is sold) can. With 1 share held, half is 0 shares:
  nothing is sold, and the position can still scale out once a later buy
  makes it 2 or more. A partial sale the fees would refuse is not made, and is
  tried again on later bars.
- **The rest** stays open and is sold by whatever would have sold it: the
  strategy's SELL (which sells everything left), a stop, target, trailing
  stop, ATR stop or breakeven stop, `--max-hold` or `--max-drawdown`.
- **The entry price** is the average cost of the shares still held. The
  partial sale does not change it, so every level measured from it (the stop,
  the target, the breakeven trigger and level, the ATR stop, the trailing
  stop's start) stays where it was. A later buy averages the new shares with
  the ones still held, not with the ones sold.
- **Any other fill on the bar wins.** A bar has at most one fill, and the
  scale-out only takes a bar nothing else fills on. A stop or target the bar
  also reaches sells the whole position, and so does the strategy's SELL due
  on that bar; a BUY due on that bar fills instead. With close fills it comes
  after the bar's range (stops and target) and the signal fill at the close,
  and before `--max-hold` and `--max-drawdown`: a time exit or drawdown sale
  due on a bar the scale-out takes waits for the next bar. With `--fill open`
  the signal fill and, when due, a gap through a stop or the target, the time
  exit, the drawdown sale and an `--add-on` buy all happen at the open and
  come first; the scale-out then comes after the bar's stops and target.
- **Not a round trip.** A round trip still goes from no shares to no shares,
  and the partial sale is part of it: its proceeds count in the round trip
  the rest completes. So `Round trips:`, the win rate, the profit factor, the
  average win and loss and `--max-losses` see one round trip with all its
  sales. The `Trades:` line counts the partial sale as a sell.
- **With other options.** It is not a stop: it starts no cooldown, and
  `--cooldown` with only `--scale-out` is still a usage error. `--min-hold`
  does not hold it back. Slippage and fees apply as for every sell. With
  `--take-profit` at or below `PCT` it is allowed but never acts: the bar that
  reaches it has also reached the target, which sells everything.
- **Rules.** `PCT` is above 0 (decimals allowed, no upper limit); `0`, a
  negative number, `nan`, `inf` or a word is a usage error (exit 2; see
  [Scale out values](#scale-out-values)). It needs `--backtest` (exit 2
  without), reads the file as a candle file (a close-only file is exit 1) and
  cannot be combined with `--resample` yet or with `--scan` (exit 2). It
  needs no other exit option. It is listed in `--help`, after `--max-losses`,
  but not in the usage line. `--scal` to `--scale-ou` are short for it, while
  `--sc` and `--sca` still mean `--scan`.

The report adds a `Scale out:` line right after the `Exits:` line (or where it
would be), only with the option; a run without it prints exactly what it
printed before. With the 11-bar `c.csv` of [Breakeven stop](#breakeven-stop),
`--short 1 --long 2 --cash 1000`: the BUY fills on bar 4, 90 @ 11.00; bar 5's
high 12 reaches 11.55, so 45 are sold at 11.55; the SELL signal sells the
other 45 at 10.00 on bar 7. The round trip made 519.75 + 450.00 - 990.00 =
-20.25. Without the option the SELL sells all 90 at 10.00 and the run ends at
925.00.

```text
$ python -m trading_assistant c.csv --backtest --short 1 --long 2 --cash 1000 --scale-out 5
...
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 5     SELL       45 @      11.55  value       519.75  cost     0.00  cash       529.75  scale_out
    #3   bar 7     SELL       45 @      10.00  value       450.00  cost     0.00  cash       979.75  signal
    #4   bar 9     BUY        81 @      12.00  value       972.00  cost     0.00  cash         7.75  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the average entry; 1 partial sell, not counted as round trips
  Round trips: 1 completed, 0 made money (0%)
...
  End equity:  995.95
```

| Run (`c.csv`, cash 1000, `--short 1 --long 2`) | What happens | Partial sells | End equity |
| --- | --- | --- | --- |
| without the option | SELL 90 @ 10.00 on bar 7; 75 bought @ 12 on bar 9 | - | 925.00 |
| `--scale-out 5` | 45 @ 11.55 on bar 5, 45 @ 10.00 on bar 7 (round trip -20.25); 81 bought on bar 9 | 1 | 995.95 |
| `--scale-out 9` | 45 @ 11.99 on bar 5 (round trip -0.45); 83 bought on bar 9 | 1 | 1,016.15 |
| `--scale-out 10` | 12.10 is never reached (the highs while held are 12, 12 and 10.20; after the bar 9 buy the level is 13.20, bar 10's high 12.40): as without | 0 | 925.00 |
| `--scale-out 5 --stop-loss 10` | the stop stays at 9.90: 45 @ 9.90 on bar 6 (`stop`; round trip -24.75) | 1 | 991.45 |
| `--scale-out 5 --breakeven 5` | bar 5 also arms the breakeven stop at 11.00: 45 @ 11.00 on bar 6 (round trip +24.75) | 1 | 1,041.75 |
| `--scale-out 5 --take-profit 8` | bar 5 reaches the target 11.88 too: the target sells all 90 and there is no partial sale | 0 | 1,097.00 |
| `--scale-out 9 --take-profit 5` | at or above the target: never acts; the same fills as `--take-profit 5` alone | 0 | 1,066.90 |
| `--scale-out 5 --max-hold 1` | the time exit due on bar 5 waits: 45 @ 10.00 on bar 6 (`time`); 81 bought on bar 9 and sold @ 12.20 on bar 10 (`time`) | 1 | 995.95 |
| `--scale-out 5 --fill open` | 92 @ 10.80 (level 11.34): 46 @ 11.34 on bar 5, 46 @ 9.80 on bar 7; 90 bought on bar 9, and bar 10 opens at 12.00, above 11.34: 45 @ 12.00 (a gap) | 2 | 1,095.84 |
| `--scale-out 5 --fill open --max-hold 1` | the time exits at the opens of bars 5 and 10 come first (bar 10 would have been a gap) | 0 | 1,131.20 |
| `--scale-out 5 --min-hold 5` | the bar 7 SELL is skipped; the bar 9 buy adds 44 (average 11.49, level 12.07); bar 10's high 12.40 reaches it, but the position has already scaled out | 1 | 1,087.55 |
| `--scale-out 5 --cash 1001` | 91 shares: 45 sold (rounded down), the other 46 on bar 7 | 1 | 995.95 |
| `--scale-out 5 --cash 12` | 1 share: nothing to sell; as without | 0 | 11.00 |
| `--scale-out 5 --fee 1` | the partial sale pays the fee too: round trip 518.75 + 449.00 - 991.00 = -23.25 | 1 | 991.95 |
| `--scale-out 9 --max-losses 1` | one round trip (-0.45), completed on bar 7: the halt is on bar 7, not on bar 5; the bar 9 buy is skipped | 1 | 999.55 |
| `--scale-out 9 --stop-loss 5 --max-losses 1` | the rest alone lost (45 @ 10.45), but the round trip made +19.80: no halt | 1 | 1,036.60 |

With `--json` the backtest object gets `scale_out_pct` right after
`breakeven_pct` (or the exit setting before it) and `scale_out_exits`, the
number of partial sales, right after `breakeven_exits` (or `risk_skipped_buys`,
or `sells`); see [JSON output](#json-output---json):

```
    "take_profit_pct": null,
    "scale_out_pct": 5.0,
    "trades": 4,
    "buys": 2,
    "sells": 2,
    "scale_out_exits": 1,
    "fills": [
```

`--export` gets the `reason` column, with `scale_out` on the partial sales;
its `position` column shows the shares left. The config file key is
`scale_out` (see [Config file](#config-file---config-file)),
`POST /api/backtest` takes `scale_out` (see
[`POST /api/backtest`](#post-apibacktest)), and the web page has a
**Scale out (%)** field after **Breakeven (%)** (greyed out for a close-only
CSV; the Trades card then adds "N partial sells by scale-out"). The sweep,
walk-forward, portfolio, Monte Carlo and drawdowns commands do not take it
(`unrecognized arguments`, exit 2).

#### Scale out values

The three ways to set it read a value the way `breakeven` is read on each
path:

| Value | `--scale-out` | `scale_out =` in a config file | `"scale_out"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `5`, `0.5`, `1e1` | used | used | used (also as a string, `"5"`) |
| `0`, `-1` | exit 2, `--scale-out must be above 0, got 0` | exit 2, the same message | 400, the same message |
| `nan` | exit 2, `--scale-out must be above 0, got nan` | exit 1, `scale_out needs a finite number, got 'nan'` | 400, `scale_out must be a finite number` |
| `inf` | exit 2, `--scale-out must be a finite number, got inf` | exit 1, `scale_out needs a finite number, got 'inf'` | 400, `scale_out must be a finite number` (also `Infinity`) |
| `1,6` | exit 2, `invalid float value: '1,6'` | exit 1, `scale_out needs a number, got '1,6'` | **used as 16**: the API drops commas in number strings |
| `5%`, `ten` | exit 2, `invalid float value` | exit 1, `needs a number` | 400, `scale_out must be a number, got '5%'` |
| `true` / `false` | - | exit 1, `needs a number` | 400, `scale_out must be a number` |

### Add-ons

`--add-on PCT` buys more of a position that is going your way, and
`--max-adds N` says how many times per position (default 1).

- **When.** While shares are held, a close that is `PCT` percent or more
  above the fill price of the latest buy into the position sets off an
  add-on, due on the next bar. The latest buy's price is the price its fill
  records, so with `--slippage` it is the slipped price. Every buy into the
  position counts: the buy that opened it, a signal BUY while it is held
  (the strategy can buy again into a position it holds) and an earlier
  add-on, so each add-on is measured from the buy before it. The close is
  compared with `price x (1 + PCT / 100)` in floating point: after a buy at
  11, `--add-on 10` needs a close above 12.10, and a close of **exactly
  12.10 does not set it off** (11 x 1.1 is 12.100000000000001); 12.11 does.
- **How many.** At most `N` add-on buys per position; the count starts again
  with each new position. A signal BUY into the position becomes the new
  latest buy price but is not one of the `N`.
- **Size.** It is sized like any buy: all the cash, or at most
  `--position-size` of the account value (and never more than the cash), or
  with `--risk-pct` the ATR of the bar that set it off, never of the bar it
  fills on. **With the default all-cash sizing the first buy spends the
  cash, so an add-on almost always gets 0 shares**; `--position-size` or
  `--risk-pct` leave room for it. An add-on that gets 0 shares (for lack of
  cash, by `--position-size` or by the ATR rules) makes no fill and is
  counted on the `Add-ons:` line (`skipped (0 shares)`), not with the risk
  sizing skips; it is not one of the `N` and leaves the latest buy price
  where it was, so the next close is checked again and a long rise can count
  several skips.
- **Fill.** It fills on the next bar at that bar's fill price: its close, or
  its open with `--fill open`. That price can be below the level that set it
  off, when the next bar falls. Slippage and fees apply as for every buy, and
  the fill's reason is `add_on`.
- **What drops it.** It is dropped, not delayed and not counted, when:
  - the close that set it off is a **BUY or SELL signal**. After a BUY the
    signal's own buy takes the next bar (and becomes the new latest buy);
    after a SELL it would add to a position about to be sold. A SELL drops it
    even when `--min-hold` then holds the sale back. (So the signal fill on
    the next bar never meets an add-on: that fill's signal came on this
    close.)
  - **anything else fills on its bar first**, in this order. With close
    fills the add-on comes last: a stop, trailing stop, ATR stop, breakeven
    stop or target reached during the bar, a `--scale-out` partial sale, a
    `--max-hold` time exit and a `--max-drawdown` sale all take the bar
    first. With `--fill open` it fills at the open, like a signal buy: a gap
    through a stop or the target at the open, a time exit at the open and a
    drawdown sale at the open come first, and nothing later in the bar can
    drop it.

  A dropped add-on is not waiting: the next close is checked again, and if it
  is still `PCT` percent above the latest buy, a new add-on is due on the bar
  after it.
- **No look-ahead.** The buy never depends on anything that happens after
  its own fill. With close fills it fills at the close, after the bar's
  range; with `--fill open` it fills at the open, before the bar's range is
  checked.
- **With `--fill open` no exit acts on its bar (a flatter result).** A bar has
  one fill, so once the add-on fills at the open no stop, trailing stop, ATR
  stop, breakeven stop, target or scale-out acts on that bar, even when the
  bar's low goes through the stop; from the next bar on their levels follow
  the new average entry. Real trading would have been stopped out on that bar,
  the add-on's shares too, so this flatters the result: in the table below,
  `k_low5.csv` ends at 1,308.00 with the add-on and 975.01 without it.
- **The entry price** is the average cost of the shares held, so an add-on
  above it raises it, and every level measured from it moves: the stop, the
  target, the breakeven trigger and level (an armed breakeven stop stays
  armed at the new average), the ATR stop (with the distance of the buy that
  opened the position) and the scale-out level. The scale-out is still once
  per position; after it, an add-on averages with the shares still held. The
  trailing stop starts from the higher of the entry price and the highest
  high since entry, so an add-on rarely moves it.
- **One round trip.** An add-on is part of the position's round trip: its
  shares and cost go into it, the trade list's `Shares` and `Outlay` include
  them, and the win rate and `--max-losses` see one round trip. The `Trades:`
  line counts it as a buy. Adding near a top can turn a winning position into
  a losing round trip.
- **Hold clocks.** `--min-hold` and `--max-hold` count from the buy that
  opened the position; an add-on does not restart them, so `--max-hold` can
  sell an add-on one bar after it was bought.
- **Halts and cooldown.** After a `--max-drawdown` halt no add-on fills. The
  halt's own sale takes the bar, so the add-on due then is dropped and not
  counted; only when that sale is refused by the fees does the add-on get its
  turn, and then it is counted with the buys the halt dropped (the `Drawdown:`
  line), not on the `Add-ons:` line. `--max-losses` and `--cooldown` start
  only when nothing is held, so they never meet an add-on.
- **Rules.** `PCT` is above 0 (decimals allowed, no upper limit); `0`, a
  negative number, `nan`, `inf` or a word is a usage error (exit 2; see
  [Add-on values](#add-on-values)). `N` is a whole number of at least 1, and
  `--max-adds` without `--add-on` is a usage error (exit 2). Both need
  `--backtest` (exit 2 without) and cannot be combined with `--scan`
  (exit 2). They need no stop and no candle file: a close-only file works,
  and so does `--resample` (the add-on then works on the resampled bars).
  They are listed in `--help`, after `--scale-out`, but not in the usage
  line. `--ad` to `--add-o` are short for `--add-on` and `--max-a` to
  `--max-add` for `--max-adds`; `--ma`, `--max` and `--max-` still mean
  `--max-hold`, and `--a` is still ambiguous (its message now also names
  `--add-on`).

The report adds an `Add-ons:` line right after the `Scale out:` line (or
where it would be), only with the option; a run without it prints exactly
what it printed before. With `--add-on` every fill carries its reason.

The examples use `up.csv`, a close-only file (closes 10, 9, 8, 9, 11, 12, 13,
14, 15, 14, 13, 12), with `--short 1 --long 2 --cash 1000`. The BUY signal
of bar 3 fills on bar 4 at 11.00 and the SELL signal of bar 9 on bar 10 at
13.00. With `--position-size 0.5` the buy is int(500 / 11) = 45 shares
(495.00, cash 505.00), and without the option the run ends at 1,090.00.
`--add-on 10` sets the level at 11 x 1.1 = 12.10: bar 5 closes at 12, below
it, and bar 6 at 13, so the add-on fills on bar 7 at 14. The position size
allows int(0.5 x (505 + 45 x 14) / 14) = int(567.5 / 14) = 40 shares, the
cash int(505 / 14) = 36, so it buys 36 (504.00, cash 1.00), and the SELL
sells all 81 at 13.00:

```text
$ python -m trading_assistant up.csv --backtest --short 1 --long 2 --cash 1000 --position-size 0.5 --add-on 10
Bars:    12
Last:    12.00
Signal:  HOLD
RSI:     n/a
Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting
  Start cash:  1,000.00
  Trades:      3 (2 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash       505.00  signal
    #2   bar 7     BUY        36 @      14.00  value       504.00  cost     0.00  cash         1.00  add_on
    #3   bar 10    SELL       81 @      13.00  value     1,053.00  cost     0.00  cash     1,054.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Sizing:      each buy at most 50% of account value (costs and slippage included)
  Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)
  Round trips: 1 completed, 1 made money (100%)
  Comparison              Strategy    Buy & hold
    End equity            1,054.00      1,200.00
    Return                  +5.40%       +20.00%
    Max drawdown           -13.32%       -20.00%
    Trades                       3             1
    Costs paid                0.00          0.00
  End cash:    1,054.00
  End shares:  0 @ 12.00
  End equity:  1,054.00
  Return:      +5.40%
Research aid only. Not financial advice.
```

The one round trip spent 495 + 504 = 999.00 and got back 1,053.00. With
`--add-on 20` the level is 13.20: bar 6's 13 is below it, bar 7's 14 is not,
so the add-on fills on bar 8 at 15, int(505 / 15) = 33 shares (the position
size would allow int(590 / 15) = 39); the round trip spent 990.00 and got
back 1,014.00:

```text
$ python -m trading_assistant up.csv --backtest --short 1 --long 2 --cash 1000 --position-size 0.5 --add-on 20
...
  Trades:      3 (2 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash       505.00  signal
    #2   bar 8     BUY        33 @      15.00  value       495.00  cost     0.00  cash        10.00  add_on
    #3   bar 10    SELL       78 @      13.00  value     1,014.00  cost     0.00  cash     1,024.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Sizing:      each buy at most 50% of account value (costs and slippage included)
  Add-ons:     up to 1 per position, a buy on the next bar after a close 20.00% or more above the latest buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)
  Round trips: 1 completed, 1 made money (100%)
...
  End equity:  1,024.00
```

With `--add-on 50` the level is 16.50, above every close, and the run is the
one without the option apart from the reasons and the `Add-ons:` line:

```text
$ python -m trading_assistant up.csv --backtest --short 1 --long 2 --cash 1000 --position-size 0.5 --add-on 50
...
  Trades:      2 (1 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash       505.00  signal
    #2   bar 10    SELL       45 @      13.00  value       585.00  cost     0.00  cash     1,090.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Sizing:      each buy at most 50% of account value (costs and slippage included)
  Add-ons:     up to 1 per position, a buy on the next bar after a close 50.00% or more above the latest buy price, when nothing else fills on that bar; 0 add-on buys, 0 skipped (0 shares)
  Round trips: 1 completed, 1 made money (100%)
...
  End equity:  1,090.00
```

Without `--position-size` the buy takes int(1000 / 11) = 90 shares and leaves
10.00 of cash. The closes of bars 6, 7 and 8 (13, 14, 15) are all above
12.10, so add-ons are due on bars 7, 8 and 9, and each gets int(10 / price)
= 0 shares: three skips, none of them one of the `N`, and the latest buy
price stays 11. Bar 9's close is the SELL, so nothing is due on bar 10. The
fills and the end equity are those of the run without the option:

```text
$ python -m trading_assistant up.csv --backtest --short 1 --long 2 --cash 1000 --add-on 10
...
  Trades:      2 (1 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 10    SELL       90 @      13.00  value     1,170.00  cost     0.00  cash     1,180.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest buy price, when nothing else fills on that bar; 0 add-on buys, 3 skipped (0 shares)
  Round trips: 1 completed, 1 made money (100%)
...
  End equity:  1,180.00
```

Small runs on close-only files (`--short 1 --long 2 --cash 1000`;
`up2.csv` is `up.csv` with bar 5 at 12.15, and `level.csv` is 10, 9, 8, 9,
11, 12.10, 12.2, 12.3, 12.4, 12.0, 11.5):

| Run | What happens | Add-on buys | Skipped | End equity |
| --- | --- | --- | --- | --- |
| `up.csv --position-size 0.5` | no add-on | - | - | 1,090.00 |
| `up.csv --position-size 0.5 --add-on 10` | 36 @ 14.00 on bar 7 | 1 | 0 | 1,054.00 |
| `up.csv --position-size 0.5 --add-on 20` | 33 @ 15.00 on bar 8 | 1 | 0 | 1,024.00 |
| `up.csv --position-size 0.5 --add-on 50` | 16.50 is never reached | 0 | 0 | 1,090.00 |
| `up.csv --add-on 10` | all the cash: 0 shares on bars 7, 8 and 9 | 0 | 3 | 1,180.00 |
| `up.csv --position-size 0.5 --add-on 10 --max-hold 3` | the time exit sells 45 @ 14.00 on bar 7, the add-on's bar | 0 | 0 | 1,135.00 |
| `up.csv --position-size 0.5 --add-on 10 --max-hold 4` | 36 @ 14.00 on bar 7; the clock runs from bar 4, so bar 8 sells all 81 @ 15.00 (`time`) | 1 | 0 | 1,216.00 |
| `up2.csv --position-size 0.5 --fee 1 --add-on 10` | 45 @ 11.00 (496.00 with the fee); 12.15 is above 12.10: 38 @ 13.00 on bar 6 | 1 | 0 | 1,087.00 |
| `up2.csv --position-size 0.5 --fee 1 --slippage 1 --add-on 10` | the buy records 11.11, so the level is 12.221 and 12.15 is below it: 36 @ 14.14 on bar 7 | 1 | 0 | 1,028.72 |
| `level.csv --position-size 0.5 --add-on 10` | bar 5's exactly 12.10 does not set it off; bar 6's 12.2 does: 41 @ 12.30 on bar 7 (with 12.11 on bar 5: 41 @ 12.20 on bar 6, 993.80) | 1 | 0 | 989.70 |

Spacing, with `s.csv` (closes 10, 8, 9, 10, 11.5, 12, 13, 14, 15, 17, 16,
16.5; BUY on bar 2, SELL on bar 10), `--position-size 0.25 --add-on 10`:

1. Bar 3 buys int(250 / 10) = 25 @ 10.00 (cash 750.00); the level is 11.
   Bar 4 closes at 11.5, so add-on 1 fills on bar 5 at 12:
   int(0.25 x (750 + 25 x 12) / 12) = int(262.5 / 12) = 21 shares (252.00,
   cash 498.00). The level is now 12 x 1.1 = 13.2.
2. With `--max-adds 1` (the default) that is all: bar 11 sells the 46 shares
   at 16.50 = 759.00, and the run ends at 498 + 759 = **1,257.00** (round trip
   502.00 spent, 759.00 back).
3. With `--max-adds 2`, bar 6's 13 is below 13.2 and bar 7's 14 is not, so
   add-on 2 fills on bar 8 at 15: int(0.25 x (498 + 46 x 15) / 15) =
   int(297 / 15) = 19 shares (285.00, cash 213.00); the level is 16.5. Bar 11
   sells 65 @ 16.50 = 1,072.50: 1,285.50.
4. With `--max-adds 3`, bar 9's 17 sets off add-on 3, which fills on bar 10 at
   16: the position size allows int(0.25 x (213 + 65 x 16) / 16) =
   int(313.25 / 16) = 19, the cash int(213 / 16) = 13, so 13 shares (208.00,
   cash 5.00). Bar 10's own close is the SELL, so **the add-on is bought on the
   close that gives the SELL, one bar before the sale**: bar 11 sells 78 @
   16.50 = 1,287.00, and the run ends at 5 + 1,287 = **1,292.00** (round trip
   995.00 spent, 1,287.00 back).

More close-only cases (the BUY/SELL and halt rules):

| Run | What happens | End equity |
| --- | --- | --- |
| `b.csv` (10, 8, 9, 10, 9.5, 11.2, 11.5, 12.4, 13, 13.5, 13, 12.8) `--position-size 0.3 --min-hold 4 --add-on 10` | 30 @ 10.00 on bar 3; bar 4's SELL is held back by `--min-hold`; bar 5's close (11.2, above 11) is a BUY, so no add-on: the signal buys 27 @ 11.50 on bar 6, the new latest buy (level 12.65, so bar 7's 12.4 sets nothing off); bar 8's 13 does: 25 @ 13.50 on bar 9, allowed although `N` is 1 (the signal buy does not count) | 1,101.60 |
| `m.csv` (10, 10, 10, 11.6, 13.4, 15, 15.5, 16, 16) `--strategy momentum --param window=1 --param threshold=15 --position-size 0.3 --min-hold 3 --add-on 10` | 22 @ 13.40 on bar 4 (level 14.74); bar 5 closes at 15, above it, but it is a SELL (the rate of change falls through 15 on a rising close): no add-on on bar 6, although `--min-hold` holds the sale back; bar 6's 15.5 sets one off: 19 @ 16.00 on bar 7 | 1,057.20 |
| `below.csv` (10, 9, 8, 9, 11, 12.5, 11.8, 11.5, 11) `--position-size 0.5 --add-on 10` | bar 5's 12.5 sets it off; bar 6 falls to 11.80 (a SELL), and the add-on buys 42 @ 11.80 there, below 12.10; bar 7 sells all 87 @ 11.50 (without the option: 1,022.50) | 1,009.90 |
| `d.csv` (10, 8, 9, 10, 12, 11.6, 11.3, 11.2, 11.5) `--add-on 10 --max-drawdown 5 --min-hold 10` | all-in: 100 @ 10.00; the add-on due on bar 5 gets 0 shares (1 skip); bar 6's close sets one off and also the halt (1,130 is 5.83 % below 1,200): bar 7's drawdown sale takes the bar and the add-on is dropped, counted nowhere | 1,120.00 |
| `f.csv` (10, 8, 9, 10, 12, 12.5, 16, 16.5) `--fee 600 --add-on 10 --max-drawdown 50` | 40 @ 10.00 pays a 600 fee and halts the run at once; the drawdown sale is refused while 40 x price - 600 is below 0, so on bar 5 the add-on gets its turn and is counted in the `Drawdown:` line's skipped buys (1); on bar 6 the sale (40 @ 16.00) takes the bar | 40.00 |

Candle cases, with `k.csv` (`--short 1 --long 2 --cash 1000
--position-size 0.5`):

```csv
date,open,high,low,close,volume
2026-01-01,10,10.2,9.8,10,100
2026-01-02,8.5,8.6,7.9,8,100
2026-01-03,8.5,9.1,8.4,9,100
2026-01-04,9.8,10.1,9.7,10,100
2026-01-05,10.5,11.6,10.4,11.5,100
2026-01-06,11.6,12.6,11.5,12.5,100
2026-01-07,12.6,13.5,11,13.4,100
2026-01-08,13.5,14.6,13.3,14.5,100
2026-01-09,14.4,14.5,13.9,14,100
2026-01-10,13.9,14,13.4,13.5,100
```

The BUY of bar 2 fills on bar 3 (50 @ 10.00 with close fills, 51 @ 9.80 with
`--fill open`) and the SELL of bar 8 on bar 9. Bar 4's close of 11.5 sets off
`--add-on 10`, due on bar 5. `k_low5.csv` is `k.csv` with bar 5's low at 9.0,
`k_gap5.csv` with bar 5 opening at 9.0 (low 8.9).

| Run | Without `--add-on` | With `--add-on 10` |
| --- | --- | --- |
| close fills | 1,175.00 | 40 @ 12.50 on bar 5 (cash allows 40 of the 45): 1,215.00 |
| `--scale-out 30` | level 13: 25 @ 13.00 on bar 6; 1,162.50 | the add-on moves the average to 1,000 / 90 = 11.11 and the level to 14.44: 45 @ 14.44 on bar 7; 1,257.50 |
| `--scale-out 20` | level 12: 25 @ 12.00 on bar 5; 1,137.50 | the scale-out takes bar 5 and drops the add-on; bar 5's close 12.5 is still above 11, so a new one fills on bar 6: 42 @ 13.40; 1,141.70 |
| `--take-profit 20` | the target sells 50 @ 12.00 on bar 5; 1,100.00 | the target takes bar 5, the add-on is dropped; 1,100.00 |
| `--breakeven 10` | armed on bar 4 at 10, never reached; 1,175.00 | the add-on moves the armed level to 11.11; bar 6's low 11 reaches it: 90 @ 11.11, a round trip of 0.00; 1,000.00 |
| `k_low5.csv --stop-loss 5` | the stop (9.50) sells 50 during bar 5; 975.00 | the stop takes bar 5 before the close, the add-on is dropped; 975.00 |
| `--fill open` | 1,209.10 | 43 @ 11.60 at bar 5's open; 1,308.00 |
| `k_low5.csv --fill open --stop-loss 5` | the stop (9.31) sells 51 during bar 5; 975.01 | the add-on fills at bar 5's open and the bar's low of 9.0 sells nothing; from bar 6 the stop is (499.8 + 498.8) / 94 x 0.95 = 10.09, never reached; **1,308.00, the flatter result** |
| `k_gap5.csv --fill open --stop-loss 5` | bar 5 opens through the stop: 51 @ 9.00; 959.20 | the gap is known at the open: the stop sells first, the add-on is dropped; 959.20 |
| `--fill open --max-hold 2` | the time exit sells 51 @ 11.60 at bar 5's open; 1,091.80 | the time exit at the open comes first; 1,091.80 |
| `--fill open --scale-out 20` | 25 @ 11.76 on bar 5; 1,155.60 | the add-on at bar 5's open leaves no scale-out on that bar; the level from the new average is 12.75, reached on bar 6: 47 @ 12.75; 1,253.86 |

With `--json` the backtest object gets `add_on_pct` and `max_adds` right
after `scale_out_pct` (or the exit setting before it), and `add_on_buys` (the
add-on fills) and `add_on_skipped_buys` (the add-ons that got 0 shares) right
after `scale_out_exits` (or `breakeven_exits`, `risk_skipped_buys`, or
`sells`), in the order of the report's lines; see
[JSON output](#json-output---json). `max_adds` is `1` when `--max-adds` is
not given. For the first example:

```
    "take_profit_pct": null,
    "add_on_pct": 10.0,
    "max_adds": 1,
    "trades": 3,
    "buys": 2,
    "sells": 1,
    "add_on_buys": 1,
    "add_on_skipped_buys": 0,
    "fills": [
```

and without `--position-size` `"add_on_buys": 0, "add_on_skipped_buys": 3`.
The fills' `reason` is `add_on` for the add-ons.

`--export` gets the `reason` column, with `add_on` on the add-on buys; there
is no column for the counts. The config file keys are `add_on` and
`max_adds` (see [Config file](#config-file---config-file)),
`POST /api/backtest` takes `add_on` and `max_adds` (see
[`POST /api/backtest`](#post-apibacktest)), and the web page has **Add-on
(%)** and **Max adds** fields after **Max drawdown (%)** (never greyed out;
the Trades card then adds "N add-on buys, M add-ons skipped"). The sweep,
walk-forward, portfolio, Monte Carlo and drawdowns commands do not take them
(`unrecognized arguments`, exit 2).

#### Add-on values

The three ways to set them read a value the way `scale_out` and `max_hold`
are read on each path:

| Value | `--add-on` | `add_on =` in a config file | `"add_on"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `10`, `0.5`, `1e1` | used | used | used (also as a string, `"10"`) |
| `0`, `-1` | exit 2, `--add-on must be above 0, got 0` | exit 2, the same message | 400, the same message |
| `nan` | exit 2, `--add-on must be above 0, got nan` | exit 1, `add_on needs a finite number, got 'nan'` | 400, `add_on must be a finite number` |
| `inf` | exit 2, `--add-on must be a finite number, got inf` | exit 1, `add_on needs a finite number, got 'inf'` | 400, `add_on must be a finite number` (also `Infinity`, `NaN`) |
| `1,6` | exit 2, `invalid float value: '1,6'` | exit 1, `add_on needs a number, got '1,6'` | **used as 16**: the API drops commas in number strings |
| `5%`, `ten` | exit 2, `invalid float value` | exit 1, `needs a number` | 400, `add_on must be a number, got '5%'` |
| `true` / `false` | - | exit 1, `needs a number` | 400, `add_on must be a number` |

| Value | `--max-adds` | `max_adds =` in a config file | `"max_adds"` in `POST /api/backtest` |
| --- | --- | --- | --- |
| `2` | used | used | used (also `"2"`, and the JSON number `2.0`) |
| `0`, `-1` | exit 2, `--max-adds must be a whole number of at least 1, got 0` | exit 2, the same message (also without `add_on`) | 400, the same message |
| `2.5`, `2.0`, `abc` | exit 2, `invalid int value: '2.5'` | exit 1, `max_adds needs a whole number, got '2.5'` | 400, `max_adds must be a whole number, got 2.5` (the string `"2.0"` too) |
| `true` / `false` | - | exit 1, `needs a whole number` | 400, `max_adds must be a whole number` |
| without an add-on | exit 2, `--max-adds only makes sense together with --add-on` | ignored, like `cooldown` without a stop | 400, the same message as the flag |

### Trade list

`--trade-list` prints the round trips behind the `Round trips:` line, one row
each, after the report.

- **Rows.** One row per completed round trip (the position went from no
  shares to some and back to none), in order, and then, only when shares are
  still held at the end, one more row for that position. The completed rows
  are the round trips the `Round trips:` line counts, so there are as many,
  and as many of them made money (a profit after costs above 0; a round trip
  at exactly 0.00 is not a win). A `--scale-out` partial sale is not a row of
  its own: it is part of its round trip.
- **Columns.** `#` (the row number, or `open`), `Entry` (the bar of the buy
  that opened the position), `Exit` (the bar of the sale that completed it),
  `Bars` (exit bar less entry bar), `Shares` (all the shares bought into the
  position, a later buy into it and an `--add-on` buy included), `Outlay` (the cash spent on those
  buys, fees included), `Proceeds` (the net cash from its sales, fees taken
  off, a partial sale included), `P/L` (proceeds less outlay), `Return` (P/L
  divided by the outlay, in percent) and `Reason` (why the sale that completed
  it happened: `signal`, `stop`, `target`, `trail`, `atr`, `breakeven`,
  `time` or `drawdown`). The Reason column is shown even when no exit option
  is on (every reason is then `signal`). Bars are numbered from 0, as in the
  fills.
- **The open row** is not realized. Its `#` and `Exit` say `open`, `Bars`
  counts to the last bar, and `Proceeds` is the net cash of a partial sale, if
  any, plus the shares still held marked at the last close with no selling
  costs (as `End equity:` is), so a real sale would get less by its fees and
  slippage. Its `Reason` is `scale_out` when part of it has been sold and `-`
  otherwise, and the row ends with
  `(unrealized: marked at the last close, no selling costs)`. It never counts
  as a win or a loss.
- **Footer.** The last line repeats the `Round trips:` numbers
  (`1 completed, 0 made money (0%)`, or `0 completed`) and adds
  `, 1 open (unrealized)` when there is an open row. A run with no trades
  prints the one line `Trade list: no trades`.
- **A sale the fees refuse** completes nothing: the round trip goes on until
  a later sale goes through, and ends there.
- **Where.** After the report, and after the `Exported:` line and the "Risk
  and return" block when `--export` or `--stats` is given; before `--chart`.
  It changes nothing else in the output: a run without it prints exactly what
  it printed before, and `--export` writes the same file with or without it.
- **Rules.** It needs `--backtest` (`--trade-list only makes sense together
  with --backtest`, exit 2) and cannot be combined with `--scan` (exit 2). It
  needs no candle file, so it works on a close-only file and with
  `--resample`. It is listed in `--help`, after `--stats`, but not in the
  usage line. `--trad` to `--trade-lis` are short for it; `--tr` and `--tra`
  still mean `--trailing-stop`.

With the 11-bar `c.csv` of [Breakeven stop](#breakeven-stop),
`--short 1 --long 2 --cash 1000`: 90 bought @ 11.00 on bar 4 (990.00) and sold
@ 10.00 on bar 7 (900.00), then 75 bought @ 12.00 on bar 9 and still held at
the close of 12.20 (915.00):

```text
$ python -m trading_assistant c.csv --backtest --short 1 --long 2 --cash 1000 --trade-list
...
  Round trips: 1 completed, 0 made money (0%)
...
  Return:      -7.50%
Trade list (bar index is 0-based)
  #     Entry  Exit  Bars   Shares        Outlay      Proceeds          P/L    Return  Reason
  1         4     7     3       90        990.00        900.00       -90.00    -9.09%  signal
  open      9  open     1       75        900.00        915.00       +15.00    +1.67%  -  (unrealized: marked at the last close, no selling costs)
  1 completed, 0 made money (0%), 1 open (unrealized)
Research aid only. Not financial advice.
```

| Run (`c.csv`, cash 1000, `--short 1 --long 2`) | Completed rows | Open row | Footer |
| --- | --- | --- | --- |
| no other option | 4 -> 7, 3 bars, 90, 990.00, 900.00, -90.00, -9.09%, `signal` | 9, 1 bar, 75, 900.00, 915.00, +15.00, +1.67%, `-` | `1 completed, 0 made money (0%), 1 open (unrealized)` |
| `--scale-out 5` | 4 -> 7, 90, 990.00, 969.75 (519.75 from the bar 5 partial sale + 450.00), -20.25, -2.05%, `signal` | 9, 81, 972.00, 988.20, +16.20, +1.67%, `-` | as above |
| `--stop-loss 10` | 4 -> 6, 2 bars, 90, 990.00, 891.00, -99.00, -10.00%, `stop` | 9, 75, 900.00, 915.00, +15.00, +1.67%, `-` | as above |
| `--scale-out 1` | 4 -> 7, 90, 990.00, 949.95, -40.05, -4.05%, `signal` | 9, 79 bought, 39 sold @ 12.12 on bar 10: 472.68 + 40 x 12.20 = 960.68, +12.68, +1.34%, `scale_out` | as above |
| `--fee 1` | 4 -> 7, 90, 991.00, 899.00, -92.00, -9.28% | 9, 75, 901.00, 915.00 (no fee taken off), +14.00, +1.55% | as above |
| `--position-size 0.5 --min-hold 5` | none (the bar 7 SELL is skipped) | 4, 6 bars, 87 (45 on bar 4 + 42 on bar 9), 999.00, 1,061.40, +62.40, +6.25%, `-` | `0 completed, 1 open (unrealized)` |
| `--position-size 0.5 --min-hold 5 --max-hold 6` | 4 -> 10, 6 bars, 87, 999.00, 1,061.40, +62.40, +6.25%, `time` | none | `1 completed, 1 made money (100%)` |
| `--fee 495` | none: the bar 7 sale would leave -35.00 cash and is refused | 4, 6 bars, 45, 990.00, 549.00, -441.00, -44.55%, `-` | `0 completed, 1 open (unrealized)` |
| `--fee 495 --max-hold 3` | refused on bar 7, sold on bar 8: 4 -> 8, 4 bars, 45, 990.00, 0.00, -990.00, -100.00%, `time` | none | `1 completed, 0 made money (0%)` |
| `--cash 5` | none | none | the one line `Trade list: no trades` |

With `--json` the backtest object gets `trade_list`, only with the option:
one object per row, in the same order, with `open`, `entry_bar`, `exit_bar`
(`null` for the open row), `bars_held`, `shares`, `outlay`, `proceeds`,
`pnl`, `return_pct` and `reason` (`null` where the table shows `-`); an
empty list when there were no trades. It is the last key, after `stats` and
`export`. `round_trips` and `winning_round_trips` do not change. Numbers are
unrounded, as everywhere in `--json`: with `--scale-out 5` the open row's
`proceeds` is `988.1999999999999` where the table shows 988.20.

```
    "trade_list": [
      {
        "open": false,
        "entry_bar": 4,
        "exit_bar": 7,
        "bars_held": 3,
        "shares": 90,
        "outlay": 990.0,
        "proceeds": 900.0,
        "pnl": -90.0,
        "return_pct": -9.090909090909092,
        "reason": "signal"
      },
      {
        "open": true,
        "entry_bar": 9,
        "exit_bar": null,
        "bars_held": 1,
        "shares": 75,
        "outlay": 900.0,
        "proceeds": 915.0,
        "pnl": 15.0,
        "return_pct": 1.6666666666666667,
        "reason": null
      }
    ]
```

The config file key is `trade_list = yes` (see
[Config file](#config-file---config-file)), `POST /api/backtest` takes
`"trade_list": true` (see [`POST /api/backtest`](#post-apibacktest)), and
the web page has a **Trade list** box after the **ATR stop** box. The sweep,
walk-forward, portfolio, Monte Carlo and drawdowns commands do not take it
(`unrecognized arguments`, exit 2).

### Buy and hold comparison

The report's "Buy & hold" column buys as many whole shares as possible on the
first bar and holds them to the end. Its purchase follows the strategy's buy
rules, so the comparison is fair:

- it buys at the first bar's **fill price**: its open with `--fill open`, its
  close otherwise;
- it pays the same **`--slippage`** on that price, before the same fees;
- it is always **all-in**: `--position-size`, stops, targets, the trailing
  stop, risk sizing, the scale-out, the add-ons, the maximum holding time and
  the drawdown halt do not apply.

With close fills and no slippage it is the plain buy at the first close, as in
earlier versions. On `candles.csv` above (first open 9, first close 10, last
close 8, cash 10,000):

| Run | Buy & hold buys | End equity |
| --- | --- | --- |
| close fills | 1,000 @ 10.00 | 8,000.00 |
| `--fill open` | 1,111 @ 9.00 (1.00 cash left) | 8,889.00 |
| `--slippage 1` | 990 @ 10.10 (1.00 cash left) | 7,921.00 |

### JSON output (`--json`)

`--json` prints the same information as the text report as **one JSON object
on stdout and nothing else** (the disclaimer is a field of the object). The
text report and the JSON are built from the same analysis call, so they cannot
disagree. Numbers are plain JSON numbers, unrounded (the text report rounds
them for display); `null` stands where the text says `n/a`.

```
$ python -m trading_assistant candles.csv --short 2 --long 3 --json
{
  "bars": 10,
  "last_close": 8.0,
  "signal": "HOLD",
  "rsi": null,
  "rsi_label": null,
  "disclaimer": "Research aid only. Not financial advice."
}
```

With `--explain` it also has `explanation`, the `--explain` sentence, right
after `signal` (see [Signal explanation](#signal-explanation---explain)); it
stays a top-level key with `--backtest`.

With `--backtest` the object also has `backtest`:

| Key | Contents |
| --- | --- |
| `strategy`, `params` | the strategy traded and the parameters actually used |
| `fill`, `start_cash`, `fee`, `fee_pct`, `slippage_pct`, `position_size`, `stop_loss_pct`, `take_profit_pct` | the settings (`null` when not set) |
| `risk_pct` | only with `--risk-pct` (or the config key), right after `position_size`: the percentage; absent otherwise |
| `atr_mult`, `atr_period` | only with `--risk-pct` (or the config key) or `--atr-stop`, right after `risk_pct` (or `position_size` without it): the settings used, with the defaults filled in (`2.0`, `14`); absent otherwise |
| `trailing_stop_pct` | only with `--trailing-stop` (or the config key), right after `take_profit_pct`: the percentage, e.g. `10.0`; absent otherwise, so a run without it prints exactly the JSON it printed before the option existed |
| `atr_stop` | only with `--atr-stop`, right after `trailing_stop_pct` (or `take_profit_pct` without it): always `true`; absent otherwise, so a run without it prints exactly the JSON it printed before |
| `breakeven_pct` | only with `--breakeven`, right after `atr_stop` (or `trailing_stop_pct`, or `take_profit_pct`): the percentage, e.g. `5.0`; absent otherwise, so a run without it prints exactly the JSON it printed before |
| `scale_out_pct` | only with `--scale-out` (or the config key), right after `breakeven_pct` (or `atr_stop`, `trailing_stop_pct`, or `take_profit_pct`): the percentage, e.g. `5.0`; absent otherwise, so a run without it prints exactly the JSON it printed before |
| `add_on_pct`, `max_adds` | only with `--add-on` (or the config key), right after `scale_out_pct` (or `breakeven_pct`, `atr_stop`, `trailing_stop_pct`, or `take_profit_pct`): the percentage, e.g. `10.0`, and the most add-ons per position (`1` when `--max-adds` is not given); absent otherwise, so a run without it prints exactly the JSON it printed before |
| `cooldown_bars` | only with `--cooldown` (or the config key), right after the exit and add-on settings (`max_adds`, `scale_out_pct`, `breakeven_pct`, `atr_stop`, `trailing_stop_pct` or `take_profit_pct`, the last of those present): `N`; absent otherwise |
| `min_hold_bars` | only with `--min-hold` (or the config key), right before `max_hold_bars` (or where that key would be: after `cooldown_bars`, or the exit settings): `N`; absent otherwise |
| `max_hold_bars` | only with `--max-hold` (or the config key), right after `min_hold_bars` (or `cooldown_bars`, or the exit settings): `N`; absent otherwise |
| `max_drawdown_limit_pct` | only with `--max-drawdown` (or the config key), right after `max_hold_bars` (or `min_hold_bars`, `cooldown_bars`, or the exit settings): `PCT`; absent otherwise. Not to be confused with `max_drawdown_pct` below, the drawdown the run had |
| `max_losses` | only with `--max-losses` (or the config key), right after `max_drawdown_limit_pct` (or where that key would be): `N`; absent otherwise |
| `trades`, `buys`, `sells` | fill counts |
| `risk_skipped_buys` | only with `--risk-pct` or `--atr-stop`, right after `sells`: how many buys were skipped (no usable ATR on the signal bar, or with risk sizing under one share); a buy is counted once |
| `breakeven_exits` | only with `--breakeven`, right after `risk_skipped_buys` (or `sells`): how many sells the breakeven stop made (fills with reason `breakeven`); `0` when it never sold |
| `scale_out_exits` | only with `--scale-out` (or the config key), right after `breakeven_exits` (or `risk_skipped_buys`, or `sells`): how many partial sales the scale-out made (fills with reason `scale_out`; none of them is a round trip); `0` when it never sold |
| `add_on_buys`, `add_on_skipped_buys` | only with `--add-on` (or the config key), right after `scale_out_exits` (or `breakeven_exits`, `risk_skipped_buys`, or `sells`): how many add-on buys filled (fills with reason `add_on`) and how many add-ons got 0 shares (see [Add-ons](#add-ons)); an add-on dropped because another fill took its bar is in neither |
| `cooldown_skipped_buys` | only with `--cooldown` (or the config key), right after `sells` (or `add_on_skipped_buys`, `scale_out_exits`, `breakeven_exits`, or `risk_skipped_buys`): how many buys were dropped because they were due in a cooldown; such a buy is not also counted in `risk_skipped_buys` |
| `min_hold_skipped_sells` | only with `--min-hold` (or the config key), right before `time_exits` (or where that key would be): how many signal sells were dropped because the position had not been held `N` bars; a sell is counted only when it would otherwise have filled |
| `time_exits` | only with `--max-hold` (or the config key), right after `min_hold_skipped_sells` (or `cooldown_skipped_buys`, `add_on_skipped_buys`, `scale_out_exits`, `breakeven_exits`, `risk_skipped_buys`, or `sells`): how many sells the maximum holding time made (fills with reason `time`) |
| `drawdown_halt_bar`, `drawdown_skipped_buys` | only with `--max-drawdown` (or the config key), right after `time_exits` (or `min_hold_skipped_sells`, `cooldown_skipped_buys`, `add_on_skipped_buys`, `scale_out_exits`, `breakeven_exits`, `risk_skipped_buys` or `sells`): the bar whose close set off the halt (`null` when it never triggered) and how many buys the halt dropped; such a buy is counted in neither `cooldown_skipped_buys` nor `risk_skipped_buys` |
| `loss_halt_bar`, `loss_skipped_buys` | only with `--max-losses` (or the config key), right after `drawdown_skipped_buys` (or where that key would be), just before `fills`: the bar of the sale that completed the losing streak (`null` when it never did) and how many buys the halt dropped; such a buy is counted in neither `cooldown_skipped_buys` nor `risk_skipped_buys`, and a buy the drawdown halt also blocked is counted in `drawdown_skipped_buys` only |
| `fills` | one object per fill: `bar`, `side`, `shares`, `price`, `value`, `cost`, `cash_after`, `reason` (`signal`, `stop`, `target`, `trail`, `atr`, `breakeven`, `time`, `drawdown` or `scale_out`; `add_on` for an add-on buy) |
| `total_costs`, `round_trips`, `winning_round_trips` | costs and completed round trips (a `--scale-out` partial sale and an `--add-on` buy are part of their round trip, not ones of their own) |
| `final_cash`, `final_position`, `final_price`, `final_equity`, `return_pct`, `max_drawdown_pct` | the end of the run |
| `benchmark` | buy and hold: `shares`, `final_cash`, `final_equity`, `return_pct`, `max_drawdown_pct`, `trades`, `total_costs` |
| `stats` | only with `--stats`: the ten "Risk and return" numbers, `null` for `n/a` |
| `export` | only with `--export`: `path` and `rows` |
| `trade_list` | only with `--trade-list` (or `trade_list = yes`), the last key (after `stats` and `export`): one object per row of the trade list (`open`, `entry_bar`, `exit_bar`, `bars_held`, `shares`, `outlay`, `proceeds`, `pnl`, `return_pct`, `reason`; see [Trade list](#trade-list)); absent otherwise, so a run without it prints exactly the JSON it printed before |

For the stop example above, the second fill is (condensed here; the real
output is indented two spaces per level)

```
{"bar": 7, "side": "SELL", "shares": 769, "price": 9.0, "value": 6921.0,
 "cost": 0.0, "cash_after": 6924.0, "reason": "stop"}
```

and `final_equity` is `6924.0` with `benchmark.final_equity` `8889.0`.

For the trailing stop example the settings part is

```
    "stop_loss_pct": null,
    "take_profit_pct": null,
    "trailing_stop_pct": 10.0,
    "trades": 2,
```

and the sell has `"reason": "trail"`. Prices are unrounded, so its `price` is
`11.700000000000001` (13 x 0.9 in floating point) where the text shows 11.70.

For the risk sizing example the settings part is

```
    "slippage_pct": 0.0,
    "position_size": null,
    "risk_pct": 2.0,
    "atr_mult": 2.0,
    "atr_period": 3,
    "stop_loss_pct": null,
    "take_profit_pct": null,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "risk_skipped_buys": 0,
```

and the fills buy and sell 7 shares.

Errors are reported exactly as without `--json`: a message on stderr, nothing
on stdout, exit 1 or 2. `--json` together with `--chart` is a usage error.

### Config file (`--config FILE`)

An INI file read with `configparser`. Precedence, highest first:

1. flags written on the command line
2. the config file
3. built-in defaults

```ini
[cli]
short = 10
long = 30
rsi_period = 14
cash = 5000
fee = 1
fee_pct = 0.1
slippage = 0.05
position_size = 0.5
fill = open
stop_loss = 8
take_profit = 20
trailing_stop = 10
risk_pct = 1
atr_mult = 2
atr_period = 14
atr_stop = yes
cooldown = 3
min_hold = 2
max_hold = 10
max_drawdown = 20
breakeven = 5
max_losses = 3
scale_out = 5
add_on = 10
max_adds = 2
strategy = breakout
stats = yes
trade_list = yes
explain = yes

[strategy.breakout]
window = 15
```

- `[cli]` keys: `short`, `long`, `rsi_period` (whole numbers), `cash`, `fee`,
  `fee_pct`, `slippage`, `position_size`, `stop_loss`, `take_profit`,
  `trailing_stop`, `risk_pct`, `atr_mult` (numbers), `atr_period` (a whole
  number), `cooldown`, `min_hold` and `max_hold` (whole numbers), `max_drawdown` and
  `breakeven` (numbers), `max_losses` (a whole number), `scale_out` (a number), `add_on` (a number), `max_adds`
  (a whole number), `atr_stop`, `stats`, `trade_list` and `explain` (`yes`/`no`, `true`/`false`, `on`/`off`,
  `1`/`0`, any case), `fill` (`close` or `open`, lower case), `strategy` (a
  strategy name), `top` and
  `min_score` (whole numbers, for `--scan`). Each key is the flag's name with
  `_` for `-`; `position_size` is a fraction, like the flag (`0.5` is half the
  account).
- `[strategy.NAME]` sets parameters of that strategy; only the section of the
  strategy actually traded is used, and a `--param` flag for the same key wins.
- `cash`, `fee`, `fee_pct`, `slippage`, `position_size`, `fill`,
  `stop_loss`, `take_profit`, `trailing_stop`, `risk_pct`, `atr_mult`,
  `atr_period`, `atr_stop`, `cooldown`, `min_hold`, `max_hold`, `max_drawdown`, `breakeven`, `max_losses`, `scale_out`, `add_on`, `max_adds`, `strategy`, `stats`, `trade_list` and strategy parameters apply only with
  `--backtest`; without it they are ignored (even an out-of-range value).
- `top` and `min_score` apply only with `--scan`; in any other run they are
  ignored (even an out-of-range `top = 0` is not a usage error there). With
  `--scan`, `--top` and `--min-score` on the command line win over the file,
  `top = 0` is a usage error (exit 2) like `--top 0`, and `top = 1.5` or
  `min_score = high` is a config error naming the file and line (exit 1).
  There is no key for the scan folder or the `--report` file.
- `fill = open`, `stop_loss`, `take_profit` or `trailing_stop` read the price
  file as a candle file, exactly as the flags do (and cannot be combined with
  `--resample`). `trailing_stop` has the flag's range, above 0 and below 100:
  `trailing_stop = 0` is the usage error
  `--trailing-stop must be between 0 and 100 (both exclusive), got 0` (exit 2)
  and `trailing_stop = 10%` the config error
  `Error: settings.ini line 2: trailing_stop needs a number, got '10%'` (exit 1).
- `risk_pct` reads the price file as a candle file too, and the three risk
  keys have the flags' ranges: `risk_pct = 0` is the usage error
  `--risk-pct must be above 0 and at most 100, got 0` (exit 2) and
  `risk_pct = 2%` the config error
  `Error: settings.ini line 2: risk_pct needs a number, got '2%'` (exit 1).
  Each key is taken from the file only when its own flag is not given, so
  `atr_mult = 3` in the file with `--risk-pct 2 --atr-period 3` on the
  command line uses all three. `atr_mult` and `atr_period` in the file are
  used only when risk sizing or the ATR stop is on (`risk_pct` or
  `atr_stop = yes` in the file, or `--risk-pct` or `--atr-stop`); otherwise
  they are ignored without an error, even an out-of-range value. (The flags
  `--atr-mult` and `--atr-period` without `--risk-pct` or `--atr-stop` are a
  usage error.)
- `atr_stop = yes` turns the ATR stop on, like `--atr-stop`: it reads the
  price file as a candle file and cannot be combined with `--resample`. It is
  a switch like `stats`: `yes` turns it on and `no` leaves it as the command
  line has it, so `--atr-stop` wins over `atr_stop = no` (there is no flag
  to turn it off for one run; use a file without it). A value that is not a
  yes/no word is the config error
  `Error: settings.ini line 2: atr_stop needs yes or no, got 'maybe'` (exit 1),
  as for `stats`. `atr_mult = 1` in the file with `--atr-stop` on the command
  line uses both; `--atr-mult 3` with `atr_stop = yes` and `atr_mult = 1` in
  the file uses 3.
- `cooldown` is used only when a stop is on: `stop_loss`, `trailing_stop`,
  `atr_stop = yes` or `breakeven` in the file, or `--stop-loss`,
  `--trailing-stop`, `--atr-stop` or `--breakeven` on the command line
  (`take_profit` is not a stop). Without a
  stop it is ignored without an error, like `atr_mult` and `atr_period`, and
  the run prints exactly what it prints without the key. Unlike them, a value
  below 1 is still the usage error
  `--cooldown must be a whole number of at least 1, got 0` (exit 2), with or
  without a stop, and `cooldown = 1.5` is the config error
  `Error: settings.ini line 2: cooldown needs a whole number, got '1.5'`
  (exit 1). `--cooldown` on the command line wins over the file, and a stop
  from the file counts for the flag: `stop_loss = 10` in the file with
  `--cooldown 3` on the command line gives the cooldown. (The flag
  `--cooldown` without any stop is a usage error.)
- `max_hold` needs no stop and no candle file: with `--backtest` it is used
  whenever `--max-hold` is not on the command line, also with a close-only
  price file and with `--resample`. `max_hold = 0` is the usage error
  `--max-hold must be a whole number of at least 1, got 0` (exit 2) and
  `max_hold = 1.2` the config error
  `Error: settings.ini line 2: max_hold needs a whole number, got '1.2'`
  (exit 1). `--max-hold` on the command line wins, and then the file's value
  is not used at all (like `cooldown`), so `max_hold = 0` with
  `--max-hold 2` runs with 2. Without `--backtest`, and with `--scan`, it is
  ignored, even `0` (a value that is not a whole number is still the config
  error, as for every key).
- `min_hold` works like `max_hold`: it needs no stop and no candle file, and
  with `--backtest` it is used whenever `--min-hold` is not on the command
  line, also with a close-only price file and with `--resample`.
  `min_hold = 0` (or `-1`) is the usage error
  `--min-hold must be a whole number of at least 1, got 0` (exit 2) and
  `min_hold = 1.5` the config error
  `Error: settings.ini line 2: min_hold needs a whole number, got '1.5'`
  (exit 1). `--min-hold` on the command line wins, and then the file's value
  is not used at all: `min_hold = 3` with `--min-hold 4` runs with 4, and
  `min_hold = 0` with `--min-hold 4` runs with 4. `--min-hold 1` skips
  nothing, so it turns a file's `min_hold` off for one run (the report still
  shows a `Min hold:` line). Without `--backtest`, and with `--scan`, it is
  ignored, even `0` (a value that is not a whole number is still the config
  error).
- `max_drawdown` works like `max_hold`: it needs no stop and no candle file,
  and with `--backtest` it is used whenever `--max-drawdown` is not on the
  command line, also with a close-only price file and with `--resample`.
  `max_drawdown = 0` (or `100`) is the usage error
  `--max-drawdown must be above 0 and below 100, got 0` (exit 2), and a value
  that is not a finite number the config error, for example
  `Error: settings.ini line 2: max_drawdown needs a number, got '10%'` or
  `... needs a finite number, got 'nan'` (exit 1; see
  [Max drawdown values](#max-drawdown-values)). `--max-drawdown` on the
  command line wins, and then the file's value is not used at all:
  `max_drawdown = 0` with `--max-drawdown 16` runs with 16, and
  `max_drawdown = 16` with `--max-drawdown 17` runs with 17. Without
  `--backtest`, and with `--scan`, it is ignored, even `0` (a value that is
  not a number is still the config error).
- `breakeven` has the flag's rules: it reads the price file as a candle file
  and cannot be combined with `--resample` (exit 2). `breakeven = 0` (or a
  negative number) is the usage error `--breakeven must be above 0, got 0`
  (exit 2), and a value that is not a finite number is the config error, like
  every number key: `Error: settings.ini line 2: breakeven needs a number,
  got '5%'` or `... needs a finite number, got 'nan'` (or `'inf'`) (exit 1).
  Neither the file nor the flag takes `inf` (the flag: exit 2). It counts
  as a stop for `cooldown` (in the file or `--cooldown`). `--breakeven` on the command line wins, and then the file's
  value is not used at all: `breakeven = 5` with `--breakeven 9` runs with
  9, and `breakeven = 0` with `--breakeven 9` runs with 9. Without
  `--backtest`, and with `--scan`, it is ignored, even `0` (a value that is
  not a finite number is still the config error).
- `max_losses` works like `max_hold`: it needs no stop and no candle file,
  and with `--backtest` it is used whenever `--max-losses` is not on the
  command line, also with a close-only price file and with `--resample`.
  `max_losses = 0` (or `-1`) is the usage error
  `--max-losses must be a whole number of at least 1, got 0` (exit 2), and
  `max_losses = 2.5` (or `2.0`, `abc`, `true`) the config error
  `Error: settings.ini line 2: max_losses needs a whole number, got '2.5'`
  (exit 1; see [Max losses values](#max-losses-values)). `--max-losses` on
  the command line wins, and then the file's value is not used at all:
  `max_losses = 1` with `--max-losses 2` runs with 2, `max_losses = 2` with
  `--max-losses 1` runs with 1, and `max_losses = 0` with `--max-losses 2`
  runs with 2. Without `--backtest`, and with `--scan`, it is ignored, even
  `0` (a value that is not a whole number is still the config error). From
  a file it gives exactly the text and `--json` of the flag.
- `scale_out` has the flag's rules: it reads the price file as a candle file
  and cannot be combined with `--resample` (exit 2); it needs no other exit
  key. `scale_out = 0` (or a negative number) is the usage error
  `--scale-out must be above 0, got 0` (exit 2), and a value that is not a
  finite number is the config error, like every number key:
  `Error: settings.ini line 2: scale_out needs a number, got '5%'` or
  `... needs a finite number, got 'nan'` (or `'inf'`) (exit 1; see
  [Scale out values](#scale-out-values)). It is not a stop, so a `cooldown`
  in the file is not used with it alone. `--scale-out` on the command line
  wins, and then the file's value is not used at all: `scale_out = 5` with
  `--scale-out 9` runs with 9, and `scale_out = 0` with `--scale-out 9` runs
  with 9. Without `--backtest`, and with `--scan`, it is ignored, even `0` (a
  value that is not a finite number is still the config error). From a file
  it gives exactly the text and `--json` of the flag.
- `add_on` works like `scale_out`, but needs no candle file (a close-only
  price file and `--resample` work): with `--backtest` it is used whenever
  `--add-on` is not on the command line. `add_on = 0` (or a negative number)
  is the usage error `--add-on must be above 0, got 0` (exit 2), and a value
  that is not a finite number the config error
  `Error: settings.ini line 2: add_on needs a number, got '5%'` or
  `... needs a finite number, got 'nan'` (or `'inf'`) (exit 1; see
  [Add-on values](#add-on-values)). `--add-on` on the command line wins, and
  then the file's value is not used at all: `add_on = 10` with `--add-on 20`
  runs with 20.
- `max_adds` works like `max_hold` (used unless `--max-adds` is on the
  command line; `max_adds = 0` is the usage error
  `--max-adds must be a whole number of at least 1, got 0`, exit 2;
  `max_adds = 2.5` or `abc` the config error
  `Error: settings.ini line 3: max_adds needs a whole number, got '2.5'`,
  exit 1), but it is used only when `add_on` is in the file or `--add-on` on
  the command line. Without either it is ignored quietly, like a `cooldown`
  without a stop, and like `cooldown` its range is still checked then
  (`max_adds = 0` alone is still exit 2). `max_adds = 3` with `--max-adds 1`
  runs with 1; `max_adds = 3` in the file with `--add-on 10` on the command
  line uses both. The file's `max_adds` does not make a `--max-adds` flag
  valid without an add-on (that is still exit 2). Without `--backtest`, and
  with `--scan`, both keys are ignored, even `0` (a value of the wrong kind is
  still the config error). From a file they give exactly the text and
  `--json` of the flags.
- `trade_list` is a switch like `stats`: `yes` (or `true`, `on`, `1`, any
  case) turns the trade list on, and `no` (`false`, `off`, `0`) leaves it as
  the command line has it. So `--trade-list` wins over `trade_list = no`:
  with both, the trade list is printed; without the flag, `no` is the same as
  no key. A value that is not a yes/no word (or an empty value) is the config
  error `Error: settings.ini line 2: trade_list needs yes or no, got 'maybe'`
  (exit 1), as for `stats`; the file is checked when it is read, so this is
  an error even without `--backtest` or with `--scan`, where a valid value is
  ignored. It needs no candle file. From a file it gives exactly the text and
  `--json` of the flag.
- `explain` is a switch like `stats` and `trade_list` (the same words), but
  it needs no `--backtest`: `yes` turns the `--explain` sentence on in any
  single-file run, and `no` leaves it as the command line has it, so
  `--explain` wins over `explain = no` (with both, the sentence is printed;
  without the flag, `no` is the same as no key). With `--scan` it is
  ignored, even `yes`, unlike the flag, which is a usage error there. A word
  that is not yes/no is the config error
  `Error: settings.ini line 2: explain needs yes or no, got 'maybe'` (exit 1),
  also with `--scan`, because the file is checked when it is read. It needs
  no candle file. From a file it gives exactly the text and `--json` of the
  flag.
- A stop, target, trailing stop, ATR stop, breakeven stop, scale-out, `add_on` or `max_drawdown` set in the file cannot be switched off by a
  flag for one run (`--stop-loss 0` is out of range); use a file without it.
  A flag with another value wins (`--trailing-stop 30` over
  `trailing_stop = 10`). The other keys
  can be overridden with their neutral values (`--slippage 0`,
  `--position-size 1`, `--fill close`).
- No file is read unless you ask. `--config` names it. Otherwise, if the
  environment variable `TRADING_ASSISTANT_CONFIG` is set, its value is the path
  of the file (for example `TRADING_ASSISTANT_CONFIG=trading_assistant.ini`
  picks up that file in the current directory). `--config` wins over the
  variable. A variable naming a file that does not exist is an error.
- Values from the file are checked exactly like flags. `short = 30` with
  `long = 10` is a usage error (exit 2), just as `--short 30 --long 10` is,
  and `slippage = 100` gives the same message as `--slippage 100`.
- An unreadable file, a section or key that is not listed, a duplicate, or a
  value of the wrong kind (`short = ten`, `fill = midday`, `stop_loss = nan`)
  is a data problem (exit 1) with the file and, where it can be found, the
  line: `Error: settings.ini line 2: ...`.

### Exit codes

| Code | Cases |
| --- | --- |
| 0 | success |
| 1 | file missing or unreadable; no `close` column; a close that is not a number; no rows; non-positive price in `--backtest`; a candle file that fails a check with `--candles`, `--fill open`, `--stop-loss`, `--take-profit`, `--trailing-stop`, `--risk-pct`, `--atr-stop`, `--breakeven` or `--scale-out` (for example no `open` column); `--export` not writable or the same file as the input; `--resample` without a usable ascending `date` column; a config file that cannot be read or is not valid (see above); with `--scan`, the folder problems and `--report` problems listed in [its exit codes](#scan-exit-codes) |
| 2 | unparseable arguments; `--resample` not weekly/monthly; `--candles`, `--fill open`, `--stop-loss`, `--take-profit`, `--trailing-stop`, `--risk-pct`, `--atr-stop`, `--breakeven` or `--scale-out` with `--resample`; a window below 1; `--short` not below `--long`; `--cash` not above 0; negative `--fee`; `--fee-pct` or `--slippage` outside [0, 100); `--position-size` not above 0 or above 1; `--stop-loss` or `--trailing-stop` outside (0, 100); `--take-profit`, `--breakeven`, `--scale-out` or `--add-on` not above 0; `--breakeven inf`, `--scale-out inf` or `--add-on inf`; `--max-adds` not a whole number of at least 1, or without `--add-on`; `--risk-pct` not above 0 or above 100; `--atr-mult` not above 0; `--atr-period` not a whole number of at least 1; `--atr-mult` or `--atr-period` without `--risk-pct` or `--atr-stop`; `--cooldown` not a whole number of at least 1, or without `--stop-loss`, `--trailing-stop`, `--atr-stop` or `--breakeven`; `--min-hold`, `--max-hold` or `--max-losses` not a whole number of at least 1; `--max-drawdown` not a number above 0 and below 100; a backtest-only flag without `--backtest`; unknown `--strategy`; bad, unknown, duplicate or contradicting `--param`; `--json` with `--chart`; `--explain` with `--scan`; `--min-score`, `--top` or `--report` without `--scan`; the `--scan` mistakes listed in [its exit codes](#scan-exit-codes); any of these rules broken by a value from the config file |

With `--json` the same codes apply and the messages are the same; stdout stays
empty on an error.

## `python -m trading_assistant --scan FOLDER [options]`

Gives every `.csv` file **directly inside** `FOLDER` a combined score and
prints them as one table, best first. Subfolders and other kinds of files are
ignored; `AAPL.csv` and `AAPL.CSV` both count. The file name without `.csv` is
the symbol. Each file is read exactly like a single price file (a `close`
column; a `date` column is not needed).

**The combined score** (`signals.combined_score`) is the sum of four parts on
the last bar, each +1, 0 or -1, so it is a whole number from -4 to 4:

| Part | +1 | -1 | 0 |
| --- | --- | --- | --- |
| Crossover | the `--short`-bar SMA is above the `--long`-bar SMA | it is below | they are equal |
| RSI | the `--rsi-period` RSI is under 30 | it is over 70 | 30 to 70 |
| MACD | the MACD histogram (12 / 26 / 9, fixed) is above 0 | it is below 0 | it is exactly 0 |
| Bollinger | the last close is below the lower band (20 bars, 2 deviations, fixed) | it is above the upper band | inside or on the bands |

A part whose indicator has no value on the last bar yet (not enough bars)
counts 0, so a short file is scored, not skipped; the Bars column shows why.
MACD and Bollinger always use their defaults.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--scan FOLDER` | none | the folder to scan; cannot be combined with a price file |
| `--short N`, `--long N`, `--rsi-period N` | 20, 50, 14 | the crossover windows and the RSI period, checked as for one file |
| `--min-score N` | none | keep only the rows scoring `N` or more (a whole number; negative is fine) |
| `--top N` | all | then keep the first `N` rows, in the same order; at least 1 |
| `--json` | off | print one JSON object instead of the table, and nothing else (see below) |
| `--report FILE` | none | also write a Markdown report to `FILE` (see below); the screen output does not change |
| `--config FILE` | none | `short`, `long`, `rsi_period`, `top` and `min_score` may come from the file; flags win |

`--backtest` and every backtest option, `--chart`, `--candles`,
`--resample` and `--explain` cannot be combined with `--scan` (usage error,
exit 2); a config `explain = yes` is ignored there.
`--min-score`, `--top` and `--report` need `--scan`.

```
$ python -m trading_assistant --scan prices
Scan:    prices, 5 scored, 1 skipped
Symbol  Bars  Score  Crossover  RSI  MACD  Bollinger
UP        60     +2         -1   +1    +1         +1
LOW       60     +1         +1   +1    -1          0
Alpha     60      0         -1   +1    -1         +1
zeta      60      0         +1   -1    +1         -1
DOWN      60     -2         +1   -1    -1         -1
Skipped: 1
  bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)
Research aid only. Not financial advice.
```

Rows are sorted by score, highest first; equal scores are in name order,
ignoring capitals (`Alpha`, `zeta`). A file that cannot be read, has no
`close` column, holds a value that is not a number or has no rows does not
stop the scan: it is listed under `Skipped:` with its one-line reason, in the
order the files are listed in the folder (by name, capitals first). The
disclaimer is always the last line.

With `--min-score` or `--top` the top line also counts the files found, the
rows left by `--min-score` and the rows shown. The skipped list is always
complete. If nothing is left, the table header is followed by
`  (no file matched: no score at or above N)` and the exit code is 0.

```
$ python -m trading_assistant --scan prices --min-score 0 --top 3
Scan:    prices, 6 found, 5 scored, 1 skipped, 4 with score >= 0, 3 shown (top 3)
Symbol  Bars  Score  Crossover  RSI  MACD  Bollinger
UP        60     +2         -1   +1    +1         +1
LOW       60     +1         +1   +1    -1          0
Alpha     60      0         -1   +1    -1         +1
Skipped: 1
  bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)
Research aid only. Not financial advice.
```

Two things to know when reading scores: a completely flat series scores RSI
-1, because the RSI is 100 when there are no losses at all; and a perfectly
straight line can score MACD -1 instead of 0, because rounding leaves its
histogram a hair below 0 (about -2e-15).

### Scan JSON (`--scan FOLDER --json`)

One object on stdout and nothing else (no table, no disclaimer line).
`--min-score` and `--top` work exactly as for the table.

| Key | Contents |
| --- | --- |
| `found` | `.csv` files found (scored + skipped) |
| `scored` | files that were scored |
| `shown` | rows in `results` (after `--min-score` and `--top`) |
| `results` | the shown rows in table order: `symbol`, `bars`, `score` and `parts` (`crossover`, `rsi`, `macd`, `bollinger`) |
| `skipped` | every skipped file: `symbol` (file name without `.csv`) and `reason` (the table's one-line reason) |

```
$ python -m trading_assistant --scan prices --top 1 --json
{
  "found": 6,
  "scored": 5,
  "shown": 1,
  "results": [
    {
      "symbol": "UP",
      "bars": 60,
      "score": 2,
      "parts": {
        "crossover": -1,
        "rsi": 1,
        "macd": 1,
        "bollinger": 1
      }
    }
  ],
  "skipped": [
    {
      "symbol": "bad",
      "reason": "bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)"
    }
  ]
}
```

When nothing matched, `results` is `[]` and the exit code is 0. Errors are
the same as for the table: a message on stderr, nothing on stdout.

### Scan report (`--report FILE`)

Writes a Markdown report to `FILE` after the normal output, which stays
exactly the same (with `--json` the screen still gets only the JSON). An
existing file is replaced. The report has:

- a title with the folder, and today's date;
- the settings: folder, crossover windows, RSI period, MACD and Bollinger
  settings, minimum score, top, and the found / scored / skipped / shown counts;
- a table of the shown rows, in screen order, with the score and the four parts;
- one sentence per row saying why it scored what it did, built only from its
  four parts, for example "UP scored +2: the 20-bar average is below the
  50-bar average (crossover -1), the 14-bar RSI is under 30 (RSI +1), the MACD
  histogram is above 0 (MACD +1) and the last close is below the lower
  Bollinger band (Bollinger +1)." A 0 part cannot tell "level" from "not
  enough history", so its sentence names both;
- `No file matched: ...` instead of the sentences when nothing is left;
- the skipped files with their reasons (or `None.`);
- the disclaimer line.

Names and reasons are escaped for Markdown (`my_co` is written `my\_co`) so
they show as written.

### Scan exit codes

| Code | Cases |
| --- | --- |
| 0 | the table (or JSON) was printed and any `--report` written, including when nothing matched |
| 1 | the folder does not exist, is not a folder or cannot be read; it holds no `.csv` file; not one file could be scored; the `--report` file is a folder, is in a folder that does not exist, or is one of the scanned `.csv` files (checked before anything is printed); writing the report failed (the normal output was already printed); a config file problem |
| 2 | `--scan` with a price file, `--backtest` or a backtest option, `--chart`, `--candles`, `--resample` or `--explain`; no folder name; a bad window; `--top` below 1 or not a whole number; `--min-score` not a whole number; an empty `--report` name; `--min-score`, `--top` or `--report` without `--scan`; the same rules broken by a config value |

## `python -m trading_assistant.samples [NAME] [OUTPUT]`

Writes a built-in seeded sample series as `date,close` CSV, identical on every
run. `NAME` is one of `uptrend`, `downtrend`, `sideways`, `random_walk`.
`OUTPUT` defaults to standard output.

| Option | Meaning |
| --- | --- |
| `--list` | list the samples with their bar counts |
| `--candles` | write a candle file (`date,open,high,low,close,volume`) instead; the closes and dates are exactly those of the close-only file, and the open, high, low and volume are derived from them with the same seeded randomness, so the file is identical on every run |

Exit codes: 0 success; 1 unknown sample name or output not writable; 2 no name
given (without `--list`) or unparseable arguments.

## `python -m trading_assistant.sweep PRICES.csv --short LIST --long LIST`

Backtests the SMA crossover for every `(short, long)` pair with `short < long`,
sorted by return, and compares with buy and hold. Best in-sample results
overfit; check them on data they were not chosen on.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--short LIST` | required | comma list of short windows, e.g. `5,10,20` |
| `--long LIST` | required | comma list of long windows, e.g. `20,50,100` |
| `--cash AMOUNT` | 10000 | starting cash |
| `--fee AMOUNT` | 0 | fixed cost per trade |
| `--fee-pct PCT` | 0 | percent of traded value per trade |
| `--top N` | all | show only the best `N` rows |
| `--csv OUT` | none | write every row to `OUT` |

Exit codes: 0 success; 1 data problem (as above, plus `--csv` not writable or
the same file as the input); 2 a bad window list, no pair with `short < long`,
bad cash or costs, `--top` below 1, empty `--csv` name.

## `python -m trading_assistant.walkforward PRICES.csv [options]`

Walk-forward test of the SMA crossover, or of another strategy with
`--strategy` (see
[Strategies in the walk-forward](#strategies-in-the-walk-forward---strategy---grid---param);
everything below also holds for it, with "parameter set" for "pair"). The bars are split into rolling
windows of `--train` bars followed by `--test` bars; window 1 starts at bar 0
and each next window starts `--step` bars later. Only full windows count. In
each window the sweep's best pair (highest return; ties by smaller drawdown,
then smaller short, then smaller long) is picked on the train bars only and
backtested on the test bars only, with the same cash and costs; buy and hold
is run on the same test bars. Every price in the file is checked first, so a
bad price is reported with its bar number in the file.

Without `--warmup` each test backtest starts cold: its moving averages warm up
inside the test block, so a block shorter than `long + 2` bars cannot trade.
`--warmup` warms them up on the bars just before the block instead; see
[`--warmup`](#--warmup) below.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--short LIST` | required without `--strategy` | comma list of short windows, e.g. `5,10`; refused with `--strategy`, `--grid` or `--param` |
| `--long LIST` | required without `--strategy` | comma list of long windows, e.g. `20,40`; refused as `--short` |
| `--train N` | required | bars in each train block |
| `--test N` | required | bars in each test block |
| `--step N` | `--test` | bars each window moves on |
| `--cash AMOUNT` | 10000 | starting cash of each train and test run |
| `--fee AMOUNT` | 0 | fixed cost per trade |
| `--fee-pct PCT` | 0 | percent of traded value per trade |
| `--warmup` | off | warm the moving averages up on the `long` bars before each test block (a switch, takes no value) |
| `--json` | off | print one JSON object instead of the text |
| `--csv OUT` | none | also write one row per window to `OUT` |
| `--strategy NAME` | none (SMA pairs) | walk forward this strategy instead of SMA crossover pairs |
| `--grid KEY=LIST` | none | values of one `--strategy` parameter to try, e.g. `window=10,20,30`; repeatable, every combination is tried |
| `--param KEY=VALUE` | none | one fixed value for a `--strategy` parameter, e.g. `threshold=0.5`; repeatable; a list is refused |

The text has one row per window (bar ranges with both ends included), then the
compounded test and buy-and-hold returns, the mean test return, the windows
beating buy and hold (a tie does not count) and the windows without test
trades, then up to two notes (test blocks not contiguous; windows without
trades), the overfit line and the disclaimer. With `--csv` the line
`Wrote 4 rows to windows.csv` comes before the overfit line. `--warmup`
changes the header line and the no-trades note's wording (see below).

`--json` prints only `{"windows": [...], "summary": {...}, "overfit_warning": "...", "disclaimer": "..."}`
(with `--warmup`, `"warmup": true` comes first; see below).
Each window has `window` (from 1), `train_start`, `train_end`, `test_start`,
`test_end` (ends excluded, like Python slices), `short`, `long`,
`train_return_pct`, `test_return_pct`, `test_max_drawdown_pct`, `test_trades`
and `buy_hold_return_pct`. The summary has `windows`,
`compound_test_return_pct`, `compound_buy_hold_return_pct`,
`windows_beating_buy_hold`, `mean_test_return_pct`, `windows_without_trades`
and `test_blocks_contiguous` (true when each test block starts where the one
before it ended; the compounded figures only make sense then). Numbers are
unrounded. The `--csv` file has the window keys as columns, in that order,
percentages to 4 decimals, for example
`1,0,250,250,370,10,40,-12.7890,2.3664,-13.4553,2,-6.6557`.

Exit codes: 0 success; 1 data problem (file missing or unreadable, no `close`
column, bad number, no rows, a price of 0 or below, too few bars for one
window, `--csv` not writable or the same file as the input; nothing is printed
on stdout); 2 a bad window list, no pair with `short < long`, `--train`,
`--test` or `--step` below 1, bad cash or costs, empty `--csv` name, a value
after `--warmup` (`--warmup 5`, `--warmup=5`). For example:

```
Error: not enough prices for a walk-forward window: 750 bars, need at least train + test = 820
Error: --csv refuses to overwrite the input file prices.csv
trading_assistant.walkforward: error: --test must be at least 1
```

### `--warmup`

A switch, off by default; it takes no value (`--warmup 5` and `--warmup=5`
are usage errors, exit 2). Like every option it can be shortened to any
unique prefix, so `--w` to `--warmu` mean `--warmup` too. With it:

- **The pair is still chosen on the train bars only**, by the same sweep, so
  every window gets the same pair and the same train return as without it.
  Only the test columns can change.
- **The test run is warmed up on the chosen pair's `long` bars just before
  the test block**, `test_start - long` to `test_start - 1`. Each window uses
  its own chosen `long`: with `--short 1,2 --long 3,4,5 --train 9 --test 3`
  the three windows choose 1/3, 1/5 and 1/3 and are warmed up on 3, 5 and 3
  bars. When `long` is at most `--train` these are the last `long` bars of the
  train block; a larger chosen `long` reaches back before the train block.
  Either way they are bars before the test block, never after it.
- **Those bars only feed the moving averages.** The test run still starts
  flat, with fresh cash, on the first test bar; signals are only worked out on
  test bars, so a crossover on the last bar before the block is not acted on,
  and a crossover on the first test bar fills on the second (as always, a
  signal fills on the next bar). The first fill can therefore come on the
  second test bar, and a 1-bar test block still never trades.
- **Every figure is measured on the test block alone**: test return, drawdown,
  trades, and buy and hold (which does not change at all).
- **Near the start of the data** a test block can start before bar `long`
  (only when `--train` is smaller than the chosen `long`). Then whatever bars
  there are, back to bar 0, are used, and that window is only partly warmed
  up: with `--short 1 --long 5 --train 3 --test 7` window 1 starts at bar 3 and
  gets bars 0-2 (3 of 5), window 2 gets its full 5.
- **Without it every output is exactly as before**: text, `--json`, `--csv`
  and the web reply. The exceptions are `--help`, which lists and describes
  `--warmup`, and the usage line that every usage error (exit 2) prints: it
  now lists `[--warmup]`, so its options wrap differently; the error messages
  themselves do not change.

The text changes in two places. The header line ends `then traded and scored
on the test bars after them, with its moving averages warmed up on up to long
bars just before each test block` instead of `then run on the test bars after
them`, and the no-trades note gives `no BUY crossover on a test bar before its
last, or, near the start of the data, fewer than long bars before the block to
warm up` as the reasons instead of `no crossover, or fewer than long + 2 test
bars to warm up`.

Example on `tests/data/wf.csv`, 18 closes (bars 0-17: 10, 11, 12, 11, 10, 9,
10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 14):

```bash
python -m trading_assistant.walkforward tests/data/wf.csv --short 1 --long 3 --train 12 --test 6 --cash 1000
```

```
Walk-forward: 1 window; each SMA crossover pair was chosen on its train bars only, then run on the test bars after them
Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades
     1        0-11       12-17     1/3    +0.00%    +0.00%   +40.00%      0
Test return, compounded over the windows: +0.00%
Buy & hold, compounded over the windows:  +40.00%
Mean test return per window: +0.00%
Windows beating buy & hold: 0 of 1
Windows without test trades: 1 of 1
Note: 1 of 1 windows made no trades in the test block (no crossover, or fewer than long + 2 test bars to warm up); their 0.00% says nothing about the pair.
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

```bash
python -m trading_assistant.walkforward tests/data/wf.csv --short 1 --long 3 --train 12 --test 6 --cash 1000 --warmup
```

```
Walk-forward: 1 window; each SMA crossover pair was chosen on its train bars only, then traded and scored on the test bars after them, with its moving averages warmed up on up to long bars just before each test block
Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades
     1        0-11       12-17     1/3    +0.00%    +7.60%   +40.00%      1
Test return, compounded over the windows: +7.60%
Buy & hold, compounded over the windows:  +40.00%
Mean test return per window: +7.60%
Windows beating buy & hold: 0 of 1
Windows without test trades: 0 of 1
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

Worked by hand: 1/3 is chosen on bars 0-11 either way (it buys at 11 on bar 7
and sells at 11 on bar 11: +0.00%). Cold, the first signal needs 4 test bars,
so it can only come on bar 15, and bars 15-17 have no buy crossover. Warmed up
on bars 9-11 (13, 12, 11), bar 13 closes at 11 above its 3-bar average 10.67
after bar 12 closed at 10 below 11: a buy signal, filled on bar 14 at 13, 76
shares for 988.00, 12.00 cash left. The account is worth 1,000.00 on bars
12-14, 1,076.00, 1,152.00 and 1,076.00 on bars 15-17: +7.60%, a drawdown of
-6.60% (not in the text; it is in `--json` and `--csv`). Bar 17's sell signal
is the last bar, so the 76 shares are still held, marked at the last close.

Small runs on the same file, all with `--cash 1000`; each cell is the trades
and test return of every window, in order (the pairs are the same both ways):

| Settings | Windows, pair | Without `--warmup` | With `--warmup` | Shows |
| --- | --- | --- | --- | --- |
| `--short 1 --long 3 --train 12 --test 6` | 1, 1/3 | 0 (+0.00%) | 1 (+7.60%) | the example above |
| `--short 1 --long 3 --train 12 --test 4` | 1, 1/3 | 0 (+0.00%) | 1 (+7.60%) | a 4-bar block, shorter than `long + 2`, trades once warmed up (drawdown 0.00%: the 1,152.00 peak is on bar 16, after the block) |
| `--short 1 --long 3 --train 12 --test 1` | 6, 1/3 | 0 in all 6 | 0 in all 6 | a 1-bar block never trades: a signal on its only bar has no bar to fill on |
| `--short 1 --long 3 --train 3 --test 2` | 7, 1/3 | 0 in all 7 | 1 (+0.00%) in window 6 (bars 13-14), 0 in the others | a 2-bar block can trade: signal on its first bar, fill on its second |
| `--short 2 --long 3 --train 6 --test 6 --fee 1` | 2, 2/3 | 0 (+0.00%) / 0 (+0.00%) | 1 (-8.40%) / 1 (-0.10%) | fees; both positions are still held at the end of their block |
| `--short 2 --long 3 --train 7 --test 4` | 2, 2/3 | 0 (+0.00%) / 0 (+0.00%) | 1 (+0.00%) / 0 (+0.00%) | the warm-up note: window 2's only buy crossover is on bar 14, its last bar |
| `--short 1 --long 5 --train 3 --test 7` | 2, 1/5 | 0 (+0.00%) / 0 (+0.00%) | 1 (+8.30%) / 1 (+7.10%) | window 1 is only partly warmed up (bars 0-2, 3 of 5); its buy signal on bar 7 needs bar 2 |

**`--json` with `--warmup`** gets one more key, `"warmup": true`, and it comes
first, before `windows`, because it says how every number after it was made
(as the text's header line does). It is only there with `--warmup`; there is
never a `"warmup": false`, and without the switch the object is byte for byte
the old one. The other keys, their order and the window and summary fields do
not change; the numbers are the warmed-up ones and match the text (rounded
there to 2 decimals). For the example above:

```
{
  "warmup": true,
  "windows": [
    {
      "window": 1,
      "train_start": 0,
      "train_end": 12,
      "test_start": 12,
      "test_end": 18,
      "short": 1,
      "long": 3,
      "train_return_pct": 0.0,
      "test_return_pct": 7.6,
      "test_max_drawdown_pct": -6.597222222222222,
      "test_trades": 1,
      "buy_hold_return_pct": 40.0
    }
  ],
  "summary": {
    "windows": 1,
    "compound_test_return_pct": 7.600000000000007,
    "compound_buy_hold_return_pct": 39.99999999999999,
    "windows_beating_buy_hold": 0,
    "mean_test_return_pct": 7.6,
    "windows_without_trades": 0,
    "test_blocks_contiguous": true
  },
  "overfit_warning": "Best in-sample parameters overfit; check them on data they were not chosen on.",
  "disclaimer": "Research aid only. Not financial advice."
}
```

**`--csv` cannot show that warm-up was on.** Its columns and its one row per
window are the same with or without `--warmup`; only the numbers differ, so
nothing in the file tells the two apart. Keep the command that wrote it (or
its text or `--json` output) with the file. For the example above:

```
window,train_start,train_end,test_start,test_end,short,long,train_return_pct,test_return_pct,test_max_drawdown_pct,test_trades,buy_hold_return_pct
without: 1,0,12,12,18,1,3,0.0000,0.0000,0.0000,0,40.0000
with:    1,0,12,12,18,1,3,0.0000,7.6000,-6.5972,1,40.0000
```

**Web.** The page's "Walk-forward test" panel has the same settings, with a
"Warm up" box (last, after the costs) for `--warmup`, and shows the same
table, summary, notes, overfit line and disclaimer. A ticked box sends
`"warmup": true`; an unticked one sends exactly the request it sent before the
box existed. When the reply has `"warmup": true` the panel shows the
command's `--warmup` header line above the windows (a line it does not show
otherwise) and uses the warm-up wording in the no-trades note; any other reply
leaves both as before. The panel's introduction text is fixed: its "The
numbers are exactly those of `python -m trading_assistant.walkforward --json`"
means `--json --warmup` when the box is ticked.
`POST /api/walkforward` takes `sample` or `csv` (+ `source`) as
`/api/backtest` does (closes only), `short` and `long` (`"5,10"` or `[5, 10]`),
`train`, `test` and optional `step`, `cash`, `fee`, `fee_pct` and `warmup`, checked with the
command line's rules and messages; a missing one of the first four is
`the following arguments are required: --train`. The reply (status 200) is
**exactly the `--json` object** for the same prices and settings, with no `ok`
key (with `"warmup": true`, that of `--warmup --json`, `"warmup": true` first); errors are `{"ok": false, "error": "..."}`, for example 400
`not enough prices for a walk-forward window: 750 bars, need at least train + test = 820`
and 405 `use POST for /api/walkforward`. Besides the backtest's limits, one
request may ask for at most 300,000 bar-steps, counted as
windows x (pairs x train + test), so that a run cannot outlast the time limit:

```
{"ok": false, "error": "this walk-forward is too big for the web page (481 windows x 54 pairs, 6,503,120 bar-steps; the limit is 300,000); use fewer pairs, a larger step or shorter blocks, or run python -m trading_assistant.walkforward"}
```

`warmup` is read exactly like `/api/backtest`'s `atr_stop` and `trade_list`:

| `warmup` in the request | Result |
| --- | --- |
| `true` | on: the `--warmup --json` object, `"warmup": true` first |
| `false`, `null`, `""` or no key | off: exactly the old reply, byte for byte |
| a string (`"true"` and `"yes"` too) | 400 `warmup must be true or false, got 'yes'` |
| a number (`1` and `0` too) | 400 `warmup must be true or false, got 1` |
| a list or an object | 400 `warmup must be true or false` |

A bad `warmup` is reported after a `short`, `long`, `train`, `test`, `step`,
`cash`, `fee` or `fee_pct` that cannot be read at all (for example `train:
"x"` or `short: "0"`), but before the range and pairing rules (for example
`train: 0`, `cash: -1` or no pair with `short < long`) and before anything
about the prices (`source`, `sample`, `csv`). The
bar-step limit does not change with it: the warm-up bars only feed the signal.

### Strategies in the walk-forward (`--strategy`, `--grid`, `--param`)

`--strategy NAME` walks forward one of the seven strategies of
[`--backtest --strategy`](#backtest-options) (their rules are in
[indicators.md](indicators.md#strategies)) instead of SMA crossover pairs. In
each window every **parameter set** is backtested on the train bars only and
the best one is run on the test bars only, exactly as the pairs are:

- `--grid KEY=LIST` (repeatable, once per parameter) lists the values of one
  parameter to try, as a comma list of numbers (`window=10,20,30`). Every
  combination of the lists is tried.
- `--param KEY=VALUE` (repeatable) fixes one parameter to one number
  (`threshold=0.5`). A list is refused: `--param window takes one value, got
  '2,3'; give a list of values with --grid window=2,3`.
- A parameter in neither keeps its default (the defaults are in the
  [backtest's strategy table](#backtest-options)); `--strategy` alone tries
  the defaults only.

**The parameter sets.** Each list is tried once per distinct value, smallest
first, so the order and repeats of the values do not matter. Values that
compare equal are one value: `0,0.0` is tried once, as `0`, and `0.0,-0.0`
once, as `0.0`. The sets are every pick of one value per parameter, in the
strategy's own parameter order (for `zscore_reversion`: `window`, `entry`,
`exit`), whatever order the options came in. Every value is first checked on
its own (a window, period, short or long is a whole number of at least 1, a
z-score window at least 2, `oversold` and `overbought` are from 0 to 100, the
others are finite numbers), and **one bad value in a list is a usage error**.
A set that only breaks a rule between two parameters (`short < long`,
`oversold < overbought`, `entry < exit`) is skipped, as the pairs with
`short >= long` are; if none is left, that is a usage error.

**The chosen set** has the highest train return; on a tie, the smaller train
drawdown, then the smaller parameter values in the strategy's parameter order
(for `sma_cross`: the smaller short, then the smaller long, the pairs' own
order). Nothing from the test block counts.

**`--warmup`** warms each test run up on the `first_signal_bars - 1` bars just
before its block, the fewest with which the chosen set can signal on the first
test bar: `long` for `sma_cross` and `ema_cross`, `window` for `breakout` and
`zscore_reversion`, `period + 1` for `rsi_reversion`, `window + 1` for
`momentum` and `window + isqrt(window)` for `hull_trend` (fewer near the start
of the data, back to bar 0). Everything else is as in [`--warmup`](#--warmup).

**`--short` and `--long`** cannot be combined with any of the three options,
whatever the strategy; `sma_cross`'s windows are then given with `--grid`
(`--strategy sma_cross --grid short=2,3,5 --grid long=5,10,20` gives the same
windows and numbers as `--short 2,3,5 --long 5,10,20`, in the new output
shape). With `--strategy` they are not required; `--train` and `--test` still
are.

Example on `tests/data/wf20.csv`, 20 closes dated 2026-05-01 to 2026-05-20
(bars 0-19: 10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 13, 12, 11, 13, 16,
17, 15, 14, 16):

```bash
python -m trading_assistant.walkforward tests/data/wf20.csv --strategy breakout --grid window=2,3 --train 8 --test 6 --cash 1000
```

```
Walk-forward: 2 windows; each breakout parameter set was chosen on its train bars only, then run on the test bars after them
Window  Train bars   Test bars   Params     Train      Test  Buy&Hold Trades
     1         0-7        8-13 window=3   -16.60%    +0.00%   -15.20%      0
     2        6-13       14-19 window=2   -14.20%    -6.60%   +22.80%      2
Test return, compounded over the windows: -6.60%
Buy & hold, compounded over the windows:  +4.13%
Mean test return per window: -3.30%
Windows beating buy & hold: 1 of 2
Windows without test trades: 1 of 2
Note: 1 of 2 windows made no trades in the test block (no BUY signal on a test bar before its last, or too few test bars for a first signal); their 0.00% says nothing about the parameters.
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

Worked by hand (a signal on bar `t` fills at the close of bar `t + 1`; a BUY
while holding spends the cash left):

- Window 1, train bars 0-7 (10, 11, 12, 13, 12, 11, 10, 11). `window=2`: bar
  2 (12) is above 10 and 11, 76 @ 13 on bar 3 (12 left); bar 3 again, 1 @ 12
  on bar 4; bar 5 (11) is below 13 and 12, sold @ 10 on bar 6: 770, -23.00%.
  `window=3`: bar 3 (13) is above 10, 11 and 12, 83 @ 12 on bar 4 (4 left);
  bar 5 (11) is below 12, 13 and 12, sold @ 10 on bar 6: 834, -16.60%. So
  `window=3`. On test bars 8-13 (13, 14, 15, 13, 12, 11) its only signals,
  on bars 12 and 13, are SELLs while flat: no trades, +0.00%. Buy and hold:
  76 @ 13 (12 left), 76 x 11 + 12 = 848, -15.20%.
- Window 2, train bars 6-13. `window=2`: 71 @ 14 on bar 9 (6 left), sold @ 12
  on bar 12: 858, -14.20%. `window=3`: 66 @ 15 on bar 10 (10 left), sold @ 11
  on bar 13: 736, -26.40%. So `window=2`. On test bars 14-19 (13, 16, 17, 15,
  14, 16): bar 16 (17) is above 13 and 16, 66 @ 15 on bar 17 (10 left); bar 17
  (15) is below 16 and 17, sold @ 14 on bar 18: 934, -6.60% (also the
  drawdown), 2 trades; bar 19's BUY is on the last bar. Buy and hold: 76 @ 13
  (12 left), 76 x 16 + 12 = 1,228, +22.80%.
- Compounded: 0.934 - 1 = -6.60% and 0.848 x 1.228 - 1 = +4.13%.

**What the output has with `--strategy`** (without it every output is
exactly as before the options existed):

- **Text**: the header line says `each NAME parameter set` instead of `each
  SMA crossover pair`; a **Params** column (every parameter of the chosen set,
  `key=value` joined by commas in the strategy's order, as wide as its longest
  cell and at least 7) replaces **Pair**. Whole values are written as whole
  numbers (`entry=-2`, `threshold=0`), because a grid counts `-2` and `-2.0`
  as one value; other values as Python writes them (`0.5`, `1e-05`). The
  no-trades note gives `no BUY signal on a test bar before its last, or too
  few test bars for a first signal` and ends `says nothing about the
  parameters.` With `--warmup` the header line ends `then traded and scored on
  the test bars after them, with its signal warmed up on the bars just before
  each test block, so that it can signal on the first test bar` and the note
  gives `no BUY signal on a test bar before its last, or, near the start of
  the data, too few bars before the block to warm up`.
- **`--json`** starts with `"strategy": NAME` (before `"warmup"` with
  `--warmup`), and each window has `params` (the full set, as numbers:
  `-2.0` stays `-2.0`) where it had `short` and `long`. The summary, the
  overfit line and the disclaimer are as before.
- **`--csv`** has one `param_KEY` column per parameter, in the strategy's
  order, where it had `short` and `long`, holding the value as Python writes
  it (`3`, `0.5`, `-2.0`).

For the example above, `--json`:

```bash
python -m trading_assistant.walkforward tests/data/wf20.csv --strategy breakout --grid window=2,3 --train 8 --test 6 --cash 1000 --json
```

```
{
  "strategy": "breakout",
  "windows": [
    {
      "window": 1,
      "train_start": 0,
      "train_end": 8,
      "test_start": 8,
      "test_end": 14,
      "params": {
        "window": 3
      },
      "train_return_pct": -16.6,
      "test_return_pct": 0.0,
      "test_max_drawdown_pct": 0.0,
      "test_trades": 0,
      "buy_hold_return_pct": -15.2
    },
    {
      "window": 2,
      "train_start": 6,
      "train_end": 14,
      "test_start": 14,
      "test_end": 20,
      "params": {
        "window": 2
      },
      "train_return_pct": -14.2,
      "test_return_pct": -6.6000000000000005,
      "test_max_drawdown_pct": -6.6000000000000005,
      "test_trades": 2,
      "buy_hold_return_pct": 22.8
    }
  ],
  "summary": {
    "windows": 2,
    "compound_test_return_pct": -6.600000000000006,
    "compound_buy_hold_return_pct": 4.134400000000005,
    "windows_beating_buy_hold": 1,
    "mean_test_return_pct": -3.3000000000000003,
    "windows_without_trades": 1,
    "test_blocks_contiguous": true
  },
  "overfit_warning": "Best in-sample parameters overfit; check them on data they were not chosen on.",
  "disclaimer": "Research aid only. Not financial advice."
}
```

and the file `--csv windows.csv` writes (the text gets `Wrote 2 rows to
windows.csv` before the overfit line):

```
window,train_start,train_end,test_start,test_end,param_window,train_return_pct,test_return_pct,test_max_drawdown_pct,test_trades,buy_hold_return_pct
1,0,8,8,14,3,-16.6000,0.0000,0.0000,0,-15.2000
2,6,14,14,20,2,-14.2000,-6.6000,-6.6000,2,22.8000
```

Parameters the grid did not set are shown too, with whole values as whole
numbers (`--json` keeps `"entry": -2.0, "exit": 0.0`):

```bash
python -m trading_assistant.walkforward tests/data/wf.csv --strategy zscore_reversion --grid window=3,4 --train 12 --test 6 --cash 1000
```

```
Walk-forward: 1 window; each zscore_reversion parameter set was chosen on its train bars only, then run on the test bars after them
Window  Train bars   Test bars                   Params     Train      Test  Buy&Hold Trades
     1        0-11       12-17 window=3,entry=-2,exit=0    +0.00%    +0.00%   +40.00%      0
Test return, compounded over the windows: +0.00%
Buy & hold, compounded over the windows:  +40.00%
Mean test return per window: +0.00%
Windows beating buy & hold: 0 of 1
Windows without test trades: 1 of 1
Note: 1 of 1 windows made no trades in the test block (no BUY signal on a test bar before its last, or too few test bars for a first signal); their 0.00% says nothing about the parameters.
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

**Warm-up near the start of the data**, on `tests/data/wf.csv` (bars 0-17:
10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 14) with
`momentum` at `window=4`, which needs 5 warm-up bars:

```bash
python -m trading_assistant.walkforward tests/data/wf.csv --strategy momentum --param window=4 --grid threshold=0,5 --train 4 --test 7 --cash 1000 --warmup
```

```
Walk-forward: 2 windows; each momentum parameter set was chosen on its train bars only, then traded and scored on the test bars after them, with its signal warmed up on the bars just before each test block, so that it can signal on the first test bar
Window  Train bars   Test bars               Params     Train      Test  Buy&Hold Trades
     1         0-3        4-10 window=4,threshold=0    +0.00%    -7.60%   +20.00%      1
     2        7-10       11-17 window=4,threshold=0    +0.00%    +0.00%   +27.00%      1
Test return, compounded over the windows: -7.60%
Buy & hold, compounded over the windows:  +52.40%
Mean test return per window: -3.80%
Windows beating buy & hold: 0 of 2
Windows without test trades: 0 of 2
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

A 4-bar train block has no two 4-bar rates of change, so both thresholds make
0.00% and the tie goes to `threshold=0`. Block 1 starts on bar 4, so it gets
only bars 0-3 (4 of 5): the 4-bar rate of change exists from bar 4 (10 / 10,
0.00), bar 8 (12 / 10, +20.00) crosses up from bar 7's 0.00, 76 @ 13 on bar 9
(12 left), 924 on bar 10: -7.60%. Block 2 gets its full 5 bars (6-10): bar 14
(13 / 12, +8.33) crosses up from -15.38, 71 @ 14 on bar 15 (6 left), 1,000 on
bar 17: +0.00% (drawdown -6.63%). Without `--warmup` neither block trades.

**Usage errors (exit 2)**, each a one-line message after the usage line, for
example:

| Command line (after the file, `--train` and `--test`) | Message |
| --- | --- |
| `--strategy sma_cross --short 2` | `--short cannot be combined with --strategy, --grid or --param; give sma_cross's windows as --strategy sma_cross --grid short=LIST --grid long=LIST` |
| `--grid window=2` | `--grid needs --strategy` |
| `--strategy breakout --grid window=2,x` | `--grid window needs a comma list of finite numbers, got 'x'` |
| `--strategy breakout --grid window=2,0,3` | `window must be a whole number of at least 1, got 0` |
| `--strategy breakout --param window=x` | `--param window needs a number, got 'x'` (the main command's message) |
| `--strategy breakout --param window=2,3` | `--param window takes one value, got '2,3'; give a list of values with --grid window=2,3` |
| `--strategy breakout --grid window=2 --grid window=3` | `--grid window given more than once` |
| `--strategy breakout --grid window=2 --param window=3` | `window is in both --grid and --param; give only one` |
| `--strategy breakout --grid period=2` | `unknown parameter 'period' for strategy 'breakout'; choose from: window` |
| `--strategy rsi_reversion --grid oversold=20,120` | `oversold must be from 0 to 100, got 120` |
| `--strategy sma_cross --grid short=50 --grid long=20` | `no parameter combination for sma_cross passes its checks: short window must be smaller than long window` |
| `--strategy nope` | `argument --strategy: invalid choice: 'nope' (choose from 'sma_cross', 'rsi_reversion', 'breakout', 'ema_cross', 'momentum', 'zscore_reversion', 'hull_trend')` |

**Shortened option names.** Like every option these can be shortened to a
unique prefix: `--g` to `--gri` mean `--grid`, `--p` to `--para` mean
`--param` and `--str` to `--strateg` mean `--strategy`. `--st` still means
`--step` (a hidden exact alias, since `--strategy` makes the prefix
ambiguous), and `--s` is still ambiguous, now among `--short, --step, --st,
--strategy`. The usage line that `--help` and every usage error print is the
one from before the options existed; `--help` lists them after `--csv`.

**Web.** The "Walk-forward test" panel has a **Strategy** dropdown (filled
from `/api/samples`, like the portfolio panel's). With `sma_cross` the panel
sends exactly the request it sent before. Another strategy hides the two
window lists and shows one text field per parameter, holding its default:
a value with a comma goes in `grid`, another value that differs from the
default in `params`, and a default left as it is is not sent. A reply with
`strategy` gets the Params column, its cells and the strategy's header line
and notes; a refused request shows the server's message in the panel's error
box.

`POST /api/walkforward` takes the three as JSON fields:

| Field | Value | Meaning |
| --- | --- | --- |
| `strategy` | a strategy name | `--strategy`; missing, `null` or `""` means none (the SMA pairs, as before) |
| `grid` | a list of `"KEY=LIST"` strings, like `["window=10,20,30"]` | `--grid`, one string per option; `null`, `""` or `[]` means none |
| `params` | a list of `"KEY=VALUE"` strings, like `["threshold=0.5"]` | `--param`; `null`, `""` or `[]` means none |

With any of them, `short` and `long` are not required, and giving either
(anything but missing, `null`, `""` or `[]`) is the command's 400. Every
request the command refuses is a 400 with the command's message (the 28
cases of `tests/test_web_walkforward_strategy.py`, errors of the table above
included); a `strategy` that is not a string is named as Python shows it
(`argument --strategy: invalid choice: 5 (choose from ...)`), and `grid` or
`params` that is not a list of strings is `grid must be a list of "KEY=LIST"
strings, like ["window=10,20,30"]` (`params`: `"KEY=VALUE"`, `["threshold=0.5"]`).
The three are read first: a `strategy` that is not a name, or a `grid` or
`params` that is not a list of strings, is reported before anything else.
Their contents are checked after the other fields are read (so `train: "x"`
comes first), in the command's order, before `train`, `test` and `step` below
1 and the costs. Then window values (`short`, `long`, `window`, `period`) are
held to 500, before anything about the prices: `--grid window must be at most
500, got 501` (`--param ...` for `params`).
The reply is exactly the command's `--json` object. For example

```
{"source": "csv", "csv": "date,close\n2026-05-01,10\n...", "strategy": "breakout", "grid": ["window=2,3"], "train": 8, "test": 6, "cash": 1000}
```

with the 20 closes above replies with exactly the `--json` object above.
Without the three fields (or with them `null`, `""`, or `[]` for the lists)
the reply is exactly the old one, byte for byte. Before 0.22.0 the server
ignored these keys, so a request that already sent `"strategy": "breakout"`
with `short` and `long` was run as SMA pairs and is now a 400.

**Work limits.** A request may try at most **10,000 parameter sets**, counted
from the lists (after every single value is checked, before any set is built
or the rules between two parameters are applied):

```
{"ok": false, "error": "this walk-forward is too big for the web page (10,100 parameter sets; the limit is 10,000); use shorter --grid lists, or run python -m trading_assistant.walkforward"}
```

and its work is held to the same **300,000 bar-steps** as the SMA pairs (whose
count, windows x (pairs x train + test), does not change). A bar-step is one
bar of an SMA crossover backtest, about 8 microseconds where these were
measured. Each window backtests every set on `train` bars and one set on
`test` bars (counted as the dearest, with its full warm-up when `warmup` is
on), so the work is windows x (the sets' train costs + the dearest test
cost), rounded up. The cost of one backtest depends on the strategy:

| Strategy | Cost of one backtest of `n` bars after `w` warm-up bars, in bar-steps | Measured per unit |
| --- | --- | --- |
| `sma_cross` | `n x (1 + 0.005 x long)` | about 7 + 0.04 x long microseconds per bar |
| `breakout` | `n x (0.5 + 0.004 x window)` | about 3.5 + 0.025 x window microseconds per bar |
| `rsi_reversion` | `reads x 0.1` | 0.59 to 0.67 microseconds per close read |
| `ema_cross` | `reads x 0.03` | 0.17 to 0.20 microseconds per close read |
| `momentum` | `reads x 0.02` | 0.13 to 0.15 microseconds per close read |
| `zscore_reversion` | `reads x 0.17 + past x window x 0.024` | 1.04 per read + 0.148 per window-read (least-squares fit) |
| `hull_trend` | `reads x 0.45 + past x window x 0.018` | 2.76 per read + 0.113 per window-read (least-squares fit) |

`sma_cross` and `breakout` read a window of closes on each bar; the other
five work their indicator out again over every close so far, so a backtest
reads `reads = n x w + n x (n + 1) / 2` closes, and `zscore_reversion` and
`hull_trend` also do a window-long sum for each close past their window
(`past`: the sum over the bars of the closes so far past the window). The
weights are 10% to 30% above the measured times, which varied up to twice
between runs on one machine. On 16 real walk-forwards of the seven
strategies a request at the limit would take 1.0 to 4.9 seconds there; on 3
of the SMA pairs, 2.6 to 3.6. On the
750-bar `random_walk` sample, `zscore_reversion` with `grid`
`["window=5,10,20"]`, `test` 60 and `warmup` is 277,374 bar-steps with
`train` 230 (a 200, in about 2.2 seconds there) and 301,867 with `train`
240:

```
{"ok": false, "error": "this walk-forward is too big for the web page (8 windows x 3 zscore_reversion parameter sets, 301,867 bar-steps; the limit is 300,000); use fewer parameter sets, a larger step or shorter blocks, or run python -m trading_assistant.walkforward"}
```

## `python -m trading_assistant.portfolio FOLDER [options]`

Backtests the SMA crossover, or another strategy with `--strategy`, on
several symbols at once. Every `.csv` file
directly inside `FOLDER` is one symbol (the file name without `.csv`), found
and read like `--scan` does; each needs a `date` and a `close` column. The
files are lined up on the dates **every** file has: a date missing from one
file is dropped for all of them, nothing is filled in or guessed, and dates
are matched as exact text. The cash is split equally between the symbols (or
by `--weights`), each symbol is run through the same backtest as
`--backtest` with its share, and the portfolio's account value on each shared
date is the sum of the symbols' account values.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--short N` | 20 | short SMA window; `sma_cross` only |
| `--long N` | 50 | long SMA window; must be above `--short`; `sma_cross` only |
| `--cash AMOUNT` | 10000 | starting cash for the whole portfolio |
| `--fee AMOUNT` | 0 | fixed cost per trade |
| `--fee-pct PCT` | 0 | percent of traded value per trade |
| `--weights SYMBOL=PCT ...` | equal split | split the cash by these percentages: one per file used, each above 0, adding up to exactly 100 as written (`33.3 33.3 33.4` does, `33.33` three times does not) |
| `--json` | off | print one JSON object instead of the text |
| `--csv OUT` | none | also write one row per shared date to `OUT` |
| `--strategy NAME` | `sma_cross` | the rule every symbol trades, one of the seven of [`--strategy`](#backtest-options) |
| `--param KEY=VALUE` | none | change one of the strategy's parameters; numbers only; repeatable |

It trades long only, with the main backtest's rules; there is no `--fill`,
`--slippage`, `--position-size`, stop, target, trailing stop or risk sizing,
and it reads no `--config` file (so no `[strategy.NAME]` section either).

```
$ python -m trading_assistant.portfolio pf --short 5 --long 20 --weights uptrend=50 downtrend=30 sideways=20
Portfolio: 3 symbols, cash split by weight (downtrend 30%, sideways 20%, uptrend 50%), SMA 5/20 crossover, fee 0.00 + 0.00%, on the dates every file shares
Dates: 2023-01-02 to 2023-07-28 (150 shared dates)
Cash: 10,000.00  Final equity: 11,004.97
Return: +10.05%  Max drawdown: -3.40%  Buy & hold (same weights): +9.70%
Symbol     Weight  Bars used  Bars lost   Return  Trades  Buy&Hold
downtrend     30%        150         50   -2.55%       4   -20.77%
sideways      20%        150          0  -20.12%      16    +3.43%
uptrend       50%        150         50  +29.68%       3   +30.49%
Worst single-symbol drawdown: -23.92% (sideways)
Note: dates not shared by every file were dropped (see Bars lost); nothing was filled in.
Research aid only. Not financial advice.
```

(`pf` holds the `uptrend`, `downtrend` and `sideways` samples written with
`python -m trading_assistant.samples NAME pf/NAME.csv`; `sideways` has 150
bars, the others 200, so 50 of their bars are dropped.)

Return and drawdown are those of the summed account value (the drawdown is
never an average of the symbols'). Buy & hold uses the same cash split. The
symbols are in file-name order. A file that cannot be read, has no rows, no
`date` column or a blank date, holds a value that is not a number or a close
that is not positive, or repeats another file's symbol is skipped and listed
under `Skipped:` with its reason; the rest carry on.

`--json` prints `{"summary": {...}, "skipped": [...], "disclaimer": "..."}`
(with a strategy other than `sma_cross`, `"title"` comes first; see below).
`summary` has `short`, `long` (or, with another strategy, `strategy` and
`params`), `fee`, `fee_pct`, `weights` (only with
`--weights`), `start_date`, `end_date`, `shared_dates`, `initial_cash`,
`final_equity`, `return_pct`, `max_drawdown_pct`, `buy_hold_return_pct`,
`worst_symbol_drawdown` (`symbol`, `max_drawdown_pct`) and `symbols`, one per
symbol with `symbol`, `bars_used`, `bars_lost`, `return_pct`, `trades` and
`buy_hold_return_pct`. `skipped` lists `{"file", "reason"}`. Numbers are
unrounded. `--csv OUT` writes `date,portfolio,<symbol>,...` with money to 2
decimals, for example `2023-01-02,10000.00,3333.33,3333.33,3333.33`, with or
without `--json`. `OUT` is checked before any price is read, and the file is
written only after a successful run (through a temporary file), so a failed
run leaves no CSV behind.

Exit codes: 0 success; 1 the folder is missing, not a folder or holds no
`.csv` file, fewer than 2 files can be used, too few dates are shared
(`long + 2` for the SMA crossover; other strategies below), a file repeats a
date, a weighted file was skipped, or `--csv` is a folder, in a missing
folder or one of the `.csv` files; 2 a usage problem, including weights that
do not add up to 100, a weight not above 0, a weight for a symbol with no
file, a usable file without a weight, and the `--strategy`/`--param` errors
below. For example:

```
Error: only 1 of the 1 .csv files in one could be used (0 skipped); a portfolio needs at least 2
Error: only 150 dates shared by all 3 symbols; need at least 202 (long window 200 + 2)
Error: uptrend: date '2023-01-03' appears more than once
Error: --csv refuses to overwrite the input file pf/uptrend.csv
trading_assistant.portfolio: error: --weights must add up to 100, got 110
trading_assistant.portfolio: error: --weights: no weight for sideways; every file that is used needs one
```

### Strategies in the portfolio (`--strategy`, `--param`)

`--strategy NAME` picks the rule every symbol trades, one of the seven of
[`--strategy`](#backtest-options) (default `sma_cross`), and
`--param KEY=VALUE` (repeatable, numbers only) changes one of its
parameters, with the main command's meaning, checks and messages. The shared
dates, the cash split (equal or `--weights`), the costs and the buy-and-hold
comparison do not depend on it; each symbol is run through the same backtest
as `--backtest --strategy NAME` with its share of the cash.

Example: `ab/AAA.csv` and `ab/BBB.csv`, closes on the same 10 dates,
2026-04-01 to 2026-04-10 (bars 0-9):

| bar | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAA | 10 | 11 | 12 | 13 | 12 | 11 | 10 | 11 | 13 | 14 |
| BBB | 20 | 19 | 18 | 19 | 21 | 22 | 21 | 19 | 18 | 20 |

```
$ python -m trading_assistant.portfolio ab --strategy breakout --param window=3 --cash 1000
Portfolio: 2 symbols, cash split equally, breakout (window=3), fee 0.00 + 0.00%, on the dates every file shares
Dates: 2026-04-01 to 2026-04-10 (10 shared dates)
Cash: 1,000.00  Final equity: 830.00
Return: -17.00%  Max drawdown: -17.00%  Buy & hold (equal weight): +20.00%
Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold
AAA            10          0  -16.40%       3   +40.00%
BBB            10          0  -17.60%       2    +0.00%
Worst single-symbol drawdown: -17.60% (BBB)
Research aid only. Not financial advice.
```

Worked out, 500 each (`breakout` with `window=3` buys when a close is above
the highest of the 3 closes before it and sells when it is below the lowest;
a signal fills at the next bar's close):

| Symbol | Signal | Fill | Cash after | Account value by bar |
| --- | --- | --- | --- | --- |
| AAA | bar 3: 13 > 12 BUY | bar 4: BUY 41 @ 12.00 | 8.00 | bars 0-4 500, bar 5 459 |
| AAA | bar 5: 11 < 12 SELL | bar 6: SELL 41 @ 10.00 | 418.00 | bars 6-8 418 |
| AAA | bar 8: 13 > 11 BUY | bar 9: BUY 29 @ 14.00 | 12.00 | bar 9 418 |
| BBB | bar 4: 21 > 19 BUY | bar 5: BUY 22 @ 22.00 | 16.00 | bars 0-5 500, bar 6 478, bar 7 434 |
| BBB | bar 7: 19 < 21 SELL | bar 8: SELL 22 @ 18.00 | 412.00 | bars 8-9 412 |

These are exactly the fills of `python -m trading_assistant ab/AAA.csv
--backtest --strategy breakout --param window=3 --cash 500` (and the same for
`ab/BBB.csv`). The portfolio's account value is the sum, 1,000 on bars 0-4,
then 959, 896, 852, 830 and 830: the peak is 1,000 and the lowest value
after it 830, so the maximum drawdown is (830 - 1,000) / 1,000 = -17.00%.
Buy and hold: 50 AAA at 10 end at 700 and 25 BBB at 20 at 500, 1,200 in all,
+20.00%. With `--weights AAA=60 BBB=40` AAA gets 600 (50, then 35 shares;
500.00) and BBB 400 (18 shares; 328.00): 828.00, -17.20%, against +24.00%
for buy and hold with the same weights. The SMA crossover
(`--short 2 --long 3`) ends the same folder at 912.00, -8.80%.

`--json` for the first run starts like this (the rest of `summary`, then
`skipped` and `disclaimer`, as without a strategy):

```json
{
  "title": "Portfolio: 2 symbols, cash split equally, breakout (window=3), fee 0.00 + 0.00%, on the dates every file shares",
  "summary": {
    "strategy": "breakout",
    "params": {
      "window": 3
    },
    "fee": 0.0,
    "fee_pct": 0.0,
```

The rules:

- **Without `--strategy`, or with `--strategy sma_cross`, every output is as
  before**: text, `--json`, `--csv` and every error, the usage line of usage
  errors included. Only `--help` changes: it lists and describes both
  options, which the usage line does not list.
- **`--param` on its own adjusts `sma_cross`.** `--param short=2 --param
  long=3`, with or without `--strategy sma_cross`, prints exactly what
  `--short 2 --long 3` prints, `--csv` file included. A `--param short=` that
  contradicts an explicit `--short` (or the same for `long`) is a usage
  error; one equal to it is not (`--short 2 --param short=2` runs). As in the main command the parameters
  are checked against the strategy's defaults, so `--short 30 --param
  long=25` passes that check and is refused by the run instead (exit 1,
  `short window must be smaller than long window`).
- **`--short` and `--long` only apply to `sma_cross`.** With another strategy
  either is a usage error, even at its default value; set that strategy's
  parameters with `--param`.
- **The title line names the strategy and all its parameters**, defaults
  included, as the `Backtest:` line of `--backtest` does:
  `--strategy momentum --param window=3` gives
  `momentum (window=3, threshold=0.0)`. `--json` then starts with `title`,
  that line, and `summary` has `strategy` and `params` (every parameter)
  where it had `short` and `long`; every other key is as before. The
  `--csv` file has the same columns.
- **Too few shared dates names the strategy's real minimum**: the bars
  before its first possible signal plus one to fill it (exit 1).

  | Strategy | Shared dates needed | With the defaults |
  | --- | --- | --- |
  | `sma_cross`, `ema_cross` | `long + 2` | 52, 28 |
  | `breakout`, `zscore_reversion` | `window + 2` | 22, 22 |
  | `rsi_reversion` | `period + 3` | 17 |
  | `momentum` | `window + 3` | 23 |
  | `hull_trend` | `window + isqrt(window) + 2` (`isqrt`: the whole square root) | 26 |

- **Shortened option names**: `--s` still means `--short` (a hidden exact
  alias; it would otherwise be ambiguous). `--st` to `--strategy` and `--p`
  to `--param`, unrecognized arguments before, now mean the new options.
  Every other shortened name means what it meant; only the bare `--=X`,
  still an ambiguous option, now lists the new names (and `--s`) among its
  matches.

Errors, on the same folder:

```
$ python -m trading_assistant.portfolio ab --strategy breakout --short 5
trading_assistant.portfolio: error: --short only applies to --strategy sma_cross; set breakout's parameters with --param
$ python -m trading_assistant.portfolio ab --short 5 --param short=6
trading_assistant.portfolio: error: --param short=6 contradicts --short 5; give only one
$ python -m trading_assistant.portfolio ab --strategy breakout --param window=0
trading_assistant.portfolio: error: window must be a whole number of at least 1, got 0
$ python -m trading_assistant.portfolio ab --strategy nope
trading_assistant.portfolio: error: argument --strategy: invalid choice: 'nope' (choose from 'sma_cross', 'rsi_reversion', 'breakout', 'ema_cross', 'momentum', 'zscore_reversion', 'hull_trend')
$ python -m trading_assistant.portfolio ab --strategy breakout --param window=9
Error: only 10 dates shared by all 2 symbols; need at least 11 for breakout (window=9): 10 for its first signal + 1 to fill it
$ python -m trading_assistant.portfolio ab --strategy hull_trend
Error: only 10 dates shared by all 2 symbols; need at least 26 for hull_trend (window=20): 25 for its first signal + 1 to fill it
```

(the usage errors, exit 2, print the usage line first; the last two are
exit 1).

The web page's "Portfolio backtest" panel and
[`POST /api/portfolio`](#post-apiportfolio) run the same code on files sent
by the browser.

## `python -m trading_assistant.summary PRICES.csv`

Prints a summary of the data: row count, first and last date, minimum, maximum
and mean close, the largest one-bar rise and fall (percent change of the close,
with the date), the number of rows that repeat an earlier date, the number of
closes that are zero or negative, and the annualised volatility of per-bar
returns (sample standard deviation times the square root of 252). Returns use
only bars whose previous close is above zero. Without a `date` column the date
lines say `n/a` and bars are named by position. It does not look for missing
business days or holidays.

Exit codes: 0 success; 1 data problem (file missing or unreadable, no `close`
column, bad number, no rows); 2 unparseable arguments.

## `python -m trading_assistant.web`

Serves the backtest page on your own machine; it loads nothing from the
internet.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--host HOST` | `127.0.0.1` | address to bind (loopback only by default) |
| `--port PORT` | 8765 | port to listen on; if busy, the next free one above it; `0` means any free port |
| `--verbose` | off | log every request and debug details |

Press Ctrl+C to stop. `scripts/web.sh` runs the same thing. Each request is
logged as one line, `METHOD PATH STATUS TIMEms` (for example
`GET /nope 404 0ms`); the line is written before the response is sent, so once
a client has its response the line is already in the log.

The page's settings form has the same settings as the command line: windows,
RSI period, starting cash, both fees, strategy and its parameters, slippage,
position size, fill price, stop loss, take profit, trailing stop and risk
sizing. **Position size is entered as a percentage of the account** (`50`
means half; blank means all-in) and sent to the server as a fraction. Stop
loss, take profit and trailing stop are optional: empty means not used, and an
empty trailing stop is not sent at all, so the request is exactly the one the
page sent before the field existed. **Risk % per buy**, **ATR multiplier**
and **ATR period** sit after the trailing stop. An empty Risk % means no risk
sizing, and then Risk % is not sent; the ATR fields count (and are sent) only
when Risk % has a value or the ATR stop box is ticked (empty means the
defaults 2 and 14, as their placeholders say). The **ATR stop** box sits after the ATR period: ticked, the page sends
`"atr_stop": true` (after the ATR fields, which are then sent too when filled
in, with or without Risk %); unticked or untouched, the request is exactly the
one the page sent before the box existed. The **Cooldown (bars)** field
sits after the ATR stop box: filled in, the page sends `cooldown`; empty, the
request is exactly the one the page sent before the field existed. The
**Min hold (bars)** field sits after the Cooldown field: filled in, the page
sends `min_hold`; empty, the request is exactly the one the page sent before
the field existed. The **Max hold (bars)** field sits after it: filled in,
the page sends `max_hold`; empty, the request is again exactly the old one.
The **Max drawdown (%)** field sits after that: filled in,
the page sends `max_drawdown`; empty, the request is again exactly the old
one. The **Max losses** field sits between the Cooldown and Min hold
fields: filled in, the page sends `max_losses` (right after `min_hold` in the
request); empty, the request is again exactly the old one. None of these four
needs candle data, so unlike the fields below they are never greyed out, and
the close-only hint names none of them. The **Add-on (%)** and **Max adds**
fields sit after the Max drawdown field: each is sent only when filled in
(`add_on`, then `max_adds`, right after `max_drawdown` in the request), so with
both empty the request is exactly the one the page sent before they existed.
A filled Max adds is sent even with Add-on empty, and the page then shows the
server's message, `--max-adds only makes sense together with --add-on`. They
need no candle data either: never greyed out or cleared, also for a
close-only CSV, and the close-only hint does not name them. The **Trade list** box sits right
after the ATR stop box (and before the Explain signal box): ticked, the page sends
`"trade_list": true` (right after `max_drawdown`, or after `add_on` and
`max_adds` when they are sent, or where it would be, before `strategy`,
`params` and `csv`); unticked,
the request is exactly the one the page sent before the box existed. It needs
no candle data either, so it is never greyed out or unticked, and the
close-only hint does not name it. When the reply has `trade_list`, a
**Trade list** panel after the Trades table shows it with the text table's
columns and numbers (formatted as the text report formats them, down to an
exact half: an outlay of 990.125 shows as 990.12, as in the text), the open
row says `open` and ends "(unrealized: marked at the last close, no selling
costs)", and the footer line is the text's; with no trades it says "No
trades.". Without `trade_list` in the reply the panel stays hidden. The
**Explain signal** box sits right after the Trade list box (and before the
Cooldown field), next to the other switch that changes no trade: ticked, the
page sends `"explain": true` (right after `trade_list` in the request, or
where it would be); unticked, the request is exactly the one the page sent
before the box existed. It needs no candle data, so it is never greyed out or
unticked, and the close-only hint does not name it. The page has no signal
of its own outside the text report, and with `explain` the reply's `report`
already has the sentence right under its `Signal:` line, so the page shows
that report as it is: the sentence appears once, in the **Text report**
panel (open it to see it), and nothing else on the page changes. An unticked
run, also one after a ticked run, shows no sentence. The **Breakeven (%)**
field sits after the trailing stop: filled in, the page sends `breakeven`;
empty, the request is again exactly the old one. The **Scale out (%)** field
sits after the Breakeven field: filled in, the page sends `scale_out` (right
after `breakeven` in the request, or where it would be); empty, the request
is again exactly the old one. Fill price,
stop loss, take profit, trailing stop, breakeven, the scale-out, risk sizing, the ATR stop and the
cooldown need candle data: every built-in sample has it, but for a pasted or
uploaded CSV they are greyed out (and cleared, the box unticked) until its
header has `open`, `high` and `low` columns; the close-only hint then names
them (ending "The scale-out needs them too."). Risk sizing shows in the text report (its `Risk sizing:` and
`Skipped:` lines); with Risk % or the ATR stop the **Trades** card also gives
the number of skipped buys (`1 buys, 1 sells, 0 skipped`), and with a cooldown
it adds the buys the cooldown dropped (`1 buys, 1 sells, 1 skipped by
cooldown`); with a minimum holding time it adds the signal sells it skipped
(`1 buys, 0 sells, 1 signal sells skipped by min hold`; with a maximum
holding time too, `2 buys, 1 sells, 0 signal sells skipped by min hold, 1 sold
by max hold`); with a maximum holding time it adds the time exits
(`2 buys, 2 sells, 2 sold by max hold`), and with a maximum drawdown the buys
the halt dropped (`1 buys, 1 sells, 1 skipped by drawdown`; with both,
`1 buys, 1 sells, 1 sold by max hold, 1 skipped by drawdown`); with a
breakeven stop it adds its sales right after the risk sizing count
(`2 buys, 1 sells, 1 sold at breakeven`; with a cooldown as well,
`1 buys, 1 sells, 1 sold at breakeven, 1 skipped by cooldown`); with a
scale-out it adds its partial sales right after that (`2 buys, 2 sells, 1
partial sells by scale-out`; with a breakeven stop as well, `2 buys, 2 sells,
1 sold at breakeven, 1 partial sells by scale-out`); with a
losing-streak halt it adds the buys the halt dropped, last
(`1 buys, 1 sells, 2 buys skipped by losing streak`; the count is shown even
when it is 0, `3 buys, 2 sells, 0 buys skipped by losing streak`); with
add-ons it adds the add-on buys and the add-ons that got 0 shares, right after
the scale-out count (`2 buys, 1 sells, 1 add-on buys, 0 add-ons skipped` for
`up.csv` at a position size of 50 with Add-on 10; `1 buys, 1 sells, 0 add-on
buys, 3 add-ons skipped` all-in), and nothing when the option is not used. The results show the
fill, sizing and exit settings as cards next to the other numbers, and the
trades table has a Reason column (`signal`, `stop`, `target`, `trail`, `atr`,
`breakeven`, `time`, `drawdown`, `scale_out`, `add_on`). The **Exits** card lists only the stop loss and take profit; a
trailing stop, the ATR stop, the breakeven stop, the scale-out, the maximum holding time or the maximum drawdown does not show on it (see the trades table and the text
report's `Exits:`, `Scale out:`, `Max hold:` and `Drawdown:` lines). A rejected request shows the server's message in
the page's error area. The page computes nothing itself: every number comes
from the server, which uses the same analysis code as the command line.

The **"Scan several files"** panel under the backtest is the command line's
`--scan` for files you pick on your computer: choose one or more `.csv` files,
optionally set the minimum score, the rows to keep and the windows, and run.
It shows the ranked table with the score and the four parts (green above 0,
red below), the found / scored / skipped / shown counts, the skipped files
with their reasons, and the research-aid line. The files are sent to the local
server only and never saved; the numbers are those of `--scan --json`.

The **"Walk-forward test"** panel is described with
[its command](#python--m-trading_assistantwalkforward-pricescsv-options). The
**"Portfolio backtest"** panel is the
[portfolio command](#python--m-trading_assistantportfolio-folder-options) for
files you pick: choose two or more `.csv` files with `date` and `close`
columns, set the windows, cash, costs and optional weights (`A=70 B=30`,
spaces or commas between them; empty splits the cash equally), and run. It
shows the title line, the summary, one row per symbol (with a Weight column
when weights are set), the worst single-symbol drawdown, the note about
dropped dates, the skipped files and the disclaimer, with the numbers of the
command's `--json`.

Its **Strategy** dropdown, filled from the same list as the backtest panel's,
is `--strategy`. With `sma_cross` (or before the list has loaded) the panel is
as before and sends exactly the request it sent before. Another strategy
hides **Short SMA** and **Long SMA** and shows one number field per
parameter, holding its default, as the backtest panel does; the request then
has no `short` or `long` but `strategy` and `params`. Only parameters that
are filled in and differ from their default are sent, so an untouched
`threshold` shows as `threshold=0.0` in the title, as in the command without
`--param`. The title is then the reply's `title`, word for word the
command's; without one the panel builds the line itself, as before. A value
the server refuses (say `window` 0, or 600) shows its one-line message in the
panel's error box.

### `POST /api/backtest`

The page's JSON API, usable directly. Body: a JSON object with
`Content-Type: application/json`.

| Key | Meaning |
| --- | --- |
| `sample` or `csv` (+ `source`: `"sample"` or `"csv"`) | a built-in sample name, or CSV text |
| `short`, `long`, `rsi_period`, `cash`, `fee`, `fee_pct` | as the flags |
| `strategy`, `params` | strategy name and an object of numeric parameters |
| `slippage`, `fill`, `stop_loss`, `take_profit`, `trailing_stop` | as the flags (`fill`: `"close"` or `"open"`) |
| `risk_pct`, `atr_mult`, `atr_period` | as `--risk-pct`, `--atr-mult`, `--atr-period` (checked by the same `cli.check_risk`) |
| `atr_stop` | `true` or `false`, as `--atr-stop` (see below) |
| `cooldown` | a whole number of at least 1, as `--cooldown` (see below) |
| `min_hold` | a whole number of at least 1, as `--min-hold` (see below) |
| `max_hold` | a whole number of at least 1, as `--max-hold` (see below) |
| `max_drawdown` | a number above 0 and below 100, as `--max-drawdown` (see below) |
| `breakeven` | a number above 0, as `--breakeven` (see below) |
| `max_losses` | a whole number of at least 1, as `--max-losses` (see below) |
| `scale_out` | a number above 0, as `--scale-out` (see below) |
| `add_on`, `max_adds` | a number above 0 and a whole number of at least 1, as `--add-on` and `--max-adds` (see below) |
| `explain` | `true` or `false`, as `--explain` (see below) |
| `position_size` | a fraction of the account, above 0 and at most 1, as `--position-size` |

Missing keys, `null` and `""` mean the default. Values are checked with the
command line's rules, and a rejected request gets status 400 and
`{"ok": false, "error": "..."}` with a one-line message, for example
`fill must be 'close' or 'open', got 'midday'` or
`--slippage must be between 0 and 100 (exclusive), got 100`.

`fill: "open"`, `stop_loss`, `take_profit`, `trailing_stop`, `risk_pct`, `atr_stop: true`, `breakeven` or `scale_out` need candle data. A sample then
uses its sample candles (same closes and dates as the plain sample); a pasted
CSV is read as a candle file, and one without the candle columns is rejected
with the same message the command line gives:

```
{"ok": false, "error": "CSV has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'"}
```

The reply's `params` lists the old settings plus each new one that was given,
in this order, for example `{"short": 5, "long": 20, "rsi_period": 14,
"cash": 10000.0, "fee": 0.0, "fee_pct": 0.0, "slippage": 0.5,
"position_size": 0.5, "fill": "open", "stop_loss": 3.0, "take_profit": 6.0,
"trailing_stop": 2.0}`. With a stop, target, trailing stop, ATR stop, breakeven stop, `max_hold`, `max_drawdown`, `scale_out` or `add_on` each entry in
`trades` has a `reason` (`signal`, `stop`, `target`, `trail`, `atr`, `breakeven`, `time`, `drawdown`, `scale_out` or `add_on`), and `columns`
(and the `csv`) end with `reason`. `trailing_stop` follows the flag's rules:
`{"trailing_stop": 0}` is a 400 with
`--trailing-stop must be between 0 and 100 (both exclusive), got 0`, and
`{"trailing_stop": "abc"}` a 400 with `trailing_stop must be a number, got 'abc'`.
`risk_pct`, `atr_mult` and `atr_period` are echoed in `params` the same
way, right after `trailing_stop`, only when sent (defaults are not echoed):
`{"csv": ..., "short": 1, "long": 2, "cash": 1000, "risk_pct": 2,
"atr_mult": 2, "atr_period": 3}` on `candles8.csv` gives `params`
`{"short": 1, "long": 2, "rsi_period": 14, "cash": 1000.0, "fee": 0.0,
"fee_pct": 0.0, "risk_pct": 2.0, "atr_mult": 2.0, "atr_period": 3}`, trades
BUY 7 @ 11.00 and SELL 7 @ 8.00, and `summary.risk_skipped_buys` `0` (right
after `sells`, only when `risk_pct` or `atr_stop` is used). They follow the flags' rules
with the command's messages: `{"risk_pct": 0}` is a 400 with
`--risk-pct must be above 0 and at most 100, got 0`, `{"atr_mult": 3}`
without `risk_pct` a 400 with
`--atr-mult only makes sense together with --risk-pct or --atr-stop` (the
command's message), and
`{"risk_pct": 2, "atr_mult": "inf"}` a 400 with
`atr_mult must be a finite number`. Before 0.8.0 the server ignored these
keys, so a request that already sent them now gets risk-sized numbers or a 400.

`atr_stop` is the command's `--atr-stop`. It must be JSON `true` or
`false`: `true` turns the ATR stop on; `false`, `null`, `""` or no key leave
it off; anything else is a 400, for example `{"atr_stop": "yes"}` with
`atr_stop must be true or false, got 'yes'` and `{"atr_stop": 1}` with
`atr_stop must be true or false, got 1`. With it on, `atr_mult` and
`atr_period` count without `risk_pct` (the same `cli.check_risk` and
messages: `{"atr_stop": true, "atr_mult": 0}` is a 400 with
`--atr-mult must be above 0, got 0`), and it needs candle data like the exits.
It is echoed in `params` only when sent (`true` or `false`), right after
`atr_period`; defaults are not echoed. With `risk_pct` or `atr_stop` on,
`summary` has `risk_skipped_buys` right after `sells`, and each trade has a
`reason` (`atr` for the ATR stop's sells). `{"csv": ..., "short": 1, "long": 2,
"cash": 1000, "atr_stop": true, "atr_period": 3}` on `candles8.csv` gives
`params` ending `"atr_period": 3, "atr_stop": true`, trades BUY 90 @ 11.00
and SELL 90 @ 8.22 (`atr`), end equity 750.00 and
`summary.risk_skipped_buys` `0`. A request without `atr_stop` (or with
`null` or `""`) gets exactly the reply it got before; `{"atr_stop": false}`
gets that reply with `"atr_stop": false` added at the end of `params`.
Before this the server ignored an `atr_stop` key, so a request that already
sent one now gets the ATR stop, a 400, or the echo.
`cooldown` is the command's `--cooldown N`. It is read like the other
whole-number keys (`atr_period`): a JSON whole number (`3`, and also `3.0`) or
a string holding one (`"3"`, `" 3 "`); `null`, `""` or no key leave it off;
`true`, `false`, a fraction, other text, a list or an object is a 400, for
example `{"cooldown": 1.5}` with `cooldown must be a whole number, got 1.5`
and `{"cooldown": "abc"}` with `cooldown must be a whole number, got 'abc'`.
Then the command's own `cli.check_cooldown` applies, with its messages: without
`stop_loss`, `trailing_stop` or `atr_stop: true` it is a 400 with
`--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop`,
and `{"cooldown": 0}` a 400 with
`--cooldown must be a whole number of at least 1, got 0`. Through the stop it
needs candle data, so a close-only CSV gets the stop's 400. It is echoed in
`params` only when sent, right after `atr_stop`; with it, `summary` has
`cooldown_bars` and `cooldown_skipped_buys` (the `--json` keys) right after
`sells` (or `risk_skipped_buys`), and the `report` has the `Cooldown:` line.
`{"csv": ..., "short": 1, "long": 2, "cash": 1000, "stop_loss": 10,
"cooldown": 3}` on `candles11.csv` gives trades BUY 90 @ 11.00 and SELL 90 @
9.90 (`stop`), `summary.cooldown_bars` `3`, `summary.cooldown_skipped_buys`
`1` and end equity 901.00. A request without `cooldown` (or with `null` or
`""`) gets exactly the reply it got before. Before 0.10.0 the server ignored a
`cooldown` key, so a request that already sent one now gets the cooldown or a
400.
`max_hold` is the command's `--max-hold N`. It is read exactly like
`cooldown`: `2`, `2.0`, `"2"` and `" 2 "` are 2; `null`, `""` or no key leave
it off; `true`, `false`, a fraction, other text, a list or an object is a 400,
for example `{"max_hold": 1.5}` with `max_hold must be a whole number, got 1.5`,
`{"max_hold": "1.5"}` with `max_hold must be a whole number, got '1.5'` and
`{"max_hold": true}` with `max_hold must be a whole number`. Then the command's
own `cli.check_max_hold`: `{"max_hold": 0}` (or `"0"`, or `-1`) is a 400 with
`--max-hold must be a whole number of at least 1, got 0`. It needs no stop and
no candle data, so it works on a close-only CSV. It is echoed in `params`
only when sent, right after `cooldown` (or `min_hold`); with it, `summary` has
`max_hold_bars` and `time_exits` (the `--json` keys) right after `sells`
(after `risk_skipped_buys`, the cooldown keys and the min hold keys when those
are there), each
trade has a `reason` (`time` for its sells), `columns` and the `csv` end with
`reason`, and the `report` has the `Max hold:` line. `{"csv": ..., "short": 1,
"long": 2, "cash": 1000, "max_hold": 1}` on `closes.csv` gives trades BUY
90 @ 11.00, SELL 90 @ 12.00 (`time`), BUY 90 @ 12.00, SELL 90 @ 12.20
(`time`), `summary.max_hold_bars` `1`, `summary.time_exits` `2` and end
equity 1,108.00. A request without `max_hold` (or with `null` or `""`) gets
exactly the reply it got before. Before 0.11.0 the server ignored a
`max_hold` key, so a request that already sent one now gets the maximum
holding time or a 400.
`min_hold` is the command's `--min-hold N`, read exactly like `max_hold`: `4`,
`4.0`, `"4"` and `" 4 "` are 4; `null`, `""` or no key leave it off (and it is
not echoed); `true`, `false`, a fraction, other text (`"4.0"` too), a list or
an object is a 400, for example `{"min_hold": 4.5}` with
`min_hold must be a whole number, got 4.5`, `{"min_hold": "abc"}` with
`min_hold must be a whole number, got 'abc'` and `{"min_hold": true}` with
`min_hold must be a whole number`. Then the command's own
`cli.check_min_hold`: `{"min_hold": 0}` (or `"0"`, or `-1`) is a 400 with
`--min-hold must be a whole number of at least 1, got 0`. It needs no stop and
no candle data, so it works on a close-only CSV. It is echoed in `params`
only when sent, right after `cooldown` (before `max_hold`); with it, `summary`
has `min_hold_bars` and `min_hold_skipped_sells` (the `--json` keys) right
before the max hold keys (or where they would be), and the `report` has the
`Min hold:` line. It makes no fills, so it adds no `reason` to the trades and
no `reason` column. `{"csv": ..., "short": 1, "long": 2, "cash": 1000,
"min_hold": 4}` on `closes.csv` gives one trade, BUY 90 @ 11.00,
`summary.min_hold_bars` `4`, `summary.min_hold_skipped_sells` `1` and end
equity 1,108.00; with `3` or `1` the trades and end equity are those without
it (925.00) and `min_hold_skipped_sells` is `0`. A request without `min_hold`
(or with `null` or `""`) gets exactly the reply it got before. Before 0.14.0
the server ignored a `min_hold` key, so a request that already sent one now
gets the minimum holding time or a 400. `POST /api/walkforward`,
`/api/portfolio` and `/api/scan` ignore a `min_hold` key, as any key they do
not know.
`max_drawdown` is the command's `--max-drawdown PCT`. It is read like the
other number keys (`stop_loss`): a JSON number or a string holding one
(`16`, `16.0`, `"16"`, `" 16 "`); `null`, `""` or no key leave it off;
`true`, `false`, other text, a list or an object is a 400 with
`max_drawdown must be a number` (`..., got '16%'` for a string), and `NaN`,
`Infinity`, `"nan"` or `"inf"` a 400 with `max_drawdown must be a finite
number`. As for every number key, commas are dropped from a string first, so
`"1,6"` is 16 and `"16,5"` is 165 (see
[Max drawdown values](#max-drawdown-values)). Then the command's own
`cli.check_max_drawdown`: `{"max_drawdown": 0}` (or `"0"`, `100` or `-5`) is a
400 with `--max-drawdown must be above 0 and below 100, got 0`. It needs no
stop and no candle data, so it works on a close-only CSV. It is echoed in
`params` only when sent, right after `max_hold`; with it, `summary` has
`max_drawdown_limit_pct`, `drawdown_halt_bar` (`null` when the halt never
triggered) and `drawdown_skipped_buys` (the `--json` keys) right after
`sells` (after the other optional keys when those are there), each trade has
a `reason` (`drawdown` for its sale), `columns` and the `csv` end with
`reason`, and the `report` has the `Drawdown:` line. `{"csv": ..., "short":
1, "long": 2, "cash": 1000, "max_drawdown": 16}` on `closes.csv` gives trades
BUY 90 @ 11.00 and SELL 90 @ 10.00 (`signal`), `summary.drawdown_halt_bar`
`6`, `summary.drawdown_skipped_buys` `1` and end equity 910.00; with `17`,
`drawdown_halt_bar` is `null`, `drawdown_skipped_buys` `0` and the end equity
925.00. A request without `max_drawdown` (or with `null` or `""`) gets
exactly the reply it got before. Before 0.12.0 the server ignored a
`max_drawdown` key, so a request that already sent one now gets the drawdown
halt or a 400.
`breakeven` is the command's `--breakeven PCT`, read exactly like
`take_profit`: a JSON number or a string holding one (`5`, `5.0`, `"5"`,
`" 5 "`); `null`, `""` or no key leave it off (and it is not echoed);
`true`, `false`, other text, a list or an object is a 400 with
`breakeven must be a number` (`..., got 'abc'` for a string); `NaN`,
`Infinity`, `-Infinity`, `"nan"` or `"inf"` is a 400 with `breakeven must
be a finite number`, so the API does not take infinity (nor do the flag
and the config key). Then the command's rule: `{"breakeven": 0}` (or `"0"`,
`-1`) is a 400 with `--breakeven must be above 0, got 0`. It is a stop: it
needs candle data (a close-only CSV is the 400 shown above), and it counts as
a stop for `cooldown` (`{"breakeven": 5, "cooldown": 3}` is accepted; the
message for `cooldown` with no stop at all is unchanged). It is echoed in
`params` only when sent, right after `max_drawdown`; with it, `summary` has
`breakeven_pct` and `breakeven_exits` (the `--json` keys) right after
`sells` (after `risk_skipped_buys` when that is there, before the cooldown
keys), each trade has a `reason` (`breakeven` for its sales), `columns` and
the `csv` end with `reason`, and the `report` has the `Exits:` line (and
names it on the `Cooldown:` line). `{"csv": ..., "short": 1, "long": 2,
"cash": 1000, "breakeven": 5}` on the c.csv file of
[Breakeven stop](#breakeven-stop) gives SELL 90 @ 11.00 on bar 6
(`breakeven`), `summary.breakeven_exits` `1` and end equity 1,016.60 (the
same with `9`); with `10`, `breakeven_exits` is `0` and the end equity
925.00; with `5` and `"cooldown": 3`, 2 trades, `cooldown_skipped_buys` `1`
and 1,000.00. A request without `breakeven` (or with `null` or `""`) gets
exactly the reply it got before. Before 0.13.0 the server ignored a
`breakeven` key, so a request that already sent one now gets the breakeven
stop or a 400.
`max_losses` is the command's `--max-losses N`, read exactly like `max_hold`
and `min_hold`: a JSON whole number (`2`, or `2.0`, which reads as 2) or a
string holding one (`"2"`, `" 2 "`); `null`, `""` or no key leave it off;
`true`, `false`, a fraction (`2.5`), other text (`"2.0"`, `"abc"`, `"1,6"`),
a list or an object is a 400 with `max_losses must be a whole number`
(`..., got 2.5`, `..., got 'abc'`; see
[Max losses values](#max-losses-values)). Then the command's own
`cli.check_max_losses`: `{"max_losses": 0}` (or `"0"`, or `-1`) is a 400 with
`--max-losses must be a whole number of at least 1, got 0`. It needs no stop
and no candle data, so it works on a close-only CSV. It is echoed in `params`
only when sent, right after `breakeven` (or where it would be); with it,
`summary` has `max_losses`, `loss_halt_bar` (`null` when the halt never
triggered) and `loss_skipped_buys` (the `--json` keys) right before
`round_trips` (after the drawdown keys when those are there), and the
`report` has the `Max losses:` line. It makes no fills, so it adds no
`reason` to the trades and no `reason` column. `{"csv": ..., "short": 1,
"long": 2, "cash": 1000, "max_losses": 2}` on `losses.csv` (see
[Max losses](#max-losses)) gives trades BUY 90 @ 11.00, SELL 90 @ 9.00, BUY
82 @ 10.00 and SELL 82 @ 9.00, `summary.loss_halt_bar` `13`,
`summary.loss_skipped_buys` `1` and end equity 738.00; with `1`, bar `7`, 2
skipped and 820.00; with `3`, `loss_halt_bar` is `null`,
`loss_skipped_buys` `0` and the end equity 799.00. A request without
`max_losses` (or with `null` or `""`) gets exactly the reply it got before.
Before 0.15.0 the server ignored a `max_losses` key (even `0`), so a request
that already sent one now gets the losing-streak halt or a 400.
`scale_out` is the command's `--scale-out PCT`, read exactly like
`breakeven`: a JSON number or a string holding one (`5`, `5.0`, `"5"`,
`" 5 "`); `null`, `""` or no key leave it off (and it is not echoed);
`true`, `false`, other text, a list or an object is a 400 with
`scale_out must be a number` (`..., got 'abc'` for a string); `NaN`,
`Infinity`, `-Infinity`, `"nan"` or `"inf"` is a 400 with `scale_out must be
a finite number`. Then the command's rule: `{"scale_out": 0}` (or `"0"`,
`-1`) is a 400 with `--scale-out must be above 0, got 0`. It needs candle
data (a close-only CSV is the 400 shown above) but no other exit, and it is
not a stop: `{"scale_out": 5, "cooldown": 2}` is the 400 for `cooldown`
without a stop. It is echoed in `params` only when sent, right after
`max_losses` (or where it would be); with it, `summary` has `scale_out_pct`
and `scale_out_exits` (the `--json` keys) right after the breakeven keys (or
where they would be, before the cooldown keys), each trade has a `reason`
(`scale_out` for its partial sales), `columns` and the `csv` end with
`reason`, and the `report` has the `Scale out:` line. `{"csv": ..., "short":
1, "long": 2, "cash": 1000, "scale_out": 5}` on the c.csv file of
[Breakeven stop](#breakeven-stop) gives SELL 45 @ 11.55 on bar 5
(`scale_out`), `summary.scale_out_exits` `1` and end equity 995.95; with
`9`, 1,016.15; with `10`, `scale_out_exits` is `0` and the end equity
925.00; with `5` and `"stop_loss": 10`, 991.45. A request without
`scale_out` (or with `null` or `""`) gets exactly the reply it got before.
Before 0.16.0 the server ignored a `scale_out` key (even `0`), so a request
that already sent one now gets the scale-out or a 400.
`add_on` and `max_adds` are the command's `--add-on PCT` and `--max-adds N`.
`add_on` is read exactly like `scale_out`: a JSON number or a string holding
one (`10`, `10.0`, `"10"`, `" 10 "`; a comma is dropped, so `"1,6"` is 16);
`null`, `""` or no key leave it off; `true`, `false`, other text, a list or
an object is a 400 with `add_on must be a number` (`..., got 'abc'` for a
string); `NaN`, `Infinity`, `"nan"` or `"inf"` is a 400 with `add_on must be
a finite number`. `max_adds` is read exactly like `max_hold`: a JSON whole
number (`2`, or `2.0`) or a string holding one (`"2"`); `true`, `false`, a
fraction (`2.5`), other text (`"2.0"`, `"abc"`), a list or an object is a 400
with `max_adds must be a whole number` (`..., got 2.5`). Then the command's
rules and messages (`cli.check_add_on`): `{"add_on": 0}` (or `-1`) is a 400
with `--add-on must be above 0, got 0`, `{"add_on": 10, "max_adds": 0}` a 400
with `--max-adds must be a whole number of at least 1, got 0`, and
`max_adds` without `add_on` a 400 with `--max-adds only makes sense together
with --add-on`. `max_adds` as `null` or `""` counts as not sent: with
`add_on` it is 1, without it nothing happens (the reply is the old one). They
need no candle data, so they work on a close-only CSV. When `add_on` is sent,
`params` echoes both, right after `scale_out` (or where it would be):
`add_on` and `max_adds`, which is `1` when `max_adds` was not sent. That is
on purpose and unlike the other settings, whose defaults are never echoed
(`atr_mult` and `atr_period` are echoed only when sent): with `add_on` the
reply always says how many add-ons a position may take. With `add_on`,
`summary` has `add_on_pct`, `max_adds`, `add_on_buys` and
`add_on_skipped_buys` (the `--json` keys) right after the scale-out keys (or
where they would be, before the cooldown keys), each trade has a `reason`
(`add_on` for its buys), `columns` and the `csv` end with `reason`, and the
`report` has the `Add-ons:` line; the `report` is the command's, line for
line. `{"csv": ..., "short": 1, "long": 2, "cash": 1000, "position_size":
0.5, "add_on": 10}` on the `up.csv` of [Add-ons](#add-ons) gives BUY 36 @
14.00 on bar 7 (`add_on`), `summary.add_on_buys` `1` and end equity 1,054.00;
with `"20"`, 1,024.00; without `position_size`, `add_on_buys` `0`,
`add_on_skipped_buys` `3` and 1,180.00. A request without `add_on` and
`max_adds` (or with `null` or `""`) gets exactly the reply it got before.
Before this the server ignored these keys, so a request that already sent
them now gets the add-ons or a 400.
`trade_list` is the command's `--trade-list`, read exactly like `atr_stop`,
another switch of `/api/backtest`: JSON `true` turns it on; `false`, `null`, `""` or no
key leave it off; any string (`"true"` and `"yes"` included), any number (`1`
and `0` included), a list or an object is a 400 with `trade_list must be true
or false` (`..., got 'yes'` for a string, `..., got 1` for a number). It
changes no setting of the run and needs no candle data, so it works on a
close-only CSV. It is echoed in `params` only when sent (`true` or `false`),
right after `max_adds` (or `scale_out`, or where it would be), so `"trade_list": false`
differs from no key by that echo only. With `true` the `report` ends with the
command's trade list table (the `report` is still the command line's text
line for line), and the reply ends with `trade_list`, the `--json` array;
`summary.round_trips` and `summary.winning_round_trips` do not change.
`{"csv": ..., "short": 1, "long": 2, "cash": 1000, "trade_list": true}` on the
c.csv file of [Breakeven stop](#breakeven-stop) gives the two rows of
[Trade list](#trade-list). A request without `trade_list` (or with `null` or
`""`) gets exactly the reply it got before. Before 0.17.0 the server ignored
a `trade_list` key, so a request that sent `"trade_list": "yes"` or `1` now
gets a 400.
`explain` is the command's `--explain`, read exactly like `atr_stop` and
`trade_list`: JSON `true` turns it on; `false`, `null`, `""` or no key leave
it off; any string (`"true"` and `"yes"` included), any number (`1` and `0`
included), a list or an object is a 400 with `explain must be true or false`
(`..., got 'yes'` for a string, `..., got 1` for a number). It changes no
setting of the run and needs no candle data, so it works on a close-only CSV.
It is echoed in `params` only when sent (`true` or `false`), right after
`trade_list` (or where it would be), so `"explain": false` differs from no
key by that echo only. With `true`:

- the `report` gets the sentence as its own line right after its `Signal:`
  line, so it is the command's `--backtest --explain` output line for line
  (without the disclaimer, as always);
- the reply gets `explanation` right after `report`, next to the line it
  explains (not in `summary`, which is the traded strategy's numbers, nor in
  `params`, which echoes the request): `decision` (the `Signal:` line's BUY,
  SELL or HOLD, from `signals.crossover_signal` on `short`/`long`, whatever
  `strategy` is), `sentence` (that line, word for word), and `last_bar` and
  `previous_bar`, each `{"short": ..., "long": ...}` with the two SMAs
  unrounded (`null` where there are not enough bars yet).

`{"csv": ..., "short": 1, "long": 3, "explain": true}` on the c.csv file of
[Breakeven stop](#breakeven-stop) gives:

```
"explanation": {"decision": "HOLD", "sentence": "HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: 12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.", "last_bar": {"short": 12.2, "long": 11.733333333333334}, "previous_bar": {"short": 12.0, "long": 11.0}}
```

With its first 4, 7 and 3 rows the decision is BUY, SELL and HOLD, with the
sentences of [Signal explanation](#signal-explanation---explain); with 3
rows, too few for a crossover, `previous_bar` is
`{"short": 9.0, "long": null}`. The backtest still runs on so few bars; its
`report` already said HOLD on the `Signal:` line before, and the sentence now
says why. The API has no `--resample`, so it always explains the closes as
sent. A request without `explain` (or with `null` or `""`) gets exactly the
reply it got before; before this the server ignored an `explain` key, so a
request that sent `"explain": "yes"` or `1` now gets a 400.
`POST /api/walkforward`, `/api/portfolio` and `/api/scan` ignore it, as any
key they do not know.
The API has no weekly or monthly bars, so the `--resample` rule does not
arise there. The `report` lines are the command line's text report for the same
input. A request without the new settings gets exactly the reply it got
before they existed.

### `POST /api/scan`

The scan panel's JSON API: the command line's `--scan FOLDER --json` for files
sent in the body. The server never reads a folder or file from its disk; the
names are only labels.

| Key | Meaning |
| --- | --- |
| `files` | required: an object of file name to CSV text, e.g. `{"AAPL.csv": "date,close\n..."}` |
| `min_score`, `top` | as `--min-score` and `--top` |
| `short`, `long`, `rsi_period` | as the flags |

The names are treated like a folder listing: only names ending in `.csv` (any
capitals) count, the symbol is the name without `.csv`, and a name containing
`/` or `\` is rejected. A file that cannot be read is skipped with its reason
and does not stop the others. The reply (status 200) is **exactly the object
`--scan --json` prints** for the same files and settings: `found`, `scored`,
`shown`, `results`, `skipped`, and no `ok` key. When nothing matched,
`results` is `[]`.

Missing keys, `null` and `""` mean the default. Errors are the backtest's
kind: a 4xx status and `{"ok": false, "error": "..."}` with a one-line message,
for example `no files: send at least one .csv file in files`,
`no .csv files in the request`,
`none of the 2 .csv files in the request could be scored (2 skipped)`,
`--top must be at least 1, got 0` or
`--short (50) must be smaller than --long (20)`. The limits are the
backtest's: the body size (413), at most `max_bars` rows per file (413),
windows up to `max_window`, the run time (503) and the number of runs at a
time (429).

### `POST /api/portfolio`

The portfolio panel's JSON API: the
[portfolio command](#python--m-trading_assistantportfolio-folder-options)'s
`--json` for files sent in the body. Like `/api/scan` it never reads the
server's disk.

| Key | Meaning |
| --- | --- |
| `files` | required: an object of file name to CSV text, as for `/api/scan` |
| `short`, `long`, `cash`, `fee`, `fee_pct` | as the command's flags, with its defaults (20, 50, 10000, 0, 0) |
| `weights` | optional: a list of `"SYMBOL=PERCENT"` strings, as `--weights`, e.g. `["uptrend=50", "downtrend=30", "sideways=20"]` |
| `strategy` | optional: `--strategy`, a strategy name, read as `/api/backtest` reads it |
| `params` | optional: `--param`, a list of `"KEY=VALUE"` strings, e.g. `["window=3"]` (a list, as for `weights`) |

The reply (status 200) is **exactly the command's `--json` object**:
`summary`, `skipped` and `disclaimer`, with no `ok` key (and `title` first
with a strategy other than `sma_cross`). Errors are
`{"ok": false, "error": "..."}` with the command's one-line message, the
folder being called "the request", for example 400
`only 1 of the 1 .csv files in the request could be used (0 skipped); a portfolio needs at least 2`,
`--weights: no weight for sideways; every file that is used needs one` or
`weights must be a list of "SYMBOL=PERCENT" strings, like ["A=60", "B=40"]`
(an object is refused, so a symbol given twice is seen). The backtest's
limits apply (413, 415, 429, 503). `--csv` is command-line only.

`strategy` and `params` follow `--strategy` and `--param`:

| Value | `strategy` | `params` |
| --- | --- | --- |
| missing or `null` | `sma_cross` | none |
| `""` | `sma_cross` | 400 `params must be a list of "KEY=VALUE" strings, like ["window=10"]` |
| `[]` | 400 `unknown strategy 'list'; choose from: sma_cross, rsi_reversion, ...` | none (as `null`) |
| `true`/`false`, a number, an object | 400 `unknown strategy 'bool'` (`'int'`, `'float'`, `'dict'`) `; choose from: ...` | 400, the list message above |
| a string | a strategy name (exact, lower case), else 400 `unknown strategy 'nope'; choose from: ...` | (a list holding anything but strings: the list message) |

- A request without them, or with `strategy` `"sma_cross"`, `null` or `""`
  and `params` missing, `null` or `[]`, gets exactly the reply it got
  before, byte for byte.
- Each `"KEY=VALUE"` is read by the command's own code, so its messages are
  the command's (`--param window needs a number, got 'x'`,
  `--param short given more than once`, `window must be a whole number of at least 1, got 0`).
- `params` alone adjusts `sma_cross`: `{"params": ["short=2", "long=3"]}` (with
  or without `"strategy": "sma_cross"`) gets exactly the reply of
  `{"short": 2, "long": 3}`. A `params` value that contradicts a given
  `short` or `long` is a 400 with the command's message
  (`--param short=6 contradicts --short 5; give only one`).
- `short` or `long` counts as given when it is there and not `null` or `""`
  (the values that mean "the default"); given with another strategy, it is a
  400: `--short only applies to --strategy sma_cross; set breakout's parameters with --param`.
- Window parameters in `params` (`short`, `long`, `window`, `period`) are
  held to the page's window limit like `short` and `long`:
  `--param window must be at most 500, got 600`. A top-level `long` over the
  limit is reported first, as before.
- Too few shared dates is a 400 with the command's message, naming the real
  minimum (`need at least 524 for hull_trend (window=500): 523 for its first signal + 1 to fill it`).
- An unknown name is worded as in `/api/backtest`
  (`unknown strategy 'nope'; choose from: sma_cross, rsi_reversion, breakout, ema_cross, momentum, zscore_reversion, hull_trend`),
  not as the command's argparse message.

For example, `{"files": {...AAA.csv, BBB.csv...}, "strategy": "breakout",
"params": ["window=3"], "cash": 1000, "weights": ["AAA=60", "BBB=40"]}` gets
the object of `--strategy breakout --param window=3 --cash 1000 --weights
AAA=60 BBB=40 --json`: title
`Portfolio: 2 symbols, cash split by weight (AAA 60%, BBB 40%), breakout (window=3), fee 0.00 + 0.00%, on the dates every file shares`,
final equity 828.0.

## Other tools

Documented in their own pages:

- `drawdowns`: list every peak-to-trough-to-recovery fall of buy and hold or of a strategy. See [analysis.md](analysis.md).
- `montecarlo`: seeded bootstrap of a strategy's per-bar returns to see the spread of outcomes. See [analysis.md](analysis.md).
- `alerts`: check a file of simple price and indicator rules against the last bar. See [alerts.md](alerts.md).
- `journal`: a manual paper-trade journal kept in a CSV file you name. See [journal.md](journal.md).
