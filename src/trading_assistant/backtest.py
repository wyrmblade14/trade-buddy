"""Historical simulation ("backtest") of the SMA crossover signal.

The rules are deliberately simple and strict:

* No look-ahead. The signal for bar ``t`` is computed from ``closes[0..t]``
  only, i.e. from prices that were known at the close of bar ``t``. With
  ``warmup_closes`` (bars before bar 0, only for the signal; see
  ``run_backtest``) it also sees those earlier bars, never a later one.
* Next-bar fills. A signal produced on bar ``t`` is executed at the close of
  bar ``t + 1`` (``fill="close"``, the default) or, when the open prices are
  supplied, at the open of bar ``t + 1`` (``fill="open"``). A signal on the
  final bar can never be acted on. Account value is always marked at the close.
* BUY buys as many whole shares as the available cash allows. SELL sells the
  entire position. A BUY that cannot afford a single share, or a SELL with
  nothing held, is skipped silently.
* Whole shares only, no short selling, no leverage. ``Portfolio.buy`` and
  ``Portfolio.sell`` raise ``ValueError`` for impossible orders and leave the
  portfolio unchanged.
* Optional trading costs: a fixed fee per trade plus a percentage of the
  traded value, both charged on every buy and every sell. Both default to
  zero. A buy must afford the shares *and* the costs; a sell whose costs
  would push cash below zero is rejected. Cash never goes negative.
* Optional slippage (``slippage_pct``, default 0): a buy fills that much
  higher than the bar's fill price and a sell that much lower, before the
  fees are worked out on the slipped price. Fills record the slipped price.
* Optional position sizing (``position_size``, default None = spend all the
  cash): a buy spends at most that fraction of the account value (cash plus
  the shares held, marked at the bar's fill price) on shares, costs and
  slippage included, and never more than the cash. Whole shares only.
* Optional stop loss and take profit (``stop_pct``, ``take_profit_pct``,
  default None; both need ``highs`` and ``lows``). While shares are held, on
  every bar after the entry bar: if the bar's low reaches the entry price
  less ``stop_pct`` percent the whole position is sold at that stop price; if
  the bar's high reaches the entry price plus ``take_profit_pct`` percent it
  is sold at that target price. If one bar touches both, the stop wins. When
  the open prices are supplied, a bar that *opens* at or beyond a level (a
  gap) is sold at its open instead, because a real order would fill near the
  open, not at the level the price jumped over: at or below the stop ->
  ``stop`` at the open; at or above the target -> ``target`` at the open (the
  open comes first, so this also holds if the bar later reaches the stop).
  Without opens no gap can be seen and the level is used. The
  entry price is the average price paid for the open position. These exits
  are sells, so slippage and fees apply to them too. Each fill records why
  it happened: ``signal``, ``stop`` or ``target``. One fill per bar: with
  close fills the intrabar exit is checked before the close fill, with open
  fills the open fill comes first; an exit on a bar cancels that bar's
  pending signal fill.
* Optional trailing stop (``trail_pct``, default None; needs ``highs`` and
  ``lows``). While shares are held, on every bar after the entry bar the
  level is the highest high since entry times ``1 - trail_pct / 100``. The
  highest high starts at the entry price (the average price paid) and takes
  in the highs of the bars after the entry bar up to, but not including, the
  bar being checked: a bar's own high is never used, because it is not known
  whether the bar's high or its low came first. If the bar's low reaches the
  level the whole position is sold at the level; when the opens are supplied
  and the bar opens at or below the level it is sold at the open instead.
  The reason recorded is ``trail``. It is a stop, so it is checked together
  with ``stop_pct``: a falling price meets the higher of the two levels first,
  so that one is used (``stop`` on a tie; with ``atr_stop`` as well, the
  highest of the three, see below), and it wins over the target.
  Slippage and fees apply as for the other exits.
* Optional risk-based sizing (``risk_pct``, default None; needs ``highs`` and
  ``lows``). A buy risks ``risk_pct`` percent of the account value at the
  time of the fill (marked at the bar's fill price, as for
  ``position_size``). The stop distance is ``atr_mult`` times the Wilder ATR
  over ``atr_period`` bars, taken from the bar the buy signal came on, never
  from the bar the buy fills on. The share count is the risk divided by the
  stop distance, rounded down to whole shares, and never more than the cash
  (or ``position_size``) allows. A buy signal on a bar that has no ATR yet
  (the first ``atr_period - 1`` bars) or an ATR of 0 (flat bars) is skipped,
  as is a buy whose risk is less than one share; the result counts these in
  ``risk_skipped_buys``. Without ``atr_stop`` no stop order is placed: the
  ATR distance only sizes the buy.
* Optional ATR stop (``atr_stop``, default False; needs ``highs`` and
  ``lows``). When a buy opens a position, the distance ``atr_mult`` times
  the Wilder ATR over ``atr_period`` bars is taken from the bar the buy
  signal came on (as for ``risk_pct``) and kept for the whole position. On
  every bar after the entry bar the level is the entry price (the average
  price paid) less that distance, so a later buy into the same position
  moves the level with the average price but keeps the first distance. A buy
  signal on a bar with no ATR yet, or an ATR of 0, is skipped and counted in
  ``risk_skipped_buys``. A bar whose low reaches the level sells the whole
  position at the level, or at the open when the opens are supplied and the
  bar opens at or below it (a gap). The reason recorded is ``atr``. It is a
  stop like ``stop_pct`` and ``trail_pct``: of the levels in use the highest
  is used (on a tie ``stop`` first, then ``trail``, then ``atr``), and it
  wins over the target. Slippage and fees apply as for the other exits.
* Optional breakeven stop (``breakeven_pct``, above 0, no upper limit,
  default None; needs ``highs`` and ``lows``). While shares are held, once
  the high of a bar after the entry bar is at or above the entry price plus
  ``breakeven_pct`` percent, the position is armed and stays armed until it
  is sold. The entry bar's own high never counts, in either fill mode. A bar
  is checked when it is over, so the stop first acts on the next bar, never
  on the bar that armed it. From then on the level is the entry price itself
  (the average price paid, with no allowance for fees or slippage, so a sale
  there still loses the costs). A bar whose low reaches the level sells the
  whole position at the level, or at the open when the opens are supplied
  and the bar opens at or below it (a gap). The reason recorded is
  ``breakeven``. A later buy into the same position moves the average entry
  price: an armed stop stays armed and follows the new average, and an
  unarmed one measures ``breakeven_pct`` from the new average. It is a stop
  like the others: of the levels in use the highest is used (on a tie
  ``stop``, then ``trail``, then ``atr``, then ``breakeven``), and it wins
  over the target. ``take_profit_pct`` at or below ``breakeven_pct`` is
  allowed, but then the breakeven stop can never act: a bar whose high
  would arm it has also reached the target, which sells the position on
  that bar. (The only way around this is a later buy into the position,
  which moves the average entry price after the bar's target check, or
  fills at a bar's open and so takes that bar's exit check.) Slippage and
  fees apply as for the other exits.
* Optional cooldown (``cooldown``, a whole number of bars, default 0 = off).
  When a ``stop``, ``trail``, ``atr`` or ``breakeven`` exit sells the position on bar ``t``,
  no buy can fill on bars ``t + 1`` to ``t + cooldown``; the first buy can
  fill on bar ``t + cooldown + 1``. A buy due on a blocked bar is dropped, not
  delayed, and counted in ``cooldown_skipped_buys`` (even one that would have
  got 0 shares anyway; it is then not also counted in ``risk_skipped_buys``).
  A ``target`` or ``signal`` sell starts no cooldown. A buy signal on the
  exit bar's close is due on bar ``t + 1``, the first blocked bar. A buy due
  on the exit bar itself is not a cooldown skip: with close fills the exit
  comes first and cancels it (one fill per bar); with open fills it fills at
  the open, and then no exit is checked on that bar, so no cooldown starts
  there. Because a blocked buy is dropped, a strategy that signals only on
  the bar of a crossing (``sma_cross``, ``ema_cross``, ...) stays out until
  its next BUY signal, however long after the cooldown; one that keeps
  signalling (``breakout``) buys again on the first bar after the cooldown
  that a BUY signal is due on. A BUY signal on the last bar has no bar to
  fill on and is never counted.
* Optional maximum holding time (``max_hold``, a whole number of bars,
  default 0 = off; needs no highs or lows, so it works with closes only).
  The clock starts on the bar of the buy that opened the position (``e``);
  a later buy into the same position does not restart it. On bar ``e +
  max_hold`` the whole position is sold at that bar's fill price (its close,
  or its open with ``fill="open"``), with slippage and fees as for any sell.
  The reason recorded is ``time``. A time exit never takes a bar that
  already has a fill: if a signal buy or sell, a stop, trail, ATR stop,
  breakeven or target fills on that bar, or with close fills a scale-out, the
  time exit waits for the next bar without one. With close fills the bar's
  range (the stops and the target), then the signal fill at the close, then
  the scale-out come first. With open fills the signal fill
  at the open comes first, then a gap through a stop or the target at the
  open (a ``stop``, ``trail``, ``atr``, ``breakeven`` or ``target`` sale at the open), then
  the time exit at the open; a stop or target that is only reached later in
  the bar does not beat it. A time exit starts no cooldown. After it the
  strategy can buy again on its next BUY signal, as after any sell.
* Optional minimum holding time (``min_hold``, a whole number of bars,
  default 0 = off; needs no highs or lows, so it works with closes only).
  The clock is the one ``max_hold`` uses: it starts on the bar of the buy
  that opened the position (``e``) and a later buy into the same position
  does not restart it. A signal sell due on a bar before ``e + min_hold``
  is dropped, not delayed, and counted in ``min_hold_skipped_sells``; from
  bar ``e + min_hold`` on signal sells fill as usual. Only signal sells are
  held back: the stops, the target, the time exit and the drawdown sale
  still sell inside the window. A sell is counted only when it would
  otherwise have filled: shares are held and nothing sold them earlier on
  that bar (with close fills the bar's range comes first, so a stop or
  target sale on the bar leaves no sell to skip; with open fills the signal
  comes first at the open, so it is counted even if a stop sells later in
  the bar). It is counted before the fees are checked, so a sell the fees
  would have made impossible is counted too. A skipped sell makes no fill,
  so the bar is still free for the time exit or the drawdown sale. A signal
  sell can never be due on the bar its position was opened, so ``min_hold
  = 1`` never skips anything. ``min_hold`` at or above ``max_hold`` is
  allowed: the time exit then sells first.
* Optional drawdown halt (``max_drawdown_limit_pct``, default None = off;
  above 0 and below 100; needs no highs or lows). The peak is the highest
  account value at a close so far, the first bar's included. When the
  account value at the close of bar ``h`` is that percentage or more below
  the peak (worked out as ``drawdown_curve_pct`` does, so it agrees with the
  export's ``drawdown_pct`` column), the run halts: it is checked until it
  triggers, once. From bar ``h + 1`` to the end no buy can fill; a buy due
  then is dropped and counted in ``drawdown_skipped_buys`` (even one that
  would have got 0 shares; it is then counted in neither
  ``cooldown_skipped_buys`` nor ``risk_skipped_buys``). A position still
  held is sold whole on bar ``h + 1`` at that bar's fill price (its close,
  or its open with ``fill="open"``), with slippage and fees as for any sell;
  the reason recorded is ``drawdown``. That sale is only made when nothing
  else sells on the bar, in the order the time exit uses: with close fills
  the bar's range (stops and target), then the signal fill, then the
  scale-out, then the time exit, then the drawdown sale at the close; with open fills the signal fill
  at the open, then a gap through a stop or the target at the open, then the
  time exit, then the drawdown sale at the open (a stop or target only
  reached later in the bar does not beat it). A signal, stop, trail, ATR
  stop, breakeven, target or time sale on that bar keeps its own reason. A drawdown
  sale the fees would make impossible is tried again on each later bar. It
  starts no cooldown.
* Optional losing-streak halt (``max_losses``, a whole number, default 0 =
  off; needs no highs or lows). Every completed round trip, whatever sold it
  (``signal``, ``stop``, ``target``, ``trail``, ``atr``, ``breakeven``,
  ``time`` or ``drawdown``), adds one to the streak when its profit after
  costs is below 0 and sets the streak back to 0 otherwise (a round trip at
  exactly 0.00 is not a loss, so it resets the streak too). A sale the fees
  refuse completes no round trip and does not count. When the streak
  reaches ``max_losses`` on bar ``h`` (the bar of the losing sale), the run
  halts, once: from bar ``h + 1`` to the end no buy can fill; a buy due then
  is dropped and counted in ``loss_skipped_buys`` (even one that would have
  got 0 shares; it is then counted in neither ``cooldown_skipped_buys`` nor
  ``risk_skipped_buys``). A buy the drawdown halt also blocks is counted in
  ``drawdown_skipped_buys`` only. A scale-out completes no round trip and so
  does not count. Every round trip ends with the whole position sold, so
  nothing is held when the halt starts and nothing is sold because of it;
  no buy can fill on bar ``h`` either (one fill per bar).
* Optional scale-out (``scale_out_pct``, above 0, default None; needs
  ``highs`` and ``lows``). While shares are held, on a bar after the entry
  bar whose high reaches the average entry price plus ``scale_out_pct``
  percent, half the shares held (rounded down) are sold at that level, or at
  the bar's open when the opens are supplied and the bar opens at or above it
  (a gap). The reason recorded is ``scale_out``. It happens at most once per
  position: the position is marked when it sells, and the mark goes only when
  the position is back to 0, so a later buy into the same position does not
  allow a second one. With 1 share held half is 0 shares: nothing is sold and
  the position is not marked, so it can still scale out after a later buy; a
  sale the fees refuse does not mark it either and is tried again on later
  bars. The rest stays open and is sold by whatever would have sold it. A
  scale-out is not a round trip: the round trip is completed when the rest is
  sold, and its proceeds (so its profit, the win rate and the losing streak)
  include the partial sale. The entry price of the shares still held (the
  level of every stop, the target, the breakeven trigger and the trailing
  stop's starting point) is their average cost: a partial sale does not
  change it, and a later buy averages the new shares with the ones still
  held, not with the ones sold. Any other fill on the bar beats the
  scale-out, which is then skipped on that bar (one fill per bar): with close
  fills the bar's range (stops and target), then the signal fill at the close
  (a buy or a sell), then the scale-out, then the time exit, then the
  drawdown sale, so a scale-out makes those two wait for a later bar; with
  open fills the signal fill at the open, then (when due) a gap through a stop
  or the target, the time exit and the drawdown sale at the open, then (when
  due) an add-on at the open, then the bar's range (stops and target), then
  the scale-out. Slippage and fees
  apply as for the other exits. It starts no cooldown and ``min_hold`` does
  not hold it back.
* Optional add-ons (``add_on_pct``, above 0, default None = off; ``max_adds``,
  a whole number of at least 1, default 1 with ``add_on_pct`` and an error
  without it; needs no highs or lows). While shares are held, when the close
  of bar ``t`` is ``add_on_pct`` percent or more above the fill price of the
  latest buy into the position (as the fill records it, slippage included),
  fewer than ``max_adds`` add-ons have filled in the position, and the
  signal of bar ``t`` is neither BUY nor SELL, an add-on is due on bar
  ``t + 1``. It comes after every other fill that can be known when it would
  fill, and is dropped (not delayed, not counted) when one of them happens.
  With close fills it is the lowest-priority fill: a stop, trail, ATR stop,
  breakeven or target sale during the bar, the signal fill, a scale-out, a
  time exit or a drawdown sale on that bar drops it. With open fills it fills
  at the open, like a signal buy, and only what is known at the open drops
  it: the signal fill at the open, a gap through a stop or the target at the
  open, or the time exit or drawdown sale at the open. Once it fills the
  bar's range is not checked (one fill per bar), so a stop, target or
  scale-out level reached later in that bar does nothing on that bar; from
  the next bar on the levels follow the new average entry price. An add-on
  that does not fill (0 shares, or halted) leaves the bar's range to be
  checked as usual. A SELL signal on bar ``t`` drops it even when
  ``min_hold`` then holds the sale back; a BUY signal on bar ``t`` leaves
  the buy on bar ``t + 1`` to the signal. Otherwise it buys at bar ``t +
  1``'s fill price (its close, or its open with ``fill="open"``), sized like
  any buy (all the cash, ``position_size``, ``risk_pct`` with the ATR of bar
  ``t``), with slippage and fees, and the fill's reason is ``add_on``. With
  the default sizing the first buy spends the cash, so an add-on usually
  gets 0 shares. An add-on that gets 0 shares is counted in
  ``add_on_skipped_buys`` (not in ``risk_skipped_buys``), is not one of the
  ``max_adds`` and leaves the reference price where it was, so the next
  close is checked again. After a drawdown halt an add-on that gets its turn
  (only when the drawdown sale was refused by the fees) is blocked and
  counted in ``drawdown_skipped_buys``. Every buy into the position, a signal
  buy included, becomes the new reference price; only add-ons count towards
  ``max_adds``, and the count starts again with each new position. An
  add-on is a later buy into the same position: it raises the average entry
  price (so the stop, ATR stop, breakeven, target and scale-out levels
  follow it), its shares and outlay go into the round trip the position
  completes (one round trip, one step of the losing streak), and it
  restarts neither the ``min_hold`` nor the ``max_hold`` clock. A close is
  compared with ``price * (1 + add_on_pct / 100)`` in floating point, so a
  close exactly on the level can fall just short of it: after a buy at 11,
  ``add_on_pct=10`` needs a close above 12.10 (``11 * 1.1`` is
  ``12.100000000000001``), and a close of exactly 12.10 does not set it off.
* No dividends or interest on cash.
* Final equity is marked to market at the last close; the position is not
  force-liquidated.

To judge the strategy the result also carries:

* a buy-and-hold benchmark: spend as much as possible on the first bar and
  hold to the end. The purchase follows the strategy's buy rules: it fills at
  the first bar's fill price (its close, or its open with open fills) plus the
  same slippage, with the same costs. It is always all-in, so position sizing
  and the exits do not apply to it;
* the equity curve (account value after each bar) and its maximum drawdown,
  the worst peak-to-trough fall in account value, as a percentage;
* completed round trips (position 0 -> long -> 0) with their profit after
  costs, so a win rate can be reported. A scale-out's partial sale is part of
  its round trip, not one of its own.

``trade_list(result)`` turns those round trips into rows (entry and exit bar,
bars held, shares bought, outlay, proceeds, profit, return on the outlay and
the reason of the sale that completed each one), plus one row for a position
still held at the end, marked at the last close with no selling costs
(unrealized); ``format_trade_list(result)`` is its text table, printed by the
command line's ``--trade-list``. Neither changes the result.

This is a research aid. It places no orders and it is not financial advice.
"""

import csv
from dataclasses import dataclass, field
from typing import List, Optional

from . import metrics
from .account import (  # noqa: F401  re-exported: tests and callers import Portfolio from here
    Portfolio,
    _check_price,
    _check_shares,
)
from .indicators import atr
from .signals import BUY, SELL, crossover_signal
from .strategies import get_strategy, resolve_params

DEFAULT_CASH = 10_000.0

FILLS = ("close", "open")  # price of bar t + 1 that a signal from bar t is filled at


@dataclass(frozen=True)
class Trade:
    """One fill. ``bar`` is the 0-based index of the bar the fill happened on.

    ``cost`` is the fee charged on this fill. For a BUY the cash outlay is
    ``value + cost``; for a SELL the net proceeds are ``value - cost``.
    """

    bar: int
    side: str  # BUY or SELL
    shares: int
    price: float
    cash_after: float
    cost: float = 0.0
    # "signal", "stop", "target", "trail", "atr", "breakeven", "time", "drawdown" or "scale_out";
    # "add_on" for a buy made by the add-ons
    reason: str = "signal"

    @property
    def value(self):
        return self.shares * self.price


@dataclass(frozen=True)
class RoundTrip:
    """A completed buy-then-sell cycle: position went 0 -> long -> 0."""

    entry_bar: int
    exit_bar: int
    shares: int  # shares bought (a scale-out sells some of them before the exit bar)
    outlay: float  # total cash spent on the buys, fees included
    proceeds: float  # net cash received from the sells (a scale-out's included), fees deducted

    @property
    def pnl(self):
        return self.proceeds - self.outlay

    @property
    def is_win(self):
        return self.pnl > 0


@dataclass(frozen=True)
class DailyRecord:
    """Account state at the close of one bar, after any fill on that bar."""

    bar: int
    close: float
    signal: str  # signal generated at this close; it is acted on the next bar
    trade: Optional[Trade]
    cash: float
    position: int
    equity: float


@dataclass
class BenchmarkResult:
    """Buy as many shares as possible on the first bar and hold to the end."""

    initial_cash: float
    shares: int
    final_cash: float
    final_price: float
    total_costs: float = 0.0
    equity_curve: List[float] = field(default_factory=list)

    @property
    def final_equity(self):
        return self.final_cash + self.shares * self.final_price

    @property
    def return_pct(self):
        return (self.final_equity - self.initial_cash) / self.initial_cash * 100.0

    @property
    def max_drawdown_pct(self):
        return max_drawdown_pct(self.equity_curve)

    @property
    def n_trades(self):
        return 1 if self.shares else 0


@dataclass
class BacktestResult:
    initial_cash: float
    final_cash: float
    final_position: int
    final_price: float
    trades: List[Trade] = field(default_factory=list)
    fee: float = 0.0
    fee_pct: float = 0.0
    total_costs: float = 0.0
    round_trips: List[RoundTrip] = field(default_factory=list)
    daily: List[DailyRecord] = field(default_factory=list)
    benchmark: Optional[BenchmarkResult] = None
    strategy: str = "sma_cross"
    strategy_params: dict = field(default_factory=dict)
    fill: str = "close"
    slippage_pct: float = 0.0
    position_size: Optional[float] = None
    stop_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trail_pct: Optional[float] = None
    risk_pct: Optional[float] = None  # None: no risk sizing
    # atr_mult and atr_period are None unless risk sizing or the ATR stop is on
    atr_mult: Optional[float] = None
    atr_period: Optional[int] = None
    # buys skipped by the ATR rules: no usable ATR on the signal bar, or (risk sizing) risk under 1 share
    risk_skipped_buys: int = 0
    atr_stop: bool = False  # True: a stop atr_mult x ATR below the entry price
    cooldown: int = 0  # bars after a stop, trail, atr or breakeven exit on which no buy can fill; 0: off
    cooldown_skipped_buys: int = 0  # buys dropped because they fell in a cooldown
    max_hold: int = 0  # bars after a position's first buy at which it is sold ("time"); 0: off
    # percentage below the peak account value at a close that halts the run ("drawdown"); None: off
    max_drawdown_limit_pct: Optional[float] = None
    drawdown_halt_bar: Optional[int] = None  # bar whose close set off the halt; None: it never did
    drawdown_skipped_buys: int = 0  # buys dropped because the run had halted
    # a stop at the entry price once a high after the entry bar is this percentage above it; None: off
    breakeven_pct: Optional[float] = None
    # New last fields, so the order of the ones above is as in 0.13.0.
    min_hold: int = 0  # bars after a position's first buy before a signal sell can fill; 0: off
    min_hold_skipped_sells: int = 0  # signal sells dropped because they fell inside the minimum holding time
    max_losses: int = 0  # losing round trips in a row that halt the run; 0: off
    loss_halt_bar: Optional[int] = None  # bar of the sale that completed the streak; None: it never did
    loss_skipped_buys: int = 0  # buys dropped because the losing streak had halted the run
    # sell half the position once a high after the entry bar is this percentage above the entry; None: off
    scale_out_pct: Optional[float] = None
    # buy more on the next bar after a close this percentage above the latest buy's fill price; None: off
    add_on_pct: Optional[float] = None
    max_adds: Optional[int] = None  # add-on buys allowed per position; None unless add_on_pct is set
    add_on_skipped_buys: int = 0  # add-ons that got 0 shares (not one of max_adds; the reference price stays)

    @property
    def has_price_exits(self):
        """True when a stop loss, take profit, trailing stop, ATR stop or breakeven stop was in use (the "Exits:" line)."""
        return (
            self.stop_pct is not None
            or self.take_profit_pct is not None
            or self.trail_pct is not None
            or self.atr_stop
            or self.breakeven_pct is not None
        )

    @property
    def has_exits(self):
        """True when any exit besides the signal was in use: the price exits, the maximum holding time, the
        drawdown halt or the scale-out; or when add-ons were on (not an exit, but a fill that is not the signal's).

        Fills then carry a reason in the report, the export and the web reply.
        """
        return (
            self.has_price_exits or bool(self.max_hold) or self.max_drawdown_limit_pct is not None
            or self.scale_out_pct is not None or self.add_on_pct is not None
        )

    @property
    def n_add_on_buys(self):
        """Buys made by the add-ons (reason ``add_on``)."""
        return sum(1 for t in self.trades if t.reason == "add_on")

    @property
    def n_scale_out_exits(self):
        """Partial sells made by the scale-out (reason ``scale_out``); none of them is a round trip."""
        return sum(1 for t in self.trades if t.reason == "scale_out")

    @property
    def n_breakeven_exits(self):
        """Sells made by the breakeven stop (reason ``breakeven``)."""
        return sum(1 for t in self.trades if t.reason == "breakeven")

    @property
    def n_time_exits(self):
        """Sells made by the maximum holding time (reason ``time``)."""
        return sum(1 for t in self.trades if t.reason == "time")

    @property
    def final_equity(self):
        return self.final_cash + self.final_position * self.final_price

    @property
    def return_pct(self):
        return (self.final_equity - self.initial_cash) / self.initial_cash * 100.0

    @property
    def n_trades(self):
        return len(self.trades)

    @property
    def n_buys(self):
        return sum(1 for t in self.trades if t.side == BUY)

    @property
    def n_sells(self):
        return sum(1 for t in self.trades if t.side == SELL)

    @property
    def equity_curve(self):
        return [d.equity for d in self.daily]

    @property
    def max_drawdown_pct(self):
        return max_drawdown_pct(self.equity_curve)

    @property
    def n_round_trips(self):
        return len(self.round_trips)

    @property
    def n_winning_round_trips(self):
        return sum(1 for r in self.round_trips if r.is_win)

    @property
    def stats(self):
        """Risk and return statistics as a dict; None marks an undefined value.

        See ``trading_assistant.metrics`` for each definition.
        """
        curve = self.equity_curve
        return {
            "total_return_pct": metrics.total_return_pct(curve),
            "cagr_pct": metrics.cagr_pct(curve),
            "annualized_volatility_pct": metrics.annualized_volatility_pct(curve),
            "sharpe_ratio": metrics.sharpe_ratio(curve),
            "sortino_ratio": metrics.sortino_ratio(curve),
            "exposure_pct": metrics.exposure_pct([d.position for d in self.daily]),
            "profit_factor": metrics.profit_factor(self.round_trips),
            "average_win": metrics.average_win(self.round_trips),
            "average_loss": metrics.average_loss(self.round_trips),
            "longest_drawdown_bars": metrics.longest_drawdown_bars(curve),
        }


def max_drawdown_pct(equity_curve):
    """Worst peak-to-trough fall in ``equity_curve`` as a percentage (<= 0).

    0.0 for an empty or never-falling curve.
    """
    worst = 0.0
    peak = None
    for value in equity_curve:
        if peak is None or value > peak:
            peak = value
        if peak > 0:
            drop = (value - peak) / peak * 100.0
            if drop < worst:
                worst = drop
    return worst


def drawdown_curve_pct(equity_curve):
    """Running drawdown from the peak so far, in percent (<= 0), one value per bar."""
    out = []
    peak = None
    for value in equity_curve:
        if peak is None or value > peak:
            peak = value
        out.append((value - peak) / peak * 100.0 if peak > 0 else 0.0)
    return out


def _validate_inputs(closes, initial_cash, fee, fee_pct):
    if not closes:
        raise ValueError("no prices to backtest")
    if not initial_cash > 0:
        raise ValueError(f"initial cash must be positive, got {initial_cash}")
    if fee < 0:
        raise ValueError(f"fee must not be negative, got {fee}")
    if not 0 <= fee_pct < 100:
        raise ValueError(f"fee_pct must be between 0 and 100 (exclusive), got {fee_pct}")
    for i, price in enumerate(closes):
        if not price > 0:
            raise ValueError(f"bar {i}: price must be positive, got {price}")


def _check_opens(opens, closes):
    """Raise ValueError unless ``opens`` has one positive price per close."""
    if len(opens) != len(closes):
        raise ValueError(f"{len(opens)} opens but {len(closes)} closes")
    for i, price in enumerate(opens):
        if not price > 0:
            raise ValueError(f"bar {i}: open must be positive, got {price}")


def _max_shares_within(portfolio, price, budget):
    """Largest whole number of shares whose cost, fees included, fits in ``budget`` and in the cash."""
    budget = min(budget, portfolio.cash)
    spend = budget - portfolio.fee
    if spend <= 0:
        return 0
    shares = int(spend / (price * (1 + portfolio.fee_pct / 100.0)))
    # Guard against floating point rounding making the estimate one too many.
    while shares > 0 and shares * price + portfolio.trade_cost(shares, price) > budget:
        shares -= 1
    return shares


def run_buy_and_hold(closes, initial_cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0, fill="close", opens=None, slippage_pct=0.0):
    """Benchmark: buy as many whole shares as possible on the first bar and hold.

    The purchase follows the same rules as the strategy's buys: it fills at
    the first bar's fill price, ``closes[0]`` (``fill="close"``, the default)
    or ``opens[0]`` (``fill="open"``, which needs ``opens``), raised by
    ``slippage_pct`` percent, and the same fee schedule is charged on that
    slipped price. The account is marked at the closes. With the defaults this
    is the plain buy at ``closes[0]``. If not even one share is affordable the
    cash is simply held. Raises ValueError as ``run_backtest`` does for bad
    prices, costs, ``fill``, ``opens`` or ``slippage_pct``.
    """
    _validate_inputs(closes, initial_cash, fee, fee_pct)
    if not 0 <= slippage_pct < 100:
        raise ValueError(f"slippage_pct must be between 0 and 100 (exclusive), got {slippage_pct}")
    if fill not in FILLS:
        raise ValueError(f"unknown fill {fill!r}; choose one of: {', '.join(FILLS)}")
    if fill == "open":
        if opens is None:
            raise ValueError("fill on open needs the open price of every bar")
        _check_opens(opens, closes)
    price = opens[0] if fill == "open" else closes[0]
    if slippage_pct:
        price = price * (1 + slippage_pct / 100.0)  # same as a strategy buy
    portfolio = Portfolio(initial_cash, fee=fee, fee_pct=fee_pct)
    shares = portfolio.max_affordable(price)
    if shares:
        portfolio.buy(shares, price)
    curve = [portfolio.equity(price) for price in closes]
    return BenchmarkResult(
        initial_cash=float(initial_cash),
        shares=portfolio.position,
        final_cash=portfolio.cash,
        final_price=closes[-1],
        total_costs=portfolio.total_costs,
        equity_curve=curve,
    )


def run_backtest(
    closes,
    initial_cash=DEFAULT_CASH,
    short=20,
    long=50,
    fee=0.0,
    fee_pct=0.0,
    strategy="sma_cross",
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
    warmup_closes=None,
    add_on_pct=None,
    max_adds=None,
):
    """Trade a strategy's signal over ``closes`` and report the outcome.

    ``strategy`` is a name from ``trading_assistant.strategies``; the default
    is the SMA crossover, whose windows are ``short`` and ``long``.
    ``strategy_params`` overrides the strategy's default parameters (for
    ``sma_cross`` it overrides ``short`` and ``long``). The strategy name and
    the parameters actually used are recorded on the result.

    ``fill`` is the price of bar ``t + 1`` at which a signal from bar ``t`` is
    filled: ``"close"`` (the default; ``opens`` then only serve the exits' gap check) or ``"open"``,
    which needs ``opens``, one positive open price per close. Signals are
    always computed from the closes, and the account value is always marked at
    the close. ``slippage_pct`` (0 <= value < 100) makes every buy fill that
    percentage above and every sell that percentage below the bar's fill
    price, before fees. ``position_size`` (0 < value <= 1) caps each buy at
    that fraction of the account value (cash plus shares held, marked at the
    bar's fill price), costs and slippage included; None spends all the cash
    as before. ``stop_pct`` (0 < value < 100) and ``take_profit_pct`` (> 0)
    sell the position when a bar's low or high reaches the level below or
    above the entry price (see the module docstring); either needs ``highs``
    and ``lows``, one per close. With an exit set, ``opens`` (if given) are
    also used with ``fill="close"``: a bar that gaps past a level is sold at
    its open rather than at the level. The buy-and-hold benchmark buys on the
    first bar at that bar's ``fill`` price with the same ``slippage_pct`` and
    costs (see ``run_buy_and_hold``); ``position_size`` and the exits do not
    apply to it. ``trail_pct`` (0 < value < 100) is a trailing stop: it sells
    the position when a bar's low reaches the highest high since entry less
    that percentage (see the module docstring); it needs ``highs`` and
    ``lows`` too and uses ``opens`` for the gap check in the same way. With
    ``trail_pct`` left as None nothing changes.

    ``risk_pct`` (0 < value <= 100) sizes each buy by risk: the money at risk
    is that percentage of the account value at the fill (marked at the bar's
    fill price), the stop distance is ``atr_mult`` (> 0) times the ATR over
    ``atr_period`` (a whole number >= 1) bars from the bar the buy signal came
    on, and the share count is the risk divided by the stop distance, rounded
    down. It is capped by the cash and by ``position_size`` if that is set. A
    buy signal on a bar with no ATR yet, or an ATR of 0, is skipped, as is a
    buy whose risk is under one share; ``risk_skipped_buys`` on the result
    counts them (a buy skipped only for lack of cash is not counted). It
    needs ``highs`` and ``lows``. With ``risk_pct`` left as None nothing
    changes.

    ``atr_stop`` (True or False) adds an ATR stop: the distance ``atr_mult``
    times the ATR over ``atr_period`` bars from the signal bar of the buy that
    opens the position is kept for the whole position, and the position is sold
    when a bar's low reaches the entry price (the average price paid) less that
    distance (see the module docstring). A buy signal with no usable ATR is
    skipped and counted in ``risk_skipped_buys``, as for ``risk_pct``; the two
    work together and the buy is counted once. It needs ``highs`` and ``lows``
    and uses ``opens`` for the gap check like the other exits. The ATR is only
    worked out when ``risk_pct`` or ``atr_stop`` is on. With ``atr_stop`` left
    False nothing changes.

    ``breakeven_pct`` (> 0, no upper limit) adds a breakeven stop: once the
    high of a bar after the entry bar is at or above the entry price (the
    average price paid) plus that percentage, the position is sold on a later
    bar whose low reaches the entry price, with reason ``breakeven`` (see the
    module docstring for gaps, later buys and ties). At or above
    ``take_profit_pct`` it is allowed but can never act, because the target
    sells first, unless a later buy into the position moves the average
    (see the module docstring). It needs ``highs`` and ``lows`` and uses ``opens`` for the
    gap check like the other exits. With ``breakeven_pct`` left as None
    nothing changes.

    ``cooldown`` (a whole number >= 0, default 0 = off): after a ``stop``,
    ``trail``, ``atr`` or ``breakeven`` exit on bar ``t`` no buy can fill on bars ``t + 1``
    to ``t + cooldown``. A buy due then is dropped (not delayed) and counted in
    ``cooldown_skipped_buys``, whether or not it would have got any shares. A
    ``target`` or ``signal`` sell starts no cooldown. With ``cooldown`` left
    at 0 nothing changes.

    ``max_hold`` (a whole number >= 0, default 0 = off) sells the whole
    position on bar ``e + max_hold``, ``e`` being the bar of the buy that
    opened it, at that bar's fill price (close, or open with ``fill="open"``),
    with reason ``time``. It needs only the closes (and ``opens`` for open
    fills). A bar that already has a fill (a signal buy or sell, a stop,
    trail, ATR stop, breakeven or target sale, or with close fills a scale-out) is left to that fill and the time exit
    waits for the next bar; see the module docstring for the order within a
    bar. It starts no cooldown. With ``max_hold`` left at 0 nothing changes.

    ``min_hold`` (a whole number >= 0, default 0 = off) drops a signal sell
    due before bar ``e + min_hold``, ``e`` being the bar of the buy that
    opened the position, and counts it in ``min_hold_skipped_sells``. Only
    signal sells are held back; every other exit still sells inside the
    window. It needs only the closes. See the module docstring for which
    sells are counted. With ``min_hold`` left at 0 nothing changes.

    ``max_drawdown_limit_pct`` (0 < value < 100, default None = off) halts the
    run when the account value at a close is that percentage or more below the
    peak account value at a close so far. From the next bar on no buy fills
    (each buy due is counted in ``drawdown_skipped_buys``), and a position
    still held is sold on the next bar at its fill price with reason
    ``drawdown``, unless a signal, stop, trail, ATR stop, breakeven, target or time sale
    sells it on that bar first, or with close fills a scale-out takes that bar (see the module
    docstring). It needs only the
    closes and starts no cooldown. ``drawdown_halt_bar`` on the result is the
    bar whose close set off the halt, or None. With it left as None nothing
    changes.

    ``max_losses`` (a whole number >= 0, default 0 = off) halts the run once
    that many completed round trips in a row have lost money (profit after
    costs below 0; any other round trip resets the streak). From the bar after
    the losing sale on, no buy fills (each buy due is counted in
    ``loss_skipped_buys``, unless the drawdown halt already counts it). No
    position is held then, so nothing is sold. It needs only the closes.
    ``loss_halt_bar`` on the result is the bar of the sale that completed the
    streak, or None. With it left at 0 nothing changes.

    ``scale_out_pct`` (> 0, default None = off) sells half the shares held
    (rounded down) once per position, when the high of a bar after the entry
    bar reaches the average entry price plus that percentage, at that level
    (or at the open on a gap), with reason ``scale_out``. Any other fill on the
    bar beats it; it makes the time exit and the drawdown sale wait. It is not
    a round trip: its proceeds go into the round trip the rest of the position
    completes. The entry price is then the average cost of the shares still
    held. It needs ``highs`` and ``lows`` and uses ``opens`` for the gap check
    like the other exits (see the module docstring). With it left as None
    nothing changes.

    ``add_on_pct`` (> 0, default None = off) buys more of the position held on
    the bar after a close that is that percentage or more above the fill price
    of the latest buy into the position, at most ``max_adds`` times per
    position (a whole number >= 1; default 1 with ``add_on_pct``, and a
    ValueError without it). The add-on is sized like any buy, its fill says
    ``add_on``, and any other fill on the bar that is known when it would fill
    drops it (with open fills it fills at the open, before the bar's range is
    checked); one that gets 0
    shares is counted in ``add_on_skipped_buys``. It needs only the closes
    (and ``opens`` for open fills). See the module docstring. With it left as
    None nothing changes.

    ``warmup_closes`` (default None = off) are closes from the bars just
    before ``closes[0]``, oldest first. Only the signal sees them: the signal
    for bar ``t`` is worked out over ``warmup_closes + closes`` as of bar
    ``t``, so a moving average can already have its full window on bar 0.
    Signals are still only worked out on the bars of ``closes``, never on a
    warm-up bar, so nothing can fill on bar 0 (a crossing on the last warm-up
    bar is not acted on) and the first fill can come on bar 1. Everything else
    is counted on ``closes`` alone: bar numbers, fills, cash, the equity curve
    and its drawdown, the round trips and the buy-and-hold benchmark; the
    exits, ATR, ``highs``, ``lows`` and ``opens`` do not use the warm-up bars.
    None and an empty list both leave everything as without it.

    Raises ValueError for an empty price list, a non-positive price, a
    non-positive ``initial_cash``, negative costs, a ``slippage_pct`` outside
    [0, 100), a ``position_size`` outside (0, 1], a ``stop_pct`` outside
    (0, 100), a ``take_profit_pct`` that is not positive, a ``trail_pct``
    outside (0, 100), a ``breakeven_pct`` that is not positive, exits without
    matching ``highs`` and ``lows``, a ``risk_pct`` outside (0, 100], an
    ``atr_mult`` that is not positive, an ``atr_period`` that is not a whole
    number of at least 1, ``risk_pct`` without matching ``highs`` and
    ``lows`` (or with a high below its low), an ``atr_stop`` that is not True
    or False, ``atr_stop`` with a high below its low, a ``cooldown`` that is
    not a whole number of at least 0, a ``max_hold`` or ``min_hold`` that is
    not a whole number of at least 0, a ``max_drawdown_limit_pct`` outside (0, 100), a
    ``max_losses`` that is not a whole number of at least 0, a ``scale_out_pct`` that
    is not positive, an ``add_on_pct`` that is not positive, a ``max_adds``
    without ``add_on_pct`` or that is not a whole number of at least 1, an unknown strategy or
    parameter, invalid parameters (for
    example an invalid window pair), an unknown ``fill``, ``fill="open"``
    without matching positive ``opens``, or ``opens`` given together with an
    exit that do not match the closes or are not positive, or a non-positive
    price in ``warmup_closes`` (its message counts warm-up bars from 0).
    """
    _validate_inputs(closes, initial_cash, fee, fee_pct)
    warmup_closes = list(warmup_closes or ())
    for i, price in enumerate(warmup_closes):
        if not price > 0:
            raise ValueError(f"warm-up bar {i}: price must be positive, got {price}")
    if not 0 <= slippage_pct < 100:
        raise ValueError(f"slippage_pct must be between 0 and 100 (exclusive), got {slippage_pct}")
    if position_size is not None and not 0 < position_size <= 1:
        raise ValueError(f"position_size must be above 0 and at most 1, got {position_size}")
    if stop_pct is not None and not 0 < stop_pct < 100:
        raise ValueError(f"stop_pct must be between 0 and 100 (both exclusive), got {stop_pct}")
    if take_profit_pct is not None and not take_profit_pct > 0:
        raise ValueError(f"take_profit_pct must be positive, got {take_profit_pct}")
    if trail_pct is not None and not 0 < trail_pct < 100:
        raise ValueError(f"trail_pct must be between 0 and 100 (both exclusive), got {trail_pct}")
    if breakeven_pct is not None and not breakeven_pct > 0:
        raise ValueError(f"breakeven_pct must be positive, got {breakeven_pct}")
    if scale_out_pct is not None and not scale_out_pct > 0:
        raise ValueError(f"scale_out_pct must be positive, got {scale_out_pct}")
    if risk_pct is not None and not 0 < risk_pct <= 100:
        raise ValueError(f"risk_pct must be above 0 and at most 100, got {risk_pct}")
    if not atr_mult > 0:
        raise ValueError(f"atr_mult must be positive, got {atr_mult}")
    if isinstance(atr_period, bool) or not isinstance(atr_period, int) or atr_period < 1:
        raise ValueError(f"atr_period must be a whole number of at least 1, got {atr_period!r}")
    if not isinstance(atr_stop, bool):
        raise ValueError(f"atr_stop must be True or False, got {atr_stop!r}")
    if isinstance(cooldown, bool) or not isinstance(cooldown, int) or cooldown < 0:
        raise ValueError(f"cooldown must be a whole number of at least 0, got {cooldown!r}")
    if isinstance(max_hold, bool) or not isinstance(max_hold, int) or max_hold < 0:
        raise ValueError(f"max_hold must be a whole number of at least 0, got {max_hold!r}")
    if isinstance(min_hold, bool) or not isinstance(min_hold, int) or min_hold < 0:
        raise ValueError(f"min_hold must be a whole number of at least 0, got {min_hold!r}")
    if isinstance(max_losses, bool) or not isinstance(max_losses, int) or max_losses < 0:
        raise ValueError(f"max_losses must be a whole number of at least 0, got {max_losses!r}")
    if add_on_pct is not None and not add_on_pct > 0:
        raise ValueError(f"add_on_pct must be positive, got {add_on_pct}")
    if max_adds is not None:
        if add_on_pct is None:
            raise ValueError("max_adds needs add_on_pct")
        if isinstance(max_adds, bool) or not isinstance(max_adds, int) or max_adds < 1:
            raise ValueError(f"max_adds must be a whole number of at least 1, got {max_adds!r}")
    elif add_on_pct is not None:
        max_adds = 1  # add_on_pct alone: one add-on per position
    if max_drawdown_limit_pct is not None and not 0 < max_drawdown_limit_pct < 100:
        raise ValueError(
            f"max_drawdown_limit_pct must be between 0 and 100 (both exclusive), got {max_drawdown_limit_pct}"
        )
    exits = (
        stop_pct is not None or take_profit_pct is not None or trail_pct is not None or atr_stop
        or breakeven_pct is not None or scale_out_pct is not None
    )
    if exits:
        if highs is None or lows is None:
            if stop_pct is not None or take_profit_pct is not None:
                raise ValueError("a stop loss or take profit needs the high and low of every bar")
            if trail_pct is not None:
                raise ValueError("a trailing stop needs the high and low of every bar")
            if atr_stop:
                raise ValueError("an ATR stop needs the high and low of every bar")
            if breakeven_pct is not None:
                raise ValueError("a breakeven stop needs the high and low of every bar")
            raise ValueError("a scale-out needs the high and low of every bar")
        if len(highs) != len(closes) or len(lows) != len(closes):
            raise ValueError(f"{len(highs)} highs and {len(lows)} lows but {len(closes)} closes")
    atr_values = None
    if risk_pct is not None:
        if highs is None or lows is None:
            raise ValueError("risk sizing needs the high and low of every bar")
        if len(highs) != len(closes) or len(lows) != len(closes):
            raise ValueError(f"{len(highs)} highs and {len(lows)} lows but {len(closes)} closes")
    if risk_pct is not None or atr_stop:
        # Only then: the exits alone never check candle shape, and atr() would.
        # ATR at index t uses bars 0..t only; also raises ValueError for a high below its low.
        atr_values = atr(highs, lows, closes, atr_period)
    if fill not in FILLS:
        raise ValueError(f"unknown fill {fill!r}; choose one of: {', '.join(FILLS)}")
    use_opens = fill == "open" or (exits and opens is not None)  # fills, or gap checks on exits
    if fill == "open" and opens is None:
        raise ValueError("fill on open needs the open price of every bar")
    if use_opens:
        _check_opens(opens, closes)
    signal_fn, _, _ = get_strategy(strategy)
    if strategy == "sma_cross":
        params = {"short": short, "long": long}
        params.update(strategy_params or {})
        if strategy_params is None:
            if short >= long:
                raise ValueError("short window must be smaller than long window")
        else:
            params = resolve_params(strategy, params)
    else:
        params = resolve_params(strategy, strategy_params)

    portfolio = Portfolio(initial_cash, fee=fee, fee_pct=fee_pct)
    trades = []
    round_trips = []
    daily = []
    # dict(entry_bar, shares, outlay, basis, peak, atr_distance, armed, held, entry, proceeds, scaled) while a
    # position is held; see fill_signal
    open_round = None
    pending = None  # signal from the previous bar, to be filled on this bar
    risk_skipped = 0  # buys the ATR rules gave 0 shares
    blocked_until = -1  # last bar of the current cooldown: no buy fills on a bar <= this
    cooldown_skipped = 0  # buys dropped because they fell in a cooldown
    equity_peak = None  # highest account value at a close so far (drawdown halt)
    halt_bar = None  # bar whose close set off the drawdown halt: no buy fills after it
    drawdown_skipped = 0  # buys dropped because the run had halted
    min_hold_skipped = 0  # signal sells dropped because they fell inside the minimum holding time
    loss_streak = 0  # completed round trips in a row that lost money (max_losses)
    loss_halt_bar = None  # bar of the losing sale that completed the streak: no buy fills after it
    loss_skipped = 0  # buys dropped because the losing streak had halted the run
    add_on_due = False  # the last close set off an add-on, to be tried on this bar after everything else
    add_on_skipped = 0  # add-ons that got 0 shares (cash, position size or the ATR rules)
    # The signal's view of the prices: the warm-up bars, then closes; bar t of closes is index t + offset.
    offset = len(warmup_closes)
    signal_closes = warmup_closes + list(closes) if offset else closes

    def sell_all(t, fill_price, reason):
        """Sell the whole position; None if the fees would make the cash negative."""
        nonlocal open_round, loss_streak, loss_halt_bar
        shares = portfolio.position
        try:
            cost = portfolio.sell(shares, fill_price)
        except ValueError:
            return None  # fees would make cash negative: keep the position
        round_trip = RoundTrip(
            entry_bar=open_round["entry_bar"],
            exit_bar=t,
            shares=open_round["shares"],
            outlay=open_round["outlay"],
            proceeds=open_round["proceeds"] + (shares * fill_price - cost),  # plus a scale-out's, if any
        )
        round_trips.append(round_trip)
        open_round = None
        if max_losses and loss_halt_bar is None:
            # Any round trip that did not lose (0.00 included) resets the streak, whatever sold it.
            loss_streak = loss_streak + 1 if round_trip.pnl < 0 else 0
            if loss_streak >= max_losses:
                loss_halt_bar = t  # nothing is held now; buys due from bar t + 1 on are dropped
        return Trade(t, SELL, shares, fill_price, portfolio.cash, cost, reason)

    def size_buy(t, bar_price):
        """Size a buy on bar ``t`` at ``bar_price`` (plus slippage) by the sizing rules in use.

        Returns ``(shares, fill_price, stop_distance, atr_skip)``; ``atr_skip`` is True when the ATR rules gave
        0 shares (no usable ATR on the signal bar, or with risk sizing a risk under 1 share). Counts nothing.
        """
        fill_price = bar_price * (1 + slippage_pct / 100.0) if slippage_pct else bar_price
        if position_size is None:
            shares = portfolio.max_affordable(fill_price)
        else:
            shares = _max_shares_within(portfolio, fill_price, position_size * portfolio.equity(bar_price))
        stop_distance = None
        atr_skip = False
        if atr_values is not None:
            # The buy was set off on bar t - 1: use that bar's ATR, never bar t's.
            signal_atr = atr_values[t - 1]
            stop_distance = 0.0 if signal_atr is None else atr_mult * signal_atr
        if risk_pct is not None:
            if stop_distance > 0:
                risk = portfolio.equity(bar_price) * risk_pct / 100.0
                # Cap before int(): a ratio above the cash limit (even inf, from a tiny
                # stop distance) would be cut to that limit anyway.
                risk_shares = int(min(risk / stop_distance, shares + 1))
            else:
                risk_shares = 0  # no ATR yet, or an ATR of 0: the risk cannot be sized
            if risk_shares == 0:
                atr_skip = True
            shares = min(shares, risk_shares)
        elif atr_stop and not stop_distance > 0:
            atr_skip = True  # no ATR yet, or an ATR of 0: no stop level can be set
            shares = 0
        return shares, fill_price, stop_distance, atr_skip

    def book_buy(t, shares, fill_price, stop_distance, reason):
        """Buy ``shares`` at ``fill_price`` into the position (opening it if none is held); the Trade."""
        nonlocal open_round
        cost = portfolio.buy(shares, fill_price)
        if open_round is None:
            # peak: highest high of the bars after the entry bar seen so far (trailing stop)
            # atr_distance: the ATR stop's distance, fixed by the buy that opens the position
            # armed: a high after the entry bar has reached the breakeven trigger (breakeven stop)
            # shares: shares bought; held: shares still held (fewer after a scale-out)
            # basis: cost of the shares held, fees left out; entry: their average cost, basis / held
            # proceeds: net cash from a scale-out so far; scaled: the scale-out has sold (once per position)
            # last_buy: fill price of the latest buy into the position (add-ons); adds: add-on buys filled
            open_round = {
                "entry_bar": t, "shares": 0, "outlay": 0.0, "basis": 0.0, "peak": None,
                "atr_distance": stop_distance if atr_stop else None, "armed": False,
                "held": 0, "entry": None, "proceeds": 0.0, "scaled": False,
                "last_buy": None, "adds": 0,
            }
        open_round["shares"] += shares
        open_round["held"] += shares
        open_round["outlay"] += shares * fill_price + cost
        open_round["basis"] += shares * fill_price
        open_round["entry"] = open_round["basis"] / open_round["held"]
        open_round["last_buy"] = fill_price  # slippage included, as the fill records it
        return Trade(t, BUY, shares, fill_price, portfolio.cash, cost, reason)

    def fill_signal(t, bar_price):
        """Fill the pending signal at ``bar_price`` (plus slippage); the Trade or None."""
        nonlocal risk_skipped, cooldown_skipped, drawdown_skipped, min_hold_skipped, loss_skipped
        if pending == BUY:
            if halt_bar is not None:
                # Halted: dropped and counted here only, before the cooldown and the sizing rules look at it.
                drawdown_skipped += 1
                return None
            if loss_halt_bar is not None:
                # Halted by the losing streak: likewise, but after the drawdown halt, which counts a buy first.
                loss_skipped += 1
                return None
            if t <= blocked_until:
                # In a cooldown: dropped, not delayed, and counted before any sizing rule looks at it.
                cooldown_skipped += 1
                return None
            shares, fill_price, stop_distance, atr_skip = size_buy(t, bar_price)
            if atr_skip:
                risk_skipped += 1
            if shares:
                return book_buy(t, shares, fill_price, stop_distance, "signal")
        elif pending == SELL and portfolio.position:
            if min_hold and t - open_round["entry_bar"] < min_hold:
                # Held too briefly: dropped, not delayed, and counted before the fees are looked at.
                min_hold_skipped += 1
                return None
            fill_price = bar_price * (1 - slippage_pct / 100.0) if slippage_pct else bar_price
            return sell_all(t, fill_price, "signal")
        return None

    def check_exits(t, open_only=False):
        """Stop loss / trailing stop / ATR stop / breakeven stop / take profit on bar ``t`` for a position entered earlier; the Trade or None.

        ``open_only``: look only for a gap through a level at the bar's open, not at the bar's range.
        """
        nonlocal blocked_until
        if not exits or open_round is None or open_round["entry_bar"] >= t:
            return None
        entry = open_round["entry"]
        stop = entry * (1 - stop_pct / 100.0) if stop_pct is not None else None
        stop_reason = "stop"
        if trail_pct is not None:
            # Highest high since entry: the entry price and the highs of the bars
            # after the entry bar, up to bar t - 1. Bar t's own high is not used.
            peak = entry if open_round["peak"] is None else max(entry, open_round["peak"])
            trail = peak * (1 - trail_pct / 100.0)
            if stop is None or trail > stop:  # a falling price meets the higher level first
                stop, stop_reason = trail, "trail"
        if atr_stop:
            # Measured from the current average entry, with the distance fixed when the position opened.
            atr_level = entry - open_round["atr_distance"]
            if stop is None or atr_level > stop:  # on a tie the stop or the trail keeps it
                stop, stop_reason = atr_level, "atr"
        if breakeven_pct is not None and open_round["armed"]:
            # Armed by an earlier bar's high; the level follows the current average entry.
            if stop is None or entry > stop:  # on a tie the stop, the trail or atr keeps it
                stop, stop_reason = entry, "breakeven"
        target = entry * (1 + take_profit_pct / 100.0) if take_profit_pct is not None else None
        bar_open = opens[t] if use_opens else None
        if bar_open is not None and stop is not None and bar_open <= stop:
            exit_price, reason = bar_open, stop_reason  # gapped through the stop: fills at the open
        elif bar_open is not None and target is not None and bar_open >= target:
            exit_price, reason = bar_open, "target"  # gapped through the target: fills at the open
        elif open_only:
            return None
        elif stop is not None and lows[t] <= stop:
            exit_price, reason = stop, stop_reason  # the stop wins over the target
        elif target is not None and highs[t] >= target:
            exit_price, reason = target, "target"
        else:
            return None
        if slippage_pct:
            exit_price *= 1 - slippage_pct / 100.0
        trade = sell_all(t, exit_price, reason)
        if trade is not None and cooldown and reason in ("stop", "trail", "atr", "breakeven"):
            blocked_until = t + cooldown  # bars t + 1 .. t + cooldown take no buy
        return trade

    def scale_out(t):
        """Sell half the shares held (rounded down) once per position on bar ``t``; the Trade or None.

        Called only when nothing else has filled on the bar: every other fill beats it.
        """
        if scale_out_pct is None or open_round is None or open_round["scaled"] or open_round["entry_bar"] >= t:
            return None
        shares = portfolio.position // 2
        if not shares:
            return None  # 1 share: nothing to sell, and the scale-out is not used up
        entry = open_round["entry"]
        level = entry * (1 + scale_out_pct / 100.0)
        if use_opens and opens[t] >= level:
            exit_price = opens[t]  # gapped through the level: fills at the open
        elif highs[t] >= level:
            exit_price = level
        else:
            return None
        if slippage_pct:
            exit_price *= 1 - slippage_pct / 100.0
        try:
            cost = portfolio.sell(shares, exit_price)
        except ValueError:
            return None  # fees would make cash negative: not used up, tried again on a later bar
        open_round["scaled"] = True
        open_round["held"] -= shares
        open_round["proceeds"] += shares * exit_price - cost
        open_round["basis"] = entry * open_round["held"]  # the average cost of the shares held stays the entry
        return Trade(t, SELL, shares, exit_price, portfolio.cash, cost, "scale_out")

    def time_due(t):
        """True when the position has been held ``max_hold`` bars or more by bar ``t``."""
        return bool(max_hold) and open_round is not None and t - open_round["entry_bar"] >= max_hold

    def time_exit(t, bar_price):
        """Sell the whole position at ``bar_price`` (less slippage) for the maximum holding time; the Trade or None."""
        fill_price = bar_price * (1 - slippage_pct / 100.0) if slippage_pct else bar_price
        return sell_all(t, fill_price, "time")  # no cooldown: only stop, trail, atr and breakeven exits start one

    def drawdown_due(t):
        """True when the run has halted and a position is still held (only buys before the halt can open one)."""
        return halt_bar is not None and open_round is not None

    def drawdown_exit(t, bar_price):
        """Sell the whole position at ``bar_price`` (less slippage) after the drawdown halt; the Trade or None."""
        fill_price = bar_price * (1 - slippage_pct / 100.0) if slippage_pct else bar_price
        return sell_all(t, fill_price, "drawdown")  # no cooldown: only stop, trail, atr and breakeven exits start one

    def add_on(t, bar_price):
        """Buy more of the position held at ``bar_price`` (plus slippage), sized like any buy; the Trade or None.

        Called only when an add-on is due and no fill known by then has happened on the bar: with close fills
        after every other fill, with open fills at the open, after the signal fill, a gap sale, the time exit
        and the drawdown sale, and before the bar's range is checked.
        """
        nonlocal drawdown_skipped, add_on_skipped
        if open_round is None:
            return None
        if halt_bar is not None:
            # Halted: blocked like any buy and counted there only (in practice only when the drawdown sale was
            # refused by the fees, since that sale otherwise takes the bar).
            drawdown_skipped += 1
            return None
        shares, fill_price, stop_distance, _ = size_buy(t, bar_price)
        if not shares:
            add_on_skipped += 1  # not one of max_adds, and the last buy price stays
            return None
        open_round["adds"] += 1
        return book_buy(t, shares, fill_price, stop_distance, "add_on")

    for t, price in enumerate(closes):
        bar_price = opens[t] if fill == "open" else price
        if fill == "open":
            trade = fill_signal(t, bar_price)  # the open comes first, then the bar's range
            if trade is None and (time_due(t) or drawdown_due(t) or add_on_due):
                # Still at the open: a gap through a stop or the target sells first, then the time exit,
                # then the drawdown sale, then the add-on. Only what is known at the open can drop the add-on:
                # once it fills, the bar's range is not checked (one fill per bar), so nothing later in the bar
                # decides whether it was made.
                trade = check_exits(t, open_only=True)
                if trade is None and time_due(t):
                    trade = time_exit(t, bar_price)
                if trade is None and drawdown_due(t):
                    trade = drawdown_exit(t, bar_price)
                if trade is None and add_on_due:
                    trade = add_on(t, bar_price)
            if trade is None:
                trade = check_exits(t)
            if trade is None:
                trade = scale_out(t)  # every other fill on the bar beats it
        else:
            trade = check_exits(t)  # the bar's range comes before its close
            if trade is None:
                trade = fill_signal(t, bar_price)
            if trade is None:
                trade = scale_out(t)  # after the signal fill, which beats it; the time exit waits for it
            if trade is None and time_due(t):
                trade = time_exit(t, bar_price)  # only on a bar that has no other fill
            if trade is None and drawdown_due(t):
                trade = drawdown_exit(t, bar_price)  # likewise, and after the time exit
            if trade is None and add_on_due:
                trade = add_on(t, bar_price)  # lowest priority: any other fill on the bar drops it
        if trade is not None:
            trades.append(trade)
        if trail_pct is not None and open_round is not None and open_round["entry_bar"] < t:
            # Bar t is over: its high may now count towards the trailing stop of later bars.
            peak = open_round["peak"]
            open_round["peak"] = highs[t] if peak is None else max(peak, highs[t])
        if (
            breakeven_pct is not None and open_round is not None and open_round["entry_bar"] < t
            and not open_round["armed"]
        ):
            # Bar t is over: if its high reached the trigger, the breakeven stop acts from bar t + 1 on.
            # Measured from the average entry as it stands now, after any buy on this bar.
            entry = open_round["entry"]
            if highs[t] >= entry * (1 + breakeven_pct / 100.0):
                open_round["armed"] = True

        # Signal generated at this close, using only prices up to and including it (warm-up bars included).
        signal = signal_fn(signal_closes, t + offset, **params)
        equity = portfolio.equity(price)
        daily.append(
            DailyRecord(
                bar=t,
                close=price,
                signal=signal,
                trade=trade,
                cash=portfolio.cash,
                position=portfolio.position,
                equity=equity,
            )
        )
        pending = signal
        # An add-on is due on bar t + 1 when this close is add_on_pct or more above the latest buy's fill price,
        # fewer than max_adds add-ons have filled in the position, and the bar's signal is neither BUY nor SELL
        # (a SELL drops it even if min_hold then holds the sale back; a BUY takes the next bar's buy).
        add_on_due = (
            add_on_pct is not None and open_round is not None and open_round["adds"] < max_adds
            and signal != BUY and signal != SELL
            and price >= open_round["last_buy"] * (1 + add_on_pct / 100.0)
        )
        if max_drawdown_limit_pct is not None and halt_bar is None:
            # Same peak and percentage as drawdown_curve_pct, so the halt agrees with the export's drawdown_pct.
            if equity_peak is None or equity > equity_peak:
                equity_peak = equity
            if equity_peak > 0 and (equity - equity_peak) / equity_peak * 100.0 <= -max_drawdown_limit_pct:
                halt_bar = t

    return BacktestResult(
        initial_cash=float(initial_cash),
        final_cash=portfolio.cash,
        final_position=portfolio.position,
        final_price=closes[-1],
        trades=trades,
        fee=float(fee),
        fee_pct=float(fee_pct),
        total_costs=portfolio.total_costs,
        round_trips=round_trips,
        daily=daily,
        benchmark=run_buy_and_hold(
            closes, initial_cash, fee=fee, fee_pct=fee_pct, fill=fill, opens=opens, slippage_pct=slippage_pct
        ),
        strategy=strategy,
        strategy_params=dict(params),
        fill=fill,
        slippage_pct=float(slippage_pct),
        position_size=None if position_size is None else float(position_size),
        stop_pct=None if stop_pct is None else float(stop_pct),
        take_profit_pct=None if take_profit_pct is None else float(take_profit_pct),
        trail_pct=None if trail_pct is None else float(trail_pct),
        risk_pct=None if risk_pct is None else float(risk_pct),
        atr_mult=None if risk_pct is None and not atr_stop else float(atr_mult),
        atr_period=None if risk_pct is None and not atr_stop else atr_period,
        risk_skipped_buys=risk_skipped,
        atr_stop=atr_stop,
        breakeven_pct=None if breakeven_pct is None else float(breakeven_pct),
        cooldown=cooldown,
        cooldown_skipped_buys=cooldown_skipped,
        max_hold=max_hold,
        min_hold=min_hold,
        min_hold_skipped_sells=min_hold_skipped,
        max_drawdown_limit_pct=None if max_drawdown_limit_pct is None else float(max_drawdown_limit_pct),
        drawdown_halt_bar=halt_bar,
        drawdown_skipped_buys=drawdown_skipped,
        max_losses=max_losses,
        loss_halt_bar=loss_halt_bar,
        loss_skipped_buys=loss_skipped,
        scale_out_pct=None if scale_out_pct is None else float(scale_out_pct),
        add_on_pct=None if add_on_pct is None else float(add_on_pct),
        max_adds=max_adds,
        add_on_skipped_buys=add_on_skipped,
    )


def signal_at(closes, t, short=20, long=50):
    """Signal for bar ``t`` using only ``closes[0..t]``.

    ``crossover_signal`` only looks at the last ``long + 1`` bars, so passing
    that window is identical to passing the full prefix ``closes[:t + 1]``
    while keeping the cost per bar constant. The slice ends at ``t``, so no
    later price can leak in.
    """
    start = max(0, t - long)
    return crossover_signal(closes[start : t + 1], short=short, long=long)


EXPORT_COLUMNS = [
    "bar",
    "date",
    "close",
    "signal",
    "action",
    "shares",
    "price",
    "value",
    "cost",
    "cash",
    "position",
    "equity",
    "drawdown_pct",
    "buy_hold_equity",
]


def export_columns(result):
    """Header for ``export_rows``: ``EXPORT_COLUMNS`` plus ``reason`` when exits were in use."""
    return EXPORT_COLUMNS + ["reason"] if result.has_exits else list(EXPORT_COLUMNS)


def export_rows(result, dates=None):
    """One list of strings per bar, in ``export_columns(result)`` order (header not included).

    ``dates`` is an optional list of labels (e.g. the input file's date
    column) with one entry per bar; the column is left blank otherwise. With
    a stop loss, take profit, trailing stop, ATR stop, breakeven stop,
    maximum holding time, drawdown halt, scale-out or add-ons in use a last
    column says why a fill happened (``signal``, ``stop``, ``target``,
    ``trail``, ``atr``, ``breakeven``, ``time``, ``drawdown`` or
    ``scale_out``; ``add_on`` for an add-on buy).
    """
    drawdowns = drawdown_curve_pct(result.equity_curve)
    bench = result.benchmark.equity_curve if result.benchmark else []
    rows = []
    for i, day in enumerate(result.daily):
        trade = day.trade
        rows.append(
            [
                str(day.bar),
                dates[i] if dates and i < len(dates) else "",
                f"{day.close:.2f}",
                day.signal,
                trade.side if trade else "",
                str(trade.shares) if trade else "",
                f"{trade.price:.2f}" if trade else "",
                f"{trade.value:.2f}" if trade else "",
                f"{trade.cost:.2f}" if trade else "",
                f"{day.cash:.2f}",
                str(day.position),
                f"{day.equity:.2f}",
                f"{drawdowns[i]:.2f}",
                f"{bench[i]:.2f}" if i < len(bench) else "",
            ]
            + ([trade.reason if trade else ""] if result.has_exits else [])
        )
    return rows


def write_export(result, fileobj, dates=None):
    """Write the header plus ``export_rows`` as CSV to an open text file. Returns the row count."""
    writer = csv.writer(fileobj)
    writer.writerow(export_columns(result))
    rows = export_rows(result, dates)
    writer.writerows(rows)
    return len(rows)


def export_csv(result, path, dates=None):
    """Write one row per bar (account value, signal, and any fill) to ``path``.

    Returns the number of rows written. See ``export_rows`` for the columns.
    """
    with open(path, "w", newline="") as f:
        return write_export(result, f, dates)


# Note after the "Exits:" line, keyed by (stop, trail, target) in use; "" when only one exit is set.
_EXITS_NOTES = {
    (True, False, True): " (stop wins if a bar touches both)",
    (True, True, False): " (the higher of stop and trail is used)",
    (False, True, True): " (trail wins if a bar touches both)",
    (True, True, True): " (the higher of stop and trail is used; it wins if a bar also touches the target)",
}


def _exits_note(stop, trail, atr_stop, target, breakeven=False):
    """Note after the "Exits:" line; ``_EXITS_NOTES`` when the ATR and breakeven stops are off, so those lines
    never change."""
    if not atr_stop and not breakeven:
        return _EXITS_NOTES.get((stop, trail, target), "")
    stops = [
        name
        for name, on in (("stop", stop), ("trail", trail), ("atr", atr_stop), ("breakeven", breakeven))
        if on
    ]
    if len(stops) == 1:
        return f" ({stops[0]} wins if a bar touches both)" if target else ""
    if len(stops) == 2:
        rule = f"the higher of {stops[0]} and {stops[1]} is used, {stops[0]} on a tie"
    else:
        rule = f"the highest of {', '.join(stops[:-1])} and {stops[-1]} is used, in that order on a tie"
    return f" ({rule}; it wins if a bar also touches the target)" if target else f" ({rule})"


def format_result(result, short, long):
    """Human-readable report lines for the CLI."""
    if result.strategy == "sma_cross":
        title = f"SMA {short}/{long} crossover"
    else:
        params = ", ".join(f"{k}={v}" for k, v in result.strategy_params.items())
        title = f"{result.strategy} ({params})"
    fills = "next-bar open fills" if result.fill == "open" else "next-bar fills"
    lines = [
        f"Backtest: {title}, {fills}, whole shares, no shorting",
        f"  Start cash:  {result.initial_cash:,.2f}",
        f"  Trades:      {result.n_trades} ({result.n_buys} buy, {result.n_sells} sell)",
    ]
    if result.trades:
        lines.append("  Fills (bar index is 0-based):")
    for i, trade in enumerate(result.trades, start=1):
        lines.append(
            f"    #{i:<3d} bar {trade.bar:<5d} {trade.side:<4s} {trade.shares:>8d} @ {trade.price:>10,.2f}"
            f"  value {trade.value:>12,.2f}  cost {trade.cost:>8,.2f}  cash {trade.cash_after:>12,.2f}"
            + (f"  {trade.reason}" if result.has_exits else "")
        )

    lines.append(
        f"  Costs:       {result.total_costs:,.2f} paid "
        f"(fee {result.fee:,.2f} per trade + {result.fee_pct:.2f}% of value)"
    )
    if result.slippage_pct:
        lines.append(
            f"  Slippage:    {result.slippage_pct:.2f}% (buys fill higher, sells lower, before fees)"
        )
    if result.position_size is not None:
        lines.append(
            f"  Sizing:      each buy at most {result.position_size:.0%} of account value "
            f"(costs and slippage included)"
        )
    skipped = result.risk_skipped_buys
    plural = "" if skipped == 1 else "s"
    if result.risk_pct is not None:
        placed = (
            "the ATR stop sells at this distance, as of the buy that opened the position, below the average "
            "entry price; a gap, slippage, fees or a later buy can lose more"
            if result.atr_stop
            else "this only sets the number of shares; no stop is placed"
        )
        lines.append(
            f"  Risk sizing: {result.risk_pct:.2f}% of account value at risk per buy, "
            f"stop distance {result.atr_mult:g} x ATR({result.atr_period}) ({placed})"
        )
        if skipped:
            lines.append(
                f"  Skipped:     {skipped} buy{plural} "
                f"(risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)"
            )
    elif result.atr_stop and skipped:
        lines.append(f"  Skipped:     {skipped} buy{plural} (ATR stop: no usable ATR on the signal bar)")
    if result.has_price_exits:
        parts = []
        if result.stop_pct is not None:
            parts.append(f"stop {result.stop_pct:.2f}% below entry")
        if result.trail_pct is not None:
            parts.append(f"trail {result.trail_pct:.2f}% below the highest high since entry")
        if result.atr_stop:
            parts.append(f"atr {result.atr_mult:g} x ATR({result.atr_period}) below entry")
        if result.breakeven_pct is not None:
            parts.append(f"breakeven at entry once a later high is {result.breakeven_pct:.2f}% above it")
        if result.take_profit_pct is not None:
            parts.append(f"target {result.take_profit_pct:.2f}% above entry")
        note = _exits_note(
            result.stop_pct is not None, result.trail_pct is not None, result.atr_stop,
            result.take_profit_pct is not None, result.breakeven_pct is not None,
        )
        lines.append(f"  Exits:       {', '.join(parts)}{note}")
    if result.scale_out_pct is not None:
        # Only when the scale-out is on, so the report of a run without it stays exactly as before.
        k = result.n_scale_out_exits
        lines.append(
            f"  Scale out:   half the shares held (rounded down), once per position, when a high reaches "
            f"{result.scale_out_pct:.2f}% above the average entry; {k} partial sell{'' if k == 1 else 's'}, "
            f"not counted as round trips"
        )
    if result.add_on_pct is not None:
        # Only when add-ons are on, so the report of a run without them stays exactly as before.
        n, k, z = result.max_adds, result.n_add_on_buys, result.add_on_skipped_buys
        lines.append(
            f"  Add-ons:     up to {n} per position, a buy on the next bar after a close {result.add_on_pct:.2f}% "
            f"or more above the latest buy price, when nothing else fills on that bar; "
            f"{k} add-on buy{'' if k == 1 else 's'}, {z} skipped (0 shares)"
        )
    if result.cooldown:
        # Only when a cooldown is on, so the report of a run without one stays exactly as before.
        n, k = result.cooldown, result.cooldown_skipped_buys
        # "breakeven" is named only when that stop is on, so the line of a run without it stays as before.
        kinds = "stop, trail, atr or breakeven" if result.breakeven_pct is not None else "stop, trail or atr"
        lines.append(
            f"  Cooldown:    {n} bar{'' if n == 1 else 's'} after a {kinds} exit; "
            f"{k} buy{'' if k == 1 else 's'} skipped"
        )
    if result.min_hold:
        # Only when a minimum holding time is on, so the report of a run without one stays exactly as before.
        n, k = result.min_hold, result.min_hold_skipped_sells
        lines.append(
            f"  Min hold:    {n} bar{'' if n == 1 else 's'} after a position's first buy before a signal sell "
            f"can fill; {k} signal sell{'' if k == 1 else 's'} skipped"
        )
    if result.max_hold:
        # Only when a maximum holding time is on, so the report of a run without one stays exactly as before.
        n, k = result.max_hold, result.n_time_exits
        lines.append(
            f"  Max hold:    {n} bar{'' if n == 1 else 's'} after a position's first buy, "
            f"then sold at the bar's fill price; {k} time exit{'' if k == 1 else 's'}"
        )
    if result.max_drawdown_limit_pct is not None:
        # Only when the drawdown halt is on, so the report of a run without it stays exactly as before.
        h, k = result.drawdown_halt_bar, result.drawdown_skipped_buys
        state = "not triggered" if h is None else f"triggered at bar {h}, no buy fills after it"
        lines.append(
            f"  Drawdown:    halt at {result.max_drawdown_limit_pct:.2f}% below the peak account value at a close; "
            f"{state}; {k} buy{'' if k == 1 else 's'} skipped"
        )
    if result.max_losses:
        # Only when the losing-streak halt is on, so the report of a run without it stays exactly as before.
        n, h, k = result.max_losses, result.loss_halt_bar, result.loss_skipped_buys
        state = "not triggered" if h is None else f"triggered at bar {h}, no buy fills after it"
        lines.append(
            f"  Max losses:  halt after {n} losing round trip{'' if n == 1 else 's'} in a row; "
            f"{state}; {k} buy{'' if k == 1 else 's'} skipped"
        )
    n_rt = result.n_round_trips
    if n_rt:
        wins = result.n_winning_round_trips
        lines.append(
            f"  Round trips: {n_rt} completed, {wins} made money ({wins / n_rt * 100:.0f}%)"
        )
    else:
        lines.append("  Round trips: 0 completed")

    bench = result.benchmark
    if bench is not None:
        lines.append(f"  {'Comparison':<18s}{'Strategy':>14s}{'Buy & hold':>14s}")
        rows = [
            ("End equity", f"{result.final_equity:,.2f}", f"{bench.final_equity:,.2f}"),
            ("Return", f"{result.return_pct:+.2f}%", f"{bench.return_pct:+.2f}%"),
            ("Max drawdown", f"{result.max_drawdown_pct:.2f}%", f"{bench.max_drawdown_pct:.2f}%"),
            ("Trades", str(result.n_trades), str(bench.n_trades)),
            ("Costs paid", f"{result.total_costs:,.2f}", f"{bench.total_costs:,.2f}"),
        ]
        for label, a, b in rows:
            lines.append(f"    {label:<16s}{a:>14s}{b:>14s}")

    lines += [
        f"  End cash:    {result.final_cash:,.2f}",
        f"  End shares:  {result.final_position} @ {result.final_price:,.2f}",
        f"  End equity:  {result.final_equity:,.2f}",
        f"  Return:      {result.return_pct:+.2f}%",
    ]
    return lines


def format_stats(result):
    """Report lines for the "Risk and return" block; ``n/a`` marks an undefined value.

    Kept apart from ``format_result`` so that function's output, which ends
    with the closing cash/shares/equity/return lines, stays unchanged.
    """
    st = result.stats

    def fmt(key, spec, suffix=""):
        value = st[key]
        return "n/a" if value is None else format(value, spec) + suffix

    return [
        "Risk and return",
        f"  Total return:       {fmt('total_return_pct', '+.2f', '%')}",
        f"  CAGR:               {fmt('cagr_pct', '.2f', '%')}",
        f"  Volatility (ann.):  {fmt('annualized_volatility_pct', '.2f', '%')}",
        f"  Sharpe ratio:       {fmt('sharpe_ratio', '.2f')}",
        f"  Sortino ratio:      {fmt('sortino_ratio', '.2f')}",
        f"  Exposure:           {fmt('exposure_pct', '.2f', '%')}",
        f"  Profit factor:      {fmt('profit_factor', '.2f')}",
        f"  Average win:        {fmt('average_win', ',.2f')}",
        f"  Average loss:       {fmt('average_loss', ',.2f')}",
        f"  Longest drawdown:   {fmt('longest_drawdown_bars', 'd', ' bars')}",
    ]


def trade_list(result):
    """One dict per completed round trip, in order, then one for a position still held at the end.

    The completed rows are ``result.round_trips`` itself, so their number and
    their wins are always those of the "Round trips:" line. Each row has
    ``open`` (False), ``entry_bar``, ``exit_bar``, ``bars_held`` (``exit_bar -
    entry_bar``), ``shares`` (all the shares bought), ``outlay`` (cash spent on
    the buys, fees included), ``proceeds`` (net cash from the sells, a
    scale-out's included), ``pnl``, ``return_pct`` (``pnl / outlay * 100``),
    ``reason`` (why the sale that completed it happened: ``signal``, ``stop``,
    ``time``, ...) and ``win`` (``pnl > 0``, as ``RoundTrip.is_win``).

    A position still held after the last fill adds a last row with ``open``
    True. It is not realized: ``exit_bar`` is None, ``bars_held`` counts to
    the last bar, and ``proceeds`` is the net cash of any scale-out plus the
    shares still held (``held``) marked at the last close with no selling
    costs, as the end equity is. ``reason`` is ``scale_out`` when part of it
    has been sold, otherwise None, and ``win`` is None. The row is rebuilt
    from the fills after the last round trip's exit bar (one fill per bar, so
    none of them belongs to a completed round trip).
    """
    sells = {t.bar: t for t in result.trades if t.side == SELL}
    rows = []
    for rt in result.round_trips:
        pnl = rt.pnl
        rows.append(
            {
                "open": False,
                "entry_bar": rt.entry_bar,
                "exit_bar": rt.exit_bar,
                "bars_held": rt.exit_bar - rt.entry_bar,
                "shares": rt.shares,
                "outlay": rt.outlay,
                "proceeds": rt.proceeds,
                "pnl": pnl,
                "return_pct": pnl / rt.outlay * 100.0,
                "reason": sells[rt.exit_bar].reason,
                "win": rt.is_win,
            }
        )
    if result.final_position:
        last_exit = result.round_trips[-1].exit_bar if result.round_trips else -1
        later = [t for t in result.trades if t.bar > last_exit]
        buys = [t for t in later if t.side == BUY]
        partial = [t for t in later if t.side == SELL]
        bought = sum(t.shares for t in buys)
        held = bought - sum(t.shares for t in partial)
        if not buys or held != result.final_position:
            raise ValueError(
                f"the fills after bar {last_exit} leave {held} shares, but the result holds {result.final_position}"
            )
        outlay = sum(t.value + t.cost for t in buys)  # same sum, in the same order, as the engine's outlay
        proceeds = sum(t.value - t.cost for t in partial) + held * result.final_price
        pnl = proceeds - outlay
        entry_bar = buys[0].bar
        rows.append(
            {
                "open": True,
                "entry_bar": entry_bar,
                "exit_bar": None,
                "bars_held": result.daily[-1].bar - entry_bar,
                "shares": bought,
                "held": held,
                "outlay": outlay,
                "proceeds": proceeds,
                "pnl": pnl,
                "return_pct": pnl / outlay * 100.0,
                "reason": "scale_out" if partial else None,
                "win": None,
            }
        )
    return rows


def format_trade_list(result):
    """Report lines for the trade list: a table of ``trade_list(result)`` and a footer, or one line when empty.

    The footer's completed and winning counts are taken from the rows, and are
    the numbers of the "Round trips:" line of ``format_result``.
    """
    rows = trade_list(result)
    if not rows:
        return ["Trade list: no trades"]
    lines = [
        "Trade list (bar index is 0-based)",
        f"  {'#':<5s}{'Entry':>6s}{'Exit':>6s}{'Bars':>6s}{'Shares':>9s}{'Outlay':>14s}{'Proceeds':>14s}"
        f"{'P/L':>13s}{'Return':>10s}  Reason",
    ]
    for i, row in enumerate(rows, start=1):
        label = "open" if row["open"] else str(i)
        exit_bar = "open" if row["open"] else str(row["exit_bar"])
        reason = row["reason"] or "-"
        lines.append(
            f"  {label:<5s}{row['entry_bar']:>6d}{exit_bar:>6s}{row['bars_held']:>6d}{row['shares']:>9d}"
            f"{row['outlay']:>14,.2f}{row['proceeds']:>14,.2f}{row['pnl']:>+13,.2f}{row['return_pct']:>+9.2f}%"
            f"  {reason}"
            + ("  (unrealized: marked at the last close, no selling costs)" if row["open"] else "")
        )
    completed = [row for row in rows if not row["open"]]
    n_rt = len(completed)
    if n_rt:
        wins = sum(1 for row in completed if row["win"])
        footer = f"  {n_rt} completed, {wins} made money ({wins / n_rt * 100:.0f}%)"
    else:
        footer = "  0 completed"
    if len(rows) > n_rt:
        footer += ", 1 open (unrealized)"
    lines.append(footer)
    return lines
