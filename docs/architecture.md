# Architecture

A small research tool: it reads prices, computes indicators and signals, and
simulates trading on paper. It never places orders. Standard library only.

## Modules (`src/trading_assistant/`)

- `indicators.py`: SMA, EMA, RSI, ATR and the other indicators in [indicators.md](indicators.md).
- `signals.py`: SMA crossover signal, its one-sentence explanation (`explain_crossover` for the text and `--json`, `explain_crossover_data` for the API: the decision, the sentence and the two SMAs on the last two bars, from one computation that calls `crossover_signal` itself), the RSI label and the combined score.
- `scan.py`: `--scan` (score a folder, or files held in memory for the web), its table, JSON and Markdown report.
- `strategies.py`: registry of the seven strategies; parameter defaults and validation; `first_signal_bars`, the fewest closes with which each strategy can signal (the portfolio's not-enough-dates rule, and the walk-forward's warm-up: `first_signal_bars - 1` bars); `check_param_value`, the checks that need one value only (for parameter grids).
- `data.py`: reading close-only CSV and strict candle CSV.
- `backtest.py`: simulation engine (fills, costs, slippage, position size, ATR risk sizing, stops, targets, the trailing stop, the ATR stop, the breakeven stop, the cooldown after a stop, the minimum and maximum holding times, the drawdown halt, the losing-streak halt, the scale-out and the add-ons; `warmup_closes`, bars before the first one that only feed the signal), buy-and-hold benchmark, report text, the trade list (`trade_list` rows and the `format_trade_list` table, built from the result's round trips and fills after the run), per-bar CSV export.
- `account.py`: the backtest's account (its class is called `Portfolio`): cash plus a whole-share long position in one instrument, with the fee rules. Not to be confused with `portfolio.py`.
- `metrics.py`: risk and return statistics (CAGR, volatility, Sharpe, Sortino, exposure, ...).
- `resample.py`: reduce daily bars to weekly or monthly bars.
- `sweep.py`: backtest many SMA window pairs (`python -m trading_assistant.sweep`); `grid_combinations` (every parameter set of a strategy's grid: each value checked on its own, equal values once, sets that break a rule between two parameters skipped, an optional `max_combinations` raising `GridTooLarge`) and `sweep_grid` (backtest each set, best first: return, then smaller drawdown, then smaller parameter values in registry order), used by the walk-forward.
- `walkforward.py`: pick the best SMA pair on each train block and test it on the bars after it (`python -m trading_assistant.walkforward`). With `--warmup` (`warmup=True`) the pair is still picked on the train bars only, and each test run gets the chosen pair's `long` bars before its block as `run_backtest`'s `warmup_closes`, so its moving averages are warmed up while it still trades and is scored on the test bars only. With `--strategy NAME`, `--grid KEY=LIST` and `--param KEY=VALUE` (`walk_forward(..., strategy=, grid=, params=)`) each window chooses among `sweep.grid_combinations` with `sweep.sweep_grid` instead, warms up on `first_signal_bars - 1` bars, and the rows have a `params` object; `check_strategy_options` (shared with the web server as `parse_strategy_options` plus `grid_combinations`) holds the command's checks and messages, and `format_walk_forward`, `json_data` and `write_csv` take `strategy` for the Params column, the `strategy` key and the `param_KEY` columns.
- `portfolio.py`: several symbols on the dates they all share, the cash split equally or by weights, one `run_backtest` per symbol with the chosen strategy (`--strategy`/`--param`, checked by `check_strategy` with the main command's messages) and the summed account value (`python -m trading_assistant.portfolio`); also runs `POST /api/portfolio` on files held in memory.
- `samples.py`: built-in seeded price series.
- `config.py`: reading and type-checking the `--config` INI file.
- `cli.py`: argument parsing, applying the config file, report assembly (`summarise`, then text or `--json`; `trade_list_data` builds the `trade_list` array that `--json` and `POST /api/backtest` share; `report_lines` puts the `--explain` sentence right after the Signal line when given one, and `analyse` passes it through for the web server), exit codes, and the range checks the web server shares (`check_windows`, `check_costs`, `check_risk`, `check_cooldown`, `check_min_hold`, `check_max_hold`, `check_max_drawdown`, `check_max_losses`, `check_add_on`).
- `__main__.py`: `python -m trading_assistant` as a shorter form of the CLI.
- `web/server.py`: local HTTP server, request validation, JSON replies.
- `web/assets.py`: the page, stylesheet and script as Python strings.

## Data flow

```
settings: flags > config file > defaults      (CLI)
          JSON body, checked by the CLI's rules (web)
CSV (file, upload or sample) -> parse (dates, closes; opens, highs, lows when
  --fill open, a stop, target, trailing, ATR or breakeven stop, the scale-out, or risk sizing needs them:
  candle file or sample candles)
  -> optional resample (weekly / monthly)
  -> cli.summarise: signal + RSI, and with --backtest the simulation
  -> cli.report_lines (text report)  | cli.report_data (--json)
     web reply (report lines + summary, trades, per-bar rows)
```

Every path runs the same `cli.summarise` (the web page through `cli.analyse`,
which is `report_lines(summarise(...))`), so the text report, the `--json`
object and the web reply cannot drift apart. The web page adds the strategy,
its parameters, the statistics and the echoed settings to its JSON; the CLI
prints statistics only with `--stats`. The browser page computes nothing: it
only sends the settings and shows what the server returns.

The trade list (`--trade-list`, the config key `trade_list`, `trade_list` in
`POST /api/backtest` and the page's Trade list box) is built after the run
from `result.round_trips` and `result.trades`: the engine, the report lines
before it, the statistics and the export are not touched by it. Its
completed rows are the round trips themselves, so their count and wins are
those of the `Round trips:` line; a position still held adds one row
rebuilt from the fills after the last round trip's exit bar (one fill per
bar, so none of them belongs to a completed round trip), marked at the last
close. The text table (`format_trade_list`) is appended to the report by the
command line (after `--stats`) and by the web server (the end of `report`);
`cli.trade_list_data` gives the same rows to `--json` and the API reply.

The signal explanation (`--explain`, the config key `explain`, `explain` in
`POST /api/backtest` and the page's Explain signal box) is built from the
closes and windows the `Signal:` line used (`summary["short"]`,
`summary["long"]`, after `--resample`; the API's `short`/`long`), never from
`--strategy`: `signals.explain_crossover` calls `crossover_signal` itself, so
its first word is the Signal line's decision. The command line passes the
sentence to `report_lines` (text) and `report_data` (`--json`, the
`explanation` key after `signal`); the web server passes it to
`cli.analyse`, so its `report` gets the same line from the same code, and
adds the `explanation` object from `explain_crossover_data`. Nothing else is
touched by it: the backtest, the statistics, the export and, without it,
every output.

## Backtest rules

- No look-ahead: the signal for bar `t` uses `closes[0..t]` only.
- Next-bar fills: a signal on bar `t` is executed at the close of bar `t + 1`
  (or its open with `--fill open`); a signal on the last bar is never acted on.
- BUY spends as much cash as whole shares allow (shares and costs must be
  affordable), or at most `--position-size` of the account value; SELL sells
  the whole position. Impossible orders are skipped.
- Slippage moves buys up and sells down by a percentage before fees.
- Risk sizing (`--risk-pct`) sets a buy's share count to `PCT` % of the
  account value at the fill divided by `atr_mult x ATR(atr_period)`, the ATR
  taken on the signal bar (never the fill bar), rounded down and capped by the
  cash and `--position-size`. It places no stop itself (the ATR stop below
  does) and it never limits the loss.
  A buy it gives 0 shares (no ATR yet, an ATR of 0, or risk under one share)
  is skipped and counted in `risk_skipped_buys`. See
  [cli.md](cli.md#risk-sizing).
- Stops and targets are measured from the average entry price. A bar that
  opens at or beyond a level (a gap) fills at its open; a bar that only
  touches a level fills at the level; if a bar touches both the stop wins.
  Without open prices no gap can be seen and the level is used. See
  [cli.md](cli.md#stops-targets-and-gaps).
- The trailing stop's level is the highest high since entry less its
  percentage. The highest high starts at the average entry price and takes in
  the highs of the bars after the entry bar up to the bar before the one being
  checked (never the checked bar's own high); a new position starts a new one.
  Gaps fill at the open as for the stop. With a stop as well, the higher of
  the two levels is used (the stop on a tie), and either wins over the target
  on a bar that touches both. See [cli.md](cli.md#trailing-stop).
- The ATR stop (`run_backtest(..., atr_stop=True)`; `--atr-stop`, the config
  key `atr_stop`, `atr_stop` in `POST /api/backtest` and the page's ATR stop
  box) sells when a bar's low reaches the average entry price less
  `atr_mult x ATR(atr_period)`. The
  ATR is taken on the signal bar of the buy that opens the position and the
  distance is kept for the whole position, so a later buy moves the level with
  the average price only. A buy with no usable ATR is skipped and counted in
  `risk_skipped_buys`. Gaps fill at the open; of the stop, trail and ATR
  levels the highest is used (on a tie stop, then trail, then atr), and it
  wins over the target. Fills say `atr`. With `--risk-pct` the buy that opens
  a position is sized on the same distance; a later buy is sized on its own
  signal bar's ATR while the stop keeps the first distance, so the position
  can lose more than the risks added up (as a gap, slippage or fees can).
- The breakeven stop (`run_backtest(..., breakeven_pct=PCT)`; `--breakeven
  PCT`, the config key `breakeven`, `breakeven` in `POST /api/backtest` and
  the page's Breakeven field): once the high of a bar after the entry bar is
  `PCT` percent or more above the average entry price (the entry bar's own
  high never counts, and the bar that arms it is never sold by it), later
  bars whose low reaches the entry price sell there (at the open on a gap),
  with no allowance for fees or slippage. A later buy moves the level with
  the average price. It is checked with the other stops (highest level wins;
  on a tie stop, trail, atr, breakeven) and counts as a stop for the
  cooldown. Fills say `breakeven`; `result.breakeven_pct` records `PCT` and
  `result.n_breakeven_exits` counts its sells. See
  [cli.md](cli.md#breakeven-stop).
- The cooldown (`run_backtest(..., cooldown=N)`; `--cooldown N`, the config
  key `cooldown`, `cooldown` in `POST /api/backtest` and the page's Cooldown
  field): after a `stop`, `trail`, `atr` or `breakeven` sell on bar `t`, no buy can fill
  on bars `t + 1` to `t + N`. A `target` or `signal` sell starts none. A buy
  due then is dropped, not delayed (a crossover strategy stays out until its
  next crossing), and counted in `cooldown_skipped_buys`, before any sizing
  rule looks at it, so it is never also a risk sizing skip. A buy due on the
  exit bar itself is not a cooldown skip (close fills: the exit cancels it;
  open fills: it fills at the open and no exit happens on that bar). `0` is
  off in the engine; the command line, config file and API need a whole
  number of at least 1 and a stop. See [cli.md](cli.md#cooldown).
- The minimum holding time (`run_backtest(..., min_hold=N)`; `--min-hold N`,
  the config key `min_hold`, `min_hold` in `POST /api/backtest` and the
  page's Min hold field) is checked in `fill_signal`, on the same clock as
  `max_hold`: a signal sell due on bar `t` with `t - e < N`, `e` being the bar
  of the buy that opened the position (a later buy does not restart it), is
  dropped, not delayed, and counted in `result.min_hold_skipped_sells`. Only
  signal sells go through `fill_signal`, so the stops and target
  (`check_exits`), the time exit and the drawdown sale are untouched and
  still sell inside the window. The check runs only for a sell that would
  otherwise have filled (shares held, `fill_signal` reached on that bar) and
  before the fees are tried, so with close fills a stop or target sale earlier
  in the bar leaves nothing to count, with open fills the signal at the open
  is counted before a stop later in the bar, and a sell the fees would refuse
  is counted too. A skipped sell makes no fill, so the bar is still free for
  the time exit or the drawdown sale (which then records `drawdown` where the
  signal sale would have said `signal`). It needs only the closes. It adds no
  reason: `has_exits` and `has_price_exits` are unchanged by it.
  `result.min_hold` records `N`; both are the last fields of `BacktestResult`
  and `min_hold` the last parameter of `run_backtest` and `cli.summarise`.
  `0` is off in the engine; the command line, config file and API need a
  whole number of at least 1 (`1` skips nothing). See [cli.md](cli.md#min-hold).
- The maximum holding time (`run_backtest(..., max_hold=N)`; `--max-hold N`,
  the config key `max_hold`, `max_hold` in `POST /api/backtest` and the
  page's Max hold field) sells the whole position on bar `e + N`, `e` being
  the bar of the buy that opened it, at that bar's fill price; a later buy
  does not restart the count. It needs only the closes (and the opens for
  open fills), so no stop and no candle file. It never takes a bar that
  already has a fill: with close fills the stops and target, then the signal
  fill, come first; with open fills the signal fill at the open and a gap
  through a stop or target at the open come first. Then it waits for the next
  bar. Fills say `time`; it starts no cooldown. `result.max_hold` records `N`
  and `result.n_time_exits` counts its sells; `has_exits` (the reason column)
  is true with it, `has_price_exits` (the `Exits:` line) only with a stop or
  target. `0` is off in the engine; the command line, config file and API
  need a whole number of at least 1. See [cli.md](cli.md#max-hold).
- The drawdown halt (`run_backtest(..., max_drawdown_limit_pct=PCT)`;
  `--max-drawdown PCT`, the config key `max_drawdown`, `max_drawdown` in
  `POST /api/backtest` and the page's Max drawdown field): after each bar the
  account value at the close is compared with the highest one so far (the
  same numbers as `drawdown_curve_pct`, so the report's `Max drawdown` and the
  export's `drawdown_pct`). When it is `PCT` % or more below, on bar `h`, no
  buy fills from bar `h + 1` on (each one due is counted in
  `drawdown_skipped_buys`, before the cooldown and sizing rules look at it)
  and a position still held is sold on bar `h + 1` at its fill price, after
  any other sale on that bar and in the time exit's order (reason
  `drawdown`). It needs only the closes and starts no cooldown, which could
  not matter anyway once every buy is blocked. `result.max_drawdown_limit_pct`
  records `PCT` and `result.drawdown_halt_bar` the bar `h` (None if it never
  triggered); `has_exits` is true with it. The name avoids
  `result.max_drawdown_pct`, the drawdown the run had. None is off in the
  engine; every path needs a number above 0 and below 100. See
  [cli.md](cli.md#max-drawdown).
- The losing-streak halt (`run_backtest(..., max_losses=N)`; `--max-losses N`,
  the config key `max_losses`, `max_losses` in `POST /api/backtest` and the
  page's Max losses field): `sell_all`, which every sale that closes a position goes through, adds
  one to the streak when the round trip it completes has a profit after costs
  below 0 and sets it back to 0 otherwise (0.00 included). A sale the fees
  refuse completes no round trip and changes nothing. When the streak reaches
  `N` on the sale's bar `h`, no buy fills from bar `h + 1` on: each one due is
  counted in `loss_skipped_buys`, after the drawdown halt (which counts a buy
  it also blocks) and before the cooldown and sizing rules look at it. Every
  round trip ends with the whole position sold (a scale-out's partial sale
  completes none and does not count), so nothing is held then and nothing is
  sold; it adds no fill reason, so `has_exits` and `has_price_exits` do not
  change with it. It needs only the closes. `result.max_losses` records `N`
  and `result.loss_halt_bar` the bar `h` (None if it never triggered). `0` is
  off in the engine; the command line, config file and API need a whole
  number of at least 1. See [cli.md](cli.md#max-losses).
- The scale-out (`run_backtest(..., scale_out_pct=PCT)`; `--scale-out PCT`,
  the config key `scale_out`, `scale_out` in `POST /api/backtest` and the
  page's Scale out (%) field): the engine's `scale_out` step sells half the
  shares held (rounded down) once per position, when the high of a bar after
  the entry bar reaches the entry price plus `PCT` (at the open on a gap), with
  reason `scale_out`. It does not go through `sell_all`: the position stays
  open, its proceeds are added to the open round trip's, and `sell_all` then
  completes that round trip with all its proceeds, so `round_trips`, the win
  rate and the losing streak see one round trip. Each position keeps the
  shares still held and their average cost (`entry`, set on every buy); the
  partial sale leaves the average cost as it is, so the stops, the target,
  the breakeven trigger and the trailing stop's start do not move. A flag
  marks the position once it has scaled out; it goes with the position, when
  the rest is sold. 1 share (half is 0) or a sale the fees refuse leaves it
  unmarked. It is called only when nothing else has filled on the bar: with
  close fills after the bar's range and the signal fill, before the time
  exit and the drawdown sale (which then wait); with open fills after
  everything at the open and the bar's range. It is not a stop (no cooldown)
  and `min_hold` does not hold it back. It needs `highs` and `lows` (and uses
  `opens` for the gap, like the other exits). `result.scale_out_pct` records
  `PCT` and `result.n_scale_out_exits` counts the partial sales; `has_exits`
  is true with it, `has_price_exits` (the `Exits:` line) is not. None is off
  in the engine; every path needs a finite number above 0. See
  [cli.md](cli.md#scale-out).
- The add-ons (`run_backtest(..., add_on_pct=PCT, max_adds=N)`; `--add-on
  PCT` and `--max-adds N`, the config keys `add_on` and `max_adds`, `add_on`
  and `max_adds` in `POST /api/backtest` and the page's Add-on (%) and Max
  adds fields): an add-on is a later buy into the position, so it goes
  through the same two steps as a signal buy: `size_buy` (all the cash,
  `position_size`, or `risk_pct` with the ATR of bar `t - 1`, the bar that
  set it off) and `book_buy` (the account, and the open round trip's shares,
  outlay, cost basis and average `entry`). `book_buy` also keeps, per
  position, the latest buy's fill price (`last_buy`, slippage included, from
  every buy) and the number of add-ons filled (`adds`). At each close, after
  the bar's signal is known, an add-on is set due for the next bar when a
  position is held, fewer than `N` add-ons have filled, the signal is neither
  BUY nor SELL, and the close is at least `last_buy x (1 + PCT / 100)` (in
  floating point: after a buy at 11, `PCT` 10 needs more than 12.10). On the
  next bar the `add_on` step runs only when nothing else has filled: with
  close fills last of all (after the bar's range, the signal fill, the
  scale-out, the time exit and the drawdown sale); with open fills at the
  open, after the signal fill, a gap through a stop or target, the time exit
  and the drawdown sale, and before the bar's range, which then is not
  checked (one fill per bar), so nothing after its fill decides whether it
  was made. Halted by the drawdown, it is counted in `drawdown_skipped_buys`;
  with 0 shares in `add_on_skipped_buys` (not one of the `N`, `last_buy`
  unchanged); otherwise it fills with reason `add_on`. A due add-on that
  another fill beats is simply not tried, and the next close sets one due
  again if it still qualifies. It needs only the closes. `result.add_on_pct`
  and `result.max_adds` record the settings (`max_adds` is 1 when only
  `add_on_pct` is given, and `max_adds` without `add_on_pct` is a
  ValueError), `result.n_add_on_buys` counts the add-on fills and
  `result.add_on_skipped_buys` the 0-share ones; `has_exits` is true with it
  (so the fills carry reasons), `has_price_exits` is not. See
  [cli.md](cli.md#add-ons).
- Whole shares only, no shorting, no leverage; cash never goes negative.
- Costs: a fixed fee plus a percentage of traded value on every buy and sell.
  Both default to 0.
- Final equity is marked at the last close; the position is not liquidated.
- Buy and hold buys as much as possible on the first bar, at that bar's fill
  price (open or close, as the strategy) plus the same slippage, with the same
  costs; it is all-in and never exits (no stop, target, trailing stop or ATR
  stop, no risk sizing, no maximum holding time, no drawdown halt, no
  losing-streak halt, no scale-out and no add-ons). See
  [cli.md](cli.md#buy-and-hold-comparison).
- Statistics use one account value per bar, 252 bars per year, risk-free rate 0.

## Exit codes (command line)

- 0: success.
- 1: data problem (file missing or unreadable, no `close` column, bad number,
  no rows, non-positive price in `--backtest`, unwritable `--export`, bad or
  missing dates for `--resample`). One `Error:` line on stderr, no traceback.
- 2: usage problem, reported by the argument parser (bad windows, bad costs,
  options that need `--backtest` used without it, unknown `--strategy`,
  malformed or unknown `--param`, out-of-range slippage, position size, stop,
  target, trailing stop, breakeven, scale-out or risk sizing setting, `--atr-mult` or `--atr-period`
  without `--risk-pct`, `--cooldown` below 1 or without a stop, `--min-hold`, `--max-hold`
  or `--max-losses` below 1, `--max-drawdown` not above 0 and below 100,
  `--add-on` not above 0 or `inf`, `--max-adds` below 1 or without `--add-on`, a
  candle-only option with `--resample`, `--json`
  with `--chart`). `--json` keeps the same codes and
  messages. The full list is in [cli.md](cli.md#exit-codes).

## Web page

Routes: `/`, `/style.css`, `/app.js`, `/api/samples` (samples, strategies,
limits), `/api/health`, `POST /api/backtest`, `POST /api/scan` (the same
`scan` code as `--scan`, on files sent in the body; the reply is the
`--scan --json` object), `POST /api/walkforward` (the same `run_walk_forward`
as the walk-forward command; the reply is its `--json` object; `warmup`, JSON
`true`/`false` read like `atr_stop`, is `--warmup`; `strategy`, `grid` and
`params` are `--strategy`, `--grid` and `--param`, checked by the command's
own code, with at most 10,000 parameter sets and the work held to
300,000 bar-steps by `_strategy_work`, which weights each strategy's cost),
`POST /api/portfolio` (the portfolio command's own `run_texts` on files sent
in the body; the reply is its `--json` object; `strategy` is read by the same
`_strategy_name` as `/api/backtest`, and `params`, a list of `"KEY=VALUE"`
strings, by the command's `portfolio.check_strategy`). Input is validated with the same
functions as the CLI; client mistakes come back as `{"ok": false, "error": ...}`
with a 4xx status. The server listens on the loopback address only and the page
loads nothing from the network.

`POST /api/backtest` also takes `slippage`, `position_size`, `fill`,
`stop_loss`, `take_profit`, `trailing_stop`, `risk_pct`, `atr_mult`,
`atr_period`, `atr_stop` (JSON `true`/`false`), `cooldown`, `min_hold`, `max_hold`, `max_drawdown`, `breakeven`, `max_losses`, `scale_out`, `add_on`, `max_adds`, `trade_list` and `explain` (JSON `true`/`false`) (see
[cli.md](cli.md#post-apibacktest)); a request without them
is answered exactly as before they existed, and each one given is echoed in
the reply's `params` (with `add_on`, `max_adds` is echoed too, 1 when not
sent). The risk and ATR settings are checked by the command's own
`cli.check_risk`; with `risk_pct` or `atr_stop` the reply's `summary` also has
`risk_skipped_buys`; `cooldown` is checked by the command's own
`cli.check_cooldown`, and with it the `summary` has `cooldown_bars` and
`cooldown_skipped_buys`; `min_hold` is read like `max_hold`, checked by
`cli.check_min_hold`, needs no candle data, and with it the `summary` has
`min_hold_bars` and `min_hold_skipped_sells`; `max_hold` is checked by `cli.check_max_hold`, needs
no candle data, and with it the `summary` has `max_hold_bars` and
`time_exits`; `max_drawdown` is checked by `cli.check_max_drawdown`, needs no
candle data, and with it the `summary` has `max_drawdown_limit_pct`,
`drawdown_halt_bar` and `drawdown_skipped_buys`; `breakeven` is a stop (candle data, counts for
`cooldown`), and with it the `summary` has `breakeven_pct` and
`breakeven_exits`; `max_losses` is read like `max_hold`, checked by
`cli.check_max_losses`, needs no candle data, and with it the `summary` has
`max_losses`, `loss_halt_bar` and `loss_skipped_buys`; `scale_out` is read like `breakeven`, needs
candle data but is not a stop (no `cooldown` with it alone), and with it the `summary` has
`scale_out_pct` and `scale_out_exits`; `add_on` is read like `scale_out` and `max_adds` like `max_hold`, both
checked by `cli.check_add_on`, need no candle data, and with `add_on` the `summary` has `add_on_pct`,
`max_adds`, `add_on_buys` and `add_on_skipped_buys`; `trade_list` is read like `atr_stop`, changes no setting of the run,
needs no candle data, and with `true` the `report` ends with the trade list table and the reply ends with the
`trade_list` array; `explain` is read like `atr_stop` too, changes no setting of the run, needs no candle
data, and with `true` the `report` gets the sentence right after its Signal line and the reply gets the
`explanation` object right after `report`. The page's script (`web/assets.py`) only sends
`trailing_stop` when its field has a value, `risk_pct` (with `atr_mult` and
`atr_period` when filled in) when Risk % has one, and `atr_stop: true` (with
the ATR fields when filled in) when the ATR stop box is ticked, and
`cooldown` when the Cooldown field has a value, `min_hold` when the Min hold
field has one, `max_hold` when the Max
hold field has one, `max_drawdown` when the Max drawdown field has one, and
`breakeven` when the Breakeven field has one, `scale_out` when the Scale out
field has one, `max_losses` when the Max losses field has one, `add_on` and `max_adds` when their fields
have one (never greyed out; a Max adds without an Add-on is sent anyway, for the server's message), `trade_list: true` when the Trade list box
is ticked (never greyed out), and `explain: true` when the Explain signal box is ticked (never greyed out; the
sentence then shows in the text report as the server sent it, so it appears once);
it greys out
the candle-only fields for a close-only paste (Breakeven and Scale out among them; unticking the box; the Max
losses, Min hold, Max hold, Max drawdown, Add-on and Max adds fields are not among them), and shows
each trade's `reason`; its Exits card lists only the stop loss and take
profit, and the Trades card adds the skipped-buy count when the reply has
one, the count of breakeven sales when it has that, the count of partial sales by the scale-out when it has that, the add-on buys and the add-ons that got 0 shares when it has those, the count of buys the cooldown dropped when it has that, the
count of signal sells the minimum holding time skipped when it has that, the
count of time exits when it has that, the count of buys the drawdown halt
dropped when it has that, and the count of buys the losing-streak halt
dropped when it has that. When the reply has `trade_list`, the Trade list
panel shows it, its numbers formatted as Python formats them in the text
report (an exact half goes to the even digit, where JavaScript's `toFixed`
would go up). Each request
is logged as one line before its response is sent.

## Tests that keep the paths in step

`tests/test_paths_agree.py` runs three candle files against sixteen setting
combinations (every strategy, and every setting except the trailing stop, risk sizing, the ATR stop, the cooldown, the minimum and maximum holding times, the drawdown halt, the breakeven stop, the losing-streak halt, the scale-out, the add-ons and the trade list) through command-line flags, a
config file and the web API, with `backtest.run_backtest` as the reference. It
checks that all of them give the same fills, final equity, buy-and-hold final
equity and statistics, that flags and config give byte-identical output, and
that the web report equals the command line's report line for line. A change
to one path that is not made to the others fails these tests.

`tests/test_scan_agreement.py` does the same for the scan: four sets of files
and seven setting combinations through the `--scan` table, `--scan --json`, a
config file and `POST /api/scan`.

The trailing stop is checked path by path instead: `test_trailing_stop.py`
(the engine, hand-worked), `test_trailing_stop_report.py` (report and
export), `test_cli_trailing_stop.py` and `test_cli_trailing_json.py` (the
command and its `--json`), `test_config_trailing_stop.py` (config key against
the flag), `test_web_trailing_stop.py` (the API's numbers against `--json`)
and `test_web_trailing_stop_page.py` (the page, run in Node). Risk sizing
likewise: `test_atr.py` (the indicator), `test_risk_sizing.py` and
`test_risk_sizing_report.py` (the engine and report, hand-worked),
`test_cli_risk_sizing.py` and `test_cli_risk_json.py` (the command and its
`--json`), `test_config_risk_sizing.py`, `test_web_risk_sizing.py` and
`test_web_risk_sizing_page.py`. The cooldown likewise: `test_cooldown.py`
(the engine, hand-worked), `test_cli_cooldown.py` (the command and its
report), `test_cli_cooldown_unchanged.py` (commands, `--help` and short option
names without it), `test_cli_cooldown_json.py`, `test_config_cooldown.py`,
`test_web_cooldown.py` (the API against the command) and
`test_web_cooldown_page.py` (the page, run in Node). The maximum holding
time likewise: `test_max_hold.py` (the engine and report, hand-worked,
including open fills), `test_cli_max_hold.py` (the command, `--json`,
`--export`, `--help` and `--m`), `test_config_max_hold.py`,
`test_web_max_hold.py` (the API against the command) and
`test_web_max_hold_page.py` (the page, run in Node). The drawdown halt
likewise: `test_max_drawdown.py` (the engine and report, hand-worked,
including open fills and a sale the fees refuse), `test_cli_max_drawdown.py`
(the command, `--json`, `--export`, `--help` and every short option name),
`test_config_max_drawdown.py`, `test_web_max_drawdown.py` (the API against
the command) and `test_web_max_drawdown_page.py` (the page, run in Node). The minimum
holding time likewise: `test_min_hold.py` (the engine and report, hand-worked,
including open fills, the fee check and the drawdown sale, with
`data/c_before_min_hold.json` for runs without it), `test_cli_min_hold.py`
(the command, `--json` against `data/closes_json_before_min_hold.json`,
`--export`, `--help` and the `--mi`/`--min`/`--min-` aliases),
`test_config_min_hold.py`, `test_web_min_hold.py` (the API against the
command) and `test_web_min_hold_page.py` (the page, run in Node). The
losing-streak halt likewise: `test_max_losses.py` (the engine and report,
hand-worked, including open fills, the fee check, the drawdown sale and the
cooldown, with `data/c_before_max_losses.json` for runs without it),
`test_cli_max_losses.py` (the command, `--json`, `--export`, `--help`, every
short option name, with `data/cli_before_max_losses.json`),
`test_config_max_losses.py` (with `data/config_before_max_losses.json`),
`test_web_max_losses.py` (the API against the command, with the hashes of
replies without it) and `test_web_max_losses_page.py` (the page, run in
Node). The scale-out likewise: `test_scale_out.py` (the engine and report,
hand-worked, including gaps, odd share counts, a later buy, the other exits
on the same bar, fees and the losing streak, with
`data/before_scale_out.json` for 26 runs without it), `test_cli_scale_out.py`
(the command, `--help`, every short option name and the `--sc`/`--sca`
aliases, with `data/cli_before_scale_out.json`), `test_cli_scale_out_json.py`
(`--json`), `test_config_scale_out.py`, `test_web_scale_out.py` (the API
against the command, with the hashes of replies without it) and
`test_web_scale_out_page.py` (the page, run in Node). The add-ons
likewise: `test_add_on.py` (the engine and report, hand-worked, including the
spacing of several add-ons, a signal buy, a SELL on the close that sets one
off, the time exit, the drawdown sale, the scale-out, the breakeven stop, open
fills, fees and slippage, with `data/before_add_on.json` for 36 runs without
it), `test_cli_add_on.py` (the command, `--help`, every short option name,
with `data/cli_before_add_on.json`), `test_cli_add_on_json.py` (`--json`),
`test_config_add_on.py` (the keys against the flags, and config files without
them against the recorded flags), `test_web_add_on.py` (the API against the
command, with the hashes of replies without it) and `test_web_add_on_page.py`
(the page, run in Node). The signal
explanation likewise: `test_explain_crossover.py` (the sentence, hand-worked,
and random series whose first word must be `crossover_signal`'s),
`test_cli_explain.py` (the command and `--json`, each only one line or key
apart from the run without it), `test_config_explain.py` (the key against
the flag), `test_web_explain.py` (the API against the command, with the
hashes of replies without it) and `test_web_explain_page.py` (the page, run
in Node). The portfolio
command, API and page are compared in `test_portfolio_*.py` and
`test_web_portfolio*.py`; its strategies in `test_portfolio_strategy.py`
(the engine, hand-worked, and `first_signal_bars` by brute force against
each strategy's function), `test_portfolio_strategy_cli.py`,
`test_web_portfolio_strategy.py` and `test_web_portfolio_strategy_page.py`,
each against outputs recorded before the option existed
(`tests/data/portfolio_*before_strategy.json`).
