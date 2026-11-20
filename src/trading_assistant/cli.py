"""Command line entry point.

Usage:
    python -m trading_assistant.cli prices.csv [--short 20] [--long 50] [--rsi-period 14]
        [--resample weekly|monthly]
    python -m trading_assistant.cli prices.csv --backtest [--cash 10000]
        [--fee 0] [--fee-pct 0] [--slippage 0] [--position-size 1] [--export report.csv]
        [--fill close|open] [--stop-loss PCT] [--take-profit PCT] [--trailing-stop PCT]
        [--risk-pct PCT] [--atr-stop] [--atr-mult N] [--atr-period N] [--cooldown N]
        [--min-hold N] [--max-hold N] [--max-drawdown PCT] [--breakeven PCT] [--max-losses N]
        [--strategy sma_cross|rsi_reversion|breakout] [--param KEY=VALUE ...] [--stats]
        [--trade-list]
    Either form also accepts [--config FILE], [--chart], [--candles], [--explain] and [--json].
    python -m trading_assistant.cli --scan FOLDER [--short 20] [--long 50] [--rsi-period 14]
        [--min-score N] [--top N] [--json] [--report FILE] [--config FILE]

The CSV must have a header row with a `close` column. With --candles the file
is instead read as a candle file (date, open, high, low, close, volume
columns, checked strictly) and its closes are analysed exactly as a close-only
file's would be; --candles cannot be combined with --resample yet.

With --resample the daily bars are first reduced to weekly or monthly bars
(last date and last close of each ISO week or calendar month); everything
else, including --backtest, then works on those bars. This needs a `date`
column with YYYY-MM-DD dates in ascending order.

With --backtest the crossover signal is also traded over the whole file,
starting from --cash (default 10000), and a summary is appended to the report:
trades, costs, completed round trips and how many made money, and a
side-by-side comparison with buy-and-hold (end equity, return, max drawdown).
--fee / --fee-pct add trading costs (default 0, i.e. no costs). --slippage PCT
makes buys fill that percentage above and sells that percentage below the
fill price, before fees (default 0). --position-size FRACTION (above 0, at
most 1) lets each buy spend at most that fraction of the account value, costs
and slippage included (default: all the cash, as without the option). --export writes
one CSV row per bar with the account value, signal and any fill.
With --stats a "Risk and return" block (CAGR, volatility, Sharpe, ...) is
printed after the report; "n/a" marks a number that is undefined. It is opt-in
so the default report stays identical to the web page's text report.
With --trade-list a "Trade list" table follows (after the "Risk and return"
block with --stats, before --chart): one row per completed round trip (entry
and exit bar, bars held, shares bought, outlay, proceeds, P/L, return % and the
reason of the sale that completed it) and a row for a position still held at
the end, marked at the last close with no selling costs (unrealized). Its
footer repeats the "Round trips:" numbers. It needs no candle file and works
with --resample; with --json the backtest object gets a trade_list array
instead (see below).

--explain (a switch) prints one sentence on its own line right after the
"Signal:" line of the text report. It starts with the Signal line's decision
(BUY, SELL or HOLD, from the same SMA crossover on --short/--long, whatever
--strategy or --param is, and on the resampled bars with --resample), gives
the short and long SMA on the last bar and on the bar before, and says why;
a HOLD sentence never says "crossed", and with fewer than --long + 1 bars it
says how many a crossover needs. Numbers have 2 decimals, more when two
different averages would print the same. It needs no --backtest and no
candle file, works with --backtest and every other option of the text
report, and is a usage error with --scan. With --json the object gets an explanation
key right after signal, holding the same sentence (with --backtest too: it is
a top-level key, before rsi and the backtest object). Without it the output,
text or JSON, is exactly what it was before. It is listed in --help but not in
the usage line. The config file key is explain (yes/no; see --config below).

--strategy picks the rule that is traded in --backtest (default sma_cross) and
--param KEY=VALUE (repeatable, numeric) overrides one of its parameters. They
change only the backtest: the top "Signal:" line is always the SMA crossover
signal from --short/--long. For sma_cross, --short/--long set the windows and
--param short=/long= may set them too, but giving both --short and a different
--param short= (likewise long) is a usage error. For the other strategies
--short/--long still feed the Signal line only.

--fill picks the price of bar x+1 at which a signal decided on bar x is
filled in --backtest: close (default) or open. --fill open reads the file as a
candle file (like --candles) and cannot be combined with --resample yet;
signals still come from the closes and account value is marked at the close.

--stop-loss PCT and --take-profit PCT sell the position while it is held
when a bar's low reaches the entry price less PCT percent (at that stop
price) or its high reaches the entry price plus PCT percent (at that target
price); if one bar touches both, the stop wins. Either option reads the file
as a candle file (like --fill open) and cannot be combined with --resample
yet. Each fill in the report and in --export then says why it happened:
signal, stop or target.

--trailing-stop PCT sells the position while it is held when a bar's low
reaches the highest high since entry less PCT percent (at that level, or at
the bar's open if it opens at or below it). The highest high starts at the
entry price and takes in the highs of the bars after the entry bar, never
the checked bar's own high. It follows the rules of --stop-loss: it needs
--backtest, reads the file as a candle file and cannot be combined with
--resample yet. It works next to --stop-loss and --take-profit: the higher
of the stop and trail levels is used, and it wins over the target if a bar
touches both. Its fills say trail.

--risk-pct PCT sizes each buy by risk: PCT percent (above 0, at most 100) of
the account value at the fill, divided by a stop distance of --atr-mult N
(above 0, default 2) times the Wilder ATR over --atr-period N bars (a whole
number of at least 1, default 14) taken on the bar the buy signal came on,
rounded down to whole shares. With --position-size the smaller size wins. A
buy the rule gives 0 shares (no ATR yet, an ATR of 0, or under one share) is
skipped, and the report counts it. Risk sizing only sets the number of
shares and places no stop itself (--atr-stop adds one, at the distance of the
buy that opened the position); a loss is not limited to PCT percent (with
--atr-stop a gap, slippage, fees or a later buy into the position can still
lose more). It follows the rules of --stop-loss: it needs --backtest, reads
the file as a candle file and cannot be combined with --resample yet. It
works next to --stop-loss, --take-profit, --trailing-stop and --atr-stop,
which are the exits. --atr-mult and
--atr-period need --risk-pct or --atr-stop. The config file keys are risk_pct, atr_mult and
atr_period (see --config below). The text report shows a "Risk sizing:" line and
--json the matching backtest fields (see below). Like --trailing-stop, these
options are listed in --help but not in the usage line.

--atr-stop (a switch) sells the position while it is held when a bar's low
reaches the entry price (the average price paid) less --atr-mult times the
ATR over --atr-period bars, the ATR taken on the signal bar of the buy that
opened the position. That distance is fixed per position; a later buy moves
the level with the average price only. A bar that opens at or below the level
sells at its open. A buy signal with no ATR yet, or an ATR of 0, is skipped
and counted, as for --risk-pct (once when both are on). With --stop-loss
and --trailing-stop the highest level is used (on a tie the stop, then the
trail, then atr) and it wins over --take-profit. Its fills say atr. With
--risk-pct the buy that opens a position is sized on the same distance; a
later buy is sized on its own signal bar's ATR, so a gap, slippage, fees or
a later buy can lose more than the risk. It follows the rules of
--stop-loss: it needs --backtest, reads the file as a candle file and cannot
be combined with --resample yet. It is listed in --help but not in the usage
line. --json shows atr_stop, atr_mult, atr_period and risk_skipped_buys (see
below). The config file key is atr_stop (yes/no; see --config below).

--cooldown N (a whole number of at least 1) stops buys for N bars after a
stop exit: when --stop-loss, --trailing-stop, --atr-stop or --breakeven sells the position
on bar t, no buy can fill on bars t+1 to t+N. A buy due then is dropped, not
delayed, and counted, even one that would have got 0 shares anyway (it is
then not also counted as a risk sizing skip); a buy signal on the exit bar
itself is the first one blocked. A --take-profit or signal sell starts no
cooldown. It needs --backtest and one of --stop-loss,
--trailing-stop, --atr-stop or --breakeven (its error message for no stop at
all names only the first three). The text report then shows a "Cooldown:" line
after the "Exits:" line. It is listed in --help but not in the usage line.
--json shows cooldown_bars and cooldown_skipped_buys (see below). The config
file key is cooldown (see --config below).

--min-hold N (a whole number of at least 1) holds back signal sells: a
signal sell due before bar e+N, e being the bar of the buy that opened the
position, is dropped, not delayed, and counted. A later buy into the
position does not restart the count, and since a signal sell is never due on
the buy's own bar, N=1 skips nothing. Only signal sells are held back: stops,
the target, --max-hold and --max-drawdown still sell inside the window. A
sell is counted only when it would otherwise have filled (shares held and
nothing sold them earlier on that bar), before the fees are looked at. It
needs --backtest but no stop and no candle file: a close-only file works,
and it can be combined with --resample (N then counts the resampled bars).
The text report then shows a "Min hold:" line right before the "Max hold:"
line (or where that line would be). It is listed in --help but not in the
usage line. --json shows min_hold_bars and min_hold_skipped_sells (see
below). The config file key is min_hold (see --config below).

--max-hold N (a whole number of at least 1) sells the whole position N bars
after the buy that opened it: on bar e+N, e being that buy's bar, at that
bar's fill price (its close, or its open with --fill open). A later buy into
the position does not restart the count. A bar that already has a fill (a
signal buy or sell, a stop, trail, ATR stop, breakeven or target sale, or with
close fills a --scale-out partial sale) keeps it and the time exit waits for
the next bar; with --fill open a stop or target that
the bar gaps through at the open comes first, one reached later in the bar
does not. Its fills say time, and it starts no cooldown. It needs --backtest
but no stop and no candle file: a close-only file works, and it can be
combined with --resample (N then counts the resampled bars). The text report
then shows a "Max hold:" line after the "Cooldown:" (or "Exits:") line, fills
carry a reason and --export gets its reason column. It is listed in --help
but not in the usage line. --json shows max_hold_bars and time_exits (see
below). The config file key is max_hold (see --config below).

--max-drawdown PCT (above 0 and below 100, decimals allowed) halts the run
when the account value at a close is PCT percent or more below its highest
value at a close so far. From the next bar on no buy can fill: each buy due
is dropped and counted, even one that would have got 0 shares (it is then not
also counted as a cooldown or risk sizing skip). A position still held is
sold whole on the next bar at its fill price (its close, or its open with
--fill open); a signal, stop, trail, ATR stop, breakeven, target or time sale on that bar
goes first and keeps its own reason, otherwise the fill says drawdown (with
close fills a --scale-out partial sale on that bar goes first too, and the
drawdown sale waits for the next bar). A sale
the fees would refuse is tried again on each later bar. It starts no
cooldown. It needs --backtest but no stop and no candle file: a close-only
file works, and it can be combined with --resample. The text report then
shows a "Drawdown:" line just before the "Round trips:" line, fills carry a
reason and --export gets its reason column. It is listed
in --help but not in the usage line. --json shows max_drawdown_limit_pct,
drawdown_halt_bar and drawdown_skipped_buys (see below). The config file key
is max_drawdown (see --config below).

--breakeven PCT (above 0, decimals allowed, no upper limit but not inf) moves a stop up
to the entry price (the average price paid) once the high of a bar after the
entry bar is at or above the entry price plus PCT percent; the entry bar's
own high never counts, with either --fill. From the next bar on, a bar whose
low reaches the entry price sells the whole position there, or at the bar's
open if it opens at or below it. No allowance is made for fees or slippage,
so such a sale still loses the costs. A later buy into the position moves
the level with the average price: an armed stop stays armed, an unarmed one
measures PCT from the new average. It works next to --stop-loss,
--trailing-stop and --atr-stop (the highest level is used; on a tie the
stop, then the trail, then atr, then breakeven) and wins over --take-profit
if a bar touches both; with --take-profit at or below PCT it is allowed but
can never act, because the target sells on the bar that would arm it (except
after a later buy into the position: a lower-priced one with close fills, or
any one with --fill open, whose bar skips its exit checks). Its
fills say breakeven. It counts as a stop for --cooldown: --cooldown may be
used with it alone, and a breakeven sale starts the cooldown. It follows
the rules of --stop-loss: it needs --backtest, reads the file as a candle
file and cannot be combined with --resample yet. The "Exits:" line then
shows it and the "Cooldown:" line names it; a run without it prints exactly
what it printed before. It is listed in --help but not in the usage line.
--json shows breakeven_pct and breakeven_exits (see below). The config file
key is breakeven (see --config below); a config cooldown is used with it, as
with the other stops.

--max-losses N (a whole number of at least 1) halts buying after N losing
round trips in a row. A round trip loses when its profit after costs is
below 0, whatever sold it (signal, stop, target, trail, atr, breakeven, time
or drawdown); any other round trip, one at exactly 0.00 included, resets the
count. A sale the fees refuse completes no round trip and does not count.
From the bar after the losing sale on, no buy can fill: each buy due is
dropped and counted, even one that would have got 0 shares (it is then not
also counted as a cooldown or risk sizing skip; a buy the --max-drawdown
halt also blocks is counted there only). Every round trip ends with the
whole position sold (a --scale-out partial sale completes none and does not
count), so nothing is held when the halt starts and nothing is sold because
of it. It needs --backtest but no stop and no candle file: a
close-only file works, and it can be combined with --resample. The text
report then shows a "Max losses:" line just before the "Round trips:" line
(after the "Drawdown:" line when that is there); a run without it prints
exactly what it printed before. It is listed in --help but not in the usage
line. It adds no fill reason, so --export's columns do not change. --json
shows max_losses, loss_halt_bar and loss_skipped_buys (see below). The
config file key is max_losses (see --config below).

--scale-out PCT (above 0, decimals allowed, not inf) sells half the shares
held (rounded down) once per position, when the high of a bar after the
entry bar reaches the entry price (the average cost of the shares held) plus
PCT percent: at that price, or at the bar's open if it opens at or above it.
The rest stays open and is sold by whatever would have sold it. With 1 share
nothing is sold and it can still scale out after a later buy into the
position; after a scale-out a later buy cannot make it scale out again, until
the position is back to 0. Any other fill on the bar (a signal buy or sell, a
stop, trail, ATR stop, breakeven or target sale) goes first and the scale-out
is skipped on that bar; with close fills a --max-hold or --max-drawdown sale
then waits for a later bar, with --fill open those sales at the open go
first. A partial sale is not a round trip: its proceeds count in the round
trip the rest of the position completes (so in the win rate and in
--max-losses). Its fills say scale_out. It starts no cooldown, --min-hold
does not hold it back, and it needs no other exit option. It follows the
rules of --take-profit: it needs --backtest, reads the file as a candle file
and cannot be combined with --resample yet. The text report then shows a
"Scale out:" line right after the "Exits:" line (or where it would be); a run
without it prints exactly what it printed before. It is listed in --help but
not in the usage line. --json shows scale_out_pct and scale_out_exits (see
below). The config file key is scale_out (see --config below).

--add-on PCT (above 0, decimals allowed, not inf) buys more of a position
while it is held: when a close is PCT percent or more above the fill price of
the latest buy into the position (as the fill records it, slippage
included), an add-on buy fills on the next bar at that bar's fill price (its
close, or its open with --fill open), up to --max-adds N times per position
(a whole number of at least 1, default 1; --max-adds without --add-on is a
usage error). Every buy into the position, a signal buy too, becomes the new
latest buy price, but only add-ons count towards N, and the count starts
again with each new position. The add-on is sized like any buy (all the
cash, --position-size or --risk-pct); with the default all-cash sizing the
first buy spends the cash, so an add-on usually gets 0 shares. One that gets
0 shares is skipped and counted in the report; it is not one of the N and
leaves the latest buy price as it was, so the next close is checked again.
A BUY or SELL signal on the close that would set it off drops it (a SELL even
when --min-hold then holds the sale back). On the next bar anything known
when it would fill drops it, not delayed and not counted: with close fills a
stop, trail, ATR stop, breakeven or target sale during the bar, the signal
fill, a --scale-out partial sale, a --max-hold sale or a --max-drawdown sale;
with --fill open the signal fill, a gap through a stop or the target at the
open, or a --max-hold or --max-drawdown sale at the open. With --fill open
it fills at the open, before the bar's range is checked, so no stop, target
or scale-out acts on that bar (one fill per bar); from the next bar on their
levels follow the new average. After a --max-drawdown halt an add-on that
gets its turn (only when the drawdown sale was refused by the fees) is
counted with the buys the halt dropped. An add-on raises the average entry
price (the stop, ATR stop, breakeven, target and scale-out levels follow
it), its shares and cost go into the same round trip (one round trip, one
step of the --max-losses count), and it restarts neither --min-hold nor
--max-hold. The close is compared in floating point, so a close exactly on
the level can fall just short of it: after a buy at 11, --add-on 10 needs a
close above 12.10, and a close of exactly 12.10 does not set it off. Its
fills say add_on. It needs --backtest but no stop and no candle file: a
close-only file works, and it can be combined with --resample. The text
report then shows an "Add-ons:" line right after the "Scale out:" line (or
where it would be), fills carry a reason and --export gets its reason column;
a run without it prints exactly what it printed before. Both options are
listed in --help but not in the usage line. --json shows add_on_pct,
max_adds, add_on_buys and add_on_skipped_buys (see below). The config file
keys are add_on and max_adds (see --config below).

--chart prints a plain-text chart of the closes after the report; with
--backtest the fills are marked B (buy) and S (sell).

--json prints the same information as one JSON object on stdout instead of
the text report, and nothing else (the disclaimer is a field of the object).
It has bars, last_close, signal, rsi and rsi_label (null where the text says
n/a), and with --explain an explanation (the --explain sentence) right after
signal; with --backtest a backtest object (strategy, params, settings, fills,
final and return figures, a benchmark object, plus stats with --stats, null
for n/a, and export with --export). Numbers are unrounded JSON numbers. Both
outputs are built from one `summarise` call. Errors are reported exactly as
without --json (stderr, exit 1 or 2, nothing on stdout). --json cannot be
combined with --chart.
With --trailing-stop the backtest object also has trailing_stop_pct, right after take_profit_pct.
With --risk-pct it also has risk_pct, right after position_size. With --risk-pct or --atr-stop
it also has atr_mult and atr_period (the settings used, with the defaults filled in) right after
risk_pct (or position_size), and risk_skipped_buys (how many buys were skipped for want of a
usable ATR, or by risk sizing for under one share) right after sells. With --atr-stop it also
has atr_stop (true), right after trailing_stop_pct (or take_profit_pct). With --breakeven it
also has breakeven_pct (PCT), right after atr_stop (or trailing_stop_pct, or take_profit_pct),
and breakeven_exits (how many sells the breakeven stop made) right after risk_skipped_buys (or
sells). With --cooldown it
also has cooldown_bars (N), right after the exit and add-on settings (max_adds, scale_out_pct,
breakeven_pct, atr_stop, trailing_stop_pct or take_profit_pct, the last of those present), and
cooldown_skipped_buys (how many buys the cooldown dropped) right after sells (or after
add_on_skipped_buys, scale_out_exits, breakeven_exits or risk_skipped_buys when one is there).
With --scale-out it also has scale_out_pct (PCT), right after breakeven_pct (or atr_stop,
trailing_stop_pct, or take_profit_pct), and scale_out_exits (how many partial sells the
scale-out made; none of them is a round trip) right after breakeven_exits (or
risk_skipped_buys, or sells).
With --add-on it also has add_on_pct (PCT) and max_adds (N, 1 when --max-adds is not given),
right after scale_out_pct (or breakeven_pct, atr_stop, trailing_stop_pct, or take_profit_pct),
and add_on_buys (how many add-on buys filled) and add_on_skipped_buys (how many add-ons got 0
shares) right after scale_out_exits (or breakeven_exits, risk_skipped_buys, or sells), in the
order of the text report's lines. Its fills say add_on.
With --min-hold it also has min_hold_bars (N), right before max_hold_bars (or where that key
would be), and min_hold_skipped_sells (how many signal sells the minimum holding time dropped)
right before time_exits (or where that key would be).
With --max-hold it also has max_hold_bars (N), right after min_hold_bars (or cooldown_bars,
or the exit settings, or take_profit_pct), and time_exits (how many sells the maximum holding
time made) right after min_hold_skipped_sells (or cooldown_skipped_buys, risk_skipped_buys, or
sells).
With --max-drawdown it also has max_drawdown_limit_pct (PCT), right after max_hold_bars (or
min_hold_bars, cooldown_bars, or the exit settings), and drawdown_halt_bar (the bar whose close
set off the halt, null when it never did) and drawdown_skipped_buys (how many buys the halt
dropped) right after time_exits (or min_hold_skipped_sells, cooldown_skipped_buys,
risk_skipped_buys, or sells).
With --max-losses it also has max_losses (N), right after max_drawdown_limit_pct (or where that
key would be), and loss_halt_bar (the bar of the losing sale that completed the streak, null
when it never did) and loss_skipped_buys (how many buys the halt dropped; a buy the drawdown
halt also blocked is counted in drawdown_skipped_buys only) right after drawdown_skipped_buys
(or where that key would be), just before fills.
With --trade-list it also has trade_list, the last key (after stats): one object per row of the
text trade list, in the same order, with the table's columns: open (true only for the position
still held at the end, which is unrealized: marked at the last close, no selling costs),
entry_bar, exit_bar (null when open), bars_held, shares (shares bought), outlay, proceeds, pnl,
return_pct and reason (null where the table shows "-"); an empty list when there were no
trades. round_trips and winning_round_trips do not change.

--scan FOLDER scores every .csv file directly inside FOLDER (not in
subfolders; other files are ignored) with the combined score
(signals.combined_score), using --short/--long/--rsi-period, and prints one
table row per file: highest score first, equal scores in name order. The
symbol is the file name without .csv. Each file is read like a single price
file; one that cannot be read, has no `close` column, holds a bad number or
has no rows is skipped and listed with its one-line reason under "Skipped:"
after the table. --scan cannot be combined with a price file, --backtest or
any backtest option, --chart, --candles, --resample or --explain (a config
explain = yes is ignored there).
--min-score N keeps only the rows scoring N or more and --top N then keeps the
first N of those rows in the same order; with either, the top line also says
how many files were found, how many rows are left and how many are shown. The
skipped list is always shown in full. If nothing is left the table header is
printed with a "no file matched" line (exit 0). Both options need --scan.
With --scan, --json prints one JSON object on stdout instead of the table and
nothing else (no disclaimer line): found, scored and shown (counted like the
table's top line), results (the shown rows in table order, each with symbol,
bars, score and parts: crossover, rsi, macd, bollinger; empty when nothing
matched, still exit 0) and skipped (every skipped file, with symbol and its
one-line reason). Errors are reported exactly as without --json.
--report FILE (needs --scan) also writes a Markdown report to FILE after the
normal output, which stays exactly the same (only the JSON object with
--json): title, today's date, the settings, a table of the shown rows in
screen order with the score and the four parts, one sentence per row saying
why it scored what it did (built only from its four parts), the skipped files
with their reasons and the disclaimer. A FILE that is a folder, sits in a
folder that does not exist or is one of the scanned .csv files is refused
before anything is printed (exit 1); if writing fails after the output was
printed, the error goes to stderr and the exit code is 1.

--config FILE reads defaults from an INI file (see the config module). The
order of precedence is: flags written on the command line, then the config
file, then the built-in defaults. Without --config no file is read, unless the
environment variable TRADING_ASSISTANT_CONFIG is set, in which case its value
is the path of the file (for example `trading_assistant.ini` in the current
directory). Config values for --cash, --fee, --fee-pct, --slippage,
--position-size, --fill, --stop-loss, --take-profit, --trailing-stop,
--risk-pct, --atr-mult, --atr-period, --atr-stop, --cooldown, --min-hold, --max-hold, --max-drawdown,
--breakeven, --max-losses, --scale-out, --add-on, --max-adds, --strategy,
--stats, --trade-list and [strategy.NAME] parameters apply only with
--backtest and are ignored without it; config `top` and `min_score` apply
only with --scan and are ignored without it (there is no key for the scan
folder or --report); config `explain` applies with or without --backtest and
is ignored with --scan (unlike the --explain flag, it is no error there). Values from the file are checked by the same rules as
flags, and a config fill = open, stop_loss, take_profit, trailing_stop,
risk_pct, atr_stop = yes, breakeven or scale_out reads the file as a candle file
exactly as the flags do. Each of risk_pct, atr_mult and atr_period is taken from the file
only when its own flag is not written; the file's atr_mult and atr_period are
used only when risk sizing or the ATR stop is on (risk_pct or atr_stop = yes
from the file, or --risk-pct or --atr-stop) and are otherwise ignored, without
an error. atr_stop, stats, trade_list and explain are yes/no switches: yes turns the option on, no
leaves it as the command line has it (so --atr-stop, --stats, --trade-list or --explain wins over no:
with trade_list = no and --trade-list written, the trade list is printed; with explain = no and
--explain written, the sentence is printed).
A config cooldown is used only when a stop is on (stop_loss, trailing_stop,
atr_stop = yes or breakeven from the file, or --stop-loss, --trailing-stop,
--atr-stop or --breakeven)
and is otherwise ignored, like atr_mult and atr_period; unlike them, a value
below 1 is an error (exit 2) even then. --cooldown on the command line wins
over it. A config max_hold needs no stop, so with --backtest it is always used
unless --max-hold is written (then the file's value is not used at all); a
value below 1 is an error (exit 2) and one that is not a whole number a config
error (exit 1). A config min_hold works the same way: with --backtest it is
used unless --min-hold is written; a value below 1 is an error (exit 2) and
one that is not a whole number a config error (exit 1). A config max_drawdown
works the same way: with --backtest it
is used unless --max-drawdown is written; a value not above 0 and below 100 is
an error (exit 2) and one that is not a finite number (nan, inf) a config
error (exit 1). A config breakeven works the same way: with --backtest it is
used unless --breakeven is written; a value not above 0 is an error (exit 2,
the flag's message) and nan or inf a config error (exit 1); the flag refuses
inf too (exit 2). A config max_losses works like max_hold: with --backtest it
is used unless --max-losses is written (then the file's value is not used at
all); a value below 1 is an error (exit 2, the flag's message) and one that
is not a whole number a config error (exit 1). Without --backtest, or with
--scan, it is ignored like the other backtest keys, so there only a value
that is not a whole number is an error. A config scale_out works like
breakeven: with --backtest it is used unless --scale-out is written (then the
file's value is not used at all); a value not above 0 is an error (exit 2,
the flag's message) and one that is not a finite number (nan, inf) or not a
number a config error (exit 1). It needs no other exit key. Without
--backtest, or with --scan, it is ignored, so there only a value that is not
a finite number is an error. A config add_on works like scale_out: with
--backtest it is used unless --add-on is written; a value not above 0 is an
error (exit 2, the flag's message) and one that is not a finite number (nan,
inf) or not a number a config error (exit 1). A config max_adds works like
max_hold (used unless --max-adds is written; a value below 1 is an error,
exit 2, the flag's message; one that is not a whole number, like 2.5 or abc,
a config error, exit 1), but it is used only when add_on or --add-on is
there: without either it is ignored quietly, like a config cooldown without a
stop, and like cooldown its range is still checked then (0 is exit 2). Without
--backtest, or with --scan, both are ignored, so there only a value of the
wrong kind is an error.

Exit codes:
    0  success
    1  data problem (file missing/unreadable, no `close` column, bad number,
       no rows, a candle file that fails a check with --candles, --fill open,
       --stop-loss, --take-profit, --trailing-stop, --risk-pct, --atr-stop, --breakeven or --scale-out (for
       example no `open` column),
       non-positive price in --backtest mode, --export not writable,
       --resample without a `date` column or with a missing, unparseable or
       non-ascending date, a config file that cannot be read or holds an
       unknown section or key, a duplicate, or a value of the wrong kind;
       with --scan: the folder is missing or not a folder, holds no .csv
       file, or not one of its files could be scored; a --report file that
       cannot be written)
    2  usage problem (unparseable arguments, --resample not weekly/monthly,
       --candles, --fill open, --stop-loss, --take-profit, --trailing-stop,
       --risk-pct, --atr-stop, --breakeven or --scale-out together with --resample, window < 1,
       --short >= --long,
       --cash <= 0, negative --fee, --fee-pct or --slippage outside [0, 100),
       --position-size not above 0 or above 1, --stop-loss outside (0, 100),
       --take-profit not positive, --trailing-stop outside (0, 100), --breakeven not above 0 or inf,
       --scale-out not above 0 or inf, --add-on not above 0 or inf (or nan),
       --max-adds not a whole number of at least 1 or without --add-on,
       --risk-pct outside (0, 100], --atr-mult not above 0, --atr-period not a
       whole number of at least 1, --atr-mult or --atr-period without
       --risk-pct or --atr-stop, --cooldown not a whole number of at least 1,
       --cooldown without --stop-loss, --trailing-stop, --atr-stop or --breakeven,
       --min-hold, --max-hold or --max-losses not a whole number of at least 1,
       --max-drawdown not a number above 0 and below 100, or any of
       --cash/--fee/--fee-pct/--slippage/--position-size/--export/--fill/
       --stop-loss/--take-profit/--trailing-stop/--risk-pct/--atr-stop/--cooldown/
       --min-hold/--max-hold/--max-drawdown/--breakeven/--max-losses/--scale-out/--add-on/--max-adds/--strategy/
       --param/--stats/--trade-list without
       --backtest,
       unknown --strategy, a --param that is not KEY=VALUE with a numeric
       value, an unknown key for the strategy, a value the strategy rejects,
       a --param short/long that contradicts an explicit --short/--long,
       or --json together with --chart, or --scan together with a price
       file, --backtest, a backtest option, --chart, --candles,
       --resample or --explain, --min-score, --top or --report without --scan, --top < 1,
       an empty --report file name;
       the same rules apply to values that come from a config file, e.g. a
       config `short` not below `long`)

This is a research aid. It does not place orders and it is not financial advice.
"""

import argparse
import json
import math
import os
import sys

from .backtest import DEFAULT_CASH, FILLS, export_csv, format_result, format_stats, format_trade_list, run_backtest
from .backtest import trade_list as trade_list_rows
from .config import load_config
from .data import (  # noqa: F401  re-exported: other modules and tests import these from here
    CSV_EXAMPLE,
    decode_price_bytes,
    load_candles,
    load_closes,
    load_price_table,
    parse_price_text,
    read_price_table,
)
from .resample import PERIODS, resample
from .scan import ScanError, format_scan, report_markdown, scan_data, scan_folder, write_report
from .signals import BUY, crossover_signal, explain_crossover, rsi_filter
from .strategies import resolve_params, strategy_names
from .textchart import line_chart

DEFAULT_SHORT = 20
DEFAULT_LONG = 50
DEFAULT_RSI_PERIOD = 14

DEFAULT_STRATEGY = "sma_cross"

CONFIG_ENV_VAR = "TRADING_ASSISTANT_CONFIG"

CHART_WIDTH = 60
CHART_HEIGHT = 12

DISCLAIMER = "Research aid only. Not financial advice."


class _Given(argparse.Action):
    """Store the value and remember that the option was written on the command line."""

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, self.dest + "_given", True)


def parse_param(text):
    """Turn ``KEY=VALUE`` into ``(key, number)``; the number is an int when it reads as one.

    Raises ValueError with a one-line message for anything else.
    """
    key, sep, raw = text.partition("=")
    key, raw = key.strip(), raw.strip()
    if not sep or not key or not raw:
        raise ValueError(f"--param must look like KEY=VALUE, got {text!r}")
    try:
        return key, int(raw)
    except ValueError:
        pass
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"--param {key} needs a number, got {raw!r}") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"--param {key} needs a finite number, got {raw!r}")
    return key, value


def build_parser(scan=False):
    """The argument parser. With ``scan=True`` the price file is optional (for ``--scan``)."""
    parser = argparse.ArgumentParser(
        prog="trading_assistant.cli",
        description="Suggest BUY/SELL/HOLD from closing prices.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("csv_path", nargs="?" if scan else None, help="CSV file with a 'close' column")
    parser.add_argument(
        "--short", type=int, default=DEFAULT_SHORT, action=_Given, help="short SMA window (default: %(default)s)"
    )
    parser.add_argument(
        "--long", type=int, default=DEFAULT_LONG, action=_Given, help="long SMA window (default: %(default)s)"
    )
    parser.add_argument(
        "--rsi-period",
        type=int,
        default=DEFAULT_RSI_PERIOD,
        action=_Given,
        help="RSI lookback (default: %(default)s)",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="also simulate trading the crossover signal over the whole file",
    )
    # Hidden exact alias: "--b" meant --backtest (argparse abbreviation) before --breakeven existed,
    # and an exact option string wins over the now-ambiguous prefix. Its errors still say --backtest.
    backtest_alias = parser.add_argument("--b", dest="backtest", action="store_true", help=argparse.SUPPRESS)
    backtest_alias.option_strings = ["--backtest"]
    parser.add_argument(
        "--cash",
        type=float,
        default=None,
        metavar="AMOUNT",
        help=f"starting cash for --backtest (default: {DEFAULT_CASH:,.0f})",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=None,
        metavar="AMOUNT",
        help="fixed cost charged on every buy and every sell in --backtest (default: 0)",
    )
    parser.add_argument(
        "--fee-pct",
        type=float,
        default=None,
        metavar="PCT",
        help="percentage of traded value charged on every buy and sell in --backtest, "
        "e.g. 0.1 for 0.1%% (default: 0)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, buys fill this percentage above and sells this percentage below the fill price, "
        "before fees, e.g. 0.1 for 0.1%% (default: 0)",
    )
    parser.add_argument(
        "--position-size",
        type=float,
        default=None,
        metavar="FRACTION",
        help="with --backtest, each buy spends at most this fraction of the account value (above 0, at most 1), "
        "costs and slippage included (default: all the cash)",
    )
    parser.add_argument(
        "--stop-loss",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, sell when a bar's low reaches the entry price less PCT%% (reads a candle file; "
        "cannot be combined with --resample yet)",
    )
    parser.add_argument(
        "--take-profit",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, sell when a bar's high reaches the entry price plus PCT%% (reads a candle file; "
        "cannot be combined with --resample yet); if a bar touches both levels the stop wins",
    )
    # Hidden exact alias: "--t" meant --take-profit (argparse abbreviation) before --top existed,
    # and an exact option string wins over the now-ambiguous prefix. Its errors still say --take-profit.
    take_profit_alias = parser.add_argument(
        "--t", dest="take_profit", type=float, default=None, help=argparse.SUPPRESS
    )
    take_profit_alias.option_strings = ["--take-profit"]
    trailing_stop = parser.add_argument(
        "--trailing-stop",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, sell when a bar's low reaches the highest high since entry less PCT%% "
        "(the bar's own high is not used; reads a candle file; cannot be combined with --resample yet); "
        "works next to --stop-loss and --take-profit: the higher of the stop and trail levels is used, "
        "and it wins over the target if a bar touches both",
    )
    # Hidden exact aliases: "--tr" and "--tra" meant --trailing-stop (argparse abbreviation) before --trade-list
    # existed, and an exact option string wins over the now-ambiguous prefix. Their errors still say --trailing-stop.
    for short_form in ("--tr", "--tra"):
        trailing_stop_alias = parser.add_argument(
            short_form, dest="trailing_stop", type=float, default=None, help=argparse.SUPPRESS
        )
        trailing_stop_alias.option_strings = ["--trailing-stop"]
    risk_pct = parser.add_argument(
        "--risk-pct",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, size each buy by risk: PCT%% of the account value (above 0, at most 100) divided by "
        "a stop distance of --atr-mult times the ATR (--atr-period bars) on the bar the buy signal came on, "
        "rounded down to whole shares; with --position-size the smaller size wins. A buy that gets 0 shares "
        "this way (no ATR yet, or under one share) is skipped and counted in the report. This only sets the "
        "number of shares: no stop is placed, so a loss is not limited to PCT%% (--atr-stop adds a stop at the "
        "distance of the buy that opened the position; even then a gap, slippage, fees or a later buy into the "
        "position can lose more). Works next to --stop-loss, --take-profit and --trailing-stop, and next to "
        "--atr-stop (reads a candle file; cannot be combined with --resample yet)",
    )
    atr_mult = parser.add_argument(
        "--atr-mult",
        type=float,
        default=None,
        metavar="N",
        help="with --risk-pct, the stop distance used for sizing is N times the ATR (above 0; default: 2); "
        "without --atr-stop it only sets the number of shares, no stop is placed. With --atr-stop (with or "
        "without --risk-pct) it is the distance of the ATR stop, taken on the buy that opened the position",
    )
    atr_period = parser.add_argument(
        "--atr-period",
        type=int,
        default=None,
        metavar="N",
        help="with --risk-pct, the number of bars in the ATR (a whole number of at least 1; default: 14); "
        "--atr-stop uses the same ATR",
    )
    atr_stop = parser.add_argument(
        "--atr-stop",
        action="store_true",
        default=None,  # None means "not written", like the other backtest options
        help="with --backtest, sell when a bar's low reaches the entry price less --atr-mult times the ATR "
        "(--atr-period bars) on the bar the buy signal came on; that distance is fixed when the position "
        "opens, and a later buy moves the level with the average entry price only. A buy signal with no "
        "ATR yet (or an ATR of 0) is skipped and counted in the report. Works next to --stop-loss, "
        "--trailing-stop and --take-profit: the highest stop level is used (on a tie the stop, then the "
        "trail, then atr) and it wins over the target if a bar touches both; its fills say atr. With "
        "--risk-pct a position's first buy is sized on the same distance the stop uses; a gap, slippage, fees "
        "or a later buy (sized on its own signal bar's ATR) can still lose more than the risk (reads a candle "
        "file; cannot be combined with --resample yet)",
    )
    cooldown = parser.add_argument(
        "--cooldown",
        type=int,
        default=None,
        metavar="N",
        help="with --backtest and one of --stop-loss, --trailing-stop or --atr-stop: after a sell by one of "
        "them, no buy can fill for the next N bars (a whole number of at least 1). A buy due then is dropped, "
        "not delayed, and counted in the report. A --take-profit or signal sell starts no cooldown",
    )
    min_hold = parser.add_argument(
        "--min-hold",
        type=int,
        default=None,
        metavar="N",
        help="with --backtest, drop a signal sell due before the position has been held N bars (a whole number of "
        "at least 1), counted from the buy that opened it; a later buy does not restart the count. The sell is "
        "dropped, not delayed, and counted in the report. Stops, the target, --max-hold and --max-drawdown still "
        "sell inside the window. Needs no stop and works with a close-only file and with --resample (N counts "
        "the resampled bars)",
    )
    max_hold = parser.add_argument(
        "--max-hold",
        type=int,
        default=None,
        metavar="N",
        help="with --backtest, sell the whole position N bars after the buy that opened it (a whole number of at "
        "least 1), at that bar's fill price (close, or open with --fill open); a later buy does not restart the "
        "count. A bar that already has a fill keeps it and the sale waits for the next bar. Its fills say time; "
        "it starts no cooldown. Needs no stop and works with a close-only file and with --resample (N counts "
        "the resampled bars)",
    )
    # Hidden exact aliases: "--ma", "--max" and "--max-" meant --max-hold (argparse abbreviation) before
    # --max-drawdown existed, and an exact option string wins over the now-ambiguous prefix. Their errors
    # still say --max-hold.
    for short_form in ("--ma", "--max", "--max-"):
        max_hold_alias = parser.add_argument(short_form, dest="max_hold", type=int, default=None, help=argparse.SUPPRESS)
        max_hold_alias.option_strings = ["--max-hold"]
    max_drawdown = parser.add_argument(
        "--max-drawdown",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, halt when the account value at a close is PCT%% or more below its highest value at "
        "a close so far (above 0, below 100): from the next bar on no buy can fill (each buy due is dropped and "
        "counted in the report), and a position still held is sold on the next bar at its fill price (close, or "
        "open with --fill open). A signal, stop, trail, ATR stop, target or time sale on that bar goes first and "
        "keeps its reason; otherwise the fill says drawdown. It starts no cooldown. Needs no stop and works with "
        "a close-only file and with --resample",
    )
    breakeven = parser.add_argument(
        "--breakeven",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, once the high of a bar after the entry bar is at or above the entry price (the "
        "average price paid) plus PCT%% (above 0), sell on a later bar whose low reaches the entry price (at "
        "that price, or at the bar's open if it opens at or below it); no allowance is made for fees or "
        "slippage. A later buy moves the level with the average price. Works next to --stop-loss, "
        "--trailing-stop and --atr-stop (the highest stop level is used; on a tie the stop, then the trail, "
        "then atr, then breakeven) and wins over --take-profit if a bar touches both; at or above "
        "--take-profit it can never act, unless a later buy into the position moves the average (a lower-priced "
        "one with close fills, any one with --fill open). Its fills say breakeven. It counts as a stop for --cooldown: "
        "--cooldown may be used with it alone, and a breakeven sale starts the cooldown (reads a candle "
        "file; cannot be combined with --resample yet)",
    )
    max_losses = parser.add_argument(
        "--max-losses",
        type=int,
        default=None,
        metavar="N",
        help="with --backtest, after N losing round trips in a row (a whole number of at least 1) no buy can fill "
        "for the rest of the run; each buy due then is dropped and counted in the report. A round trip loses when "
        "its profit after costs is below 0; any other, one at exactly 0.00 included, resets the count. Nothing is "
        "held when the halt starts, so nothing is sold because of it. Needs no stop and works with a close-only "
        "file and with --resample",
    )
    scale_out = parser.add_argument(
        "--scale-out",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, sell half the shares held (rounded down) once per position when the high of a bar "
        "after the entry bar reaches the entry price (the average cost of the shares held) plus PCT%% (above 0): "
        "at that price, or at the bar's open if it opens at or above it. The rest stays open. Any other fill on "
        "the bar goes first and the scale-out is skipped on that bar; with close fills a --max-hold or "
        "--max-drawdown sale waits for it. A partial sale is not a round trip: its proceeds count in the round "
        "trip the rest completes. Its fills say scale_out. It starts no cooldown, --min-hold does not hold it "
        "back, and it needs no other exit option (reads a candle file; cannot be combined with --resample yet)",
    )
    add_on = parser.add_argument(
        "--add-on",
        type=float,
        default=None,
        metavar="PCT",
        help="with --backtest, while a position is held, buy more on the next bar after a close that is PCT%% or "
        "more above the fill price of the latest buy into the position (slippage included; above 0, decimals "
        "allowed, not inf), up to --max-adds times per position (default 1). The add-on is sized like any buy "
        "(all the cash, --position-size, --risk-pct), so with the default all-cash sizing it usually gets 0 "
        "shares: it is then skipped and counted in the report, is not one of the --max-adds and leaves the "
        "latest buy price as it was. Every buy into the position, a signal buy too, becomes the new latest buy "
        "price; only add-ons count towards --max-adds. A BUY or SELL signal on that close drops it (a SELL even "
        "when --min-hold holds the sale back), and so does any other fill on the next bar that is known when it "
        "would fill: with close fills a stop, trail, ATR stop, breakeven or target sale during the bar, the "
        "signal fill, a --scale-out partial sale, a --max-hold or a --max-drawdown sale; with --fill open the "
        "signal fill, a gap through a stop or the target at the open, or a --max-hold or --max-drawdown sale "
        "at the open. With --fill open it fills at the open, before the bar's range is checked, so no stop, "
        "target or scale-out acts on that bar. It raises the average entry price (the stop, target, breakeven "
        "and scale-out levels follow it), its shares and cost go into the same round trip, and it restarts "
        "neither --min-hold nor --max-hold. The close is compared in floating point: after a buy at 11, "
        "--add-on 10 needs a close above 12.10, and a close of exactly 12.10 does not set it off. Its fills say "
        "add_on. Needs no candle file and works with a close-only file and with --resample",
    )
    max_adds = parser.add_argument(
        "--max-adds",
        type=int,
        default=None,
        metavar="N",
        help="with --add-on, the most add-on buys per position (a whole number of at least 1; default 1); the "
        "count starts again with each new position",
    )
    parser.add_argument(
        "--export",
        default=None,
        metavar="FILE",
        help="with --backtest, write one CSV row per bar (account value, signal, fills) to FILE",
    )
    # Hidden exact aliases: "--e", "--ex" and "--exp" meant --export (argparse abbreviation) before --explain
    # existed, and an exact option string wins over the now-ambiguous prefix. Their errors still say --export.
    for short_form in ("--e", "--ex", "--exp"):
        export_alias = parser.add_argument(short_form, dest="export", default=None, help=argparse.SUPPRESS)
        export_alias.option_strings = ["--export"]
    parser.add_argument(
        "--fill",
        choices=FILLS,
        default=None,
        help="with --backtest, the price of the next bar a signal is filled at (default: close); "
        "open reads the file as a candle file and cannot be combined with --resample yet",
    )
    parser.add_argument(
        "--resample",
        choices=PERIODS,
        default=None,
        help="reduce daily bars to weekly or monthly bars before analysing (needs a 'date' column)",
    )
    # Hidden exact alias: "--re" meant --resample (argparse abbreviation) before --report existed.
    # Its errors still say --resample.
    resample_alias = parser.add_argument("--re", dest="resample", choices=PERIODS, default=None, help=argparse.SUPPRESS)
    resample_alias.option_strings = ["--resample"]
    parser.add_argument(
        "--strategy",
        choices=strategy_names(),
        default=None,
        help=f"rule traded by --backtest (default: {DEFAULT_STRATEGY}); does not change the Signal line",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="override a strategy parameter in --backtest, e.g. window=10 (repeatable)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="with --backtest, also print the risk and return statistics block",
    )
    trade_list = parser.add_argument(
        "--trade-list",
        action="store_true",
        default=None,  # None means "not written", like the other backtest options
        help="with --backtest, print one row per completed round trip after the report (after the risk and return "
        "block with --stats, before --chart): entry bar, exit bar, bars held, shares bought, outlay, proceeds, "
        "P/L, return %% and the reason of the sale that completed it, plus a row for a position still held at the "
        "end (unrealized: marked at the last close, no selling costs). Its footer repeats the Round trips numbers. "
        "Needs no candle file and works with --resample; with --json the backtest object gets a trade_list array "
        "instead",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="FILE",
        help=f"read defaults from an INI file; flags win over the file (no file is read unless this is given "
        f"or ${CONFIG_ENV_VAR} is set)",
    )
    # Hidden exact alias: "--co" meant --config (argparse abbreviation) before --cooldown existed.
    # Its errors still say --config.
    config_alias = parser.add_argument("--co", dest="config", default=None, help=argparse.SUPPRESS)
    config_alias.option_strings = ["--config"]
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as one JSON object on stdout instead of text (cannot be combined with --chart)",
    )
    parser.add_argument(
        "--chart",
        action="store_true",
        help="print a text chart of the closes after the report (fills marked B and S with --backtest)",
    )
    explain = parser.add_argument(
        "--explain",
        action="store_true",
        help="print one sentence right after the Signal line explaining it: the decision, the --short and --long "
        "SMA on the last bar and on the bar before, and why (always the SMA crossover, whatever --strategy is; "
        "needs no candle file; cannot be combined with --scan)",
    )
    parser.add_argument(
        "--candles",
        action="store_true",
        help="read the file as a candle file (date, open, high, low, close, volume) and analyse its closes; "
        "cannot be combined with --resample yet",
    )
    parser.add_argument(
        "--scan",
        default=None,
        metavar="FOLDER",
        help="instead of one price file, give the combined score of every .csv file directly inside FOLDER "
        "(cannot be combined with a price file or backtest options)",
    )
    # Hidden exact aliases: "--sc" and "--sca" meant --scan (argparse abbreviation) before --scale-out existed,
    # and an exact option string wins over the now-ambiguous prefix. Their errors still say --scan.
    for short_form in ("--sc", "--sca"):
        scan_alias = parser.add_argument(short_form, dest="scan", default=None, help=argparse.SUPPRESS)
        scan_alias.option_strings = ["--scan"]
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        metavar="N",
        help="with --scan, keep only the files scoring N or more",
    )
    # Hidden exact alias: "--m" meant --min-score (argparse abbreviation) before --max-hold existed.
    # Its errors still say --min-score.
    min_score_alias = parser.add_argument("--m", dest="min_score", type=int, default=None, help=argparse.SUPPRESS)
    min_score_alias.option_strings = ["--min-score"]
    # Hidden exact aliases: "--mi", "--min" and "--min-" meant --min-score (argparse abbreviation) before
    # --min-hold existed, and an exact option string wins over the now-ambiguous prefix. Their errors
    # still say --min-score.
    for short_form in ("--mi", "--min", "--min-"):
        min_score_alias = parser.add_argument(
            short_form, dest="min_score", type=int, default=None, help=argparse.SUPPRESS
        )
        min_score_alias.option_strings = ["--min-score"]
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="with --scan, show only the first N rows (after --min-score)",
    )
    parser.add_argument(
        "--report",
        default=None,
        metavar="FILE",
        help="with --scan, also write a Markdown report to FILE (the screen output does not change)",
    )
    # Keep the usage line (printed with --help and with every usage error) exactly as it was before
    # --trailing-stop existed; it, the risk sizing options, --atr-stop, --cooldown, --min-hold, --max-hold,
    # --max-drawdown, --breakeven, --max-losses, --scale-out, --add-on, --max-adds, --trade-list and --explain are
    # still listed, with their help, in --help.
    unlisted = (
        trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven,
        max_losses, scale_out, add_on, max_adds, trade_list, explain,
    )
    helps = [action.help for action in unlisted]
    for action in unlisted:
        action.help = argparse.SUPPRESS
    parser.usage = parser.format_usage()[len("usage: ") :].rstrip("\n").replace("%", "%%")
    for action, text in zip(unlisted, helps):
        action.help = text
    return parser


def find_config_path(args, environ=None):
    """Path of the config file to read, or None.

    ``--config`` wins. Otherwise the value of ``TRADING_ASSISTANT_CONFIG`` is
    used when it is set and not blank. Nothing else is ever looked for.
    """
    if args.config is not None:
        return args.config
    env = (os.environ if environ is None else environ).get(CONFIG_ENV_VAR, "").strip()
    return env or None


def apply_config(args, config):
    """Fill options the user did not write on the command line from ``config``.

    ``config`` is the result of ``config.load_config``. Flags win; the file
    comes next; built-in defaults are left for ``validate_args``. Backtest-only
    settings (cash, fee, fee_pct, slippage, position_size, fill, stop_loss,
    take_profit, trailing_stop, risk_pct, atr_mult, atr_period, atr_stop,
    cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, strategy, stats,
    trade_list, strategy parameters)
    are used
    only when
    ``args.backtest`` is true, and the scan settings (top, min_score) only
    with ``--scan``. ``atr_mult`` and ``atr_period`` are further used only when
    ``risk_pct`` is set or the ATR stop is on (by the file or the flag), and
    ``cooldown`` only when a stop is on (``stop_loss``, ``trailing_stop`` or the
    ATR stop, by the file or the flags, or ``--breakeven``); an unused ``cooldown`` is kept in
    ``args.config_cooldown_unused`` so ``validate_args`` still checks its range.
    ``min_hold`` needs no stop: with ``--backtest`` it is used whenever
    ``--min-hold`` is not written; ``max_hold`` likewise, unless
    ``--max-hold`` is written; ``max_drawdown`` likewise, unless
    ``--max-drawdown`` is written, ``breakeven`` unless ``--breakeven``
    is written (it then counts as a stop for ``cooldown``), ``max_losses``
    unless ``--max-losses`` is written, and ``scale_out`` unless ``--scale-out``
    is written (it is not a stop, so it does not count for ``cooldown``), and ``add_on`` unless ``--add-on`` is
    written. ``max_adds`` is used unless ``--max-adds`` is written, and only when ``add_on`` or ``--add-on`` is
    there; otherwise it is kept in ``args.config_max_adds_unused`` so ``validate_args`` still checks its range,
    as for ``cooldown``.
    ``atr_stop``, ``stats``, ``trade_list`` and ``explain`` are switches: ``yes`` in the file turns them on,
    ``no`` leaves them as the command line has them (a flag can only turn them
    on, so the flag wins over ``no``). ``explain`` needs no ``--backtest`` and is
    ignored with ``--scan``. Nothing is range-checked here.
    """
    cli = config["cli"]
    for name in ("short", "long", "rsi_period"):
        if name in cli and not getattr(args, name + "_given", False):
            setattr(args, name, cli[name])
    if getattr(args, "scan", None) is not None:
        for name in ("top", "min_score"):  # these flags default to None, so None means "not written"
            if name in cli and getattr(args, name) is None:
                setattr(args, name, cli[name])
    if cli.get("explain") and getattr(args, "scan", None) is None:
        # Like stats: "yes" turns it on, "no" leaves args.explain as the command line set it. Unlike stats it
        # needs no --backtest; with --scan it is ignored like the other keys that do not apply there.
        args.explain = True
    if not args.backtest:
        return args
    backtest_only = (
        "cash", "fee", "fee_pct", "slippage", "position_size", "fill", "stop_loss", "take_profit", "trailing_stop",
        "strategy", "risk_pct",
        "min_hold",  # needs no stop, so unlike cooldown it is always used with --backtest; the flag wins
        "max_hold",  # likewise
        "max_drawdown",  # likewise
        "breakeven",  # likewise; set before the cooldown check below, which counts it as a stop
        "max_losses",  # needs no stop, like min_hold; the flag wins
        "scale_out",  # needs no other exit; the flag wins. Not a stop, so not part of the cooldown check below
        "add_on",  # needs no other option; the flag wins
    )
    for name in backtest_only:  # these flags default to None, so None means "not written"
        if name in cli and getattr(args, name) is None:
            setattr(args, name, cli[name])
    if cli.get("atr_stop"):
        # Like stats: "yes" turns it on; "no" leaves args.atr_stop as the command line set it
        # (None when --atr-stop is not written, so the --resample and --scan rules see no ATR stop).
        args.atr_stop = True
    if args.risk_pct is not None or args.atr_stop:
        # The file's atr_mult/atr_period only apply with risk sizing or the ATR stop (from the file
        # or the flag); without either they are ignored quietly, like backtest keys without --backtest.
        for name in ("atr_mult", "atr_period"):
            if name in cli and getattr(args, name) is None:
                setattr(args, name, cli[name])
    if "max_adds" in cli and args.max_adds is None:
        if args.add_on is not None:  # from the file (just above) or the flag
            args.max_adds = cli["max_adds"]
        else:
            # Like cooldown without a stop: without add_on (from the file or the flag) the file's max_adds is
            # ignored quietly, but its range is still checked (by validate_args), so a value below 1 is an error.
            args.config_max_adds_unused = cli["max_adds"]
    if "cooldown" in cli and args.cooldown is None:
        # --breakeven has no config key yet; written on the command line it counts as a stop here too.
        if args.stop_loss is not None or args.trailing_stop is not None or args.atr_stop or args.breakeven is not None:
            args.cooldown = cli["cooldown"]
        else:
            # Like atr_mult/atr_period: without a stop (from the file or the flags) the file's cooldown is
            # ignored quietly. Its range is still checked (by validate_args), so a bad value is an error
            # either way.
            args.config_cooldown_unused = cli["cooldown"]
    if cli.get("stats"):
        args.stats = True
    if cli.get("trade_list"):
        # Like stats: "yes" turns it on; "no" leaves args.trade_list as the command line set it.
        args.trade_list = True
    strategy = args.strategy or DEFAULT_STRATEGY
    given = {text.partition("=")[0].strip() for text in args.param or []}
    from_file = []
    for key, value in config["strategy"].get(strategy, {}).items():
        if key in given:
            continue
        if strategy == "sma_cross" and key in ("short", "long") and getattr(args, key + "_given", False):
            continue
        from_file.append(f"{key}={value!r}")
    if from_file:
        args.param = from_file + list(args.param or [])
    return args


def check_windows(short, long, rsi_period=DEFAULT_RSI_PERIOD):
    """Raise ValueError for window values the indicator code would refuse.

    The checks mirror the rules in `indicators._check_window` and
    `signals.crossover_signal`. Shared by the CLI and the web page so both
    give the same message.
    """
    if short < 1:
        raise ValueError("--short must be at least 1")
    if long < 1:
        raise ValueError("--long must be at least 1")
    if rsi_period < 1:
        raise ValueError("--rsi-period must be at least 1")
    if short >= long:
        raise ValueError(f"--short ({short}) must be smaller than --long ({long})")


def check_scan_trim(min_score=None, top=None):
    """Raise ValueError for a --top (or --min-score) the scan would refuse. Shared by the CLI and the web page."""
    if top is not None and top < 1:
        raise ValueError(f"--top must be at least 1, got {top}")


def check_costs(cash=None, fee=None, fee_pct=None, slippage=None, position_size=None):
    """Raise ValueError for a starting cash, cost, slippage or position size setting that is out of range."""
    if cash is not None and not cash > 0:
        raise ValueError(f"--cash must be positive, got {cash:g}")
    if fee is not None and fee < 0:
        raise ValueError(f"--fee must not be negative, got {fee:g}")
    if fee_pct is not None and not 0 <= fee_pct < 100:
        raise ValueError(f"--fee-pct must be between 0 and 100 (exclusive), got {fee_pct:g}")
    if slippage is not None and not 0 <= slippage < 100:
        raise ValueError(f"--slippage must be between 0 and 100 (exclusive), got {slippage:g}")
    if position_size is not None and not 0 < position_size <= 1:
        raise ValueError(f"--position-size must be above 0 and at most 1, got {position_size:g}")


def check_risk(risk_pct=None, atr_mult=None, atr_period=None, atr_stop=False):
    """Raise ValueError for risk sizing settings the command line refuses. Shared by the CLI and the web page.

    ``atr_mult`` and ``atr_period`` need ``risk_pct`` or ``atr_stop`` (the web
    page has no ATR stop yet and leaves it False); then ``risk_pct`` must be
    above 0 and at most 100, ``atr_mult`` above 0 and ``atr_period`` (a whole
    number) at least 1. The messages name the command-line flags.
    """
    if risk_pct is None and not atr_stop:
        for flag, value in (("--atr-mult", atr_mult), ("--atr-period", atr_period)):
            if value is not None:
                raise ValueError(f"{flag} only makes sense together with --risk-pct or --atr-stop")
    if risk_pct is not None and not 0 < risk_pct <= 100:
        raise ValueError(f"--risk-pct must be above 0 and at most 100, got {risk_pct:g}")
    if atr_mult is not None and not atr_mult > 0:
        raise ValueError(f"--atr-mult must be above 0, got {atr_mult:g}")
    if atr_period is not None and atr_period < 1:
        raise ValueError(f"--atr-period must be a whole number of at least 1, got {atr_period}")


def check_cooldown(cooldown=None, stops=False):
    """Raise ValueError for a cooldown the command line refuses.

    ``cooldown`` needs a stop (``stops`` true: --stop-loss, --trailing-stop or
    --atr-stop is on); then it must be a whole number of at least 1. ``None``
    means the option is off and is always fine. The messages name the
    command-line flags.
    """
    if cooldown is None:
        return
    if not stops:
        raise ValueError("--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop")
    if cooldown < 1:
        raise ValueError(f"--cooldown must be a whole number of at least 1, got {cooldown}")


def check_max_hold(max_hold=None):
    """Raise ValueError for a --max-hold the command line refuses: it must be a whole number of at least 1.

    ``None`` means the option is off and is always fine. It needs no stop.
    """
    if max_hold is not None and max_hold < 1:
        raise ValueError(f"--max-hold must be a whole number of at least 1, got {max_hold}")


def check_min_hold(min_hold=None):
    """Raise ValueError for a --min-hold the command line refuses: it must be a whole number of at least 1.

    ``None`` means the option is off and is always fine. It needs no stop. 1 is accepted and skips nothing.
    """
    if min_hold is not None and min_hold < 1:
        raise ValueError(f"--min-hold must be a whole number of at least 1, got {min_hold}")


def check_max_drawdown(max_drawdown=None):
    """Raise ValueError for a --max-drawdown the command line refuses: it must be above 0 and below 100.

    ``None`` means the option is off and is always fine. It needs no stop.
    """
    if max_drawdown is not None and not 0 < max_drawdown < 100:
        raise ValueError(f"--max-drawdown must be above 0 and below 100, got {max_drawdown:g}")


def check_max_losses(max_losses=None):
    """Raise ValueError for a --max-losses the command line refuses: it must be a whole number of at least 1.

    ``None`` means the option is off and is always fine. It needs no stop.
    """
    if max_losses is not None and max_losses < 1:
        raise ValueError(f"--max-losses must be a whole number of at least 1, got {max_losses}")


def check_add_on(add_on=None, max_adds=None):
    """Raise ValueError for an --add-on or --max-adds the command line refuses.

    ``--add-on`` must be above 0 and finite (0, a negative number, nan and inf are refused); ``--max-adds`` must be
    a whole number of at least 1 and needs ``--add-on``. ``None`` means the option was not given.
    """
    if add_on is not None and not add_on > 0:
        raise ValueError(f"--add-on must be above 0, got {add_on:g}")
    if add_on is not None and not math.isfinite(add_on):
        # Like --scale-out: inf would never be reached.
        raise ValueError(f"--add-on must be a finite number, got {add_on:g}")
    if max_adds is not None and add_on is None:
        raise ValueError("--max-adds only makes sense together with --add-on")
    if max_adds is not None and max_adds < 1:
        raise ValueError(f"--max-adds must be a whole number of at least 1, got {max_adds}")


def validate_args(parser, args):
    """Turn rule violations into usage errors.

    `parser.error` prints the usage line plus the message to stderr and
    exits with status 2, so the user gets a clean message instead of a
    traceback.
    """
    try:
        check_windows(args.short, args.long, args.rsi_period)
    except ValueError as exc:
        parser.error(str(exc))
    for name in ("min_score", "top", "report"):
        if getattr(args, name, None) is not None:
            parser.error(f"--{name.replace('_', '-')} only makes sense together with --scan")
    if args.candles and args.resample is not None:
        parser.error("--candles cannot be combined with --resample yet")
    if args.json and args.chart:
        parser.error("--chart cannot be combined with --json (the JSON output is one object and nothing else)")
    if not args.backtest:
        for name in (
            "cash", "fee", "fee_pct", "slippage", "position_size", "export", "fill", "stop_loss", "take_profit",
            "trailing_stop", "risk_pct", "atr_stop", "cooldown", "min_hold", "max_hold", "max_drawdown", "breakeven",
            "max_losses", "scale_out", "add_on", "max_adds", "trade_list",
        ):
            if getattr(args, name) is not None:
                flag = "--" + name.replace("_", "-")
                parser.error(f"{flag} only makes sense together with --backtest")
    if args.risk_pct is None and not args.atr_stop:
        # Only check_risk's "needs --risk-pct" rule can fire here; the ranges are checked below,
        # after the other settings, as they always were.
        try:
            check_risk(None, args.atr_mult, args.atr_period)
        except ValueError as exc:
            parser.error(str(exc))
    stops = (
        args.stop_loss is not None or args.trailing_stop is not None or bool(args.atr_stop)
        or args.breakeven is not None
    )
    if not stops:
        # Likewise only check_cooldown's "needs a stop" rule can fire here; its range is checked below.
        try:
            check_cooldown(args.cooldown)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        check_costs(args.cash, args.fee, args.fee_pct, args.slippage, args.position_size)
    except ValueError as exc:
        parser.error(str(exc))
    if args.export is not None and not args.export.strip():
        parser.error("--export needs a file name")
    if args.fill == "open" and args.resample is not None:
        parser.error("--fill open cannot be combined with --resample yet")
    if args.stop_loss is not None and not 0 < args.stop_loss < 100:
        parser.error(f"--stop-loss must be between 0 and 100 (both exclusive), got {args.stop_loss:g}")
    if args.take_profit is not None and not args.take_profit > 0:
        parser.error(f"--take-profit must be positive, got {args.take_profit:g}")
    if args.trailing_stop is not None and not 0 < args.trailing_stop < 100:
        parser.error(f"--trailing-stop must be between 0 and 100 (both exclusive), got {args.trailing_stop:g}")
    if args.breakeven is not None and not args.breakeven > 0:
        parser.error(f"--breakeven must be above 0, got {args.breakeven:g}")
    if args.breakeven is not None and not math.isfinite(args.breakeven):
        # Unlike --take-profit, and like the config key and the API: inf would never arm the stop.
        parser.error(f"--breakeven must be a finite number, got {args.breakeven:g}")
    if args.scale_out is not None and not args.scale_out > 0:
        parser.error(f"--scale-out must be above 0, got {args.scale_out:g}")
    if args.scale_out is not None and not math.isfinite(args.scale_out):
        # Like --breakeven: inf would never be reached.
        parser.error(f"--scale-out must be a finite number, got {args.scale_out:g}")
    try:
        check_add_on(args.add_on, args.max_adds)
        unused = getattr(args, "config_max_adds_unused", None)
        if unused is not None:
            check_add_on(1.0, unused)  # only the range: the file's max_adds is not used
    except ValueError as exc:
        parser.error(str(exc))
    try:
        check_risk(args.risk_pct, args.atr_mult, args.atr_period, bool(args.atr_stop))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        check_cooldown(args.cooldown, stops)
        unused = getattr(args, "config_cooldown_unused", None)
        if unused is not None:
            check_cooldown(unused, stops=True)  # only the range: the file's cooldown is not used
    except ValueError as exc:
        parser.error(str(exc))
    try:
        check_min_hold(args.min_hold)
        check_max_hold(args.max_hold)
        check_max_drawdown(args.max_drawdown)
        check_max_losses(args.max_losses)
    except ValueError as exc:
        parser.error(str(exc))
    for name in ("stop_loss", "take_profit", "trailing_stop", "risk_pct", "atr_stop", "breakeven", "scale_out"):
        if getattr(args, name) is not None and args.resample is not None:
            parser.error(f"--{name.replace('_', '-')} cannot be combined with --resample yet")
    if args.stats and not args.backtest:
        parser.error("--stats only makes sense together with --backtest")
    for name in ("strategy", "param"):
        if not args.backtest and getattr(args, name) is not None:
            parser.error(f"--{name} only makes sense together with --backtest")
    if args.strategy is None:
        args.strategy = DEFAULT_STRATEGY
    overrides = {}
    try:
        for text in args.param or []:
            key, value = parse_param(text)
            if key in overrides:
                raise ValueError(f"--param {key} given more than once")
            overrides[key] = value
        if args.strategy == "sma_cross":
            for key in ("short", "long"):
                if key in overrides and getattr(args, key + "_given", False) and overrides[key] != getattr(args, key):
                    raise ValueError(
                        f"--param {key}={overrides[key]} contradicts --{key} {getattr(args, key)}; give only one"
                    )
        resolve_params(args.strategy, overrides)
    except ValueError as exc:
        parser.error(str(exc))
    args.strategy_params = overrides
    if args.cash is None:
        args.cash = DEFAULT_CASH
    if args.fee is None:
        args.fee = 0.0
    if args.fee_pct is None:
        args.fee_pct = 0.0
    if args.fill is None:
        args.fill = "close"
    if args.slippage is None:
        args.slippage = 0.0
    return args


def summarise(
    closes,
    short=DEFAULT_SHORT,
    long=DEFAULT_LONG,
    rsi_period=DEFAULT_RSI_PERIOD,
    backtest=False,
    cash=DEFAULT_CASH,
    fee=0.0,
    fee_pct=0.0,
    strategy=DEFAULT_STRATEGY,
    strategy_params=None,
    fill="close",
    opens=None,
    slippage_pct=0.0,
    position_size=None,
    stop_pct=None,
    take_profit_pct=None,
    highs=None,
    lows=None,
    trail_pct=None,
    risk_pct=None,
    atr_mult=2.0,
    atr_period=14,
    atr_stop=False,
    cooldown=0,
    max_hold=0,
    max_drawdown_limit_pct=None,
    breakeven_pct=None,
    min_hold=0,
    max_losses=0,
    scale_out_pct=None,
    add_on_pct=None,
    max_adds=None,
):
    """Work out everything the report shows for ``closes``, as raw values.

    Returns a dict with ``bars``, ``last_close``, ``signal``, ``rsi`` (None
    when there are too few bars), ``rsi_label``, ``short``, ``long`` and
    ``result`` (the BacktestResult when ``backtest`` is true, else None).
    ``report_lines`` turns it into the text report and ``report_data`` into
    the ``--json`` object, so the two cannot drift apart.

    ``fill``, ``opens``, ``slippage_pct``, ``position_size``, ``stop_pct``,
    ``take_profit_pct``, ``highs``, ``lows``, ``trail_pct``, ``risk_pct``, ``atr_mult``,
    ``atr_period``, ``atr_stop`` and ``cooldown`` are passed to the backtest
    (``fill="open"`` fills at the next bar's open and needs ``opens``;
    ``slippage_pct`` moves buy fills up and sell fills down; ``position_size``
    caps each buy; ``risk_pct`` sizes each buy by ATR risk; ``atr_stop`` adds
    the ATR stop; ``cooldown`` blocks buys for that many bars after a stop exit;
    ``max_hold`` sells a position that many bars after its first buy (closes only is enough);
    ``min_hold`` drops a signal sell due before a position is that many bars old (closes only is enough);
    ``max_drawdown_limit_pct`` halts the run at that drawdown (closes only is enough);
    ``max_losses`` halts buying after that many losing round trips in a row (closes only is enough);
    ``add_on_pct`` and ``max_adds`` buy more of a position after a rise (closes only is enough);
    ``scale_out_pct`` sells half the position once; the exits, ``scale_out_pct`` and ``risk_pct`` need ``highs`` and
    ``lows``). Raises ValueError from the
    backtest for bad prices or settings.
    """
    signal = crossover_signal(closes, short=short, long=long)
    value, label = rsi_filter(closes, period=rsi_period)
    result = None
    if backtest:
        result = run_backtest(
            closes,
            initial_cash=cash,
            short=short,
            long=long,
            fee=fee,
            fee_pct=fee_pct,
            strategy=strategy,
            strategy_params=strategy_params,
            fill=fill,
            opens=opens,
            slippage_pct=slippage_pct,
            position_size=position_size,
            stop_pct=stop_pct,
            take_profit_pct=take_profit_pct,
            highs=highs,
            lows=lows,
            trail_pct=trail_pct,
            risk_pct=risk_pct,
            atr_mult=atr_mult,
            atr_period=atr_period,
            atr_stop=atr_stop,
            cooldown=cooldown,
            max_hold=max_hold,
            max_drawdown_limit_pct=max_drawdown_limit_pct,
            breakeven_pct=breakeven_pct,
            min_hold=min_hold,
            max_losses=max_losses,
            scale_out_pct=scale_out_pct,
            add_on_pct=add_on_pct,
            max_adds=max_adds,
        )
    return {
        "bars": len(closes),
        "last_close": closes[-1],
        "signal": signal,
        "rsi": value,
        "rsi_label": label,
        "short": short,
        "long": long,
        "result": result,
    }


def report_lines(summary, explanation=None):
    """The text report for a ``summarise`` result (without the disclaimer).

    ``explanation`` (the ``--explain`` sentence), when given, is its own line right after the Signal line.
    """
    value, result = summary["rsi"], summary["result"]
    rsi_text = "n/a" if value is None else f"{value:.1f} ({summary['rsi_label']})"
    lines = [
        f"Bars:    {summary['bars']}",
        f"Last:    {summary['last_close']:.2f}",
        f"Signal:  {summary['signal']}",
        f"RSI:     {rsi_text}",
    ]
    if explanation is not None:
        lines.insert(3, explanation)
    if result is not None:
        # For sma_cross, --param short=/long= may have set the windows actually traded.
        lines += format_result(
            result,
            result.strategy_params.get("short", summary["short"]),
            result.strategy_params.get("long", summary["long"]),
        )
    return lines


def analyse(closes, *args, explanation=None, **kwargs):
    """Build the report lines for ``closes`` and return ``(lines, result)``.

    Takes the same arguments as ``summarise``, plus ``explanation`` (the
    ``--explain`` sentence), which ``report_lines`` puts right after the Signal
    line when given. ``result`` is the BacktestResult when ``backtest`` is
    true, else None. Raises ValueError from the backtest for bad prices or
    settings. Used by both the CLI and the web page, so they print exactly the
    same report.
    """
    summary = summarise(closes, *args, **kwargs)
    return report_lines(summary, explanation), summary["result"]


def _finite_or_none(value):
    """The value, or None for a number that is undefined (prints as n/a) or not finite."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return value


TRADE_LIST_KEYS = ("open", "entry_bar", "exit_bar", "bars_held", "shares", "outlay", "proceeds", "pnl", "return_pct",
                   "reason")


def trade_list_data(result):
    """The ``trade_list`` array of ``--json`` (and of ``POST /api/backtest``): one object per trade list row."""
    return [{key: row[key] for key in TRADE_LIST_KEYS} for row in trade_list_rows(result)]


def report_data(summary, stats=False, export=None, trade_list=False, explanation=None):
    """The ``--json`` object for a ``summarise`` result: the text report's information as plain values.

    Numbers are unrounded (the text report rounds them for display). Top level:
    ``bars``, ``last_close``, ``signal``, ``rsi`` (null when the text says n/a)
    and ``rsi_label`` (likewise), then ``backtest`` when a backtest was run,
    and ``disclaimer``. ``explanation`` (the ``--explain`` sentence), when
    given, is an ``explanation`` key right after ``signal``. ``stats=True`` adds ``backtest.stats`` with the
    "Risk and return" numbers (null for n/a); ``export`` (``(path, rows)``)
    adds ``backtest.export``. ``backtest.trailing_stop_pct`` (right after
    ``take_profit_pct``) is there only when a trailing stop was used.
    ``backtest.risk_pct`` (right after ``position_size``) is there only when
    risk sizing was used. ``backtest.atr_mult`` and ``atr_period`` (right after
    ``risk_pct``, or after ``position_size`` without it) and
    ``backtest.risk_skipped_buys`` (right after ``sells``) are there when risk
    sizing or the ATR stop was used. ``backtest.atr_stop`` (``true``; right
    after ``trailing_stop_pct``, or after ``take_profit_pct`` without it) is
    there only when the ATR stop was used. ``backtest.scale_out_pct`` (right
    after ``breakeven_pct``, or ``atr_stop``, ``trailing_stop_pct`` or
    ``take_profit_pct``) and ``backtest.scale_out_exits`` (right after
    ``breakeven_exits``, or ``risk_skipped_buys`` or ``sells``) are there only
    when the scale-out was used. ``backtest.add_on_pct`` and ``backtest.max_adds``
    (right after ``scale_out_pct``, or where it would be) and
    ``backtest.add_on_buys`` and ``backtest.add_on_skipped_buys`` (right after
    ``scale_out_exits``, or where it would be) are there only when the add-ons
    were used. ``backtest.breakeven_pct`` (right
    after ``atr_stop``, or ``trailing_stop_pct``, or ``take_profit_pct``) and
    ``backtest.breakeven_exits`` (right after ``risk_skipped_buys``, or
    ``sells``) are there only when the breakeven stop was used.
    ``backtest.cooldown_bars`` (right
    after the exit and add-on settings: ``max_adds``, ``scale_out_pct``, ``breakeven_pct``, ``atr_stop``,
    ``trailing_stop_pct`` or ``take_profit_pct``, the last of those present) and
    ``backtest.cooldown_skipped_buys`` (right after ``sells``, or after ``add_on_skipped_buys``,
    ``scale_out_exits``, ``breakeven_exits`` or ``risk_skipped_buys`` when one is there) are there only when a cooldown
    was used. ``backtest.max_hold_bars`` (right after ``min_hold_bars``,
    ``cooldown_bars``, or the exit settings) and ``backtest.time_exits`` (right
    after ``min_hold_skipped_sells``, ``cooldown_skipped_buys``,
    ``risk_skipped_buys`` or ``sells``) are there
    only when a maximum holding time was used. ``backtest.min_hold_bars`` (right
    before ``max_hold_bars``, or where it would be) and
    ``backtest.min_hold_skipped_sells`` (right before ``time_exits``, or where
    it would be) are there only when a minimum holding time was used.
    ``backtest.max_drawdown_limit_pct``
    (right after ``max_hold_bars``, or ``min_hold_bars``, ``cooldown_bars``, or
    the exit settings) and ``backtest.drawdown_halt_bar`` (null when the halt
    never triggered) and ``backtest.drawdown_skipped_buys`` (right after
    ``time_exits``, or ``min_hold_skipped_sells``, ``cooldown_skipped_buys``,
    ``risk_skipped_buys`` or ``sells``) are there
    only when the drawdown halt was used. ``backtest.max_losses`` (right after
    ``max_drawdown_limit_pct``, or where it would be) and
    ``backtest.loss_halt_bar`` (null when the halt never triggered) and
    ``backtest.loss_skipped_buys`` (right after ``drawdown_skipped_buys``, or
    where it would be, just before ``fills``) are there only when the
    losing-streak halt was used. ``trade_list=True`` adds ``backtest.trade_list``
    (the last key, after ``stats``): one object per row of the text trade list,
    in the same order, with the table's columns: ``open`` (true only for the
    position still held at the end, which is unrealized: marked at the last
    close, no selling costs), ``entry_bar``, ``exit_bar`` (null when open),
    ``bars_held``, ``shares`` (shares bought), ``outlay``, ``proceeds``, ``pnl``,
    ``return_pct`` and ``reason`` (null where the table shows "-"). It is an
    empty list when there were no trades. ``round_trips`` and
    ``winning_round_trips`` are unchanged by it.
    """
    value = summary["rsi"]
    data = {
        "bars": summary["bars"],
        "last_close": summary["last_close"],
        "signal": summary["signal"],
    }
    if explanation is not None:
        data["explanation"] = explanation
    data["rsi"] = value
    data["rsi_label"] = None if value is None else summary["rsi_label"]
    result = summary["result"]
    if result is not None:
        bench = result.benchmark
        atr_used = result.risk_pct is not None or result.atr_stop  # the ATR settings were used
        drawdown_used = result.max_drawdown_limit_pct is not None  # --max-drawdown was given
        breakeven_used = result.breakeven_pct is not None  # --breakeven was given
        scale_out_used = result.scale_out_pct is not None  # --scale-out was given
        add_on_used = result.add_on_pct is not None  # --add-on was given
        backtest = {
            "strategy": result.strategy,
            "params": dict(result.strategy_params),
            "fill": result.fill,
            "start_cash": result.initial_cash,
            "fee": result.fee,
            "fee_pct": result.fee_pct,
            "slippage_pct": result.slippage_pct,
            "position_size": result.position_size,
            # Only with --risk-pct, so the JSON of runs without it stays exactly as before.
            **({"risk_pct": result.risk_pct} if result.risk_pct is not None else {}),
            # Only with --risk-pct or --atr-stop (here and risk_skipped_buys below): the ATR settings
            # both of them use, in the place they always had.
            **({"atr_mult": result.atr_mult, "atr_period": result.atr_period} if atr_used else {}),
            "stop_loss_pct": result.stop_pct,
            "take_profit_pct": result.take_profit_pct,
            # Only with --trailing-stop, so the JSON of runs without it stays exactly as before.
            **({"trailing_stop_pct": result.trail_pct} if result.trail_pct is not None else {}),
            # Only with --atr-stop, so the JSON of runs without it stays exactly as before.
            **({"atr_stop": True} if result.atr_stop else {}),
            # Only with --breakeven (here and breakeven_exits below), so the JSON of runs without it stays
            # exactly as before.
            **({"breakeven_pct": result.breakeven_pct} if breakeven_used else {}),
            # Only with --scale-out (here and scale_out_exits below), so the JSON of runs without it stays exactly
            # as before. After the breakeven keys, in the order of the report's lines.
            **({"scale_out_pct": result.scale_out_pct} if scale_out_used else {}),
            # Only with --add-on (here and the two counts after scale_out_exits below), so the JSON of runs without
            # it stays exactly as before. After the scale-out keys, in the order of the report's lines.
            **({"add_on_pct": result.add_on_pct, "max_adds": result.max_adds} if add_on_used else {}),
            # Only with --cooldown (here and cooldown_skipped_buys below), so the JSON of runs without
            # it stays exactly as before.
            **({"cooldown_bars": result.cooldown} if result.cooldown else {}),
            # Only with --min-hold (here and min_hold_skipped_sells below), so the JSON of runs without it
            # stays exactly as before. Next to the max-hold keys, in the order of the report's lines.
            **({"min_hold_bars": result.min_hold} if result.min_hold else {}),
            # Only with --max-hold (here and time_exits below), so the JSON of runs without it stays
            # exactly as before.
            **({"max_hold_bars": result.max_hold} if result.max_hold else {}),
            # Only with --max-drawdown (here and the two keys after time_exits below), so the JSON of runs
            # without it stays exactly as before.
            **({"max_drawdown_limit_pct": result.max_drawdown_limit_pct} if drawdown_used else {}),
            # Only with --max-losses (here and the two keys before fills below), so the JSON of runs without it
            # stays exactly as before. After the drawdown keys, in the order of the report's lines.
            **({"max_losses": result.max_losses} if result.max_losses else {}),
            "trades": result.n_trades,
            "buys": result.n_buys,
            "sells": result.n_sells,
            **({"risk_skipped_buys": result.risk_skipped_buys} if atr_used else {}),
            **({"breakeven_exits": result.n_breakeven_exits} if breakeven_used else {}),
            **({"scale_out_exits": result.n_scale_out_exits} if scale_out_used else {}),
            **(
                {"add_on_buys": result.n_add_on_buys, "add_on_skipped_buys": result.add_on_skipped_buys}
                if add_on_used
                else {}
            ),
            **({"cooldown_skipped_buys": result.cooldown_skipped_buys} if result.cooldown else {}),
            **({"min_hold_skipped_sells": result.min_hold_skipped_sells} if result.min_hold else {}),
            **({"time_exits": result.n_time_exits} if result.max_hold else {}),
            **(
                {"drawdown_halt_bar": result.drawdown_halt_bar, "drawdown_skipped_buys": result.drawdown_skipped_buys}
                if drawdown_used
                else {}
            ),
            **(
                {"loss_halt_bar": result.loss_halt_bar, "loss_skipped_buys": result.loss_skipped_buys}
                if result.max_losses
                else {}
            ),
            "fills": [
                {
                    "bar": t.bar,
                    "side": t.side,
                    "shares": t.shares,
                    "price": t.price,
                    "value": t.value,
                    "cost": t.cost,
                    "cash_after": t.cash_after,
                    "reason": t.reason,
                }
                for t in result.trades
            ],
            "total_costs": result.total_costs,
            "round_trips": result.n_round_trips,
            "winning_round_trips": result.n_winning_round_trips,
            "final_cash": result.final_cash,
            "final_position": result.final_position,
            "final_price": result.final_price,
            "final_equity": result.final_equity,
            "return_pct": result.return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "benchmark": {
                "shares": bench.shares,
                "final_cash": bench.final_cash,
                "final_equity": bench.final_equity,
                "return_pct": bench.return_pct,
                "max_drawdown_pct": bench.max_drawdown_pct,
                "trades": bench.n_trades,
                "total_costs": bench.total_costs,
            },
        }
        if export is not None:
            backtest["export"] = {"path": export[0], "rows": export[1]}
        if stats:
            backtest["stats"] = {key: _finite_or_none(v) for key, v in result.stats.items()}
        if trade_list:
            # Only with --trade-list, so the JSON of runs without it stays exactly as before.
            backtest["trade_list"] = trade_list_data(result)
        data["backtest"] = backtest
    data["disclaimer"] = DISCLAIMER
    return data


# Options --scan cannot be combined with (attribute name, flag); they default to None or False.
_NOT_WITH_SCAN = (
    ("backtest", "--backtest"),
    ("cash", "--cash"),
    ("fee", "--fee"),
    ("fee_pct", "--fee-pct"),
    ("slippage", "--slippage"),
    ("position_size", "--position-size"),
    ("stop_loss", "--stop-loss"),
    ("take_profit", "--take-profit"),
    ("trailing_stop", "--trailing-stop"),
    ("risk_pct", "--risk-pct"),
    ("atr_mult", "--atr-mult"),
    ("atr_period", "--atr-period"),
    ("atr_stop", "--atr-stop"),
    ("cooldown", "--cooldown"),
    ("min_hold", "--min-hold"),
    ("max_hold", "--max-hold"),
    ("max_drawdown", "--max-drawdown"),
    ("breakeven", "--breakeven"),
    ("max_losses", "--max-losses"),
    ("scale_out", "--scale-out"),
    ("add_on", "--add-on"),
    ("max_adds", "--max-adds"),
    ("export", "--export"),
    ("fill", "--fill"),
    ("strategy", "--strategy"),
    ("param", "--param"),
    ("stats", "--stats"),
    ("trade_list", "--trade-list"),
    ("chart", "--chart"),
    ("candles", "--candles"),
    ("resample", "--resample"),
    ("explain", "--explain"),
)


def _scan_requested(argv):
    """True when ``argv`` holds ``--scan`` (or an abbreviation argparse would accept, like ``--sca``)."""
    for token in argv:
        if token == "--":
            break
        name = token.split("=", 1)[0]
        if len(name) >= 4 and "--scan".startswith(name):
            return True
    return False


def validate_scan_args(parser, args):
    """Usage errors (exit 2) for ``--scan``: a price file, backtest options and bad windows."""
    if args.csv_path is not None:
        parser.error(f"--scan cannot be combined with a price file (got {args.csv_path})")
    for name, flag in _NOT_WITH_SCAN:
        if getattr(args, name) not in (None, False):
            parser.error(f"{flag} cannot be combined with --scan")
    if not args.scan.strip():
        parser.error("--scan needs a folder name")
    try:
        check_scan_trim(args.min_score, args.top)
    except ValueError as exc:
        parser.error(str(exc))
    if args.report is not None and not args.report.strip():
        parser.error("--report needs a file name")
    try:
        check_windows(args.short, args.long, args.rsi_period)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def scan_main(argv):
    """``--scan FOLDER``: print the combined-score table (or ``--json`` object) for the folder. Returns the exit code."""
    parser = build_parser(scan=True)
    args = parser.parse_args(argv)
    config_path = find_config_path(args)
    if config_path is not None:
        try:
            config = load_config(config_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        apply_config(args, config)  # without --backtest only short, long and rsi_period are taken
    validate_scan_args(parser, args)
    try:
        result = scan_folder(args.scan, short=args.short, long=args.long, rsi_period=args.rsi_period)
    except ScanError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    report = None
    if args.report is not None:
        problem = report_path_problem(args.report, result.paths)
        if problem is not None:
            print(f"Error: {problem}", file=sys.stderr)
            return 1
        report = report_markdown(
            result,
            DISCLAIMER,
            short=args.short,
            long=args.long,
            rsi_period=args.rsi_period,
            min_score=args.min_score,
            top=args.top,
        )
    if args.json:
        print(json.dumps(scan_data(result, min_score=args.min_score, top=args.top), indent=2))
    else:
        for line in format_scan(result, min_score=args.min_score, top=args.top):
            print(line)
        print(DISCLAIMER)
    if report is not None:
        try:
            write_report(args.report, report)
        except OSError as exc:
            print(f"Error: cannot write report {args.report}: {exc.strerror or exc}", file=sys.stderr)
            return 1
    return 0


def report_path_problem(path, price_paths):
    """One-line reason why ``path`` must not be written as the --report file, or None.

    Checked before anything is printed: a folder, a folder that does not
    exist, or one of the scanned price files.
    """
    if os.path.isdir(path):
        return f"cannot write report {path}: it is a folder"
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        return f"cannot write report {path}: folder {parent} does not exist"
    if os.path.exists(path):
        for price_path in price_paths:
            if os.path.samefile(path, price_path):
                return f"--report refuses to overwrite the price file {path}"
    return None


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if _scan_requested(argv):
        return scan_main(list(argv))
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = find_config_path(args)
    if config_path is not None:
        try:
            config = load_config(config_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        apply_config(args, config)
    args = validate_args(parser, args)

    opens = highs = lows = None
    exits = (
        args.stop_loss is not None or args.take_profit is not None or args.trailing_stop is not None
        or bool(args.atr_stop) or args.breakeven is not None or args.scale_out is not None
    )
    risk = args.risk_pct is not None  # risk sizing needs the highs and lows for the ATR
    try:
        if args.candles or args.fill == "open" or exits or risk:
            candles = load_candles(args.csv_path)
            dates = [c.date for c in candles]
            closes = [c.close for c in candles]
            if args.fill == "open" or exits:  # exits use the opens to see gaps
                opens = [c.open for c in candles]
            if exits or risk:
                highs = [c.high for c in candles]
                lows = [c.low for c in candles]
        else:
            dates, closes = load_price_table(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not closes:
        print("No price rows found.", file=sys.stderr)
        return 1

    if args.resample is not None:
        if dates is None:
            print(f"Error: --resample needs a 'date' column, but {args.csv_path} has none", file=sys.stderr)
            return 1
        try:
            dates, closes = resample(dates, closes, args.resample)
        except ValueError as exc:
            print(f"Error: {args.csv_path} {exc}", file=sys.stderr)
            return 1

    try:
        summary = summarise(
            closes,
            short=args.short,
            long=args.long,
            rsi_period=args.rsi_period,
            backtest=args.backtest,
            cash=args.cash,
            fee=args.fee,
            fee_pct=args.fee_pct,
            strategy=args.strategy,
            strategy_params=args.strategy_params or None,
            fill=args.fill,
            opens=opens,
            slippage_pct=args.slippage,
            position_size=args.position_size,
            stop_pct=args.stop_loss,
            take_profit_pct=args.take_profit,
            highs=highs,
            lows=lows,
            trail_pct=args.trailing_stop,
            risk_pct=args.risk_pct,
            atr_mult=2.0 if args.atr_mult is None else args.atr_mult,
            atr_period=14 if args.atr_period is None else args.atr_period,
            atr_stop=bool(args.atr_stop),
            cooldown=0 if args.cooldown is None else args.cooldown,
            max_hold=0 if args.max_hold is None else args.max_hold,
            max_drawdown_limit_pct=args.max_drawdown,
            breakeven_pct=args.breakeven,
            min_hold=0 if args.min_hold is None else args.min_hold,
            max_losses=0 if args.max_losses is None else args.max_losses,
            scale_out_pct=args.scale_out,
            add_on_pct=args.add_on,
            max_adds=args.max_adds,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    result = summary["result"]

    exported = None  # (path, rows) once --export has written its file
    if args.backtest and args.export is not None:
        if os.path.abspath(args.export) == os.path.abspath(args.csv_path):
            print(f"Error: --export refuses to overwrite the input file {args.csv_path}", file=sys.stderr)
            return 1
        try:
            rows = export_csv(result, args.export, dates=dates)
        except OSError as exc:
            print(f"Error: cannot write {args.export}: {exc.strerror or exc}", file=sys.stderr)
            return 1
        exported = (args.export, rows)

    explanation = None
    if args.explain:  # the Signal line's own closes and windows, so the sentence matches it
        explanation = explain_crossover(closes, short=summary["short"], long=summary["long"])

    if args.json:
        data = report_data(
            summary,
            stats=args.backtest and args.stats,
            export=exported,
            trade_list=bool(args.backtest and args.trade_list),
            explanation=explanation,
        )
        print(json.dumps(data, indent=2, allow_nan=False))
        return 0

    lines = report_lines(summary, explanation)
    if args.backtest:
        if exported is not None:
            lines.append(f"  Exported:    {exported[1]} rows to {exported[0]}")
        if args.stats:
            lines += format_stats(result)
        if args.trade_list:
            lines += format_trade_list(result)

    if args.chart:
        marks = {}
        if result is not None:
            marks = {t.bar: ("B" if t.side == BUY else "S") for t in result.trades}
        lines.append(f"Chart:   close, {len(closes)} bars" + (", B = buy, S = sell" if marks else ""))
        lines += line_chart(closes, CHART_WIDTH, CHART_HEIGHT, marks)

    for line in lines:
        print(line)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
