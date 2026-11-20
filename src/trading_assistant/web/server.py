"""Small local web page for running backtests in the browser.

Start it with::

    python -m trading_assistant.web            # http://127.0.0.1:8765/
    python -m trading_assistant.web --port 9000

Design notes
------------
* Standard library only (``http.server``). No files are read from disk: the
  page, stylesheet and script are Python strings in ``assets.py``. The only
  routes are ``/``, ``/style.css``, ``/app.js``, ``/api/samples``,
  ``/api/health``, ``POST /api/backtest``, ``POST /api/scan``,
  ``POST /api/walkforward`` and ``POST /api/portfolio``; anything else is a 404.
  ``/api/samples`` also lists the strategies (name, default parameters,
  description) for the strategy picker.
* The server binds to the loopback address by default and checks the
  ``Host`` header, so pages on other sites (or DNS-rebinding tricks) cannot
  use it. ``POST /api/backtest`` requires ``Content-Type: application/json``,
  which browsers will not send cross-origin without a CORS preflight that we
  never approve.
* Every response carries a strict Content-Security-Policy (no inline script or
  style, nothing from the network), ``X-Content-Type-Options: nosniff``,
  ``X-Frame-Options: DENY`` and ``Referrer-Policy: no-referrer``.
* All input is validated on the server with the same functions the command
  line uses, so the page and the CLI give identical numbers and identical
  error messages. Errors are JSON with a one-line message; unexpected
  exceptions are logged with their traceback and answered with a generic
  500, never a stack trace.
* Limits: request body <= MAX_BODY_BYTES, <= MAX_BARS price rows, SMA windows
  <= MAX_WINDOW, and a run is abandoned after MAX_RUN_SECONDS.
* ``POST /api/backtest`` also takes the later command-line settings under the
  config-file names: ``slippage``, ``position_size``, ``fill`` (``close`` or
  ``open``), ``stop_loss``, ``take_profit`` and ``trailing_stop``. They are
  checked with the command line's rules and passed to the same ``cli.analyse``.
  ``fill: "open"``, ``stop_loss``, ``take_profit`` or ``trailing_stop`` need
  candle data: a built-in sample then uses its sample candles, and a pasted CSV
  is read as a candle file. A request without these settings behaves exactly
  as before; when given, they are echoed in the reply's ``params`` in that
  order (``trailing_stop`` after ``take_profit``).
  It also takes ``risk_pct``, ``atr_mult`` and ``atr_period`` (the command's
  ``--risk-pct``, ``--atr-mult`` and ``--atr-period``), checked by the same
  ``cli.check_risk`` with the command's one-line messages: ``risk_pct`` above
  0 and at most 100, ``atr_mult`` above 0, ``atr_period`` a whole number of at
  least 1, and ``atr_mult`` or ``atr_period`` without ``risk_pct`` is a 400.
  ``risk_pct`` needs candle data like the exits. Like the other later
  settings they are echoed in ``params`` only when the request sent them,
  right after ``trailing_stop`` (``risk_pct``, ``atr_mult``, ``atr_period``;
  defaults are not echoed). With ``risk_pct`` the reply's ``summary`` also has
  ``risk_skipped_buys`` (buys risk sizing gave 0 shares) right after
  ``sells``, and ``report`` has the "Risk sizing:" line. A request without
  ``risk_pct`` gets exactly the old reply.
  It also takes ``atr_stop`` (JSON ``true`` or ``false``; the command's
  ``--atr-stop``): ``true`` turns the ATR stop on, ``false``, ``null``, ``""``
  or no key leave it off, and anything else is a 400 (``atr_stop must be true
  or false, got ...``). With it on, ``atr_mult`` and ``atr_period`` count
  without ``risk_pct`` (``cli.check_risk`` again, with the command's
  messages), and it needs candle data like the exits. It is echoed in
  ``params`` only when sent (``true`` or ``false``), right after
  ``atr_period``; with ``risk_pct`` or ``atr_stop`` on, ``summary`` has
  ``risk_skipped_buys`` right after ``sells``; trades then carry a
  ``reason`` (``atr`` for its sells). A request without ``atr_stop`` gets
  exactly the old reply.
  It also takes ``cooldown`` (the command's ``--cooldown N``), read like the
  other whole-number fields (``atr_period``): a JSON whole number or a string
  holding one; ``null``, ``""`` or no key leave it off; ``true``/``false``, a
  fraction or other text is a 400 (``cooldown must be a whole number...``).
  Then ``cli.check_cooldown`` with the command's messages: it needs
  ``stop_loss``, ``trailing_stop`` or ``atr_stop: true`` and must be at least
  1. It is echoed in ``params`` only when sent, right after ``atr_stop``; with
  it, ``summary`` has ``cooldown_bars`` and ``cooldown_skipped_buys`` (the
  ``--json`` keys) right after ``sells`` (or after ``risk_skipped_buys``), and
  ``report`` has the "Cooldown:" line. A request without ``cooldown`` gets
  exactly the old reply.
  It also takes ``max_hold`` (the command's ``--max-hold N``), read like
  ``cooldown``: a JSON whole number or a string holding one; ``null``, ``""``
  or no key leave it off; anything else is a 400 (``max_hold must be a whole
  number...``). Then ``cli.check_max_hold`` with the command's message: at
  least 1. It needs no stop and no candle data, so it works on a close-only
  CSV. It is echoed in ``params`` only when sent, right after ``cooldown``
  (or ``min_hold``); with it, ``summary`` has ``max_hold_bars`` and ``time_exits`` (the
  ``--json`` keys) right after ``sells`` (after ``risk_skipped_buys``, the
  cooldown keys and the min hold keys when those are there), trades carry a ``reason`` (``time``
  for its sells), the export columns end with ``reason``, and ``report`` has
  the "Max hold:" line. A request without ``max_hold`` gets exactly the old
  reply.
  It also takes ``min_hold`` (the command's ``--min-hold N``), read exactly
  like ``max_hold`` (``_as_int``): a JSON whole number (``4``, or ``4.0``,
  which reads as 4) or a string holding one (``"4"``, ``" 4 "``); ``null``,
  ``""`` or no key leave it off; ``true``/``false``, a fraction (``4.5``),
  other text (``"4.0"``, ``"abc"``), a list or an object is a 400 (``min_hold
  must be a whole number...``). Then ``cli.check_min_hold`` with the command's
  message: at least 1 (``0`` or below is a 400, ``--min-hold must be a whole
  number of at least 1, got 0``). It needs no stop and no candle data, so it
  works on a close-only CSV. It is echoed in ``params`` only when sent, right
  after ``cooldown``; with it, ``summary`` has ``min_hold_bars`` and
  ``min_hold_skipped_sells`` (the ``--json`` keys) right before the max-hold
  keys (or where they would be), and ``report`` has the "Min hold:" line. It
  makes no fill of its own, so trades get no ``reason`` and the export
  columns do not change because of it. A request without ``min_hold`` gets
  exactly the old reply.
  It also takes ``max_drawdown`` (the command's ``--max-drawdown PCT``), read
  like the other number fields (``stop_loss``): a JSON number or a string
  holding one; ``null``, ``""`` or no key leave it off; ``true``/``false``,
  other text, nan or infinity is a 400 (``max_drawdown must be a number...``).
  Then ``cli.check_max_drawdown`` with the command's message: above 0 and
  below 100. It needs no stop and no candle data, so it works on a close-only
  CSV. It is echoed in ``params`` only when sent, right after ``max_hold``;
  with it, ``summary`` has ``max_drawdown_limit_pct``, ``drawdown_halt_bar``
  (null when the halt never triggered) and ``drawdown_skipped_buys`` (the
  ``--json`` keys) right after ``sells`` (after the other optional keys when
  those are there), trades carry a ``reason`` (``drawdown`` for its sale),
  the export columns end with ``reason``, and ``report`` has the "Drawdown:"
  line. A request without ``max_drawdown`` gets exactly the old reply.
  It also takes ``breakeven`` (the command's ``--breakeven PCT``), read
  exactly like ``take_profit``: a JSON number or a string holding one;
  ``null``, ``""`` or no key leave it off; ``true``/``false``, other text, a
  list or an object is a 400 (``breakeven must be a number...``), and nan or
  infinity (``NaN``, ``Infinity``, ``"nan"``, ``"inf"``) a 400
  (``breakeven must be a finite number``), so, like the flag and the config
  key, it never takes infinity. Then the command's rule and message: above 0. It is a stop: it
  needs candle data and counts as a stop for ``cooldown``. It is echoed in
  ``params`` only when sent, right after ``max_drawdown``; with it,
  ``summary`` has ``breakeven_pct`` and ``breakeven_exits`` (the ``--json``
  keys) right after ``sells`` (after ``risk_skipped_buys``, before the
  cooldown keys), trades carry a ``reason`` (``breakeven`` for its sales),
  the export columns end with ``reason``, and ``report`` has the "Exits:"
  line. A request without ``breakeven`` gets exactly the old reply.
  It also takes ``max_losses`` (the command's ``--max-losses N``), read
  exactly like ``max_hold`` and ``min_hold`` (``_as_int``): a JSON whole
  number (``2``, or ``2.0``, which reads as 2) or a string holding one
  (``"2"``, ``" 2 "``); ``null``, ``""`` or no key leave it off;
  ``true``/``false``, a fraction (``2.5``), other text (``"2.0"``,
  ``"abc"``), a list or an object is a 400 (``max_losses must be a whole
  number...``). Then ``cli.check_max_losses`` with the command's message: at
  least 1 (``0`` or below is a 400, ``--max-losses must be a whole number of
  at least 1, got 0``). It needs no stop and no candle data, so it works on a
  close-only CSV. It is echoed in ``params`` only when sent, right after
  ``breakeven`` (or where it would be); with it, ``summary`` has
  ``max_losses``, ``loss_halt_bar`` (null when the halt never triggered) and
  ``loss_skipped_buys`` (the ``--json`` keys) right before ``round_trips``
  (after the drawdown keys when those are there), and ``report`` has the
  "Max losses:" line. It makes no fill of its own, so trades get no
  ``reason`` and the export columns do not change because of it. A request
  without ``max_losses`` gets exactly the old reply.
  It also takes ``scale_out`` (the command's ``--scale-out PCT``), read
  exactly like ``breakeven`` (``_as_float``): a JSON number (``5`` or
  ``5.0``) or a string holding one (``"5"``, ``" 5 "``; a thousands comma is
  dropped, as for every number field); ``null``, ``""`` or no key leave it
  off; ``true``/``false``, other text, a list or an object is a 400
  (``scale_out must be a number...``), and nan or infinity (``NaN``,
  ``Infinity``, ``"nan"``, ``"inf"``) a 400 (``scale_out must be a finite
  number``), so, like the flag and the config key, it never takes infinity.
  Then the command's rule and message: above 0 (``0`` or below is a 400,
  ``--scale-out must be above 0, got 0``). It needs candle data like the
  exits (a pasted close-only CSV is a 400 with the candle reader's message;
  a built-in sample uses its candles) but no other exit, and it is not a
  stop, so it does not count for ``cooldown``. It is echoed in ``params``
  only when sent, right after ``max_losses`` (or where it would be); with it,
  ``summary`` has ``scale_out_pct`` and ``scale_out_exits`` (the ``--json``
  keys) right after the breakeven keys (or where they would be, before the
  cooldown keys), trades carry a ``reason`` (``scale_out`` for its partial
  sales), the export columns end with ``reason``, and ``report`` has the
  "Scale out:" line. A request without ``scale_out`` gets exactly the old
  reply.
  It also takes ``add_on`` and ``max_adds`` (the command's ``--add-on PCT``
  and ``--max-adds N``). ``add_on`` is read exactly like ``scale_out``
  (``_as_float``): a JSON number (``10`` or ``10.0``) or a string holding one
  (``"10"``, ``" 10 "``; a thousands comma is dropped); ``null``, ``""`` or no
  key leave it off; ``true``/``false``, other text, a list or an object is a
  400 (``add_on must be a number...``), and nan or infinity (``NaN``,
  ``Infinity``, ``"nan"``, ``"inf"``) a 400 (``add_on must be a finite
  number``), so, like the flag and the config key, it never takes infinity.
  ``max_adds`` is read exactly like ``max_hold`` (``_as_int``): a JSON whole
  number (``2``, or ``2.0``) or a string holding one (``"2"``); ``null``,
  ``""`` or no key mean it was not sent; ``true``/``false``, a fraction
  (``2.5``), other text (``"2.5"``, ``"abc"``), a list or an object is a 400
  (``max_adds must be a whole number...``). Then ``cli.check_add_on`` with
  the command's messages: ``add_on`` above 0 (``0`` or below is a 400,
  ``--add-on must be above 0, got 0``), ``max_adds`` without ``add_on`` a 400
  (``--max-adds only makes sense together with --add-on``), and ``max_adds``
  at least 1 (``--max-adds must be a whole number of at least 1, got 0``).
  They need no candle data, so they work on a close-only CSV. When
  ``add_on`` is sent, ``params`` echoes both, right after ``scale_out`` (or
  where it would be): ``add_on`` and ``max_adds``, which is 1 when
  ``max_adds`` was not sent (or was ``null`` or ``""``). That is on purpose
  and unlike the other settings, whose defaults are never echoed (``atr_mult``
  and ``atr_period`` are echoed only when sent): with ``add_on`` the reply
  always says how many add-ons a position may take. With ``add_on``,
  ``summary`` has ``add_on_pct``, ``max_adds``, ``add_on_buys`` and
  ``add_on_skipped_buys`` (the ``--json`` keys) right after the scale-out
  keys (or where they would be, before the cooldown keys), trades carry a
  ``reason`` (``add_on`` for its buys), the export columns end with
  ``reason``, and ``report`` has the "Add-ons:" line. A request without
  ``add_on`` gets exactly the old reply; ``max_adds`` alone is a 400.
  It also takes ``trade_list`` (the command's ``--trade-list``), read exactly
  like ``atr_stop`` (``_as_bool``), another switch field here: JSON ``true``
  turns it on; ``false``, ``null``, ``""`` or no key leave it off; any string
  (``"true"`` and ``"yes"`` included), any number (``1`` and ``0``
  included), a list or an object is a 400 (``trade_list must be true or
  false, got ...``). It changes no setting of the run and needs no candle
  data, so it works on a close-only CSV. It is echoed in ``params`` only when
  sent (``true`` or ``false``), right after ``max_adds`` (or ``scale_out``, or
  where it would be). With ``true``, ``report`` ends with the command's trade list table
  (``backtest.format_trade_list``, line for line the command's) and the reply
  ends with ``trade_list``, the ``--json`` array (``cli.trade_list_data``):
  one object per row, with ``open``, ``entry_bar``, ``exit_bar``,
  ``bars_held``, ``shares``, ``outlay``, ``proceeds``, ``pnl``,
  ``return_pct`` and ``reason``. ``summary.round_trips`` and
  ``summary.winning_round_trips`` do not change. A request without
  ``trade_list`` gets exactly the old reply.
  It also takes ``explain`` (the command's ``--explain``), read exactly like
  ``atr_stop`` and ``trade_list`` (``_as_bool``): JSON ``true`` turns it on;
  ``false``, ``null``, ``""`` or no key leave it off; any string (``"true"``
  and ``"yes"`` included), any number (``1`` and ``0`` included), a list or
  an object is a 400 (``explain must be true or false, got ...``; just
  ``explain must be true or false`` for a list or an object). It changes no
  setting of the run and needs no candle data, so it works on a close-only
  CSV. It is echoed in ``params`` only when sent (``true`` or ``false``),
  right after ``trade_list`` (or where it would be). With ``true`` the reply
  has ``explanation`` right after ``report``: ``decision`` (the report's
  Signal line: BUY, SELL or HOLD, from ``signals.crossover_signal`` on
  ``short``/``long``, whatever ``strategy`` is), ``sentence`` (the command's
  ``--explain`` line, word for word), and ``last_bar`` and ``previous_bar``,
  each ``{"short": ..., "long": ...}`` with the unrounded SMAs (``null``
  where there is not enough history yet). With too few bars for a crossover
  (fewer than ``long`` + 1) the decision is HOLD and the sentence says how
  many bars are needed. ``report`` also gets the sentence as its own line
  right after the Signal line, so it is line for line the command's
  ``--backtest --explain`` output (without the disclaimer). There is no
  resample setting in the API, so it always explains the closes as sent. A
  request without ``explain`` gets exactly the old reply.
* ``POST /api/scan`` is the command line's ``--scan --json`` for files sent in
  the body: ``{"files": {"NAME.csv": "csv text", ...}}`` plus optional
  ``min_score``, ``top``, ``short``, ``long`` and ``rsi_period``, checked with
  the command line's rules. The files are only ever held in memory (the
  names are labels, never paths), scored with the same ``scan`` code, and the
  reply is exactly the ``--scan --json`` object. Errors are the usual
  ``{"ok": false, "error": ...}`` with the usual limits (body size, rows per
  file, window size, run time, concurrent runs).
* ``POST /api/walkforward`` is ``python -m trading_assistant.walkforward
  --json`` for one price series: ``short`` and ``long`` (comma lists like
  ``"5,10,20"`` or JSON lists of whole numbers), ``train``, ``test``, optional
  ``step``, ``cash``, ``fee`` and ``fee_pct``, and the prices as for
  ``/api/backtest`` (``source`` ``"sample"`` with ``sample``, or ``"csv"`` with
  ``csv``; closes only). Settings are checked with the command line's rules and
  run by the same ``walkforward.run_walk_forward``; the reply is exactly the
  ``--json`` object (``walkforward.json_data``). Errors are the usual
  ``{"ok": false, "error": ...}`` with the usual limits, plus
  MAX_WALKFORWARD_BAR_STEPS on the work one request may ask for.
  It also takes ``warmup`` (the command's ``--warmup``), read exactly like
  ``atr_stop`` and ``trade_list`` of ``/api/backtest`` (``_as_bool``): JSON
  ``true`` turns it on; ``false``, ``null``, ``""`` or no key leave it off;
  any string (``"true"`` and ``"yes"`` included), any number (``1`` and
  ``0`` included), a list or an object is a 400 (``warmup must be true or
  false, got ...``; just ``warmup must be true or false`` for a list or an
  object). It is read after ``short``, ``long``, ``train``, ``test``,
  ``step``, ``cash``, ``fee`` and ``fee_pct`` and before the range and pairing
  rules (``check_settings``, ``check_costs``) and the prices: one of those
  fields that cannot be read at all (``train: "x"``, ``short: "0"``) is
  reported first, a bad ``warmup`` before ``train: 0``, ``cash: -1``, no pair
  with short < long, or a bad ``source``, ``sample`` or ``csv``.
  With ``true`` the run is
  ``run_walk_forward(..., warmup=True)`` and the reply starts with
  ``"warmup": true``, before ``windows``, exactly as ``--warmup --json``
  prints it. With it off the reply is exactly the old one. The bar-step
  limit is unchanged: the warm-up bars only feed the signal and are not
  stepped through.
  It also takes ``strategy``, ``grid`` and ``params``, the command's
  ``--strategy``, ``--grid`` and ``--param``: ``strategy`` a name (missing,
  null or "" is none), ``grid`` and ``params`` lists of the command's option
  texts (``["window=10,20,30"]``, ``["threshold=0.5"]``; null, "" or [] is
  none). With any of them ``short`` and ``long`` are not required and are a
  400 when given, and the three are checked by the command's own
  ``walkforward.parse_strategy_options`` and ``sweep.grid_combinations`` with
  its messages (see ``parse_walkforward_request`` for the order). Window
  values are held to MAX_WINDOW, the parameter sets to
  MAX_WALKFORWARD_PARAMETER_SETS (counted before they are built), and the
  work to MAX_WALKFORWARD_BAR_STEPS, counted by ``_strategy_work`` with each
  strategy's weights (WALKFORWARD_BAR_WEIGHTS, WALKFORWARD_READ_WEIGHTS). The
  reply is the command's ``--json`` object (``"strategy"`` first, a
  ``params`` object in each window). Without the three (or with them null,
  "" or []) everything is exactly as before.
* ``POST /api/portfolio`` is ``python -m trading_assistant.portfolio FOLDER
  --json`` for files sent in the body: ``files`` exactly as for
  ``/api/scan`` (names are labels, never paths; nothing is read from disk)
  plus optional ``short``, ``long``, ``cash``, ``fee`` and ``fee_pct`` with the
  command's defaults and checks (``portfolio.check_settings``), and optional
  ``weights``, a list of ``"SYMBOL=PERCENT"`` strings exactly as for
  ``--weights`` (``portfolio.parse_weights``; a list, not an object, so a
  symbol given twice is seen and refused). The files are
  read, run and summarised by the command's own code (``portfolio.run_texts``)
  in file-name order, so the order of ``files`` does not matter, and the reply
  is exactly the ``--json`` object. Anything the command refuses with exit 1
  or 2 is a 400 with the command's one-line message (the folder is called
  "the request"); the usual limits apply (413, 415, 411, 429, 503). ``--csv``
  is command-line only.
  It also takes ``strategy`` and ``params``, the command's ``--strategy`` and
  ``--param``. ``strategy`` is read as for ``/api/backtest`` (missing, null or
  "" is ``sma_cross``; anything else that is not a known name is a 400
  ``unknown strategy ...``). ``params`` is null or a list of ``"KEY=VALUE"``
  strings (``[]`` is the same as null), checked by the command's own
  ``portfolio.check_strategy`` with its messages; ``short`` or ``long`` (when
  there and not null or "") with another strategy is a 400 with the
  command's message. Window parameters (``short``, ``long``, ``window``,
  ``period``) in ``params`` are held to ``MAX_WINDOW`` like ``short`` and
  ``long`` (``--param window must be at most 500, got 600``). With another
  strategy the reply is the command's ``--json`` object, ``title`` first;
  otherwise (no strategy, ``sma_cross``, null, "", no or empty ``params``)
  it is exactly the reply without them.
"""

import argparse
import errno
import io
import json
import logging
import math
import signal
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ..backtest import DEFAULT_CASH, FILLS, export_columns, export_rows, EXPORT_COLUMNS, format_trade_list, write_export
from ..cli import (
    DEFAULT_LONG,
    DEFAULT_RSI_PERIOD,
    DEFAULT_SHORT,
    DISCLAIMER,
    analyse,
    check_add_on,
    check_cooldown,
    check_costs,
    check_max_drawdown,
    check_max_hold,
    check_max_losses,
    check_min_hold,
    check_risk,
    check_scan_trim,
    check_windows,
    read_price_table,
    trade_list_data,
)
from ..scan import ScanError, ScanLimitError, scan_data, scan_texts
from ..signals import explain_crossover_data
from ..sweep import _int_list
from ..sweep import GridTooLarge, grid_combinations
from ..walkforward import (
    check_blocks,
    check_settings,
    json_data,
    parse_strategy_options,
    run_walk_forward,
    split_window,
)
from .. import portfolio as _portfolio
from ..data import read_candle_table
from ..strategies import STRATEGIES, first_signal_bars, resolve_params, strategy_names
from ..samples import SAMPLES, describe_samples, sample_candles, sample_table
from .assets import APP_JS, INDEX_HTML, STYLE_CSS

LOG = logging.getLogger("trading_assistant.web")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SEARCH_SPAN = 20  # how many ports above the default to try when it is busy

MAX_BODY_BYTES = 1_000_000  # ~1 MB of JSON, which is ~40,000 CSV rows
MAX_BARS = 10_000
MAX_WINDOW = 500
MAX_RUN_SECONDS = 10.0
MAX_CASH = 1e12
MAX_CONCURRENT_RUNS = 2
# POST /api/walkforward: windows * (pairs * train + test) bars backtested, at most.
# Around 60,000 bar-steps run per second, so this stays well inside MAX_RUN_SECONDS;
# a run that is abandoned on time-out cannot be stopped and would keep a CPU busy.
MAX_WALKFORWARD_BAR_STEPS = 300_000
# POST /api/walkforward with a strategy: the same limit, in the same bar-steps (one bar of an SMA crossover
# backtest, about 8 us where these were measured), each strategy's cost measured against that (_strategy_work).
# sma_cross and breakout read a window of closes on each bar: bar-steps per bar backtested, as
# (base, more per unit of the parameter, the parameter). Measured per bar: sma_cross about 7 us + 0.04 us per
# unit of long, breakout 3.5 us + 0.025 us per unit of window. (The SMA pairs without a strategy keep their
# own count: one bar-step per bar, whatever long is.)
WALKFORWARD_BAR_WEIGHTS = {"sma_cross": (1.0, 0.005, "long"), "breakout": (0.5, 0.004, "window")}
# The others work their indicator out again over every close so far on each bar: a backtest of n bars after w
# warm-up bars reads n * w + n * (n + 1) / 2 closes. zscore_reversion and hull_trend also do window-long sums
# for each close past their window. Weights: (bar-steps per close read, bar-steps per close read past the
# window, times the window), 10% to 30% above what was measured:
#   rsi_reversion 0.075-0.083 per read, ema_cross 0.021-0.026, momentum 0.016-0.018;
#   zscore_reversion 0.13 + 0.0185 per window-read, hull_trend 0.345 + 0.014 (least squares over windows 5-300).
WALKFORWARD_READ_WEIGHTS = {
    "rsi_reversion": (0.1, 0.0),
    "ema_cross": (0.03, 0.0),
    "momentum": (0.02, 0.0),
    "zscore_reversion": (0.17, 0.024),
    "hull_trend": (0.45, 0.018),
}
# Parameter sets one request may try (counted before they are built).
MAX_WALKFORWARD_PARAMETER_SETS = 10_000

LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}

SECURITY_HEADERS = [
    (
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; form-action 'none'; base-uri 'none'; "
        "frame-ancestors 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cache-Control", "no-store"),
]


class WebError(Exception):
    """A problem that is the client's fault; answered with ``status`` and a message."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- input parsing


def _as_int(payload, key, default):
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise WebError(400, f"{key} must be a whole number")
    if isinstance(value, float):
        if not value.is_integer():
            raise WebError(400, f"{key} must be a whole number, got {value:g}")
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise WebError(400, f"{key} must be a whole number, got {value.strip()!r}") from None
    raise WebError(400, f"{key} must be a whole number")


def _as_bool(payload, key, default):
    """JSON ``true`` or ``false`` under ``key``; missing, null and "" mean ``default``, anything else is a 400."""
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raise WebError(400, f"{key} must be true or false, got {value.strip()!r}")
    if isinstance(value, (int, float)):
        raise WebError(400, f"{key} must be true or false, got {value:g}")
    raise WebError(400, f"{key} must be true or false")


def _as_float(payload, key, default, finite=True):
    """The number under ``key``; ``finite=False`` lets nan and inf through for the caller's own check."""
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise WebError(400, f"{key} must be a number")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", ""))
        except ValueError:
            raise WebError(400, f"{key} must be a number, got {value.strip()!r}") from None
    else:
        raise WebError(400, f"{key} must be a number")
    if finite and not math.isfinite(number):
        raise WebError(400, f"{key} must be a finite number")
    return number


def _strategy_name(payload):
    """The request's ``strategy``: missing, null or "" is ``sma_cross``; anything but a known name is a 400.

    Shared by ``POST /api/backtest`` and ``POST /api/portfolio``. A value that
    is not a string is named by its type: ``true`` is ``'bool'``, ``5`` is
    ``'int'``, ``[]`` is ``'list'``, ``{}`` is ``'dict'``.
    """
    name = payload.get("strategy")
    if name is None or name == "":
        return "sma_cross"
    if not isinstance(name, str) or name not in STRATEGIES:
        shown = name if isinstance(name, str) else type(name).__name__
        raise WebError(400, f"unknown strategy {shown!r}; choose from: {', '.join(strategy_names())}")
    return name


def _parse_strategy(payload, short, long):
    """Return ``(strategy name, effective parameters)`` for the request.

    ``params`` is an optional object of numbers. For ``sma_cross`` the windows
    default to the top-level ``short``/``long``; a ``params`` value that
    contradicts an explicit top-level one is an error.
    """
    name = _strategy_name(payload)
    raw = payload.get("params")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise WebError(400, "params must be an object of numbers")
    overrides = {}
    for key, value in raw.items():
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                raise WebError(400, f"params.{key} must be a number, got {value.strip()!r}") from None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise WebError(400, f"params.{key} must be a finite number")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        overrides[key] = value
    if name == "sma_cross":
        for key, top in (("short", short), ("long", long)):
            if key in overrides and key in payload and overrides[key] != top:
                raise WebError(400, f"params.{key} ({overrides[key]}) contradicts {key} ({top}); give only one")
            overrides.setdefault(key, top)
    try:
        effective = resolve_params(name, overrides)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    for key, value in effective.items():
        if key in ("short", "long", "window", "period") and value > MAX_WINDOW:
            raise WebError(400, f"params.{key} must be at most {MAX_WINDOW}, got {value}")
    return name, effective


def parse_request(payload):
    """Validate the JSON body of ``POST /api/backtest``.

    Returns a dict with ``dates``, ``closes``, ``source_label`` and the
    numeric settings. Raises WebError with a one-line message otherwise.
    """
    if not isinstance(payload, dict):
        raise WebError(400, "request body must be a JSON object")

    short = _as_int(payload, "short", DEFAULT_SHORT)
    long = _as_int(payload, "long", DEFAULT_LONG)
    rsi_period = _as_int(payload, "rsi_period", DEFAULT_RSI_PERIOD)
    cash = _as_float(payload, "cash", DEFAULT_CASH)
    fee = _as_float(payload, "fee", 0.0)
    fee_pct = _as_float(payload, "fee_pct", 0.0)

    try:
        check_windows(short, long, rsi_period)
        check_costs(cash, fee, fee_pct)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    for name, value in (("--short", short), ("--long", long), ("--rsi-period", rsi_period)):
        if value > MAX_WINDOW:
            raise WebError(400, f"{name} must be at most {MAX_WINDOW}, got {value}")
    if cash > MAX_CASH:
        raise WebError(400, f"--cash must be at most {MAX_CASH:,.0f}")
    if fee > MAX_CASH:
        raise WebError(400, f"--fee must be at most {MAX_CASH:,.0f}")

    strategy, strategy_params = _parse_strategy(payload, short, long)
    extra = _parse_later_settings(payload)
    exits = (
        extra["stop_loss"] is not None or extra["take_profit"] is not None or extra["trailing_stop"] is not None
        or extra["atr_stop"] or extra.get("breakeven") is not None or extra.get("scale_out") is not None
    )
    risk = extra["risk_pct"] is not None  # risk sizing needs the highs and lows for the ATR
    needs_candles = extra["fill"] == "open" or exits or risk

    source = payload.get("source")
    if source is None:
        source = "csv" if payload.get("csv") else "sample"
    if source not in ("sample", "csv"):
        raise WebError(400, "source must be 'sample' or 'csv'")

    if source == "sample":
        name = payload.get("sample", "")
        if not isinstance(name, str) or name not in SAMPLES:
            shown = name if isinstance(name, str) else type(name).__name__
            raise WebError(400, f"unknown sample {shown!r}; choose one of: {', '.join(SAMPLES)}")
        if needs_candles:
            candles = sample_candles(name)
        else:
            dates, closes = sample_table(name)
        label = SAMPLES[name][0]
    else:
        text = payload.get("csv")
        if not isinstance(text, str) or not text.strip():
            raise WebError(400, "paste or upload a CSV with a 'close' column, or pick a sample")
        if len(text) > MAX_BODY_BYTES:
            raise WebError(413, f"CSV is too large ({len(text):,} characters; the limit is {MAX_BODY_BYTES:,})")
        if needs_candles:
            try:
                candles = read_candle_table(io.StringIO(text), "CSV")
            except ValueError as exc:  # e.g. no open/high/low/volume columns: the command line's message
                raise WebError(400, _one_line(str(exc))) from None
        else:
            try:
                dates, closes = read_price_table(io.StringIO(text), "CSV")
            except ValueError as exc:
                raise WebError(400, str(exc)) from None
        label = "Pasted / uploaded CSV"

    opens = highs = lows = None
    if needs_candles:  # the same columns the command line takes from a candle file
        dates = [c.date for c in candles]
        closes = [c.close for c in candles]
        opens = [c.open for c in candles]
        if exits or risk:
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]

    if not closes:
        raise WebError(400, "No price rows found.")
    if len(closes) > MAX_BARS:
        raise WebError(413, f"too many price rows ({len(closes):,}); the limit is {MAX_BARS:,}")

    return {
        "dates": dates,
        "closes": closes,
        "source_label": label,
        "short": short,
        "long": long,
        "rsi_period": rsi_period,
        "cash": cash,
        "fee": fee,
        "fee_pct": fee_pct,
        "strategy": strategy,
        "strategy_params": strategy_params,
        **extra,
        "opens": opens,
        "highs": highs,
        "lows": lows,
    }


def parse_scan_request(payload):
    """Validate the JSON body of ``POST /api/scan``.

    Returns ``{"files", "short", "long", "rsi_period", "min_score", "top"}``.
    Raises WebError with a one-line message otherwise. Nothing is read from
    disk: ``files`` maps names to CSV text.
    """
    if not isinstance(payload, dict):
        raise WebError(400, "request body must be a JSON object")
    short = _as_int(payload, "short", DEFAULT_SHORT)
    long = _as_int(payload, "long", DEFAULT_LONG)
    rsi_period = _as_int(payload, "rsi_period", DEFAULT_RSI_PERIOD)
    min_score = _as_int(payload, "min_score", None)
    top = _as_int(payload, "top", None)
    try:
        check_windows(short, long, rsi_period)
        check_scan_trim(min_score, top)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    for name, value in (("--short", short), ("--long", long), ("--rsi-period", rsi_period)):
        if value > MAX_WINDOW:
            raise WebError(400, f"{name} must be at most {MAX_WINDOW}, got {value}")

    files = _parse_files(payload)
    return {
        "files": files,
        "short": short,
        "long": long,
        "rsi_period": rsi_period,
        "min_score": min_score,
        "top": top,
    }


def _parse_files(payload):
    """The ``files`` object of ``/api/scan`` and ``/api/portfolio``: file name to CSV text, no folder parts."""
    files = payload.get("files")
    if files is None or files == {}:
        raise WebError(400, "no files: send at least one .csv file in files")
    if not isinstance(files, dict):
        raise WebError(400, "files must be an object of file name to CSV text")
    for name, text in files.items():
        if "/" in name or "\\" in name:
            raise WebError(400, f"file name {name!r} must not contain a folder part")
        if not isinstance(text, str):
            raise WebError(400, f"files[{name!r}] must be CSV text")
        if len(text) > MAX_BODY_BYTES:
            raise WebError(413, f"{name} is too large ({len(text):,} characters; the limit is {MAX_BODY_BYTES:,})")
    return files


def parse_portfolio_request(payload):
    """Validate the JSON body of ``POST /api/portfolio``.

    Returns ``{"files", "short", "long", "cash", "fee", "fee_pct", "weights",
    "strategy", "strategy_params"}``, with the command's defaults (``weights``
    None for an equal split, ``strategy`` ``"sma_cross"``, ``strategy_params``
    None without ``params``). The settings are checked by the command's own
    ``portfolio.check_strategy_windows``, ``portfolio.check_settings`` and
    ``portfolio.check_strategy`` (same order, same messages), then against the
    web page's usual window and cash limits. Raises WebError otherwise.

    ``strategy`` is read as ``POST /api/backtest`` reads it (``_strategy_name``).
    ``params`` is null or a list of ``"KEY=VALUE"`` strings, the command's
    ``--param`` texts (a list, not an object, as for ``weights``); ``[]`` is
    the same as null. ``short`` or ``long`` counts as given (for the
    ``sma_cross``-only rule and the contradiction check) when it is there and
    not null or "", the values that mean "the default".
    """
    if not isinstance(payload, dict):
        raise WebError(400, "request body must be a JSON object")
    short = _as_int(payload, "short", _portfolio.DEFAULT_SHORT)
    long = _as_int(payload, "long", _portfolio.DEFAULT_LONG)
    cash = _as_float(payload, "cash", DEFAULT_CASH, finite=False)
    fee = _as_float(payload, "fee", 0.0, finite=False)
    fee_pct = _as_float(payload, "fee_pct", 0.0, finite=False)
    strategy = _strategy_name(payload)
    items = payload.get("params")
    if items is not None and (not isinstance(items, list) or not all(isinstance(item, str) for item in items)):
        raise WebError(400, 'params must be a list of "KEY=VALUE" strings, like ["window=10"]')
    short_given = payload.get("short") not in (None, "")
    long_given = payload.get("long") not in (None, "")
    try:
        _portfolio.check_strategy_windows(strategy, short_given, long_given)
        _portfolio.check_settings(short, long, cash, fee, fee_pct)
        overrides = _portfolio.check_strategy(strategy, items, short, long, short_given, long_given)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    for name, value in (("--short", short), ("--long", long)):
        if value > MAX_WINDOW:
            raise WebError(400, f"{name} must be at most {MAX_WINDOW}, got {value}")
    for key, value in overrides.items():
        if key in ("short", "long", "window", "period") and value > MAX_WINDOW:
            raise WebError(400, f"--param {key} must be at most {MAX_WINDOW}, got {value}")
    if cash > MAX_CASH:
        raise WebError(400, f"--cash must be at most {MAX_CASH:,.0f}")
    if fee > MAX_CASH:
        raise WebError(400, f"--fee must be at most {MAX_CASH:,.0f}")
    weights = payload.get("weights")
    if weights is not None:
        if not isinstance(weights, list) or not all(isinstance(item, str) for item in weights):
            raise WebError(400, 'weights must be a list of "SYMBOL=PERCENT" strings, like ["A=60", "B=40"]')
        try:
            weights = _portfolio.parse_weights(weights)
        except ValueError as exc:
            raise WebError(400, str(exc)) from None
    return {
        "files": _parse_files(payload),
        "short": short,
        "long": long,
        "cash": cash,
        "fee": fee,
        "fee_pct": fee_pct,
        "weights": weights,
        "strategy": strategy,
        "strategy_params": overrides or None,
    }


def build_portfolio_response(params):
    """Run the portfolio on the files of validated ``params``; the reply is the command's ``--json`` object."""
    try:
        return _portfolio.run_texts(
            params["files"],
            short=params["short"],
            long=params["long"],
            cash=params["cash"],
            fee=params["fee"],
            fee_pct=params["fee_pct"],
            max_bars=MAX_BARS,
            weights=params["weights"],
            strategy=params["strategy"],
            strategy_params=params["strategy_params"],
        )
    except ScanLimitError as exc:
        raise WebError(413, str(exc)) from None
    except (ScanError, _portfolio.WeightsError, _portfolio.PortfolioError) as exc:
        raise WebError(400, str(exc)) from None


def build_scan_response(params):
    """Score the files of validated ``params``; the reply is the ``--scan --json`` object."""
    try:
        result = scan_texts(
            params["files"],
            short=params["short"],
            long=params["long"],
            rsi_period=params["rsi_period"],
            max_bars=MAX_BARS,
        )
    except ScanLimitError as exc:
        raise WebError(413, str(exc)) from None
    except ScanError as exc:
        raise WebError(400, str(exc)) from None
    return scan_data(result, min_score=params["min_score"], top=params["top"])


def _as_window_list(payload, key):
    """``short``/``long`` of ``POST /api/walkforward``: a comma list or a JSON list of whole numbers.

    Required, as on the command line; checked by the command line's own parser
    (``sweep._int_list``), so bad values get its message.
    """
    value = payload.get(key)
    if value is None or value == "" or value == []:
        raise WebError(400, f"the following arguments are required: --{key}")
    if isinstance(value, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        text = ",".join(str(v) for v in value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise WebError(400, f"{key} must be a comma list of positive integers like 5,10,20")
    try:
        values = _int_list(text)
    except argparse.ArgumentTypeError as exc:
        raise WebError(400, f"argument --{key}: {exc}") from None  # as argparse words it on the command line
    for v in values:
        if v > MAX_WINDOW:
            raise WebError(400, f"--{key} must be at most {MAX_WINDOW}, got {v}")
    return values


def _required_int(payload, key):
    value = _as_int(payload, key, None)
    if value is None:
        raise WebError(400, f"the following arguments are required: --{key}")
    return value


def _walkforward_strategy(payload):
    """``strategy`` of ``POST /api/walkforward``: missing, null or "" is none (the SMA crossover pairs, as before).

    Anything else must be a strategy name; otherwise it is the command's own
    message for ``--strategy`` (argparse's, with the value as Python shows it).
    """
    name = payload.get("strategy")
    if name is None or name == "":
        return None
    if not isinstance(name, str) or name not in STRATEGIES:
        choices = ", ".join(repr(n) for n in strategy_names())
        raise WebError(400, f"argument --strategy: invalid choice: {name!r} (choose from {choices})")
    return name


def _walkforward_items(payload, key, shape, example):
    """``grid`` or ``params``: null, "" or [] is none; otherwise a list of the command's option texts."""
    items = payload.get(key)
    if items is None or items == "" or items == []:
        return None
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise WebError(400, f'{key} must be a list of "{shape}" strings, like ["{example}"]')
    return items


def _strategy_work(strategy, combos, windows, train, test, warmup):
    """Bar-steps (see MAX_WALKFORWARD_BAR_STEPS) one walk-forward of ``strategy`` over ``combos`` asks for.

    Each window backtests every combination on ``train`` bars and one on
    ``test`` bars (counted as the dearest, with its full warm-up when
    ``warmup``, so near the start of the data it is a little more than the run).
    """
    def cost(params, n, warm):
        if strategy in WALKFORWARD_BAR_WEIGHTS:
            base, slope, key = WALKFORWARD_BAR_WEIGHTS[strategy]
            return n * (base + slope * params[key])
        per_read, per_window_read = WALKFORWARD_READ_WEIGHTS[strategy]
        reads = n * warm + n * (n + 1) / 2  # bar t (from 0) reads warm + t + 1 closes
        window = params.get("window", 0)
        past = 0  # closes past the window, summed over the bars: warm + t + 1 - window + 1 where positive
        first, last = max(warm + 1, window), warm + n
        if window and first <= last:
            a, b = first - window + 1, last - window + 1
            past = (a + b) * (b - a + 1) / 2
        return reads * per_read + past * window * per_window_read

    train_work = sum(cost(p, train, 0) for p in combos)
    test_work = max(cost(p, test, first_signal_bars(strategy, p) - 1 if warmup else 0) for p in combos)
    return math.ceil(windows * (train_work + test_work))


def parse_walkforward_request(payload):
    """Validate the JSON body of ``POST /api/walkforward``.

    Returns ``{"closes", "short", "long", "train", "test", "step", "cash",
    "fee", "fee_pct", "warmup", "strategy", "grid", "params"}``. Raises
    WebError with a one-line message otherwise.

    Without ``strategy``, ``grid`` and ``params`` (each missing, null or "";
    ``[]`` too for the two lists) everything is read and checked exactly as
    before they existed, and ``strategy`` is None. With any of them, ``short``
    and ``long`` are not required and are refused when given (not null, ""
    or []), and the three are checked by the command's own
    ``walkforward.parse_strategy_options`` and ``sweep.grid_combinations``,
    with its messages, after the fields that cannot be read at all and before
    the block, cost and price checks. Then window values (``short``,
    ``long``, ``window``, ``period``) are held to MAX_WINDOW, the parameter
    sets to MAX_WALKFORWARD_PARAMETER_SETS and the work to
    MAX_WALKFORWARD_BAR_STEPS (``_strategy_work``).
    """
    if not isinstance(payload, dict):
        raise WebError(400, "request body must be a JSON object")
    strategy = _walkforward_strategy(payload)
    grid_items = _walkforward_items(payload, "grid", "KEY=LIST", "window=10,20,30")
    param_items = _walkforward_items(payload, "params", "KEY=VALUE", "threshold=0.5")
    with_strategy = strategy is not None or grid_items is not None or param_items is not None
    if with_strategy:
        shorts = longs = None
        short_given = payload.get("short") not in (None, "", [])
        long_given = payload.get("long") not in (None, "", [])
    else:
        shorts = _as_window_list(payload, "short")
        longs = _as_window_list(payload, "long")
    train = _required_int(payload, "train")
    test = _required_int(payload, "test")
    step = _as_int(payload, "step", None)
    cash = _as_float(payload, "cash", DEFAULT_CASH)
    fee = _as_float(payload, "fee", 0.0)
    fee_pct = _as_float(payload, "fee_pct", 0.0)
    # Read exactly like atr_stop and trade_list: true, or false/null/""/no key; anything else is a 400.
    warmup = _as_bool(payload, "warmup", False)
    grid = params = combos = None
    try:
        if with_strategy:  # the command's order: its strategy checks, then the blocks
            grid, params = parse_strategy_options(strategy, grid_items, param_items, short_given, long_given)
            try:
                combos = grid_combinations(strategy, grid, params, max_combinations=MAX_WALKFORWARD_PARAMETER_SETS)
            except GridTooLarge as exc:
                raise WebError(
                    413,
                    f"this walk-forward is too big for the web page ({exc.count:,} parameter sets; the limit is"
                    f" {exc.limit:,}); use shorter --grid lists, or run python -m trading_assistant.walkforward",
                ) from None
            check_blocks(train, test, step)
        else:
            check_settings(shorts, longs, train, test, step)  # same order and messages as the command line
        check_costs(cash, fee, fee_pct)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    for option, values in (("--grid", grid or {}), ("--param", {k: [v] for k, v in (params or {}).items()})):
        for key, listed in values.items():
            for value in listed:
                if key in ("short", "long", "window", "period") and value > MAX_WINDOW:
                    raise WebError(400, f"{option} {key} must be at most {MAX_WINDOW}, got {value}")
    if cash > MAX_CASH:
        raise WebError(400, f"--cash must be at most {MAX_CASH:,.0f}")
    if fee > MAX_CASH:
        raise WebError(400, f"--fee must be at most {MAX_CASH:,.0f}")

    source = payload.get("source")
    if source is None:
        source = "csv" if payload.get("csv") else "sample"
    if source not in ("sample", "csv"):
        raise WebError(400, "source must be 'sample' or 'csv'")
    if source == "sample":
        name = payload.get("sample", "")
        if not isinstance(name, str) or name not in SAMPLES:
            shown = name if isinstance(name, str) else type(name).__name__
            raise WebError(400, f"unknown sample {shown!r}; choose one of: {', '.join(SAMPLES)}")
        _, closes = sample_table(name)
    else:
        text = payload.get("csv")
        if not isinstance(text, str) or not text.strip():
            raise WebError(400, "paste or upload a CSV with a 'close' column, or pick a sample")
        if len(text) > MAX_BODY_BYTES:
            raise WebError(413, f"CSV is too large ({len(text):,} characters; the limit is {MAX_BODY_BYTES:,})")
        try:
            _, closes = read_price_table(io.StringIO(text), "CSV")
        except ValueError as exc:
            raise WebError(400, str(exc)) from None
    if not closes:
        raise WebError(400, "No price rows found.")
    if len(closes) > MAX_BARS:
        raise WebError(413, f"too many price rows ({len(closes):,}); the limit is {MAX_BARS:,}")

    windows = len(split_window(len(closes), train, test, step))
    if with_strategy:
        work = _strategy_work(strategy, combos, windows, train, test, warmup)
        if work > MAX_WALKFORWARD_BAR_STEPS:
            raise WebError(
                413,
                f"this walk-forward is too big for the web page ({windows:,} windows x {len(combos):,} {strategy}"
                f" parameter sets, {work:,} bar-steps; the limit is {MAX_WALKFORWARD_BAR_STEPS:,}); use fewer"
                " parameter sets, a larger step or shorter blocks, or run python -m trading_assistant.walkforward",
            )
    else:
        pairs = sum(1 for s in set(shorts) for l in set(longs) if s < l)
        work = windows * (pairs * train + test)
        if work > MAX_WALKFORWARD_BAR_STEPS:
            raise WebError(
                413,
                f"this walk-forward is too big for the web page ({windows:,} windows x {pairs} pairs,"
                f" {work:,} bar-steps; the limit is {MAX_WALKFORWARD_BAR_STEPS:,}); use fewer pairs, a larger"
                " step or shorter blocks, or run python -m trading_assistant.walkforward",
            )
    return {
        "closes": closes,
        "short": shorts,
        "long": longs,
        "train": train,
        "test": test,
        "step": step,
        "cash": cash,
        "fee": fee,
        "fee_pct": fee_pct,
        "warmup": warmup,
        "strategy": strategy,
        "grid": grid,
        "params": params,
    }


def build_walkforward_response(params):
    """Run the walk-forward for validated ``params``; the reply is the ``--json`` object.

    With ``params["warmup"]`` on, the run warms up and the reply starts with ``"warmup": true``
    (``json_data``'s own placement, as ``--warmup --json``); off, it is exactly the old reply.
    """
    warmup = params.get("warmup", False)
    strategy = params.get("strategy")
    extra = {} if strategy is None else {"strategy": strategy, "grid": params["grid"], "params": params["params"]}
    rows, summary = run_walk_forward(
        params["closes"],
        params["short"],
        params["long"],
        params["train"],
        params["test"],
        step=params["step"],
        cash=params["cash"],
        fee=params["fee"],
        fee_pct=params["fee_pct"],
        warmup=warmup,
        **extra,
    )
    return json_data(rows, summary, warmup=warmup, strategy=strategy)


LATER_SETTINGS = (
    "slippage", "position_size", "fill", "stop_loss", "take_profit", "trailing_stop", "risk_pct", "atr_mult", "atr_period",
    "atr_stop", "cooldown", "min_hold", "max_hold", "max_drawdown", "breakeven", "max_losses", "scale_out",
    "add_on", "max_adds", "trade_list", "explain",
)


def _given(payload, key):
    """True when the request sets ``key`` (missing, null and "" mean "use the default", as for the other fields)."""
    return payload.get(key) not in (None, "")


def _one_line(message):
    """The message with any line breaks turned into spaces (the candle reader's are single lines already)."""
    return " ".join(message.splitlines())


def _parse_later_settings(payload):
    """Slippage, position size, fill, stop loss, take profit, trailing stop, risk sizing, the ATR stop, the
    cooldown, the minimum and maximum holding times, the drawdown halt, the breakeven stop, the losing-streak
    halt, the scale-out and the add-ons, checked by the command line's rules, plus the trade_list and explain
    switches.

    Returns their values (defaults where not given) plus ``given``, the names
    the request actually set, in a fixed order (``LATER_SETTINGS``).
    """
    slippage = _as_float(payload, "slippage", 0.0)
    position_size = _as_float(payload, "position_size", None)
    stop_loss = _as_float(payload, "stop_loss", None)
    take_profit = _as_float(payload, "take_profit", None)
    trailing_stop = _as_float(payload, "trailing_stop", None)
    risk_pct = _as_float(payload, "risk_pct", None)
    atr_mult = _as_float(payload, "atr_mult", None)
    atr_period = _as_int(payload, "atr_period", None)
    atr_stop = _as_bool(payload, "atr_stop", False)
    cooldown = _as_int(payload, "cooldown", None)
    min_hold = _as_int(payload, "min_hold", None)  # read exactly like max_hold; needs no stop and no candle data
    max_hold = _as_int(payload, "max_hold", None)  # read like cooldown; needs no stop and no candle data
    # Read like the other number fields (stop_loss, trailing_stop); needs no stop and no candle data.
    max_drawdown = _as_float(payload, "max_drawdown", None)
    # Read like take_profit: a JSON number or a string holding one; null, "" or no key leave it off;
    # true/false, other text, nan or infinity is a 400. A stop: it needs candle data and counts for cooldown.
    breakeven = _as_float(payload, "breakeven", None)
    max_losses = _as_int(payload, "max_losses", None)  # read exactly like max_hold and min_hold; no candle data
    # Read exactly like breakeven: a JSON number or a string holding one; null, "" or no key leave it off;
    # true/false, other text, nan or infinity is a 400. It needs candle data but is not a stop (no cooldown).
    scale_out = _as_float(payload, "scale_out", None)
    # Read exactly like scale_out (_as_float): a JSON number or a string holding one; null, "" or no key leave it
    # off; true/false, other text, a list or an object, nan or infinity is a 400. Needs no candle data.
    add_on = _as_float(payload, "add_on", None)
    # Read exactly like max_hold (_as_int). null, "" or no key mean "not sent": 1 with add_on, nothing without it.
    max_adds = _as_int(payload, "max_adds", None)
    # Read exactly like atr_stop (and explain below), the other switches: true, or false/null/""/no key; anything
    # else is a 400. It only adds the trade list to the reply: no setting of the run, no candle data.
    trade_list = _as_bool(payload, "trade_list", False)
    # Read exactly like atr_stop and trade_list. Like trade_list it changes no setting of the run and needs no
    # candle data: it only adds the sentence to the report (right after its Signal line) and the explanation
    # object to the reply.
    explain = _as_bool(payload, "explain", False)
    fill = payload.get("fill")
    if fill is None or fill == "":
        fill = "close"
    if not isinstance(fill, str) or fill not in FILLS:
        shown = fill if isinstance(fill, str) else type(fill).__name__
        raise WebError(400, f"fill must be 'close' or 'open', got {shown!r}")
    try:
        check_costs(slippage=slippage, position_size=position_size)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    # Same rules and messages as cli.validate_args.
    if stop_loss is not None and not 0 < stop_loss < 100:
        raise WebError(400, f"--stop-loss must be between 0 and 100 (both exclusive), got {stop_loss:g}")
    if take_profit is not None and not take_profit > 0:
        raise WebError(400, f"--take-profit must be positive, got {take_profit:g}")
    if trailing_stop is not None and not 0 < trailing_stop < 100:
        raise WebError(400, f"--trailing-stop must be between 0 and 100 (both exclusive), got {trailing_stop:g}")
    if breakeven is not None and not breakeven > 0:
        raise WebError(400, f"--breakeven must be above 0, got {breakeven:g}")
    if scale_out is not None and not scale_out > 0:
        raise WebError(400, f"--scale-out must be above 0, got {scale_out:g}")
    try:
        # The command line's own check and messages. atr_stop is passed only when it is on, so a
        # request without it makes exactly the call it always made.
        check_risk(risk_pct, atr_mult, atr_period, *((True,) if atr_stop else ()))
        # The command line's own check and messages: it needs a stop, then a whole number of at least 1.
        check_cooldown(
            cooldown, stop_loss is not None or trailing_stop is not None or atr_stop or breakeven is not None
        )
        # The command line's own checks and messages: a whole number of at least 1.
        check_min_hold(min_hold)
        check_max_hold(max_hold)
        # The command line's own check and message: above 0 and below 100.
        check_max_drawdown(max_drawdown)
        # The command line's own check and message: a whole number of at least 1.
        check_max_losses(max_losses)
        # The command line's own check and messages: add_on above 0; max_adds needs add_on, then at least 1.
        check_add_on(add_on, max_adds)
    except ValueError as exc:
        raise WebError(400, str(exc)) from None
    return {
        "slippage": slippage,
        "position_size": position_size,
        "fill": fill,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trailing_stop": trailing_stop,
        "risk_pct": risk_pct,
        "atr_mult": atr_mult,
        "atr_period": atr_period,
        "atr_stop": atr_stop,
        # Only when sent, so the settings of a request without it are exactly as before.
        **({"cooldown": cooldown} if cooldown is not None else {}),
        **({"min_hold": min_hold} if min_hold is not None else {}),
        **({"max_hold": max_hold} if max_hold is not None else {}),
        **({"max_drawdown": max_drawdown} if max_drawdown is not None else {}),
        **({"breakeven": breakeven} if breakeven is not None else {}),
        **({"max_losses": max_losses} if max_losses is not None else {}),
        **({"scale_out": scale_out} if scale_out is not None else {}),
        # Only when add_on is sent; max_adds then always has its value (1 when not sent), and params echoes both.
        **({"add_on": add_on, "max_adds": 1 if max_adds is None else max_adds} if add_on is not None else {}),
        "trade_list": trade_list,
        "explain": explain,
        "given": [
            key for key in LATER_SETTINGS
            if _given(payload, key) or (key == "max_adds" and add_on is not None)
        ],
    }


# --------------------------------------------------------------------------- running


def _run_with_timeout(func, timeout):
    """Run ``func()`` in a worker thread; raise WebError(503) if it exceeds ``timeout``."""
    box = {}

    def target():
        try:
            box["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
            box["error"] = exc

    worker = threading.Thread(target=target, name="backtest-run", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise WebError(
            503,
            f"the run took longer than {timeout:g} seconds and was abandoned; "
            "use fewer rows or shorter windows",
        )
    if "error" in box:
        raise box["error"]
    return box["value"]


def _money(value):
    return {"value": value, "text": f"{value:,.2f}"}


def _pct(value, signed=True):
    return {"value": value, "text": f"{value:+.2f}%" if signed else f"{value:.2f}%"}


def build_response(params):
    """Run the analysis for validated ``params`` and build the JSON-able reply."""
    # Only with explain: true. The SMA crossover on short/long over these closes: the report's Signal line.
    explanation = None
    if params.get("explain"):
        explanation = explain_crossover_data(params["closes"], short=params["short"], long=params["long"])
    lines, result = analyse(
        params["closes"],
        # The sentence goes into the report right after the Signal line, as --backtest --explain prints it.
        explanation=None if explanation is None else explanation["sentence"],
        short=params["short"],
        long=params["long"],
        rsi_period=params["rsi_period"],
        backtest=True,
        cash=params["cash"],
        fee=params["fee"],
        fee_pct=params["fee_pct"],
        strategy=params.get("strategy", "sma_cross"),
        strategy_params=params.get("strategy_params"),
        fill=params.get("fill", "close"),
        opens=params.get("opens"),
        slippage_pct=params.get("slippage", 0.0),
        position_size=params.get("position_size"),
        stop_pct=params.get("stop_loss"),
        take_profit_pct=params.get("take_profit"),
        highs=params.get("highs"),
        lows=params.get("lows"),
        trail_pct=params.get("trailing_stop"),
        risk_pct=params.get("risk_pct"),
        atr_mult=2.0 if params.get("atr_mult") is None else params["atr_mult"],
        atr_period=14 if params.get("atr_period") is None else params["atr_period"],
        atr_stop=params.get("atr_stop", False),
        cooldown=params.get("cooldown") or 0,
        max_hold=params.get("max_hold") or 0,
        max_drawdown_limit_pct=params.get("max_drawdown"),
        breakeven_pct=params.get("breakeven"),
        min_hold=params.get("min_hold") or 0,
        max_losses=params.get("max_losses") or 0,
        scale_out_pct=params.get("scale_out"),
        add_on_pct=params.get("add_on"),
        max_adds=params.get("max_adds"),
    )
    trade_list = params.get("trade_list", False)
    if trade_list:
        lines = lines + format_trade_list(result)  # the command's table, after the report as on the command line
    rows = export_rows(result, params["dates"])
    buf = io.StringIO()
    write_export(result, buf, params["dates"])
    bench = result.benchmark
    n_rt = result.n_round_trips
    wins = result.n_winning_round_trips

    trades = []
    for i, trade in enumerate(result.trades, start=1):
        trades.append(
            {
                "n": i,
                "bar": trade.bar,
                "date": params["dates"][trade.bar] if params["dates"] else "",
                "side": trade.side,
                "shares": trade.shares,
                "price": {"value": trade.price, "text": f"{trade.price:,.2f}"},
                "value": _money(trade.value),
                "cost": _money(trade.cost),
                "cash_after": _money(trade.cash_after),
                **({"reason": trade.reason} if result.has_exits else {}),
            }
        )

    return {
        "ok": True,
        "source": {"label": params["source_label"], "bars": len(params["closes"])},
        "params": {
            "short": params["short"],
            "long": params["long"],
            "rsi_period": params["rsi_period"],
            "cash": params["cash"],
            "fee": params["fee"],
            "fee_pct": params["fee_pct"],
            **{key: params[key] for key in params.get("given", ())},
        },
        "strategy": result.strategy,
        "strategy_params": dict(result.strategy_params),
        "stats": result.stats,
        "report": lines,
        # Only with explain: true, so replies without it stay exactly as before. It explains the report's Signal
        # line (the SMA crossover on short/long over these closes), so it sits right after the report.
        **({"explanation": explanation} if explanation is not None else {}),
        "disclaimer": DISCLAIMER,
        "summary": {
            "start_cash": _money(result.initial_cash),
            "end_equity": _money(result.final_equity),
            "return_pct": _pct(result.return_pct),
            "max_drawdown_pct": _pct(result.max_drawdown_pct, signed=False),
            "end_cash": _money(result.final_cash),
            "end_shares": result.final_position,
            "last_price": {"value": result.final_price, "text": f"{result.final_price:,.2f}"},
            "trades": result.n_trades,
            "buys": result.n_buys,
            "sells": result.n_sells,
            # Only with risk_pct or atr_stop, so replies without them stay exactly as before.
            **(
                {"risk_skipped_buys": result.risk_skipped_buys}
                if result.risk_pct is not None or result.atr_stop
                else {}
            ),
            # Only with breakeven, the same two keys as --json, so replies without it stay exactly as before.
            **(
                {"breakeven_pct": result.breakeven_pct, "breakeven_exits": result.n_breakeven_exits}
                if result.breakeven_pct is not None
                else {}
            ),
            # Only with scale_out, the same two keys as --json, so replies without it stay exactly as before.
            # After the breakeven keys, as in --json.
            **(
                {"scale_out_pct": result.scale_out_pct, "scale_out_exits": result.n_scale_out_exits}
                if result.scale_out_pct is not None
                else {}
            ),
            # Only with add_on, the same four keys as --json, so replies without it stay exactly as before.
            # After the scale-out keys and before the cooldown keys, as in --json and the report.
            **(
                {
                    "add_on_pct": result.add_on_pct,
                    "max_adds": result.max_adds,
                    "add_on_buys": result.n_add_on_buys,
                    "add_on_skipped_buys": result.add_on_skipped_buys,
                }
                if result.add_on_pct is not None
                else {}
            ),
            # Only with cooldown, the same two keys as --json, so replies without it stay exactly as before.
            **(
                {"cooldown_bars": result.cooldown, "cooldown_skipped_buys": result.cooldown_skipped_buys}
                if result.cooldown
                else {}
            ),
            # Only with min_hold, the same two keys as --json, so replies without it stay exactly as before.
            # Right before the max-hold keys, as in the report.
            **(
                {"min_hold_bars": result.min_hold, "min_hold_skipped_sells": result.min_hold_skipped_sells}
                if result.min_hold
                else {}
            ),
            # Only with max_hold, the same two keys as --json, so replies without it stay exactly as before.
            **(
                {"max_hold_bars": result.max_hold, "time_exits": result.n_time_exits}
                if result.max_hold
                else {}
            ),
            # Only with max_drawdown, the same three keys as --json, so replies without it stay exactly as before.
            **(
                {
                    "max_drawdown_limit_pct": result.max_drawdown_limit_pct,
                    "drawdown_halt_bar": result.drawdown_halt_bar,
                    "drawdown_skipped_buys": result.drawdown_skipped_buys,
                }
                if result.max_drawdown_limit_pct is not None
                else {}
            ),
            # Only with max_losses, the same three keys as --json, so replies without it stay exactly as before.
            **(
                {
                    "max_losses": result.max_losses,
                    "loss_halt_bar": result.loss_halt_bar,
                    "loss_skipped_buys": result.loss_skipped_buys,
                }
                if result.max_losses
                else {}
            ),
            "round_trips": n_rt,
            "winning_round_trips": wins,
            "win_rate_text": f"{wins}/{n_rt} made money ({wins / n_rt * 100:.0f}%)" if n_rt else "none completed",
            "costs_paid": _money(result.total_costs),
            "buy_hold": {
                "end_equity": _money(bench.final_equity),
                "return_pct": _pct(bench.return_pct),
                "max_drawdown_pct": _pct(bench.max_drawdown_pct, signed=False),
                "shares": bench.shares,
                "trades": bench.n_trades,
                "costs_paid": _money(bench.total_costs),
            },
        },
        "trades": trades,
        "columns": export_columns(result),  # EXPORT_COLUMNS, plus "reason" when exits are in use
        "rows": rows,
        "csv": buf.getvalue(),
        # Only with trade_list: true, so replies without it stay exactly as before. The --json array.
        **({"trade_list": trade_list_data(result)} if trade_list else {}),
    }


def _describe_strategies():
    return [
        {"name": name, "params": dict(defaults), "description": description}
        for name, (_, defaults, description) in STRATEGIES.items()
    ]


def dump_json(payload):
    """JSON text that is pure ASCII and never contains raw ``<``, ``>`` or ``&``.

    The page only ever inserts values as text, but escaping them here too means
    a reply can never be mistaken for markup, whatever reads it.
    """
    text = json.dumps(payload, ensure_ascii=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# --------------------------------------------------------------------------- HTTP handler


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingAssistant"
    sys_version = ""  # do not advertise the Python version
    protocol_version = "HTTP/1.1"

    # (method, path, monotonic start) of the request whose access-log line is
    # still owed; None when there is nothing to log (e.g. errors the base class
    # raises before _dispatch runs, which have never had an access-log line).
    _pending_log = None

    # ----- plumbing

    def log_message(self, fmt, *args):  # silence the default stderr logging
        LOG.debug("http: " + fmt, *args)

    def version_string(self):
        return self.server_version

    def _send(self, status, body, content_type, extra_headers=()):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra_headers:
            self.send_header(name, value)
        self._status = status
        # Everything above only filled the in-memory header buffer; end_headers()
        # is the first write to the socket. Log now, so the line is in the log
        # before the client can possibly have the response.
        self._log_request()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _log_request(self):
        """Write the access-log line for the current request, at most once."""
        pending, self._pending_log = self._pending_log, None
        if pending is None:
            return
        method, path, started = pending
        elapsed_ms = (time.monotonic() - started) * 1000
        LOG.info("%s %s %s %.0fms", method, path, self._status if self._status else "-", elapsed_ms)

    def _send_json(self, status, payload):
        self._send(status, dump_json(payload), "application/json; charset=utf-8")

    def _send_error_json(self, status, message):
        self._send_json(status, {"ok": False, "error": message})

    def send_error(self, code, message=None, explain=None):
        """Replace the HTML error page of the base class with JSON plus our headers."""
        try:
            text = message or HTTPStatus(code).phrase
        except ValueError:
            text = "error"
        self.close_connection = True
        try:
            self._send_error_json(code, text)
        except (OSError, ValueError):
            pass

    def _host_ok(self):
        allowed = getattr(self.server, "allowed_hosts", None)
        if allowed is None:  # bound to a non-loopback address: Host checking disabled
            return True
        host = self.headers.get("Host", "")
        try:
            hostname = urlsplit("//" + host).hostname
        except ValueError:
            return False
        return bool(hostname) and hostname.lower() in allowed

    def _dispatch(self, method):
        self._status = None
        started = time.monotonic()
        path = urlsplit(self.path).path
        self._pending_log = (method, path, started)
        try:
            if not self._host_ok():
                LOG.warning("rejected request with unexpected Host header %r", self.headers.get("Host"))
                raise WebError(400, "unexpected Host header")
            if method in ("GET", "HEAD"):
                self._route_get(path)
            elif method == "POST":
                self._route_post(path)
            else:
                raise WebError(405, f"method {method} not allowed")
        except WebError as exc:
            self._send_error_json(exc.status, exc.message)
        except (BrokenPipeError, ConnectionResetError):
            LOG.info("client went away during %s %s", method, path)
            return
        except Exception:  # noqa: BLE001 - last line of defence: log, never leak
            LOG.exception("unhandled error during %s %s", method, path)
            try:
                self._send_error_json(500, "internal error; see the server log")
            except (OSError, ValueError):
                pass
        finally:
            # Normally already logged by _send(); this covers requests that never
            # got a response (e.g. the client went away while we read the body).
            self._log_request()

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    # ----- routes

    def _route_get(self, path):
        if path == "/":
            self._send(200, INDEX_HTML, "text/html; charset=utf-8")
        elif path == "/style.css":
            self._send(200, STYLE_CSS, "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send(200, APP_JS, "text/javascript; charset=utf-8")
        elif path == "/api/samples":
            self._send_json(200, {"ok": True, "samples": describe_samples(), "strategies": _describe_strategies(), "limits": self._limits()})
        elif path == "/api/health":
            self._send_json(200, {"ok": True})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path == "/api/backtest":
            raise WebError(405, "use POST for /api/backtest")
        elif path == "/api/scan":
            raise WebError(405, "use POST for /api/scan")
        elif path == "/api/walkforward":
            raise WebError(405, "use POST for /api/walkforward")
        elif path == "/api/portfolio":
            raise WebError(405, "use POST for /api/portfolio")
        else:
            raise WebError(404, "not found")

    def _route_post(self, path):
        if path == "/api/scan":
            self._post_scan()
            return
        if path == "/api/walkforward":
            self._post_walkforward()
            return
        if path == "/api/portfolio":
            self._post_portfolio()
            return
        if path != "/api/backtest":
            raise WebError(404, "not found")
        payload = self._read_json_body()
        params = parse_request(payload)
        slot = self.server.run_slots
        if not slot.acquire(blocking=False):
            raise WebError(429, "the server is busy with other runs; try again in a moment")
        try:
            response = _run_with_timeout(lambda: build_response(params), self.server.max_run_seconds)
        except ValueError as exc:  # e.g. a non-positive price, same message as the CLI
            raise WebError(400, str(exc)) from None
        finally:
            slot.release()
        self._send_json(200, response)

    def _post_scan(self):
        params = parse_scan_request(self._read_json_body())
        slot = self.server.run_slots
        if not slot.acquire(blocking=False):
            raise WebError(429, "the server is busy with other runs; try again in a moment")
        try:
            response = _run_with_timeout(lambda: build_scan_response(params), self.server.max_run_seconds)
        finally:
            slot.release()
        self._send_json(200, response)

    def _post_walkforward(self):
        params = parse_walkforward_request(self._read_json_body())
        slot = self.server.run_slots
        if not slot.acquire(blocking=False):
            raise WebError(429, "the server is busy with other runs; try again in a moment")
        try:
            response = _run_with_timeout(lambda: build_walkforward_response(params), self.server.max_run_seconds)
        except ValueError as exc:  # e.g. a non-positive price or too few bars: the command line's message
            raise WebError(400, str(exc)) from None
        finally:
            slot.release()
        self._send_json(200, response)

    def _post_portfolio(self):
        params = parse_portfolio_request(self._read_json_body())
        slot = self.server.run_slots
        if not slot.acquire(blocking=False):
            raise WebError(429, "the server is busy with other runs; try again in a moment")
        try:
            response = _run_with_timeout(lambda: build_portfolio_response(params), self.server.max_run_seconds)
        finally:
            slot.release()
        self._send_json(200, response)

    def _read_json_body(self):
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";")[0].strip().lower() != "application/json":
            raise WebError(415, "Content-Type must be application/json")
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            raise WebError(411, "chunked requests are not supported; send Content-Length")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise WebError(411, "Content-Length header is required")
        try:
            length = int(raw_length)
        except ValueError:
            raise WebError(400, "invalid Content-Length header") from None
        if length < 0:
            raise WebError(400, "invalid Content-Length header")
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # we will not read the body
            raise WebError(413, f"request body is too large ({length:,} bytes; the limit is {MAX_BODY_BYTES:,})")
        body = self.rfile.read(length)
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise WebError(400, "request body must be UTF-8 text") from None
        try:
            return json.loads(text)
        except ValueError:
            raise WebError(400, "request body is not valid JSON") from None

    def _limits(self):
        return {
            "max_body_bytes": MAX_BODY_BYTES,
            "max_bars": MAX_BARS,
            "max_window": MAX_WINDOW,
            "max_run_seconds": self.server.max_run_seconds,
        }


# --------------------------------------------------------------------------- server


class BacktestServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler=Handler, max_run_seconds=MAX_RUN_SECONDS):
        super().__init__(address, handler)
        host = address[0]
        self.allowed_hosts = LOOPBACK_NAMES | {host.lower()} if _is_loopback(host) else None
        self.max_run_seconds = max_run_seconds
        self.run_slots = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

    @property
    def url(self):
        host, port = self.server_address[:2]
        shown = "localhost" if host in ("127.0.0.1", "::1", "0.0.0.0", "::") else host
        return f"http://{shown}:{port}/"


def _is_loopback(host):
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return socket.inet_aton(host)[0] == 127
    except OSError:
        return False


def create_server(host=DEFAULT_HOST, port=DEFAULT_PORT, explicit_port=False, max_run_seconds=MAX_RUN_SECONDS):
    """Bind a server, moving to the next free port if the default one is busy.

    With ``explicit_port=True`` a busy port is an error (OSError) instead.
    ``port=0`` lets the operating system choose.
    """
    candidates = [port] if explicit_port or port == 0 else list(range(port, port + PORT_SEARCH_SPAN + 1))
    last_error = None
    for candidate in candidates:
        try:
            server = BacktestServer((host, candidate), max_run_seconds=max_run_seconds)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            last_error = exc
            LOG.info("port %d is busy, trying the next one", candidate)
            continue
        if candidate != port:
            LOG.warning("port %d was busy; using port %d instead", port, candidate)
        return server
    raise last_error


def serve(server):
    """Run until Ctrl+C / SIGTERM, then close the socket cleanly."""
    stop_reason = {"signal": None}

    def handle_sigterm(signum, frame):
        stop_reason["signal"] = "SIGTERM"
        raise KeyboardInterrupt

    previous = {}
    if threading.current_thread() is threading.main_thread():
        previous[signal.SIGTERM] = signal.signal(signal.SIGTERM, handle_sigterm)
        # A parent shell may have left SIGINT ignored (background jobs); make sure Ctrl+C works.
        previous[signal.SIGINT] = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("stopping (%s)", stop_reason["signal"] or "Ctrl+C")
    finally:
        server.server_close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        LOG.info("stopped")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="trading_assistant.web",
        description="Serve the backtest page on your own machine.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="address to bind (default: %(default)s, loopback only)")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"port to listen on (default: {DEFAULT_PORT}, or the next free one above it; 0 = any free port)",
    )
    parser.add_argument("--verbose", action="store_true", help="log every request and debug details")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    explicit = args.port is not None
    port = args.port if explicit else DEFAULT_PORT
    if explicit and not 0 <= port <= 65535:
        print(f"Error: --port must be between 0 and 65535, got {port}", file=sys.stderr)
        return 2
    if not _is_loopback(args.host):
        LOG.warning("binding to %s exposes the page to your network; Host-header checking is disabled", args.host)
    try:
        server = create_server(args.host, port, explicit_port=explicit)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            if explicit:
                print(f"Error: port {port} is already in use; pick another with --port", file=sys.stderr)
            else:
                print(
                    f"Error: ports {port}-{port + PORT_SEARCH_SPAN} are all in use; pick one with --port",
                    file=sys.stderr,
                )
        elif exc.errno == errno.EACCES:
            print(f"Error: no permission to listen on port {port}; try a port above 1024", file=sys.stderr)
        else:
            print(f"Error: cannot start the server on {args.host}:{port}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    print(f"Trading assistant page: {server.url}  (press Ctrl+C to stop)", flush=True)
    print(DISCLAIMER, flush=True)
    serve(server)
    return 0
