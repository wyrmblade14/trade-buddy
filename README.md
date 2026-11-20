# Trading Assistant

A small Python project that computes technical indicators from price history and
suggests BUY, SELL, or HOLD. It is a research aid, not financial advice. It places no orders.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

Create a CSV with a header row and a `close` column:

```csv
date,close
2026-01-02,101.5
2026-01-05,102.1
```

No price file to hand? Write a seeded sample series (about three years of
daily closes) and use that:

```bash
python -m trading_assistant.samples random_walk prices.csv
```

Add `--candles` to write the same sample as a candle file
(`date,open,high,low,close,volume`, same closes) for the options that need
candle data (`--candles`, `--fill open`, `--stop-loss`, `--take-profit`,
`--trailing-stop`, `--risk-pct`):

```bash
python -m trading_assistant.samples random_walk candles.csv --candles
python -m trading_assistant candles.csv --backtest --fill open
```

Then run:

```bash
python -m trading_assistant.cli prices.csv --short 20 --long 50 --rsi-period 14
```

`python -m trading_assistant prices.csv ...` is a shorter form that does the same.

Add `--explain` to see why the `Signal:` line says what it says (see
[Explain the signal](#explain-the-signal)).

## Explain the signal

`--explain` adds one sentence right after the `Signal:` line: the signal,
the short and long SMA on the last bar and on the bar before, and why. On the
11-bar candle file from [docs/cli.md](docs/cli.md#signal-explanation---explain)
(closes 10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2):

```text
$ python -m trading_assistant c.csv --short 1 --long 3 --explain
Bars:    11
Last:    12.20
Signal:  HOLD
HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: 12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.
RSI:     n/a
Research aid only. Not financial advice.
```

Its first 4 rows give `BUY because the 1-bar SMA crossed above the 3-bar
SMA: 9.00 against 8.67 on the last bar, after 8.00 against 9.00 on the bar
before.`, its first 7 a SELL (`crossed below`, 10.00 against 11.00), and its
first 3 `HOLD because a crossover needs at least 4 bars and there are 3: ...`.

- The first word is always the `Signal:` line's decision: both come from the
  same SMA crossover on `--short`/`--long`. It does not follow `--strategy`
  or `--param` (they change the backtest only), and with `--resample` it
  explains the resampled bars. A HOLD never says "crossed".
- Numbers have 2 decimals, or more when two different averages would print
  the same (`10.004 against 10.002`).
- It needs no `--backtest` and no candle file, and cannot be combined with
  `--scan`. Without it nothing changes.
- `--json` gets an `explanation` string right after `signal`, the config file
  key is `explain = yes` (ignored with `--scan`), `POST /api/backtest` takes
  `"explain": true` (its `report` gets the line and the reply an
  `explanation` object), and the web page has an **Explain signal** box. The
  sweep, walk-forward and portfolio commands do not take it. See
  [docs/cli.md](docs/cli.md#signal-explanation---explain).

## Scan a folder

`--scan FOLDER` gives every `.csv` file directly inside a folder a combined
score from -4 to 4 and lists them best first (equal scores in name order).
The score adds four parts on the last bar, each +1, 0 or -1: the SMA
crossover (short above long +1, below -1), the RSI (under 30 +1, over 70 -1),
the MACD histogram (above 0 +1, below 0 -1) and the Bollinger bands (close
below the lower band +1, above the upper band -1). The file name without
`.csv` is the symbol. Files that cannot be read are listed as skipped, with
the reason, and do not stop the scan.

```bash
python -m trading_assistant --scan prices/                         # the table
python -m trading_assistant --scan prices/ --min-score 1 --top 10  # scores of 1 or more, best 10
python -m trading_assistant --scan prices/ --json                  # one JSON object instead
python -m trading_assistant --scan prices/ --report scan.md        # also write a Markdown report
```

| Option | Effect |
| --- | --- |
| `--short`, `--long`, `--rsi-period` | the crossover windows and RSI period (defaults 20, 50, 14) |
| `--min-score N` | keep only files scoring `N` or more |
| `--top N` | keep the first `N` rows after that |
| `--json` | print one JSON object (counts, results with the four parts, skipped files) and nothing else |
| `--report FILE` | also write a Markdown report: date, settings, the table, one sentence per row on why it scored what it did, the skipped files |

`--scan` cannot be combined with a price file or with `--backtest` and its
options. `top` and `min_score` can also come from the `--config` file. The
full rules, the JSON keys and the exit codes are in
[docs/cli.md](docs/cli.md#python--m-trading_assistant---scan-folder-options).

## Weekly and monthly bars

With a `date` column (`YYYY-MM-DD`, oldest first) you can reduce daily bars to
the last close of each ISO week or calendar month before the analysis and the
backtest:

```bash
python -m trading_assistant prices.csv --resample weekly
```

## Strategies

`--backtest` trades one of seven rules. `--strategy NAME` picks it (default
`sma_cross`) and `--param KEY=VALUE` (repeatable, numbers only) changes a
parameter. Both need `--backtest`, and they change only the backtest: the top
`Signal:` line is always the SMA crossover signal from `--short`/`--long`.
The portfolio command takes them too; see
[Portfolio with a strategy](#portfolio-with-a-strategy). The walk-forward
test takes `--strategy`, `--param` for one fixed value and `--grid` for a
list of values to try; see
[Walk-forward with a strategy](#walk-forward-with-a-strategy).

| Strategy | Parameters (defaults) | BUY | SELL |
| --- | --- | --- | --- |
| `sma_cross` | `short=20`, `long=50` | short SMA crosses above long SMA | short SMA crosses below long SMA |
| `rsi_reversion` | `period=14`, `oversold=30`, `overbought=70` | RSI crosses up through `oversold` | RSI crosses down through `overbought` |
| `breakout` | `window=20` | close is above the highest of the previous `window` closes | close is below the lowest of the previous `window` closes |
| `ema_cross` | `short=12`, `long=26` | short EMA crosses above long EMA | short EMA crosses below long EMA |
| `momentum` | `window=20`, `threshold=0.0` | rate of change crosses up through `threshold` | rate of change crosses down through `threshold` |
| `zscore_reversion` | `window=20`, `entry=-2.0`, `exit=0.0` | z-score crosses up through `entry` | z-score crosses up through `exit` |
| `hull_trend` | `window=20` | Hull moving average turns up | Hull moving average turns down |

```bash
python -m trading_assistant prices.csv --backtest --short 5 --long 10
python -m trading_assistant prices.csv --backtest --strategy rsi_reversion --param period=5 --param oversold=35
python -m trading_assistant prices.csv --backtest --strategy breakout --param window=10
```

For `sma_cross` the windows come from `--short`/`--long`; `--param short=...`
and `--param long=...` also work, but giving both `--short` and a different
`--param short=` (or the same for `long`) is a usage error (exit code 2), as
are a malformed `--param`, a key the strategy does not have, or a value it
rejects (for example a window below 1).

## Fills, slippage, sizing, stops, targets, trailing stops and risk sizing

These backtest options make the simulation closer to real trading. All need
`--backtest`; the full rules are in
[docs/cli.md](docs/cli.md#fills-slippage-and-position-size).

| Option | Effect |
| --- | --- |
| `--fill open` | fill a signal at the next bar's open instead of its close (reads a candle file) |
| `--slippage PCT` | buys fill `PCT` % higher, sells `PCT` % lower, before fees |
| `--position-size FRACTION` | each buy spends at most this fraction of the account (e.g. `0.5`) |
| `--stop-loss PCT` | sell when the price falls `PCT` % below the entry price; above 0 and below 100 (reads a candle file) |
| `--take-profit PCT` | sell when the price rises `PCT` % above the entry price; above 0 (reads a candle file) |
| `--trailing-stop PCT` | sell when the price falls `PCT` % below the highest high since entry; above 0 and below 100 (reads a candle file) |
| `--risk-pct PCT` | size each buy so that `PCT` % of the account is "at risk" over an ATR-based distance; above 0, at most 100 (reads a candle file). **Only sets the number of shares; it places no stop itself** (`--atr-stop` does) |
| `--atr-mult N` | with `--risk-pct` and/or `--atr-stop`: the distance is `N` times the ATR; above 0 (default 2) |
| `--atr-period N` | with `--risk-pct` and/or `--atr-stop`: the ATR's number of bars; a whole number of at least 1 (default 14) |
| `--atr-stop` | sell when a bar's low reaches the entry price less `--atr-mult` x ATR, the ATR taken on the buy's signal bar and fixed per position (reads a candle file). Config key `atr_stop = yes`, `"atr_stop": true` in `POST /api/backtest`, the **ATR stop** box on the web page |
| `--cooldown N` | after a sell by `--stop-loss`, `--trailing-stop`, `--atr-stop` or `--breakeven`, no buy can fill for the next `N` bars; a buy due then is dropped (not delayed) and counted. A whole number of at least 1; needs one of those stops. Config key `cooldown`, `"cooldown"` in `POST /api/backtest`, the **Cooldown (bars)** field on the web page |
| `--min-hold N` | a signal sell due before the position has been held `N` bars (counted from the buy that opened it; a later buy does not restart the count) is dropped, not delayed, and counted; stops, targets, `--max-hold` and `--max-drawdown` still sell inside the window. A whole number of at least 1 (`1` skips nothing); needs no stop and works on a close-only file and with `--resample`. `--json` shows `min_hold_bars` and `min_hold_skipped_sells`. Config key `min_hold`, `"min_hold"` in `POST /api/backtest`, the **Min hold (bars)** field on the web page |
| `--max-hold N` | sell the whole position `N` bars after the buy that opened it, at that bar's fill price; the fills say `time`. A whole number of at least 1; needs no stop and works on a close-only file and with `--resample`. Config key `max_hold`, `"max_hold"` in `POST /api/backtest`, the **Max hold (bars)** field on the web page |
| `--max-drawdown PCT` | when the account value at a close is `PCT` % or more below its highest value at a close so far, halt: sell the position on the next bar (the fill says `drawdown` unless another sale takes that bar) and let no buy fill for the rest of the run; each buy dropped that way is counted. Above 0 and below 100, decimals allowed; needs no stop and works on a close-only file and with `--resample`. Config key `max_drawdown`, `"max_drawdown"` in `POST /api/backtest`, the **Max drawdown (%)** field on the web page |
| `--breakeven PCT` | once the high of a bar after the entry bar is `PCT` % or more above the entry price, move a stop up to the entry price: a later bar whose low reaches it sells the position there (at the open on a gap); the fills say `breakeven`. Above 0, decimals allowed, no upper limit, but not `inf` (exit 2) (reads a candle file). It counts as a stop for `--cooldown`. At or above `--take-profit` it is allowed but can never act (the target sells first), except after a later buy into the position: a lower-priced one with close fills, or any one with `--fill open` (see [docs/cli.md](docs/cli.md#breakeven-stop)). `--json` shows `breakeven_pct` and `breakeven_exits`. Config key `breakeven`, `"breakeven"` in `POST /api/backtest` (neither takes `inf` either), the **Breakeven (%)** field on the web page |
| `--max-losses N` | after `N` losing round trips in a row (profit after costs below 0, whatever sold them), no buy can fill for the rest of the run; each buy dropped that way is counted. Any round trip that did not lose, one at exactly 0.00 included, resets the count. Nothing is held when it triggers, so nothing is sold because of it. A whole number of at least 1; needs no stop and works on a close-only file and with `--resample`. `--json` shows `max_losses`, `loss_halt_bar` and `loss_skipped_buys`. Config key `max_losses`, `"max_losses"` in `POST /api/backtest`, the **Max losses** field on the web page |
| `--scale-out PCT` | once per position, when the high of a bar after the entry bar reaches the entry price (the average cost of the shares held) plus `PCT` %, sell half the shares held (rounded down) at that price (at the open on a gap); the rest stays open, and the fills say `scale_out`. The partial sale is not a round trip: its proceeds count in the round trip the rest completes. Any other fill on the bar goes first. Above 0, decimals allowed, no upper limit, but not `inf` (exit 2) (reads a candle file); needs no other exit. `--json` shows `scale_out_pct` and `scale_out_exits`. Config key `scale_out`, `"scale_out"` in `POST /api/backtest`, the **Scale out (%)** field on the web page |
| `--add-on PCT` | while a position is held, when a close is `PCT` % or more above the fill price of the latest buy into it (the price the fill records, slippage included), buy more on the next bar, sized like any buy (so with the default all-cash sizing it usually gets 0 shares: use `--position-size` or `--risk-pct`); the fills say `add_on`. Any other fill on that bar, or a BUY or SELL signal on the close that set it off, drops it. Above 0, decimals allowed, not `inf` (exit 2); needs no stop and works on a close-only file and with `--resample`. `--json` shows `add_on_pct`, `max_adds`, `add_on_buys` and `add_on_skipped_buys`. Config key `add_on`, `"add_on"` in `POST /api/backtest`, the **Add-on (%)** field on the web page |
| `--max-adds N` | with `--add-on`: the most add-on buys per position (default 1); a whole number of at least 1, and without `--add-on` a usage error. Config key `max_adds`, `"max_adds"` in `POST /api/backtest`, the **Max adds** field on the web page |

```bash
python -m trading_assistant.samples random_walk candles.csv --candles
python -m trading_assistant candles.csv --backtest --fill open --slippage 0.1 --stop-loss 5 --take-profit 10
python -m trading_assistant candles.csv --backtest --trailing-stop 8
python -m trading_assistant candles.csv --backtest --risk-pct 1 --atr-mult 2 --atr-period 14
python -m trading_assistant candles.csv --backtest --stop-loss 5 --cooldown 10
python -m trading_assistant prices.csv --backtest --min-hold 5
python -m trading_assistant prices.csv --backtest --max-hold 20
python -m trading_assistant prices.csv --backtest --max-drawdown 15
python -m trading_assistant candles.csv --backtest --breakeven 5
python -m trading_assistant prices.csv --backtest --max-losses 3
python -m trading_assistant candles.csv --backtest --scale-out 5
python -m trading_assistant prices.csv --backtest --position-size 0.5 --add-on 10 --max-adds 2
```

**Candle data.** `--fill open`, `--stop-loss`, `--take-profit`,
`--trailing-stop`, `--risk-pct`, `--atr-stop`, `--breakeven` and `--scale-out` read the price file as a candle file
(`date,open,high,low,close,volume`, every row checked); a close-only file is
a data error (exit 1). None of them can be combined with `--resample` yet
(usage error, exit 2). Their config-file keys (`fill = open`, `stop_loss`,
`take_profit`, `trailing_stop`, `risk_pct`, `atr_stop = yes`, `breakeven`, `scale_out`) follow the same rules, and on the
web page and API they need candle data too (a built-in sample, or a pasted
candle CSV). `--cooldown` needs one of the stops (`--breakeven` counts) and reads the file through it.
`--min-hold`, `--max-hold`, `--max-drawdown`, `--max-losses`, `--add-on` and `--max-adds` need no candle data: they work on a
close-only file, with `--resample`, and on the web page and API with a
close-only CSV. So do `--trade-list` (see [Trade list](#trade-list)) and
`--explain` (see [Explain the signal](#explain-the-signal)).

**Gaps.** A stop or target fills at its level when a bar only *touches* it
during the bar. But when a bar *opens* beyond the level (an overnight gap), it
fills at that bar's **open**, because a real order would fill near the open,
not at a price the market jumped over. A gap down through a stop is therefore
a worse fill than the stop level, and a gap up through a target a better one.
If one bar touches both levels without a gap, the stop wins. For example,
with an entry at 13 and a 10 % stop (level 11.70), a bar that opens at 9 sells
at 9.00, while a bar that opens at 12 and dips to 11 sells at 11.70. Each fill
in the report says why it happened: `signal`, `stop`, `target`, `trail`, `atr`, `breakeven`, `time`, `drawdown` or `scale_out`, and
`add_on` for an add-on buy.

**Trailing stop.** `--trailing-stop PCT` follows the price up: its level is
the highest high since entry less `PCT` %. The highest high starts at the
entry price (the average price paid) and then takes in the highs of the bars
after the entry bar, up to the bar before the one being checked: a bar's own
high is never used, because it is not known whether its high or its low came
first. When a bar's low reaches the level the whole position is sold at the
level, or at the bar's open when it opens at or below the level (a gap, as
above). Each new position starts a new highest high. Slippage and fees apply
as for every sell. With the 8-bar candle file from
[docs/cli.md](docs/cli.md#trailing-stop), `--short 1 --long 2 --cash 500`
buys 45 shares at 11; after bar 5's high of 13 the level is 13 x 0.9 =
11.70, bar 6 dips to 10 and the position is sold at 11.70 (end equity
531.50), where `--stop-loss 10` would have held on until bar 7 gapped down
and sold at its open, 9.00 (end equity 410.00).

**Breakeven.** `--breakeven PCT` moves a stop up to the entry price once the
trade has gone `PCT` % in your favour. When a bar is over, its high is compared
with the entry price (the average price paid) plus `PCT` %; at or above it, the
stop is armed until the position is sold. The entry bar's own high never
counts (with either `--fill`), and the bar that arms it is never sold by it.
From the next bar on, a bar whose low reaches the entry price sells the whole
position there, or at its open when it opens at or below it (a gap). The level
is exactly the entry price, so slippage and fees still make such a sale a
small loss. A later buy into the position moves the level with the average
price: an armed stop stays armed, an unarmed one measures `PCT` from the new
average. With the 11-bar candle file from
[docs/cli.md](docs/cli.md#breakeven-stop), `--short 1 --long 2 --cash 1000`
buys 90 at 11 on bar 4; bar 5's high of 12 arms `--breakeven 5` (11.55), and
bar 6 dips to 9.50, so the position is sold at 11.00 (`breakeven`); the
bar 9 buy takes 83 at 12 and the run ends at 1,016.60, where without the option
the SELL signal sells at 10.00 on bar 7 and the run ends at 925.00.
`--breakeven 10` (12.10) is never armed there. With `--take-profit` at or below
`PCT` it is allowed but can never act, because the bar that would arm it has
reached the target, which sells first; the only exception is a later buy into
the position (a lower-priced one with close fills, any one with `--fill open`).
It counts as a stop for `--cooldown`.

**Scale out.** `--scale-out PCT` takes half of a winning position off once
and lets the rest run. On a bar after the entry bar whose high reaches the
entry price plus `PCT` %, half the shares held (rounded down) are sold at
that price, or at the bar's open when it opens at or above it (a gap); the
fill says `scale_out`. It happens at most once per position: a later buy into
the position cannot make it scale out again, the next position can. With 1
share there is nothing to sell, and the position can still scale out after a
later buy. The rest is sold by whatever would have sold it. The entry price
is the average cost of the shares still held, so the partial sale moves no
stop, target or breakeven level, and a later buy averages with the shares
still held. A bar has one fill, and any other fill on it goes first: a target
or stop the bar also reaches, or the strategy's signal, takes the bar and the
scale-out is skipped. With close fills a `--max-hold` or `--max-drawdown`
sale due on a bar the scale-out takes waits for the next bar; with
`--fill open` those sales happen at the open and come first. The partial sale
is not a round trip: its proceeds count in the round trip the rest completes,
so the win rate and `--max-losses` see that round trip with all its sales.
It starts no cooldown, `--min-hold` does not hold it back, and it needs no
other exit. The report adds a line after `Exits:` (or where it would be),
only with the option:

    Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the average entry; 1 partial sell, not counted as round trips

With the 11-bar candle file from [docs/cli.md](docs/cli.md#scale-out),
`--short 1 --long 2 --cash 1000` buys 90 at 11 on bar 4; bar 5's high of 12
reaches `--scale-out 5` (11.55), so 45 are sold at 11.55, and the SELL signal
sells the other 45 at 10.00 on bar 7: one round trip of -20.25, then 81
bought at 12 on bar 9, and the run ends at 995.95 (925.00 without the
option). `--scale-out 9` sells 45 at 11.99 and ends at 1,016.15;
`--scale-out 10` (12.10) is never reached; with `--stop-loss 10` the stop
stays at 9.90 and sells the other 45 on bar 6 (991.45). With `--take-profit`
at or below `PCT` it is allowed but never acts, because the target sells
everything first.

**Several exits together.** The stop, the trailing stop, the ATR stop and the
breakeven stop are all levels below the price; a falling price meets the
highest one first, so the highest of those in use is used (on a tie the stop,
then the trail, then the ATR stop, then breakeven). When a bar touches the target and one of them, that stop wins. The report's `Exits:` line says
which exits are on and, when there are several, which wins.

**Cooldown.** `--cooldown N` stops the strategy from buying straight back in
after a stop. When `--stop-loss`, `--trailing-stop`, `--atr-stop` or
`--breakeven` sells on bar `t`, no buy can fill on bars `t + 1` to `t + N`. A `--take-profit` sell or
a sell on the strategy's own signal starts no cooldown. A buy due in the
cooldown is **dropped, not delayed**: a crossover strategy (`sma_cross`,
`ema_cross`, ...) signals BUY only on the bar it crosses, so if that bar's buy
falls in the cooldown the strategy stays out until its next crossing, however
long after the cooldown that is; a strategy that keeps signalling (such as
`breakout`) buys again as soon as a BUY is due after the cooldown. A BUY
signal on the exit bar's own close is due on the next bar, so it is the first
one dropped. A buy that was due on the exit bar itself is not a cooldown skip:
with close fills the exit comes first and cancels it, and with `--fill open`
it fills at the open, so no exit (and no cooldown) happens on that bar. The
report adds a line after `Exits:`, only with the option, counting every buy
that was due in a cooldown (even one that would have got 0 shares; it is then
not also counted as a risk sizing skip; a BUY signal on the last bar never
fills and is never counted):

    Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped

With the 11-bar candle file from [docs/cli.md](docs/cli.md#cooldown),
`--short 1 --long 2 --cash 1000 --stop-loss 10` buys 90 at 11, is stopped out
on bar 6 at 9.90 and buys 75 at 12 on bar 9 (end equity 916.00). With
`--cooldown 3` (bars 7 to 9 blocked) the bar 9 buy is dropped and, with no later
crossing, the run ends in cash at 901.00; with `--cooldown 2` it is the same as
without. `N` is a whole number of at least 1 (`0` or `1.5` is exit 2), and
`--cooldown` without a stop is the usage error
`--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop`
(`--breakeven` also counts as a stop, although the message does not name it).
In a config file, `cooldown` is used only when a stop is on (from the file or
the command line) and is otherwise ignored; a value below 1 is an error either
way. `--export` has no cooldown column.

**Min hold.** `--min-hold N` keeps the strategy from selling too soon: bought
on bar `e`, a signal sell due on a bar before `e + N` is skipped. The count
starts at the buy that opened the position; a later buy does not restart it.
A skipped sell is dropped, not delayed: a crossover strategy then holds until
its next SELL signal or another exit. Only the strategy's own sells are held
back; stops, targets, `--max-hold` and `--max-drawdown` still sell inside the
window. A sell is counted only when it would otherwise have filled: with
close fills a stop or target that sells during the bar leaves nothing to
skip, while with `--fill open` the signal comes first at the open, so it is
counted even if a stop sells later in that bar; a sell the fees would have
refused is counted too. A skipped sell leaves its bar free, so after a
drawdown halt the drawdown sale can sell there instead, with the reason
`drawdown` where it would have been `signal`. The report adds a line (only
with the option):

    Min hold:    4 bars after a position's first buy before a signal sell can fill; 1 signal sell skipped

With the closes of the 11-bar file from [docs/cli.md](docs/cli.md#min-hold)
(`--short 1 --long 2 --cash 1000`, end equity 925.00 without the option), the
signal sell is due on bar 7, 3 bars after the buy on bar 4: `--min-hold 3`
(or `1`) changes nothing, `--min-hold 4` skips that sell and holds the 90
shares to the end (1,108.00), and `--min-hold 4 --max-hold 2` lets the time
exit sell on bar 6 (925.00, nothing skipped). `N` is a whole number of at
least 1 (`0` or `1.5` is exit 2). It makes no fills of its own, so `--export`
gets no `reason` column from it. The sweep, walk-forward, portfolio and Monte
Carlo tools do not take it.

**Max hold.** `--max-hold N` sells the whole position `N` bars after the buy
that opened it: bought on bar `e`, it is sold on bar `e + N` at that bar's
fill price (its close, or its open with `--fill open`), so it is held exactly
`N` bars. A later buy into the position does not restart the count. A bar
that already has a fill keeps it (a signal buy or sell, a stop, trail, ATR
stop, breakeven or target sale, or with close fills a `--scale-out` partial
sale) and the time exit waits for the next bar; with
`--fill open` a gap through a stop or target at the open also comes first,
but one reached only later in the bar does not. The fills say `time`, a time
exit starts no cooldown, and the report adds a line (only with the option):

    Max hold:    1 bar after a position's first buy, then sold at the bar's fill price; 2 time exits

With the closes of the 11-bar file from [docs/cli.md](docs/cli.md#max-hold)
(`--short 1 --long 2 --cash 1000`, end equity 925.00 without the option),
`--max-hold 1` sells on bars 5 (12.00) and 10 (12.20) and ends at 1,108.00;
`--max-hold 2` sells on bar 6 (10.00) and ends at 925.00; with
`--max-hold 3` the exit would be due on bar 7, where the signal sells anyway,
so the run is the same as without. `N` is a whole number of at least 1 (`0`
or `1.5` is exit 2). It needs no stop, works on a close-only file and with
`--resample` (`N` then counts the resampled bars). With it, `--export` gets
the `reason` column.

**Max drawdown.** `--max-drawdown PCT` stops a run that has lost too much.
After every bar the account value at the close (cash plus the shares at the
close, after that bar's fill and its costs) is compared with the highest such
value so far, the first bar's included. When it is `PCT` % or more below that
peak, the run halts for good (the check stops once it has triggered):

- From the next bar to the end no buy can fill. Each buy due then is dropped
  and counted, even one that would have got 0 shares; it is then not also
  counted as a cooldown or risk sizing skip. A BUY signal on the last bar has
  no bar to fill on and is not counted.
- A position still held is sold whole on the next bar at that bar's fill
  price (its close, or its open with `--fill open`), with slippage and fees,
  and the fill says `drawdown`. Another sale on that bar goes first and keeps
  its own reason: a stop, trailing stop, ATR stop, breakeven stop or target reached during
  the bar (close fills) or gapped through at the open (open fills), the
  strategy's own SELL, or a `--max-hold` sale (a SELL that `--min-hold`
  skips makes no fill, so the drawdown sale takes the bar). With `--fill open` the sale is
  at the open, so a stop reached only later in that bar does not beat it. A
  sale the fees would refuse is tried again on each later bar.
- It starts no cooldown: the halt already blocks every later buy, so a
  cooldown would change nothing. A buy that also falls in a cooldown from an
  earlier stop is counted once, as a drawdown skip.

The drawdown is measured exactly like the report's `Max drawdown` and the
export's `drawdown_pct` column (account value at the closes; a bar's low is
not used), and the run is the same as without the option up to the bar that
sets off the halt. So a run halts exactly when, without the option, its
`Max drawdown` would reach `PCT` %. The report adds a line before
`Round trips:`, only with the option:

    Drawdown:    halt at 16.00% below the peak account value at a close; triggered at bar 6, no buy fills after it; 1 buy skipped

With the closes of the 11-bar file from [docs/cli.md](docs/cli.md#max-drawdown)
(`--short 1 --long 2 --cash 1000`, end equity 925.00 without the option) the
account value peaks at 1,090.00 on bar 5 and is 910.00 on bar 6, 16.51 %
below. `--max-drawdown 16` halts on bar 6: the SELL signal of bar 6 sells on
bar 7 (its reason stays `signal`) and the BUY due on bar 9 is skipped, so the
run ends in cash at 910.00. `--max-drawdown 17` never halts and the run is the
same as without. A case where the drawdown itself sells is in
[docs/cli.md](docs/cli.md#max-drawdown). `PCT` is above 0 and below 100,
decimals allowed (`0`, `100` or a value that is not a number is exit 2). It
needs no stop, works on a close-only file and with `--resample`, and with it
`--export` gets the `reason` column; there is no column for the halt itself.
The report's `Max drawdown` row and `max_drawdown_pct` in `--json` are the
drawdown the run actually had, so the limit is called
`max_drawdown_limit_pct` in `--json`.

**Max losses.** `--max-losses N` stops buying after `N` losing round trips in
a row. A round trip (the buys that open a position and the sale that closes
it) loses when its profit after costs is below 0, whatever sold it: the
strategy, a stop, target, trailing stop, ATR stop, breakeven stop, a
`--max-hold` sale or a `--max-drawdown` sale. Any round trip that did not lose
resets the count, a win and also one at exactly 0.00; costs count, so one
that sells at its buying price but pays a fee is a loss. A sale the fees
refuse completes no round trip and does not count. When the count reaches
`N` with a sale on bar `h`, no buy can fill from bar `h + 1` to the end; each
buy due then is dropped and counted (a buy the drawdown halt also blocks is
counted there only). Every round trip ends with the whole position sold (a
`--scale-out` partial sale completes none and does not count), so nothing is
held then and nothing is sold because of it. The report adds a line before
`Round trips:` (after `Drawdown:`), only with the option:

    Max losses:  halt after 2 losing round trips in a row; triggered at bar 13, no buy fills after it; 1 buy skipped

That is `losses.csv` from [docs/cli.md](docs/cli.md#max-losses) (17 closes:
10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13) with
`--short 1 --long 2 --cash 1000`: without the option it loses 180.00 (bar 7)
and 82.00 (bar 13), buys again on bar 15 and ends at 799.00. `--max-losses 1`
halts on bar 7 and skips 2 buys (820.00), `--max-losses 2` halts on bar 13
and skips 1 (738.00), and `--max-losses 3` never halts (799.00). `N` is a
whole number of at least 1 (`0`, `2.5` or a word is exit 2). It needs no
stop, works on a close-only file and with `--resample`, and adds no fill
reason, so `--export` keeps its columns.

**Add-ons.** `--add-on PCT` buys more of a position that is going your way.
While shares are held, a close `PCT` % or more above the fill price of the
latest buy into the position (the price the fill records, so slippage
included) sets off an add-on, which fills on the next bar at that bar's fill
price (its close, or its open with `--fill open`), up to `--max-adds N`
times per position (default 1). Every buy into the position is the new
latest buy, a signal BUY too, but only add-ons count towards `N`. It is sized
like any buy, so with the default all-cash sizing the first buy spends the
cash and an add-on gets 0 shares: it is then counted as skipped, is not one
of the `N` and leaves the latest buy price as it was. It raises the average
entry price (the stop, target, breakeven, ATR stop and scale-out levels
follow it), its shares and cost go into the same round trip, and it restarts
neither `--min-hold` nor `--max-hold`. It is dropped, not delayed and not
counted, when the close that set it off is a BUY or SELL signal (a SELL also
when `--min-hold` holds the sale back), and when anything else fills on its
bar first: with close fills a stop or target reached during the bar, a
scale-out, a time exit or a drawdown sale; with `--fill open` a gap through a
stop or the target, a time exit or a drawdown sale at the open. Things to
know:

- The level is compared in floating point: after a buy at 11, `--add-on 10`
  needs a close above 12.10, and a close of exactly 12.10 does not set it
  off (11 x 1.1 is 12.100000000000001).
- It fills at the next bar's price, which can be below the level, and it can
  be bought on the same close that gives the strategy's SELL, one bar before
  the sale.
- With `--fill open` it fills at the open, and a bar has one fill, so no
  stop, target or scale-out acts on the bar it fills on, even if that bar's
  low goes through the stop. That flatters the result: in real trading the
  stop would have sold that bar.

The report adds a line after `Scale out:` (or where it would be), only with
the option:

    Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)

That is `up.csv` from [docs/cli.md](docs/cli.md#add-ons) (closes 10, 9, 8, 9,
11, 12, 13, 14, 15, 14, 13, 12) with `--short 1 --long 2 --cash 1000
--position-size 0.5 --add-on 10`: 45 bought at 11 on bar 4, bar 6's close
of 13 is above 12.10, so 36 more are bought at 14 on bar 7, and the SELL
sells all 81 at 13 on bar 10: 1,054.00 (1,090.00 without the option).
`--add-on 20` buys 33 at 15 on bar 8 (1,024.00), `--add-on 50` never buys
(1,090.00), and `--add-on 10` without `--position-size` skips 3 add-ons for
want of cash and ends at 1,180.00, as without the option. `PCT` is above 0
and not `inf`, `N` a whole number of at least 1 (exit 2 otherwise, and
`--max-adds` without `--add-on`). They need no stop, work on a close-only file
and with `--resample`, and with them `--export` gets the `reason` column.

**Risk sizing.** `--risk-pct PCT` changes only how many shares a buy gets:

    shares = (PCT % of the account value at the fill) / (atr_mult x ATR), rounded down

The ATR is Wilder's average true range over `--atr-period` bars (default 14)
taken on the bar the buy signal came on, never on the bar the buy fills on;
`--atr-mult` defaults to 2. The account value is the cash plus the shares
held, valued at the fill bar's price. The share count is then capped by the
cash, and by `--position-size` if given (the smaller size wins). **Risk sizing
places no stop itself**: without `--atr-stop` the `atr_mult x ATR` distance is
only used for the arithmetic and nothing sells at it. With `--atr-stop` the ATR
stop sells at the distance of the buy that opened the position. Either way a
position can lose more than `PCT` % of the account: without the ATR stop
because nothing sells at the distance, with it through a gap, slippage, fees
or a later buy into the position (sized on its own signal bar's ATR while the
stop keeps the first buy's distance). Use `--stop-loss`, `--trailing-stop` or
`--atr-stop` for an exit; risk sizing works next to them and to
`--take-profit`. A buy that risk sizing gives 0 shares (the ATR does not
exist yet on the signal bar, which is the case for the first
`atr_period - 1` bars, or it is 0, or the risk is less than one share) is
skipped, and the report counts it on a `Skipped:` line; a buy skipped only
for lack of cash or by `--position-size` is not counted. With the 8-bar
candle file from [docs/cli.md](docs/cli.md#risk-sizing), `--short 1 --long 2
--cash 1000 --risk-pct 2 --atr-mult 2 --atr-period 3` buys 7 shares at 11
(ATR 1.39 on the signal bar, distance 2.78, 20 / 2.78 = 7.2) instead of 90,
and sells them at 8: a loss of 21.00, or 2.10 % of the account, more than the
2 % "at risk". The report shows

    Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) (this only sets the number of shares; no stop is placed)

Not checked or not included: fees and slippage are not part of the risk
amount; the ATR is worked out from the file's highs, lows and closes as they
are (the candle file check is the only check on them); `--atr-mult inf` is
accepted by the command and skips every buy (the config file and the web API
refuse it); a huge `--atr-period` simply means no buy is ever sized. The
buy-and-hold comparison stays all-in, and the sweep, walk-forward, portfolio
and Monte Carlo tools do not take risk sizing.

**Buy and hold pays the same.** The "Buy & hold" comparison buys on the first
bar at that bar's fill price (its open with `--fill open`, its close
otherwise) plus the same `--slippage`, with the same fees, so it is not
flattered next to a strategy that pays for them. It is always all-in: position
size, stops and targets do not apply to it. With close fills and no slippage
it is the plain buy at the first close.

## JSON output

Add `--json` to get the same information as one JSON object on stdout, and
nothing else, for scripts:

```bash
python -m trading_assistant candles.csv --backtest --stop-loss 5 --stats --json
```

The object has `bars`, `last_close`, `signal` and `rsi`; with `--backtest` a
`backtest` object with the strategy and settings, every fill (with its
`reason`), the final and return figures and a `benchmark` (buy and hold)
object; with `--stats` the statistics. `stop_loss_pct` and `take_profit_pct`
are always there (`null` when off); `trailing_stop_pct` is there only when
`--trailing-stop` is given, right after `take_profit_pct`, so the JSON of a
run without it is unchanged. Likewise `risk_pct` (right after `position_size`)
is there only with `--risk-pct`; `atr_mult` and `atr_period` (right after
`risk_pct`, or `position_size`; defaults filled in) and `risk_skipped_buys`
(right after `sells`) with `--risk-pct` or `--atr-stop`; and `atr_stop`
(`true`, right after `trailing_stop_pct` or `take_profit_pct`) only with
`--atr-stop`; and `cooldown_bars` (right after the exit settings) and
`cooldown_skipped_buys` (right after `sells`, or `risk_skipped_buys`) only with
`--cooldown`; and `min_hold_bars` (right before `max_hold_bars`, or where it
would be) and `min_hold_skipped_sells` (right before `time_exits`, or where it
would be) only with `--min-hold`; and `max_hold_bars` (right after the exit settings,
`cooldown_bars` and `min_hold_bars`) and `time_exits` (right after the skipped counts) only
with `--max-hold`; and `max_drawdown_limit_pct` (right after `max_hold_bars`,
or the exit settings), `drawdown_halt_bar` (`null` when the halt never
triggered) and `drawdown_skipped_buys` (right after `time_exits`, or the other
counts) only with `--max-drawdown`; and `breakeven_pct` (right after the
other exit settings, before `cooldown_bars`) and `breakeven_exits` (how many
sells it made, right after `sells` or `risk_skipped_buys`) only with
`--breakeven`; and `max_losses` (right after `max_drawdown_limit_pct`, or
where it would be), `loss_halt_bar` (`null` when the halt never triggered)
and `loss_skipped_buys` (right after `drawdown_skipped_buys`, or where it
would be, just before `fills`) only with `--max-losses`; and `scale_out_pct` (right after
`breakeven_pct`, or the other exit settings) and `scale_out_exits` (how many partial
sells it made, right after `breakeven_exits`, or `risk_skipped_buys` or `sells`) only with
`--scale-out`; and `add_on_pct` and `max_adds` (right after `scale_out_pct`, or the other exit
settings) and `add_on_buys` and `add_on_skipped_buys` (right after `scale_out_exits`, or where it
would be) only with `--add-on`; and `trade_list` (the trade list's rows, the last key) only with
`--trade-list`. With `--explain` the object also has `explanation` (the
sentence) right after `signal`. Numbers are plain, unrounded JSON
numbers and `null` stands for `n/a`. The text report and the JSON come from the
same analysis call. Errors stay as they are (a message on stderr, exit 1 or
2). See [docs/cli.md](docs/cli.md#json-output---json).

## Risk and return statistics

Add `--stats` to `--backtest` to print a "Risk and return" block after the
report. It is opt-in so the default report stays identical to the web page's
text report. The web page always shows it as a table. All numbers use the
strategy's account value, one value per bar, 252 bars per year, and a
risk-free rate of 0.

| Number | Meaning |
| --- | --- |
| Total return | change from the first to the last account value |
| CAGR | compound annual growth rate, using (bars - 1) / 252 years |
| Volatility (ann.) | sample standard deviation of per-bar returns times sqrt(252) |
| Sharpe ratio | mean per-bar return over their standard deviation, times sqrt(252) |
| Sortino ratio | like Sharpe, but divided by the downside deviation (only falling bars count) |
| Exposure | percent of bars on which shares were held |
| Profit factor | gross profit over gross loss across completed round trips |
| Average win / loss | mean profit (loss) of the winning (losing) round trips, after costs |
| Longest drawdown | most consecutive bars spent below the previous peak |

A number that cannot be defined prints as `n/a` (`null` in `--json` and in the web JSON):
anything needing returns when there are fewer than 3 bars; Sharpe when the
account value never changes; Sortino when no bar fell; profit factor when
there is no losing round trip; average win or loss when there are no winning
or losing round trips; Longest drawdown with fewer than 2 bars.

## Trade list

Add `--trade-list` to `--backtest` to see the round trips behind the
`Round trips:` line. After the report (after the "Risk and return" block with
`--stats`, before `--chart`) it prints one row per completed round trip and,
when shares are still held at the end, one more row for that position. With
the 11-bar candle file from [docs/cli.md](docs/cli.md#trade-list):

```text
$ python -m trading_assistant c.csv --backtest --short 1 --long 2 --cash 1000 --trade-list
...
Trade list (bar index is 0-based)
  #     Entry  Exit  Bars   Shares        Outlay      Proceeds          P/L    Return  Reason
  1         4     7     3       90        990.00        900.00       -90.00    -9.09%  signal
  open      9  open     1       75        900.00        915.00       +15.00    +1.67%  -  (unrealized: marked at the last close, no selling costs)
  1 completed, 0 made money (0%), 1 open (unrealized)
```

- Only completed round trips are rows, so their number and their wins are
  exactly the `Round trips:` line's, which the footer repeats. A
  `--scale-out` partial sale is not a row: its proceeds are in its round
  trip's.
- `Shares` is every share bought into the position, `Outlay` the cash spent
  on the buys and `Proceeds` the cash from the sales, fees included; `Return`
  is the P/L divided by the outlay. `Reason` is why the sale that completed
  the round trip happened (`signal`, `stop`, `time`, ...), shown even when no
  exit option is on.
- The `open` row is unrealized: the shares still held are marked at the last
  close with no selling costs, as `End equity:` is. Its reason is
  `scale_out` if part of it was sold, `-` otherwise.
- A run with no trades prints `Trade list: no trades`. Without the option
  nothing changes.

It needs no candle file and works with `--resample`. `--json` gets a
`trade_list` array with the same rows, the config file key is
`trade_list = yes`, `POST /api/backtest` takes `"trade_list": true`, and the
web page has a **Trade list** box. See [docs/cli.md](docs/cli.md#trade-list).

## Parameter sweep

Backtest many SMA window pairs at once and compare them with buy and hold:

```bash
python -m trading_assistant.sweep prices.csv --short 3,5,10 --long 10,20,30 --top 5
```

Pairs where short is not below long are skipped. `--csv OUT` writes every row.
The best result on the data you tuned on is flattering; check it on data it was
not chosen on.

## Walk-forward test

The sweep picks its best pair and reports it on the same data. Walk-forward
instead splits the prices into rolling windows: in each one the best SMA pair
(or, with `--strategy`, the best parameter set of another strategy; see
[Walk-forward with a strategy](#walk-forward-with-a-strategy)) is picked on
the **train** bars only, then run on the **test** bars right after them,
which the choice never saw. Then both blocks move on by `--step`.

```bash
python -m trading_assistant.samples random_walk prices.csv
python -m trading_assistant.walkforward prices.csv --short 5,10 --long 20,40 --train 250 --test 120
```

```
Walk-forward: 4 windows; each SMA crossover pair was chosen on its train bars only, then run on the test bars after them
Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades
     1       0-249     250-369   10/40   -12.79%    +2.37%    -6.66%      2
     2     120-369     370-489   10/40   -10.46%    +0.00%   +29.04%      0
     3     240-489     490-609   10/40   +30.47%    +1.73%    -6.89%      3
     4     360-609     610-729   10/20   +24.22%   +11.82%   -19.45%      2
Test return, compounded over the windows: +16.44%
Buy & hold, compounded over the windows:  -9.66%
Mean test return per window: +3.98%
Windows beating buy & hold: 3 of 4
Windows without test trades: 1 of 4
Note: 1 of 4 windows made no trades in the test block (no crossover, or fewer than long + 2 test bars to warm up); their 0.00% says nothing about the pair.
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice.
```

| Option | Effect |
| --- | --- |
| `--short LIST`, `--long LIST` | required without `--strategy`: the window lists, as for the sweep |
| `--train N`, `--test N` | required: bars in each train and test block |
| `--step N` | bars each window moves on (default: `--test`) |
| `--cash`, `--fee`, `--fee-pct` | as for the sweep (default 10,000, 0, 0) |
| `--warmup` | warm the moving averages up on the chosen pair's `long` bars before each test block (a switch, off by default) |
| `--json` | one JSON object instead: `windows`, `summary`, `overfit_warning`, `disclaimer` (with `--warmup`, `"warmup": true` first) |
| `--csv OUT` | also write one row per window to `OUT` |
| `--strategy NAME`, `--grid KEY=LIST`, `--param KEY=VALUE` | walk forward another strategy over a grid of its parameters (see [below](#walk-forward-with-a-strategy)) |

**Reading it.** Only the Test column is out of sample; Train is the in-sample
return the pair was picked on, and the "best" pair can still have lost there
(window 1). Buy & hold is buying on the first test bar and holding to the last.
Bar ranges include both ends. Each test block starts with fresh cash and no
position, and without `--warmup` its moving averages warm up inside the block:
a block shorter than `long + 2` bars cannot trade, and the note says so. With `--short 5,10,20
--long 20,50,100 --train 250 --test 60` (the web panel's defaults) the same
file gives `Windows without test trades: 7 of 8`. The compounded figures only
mean something when the test blocks follow each other exactly (`--step` equal
to `--test`); otherwise a second note says they overlap or leave gaps. Ties on
train return are settled by the sweep's own order, never by the test bars. A
few windows on one series prove little either way.

**`--warmup`.** With it the pair is still chosen on the train bars only, but
each test run first warms its moving averages up on the chosen pair's `long`
bars just before the test block, so a short test block can trade too. It still
starts flat with fresh cash on the first test bar, a crossover on the bar
before the block is not acted on, and every figure is measured on the test
block alone (buy & hold does not change). Near the start of the data, when
fewer than `long` bars come before a test block (which needs `--train`
smaller than `long`), it uses whatever bars there are, back to bar 0. The header line and
the no-trades note say so; the first lines of the output:

```bash
python -m trading_assistant.walkforward tests/data/wf.csv --short 1 --long 3 --train 12 --test 4 --cash 1000 --warmup
```

```
Walk-forward: 1 window; each SMA crossover pair was chosen on its train bars only, then traded and scored on the test bars after them, with its moving averages warmed up on up to long bars just before each test block
Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades
     1        0-11       12-15     1/3    +0.00%    +7.60%   +40.00%      1
```

Without `--warmup` the same 4-bar test block cannot trade (`+0.00%`, 0 trades).
`--json` gets `"warmup": true` as its first key (only with `--warmup`). The
`--csv` file has the same columns and one row per window either way (only
the numbers differ), so **it cannot show that warm-up was on**: keep the command with the file. The full outputs, a
table of small runs and the exact rules are in
[docs/cli.md](docs/cli.md#--warmup).

Exit codes: 0 success; 1 data problem, for example
`Error: not enough prices for a walk-forward window: 750 bars, need at least train + test = 820`,
`Error: --csv refuses to overwrite the input file prices.csv` or
`Error: cannot write nodir/w.csv: No such file or directory`; 2 usage problem,
for example `--test must be at least 1`, no pair with short < long, or a value
after `--warmup` (`--warmup 5`).

The web page has a **"Walk-forward test"** panel with the same settings (its
**"Warm up"** box is `--warmup`) and the same table, summary and notes, and
`POST /api/walkforward` (which takes `"warmup": true` too) replies with
exactly the `--json` object; see
[docs/cli.md](docs/cli.md#python--m-trading_assistantwalkforward-pricescsv-options).

### Walk-forward with a strategy

`--strategy NAME` walks forward any of the seven [strategies](#strategies)
instead of SMA pairs. `--grid KEY=LIST` (repeatable) gives the values of one
parameter to try, and every combination of the lists is backtested on each
train block; `--param KEY=VALUE` (repeatable) fixes a parameter to one value;
the others keep their defaults. The best set (highest train return, then
smaller train drawdown, then smaller parameter values in the strategy's own
order) is run on the test block, exactly as the pairs are. On 20 closes
(`tests/data/wf20.csv`: 10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 13, 12,
11, 13, 16, 17, 15, 14, 16):

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

- Each list is tried once per distinct value, in any order (`0,0.0` is one
  value); **one bad value in a list is a usage error** (exit 2), while a set
  that only breaks a rule between two parameters (`short < long`) is
  skipped. `--param` takes one number: a list is refused.
- `--short` and `--long` cannot be combined with `--strategy`, `--grid` or
  `--param` (`sma_cross`'s windows are then `--grid short=... --grid long=...`).
- `--warmup` warms each test run up on the bars its chosen set needs to
  signal on the first test bar.
- The text has a **Params** column instead of **Pair** (whole values as
  whole numbers: `entry=-2`), `--json` starts with `"strategy"` and each
  window has a `params` object, and `--csv` has one `param_KEY` column per
  parameter. Without the three options every output is exactly as before.
- `--st` still means `--step`; `--g`, `--p` and `--str` now mean `--grid`,
  `--param` and `--strategy`.
- On the web page the panel's **Strategy** dropdown does the same, and
  `POST /api/walkforward` takes `strategy`, `grid` and `params`, with at most
  10,000 parameter sets and the work held to 300,000 bar-steps, weighted by
  each strategy's measured cost.

The hand-worked example, the output rules, every error, the API fields and
the work weights are in
[docs/cli.md](docs/cli.md#strategies-in-the-walk-forward---strategy---grid---param).

## Portfolio backtest

Run the SMA crossover (or, with `--strategy`, any of the seven
[strategies](#strategies)) on several symbols at once, each `.csv` file directly
inside a folder being one symbol (the file name without `.csv`). The files
are lined up on the dates **every** file has: a date missing from one file is
dropped for all of them, and nothing is filled in. The cash is split equally
between the symbols, or by `--weights`, and the portfolio's account value on
each shared date is the sum of the symbols' account values.

```bash
mkdir pf
python -m trading_assistant.samples uptrend pf/uptrend.csv
python -m trading_assistant.samples downtrend pf/downtrend.csv
python -m trading_assistant.samples sideways pf/sideways.csv
python -m trading_assistant.portfolio pf
```

```
Portfolio: 3 symbols, cash split equally, SMA 20/50 crossover, fee 0.00 + 0.00%, on the dates every file shares
Dates: 2023-01-02 to 2023-07-28 (150 shared dates)
Cash: 10,000.00  Final equity: 10,848.47
Return: +8.48%  Max drawdown: -2.19%  Buy & hold (equal weight): +4.31%
Symbol     Bars used  Bars lost   Return  Trades  Buy&Hold
downtrend        150         50   +0.00%       0   -21.28%
sideways         150          0   -6.43%       6    +3.40%
uptrend          150         50  +31.89%       1   +30.80%
Worst single-symbol drawdown: -8.63% (sideways)
Note: dates not shared by every file were dropped (see Bars lost); nothing was filled in.
Research aid only. Not financial advice.
```

| Option | Effect |
| --- | --- |
| `--short N`, `--long N` | the SMA windows (defaults 20, 50); `sma_cross` only |
| `--strategy NAME` | the rule every symbol trades (default `sma_cross`); see [Portfolio with a strategy](#portfolio-with-a-strategy) |
| `--param KEY=VALUE` | change one of the strategy's parameters; numbers only; repeatable |
| `--cash AMOUNT`, `--fee AMOUNT`, `--fee-pct PCT` | starting cash for the whole portfolio and the costs (defaults 10,000, 0, 0) |
| `--weights SYMBOL=PCT ...` | split the cash by these percentages instead of equally, e.g. `--weights uptrend=50 downtrend=30 sideways=20`: one per file used, each above 0, adding up to exactly 100 |
| `--json` | one JSON object instead: `summary`, `skipped`, `disclaimer` (and `title` first, with a strategy other than `sma_cross`) |
| `--csv OUT` | also write one row per shared date: date, portfolio equity, each symbol's equity |

The drawdown is that of the summed account value, never an average of the
symbols'. Files without a `date` column, with no rows, with a bad number or a
close that is not positive are skipped with a reason and the rest carry on;
at least 2 usable files are needed, and enough shared dates for the
strategy's first signal plus one to fill it (`long + 2` for the SMA
crossover). The portfolio is long only and has no stops, targets, trailing
stop, slippage, position size or risk sizing. The web page's **"Portfolio
backtest"** panel and `POST /api/portfolio` run the same code on files you
pick; see
[docs/cli.md](docs/cli.md#python--m-trading_assistantportfolio-folder-options).

### Portfolio with a strategy

`--strategy NAME` trades one of the seven rules of [Strategies](#strategies)
on every symbol, and `--param KEY=VALUE` (repeatable, numbers only) changes
one of its parameters, with the main command's meaning, checks and messages.
The shared dates, the cash split (equal or `--weights`), the costs and the
buy-and-hold comparison stay as they are; only the rule each symbol trades
changes.

Two files on the same 10 dates, 2026-04-01 to 2026-04-10:

```bash
mkdir ab
python -c "
for name, closes in (('AAA', [10, 11, 12, 13, 12, 11, 10, 11, 13, 14]), ('BBB', [20, 19, 18, 19, 21, 22, 21, 19, 18, 20])):
    open(f'ab/{name}.csv', 'w').write('date,close\n' + ''.join(f'2026-04-{i + 1:02d},{c}\n' for i, c in enumerate(closes)))
"
python -m trading_assistant.portfolio ab --strategy breakout --param window=3 --cash 1000
```

```
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

Each symbol gets 500. AAA buys 41 at 12.00 on bar 4, sells them at 10.00 on
bar 6 and buys 29 at 14.00 on bar 9 (ending at 418.00); BBB buys 22 at 22.00
on bar 5 and sells them at 18.00 on bar 8 (412.00). These are the fills of
`python -m trading_assistant ab/AAA.csv --backtest --strategy breakout --param window=3 --cash 500`
(and the same for `ab/BBB.csv`). The summed account value is 1,000 on bars
0-4, then 959, 896, 852, 830 and 830, so the drawdown is
(830 - 1,000) / 1,000 = -17.00%. With `--weights AAA=60 BBB=40` it ends at
828.00 (-17.20%), against +24.00% for buy and hold with the same weights;
with the SMA crossover (`--short 2 --long 3`) it ends at 912.00 (-8.80%).

- Without `--strategy`, or with `--strategy sma_cross`, every output (text,
  `--json`, `--csv`, errors) is exactly as before; only `--help` changes. `--param` on its own adjusts `sma_cross`:
  `--param short=2 --param long=3`, with or without `--strategy sma_cross`,
  prints exactly what `--short 2 --long 3` prints.
- `--short` or `--long` with another strategy is a usage error (exit 2):
  `--short only applies to --strategy sma_cross; set breakout's parameters with --param`.
  So are a `--param short=` that contradicts `--short` (or the same for
  `long`), a malformed `--param`, a key the strategy does not have and a
  value it refuses, with the main command's messages (for example
  `window must be a whole number of at least 1, got 0`).
- The title line names the strategy and all its parameters, defaults
  included: `--strategy momentum --param window=3` gives
  `momentum (window=3, threshold=0.0)`. `--json` then starts with a `title`
  key holding that line, and its `summary` has `strategy` and `params`
  instead of `short` and `long`. `--csv` is unchanged.
- Too few shared dates (exit 1) names the strategy's real minimum, for
  example `only 10 dates shared by all 2 symbols; need at least 11 for breakout (window=9): 10 for its first signal + 1 to fill it`.
  The minimums are `long + 2` for `sma_cross` and `ema_cross`, `window + 2`
  for `breakout` and `zscore_reversion`, `period + 3` for `rsi_reversion`,
  `window + 3` for `momentum` and `window + isqrt(window) + 2` (the whole
  square root) for `hull_trend`: with the defaults 52, 28, 22, 22, 17, 23 and 26.
- `--help` lists both options; the usage line does not, so it and every
  usage error print as before. `--s` still means `--short`; `--st` to
  `--strategy` and `--p` to `--param`, which were unrecognized before, now
  mean the new options.
- The web page's **"Portfolio backtest"** panel has a **Strategy** dropdown,
  and `POST /api/portfolio` takes `strategy` and `params` (a list of
  `"KEY=VALUE"` strings, like `weights`); see
  [docs/cli.md](docs/cli.md#strategies-in-the-portfolio---strategy---param).

## Web page

To run backtests in your browser instead of the terminal:

```bash
python -m trading_assistant.web        # or: scripts/web.sh
```

Then open the address it prints (normally http://localhost:8765/; if that
port is busy it moves to the next free one and says so, or pass `--port N`).
Press Ctrl+C to stop. The page only listens on your own machine, loads
nothing from the internet, and needs no extra packages.

On the page you can pick one of the built-in seeded sample series (steady up
trend, down trend, choppy sideways, long realistic random walk), or paste or
upload your own CSV, set the SMA windows, starting cash, trading costs,
slippage, position size, fill price, stop loss, take profit, trailing
stop, breakeven, scale-out, risk sizing (Risk % per buy, ATR multiplier, ATR period), the ATR stop, the cooldown, the maximum holding time, the maximum drawdown and the add-ons, and run
without a page reload. You get a price chart with buy/sell markers, an
account-value chart against buy & hold, summary numbers, a trade table (with
the reason for each fill) and a CSV download.

- A strategy picker lists all seven strategies; picking one other than
  `sma_cross` shows its parameters. A "Risk and return" table sits under the
  summary.
- **Position size is a percentage of the account** on the page (`50` is half;
  blank is all-in).
- Fill price, stop loss, take profit, trailing stop, breakeven, the scale-out,
  risk sizing, the ATR stop and the cooldown need candle data. Every sample has it; for your own CSV they are
  **greyed out until the pasted header has `open`, `high` and `low` columns**
  (a full candle file: `date,open,high,low,close,volume`); the ATR stop box is
  then unticked too (the close-only hint ends "The scale-out needs them too."). An empty stop, target, trailing stop, **Breakeven (%)**
  (after the trailing stop), **Scale out (%)** (after Breakeven) or Risk % is not used; the ATR multiplier and period count when Risk % has a value or the
  **ATR stop** box is ticked (empty means 2 and 14). An empty **Cooldown
  (bars)** field is not sent at all.
- The **Max losses** field sits after the cooldown, then the **Min hold
  (bars)** field, the **Max hold (bars)** field and the **Max drawdown (%)**
  field. They need no candle data, so they are never greyed out, also for a
  close-only CSV; empty, they are not sent at all.
- The **Add-on (%)** and **Max adds** fields sit after **Max drawdown (%)**.
  They need no candle data either, so they are never greyed out; each is sent
  only when filled in (a Max adds without an Add-on is sent anyway, and the
  server's message is shown).
- Risk sizing shows in the text report (the `Risk sizing:` line, and a
  `Skipped:` line when buys were skipped). With Risk % or the ATR stop, the
  **Trades** card also says how many buys were skipped (`..., 1 skipped`);
  with a cooldown it adds the buys the cooldown dropped
  (`..., 1 skipped by cooldown`), with a minimum holding time the signal
  sells it skipped (`..., 1 signal sells skipped by min hold`), with a
  maximum holding time the time
  exits (`..., 2 sold by max hold`), and with a maximum drawdown the buys the
  halt dropped (`..., 1 skipped by drawdown`). With a breakeven stop it adds
  its sales (`..., 1 sold at breakeven`), right after the risk sizing count,
  and with a scale-out its partial sales (`..., 1 partial sells by scale-out`),
  right after that.
  With a losing-streak halt it adds, last, the buys that halt dropped
  (`..., 2 buys skipped by losing streak`). With add-ons it adds the add-on
  buys and the add-ons that got 0 shares, right after the scale-out count
  (`..., 1 add-on buys, 0 add-ons skipped`).
- The trades table shows why each fill happened (`signal`, `stop`, `target`,
  `trail`, `atr`, `breakeven`, `time`, `drawdown` or `scale_out`, and `add_on`
  for an add-on buy). The **Exits** summary card lists only the stop loss and take
  profit: a trailing stop, the ATR stop, the breakeven stop, the scale-out, the maximum holding time or the
  maximum drawdown does not show on that card (they do show in the trades
  table and in the text report's `Exits:`, `Scale out:`, `Max hold:` and `Drawdown:` lines).
- The **Trade list** box sits right after the **ATR stop** box. Ticked, the
  results get a **Trade list** table (the text report's rows and footer, the
  open row marked unrealized); unticked, the page sends exactly the request it
  sent before and shows nothing extra. It needs no candle data, so it is
  never greyed out.
- The **Explain signal** box sits right after the **Trade list** box. Ticked,
  the sentence of `--explain` appears once, right under the `Signal:` line of
  the text report panel (the report is the command's `--backtest --explain`
  output); unticked, the page sends exactly the request it sent before and
  shows nothing extra. It needs no candle data, so it is never greyed out.
- A rejected request shows the server's one-line message in the error box.
- A **"Scan several files"** panel does what `--scan` does for files you pick:
  choose several `.csv` files, set the minimum score, the rows to keep and the
  windows, and see the ranked table with the four parts and the skipped files
  with their reasons. The files go to the local server only and are not saved.
- A **"Walk-forward test"** panel and a **"Portfolio backtest"** panel do what
  the walk-forward and portfolio commands do (see above). The walk-forward
  panel's **Warm up** box, its last setting, is `--warmup`. Ticked, the results
  get the command's `--warmup` header line above the windows and its warm-up
  no-trades note; unticked, the panel sends exactly the request it sent before
  and shows nothing extra.
- The walk-forward panel's **Strategy** dropdown is `--strategy`. With
  `sma_cross` the panel sends exactly the request it sent before; another
  strategy hides the two window lists and shows one text field per
  parameter, holding its default: a comma list is tried as a `--grid`, one
  changed value is a `--param`. The results then have a **Params** column,
  written as the command writes it.
- The portfolio panel's **Strategy** dropdown (the same list as the backtest
  panel's) is `--strategy`. With `sma_cross` the panel is as before and sends
  exactly the request it sent before; another strategy hides **Short SMA**
  and **Long SMA** and shows one field per parameter, holding its default.
  Only parameters that are filled in and differ from the default are sent,
  so the title reads as the command's without `--param`. The title line is
  then the one in the reply, word for word the command's.

The page computes nothing itself, and the numbers are exactly those of the
command line. The same sample can be written out for the CLI with

```bash
python -m trading_assistant.samples random_walk candles.csv --candles
python -m trading_assistant.cli candles.csv --backtest --fill open --stop-loss 5
```

The page talks to a small JSON API, `POST /api/backtest`, `POST /api/scan`
(whose reply is exactly the `--scan --json` object), `POST /api/walkforward`
(whose reply is exactly the walk-forward `--json` object) and
`POST /api/portfolio` (whose reply is exactly the portfolio `--json` object),
which you can also call yourself; all four are described in
[docs/cli.md](docs/cli.md#post-apibacktest).

## More tools

Each is a module command with the same exit codes as the main CLI (0 ok, 1 data
problem, 2 usage problem). Run any of them with `--help` for every option.

| Command | What it does | Docs |
| --- | --- | --- |
| `python -m trading_assistant.summary prices.csv` | rows, date range, price range, biggest moves, volatility | [docs/cli.md](docs/cli.md) |
| `python -m trading_assistant.drawdowns prices.csv --top 5` | deepest drawdowns with peak, trough and recovery dates | [docs/analysis.md](docs/analysis.md) |
| `python -m trading_assistant.montecarlo prices.csv --seed 7` | seeded bootstrap of the strategy's daily returns | [docs/analysis.md](docs/analysis.md) |
| `python -m trading_assistant.alerts rules.txt prices.csv` | checks price and indicator rules such as `rsi(14) < 30` on the last bar | [docs/alerts.md](docs/alerts.md) |
| `python -m trading_assistant.journal trades.csv summary` | paper-trade journal with FIFO profit and loss | [docs/journal.md](docs/journal.md) |

The main command also takes `--chart` (a text chart of closes, with fills
marked in `--backtest` mode) and `--config FILE` (defaults from an INI file,
including `slippage`, `position_size`, `fill`, `stop_loss`, `take_profit`,
`trailing_stop`, `risk_pct`, `atr_mult` and `atr_period`, and `top` and
`min_score` for `--scan`; flags on the command line win over the file); see [docs/cli.md](docs/cli.md). All indicators are listed in
[docs/indicators.md](docs/indicators.md), and how the pieces fit together is in
[docs/architecture.md](docs/architecture.md).

## Test

```bash
python -m pytest -q        # or: scripts/run_tests.sh
```

Besides unit tests with hand-worked numbers, `tests/test_paths_agree.py`
checks that the three ways to run a backtest agree: command-line flags, a
config file and the web API are run on the same candle files and settings
(every strategy, and every setting except the trailing stop, risk sizing, the ATR stop, the cooldown, the minimum and maximum holding times, the maximum drawdown, the breakeven stop, the losing-streak halt, the scale-out, the add-ons and the trade list) and must give the
same fills, final equity, buy-and-hold equity and statistics, with the web
report equal to the command line's report line for line. Changing one path
without the others fails it. The trailing stop has its own checks:
`tests/test_config_trailing_stop.py` (a config file gives the same output as
the flag), `tests/test_web_trailing_stop.py` (the API's numbers equal the
command's `--json`) and `tests/test_web_trailing_stop_page.py` (the page).
Risk sizing is checked the same way: `tests/test_atr.py`,
`tests/test_risk_sizing.py`, `tests/test_risk_sizing_report.py`,
`tests/test_cli_risk_sizing.py`, `tests/test_cli_risk_json.py`,
`tests/test_config_risk_sizing.py`, `tests/test_web_risk_sizing.py` and
`tests/test_web_risk_sizing_page.py`. The cooldown too: `tests/test_cooldown.py`
(the engine, hand-worked), `tests/test_cli_cooldown.py`,
`tests/test_cli_cooldown_unchanged.py`, `tests/test_cli_cooldown_json.py`,
`tests/test_config_cooldown.py`, `tests/test_web_cooldown.py` and
`tests/test_web_cooldown_page.py`. The maximum holding time too:
`tests/test_max_hold.py` (the engine and report, hand-worked),
`tests/test_cli_max_hold.py` (the command, `--json` and `--export`),
`tests/test_config_max_hold.py`, `tests/test_web_max_hold.py` (the API
against the command) and `tests/test_web_max_hold_page.py` (the page).
The maximum drawdown too: `tests/test_max_drawdown.py` (the engine and
report, hand-worked), `tests/test_cli_max_drawdown.py` (the command,
`--json`, `--export`, `--help` and every short option name),
`tests/test_config_max_drawdown.py`, `tests/test_web_max_drawdown.py` (the
API against the command) and `tests/test_web_max_drawdown_page.py` (the page).
The breakeven stop too: `tests/test_breakeven.py` (the engine and report,
hand-worked on `tests/data/c.csv`), `tests/test_cli_breakeven.py` (the
command, `--json`, the config key, `--help` and the `--b` alias),
`tests/test_web_breakeven.py` (the API against the command) and
`tests/test_web_breakeven_page.py` (the page).
The minimum holding time too: `tests/test_min_hold.py` (the engine and
report, hand-worked, with `tests/data/c_before_min_hold.json`, the 0.13.0
output of twelve runs without it), `tests/test_cli_min_hold.py` (the command,
`--json`, `--export`, `--help` and the `--mi`/`--min`/`--min-` aliases),
`tests/test_config_min_hold.py`, `tests/test_web_min_hold.py` (the API
against the command) and `tests/test_web_min_hold_page.py` (the page).
The losing-streak halt too: `tests/test_max_losses.py` (the engine and
report, hand-worked, with `tests/data/c_before_max_losses.json`, the 0.14.0
output of nine runs without it), `tests/test_cli_max_losses.py` (the command,
`--json`, `--export`, `--help`, the short option names, and
`tests/data/cli_before_max_losses.json`, nine 0.14.0 commands),
`tests/test_config_max_losses.py` (with `tests/data/config_before_max_losses.json`,
eight 0.14.0 config runs), `tests/test_web_max_losses.py` (the API against
the command) and `tests/test_web_max_losses_page.py` (the page).
The scale-out too: `tests/test_scale_out.py` (the engine and report,
hand-worked on `tests/data/c.csv`, with `tests/data/before_scale_out.json`,
the 0.15.0 output of 26 runs without it), `tests/test_cli_scale_out.py` (the
command, `--help`, every short option name, with
`tests/data/cli_before_scale_out.json`, 26 0.15.0 commands),
`tests/test_cli_scale_out_json.py` (`--json`), `tests/test_config_scale_out.py`,
`tests/test_web_scale_out.py` (the API against the command) and
`tests/test_web_scale_out_page.py` (the page).
The trade list too: `tests/test_trade_list.py` (the rows and the table,
hand-worked on `tests/data/c.csv`, and every row checked against the round
trips of 123 runs), `tests/test_cli_trade_list.py` (the command, `--json`,
`--help`, every short option name, with
`tests/data/cli_before_trade_list.json`, the output of 37 commands before the
option existed: 28 that must not change and 9 that now mean `--trade-list`), `tests/test_config_trade_list.py`,
`tests/test_web_trade_list.py` (the API against the command) and
`tests/test_web_trade_list_page.py` (the page).
The signal explanation too: `tests/test_explain_crossover.py` (the sentence,
hand-worked on `tests/data/c.csv`, and thousands of random series whose first
word must be `crossover_signal`'s), `tests/test_cli_explain.py` (the command,
`--json`, `--scan`, `--help` and the `--e`/`--ex`/`--exp` aliases),
`tests/test_config_explain.py`, `tests/test_web_explain.py` (the API against
the command, with the hashes of replies without it) and
`tests/test_web_explain_page.py` (the page).
The add-ons too: `tests/test_add_on.py` (the engine and report, hand-worked,
with `tests/data/before_add_on.json`, 36 runs recorded before the option
existed), `tests/test_cli_add_on.py` (the command, `--help`, every short
option name, with `tests/data/cli_before_add_on.json`, the commands and
shortened forms recorded before it existed), `tests/test_cli_add_on_json.py`
(`--json`), `tests/test_config_add_on.py`, `tests/test_web_add_on.py` (the API
against the command, with the hashes of replies without it) and
`tests/test_web_add_on_page.py` (the page).
The portfolio strategies too: `tests/test_portfolio_strategy.py` (the
engine, hand-worked on the AAA and BBB files above, every strategy's minimum
checked by brute force against its own function, and 13 runs recorded before
the option existed in `tests/data/portfolio_before_strategy.json`),
`tests/test_portfolio_strategy_cli.py` (the command, `--json`, `--help`, its
errors against the main command's, and every shortened option name, with
`tests/data/portfolio_cli_before_strategy.json`),
`tests/test_web_portfolio_strategy.py` (the API against the command, with 16
replies recorded before it took `strategy`) and
`tests/test_web_portfolio_strategy_page.py` (the panel, run in Node, with the
requests it sent before in
`tests/data/portfolio_page_requests_before_strategy.json`).
The walk-forward strategies too: `tests/test_walkforward_strategy.py` (the
engine, hand-worked on `tests/data/wf.csv`, every strategy against its own
sweep and backtest on each slice), `tests/test_walkforward_strategy_cli.py`
(the command, hand-worked on `tests/data/wf.csv`, `--json`, `--csv`, every usage error and every shortened option name, with
`tests/data/wf_cli_before_strategy.json`, the commands and prefixes recorded
before the options existed), `tests/test_web_walkforward_strategy.py` (the
API against the command, its limits and the work count, with
`tests/data/wf_api_before_strategy.json`, replies recorded before),
`tests/test_web_walkforward_strategy_page.py` (the panel, run in Node, with
`tests/data/wf_page_requests_before_strategy.json`, the requests it sent
before) and `tests/test_walkforward_strategy_docs.py` (the examples and
tables of these docs against real output and the code).
`tests/test_scan_agreement.py` does the same for `--scan`: four sets of files
and seven setting combinations through the table, `--json`, a config file and
`POST /api/scan` must give the same counts, ranking, scores, parts and skipped
files.

## Layout

```
src/trading_assistant/
  indicators.py   SMA, EMA, RSI, WMA, DEMA, TEMA, Hull, ROC, momentum,
                  rolling std, z-score, CMO, TRIX, KAMA, regression slope,
                  MACD, Bollinger bands, ATR
  signals.py      SMA crossover signal and its explanation, RSI label,
                  combined score
  scan.py         score a folder of price files (--scan), JSON and report
  strategies.py   strategy registry (seven strategies)
  backtest.py     backtest engine, costs, stops, targets, trailing stop,
                  risk sizing, ATR stop, cooldown, min and max hold, drawdown
                  and losing-streak halts, scale-out, add-ons, buy-and-hold
                  comparison, report, trade list and export
  account.py      the backtest's account: cash and a whole-share position
  data.py         reading close-only and candle CSV files
  metrics.py      risk and return statistics
  rolling.py      rolling return, volatility, Sharpe, drawdown
  drawdowns.py    drawdown periods (python -m trading_assistant.drawdowns)
  montecarlo.py   bootstrap of returns (python -m trading_assistant.montecarlo)
  sweep.py        parameter sweep (python -m trading_assistant.sweep)
  walkforward.py  walk-forward test (python -m trading_assistant.walkforward)
  portfolio.py    several symbols on shared dates
                  (python -m trading_assistant.portfolio)
  resample.py     weekly and monthly bars
  summary.py      data summary (python -m trading_assistant.summary)
  alerts.py       rule alerts (python -m trading_assistant.alerts)
  journal.py      paper-trade journal (python -m trading_assistant.journal)
  config.py       INI defaults for --config
  textchart.py    text chart for --chart
  samples.py      built-in seeded sample series
  cli.py          command line entry point
  __main__.py     python -m trading_assistant
  web/            local browser page
docs/             CLI reference, indicators, analysis, alerts, journal, architecture
tests/            pytest suite
```

## Notes

- No live order placement. Any future broker integration must be read-only until it has been reviewed.
