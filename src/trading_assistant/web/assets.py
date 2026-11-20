"""The page, stylesheet and script served by ``trading_assistant.web``.

They live here as plain strings so the server never reads a file from disk
and nothing is fetched from the internet. The page has a backtest form, a
"Scan several files" panel (``POST /api/scan``) and a "Walk-forward test" panel
(``POST /api/walkforward``). The backtest form's "Trade list" box sends
``trade_list: true`` (only when ticked), and a reply with ``trade_list`` is
shown in the "Trade list" results panel, formatted exactly as the text report
formats it. Its "Explain signal" box sends ``explain: true`` (only when
ticked); the reply's text report then has the command's ``--explain``
sentence right under its Signal line, and the page shows that report as it
is, so the sentence is shown once and nothing else changes. The walk-forward panel's "Warm up" box sends ``warmup: true``
(only when ticked); a reply with ``"warmup": true`` gets the command's
``--warmup`` header line above the windows and its no-trades note wording.
The backtest form's "Add-on (%)" and "Max adds" fields send ``add_on`` and
``max_adds``, each only when filled in, and are never greyed out (they need
no candle data); a reply with the add-on keys adds "N add-on buys, M add-ons
skipped" to the Trades card.
The "Portfolio backtest" panel (``POST /api/portfolio``) has a "Strategy"
dropdown filled from the same ``/api/samples`` list as the backtest form's;
with ``sma_cross`` it sends exactly the request it sent before, and another
strategy hides "Short SMA" and "Long SMA" and sends ``strategy`` and
``params`` (the parameters filled in and different from their defaults)
instead. A reply with ``title`` shows it as the title line; otherwise the
panel builds that line itself (``pfTitle``).
The walk-forward panel has a "Strategy" dropdown filled from the same list:
with ``sma_cross`` it sends exactly the request it sent before; another
strategy hides the window lists and shows one text field per parameter,
holding its default: a comma list goes in ``grid``, another changed value in
``params``. A reply with ``strategy`` gets the Params column (``wfNum``
writes the numbers as the command's text does), that strategy's header line
and notes; any other reply is shown as before.
The script uses no libraries and
draws the charts itself as SVG. Everything it shows is inserted with
``textContent`` / ``createElement`` (never ``innerHTML``), so data from a CSV
or an error message can never be interpreted as markup.
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Trading Assistant - Backtest</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip-link" href="#results">Skip to results</a>
<header class="topbar">
  <h1>Trading Assistant <span class="muted">backtest</span></h1>
  <button type="button" id="theme-toggle" class="ghost" aria-pressed="false" title="Switch between light and dark">Dark mode</button>
</header>

<main>
<form id="form" class="panel" novalidate aria-labelledby="settings-heading">
  <h2 id="settings-heading">Settings</h2>
  <div class="grid">
    <div class="field span2">
      <label for="source">Price series</label>
      <select id="source" name="source"></select>
      <p class="hint" id="source-hint"></p>
    </div>

    <div class="field span2" id="csv-block" hidden>
      <label for="csv">CSV with a <code>close</code> column (optional <code>date</code> column)</label>
      <textarea id="csv" name="csv" rows="6" spellcheck="false" placeholder="date,close&#10;2026-01-02,101.5&#10;2026-01-05,102.1"></textarea>
      <div class="row">
        <label class="file-label" for="file">Upload a CSV file</label>
        <input type="file" id="file" accept=".csv,text/csv,text/plain">
        <span class="hint" id="csv-hint"></span>
      </div>
    </div>

    <div class="field span2">
      <label for="strategy">Strategy</label>
      <select id="strategy" name="strategy"></select>
      <p class="hint" id="strategy-hint"></p>
    </div>
    <div class="field span2" id="strategy-params-block" hidden>
      <div class="grid nested-grid" id="strategy-params"></div>
    </div>

    <div class="field">
      <label for="short">Short SMA</label>
      <input id="short" name="short" type="number" inputmode="numeric" min="1" step="1" value="20" required>
    </div>
    <div class="field">
      <label for="long">Long SMA</label>
      <input id="long" name="long" type="number" inputmode="numeric" min="2" step="1" value="50" required>
    </div>
    <div class="field">
      <label for="cash">Starting cash</label>
      <input id="cash" name="cash" type="number" inputmode="decimal" min="0" step="any" value="10000" required>
    </div>
    <div class="field">
      <label for="rsi">RSI period</label>
      <input id="rsi" name="rsi_period" type="number" inputmode="numeric" min="1" step="1" value="14" required>
    </div>
    <div class="field">
      <label for="fee">Fee per trade</label>
      <input id="fee" name="fee" type="number" inputmode="decimal" min="0" step="any" value="0">
    </div>
    <div class="field">
      <label for="fee_pct">Cost % of trade value</label>
      <input id="fee_pct" name="fee_pct" type="number" inputmode="decimal" min="0" max="99.99" step="any" value="0">
    </div>
    <div class="field">
      <label for="slippage">Slippage %</label>
      <input id="slippage" name="slippage" type="number" inputmode="decimal" min="0" max="99.99" step="any" value="0">
    </div>
    <div class="field">
      <label for="position_size">Position size (% of account)</label>
      <input id="position_size" name="position_size" type="number" inputmode="decimal" min="0" max="100" step="any" placeholder="All-in">
    </div>
    <div class="field">
      <label for="fill">Fill price</label>
      <select id="fill" name="fill">
        <option value="close">Next bar's close (default)</option>
        <option value="open">Next bar's open</option>
      </select>
    </div>
    <div class="field">
      <label for="stop_loss">Stop loss %</label>
      <input id="stop_loss" name="stop_loss" type="number" inputmode="decimal" min="0" max="99.99" step="any" placeholder="Optional">
    </div>
    <div class="field">
      <label for="take_profit">Take profit %</label>
      <input id="take_profit" name="take_profit" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
    </div>
    <div class="field">
      <label for="trailing_stop">Trailing stop %</label>
      <input id="trailing_stop" name="trailing_stop" type="number" inputmode="decimal" min="0" max="99.99" step="any" placeholder="Optional">
    </div>
    <div class="field">
      <label for="breakeven">Breakeven (%)</label>
      <input id="breakeven" name="breakeven" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
      <span class="hint" id="breakeven-hint">Once a later bar's high is this % above the entry price, sell at the entry price if the price falls back to it.</span>
    </div>
    <div class="field">
      <label for="scale_out">Scale out (%)</label>
      <input id="scale_out" name="scale_out" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
      <span class="hint" id="scale-out-hint">Once a later bar's high is this % above the entry price, sell half the shares held (rounded down), once per position; the rest stays open.</span>
    </div>
    <div class="field">
      <label for="risk_pct">Risk % per buy</label>
      <input id="risk_pct" name="risk_pct" type="number" inputmode="decimal" min="0" max="100" step="any" placeholder="Optional">
    </div>
    <div class="field">
      <label for="atr_mult">ATR multiplier</label>
      <input id="atr_mult" name="atr_mult" type="number" inputmode="decimal" min="0" step="any" placeholder="2 (default)">
    </div>
    <div class="field">
      <label for="atr_period">ATR period</label>
      <input id="atr_period" name="atr_period" type="number" inputmode="numeric" min="1" step="1" placeholder="14 (default)">
    </div>
    <div class="field">
      <label for="atr_stop">ATR stop</label>
      <div class="row">
        <input id="atr_stop" name="atr_stop" type="checkbox">
        <span class="hint" id="atr-stop-hint">Sell when the price falls ATR multiplier &times; ATR below the entry price. The two ATR fields apply to Risk % and to this.</span>
      </div>
    </div>
    <div class="field">
      <label for="trade_list">Trade list</label>
      <div class="row">
        <input id="trade_list" name="trade_list" type="checkbox">
        <span class="hint" id="trade-list-hint">Also show every round trip, and a position still held at the end, as a table (the command's --trade-list). Changes no trade. Works with a close-only CSV.</span>
      </div>
    </div>
    <div class="field">
      <label for="explain">Explain signal</label>
      <div class="row">
        <input id="explain" name="explain" type="checkbox">
        <span class="hint" id="explain-hint">Also say why the Signal line of the text report is BUY, SELL or HOLD: one sentence right under it, with the short and long SMA on the last bar and the bar before (the command's --explain). Changes no trade. Works with a close-only CSV.</span>
      </div>
    </div>
    <div class="field">
      <label for="cooldown">Cooldown (bars)</label>
      <input id="cooldown" name="cooldown" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="cooldown-hint">After a sell by the stop loss, trailing stop or ATR stop, no buy for this many bars. Needs one of them.</span>
    </div>
    <div class="field">
      <label for="max_losses">Max losses</label>
      <input id="max_losses" name="max_losses" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="max-losses-hint">After this many losing round trips in a row, buy nothing more; a round trip that did not lose resets the count. Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="min_hold">Min hold (bars)</label>
      <input id="min_hold" name="min_hold" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="min-hold-hint">Skip a signal sell until the position has been held this many bars since the buy that opened it; the other exits still sell. Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="max_hold">Max hold (bars)</label>
      <input id="max_hold" name="max_hold" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="max-hold-hint">Sell a position this many bars after the buy that opened it, at that bar's fill price. Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="max_drawdown">Max drawdown (%)</label>
      <input id="max_drawdown" name="max_drawdown" type="number" inputmode="decimal" min="0" max="99.99" step="any" placeholder="Optional">
      <span class="hint" id="max-drawdown-hint">When the account value at a close is this % or more below its peak, sell the position on the next bar and buy nothing more. Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="add_on">Add-on (%)</label>
      <input id="add_on" name="add_on" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
      <span class="hint" id="add-on-hint">While a position is held, buy more on the next bar after a close this % or more above the latest buy price, sized like any buy (with all-in sizing it usually gets 0 shares). Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="max_adds">Max adds</label>
      <input id="max_adds" name="max_adds" type="number" inputmode="numeric" min="1" step="1" placeholder="1 (default)">
      <span class="hint" id="max-adds-hint">The most add-on buys per position. Needs Add-on (%). Works with a close-only CSV.</span>
    </div>
    <div class="field span2">
      <p class="hint" id="candle-hint" hidden>Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need open/high/low columns (pasted as a candle CSV, or pick a built-in sample, which always has them). The scale-out needs them too.</p>
    </div>
  </div>
  <div class="actions">
    <button type="submit" id="run" class="primary">Run backtest</button>
    <span id="status" class="status" role="status" aria-live="polite"></span>
  </div>
  <div id="error" class="error" role="alert" hidden></div>
</form>

<section id="results" class="results" hidden aria-live="polite">
  <h2 id="results-heading">Results <span class="muted" id="results-source"></span></h2>

  <div class="cards" id="cards"></div>

  <div class="panel chart-panel">
    <h3>Price with buys and sells</h3>
    <p class="hint">Hover or focus the chart and use the arrow keys to step through the bars. Triangles mark fills: green up = buy, red down = sell.</p>
    <div class="chart" id="price-chart" tabindex="0" role="img" aria-label="Price chart with buy and sell markers"></div>
    <div class="legend" id="price-legend"></div>
  </div>

  <div class="panel chart-panel">
    <h3>Account value</h3>
    <p class="hint">Strategy equity (solid) against buy &amp; hold (dashed). Markers show where trades happened.</p>
    <div class="chart" id="equity-chart" tabindex="0" role="img" aria-label="Account value chart, strategy against buy and hold"></div>
    <div class="legend" id="equity-legend"></div>
  </div>

  <div class="panel">
    <h3>Risk and return</h3>
    <div class="table-wrap">
      <table id="stats-table">
        <thead><tr><th scope="col">Measure</th><th scope="col" class="num">Value</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div class="panel">
    <h3>Strategy against buy &amp; hold</h3>
    <div class="table-wrap">
      <table id="compare-table">
        <thead><tr><th scope="col"></th><th scope="col">Strategy</th><th scope="col">Buy &amp; hold</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div class="panel">
    <div class="row between">
      <h3>Trades <span class="muted" id="trade-count"></span></h3>
      <button type="button" id="download" class="ghost">Download results as CSV</button>
    </div>
    <div class="table-wrap">
      <table id="trades-table">
        <thead><tr>
          <th scope="col">#</th><th scope="col">Bar</th><th scope="col">Date</th><th scope="col">Side</th>
          <th scope="col" class="num">Shares</th><th scope="col" class="num">Price</th><th scope="col" class="num">Value</th>
          <th scope="col" class="num">Cost</th><th scope="col" class="num">Cash after</th><th scope="col">Reason</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="hint" id="no-trades" hidden>No trades were made: the signal never produced a fill that could be executed.</p>
  </div>

  <div class="panel" id="trade-list-panel" hidden>
    <h3>Trade list</h3>
    <p class="hint">One row per completed round trip (bar index is 0-based), as in the text report. The open row is a position still held at the end: unrealized, marked at the last close, no selling costs.</p>
    <div class="table-wrap">
      <table id="trade-list-table">
        <thead><tr>
          <th scope="col">#</th><th scope="col" class="num">Entry</th><th scope="col" class="num">Exit</th>
          <th scope="col" class="num">Bars</th><th scope="col" class="num">Shares</th><th scope="col" class="num">Outlay</th>
          <th scope="col" class="num">Proceeds</th><th scope="col" class="num">P/L</th><th scope="col" class="num">Return</th>
          <th scope="col">Reason</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="hint" id="trade-list-footer"></p>
  </div>

  <details class="panel">
    <summary>Text report (identical to the command line)</summary>
    <pre id="report"></pre>
  </details>
</section>

<section id="scan-panel" class="panel" aria-labelledby="scan-heading">
  <h2 id="scan-heading">Scan several files</h2>
  <p class="hint">Ranks each file by its combined score (crossover, RSI, MACD and Bollinger parts, each +1, 0 or -1), exactly like <code>--scan FOLDER --json</code> on the command line. The files are sent to this local server only and are never saved.</p>
  <form id="scan-form" novalidate aria-labelledby="scan-heading">
    <div class="grid">
      <div class="field span2">
        <label for="scan-files">CSV files (the file name without .csv is the symbol)</label>
        <input type="file" id="scan-files" multiple accept=".csv,text/csv">
        <p class="hint" id="scan-files-hint">Pick one or more files with a <code>close</code> column. Files that cannot be read are listed as skipped.</p>
      </div>
      <div class="field">
        <label for="scan-min-score">Minimum score</label>
        <input id="scan-min-score" name="min_score" type="number" inputmode="numeric" step="1" placeholder="Any">
      </div>
      <div class="field">
        <label for="scan-top">Rows to keep</label>
        <input id="scan-top" name="top" type="number" inputmode="numeric" min="1" step="1" placeholder="All">
      </div>
      <div class="field">
        <label for="scan-short">Short SMA</label>
        <input id="scan-short" name="short" type="number" inputmode="numeric" min="1" step="1" value="20">
      </div>
      <div class="field">
        <label for="scan-long">Long SMA</label>
        <input id="scan-long" name="long" type="number" inputmode="numeric" min="2" step="1" value="50">
      </div>
      <div class="field">
        <label for="scan-rsi">RSI period</label>
        <input id="scan-rsi" name="rsi_period" type="number" inputmode="numeric" min="1" step="1" value="14">
      </div>
    </div>
    <div class="actions">
      <button type="submit" id="scan-run" class="primary">Run scan</button>
      <span id="scan-status" class="status" role="status" aria-live="polite"></span>
    </div>
    <div id="scan-error" class="error" role="alert" hidden></div>
  </form>

  <div id="scan-results" class="scan-results" hidden aria-live="polite">
    <h3>Ranking <span class="muted" id="scan-summary"></span></h3>
    <div class="table-wrap">
      <table id="scan-table">
        <thead><tr>
          <th scope="col">Symbol</th><th scope="col" class="num">Bars</th><th scope="col" class="num">Score</th>
          <th scope="col" class="num">Crossover</th><th scope="col" class="num">RSI</th>
          <th scope="col" class="num">MACD</th><th scope="col" class="num">Bollinger</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="hint" id="scan-none" hidden></p>
    <h3>Skipped files <span class="muted" id="scan-skipped-count"></span></h3>
    <ul id="scan-skipped" class="scan-skipped"></ul>
    <p class="hint" id="scan-no-skipped" hidden>None.</p>
    <p class="scan-disclaimer" id="scan-disclaimer">Research aid only. Not financial advice.</p>
  </div>
</section>

<section id="wf-panel" class="panel" aria-labelledby="wf-heading">
  <h2 id="wf-heading">Walk-forward test</h2>
  <p class="hint">Splits the prices into rolling train and test blocks. In each window the SMA crossover pair (or the parameter set of the strategy you pick) with the best return is picked using the train bars only, then run on the test bars right after them, which the choice never saw. Each test block starts with fresh cash. The numbers are exactly those of <code>python -m trading_assistant.walkforward --json</code>.</p>
  <form id="wf-form" novalidate aria-labelledby="wf-heading">
    <div class="grid">
      <div class="field span2">
        <label for="wf-source">Price series</label>
        <select id="wf-source" name="source"></select>
        <p class="hint" id="wf-source-hint"></p>
      </div>
      <div class="field span2" id="wf-csv-block" hidden>
        <label for="wf-csv">CSV with a <code>close</code> column</label>
        <textarea id="wf-csv" name="csv" rows="6" spellcheck="false" placeholder="date,close&#10;2026-01-02,101.5&#10;2026-01-05,102.1"></textarea>
        <div class="row">
          <label class="file-label" for="wf-file">Upload a CSV file</label>
          <input type="file" id="wf-file" accept=".csv,text/csv,text/plain">
          <span class="hint" id="wf-csv-hint"></span>
        </div>
      </div>
      <div class="field span2">
        <label for="wf-strategy">Strategy</label>
        <select id="wf-strategy" name="strategy"></select>
        <p class="hint" id="wf-strategy-hint"></p>
      </div>
      <div class="field span2" id="wf-strategy-params-block" hidden>
        <p class="hint" id="wf-strategy-params-hint">Each field holds the default. Give one value, or a comma list such as 10,20,30 to try each value on every train block; every combination of the lists is tried.</p>
        <div class="grid nested-grid" id="wf-strategy-params"></div>
      </div>
      <div class="field" id="wf-short-field">
        <label for="wf-short">Short SMA windows</label>
        <input id="wf-short" name="short" type="text" inputmode="numeric" spellcheck="false" value="5,10,20">
      </div>
      <div class="field" id="wf-long-field">
        <label for="wf-long">Long SMA windows</label>
        <input id="wf-long" name="long" type="text" inputmode="numeric" spellcheck="false" value="20,50,100">
      </div>
      <div class="field">
        <label for="wf-train">Train bars</label>
        <input id="wf-train" name="train" type="number" inputmode="numeric" min="1" step="1" value="250">
      </div>
      <div class="field">
        <label for="wf-test">Test bars</label>
        <input id="wf-test" name="test" type="number" inputmode="numeric" min="1" step="1" value="60">
      </div>
      <div class="field">
        <label for="wf-step">Step (bars)</label>
        <input id="wf-step" name="step" type="number" inputmode="numeric" min="1" step="1" placeholder="Same as test">
      </div>
      <div class="field">
        <label for="wf-cash">Starting cash</label>
        <input id="wf-cash" name="cash" type="number" inputmode="decimal" min="0" step="any" value="10000">
      </div>
      <div class="field">
        <label for="wf-fee">Fee per trade</label>
        <input id="wf-fee" name="fee" type="number" inputmode="decimal" min="0" step="any" value="0">
      </div>
      <div class="field">
        <label for="wf-fee-pct">Cost % of trade value</label>
        <input id="wf-fee-pct" name="fee_pct" type="number" inputmode="decimal" min="0" max="99.99" step="any" value="0">
      </div>
      <div class="field">
        <label for="wf-warmup">Warm up</label>
        <div class="row">
          <input id="wf-warmup" name="warmup" type="checkbox">
          <span class="hint" id="wf-warmup-hint">Warm the moving averages up on the chosen pair's long bars just before each test block (the command's --warmup). The pair is still chosen on the train bars only; trades and scores still count only inside the test block.</span>
        </div>
      </div>
    </div>
    <div class="actions">
      <button type="submit" id="wf-run" class="primary">Run walk-forward</button>
      <span id="wf-status" class="status" role="status" aria-live="polite"></span>
    </div>
    <div id="wf-error" class="error" role="alert" hidden></div>
  </form>

  <div id="wf-results" class="wf-results" hidden aria-live="polite">
    <p class="hint" id="wf-warmup-line" hidden></p>
    <h3>Windows <span class="muted" id="wf-count"></span></h3>
    <p class="hint">Bar ranges include both ends. Returns are for each block on its own.</p>
    <div class="table-wrap">
      <table id="wf-table">
        <thead><tr>
          <th scope="col">Window</th><th scope="col">Train bars</th><th scope="col">Test bars</th><th scope="col">Pair</th>
          <th scope="col" class="num">Train</th><th scope="col" class="num">Test</th>
          <th scope="col" class="num">Buy &amp; hold</th><th scope="col" class="num">Trades</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <h3>Summary</h3>
    <div class="table-wrap">
      <table id="wf-summary-table">
        <thead><tr><th scope="col">Measure</th><th scope="col" class="num">Value</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <ul id="wf-notes" class="wf-notes"></ul>
    <p class="wf-overfit" id="wf-overfit"></p>
    <p class="wf-disclaimer" id="wf-disclaimer">Research aid only. Not financial advice.</p>
  </div>
</section>

<section id="pf-panel" class="panel" aria-labelledby="pf-heading">
  <h2 id="pf-heading">Portfolio backtest</h2>
  <p class="hint">Runs the SMA crossover (or the strategy you pick) on every file at once, with the cash split equally (or by your weights), on the dates every file shares; a date missing from one file is dropped for all of them. The numbers are exactly those of <code>python -m trading_assistant.portfolio FOLDER --json</code>. The files are read in your browser and sent to this local server only; they are never saved.</p>
  <form id="pf-form" novalidate aria-labelledby="pf-heading">
    <div class="grid">
      <div class="field span2">
        <label for="pf-files">CSV files (the file name without .csv is the symbol)</label>
        <input type="file" id="pf-files" multiple accept=".csv,text/csv">
        <p class="hint" id="pf-files-hint">Pick two or more files with <code>date</code> and <code>close</code> columns. Files that cannot be used are listed as skipped.</p>
      </div>
      <div class="field span2">
        <label for="pf-strategy">Strategy</label>
        <select id="pf-strategy" name="strategy"></select>
        <p class="hint" id="pf-strategy-hint"></p>
      </div>
      <div class="field span2" id="pf-strategy-params-block" hidden>
        <div class="grid nested-grid" id="pf-strategy-params"></div>
      </div>
      <div class="field" id="pf-short-field">
        <label for="pf-short">Short SMA</label>
        <input id="pf-short" name="short" type="number" inputmode="numeric" min="1" step="1" value="20">
      </div>
      <div class="field" id="pf-long-field">
        <label for="pf-long">Long SMA</label>
        <input id="pf-long" name="long" type="number" inputmode="numeric" min="2" step="1" value="50">
      </div>
      <div class="field">
        <label for="pf-cash">Starting cash</label>
        <input id="pf-cash" name="cash" type="number" inputmode="decimal" min="0" step="any" value="10000">
      </div>
      <div class="field">
        <label for="pf-fee">Fee per trade</label>
        <input id="pf-fee" name="fee" type="number" inputmode="decimal" min="0" step="any" value="0">
      </div>
      <div class="field">
        <label for="pf-fee-pct">Cost % of trade value</label>
        <input id="pf-fee-pct" name="fee_pct" type="number" inputmode="decimal" min="0" max="99.99" step="any" value="0">
      </div>
      <div class="field span2">
        <label for="pf-weights">Weights</label>
        <input id="pf-weights" name="weights" type="text" spellcheck="false" placeholder="A=70 B=30">
        <p class="hint" id="pf-weights-hint">Empty splits the cash equally. Otherwise one SYMBOL=PERCENT per file used, each above 0, adding up to 100.</p>
      </div>
    </div>
    <div class="actions">
      <button type="submit" id="pf-run" class="primary">Run portfolio backtest</button>
      <span id="pf-status" class="status" role="status" aria-live="polite"></span>
    </div>
    <div id="pf-error" class="error" role="alert" hidden></div>
  </form>

  <div id="pf-results" class="pf-results" hidden aria-live="polite">
    <p class="pf-title" id="pf-title"></p>
    <div class="table-wrap">
      <table id="pf-summary-table">
        <thead><tr><th scope="col">Measure</th><th scope="col" class="num">Value</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <h3>Per symbol</h3>
    <div class="table-wrap">
      <table id="pf-table">
        <thead><tr>
          <th scope="col">Symbol</th><th scope="col" class="num" id="pf-weight-col" hidden>Weight</th>
          <th scope="col" class="num">Bars used</th><th scope="col" class="num">Bars lost</th>
          <th scope="col" class="num">Return</th><th scope="col" class="num">Trades</th>
          <th scope="col" class="num">Buy &amp; hold</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="pf-worst" id="pf-worst"></p>
    <p class="hint" id="pf-note" hidden></p>
    <h3>Skipped files <span class="muted" id="pf-skipped-count"></span></h3>
    <ul id="pf-skipped" class="scan-skipped"></ul>
    <p class="hint" id="pf-no-skipped" hidden>None.</p>
    <p class="pf-disclaimer" id="pf-disclaimer">Research aid only. Not financial advice.</p>
  </div>
</section>
</main>

<footer>
  <p id="disclaimer">Research aid only. Not financial advice.</p>
</footer>
<script src="/app.js"></script>
</body>
</html>
"""

STYLE_CSS = r"""
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1c2330;
  --muted: #5b6573;
  --border: #d9dee5;
  --accent: #2457c5;
  --accent-text: #ffffff;
  --focus: #ff9800;
  --buy: #1a8f4a;
  --sell: #d23d3d;
  --line-price: #2457c5;
  --line-equity: #7a3fc9;
  --line-bench: #8a93a0;
  --grid: #e6e9ee;
  --good: #1a8f4a;
  --bad: #d23d3d;
  --error-bg: #fdecec;
  --error-border: #e5a1a1;
  --shadow: 0 1px 2px rgba(0,0,0,.06);
}
:root[data-theme="dark"] {
  --bg: #12161c;
  --panel: #1b2129;
  --text: #e6e9ee;
  --muted: #9aa4b1;
  --border: #2c3542;
  --accent: #6d9cff;
  --accent-text: #0b1220;
  --focus: #ffb454;
  --buy: #3ddc84;
  --sell: #ff6b6b;
  --line-price: #6d9cff;
  --line-equity: #c792ea;
  --line-bench: #7b8594;
  --grid: #273040;
  --good: #3ddc84;
  --bad: #ff6b6b;
  --error-bg: #3a1f23;
  --error-border: #7a3b42;
  --shadow: none;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #12161c; --panel: #1b2129; --text: #e6e9ee; --muted: #9aa4b1; --border: #2c3542;
    --accent: #6d9cff; --accent-text: #0b1220; --focus: #ffb454; --buy: #3ddc84; --sell: #ff6b6b;
    --line-price: #6d9cff; --line-equity: #c792ea; --line-bench: #7b8594; --grid: #273040;
    --good: #3ddc84; --bad: #ff6b6b; --error-bg: #3a1f23; --error-border: #7a3b42; --shadow: none;
  }
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { font-size: 16px; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.45;
  color: var(--text);
  background: var(--bg);
}
main { max-width: 1100px; margin: 0 auto; padding: 0 1rem 2rem; }
h1 { font-size: 1.25rem; margin: 0; }
h2 { font-size: 1.1rem; margin: 0 0 .75rem; }
h3 { font-size: 1rem; margin: 0 0 .5rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .95em; }
pre { margin: .5rem 0 0; overflow-x: auto; font-size: .85rem; line-height: 1.35; }
.muted { color: var(--muted); font-weight: normal; }
.hint { color: var(--muted); font-size: .85rem; margin: .25rem 0 0; }

.skip-link { position: absolute; left: -999px; top: 0; background: var(--accent); color: var(--accent-text); padding: .5rem; z-index: 10; }
.skip-link:focus { left: .5rem; top: .5rem; }

.topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  max-width: 1100px; margin: 0 auto; padding: .9rem 1rem;
}

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow);
}
details.panel summary { cursor: pointer; font-weight: 600; }

.grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem 1rem; }
.nested-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.field { display: flex; flex-direction: column; gap: .25rem; min-width: 0; }
.span2 { grid-column: span 2; }
label { font-size: .85rem; font-weight: 600; }
input, select, textarea, button {
  font: inherit; color: inherit;
}
input[type="number"], select, textarea {
  width: 100%; padding: .5rem .6rem;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg); color: var(--text);
}
textarea { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .85rem; resize: vertical; }
input[type="file"] { font-size: .85rem; max-width: 100%; }
.file-label { font-weight: 600; font-size: .85rem; }
.row { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem; margin-top: .5rem; }
.row.between { justify-content: space-between; margin-top: 0; }

.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; }
button {
  padding: .55rem .9rem; border-radius: 8px; border: 1px solid var(--border);
  background: var(--panel); color: var(--text); cursor: pointer;
}
button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); font-weight: 600; }
button.ghost { background: transparent; }
button:disabled { opacity: .6; cursor: progress; }
button:hover:not(:disabled) { filter: brightness(1.05); }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }

.status { color: var(--muted); font-size: .9rem; }
.error {
  margin-top: .75rem; padding: .6rem .8rem; border-radius: 8px;
  background: var(--error-bg); border: 1px solid var(--error-border);
  white-space: pre-wrap; word-break: break-word;
}

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .75rem; margin-bottom: 1rem; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: .7rem .8rem; box-shadow: var(--shadow); }
.card .label { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .03em; }
.card .value { font-size: 1.25rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.card .sub { font-size: .8rem; color: var(--muted); }
.good { color: var(--good); }
.bad { color: var(--bad); }

.chart-panel { padding-bottom: .6rem; }
.chart { position: relative; width: 100%; min-height: 220px; border-radius: 8px; }
.chart:focus-visible { outline: 3px solid var(--focus); }
.chart svg { display: block; width: 100%; height: auto; font-size: 11px; }
.chart .axis text { fill: var(--muted); }
.chart .grid-line { stroke: var(--grid); stroke-width: 1; }
.chart .axis-line { stroke: var(--border); stroke-width: 1; }
.chart .line-price { stroke: var(--line-price); }
.chart .line-equity { stroke: var(--line-equity); }
.chart .line-bench { stroke: var(--line-bench); stroke-dasharray: 5 4; }
.chart .line { fill: none; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; }
.chart .marker-buy { fill: var(--buy); stroke: var(--panel); stroke-width: 1; }
.chart .marker-sell { fill: var(--sell); stroke: var(--panel); stroke-width: 1; }
.chart .cursor { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.chart .dot { stroke: var(--panel); stroke-width: 1.5; }
.chart .hit { fill: transparent; cursor: crosshair; }
.tooltip {
  position: absolute; top: 8px; left: 8px; pointer-events: none;
  background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: .4rem .6rem; font-size: .8rem; line-height: 1.35; box-shadow: var(--shadow);
  max-width: 60%; font-variant-numeric: tabular-nums;
}
.tooltip[hidden] { display: none; }
.tooltip .t-title { font-weight: 600; }
.legend { display: flex; flex-wrap: wrap; gap: .4rem 1rem; font-size: .8rem; color: var(--muted); margin-top: .4rem; }
.legend .swatch { display: inline-block; width: 18px; height: 0; border-top: 3px solid; vertical-align: middle; margin-right: .35rem; }
.legend .swatch.dashed { border-top-style: dashed; }
.legend .tri { display: inline-block; width: 0; height: 0; border-left: 6px solid transparent; border-right: 6px solid transparent; vertical-align: middle; margin-right: .35rem; }
.legend .tri.buy { border-bottom: 10px solid var(--buy); }
.legend .tri.sell { border-top: 10px solid var(--sell); }

.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; font-variant-numeric: tabular-nums; }
th, td { padding: .4rem .5rem; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
th.num, td.num { text-align: right; }
tbody tr:hover { background: var(--bg); }
.side-BUY { color: var(--buy); font-weight: 600; }
.side-SELL { color: var(--sell); font-weight: 600; }

footer { text-align: center; color: var(--muted); font-size: .85rem; padding: 1rem; }

.scan-results { margin-top: 1rem; }
.scan-results h3 { margin-top: 1rem; }
.scan-skipped { margin: .25rem 0 0; padding-left: 1.2rem; font-size: .9rem; word-break: break-word; }
.scan-disclaimer { color: var(--muted); font-size: .85rem; margin: 1rem 0 0; }

.wf-results { margin-top: 1rem; }
.wf-results h3 { margin-top: 1rem; }
.wf-notes { margin: .75rem 0 0; padding-left: 1.2rem; font-size: .9rem; word-break: break-word; }
.wf-overfit { font-size: .9rem; margin: .75rem 0 0; }
.wf-disclaimer { color: var(--muted); font-size: .85rem; margin: 1rem 0 0; }

.pf-results { margin-top: 1rem; }
.pf-results h3 { margin-top: 1rem; }
.pf-title { font-weight: 600; margin: 0 0 .75rem; word-break: break-word; }
.pf-worst { font-size: .9rem; margin: .75rem 0 0; }
.pf-disclaimer { color: var(--muted); font-size: .85rem; margin: 1rem 0 0; }

@media (max-width: 720px) {
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .card .value { font-size: 1.1rem; }
  html { font-size: 15px; }
}
@media (max-width: 420px) {
  .grid { grid-template-columns: 1fr; }
  .span2 { grid-column: auto; }
}
@media (prefers-reduced-motion: no-preference) {
  button { transition: filter .15s; }
}
"""

APP_JS = r"""
'use strict';
(function () {
  // ---------------------------------------------------------------- helpers
  const $ = (id) => document.getElementById(id);
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    if (attrs) for (const k of Object.keys(attrs)) {
      if (k === 'className') node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    }
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) for (const k of Object.keys(attrs)) node.setAttribute(k, attrs[k]);
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function fmtMoney(v) {
    return Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // ---------------------------------------------------------------- theme
  const root = document.documentElement;
  const themeBtn = $('theme-toggle');
  function currentTheme() {
    const forced = root.getAttribute('data-theme');
    if (forced) return forced;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function applyTheme(theme, persist) {
    root.setAttribute('data-theme', theme);
    themeBtn.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
    themeBtn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    if (persist) { try { localStorage.setItem('ta-theme', theme); } catch (e) { /* private mode */ } }
  }
  (function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem('ta-theme'); } catch (e) { /* ignore */ }
    if (saved === 'dark' || saved === 'light') applyTheme(saved, false);
    else themeBtn.textContent = currentTheme() === 'dark' ? 'Light mode' : 'Dark mode';
  })();
  themeBtn.addEventListener('click', () => applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true));

  // ---------------------------------------------------------------- form
  const form = $('form');
  const sourceSel = $('source');
  const csvBlock = $('csv-block');
  const csvArea = $('csv');
  const fileInput = $('file');
  const runBtn = $('run');
  const statusEl = $('status');
  const errorEl = $('error');
  const results = $('results');
  let limits = { max_body_bytes: 1000000, max_bars: 10000, max_window: 500 };
  let samples = [];
  let strategies = [];
  const strategySel = $('strategy');
  const pfStrategySel = $('pf-strategy');
  const wfStrategySel = $('wf-strategy');
  let lastResponse = null;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
    statusEl.textContent = '';
  }
  function clearError() { errorEl.textContent = ''; errorEl.hidden = true; }

  function updateSourceUi() {
    const isCsv = sourceSel.value === 'csv';
    csvBlock.hidden = !isCsv;
    const info = samples.find((s) => s.name === sourceSel.value);
    $('source-hint').textContent = isCsv
      ? 'Paste CSV text or upload a file. Limits: ' + limits.max_bars.toLocaleString() + ' rows, ' +
        Math.floor(limits.max_body_bytes / 1000).toLocaleString() + ' kB.'
      : (info ? info.description + '.' : '');
    updateCandleAvailability();
  }
  sourceSel.addEventListener('change', updateSourceUi);

  // fill=open, stop loss, take profit and trailing stop need candle data (open/high/low, not just close); every
  // built-in sample has it, a pasted/uploaded CSV needs it pasted in as a candle file. This only
  // reads the pasted header to decide whether to grey the controls out: it is a UI hint, not a
  // calculation, and the server checks (and rejects) for real when the backtest runs.
  const CANDLE_CONTROLS = ['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown', 'scale_out'];
  function pastedCsvHasCandleColumns(text) {
    const header = (text || '').split(/\r\n|\r|\n/, 1)[0] || '';
    const columns = header.split(',').map((c) => c.trim().toLowerCase());
    return ['open', 'high', 'low'].every((name) => columns.includes(name));
  }
  function updateCandleAvailability() {
    const available = sourceSel.value !== 'csv' || pastedCsvHasCandleColumns(csvArea.value);
    for (const id of CANDLE_CONTROLS) {
      const field = $(id);
      field.disabled = !available;
      if (!available && field.type === 'checkbox') field.checked = false;
      else if (!available) field.value = id === 'fill' ? 'close' : '';
    }
    $('candle-hint').hidden = available;
  }
  csvArea.addEventListener('input', updateCandleAvailability);

  function currentStrategy() { return strategies.find((s) => s.name === strategySel.value); }
  function updateStrategyUi() {
    const info = currentStrategy();
    const box = $('strategy-params');
    clear(box);
    $('strategy-hint').textContent = info ? info.description + '.' : '';
    const isSma = !info || info.name === 'sma_cross';
    $('strategy-params-block').hidden = isSma;
    if (isSma) return;
    for (const key of Object.keys(info.params)) {
      const id = 'param-' + key;
      const field = el('div', { className: 'field' });
      field.appendChild(el('label', { for: id }, key));
      field.appendChild(el('input', { id: id, type: 'number', step: 'any', value: String(info.params[key]), required: 'required' }));
      box.appendChild(field);
    }
  }
  strategySel.addEventListener('change', updateStrategyUi);

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (file.size > limits.max_body_bytes) {
      showError('That file is ' + file.size.toLocaleString() + ' bytes; the limit is ' +
        limits.max_body_bytes.toLocaleString() + ' bytes.');
      fileInput.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      csvArea.value = String(reader.result || '');
      $('csv-hint').textContent = 'Loaded ' + file.name + ' (' + file.size.toLocaleString() + ' bytes).';
      clearError();
      updateCandleAvailability();
    };
    reader.onerror = () => showError('Could not read ' + file.name + '.');
    reader.readAsText(file);
  });

  async function loadSamples() {
    try {
      const res = await fetch('/api/samples', { headers: { 'Accept': 'application/json' } });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'could not load samples');
      samples = data.samples;
      strategies = data.strategies || [];
      limits = data.limits || limits;
    } catch (err) {
      showError('Could not load the sample list from the server: ' + (err && err.message ? err.message : err));
      samples = [];
    }
    clear(sourceSel);
    for (const s of samples) sourceSel.appendChild(el('option', { value: s.name }, s.label + ' (' + s.bars + ' bars)'));
    sourceSel.appendChild(el('option', { value: 'csv' }, 'Paste or upload my own CSV'));
    clear(strategySel);
    for (const st of strategies) strategySel.appendChild(el('option', { value: st.name }, st.name));
    updateStrategyUi();
    clear(pfStrategySel);
    for (const st of strategies) pfStrategySel.appendChild(el('option', { value: st.name }, st.name));
    updatePfStrategyUi();
    clear(wfStrategySel);
    for (const st of strategies) wfStrategySel.appendChild(el('option', { value: st.name }, st.name));
    updateWfStrategyUi();
    for (const id of ['short', 'long', 'rsi']) $(id).max = String(limits.max_window);
    for (const id of ['scan-short', 'scan-long', 'scan-rsi']) $(id).max = String(limits.max_window);
    updateSourceUi();
    const wfSource = $('wf-source');
    clear(wfSource);
    for (const s of samples) wfSource.appendChild(el('option', { value: s.name }, s.label + ' (' + s.bars + ' bars)'));
    wfSource.appendChild(el('option', { value: 'csv' }, 'Paste or upload my own CSV'));
    updateWfSourceUi();
  }

  function readForm() {
    const payload = {
      source: sourceSel.value === 'csv' ? 'csv' : 'sample',
      sample: sourceSel.value,
      short: $('short').value.trim(),
      long: $('long').value.trim(),
      rsi_period: $('rsi').value.trim(),
      cash: $('cash').value.trim(),
      fee: $('fee').value.trim(),
      fee_pct: $('fee_pct').value.trim(),
      slippage: $('slippage').value.trim(),
      // the control is a percentage of the account (e.g. 50); the API takes a fraction (0, 1]
      position_size: $('position_size').value.trim() === '' ? '' : String(Number($('position_size').value.trim()) / 100),
      // fill/stop_loss/take_profit are disabled (and blanked) without candle data, so a disabled
      // control here never sends a value the server could not honour anyway
      fill: $('fill').disabled ? 'close' : $('fill').value,
      stop_loss: $('stop_loss').disabled ? '' : $('stop_loss').value.trim(),
      take_profit: $('take_profit').disabled ? '' : $('take_profit').value.trim(),
    };
    // trailing_stop is sent only when it has a value, so a request without it is exactly the old one
    // (like the others, it is disabled and blanked without candle data)
    const trailingStop = $('trailing_stop').disabled ? '' : $('trailing_stop').value.trim();
    if (trailingStop !== '') payload.trailing_stop = trailingStop;
    // breakeven: sent only when filled in (empty: the old request); a stop, so blanked without candle data
    const breakeven = $('breakeven').disabled ? '' : $('breakeven').value.trim();
    if (breakeven !== '') payload.breakeven = breakeven;
    // scale-out: sent only when filled in, so an empty field sends exactly the old request; the server checks it
    // (above 0, a finite number) and its message is shown as for the other fields. It needs candle data like the
    // stops, so it is in CANDLE_CONTROLS: disabled and blanked without it.
    const scaleOut = $('scale_out').disabled ? '' : $('scale_out').value.trim();
    if (scaleOut !== '') payload.scale_out = scaleOut;
    // risk sizing: sent only when Risk % has a value, and the ATR fields only count (and are only sent)
    // together with it, so a request without it is exactly the old one; disabled and blanked without
    // candle data like the stops
    const riskPct = $('risk_pct').disabled ? '' : $('risk_pct').value.trim();
    if (riskPct !== '') {
      payload.risk_pct = riskPct;
      const atrMult = $('atr_mult').value.trim();
      const atrPeriod = $('atr_period').value.trim();
      if (atrMult !== '') payload.atr_mult = atrMult;
      if (atrPeriod !== '') payload.atr_period = atrPeriod;
    }
    // ATR stop: sent (as true) only when ticked, so an unticked box sends exactly the old request; the ATR
    // fields count with it too, so they are sent with it when Risk % did not send them already. Disabled
    // and unticked without candle data like the stops.
    if (!$('atr_stop').disabled && $('atr_stop').checked === true) {
      if (riskPct === '') {
        const atrMult = $('atr_mult').value.trim();
        const atrPeriod = $('atr_period').value.trim();
        if (atrMult !== '') payload.atr_mult = atrMult;
        if (atrPeriod !== '') payload.atr_period = atrPeriod;
      }
      payload.atr_stop = true;
    }
    // cooldown: sent only when filled in, so an empty field sends exactly the old request; the server checks
    // it (a stop must be on, a whole number of at least 1) and its message is shown as for the other fields.
    // Disabled and blanked without candle data like the stops.
    const cooldown = $('cooldown').disabled ? '' : $('cooldown').value.trim();
    if (cooldown !== '') payload.cooldown = cooldown;
    // min hold: sent only when filled in, so an empty field sends exactly the old request; the server checks
    // it (a whole number of at least 1) and its message is shown as for the other fields. Like max hold it needs
    // no candle data, so it is not in CANDLE_CONTROLS: never greyed out or blanked.
    const minHold = $('min_hold').value.trim();
    if (minHold !== '') payload.min_hold = minHold;
    // max losses: sent only when filled in, so an empty field sends exactly the old request; the server checks
    // it (a whole number of at least 1) and its message is shown as for the other fields. Like min hold it needs
    // no candle data, so it is not in CANDLE_CONTROLS: never greyed out or blanked.
    const maxLosses = $('max_losses').value.trim();
    if (maxLosses !== '') payload.max_losses = maxLosses;
    // max hold: sent only when filled in, so an empty field sends exactly the old request; the server checks
    // it (a whole number of at least 1) and its message is shown as for the other fields. It needs no candle
    // data, so unlike the stops it is not in CANDLE_CONTROLS: never greyed out or blanked.
    const maxHold = $('max_hold').value.trim();
    if (maxHold !== '') payload.max_hold = maxHold;
    // max drawdown: sent only when filled in, so an empty field sends exactly the old request; the server checks
    // it (above 0 and below 100) and its message is shown as for the other fields. Like max hold it needs no
    // candle data, so it is not in CANDLE_CONTROLS: never greyed out or blanked.
    const maxDrawdown = $('max_drawdown').value.trim();
    if (maxDrawdown !== '') payload.max_drawdown = maxDrawdown;
    // add-on and max adds: each sent only when filled in, so empty fields send exactly the old request; the server
    // checks them (add_on above 0 and finite; max_adds a whole number of at least 1, and only with add_on) and its
    // message is shown as for the other fields. A filled Max adds is sent even when Add-on is empty, so the API's
    // message says why. They need no candle data, so they are not in CANDLE_CONTROLS: never greyed out or blanked.
    const addOn = $('add_on').value.trim();
    if (addOn !== '') payload.add_on = addOn;
    const maxAdds = $('max_adds').value.trim();
    if (maxAdds !== '') payload.max_adds = maxAdds;
    // trade list: sent (as true) only when ticked, so an unticked box sends exactly the old request. It changes no
    // setting of the run and needs no candle data, so it is not in CANDLE_CONTROLS: never greyed out or unticked.
    if ($('trade_list').checked === true) payload.trade_list = true;
    // explain: sent (as true) only when ticked, so an unticked box sends exactly the old request. Like trade list it
    // changes no setting of the run and needs no candle data: not in CANDLE_CONTROLS, never greyed out or unticked.
    // The reply's report then has the sentence right under its Signal line, and the page shows the report as it
    // is, so the sentence appears once, in the text report, and nothing else on the page changes.
    if ($('explain').checked === true) payload.explain = true;
    const info = currentStrategy();
    if (info && info.name !== 'sma_cross') {
      payload.strategy = info.name;
      payload.params = {};
      for (const key of Object.keys(info.params)) payload.params[key] = $('param-' + key).value.trim();
    }
    if (payload.source === 'csv') {
      payload.csv = csvArea.value;
      if (!payload.csv.trim()) throw new Error('Paste or upload a CSV first, or pick a sample series.');
      if (payload.csv.length > limits.max_body_bytes) {
        throw new Error('The CSV is ' + payload.csv.length.toLocaleString() + ' characters; the limit is ' +
          limits.max_body_bytes.toLocaleString() + '.');
      }
    }
    return payload;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();
    let payload;
    try { payload = readForm(); } catch (err) { showError(err.message); return; }
    runBtn.disabled = true;
    statusEl.textContent = 'Running...';
    const started = performance.now();
    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
      });
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok || !data || !data.ok) {
        const msg = (data && data.error) ? data.error : ('Server answered ' + res.status + ' ' + res.statusText);
        showError(msg);
        return;
      }
      render(data);
      statusEl.textContent = 'Done in ' + Math.round(performance.now() - started) + ' ms.';
    } catch (err) {
      showError('Could not reach the server: ' + (err && err.message ? err.message : err) +
        '. Is "python -m trading_assistant.web" still running?');
    } finally {
      runBtn.disabled = false;
    }
  });

  // ---------------------------------------------------------------- rendering
  function card(label, value, sub, tone) {
    const c = el('div', { className: 'card' });
    c.appendChild(el('div', { className: 'label' }, label));
    const v = el('div', { className: 'value' + (tone ? ' ' + tone : '') }, value);
    c.appendChild(v);
    if (sub) c.appendChild(el('div', { className: 'sub' }, sub));
    return c;
  }
  const tone = (v) => (v > 0 ? 'good' : v < 0 ? 'bad' : '');

  function render(data) {
    lastResponse = data;
    const s = data.summary;
    const bh = s.buy_hold;
    $('results-source').textContent = '- ' + data.source.label + ', ' + data.source.bars + ' bars, ' +
      (data.strategy === 'sma_cross' ? 'SMA ' + data.params.short + '/' + data.params.long : data.strategy);

    const cards = $('cards');
    clear(cards);
    cards.appendChild(card('Start cash', s.start_cash.text));
    cards.appendChild(card('End equity', s.end_equity.text, s.end_cash.text + ' cash + ' + s.end_shares + ' sh @ ' + s.last_price.text));
    cards.appendChild(card('Return', s.return_pct.text, 'buy & hold ' + bh.return_pct.text, tone(s.return_pct.value)));
    cards.appendChild(card('Max drawdown', s.max_drawdown_pct.text, 'buy & hold ' + bh.max_drawdown_pct.text, s.max_drawdown_pct.value < 0 ? 'bad' : ''));
    cards.appendChild(card('Trades', String(s.trades), s.buys + ' buys, ' + s.sells + ' sells' +
      (s.risk_skipped_buys === undefined ? '' : ', ' + s.risk_skipped_buys + ' skipped') +
      (s.breakeven_exits === undefined ? '' : ', ' + s.breakeven_exits + ' sold at breakeven') +
      (s.scale_out_exits === undefined ? '' : ', ' + s.scale_out_exits + ' partial sells by scale-out') +
      (s.add_on_buys === undefined ? '' : ', ' + s.add_on_buys + ' add-on buys, ' + s.add_on_skipped_buys + ' add-ons skipped') +
      (s.cooldown_skipped_buys === undefined ? '' : ', ' + s.cooldown_skipped_buys + ' skipped by cooldown') +
      (s.min_hold_skipped_sells === undefined ? '' : ', ' + s.min_hold_skipped_sells + ' signal sells skipped by min hold') +
      (s.time_exits === undefined ? '' : ', ' + s.time_exits + ' sold by max hold') +
      (s.drawdown_skipped_buys === undefined ? '' : ', ' + s.drawdown_skipped_buys + ' skipped by drawdown') +
      (s.loss_skipped_buys === undefined ? '' : ', ' + s.loss_skipped_buys + ' buys skipped by losing streak')));
    cards.appendChild(card('Round trips', s.win_rate_text === 'none completed' ? '0' : s.winning_round_trips + ' / ' + s.round_trips, s.round_trips ? 'made money' : 'none completed'));
    cards.appendChild(card('Costs paid', s.costs_paid.text, 'fee ' + fmtMoney(data.params.fee) + ' + ' + Number(data.params.fee_pct).toFixed(2) + '%'));
    const fill = data.params.fill || 'close';
    const slippagePct = Number(data.params.slippage || 0);
    cards.appendChild(card('Fill price', fill === 'open' ? "Next bar's open" : "Next bar's close",
      slippagePct ? slippagePct.toFixed(2) + '% slippage' : 'no slippage'));
    cards.appendChild(card('Position size', data.params.position_size ? (Number(data.params.position_size) * 100).toFixed(2) + '% of account' : 'all-in'));
    if (data.params.stop_loss !== undefined || data.params.take_profit !== undefined) {
      const parts = [];
      if (data.params.stop_loss !== undefined) parts.push('stop ' + Number(data.params.stop_loss).toFixed(2) + '%');
      if (data.params.take_profit !== undefined) parts.push('target ' + Number(data.params.take_profit).toFixed(2) + '%');
      cards.appendChild(card('Exits', parts.join(' / '), parts.length > 1 ? 'stop wins if a bar touches both' : ''));
    }

    const compare = $('compare-table').tBodies[0];
    clear(compare);
    const rowsC = [
      ['End equity', s.end_equity.text, bh.end_equity.text],
      ['Return', s.return_pct.text, bh.return_pct.text],
      ['Max drawdown', s.max_drawdown_pct.text, bh.max_drawdown_pct.text],
      ['Trades', String(s.trades), String(bh.trades)],
      ['Shares held at end', String(s.end_shares), String(bh.shares)],
      ['Costs paid', s.costs_paid.text, bh.costs_paid.text],
    ];
    for (const r of rowsC) {
      const tr = el('tr');
      tr.appendChild(el('th', { scope: 'row' }, r[0]));
      tr.appendChild(el('td', { className: 'num' }, r[1]));
      tr.appendChild(el('td', { className: 'num' }, r[2]));
      compare.appendChild(tr);
    }

    const statsBody = $('stats-table').tBodies[0];
    clear(statsBody);
    const st = data.stats || {};
    const num = (v, d, suffix) => (v === null || v === undefined) ? 'n/a' : Number(v).toFixed(d) + (suffix || '');
    const statRows = [
      ['Total return', num(st.total_return_pct, 2, '%')],
      ['CAGR', num(st.cagr_pct, 2, '%')],
      ['Volatility (annualised)', num(st.annualized_volatility_pct, 2, '%')],
      ['Sharpe ratio', num(st.sharpe_ratio, 2)],
      ['Sortino ratio', num(st.sortino_ratio, 2)],
      ['Exposure', num(st.exposure_pct, 2, '%')],
      ['Profit factor', num(st.profit_factor, 2)],
      ['Average win', num(st.average_win, 2)],
      ['Average loss', num(st.average_loss, 2)],
      ['Longest drawdown', (st.longest_drawdown_bars === null || st.longest_drawdown_bars === undefined) ? 'n/a' : st.longest_drawdown_bars + ' bars'],
    ];
    for (const r of statRows) {
      const tr = el('tr');
      tr.appendChild(el('th', { scope: 'row' }, r[0]));
      tr.appendChild(el('td', { className: 'num' }, r[1]));
      statsBody.appendChild(tr);
    }

    const tbody = $('trades-table').tBodies[0];
    clear(tbody);
    for (const t of data.trades) {
      const tr = el('tr');
      tr.appendChild(el('td', null, t.n));
      tr.appendChild(el('td', null, t.bar));
      tr.appendChild(el('td', null, t.date || '-'));
      tr.appendChild(el('td', { className: 'side-' + t.side }, t.side));
      tr.appendChild(el('td', { className: 'num' }, t.shares));
      tr.appendChild(el('td', { className: 'num' }, t.price.text));
      tr.appendChild(el('td', { className: 'num' }, t.value.text));
      tr.appendChild(el('td', { className: 'num' }, t.cost.text));
      tr.appendChild(el('td', { className: 'num' }, t.cash_after.text));
      tr.appendChild(el('td', null, t.reason || '-'));
      tbody.appendChild(tr);
    }
    $('trade-count').textContent = '(' + data.trades.length + ')';
    $('no-trades').hidden = data.trades.length > 0;
    $('trades-table').hidden = data.trades.length === 0;

    // Trade list: only when the reply has trade_list (the box was ticked); otherwise the panel stays hidden, so a
    // run without it shows nothing extra. The cells are the text report's: numbers formatted as Python formats
    // them there (',.2f', '+,.2f', '+.2f'), which rounds an exact tie to the even digit where toFixed rounds it
    // away from zero. A double can be exactly halfway only when v * 2 (0 decimals) or v * 8 (2 decimals) is an
    // odd whole number, so only then is the even neighbour picked by hand.
    const tradeList = Array.isArray(data.trade_list) ? data.trade_list : null;
    const tlBody = $('trade-list-table').tBodies[0];
    clear(tlBody);
    $('trade-list-panel').hidden = tradeList === null;
    if (tradeList !== null) {
      const pyFixed = (v, d, signed, grouped) => {
        const a = Math.abs(v);
        const probe = d === 0 ? a * 2 : a * 8;
        let s = a.toFixed(d);
        if (Number.isInteger(probe) && probe % 2 === 1) {
          const units = Math.floor(a * Math.pow(10, d));
          s = ((units % 2 === 0 ? units : units + 1) / Math.pow(10, d)).toFixed(d);
        }
        if (grouped) s = s.replace(/^\d+/, (w) => w.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
        const negative = v < 0 || Object.is(v, -0);
        return (negative ? '-' : signed ? '+' : '') + s;
      };
      tradeList.forEach((r, i) => {
        const tr = el('tr', { className: r.open ? 'unrealized' : '' });
        tr.appendChild(el('td', null, r.open ? 'open' : String(i + 1)));
        tr.appendChild(el('td', { className: 'num' }, String(r.entry_bar)));
        tr.appendChild(el('td', { className: 'num' }, r.exit_bar === null ? 'open' : String(r.exit_bar)));
        tr.appendChild(el('td', { className: 'num' }, String(r.bars_held)));
        tr.appendChild(el('td', { className: 'num' }, String(r.shares)));
        tr.appendChild(el('td', { className: 'num' }, pyFixed(r.outlay, 2, false, true)));
        tr.appendChild(el('td', { className: 'num' }, pyFixed(r.proceeds, 2, false, true)));
        tr.appendChild(el('td', { className: 'num' }, pyFixed(r.pnl, 2, true, true)));
        tr.appendChild(el('td', { className: 'num' }, pyFixed(r.return_pct, 2, true, false) + '%'));
        tr.appendChild(el('td', null, (r.reason || '-') +
          (r.open ? ' (unrealized: marked at the last close, no selling costs)' : '')));
        tlBody.appendChild(tr);
      });
      const done = tradeList.filter((r) => !r.open);
      const wins = done.filter((r) => r.pnl > 0).length;
      let footer = done.length ? done.length + ' completed, ' + wins + ' made money (' +
        pyFixed(wins / done.length * 100, 0, false, false) + '%)' : '0 completed';
      if (done.length < tradeList.length) footer += ', 1 open (unrealized)';
      $('trade-list-table').hidden = tradeList.length === 0;
      $('trade-list-footer').textContent = tradeList.length ? footer : 'No trades.';
    }

    $('report').textContent = data.report.join('\n') + '\n' + data.disclaimer;

    // columns: bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity
    const col = {};
    data.columns.forEach((name, i) => { col[name] = i; });
    const rows = data.rows;
    const closes = rows.map((r) => Number(r[col.close]));
    const equity = rows.map((r) => Number(r[col.equity]));
    const bench = rows.map((r) => Number(r[col.buy_hold_equity]));
    const markers = [];
    rows.forEach((r, i) => { if (r[col.action]) markers.push({ i: i, side: r[col.action] }); });

    const tooltipFor = (i) => {
      const r = rows[i];
      const lines = [(r[col.date] ? r[col.date] + '  ' : '') + 'bar ' + r[col.bar]];
      lines.push('Close ' + r[col.close] + '   signal ' + r[col.signal]);
      if (r[col.action]) lines.push(r[col.action] + ' ' + r[col.shares] + ' @ ' + r[col.price] + ' (cost ' + r[col.cost] + ')');
      lines.push('Equity ' + r[col.equity] + '   cash ' + r[col.cash] + '   shares ' + r[col.position]);
      lines.push('Drawdown ' + r[col.drawdown_pct] + '%   buy & hold ' + r[col.buy_hold_equity]);
      return lines;
    };

    drawChart($('price-chart'), {
      series: [{ values: closes, className: 'line-price', label: 'Close' }],
      markers: markers, markerSeries: 0, labels: rows.map((r) => r[col.date] || ('bar ' + r[col.bar])),
      tooltipFor: tooltipFor,
    });
    legend($('price-legend'), [['line', 'line-price', 'Close'], ['buy'], ['sell']]);

    drawChart($('equity-chart'), {
      series: [
        { values: equity, className: 'line-equity', label: 'Strategy' },
        { values: bench, className: 'line-bench', label: 'Buy & hold' },
      ],
      markers: markers, markerSeries: 0, labels: rows.map((r) => r[col.date] || ('bar ' + r[col.bar])),
      tooltipFor: tooltipFor,
    });
    legend($('equity-legend'), [['line', 'line-equity', 'Strategy equity'], ['dashed', 'line-bench', 'Buy & hold'], ['buy'], ['sell']]);

    results.hidden = false;
    results.setAttribute('tabindex', '-1');
    results.focus({ preventScroll: false });
  }

  function legend(node, items) {
    clear(node);
    for (const item of items) {
      const span = el('span');
      if (item[0] === 'buy') { span.appendChild(el('span', { className: 'tri buy' })); span.appendChild(document.createTextNode('Buy')); }
      else if (item[0] === 'sell') { span.appendChild(el('span', { className: 'tri sell' })); span.appendChild(document.createTextNode('Sell')); }
      else {
        const sw = el('span', { className: 'swatch' + (item[0] === 'dashed' ? ' dashed' : '') });
        sw.style.borderTopColor = 'var(--' + item[1] + ')';
        span.appendChild(sw);
        span.appendChild(document.createTextNode(item[2]));
      }
      node.appendChild(span);
    }
  }

  // ---------------------------------------------------------------- charts (SVG, no libraries)
  function niceTicks(min, max, count) {
    if (!(max > min)) { max = min + 1; }
    const span = max - min;
    const rough = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const norm = rough / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const ticks = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
    return ticks;
  }

  const charts = new WeakMap();

  function drawChart(container, opts) {
    clear(container);
    const n = opts.series[0].values.length;
    if (!n) { container.appendChild(el('p', { className: 'hint' }, 'Nothing to draw.')); return; }
    const width = Math.max(320, container.clientWidth || 640);
    const height = width < 520 ? 220 : 300;
    const m = { top: 12, right: 14, bottom: 28, left: 58 };
    const pw = width - m.left - m.right;
    const ph = height - m.top - m.bottom;

    let lo = Infinity, hi = -Infinity;
    for (const s of opts.series) for (const v of s.values) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (!(hi > lo)) { hi = lo + 1; lo = lo - 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    const x = (i) => m.left + (n === 1 ? pw / 2 : (i / (n - 1)) * pw);
    const y = (v) => m.top + ph - ((v - lo) / (hi - lo)) * ph;

    const svg = svgEl('svg', { viewBox: '0 0 ' + width + ' ' + height, width: width, height: height, 'aria-hidden': 'true' });

    // grid + y axis
    const axis = svgEl('g', { class: 'axis' });
    for (const t of niceTicks(lo, hi, 5)) {
      axis.appendChild(svgEl('line', { x1: m.left, x2: m.left + pw, y1: y(t), y2: y(t), class: 'grid-line' }));
      const label = svgEl('text', { x: m.left - 6, y: y(t) + 4, 'text-anchor': 'end' });
      label.textContent = t >= 1000 ? Math.round(t).toLocaleString() : String(t);
      axis.appendChild(label);
    }
    // x axis labels: as many as fit at ~110px each, first and last pinned to the edges
    const count = Math.max(2, Math.min(8, Math.floor(pw / 110)));
    const seen = new Set();
    for (let k = 0; k < count; k++) {
      const i = n === 1 ? 0 : Math.round((k * (n - 1)) / (count - 1));
      if (seen.has(i)) continue;
      seen.add(i);
      const anchor = k === 0 ? 'start' : k === count - 1 ? 'end' : 'middle';
      const label = svgEl('text', { x: x(i), y: height - 8, 'text-anchor': anchor });
      label.textContent = opts.labels[i];
      axis.appendChild(label);
    }
    axis.appendChild(svgEl('line', { x1: m.left, x2: m.left + pw, y1: m.top + ph, y2: m.top + ph, class: 'axis-line' }));
    svg.appendChild(axis);

    // series
    for (const s of opts.series) {
      let d = '';
      s.values.forEach((v, i) => { d += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
      svg.appendChild(svgEl('path', { d: d, class: 'line ' + s.className }));
    }

    // markers
    const markerValues = opts.series[opts.markerSeries].values;
    for (const mk of opts.markers) {
      const cx = x(mk.i), cy = y(markerValues[mk.i]);
      const size = 6;
      const points = mk.side === 'BUY'
        ? (cx - size) + ',' + (cy + size + 4) + ' ' + (cx + size) + ',' + (cy + size + 4) + ' ' + cx + ',' + (cy + 4)
        : (cx - size) + ',' + (cy - size - 4) + ' ' + (cx + size) + ',' + (cy - size - 4) + ' ' + cx + ',' + (cy - 4);
      const tri = svgEl('polygon', { points: points, class: mk.side === 'BUY' ? 'marker-buy' : 'marker-sell' });
      const title = svgEl('title');
      title.textContent = mk.side + ' at ' + opts.labels[mk.i];
      tri.appendChild(title);
      svg.appendChild(tri);
    }

    // cursor + dots
    const cursor = svgEl('line', { class: 'cursor', y1: m.top, y2: m.top + ph, visibility: 'hidden' });
    svg.appendChild(cursor);
    const dots = opts.series.map((s) => {
      const dot = svgEl('circle', { r: 4, class: 'dot ' + s.className, visibility: 'hidden' });
      dot.style.fill = 'var(--' + s.className + ')';
      svg.appendChild(dot);
      return dot;
    });
    const hit = svgEl('rect', { x: m.left, y: m.top, width: pw, height: ph, class: 'hit' });
    svg.appendChild(hit);
    container.appendChild(svg);

    const tip = el('div', { className: 'tooltip', hidden: '' });
    container.appendChild(tip);

    let current = -1;
    function show(i) {
      if (i < 0 || i >= n) return;
      current = i;
      const px = x(i);
      cursor.setAttribute('x1', px); cursor.setAttribute('x2', px); cursor.setAttribute('visibility', 'visible');
      opts.series.forEach((s, k) => {
        dots[k].setAttribute('cx', px); dots[k].setAttribute('cy', y(s.values[i])); dots[k].setAttribute('visibility', 'visible');
      });
      clear(tip);
      const lines = opts.tooltipFor(i);
      lines.forEach((line, k) => tip.appendChild(el('div', { className: k === 0 ? 't-title' : '' }, line)));
      tip.hidden = false;
      const rect = container.getBoundingClientRect();
      const scale = rect.width / width;
      const tipWidth = tip.offsetWidth || 160;
      const leftPx = px * scale;
      tip.style.left = (leftPx + 12 + tipWidth > rect.width ? Math.max(4, leftPx - tipWidth - 12) : leftPx + 12) + 'px';
      tip.style.top = '8px';
    }
    function hide() {
      current = -1;
      cursor.setAttribute('visibility', 'hidden');
      dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
      tip.hidden = true;
    }
    function indexFromEvent(evt) {
      const rect = svg.getBoundingClientRect();
      const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
      const relX = (clientX - rect.left) * (width / rect.width);
      const frac = (relX - m.left) / pw;
      return Math.round(Math.min(1, Math.max(0, frac)) * (n - 1));
    }
    hit.addEventListener('mousemove', (evt) => show(indexFromEvent(evt)));
    hit.addEventListener('touchstart', (evt) => { show(indexFromEvent(evt)); }, { passive: true });
    hit.addEventListener('touchmove', (evt) => { show(indexFromEvent(evt)); }, { passive: true });
    hit.addEventListener('mouseleave', hide);
    container.addEventListener('keydown', (evt) => {
      const step = evt.shiftKey ? Math.max(1, Math.round(n / 20)) : 1;
      if (evt.key === 'ArrowRight') { show(Math.min(n - 1, (current < 0 ? -1 : current) + step)); evt.preventDefault(); }
      else if (evt.key === 'ArrowLeft') { show(Math.max(0, (current < 0 ? n : current) - step)); evt.preventDefault(); }
      else if (evt.key === 'Home') { show(0); evt.preventDefault(); }
      else if (evt.key === 'End') { show(n - 1); evt.preventDefault(); }
      else if (evt.key === 'Escape') { hide(); }
    });
    container.addEventListener('focus', () => { if (current < 0) show(n - 1); });
    container.addEventListener('blur', hide);
    charts.set(container, () => drawChart(container, opts));
  }

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const id of ['price-chart', 'equity-chart']) {
        const redraw = charts.get($(id));
        if (redraw && !results.hidden) redraw();
      }
    }, 150);
  });

  // ---------------------------------------------------------------- download
  $('download').addEventListener('click', () => {
    if (!lastResponse) return;
    const blob = new Blob([lastResponse.csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: 'backtest_' + lastResponse.params.short + '_' + lastResponse.params.long + '.csv' });
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  // ---------------------------------------------------------------- scan several files
  // POST /api/scan answers with exactly the object "--scan FOLDER --json" prints (no "ok" field);
  // errors are {ok: false, error} with a non-2xx status, like the backtest.
  function signed(v) {
    return v > 0 ? '+' + v : String(v);
  }
  function buildScanPayload(files, fields) {
    // files: [{name, text}]; fields: the raw control values ('' means "use the default")
    const payload = { files: Object.create(null) };
    if (!files.length) throw new Error('Pick one or more CSV files first.');
    for (const f of files) {
      if (Object.prototype.hasOwnProperty.call(payload.files, f.name)) {
        throw new Error('Two files are both named ' + f.name + '; pick files with different names.');
      }
      payload.files[f.name] = f.text;
    }
    for (const key of ['min_score', 'top', 'short', 'long', 'rsi_period']) {
      payload[key] = String(fields[key] === undefined || fields[key] === null ? '' : fields[key]).trim();
    }
    return payload;
  }
  function scanRowCells(row) {
    return [row.symbol, String(row.bars), signed(row.score), signed(row.parts.crossover),
      signed(row.parts.rsi), signed(row.parts.macd), signed(row.parts.bollinger)];
  }
  function scanSummaryText(data) {
    return '- ' + data.found + ' found, ' + data.scored + ' scored, ' + data.skipped.length +
      ' skipped, ' + data.shown + ' shown';
  }

  const scanForm = $('scan-form');
  const scanRunBtn = $('scan-run');
  const scanStatus = $('scan-status');
  const scanErrorEl = $('scan-error');
  const scanResults = $('scan-results');

  function showScanError(message) {
    scanErrorEl.textContent = message;
    scanErrorEl.hidden = false;
    scanStatus.textContent = '';
  }
  function readFileText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('Could not read ' + file.name + '.'));
      reader.readAsText(file);
    });
  }
  function renderScan(data) {
    $('scan-summary').textContent = scanSummaryText(data);
    const body = $('scan-table').tBodies[0];
    clear(body);
    for (const row of data.results) {
      const tr = el('tr');
      // value behind each cell, for the good/bad colour: none for symbol and bars
      const values = [null, null, row.score, row.parts.crossover, row.parts.rsi, row.parts.macd, row.parts.bollinger];
      scanRowCells(row).forEach((text, k) => {
        if (k === 0) { tr.appendChild(el('th', { scope: 'row' }, text)); return; }
        const v = values[k];
        tr.appendChild(el('td', { className: 'num' + (v > 0 ? ' good' : v < 0 ? ' bad' : '') }, text));
      });
      body.appendChild(tr);
    }
    const none = $('scan-none');
    none.hidden = data.results.length > 0;
    none.textContent = data.results.length ? '' : 'No file matched: no score at or above the minimum score.';
    const list = $('scan-skipped');
    clear(list);
    for (const item of data.skipped) list.appendChild(el('li', null, item.reason));
    $('scan-skipped-count').textContent = '(' + data.skipped.length + ')';
    $('scan-no-skipped').hidden = data.skipped.length > 0;
    scanResults.hidden = false;
  }

  scanForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    scanErrorEl.textContent = '';
    scanErrorEl.hidden = true;
    const picked = Array.from($('scan-files').files || []);
    let payload;
    try {
      let total = 0;
      for (const file of picked) total += file.size;
      if (total > limits.max_body_bytes) {
        throw new Error('The files add up to ' + total.toLocaleString() + ' bytes; the limit is ' +
          limits.max_body_bytes.toLocaleString() + ' bytes.');
      }
      const files = [];
      for (const file of picked) files.push({ name: file.name, text: await readFileText(file) });
      payload = buildScanPayload(files, {
        min_score: $('scan-min-score').value,
        top: $('scan-top').value,
        short: $('scan-short').value,
        long: $('scan-long').value,
        rsi_period: $('scan-rsi').value,
      });
    } catch (err) { showScanError(err.message); return; }
    scanRunBtn.disabled = true;
    scanStatus.textContent = 'Scanning...';
    const started = performance.now();
    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
      });
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok || !data || !Array.isArray(data.results)) {
        showScanError((data && data.error) ? data.error : ('Server answered ' + res.status + ' ' + res.statusText));
        return;
      }
      renderScan(data);
      scanStatus.textContent = 'Done in ' + Math.round(performance.now() - started) + ' ms.';
    } catch (err) {
      showScanError('Could not reach the server: ' + (err && err.message ? err.message : err) +
        '. Is "python -m trading_assistant.web" still running?');
    } finally {
      scanRunBtn.disabled = false;
    }
  });

  // ---------------------------------------------------------------- walk-forward test
  // POST /api/walkforward answers with exactly the object "python -m trading_assistant.walkforward --json"
  // prints (windows, summary, overfit_warning, disclaimer; no "ok" field); errors are {ok: false, error}
  // with a non-2xx status. The page computes nothing: it only formats those numbers the way the
  // command's text output does (format_walk_forward), so the two read the same.
  function fixed2(x) {
    // Python's f"{x:.2f}": the exact binary value rounded half to even, "-" kept for negatives (also -0.0)
    const negative = x < 0 || Object.is(x, -0);
    const a = Math.abs(x);
    if (!isFinite(a) || a >= 1e21) return (negative ? '-' : '') + String(a);
    const exact = a.toFixed(100);  // every digit of the binary value for any realistic percentage
    const dot = exact.indexOf('.');
    let whole = exact.slice(0, dot);
    let cents = exact.slice(dot + 1, dot + 3);
    const rest = exact.slice(dot + 3).replace(/0+$/, '');
    const last = Number(cents[1]);
    const up = rest > '5' || (rest === '5' && last % 2 === 1);
    if (up) {
      let n = BigInt(whole + cents) + 1n;
      const digits = n.toString().padStart(3, '0');
      whole = digits.slice(0, -2);
      cents = digits.slice(-2);
    }
    return (negative ? '-' : '') + whole + '.' + cents;
  }
  function pctText(x) {
    const t = fixed2(x);
    return (t[0] === '-' ? t : '+' + t) + '%';
  }
  function buildWfPayload(fields) {
    // fields: the raw control values ('' means "use the default", as for the other panels)
    const text = (v) => String(v === undefined || v === null ? '' : v).trim();
    const payload = { source: fields.source === 'csv' ? 'csv' : 'sample' };
    if (payload.source === 'sample') payload.sample = text(fields.source);
    for (const key of ['short', 'long', 'train', 'test', 'step', 'cash', 'fee', 'fee_pct']) {
      payload[key] = text(fields[key]);
    }
    if (payload.source === 'csv') {
      payload.csv = String(fields.csv || '');
      if (!payload.csv.trim()) throw new Error('Paste or upload a CSV first, or pick a sample series.');
      if (payload.csv.length > fields.maxBodyBytes) {
        throw new Error('The CSV is ' + payload.csv.length.toLocaleString() + ' characters; the limit is ' +
          fields.maxBodyBytes.toLocaleString() + '.');
      }
    }
    // Strategy: fields.strategy is the picked name; '' or sma_cross sends exactly the old request. Another strategy
    // sends no short or long (the command refuses them with it) but strategy, then grid and params made from
    // fields.params ({key: text}, one field per parameter): a text with a comma is a list, sent in grid
    // ("KEY=LIST"); one value that is not empty and not equal to fields.defaults[key] goes in params ("KEY=VALUE");
    // the rest keep their default. Anything that is not a number is sent as typed; the server answers with the
    // command's message.
    const wfStrategy = text(fields.strategy);
    if (wfStrategy !== '' && wfStrategy !== 'sma_cross') {
      delete payload.short;
      delete payload.long;
      payload.strategy = wfStrategy;
      const defaults = fields.defaults || {};
      const grid = [];
      const fixed = [];
      for (const key of Object.keys(fields.params || {})) {
        const value = text(fields.params[key]);
        if (value.includes(',')) grid.push(key + '=' + value);
        else if (value !== '' && Number(value) !== defaults[key]) fixed.push(key + '=' + value);
      }
      if (grid.length) payload.grid = grid;
      if (fixed.length) payload.params = fixed;
    }
    // Warm up: sent (as true) only when ticked, so an unticked box sends exactly the old request.
    if (fields.warmup === true) payload.warmup = true;
    return payload;
  }
  function wfNum(v) {
    // a parameter value as the command's Params cell writes it (walkforward.param_value_text): a whole value as a
    // whole number, anything else as Python prints it (shortest digits; exponent below 1e-4 and from 1e16 on)
    if (Number.isInteger(v) && Math.abs(v) < 1e16) return String(v === 0 ? 0 : v);
    const parts = v.toExponential().split('e');
    const exp = Number(parts[1]);
    if (exp < -4 || exp >= 16) return parts[0] + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0');
    return String(v);
  }
  function wfRowCells(w) {
    // a row with "params" (a reply with "strategy") shows every parameter in the Params column, as the command does
    return [String(w.window), w.train_start + '-' + (w.train_end - 1), w.test_start + '-' + (w.test_end - 1),
      w.params ? Object.keys(w.params).map((k) => k + '=' + wfNum(w.params[k])).join(',') : w.short + '/' + w.long,
      pctText(w.train_return_pct), pctText(w.test_return_pct),
      pctText(w.buy_hold_return_pct), String(w.test_trades)];
  }
  function wfCountText(n) {
    return '(' + n + (n === 1 ? ' window)' : ' windows)');
  }
  function wfSummaryRows(s) {
    return [
      ['Test return, compounded over the windows', pctText(s.compound_test_return_pct)],
      ['Buy & hold, compounded over the windows', pctText(s.compound_buy_hold_return_pct)],
      ['Mean test return per window', pctText(s.mean_test_return_pct)],
      ['Windows beating buy & hold', s.windows_beating_buy_hold + ' of ' + s.windows],
      ['Windows without test trades', s.windows_without_trades + ' of ' + s.windows],
    ];
  }
  function wfWarmupLine(n, strategy) {
    // the command's header line with --warmup (format_walk_forward, HEADER_RUN_WARMUP), word for word
    if (strategy) {
      // with the reply's "strategy": HEADER_RUN_WARMUP_STRATEGY
      return 'Walk-forward: ' + n + (n === 1 ? ' window' : ' windows') + '; each ' + strategy + ' parameter set was' +
        ' chosen on its train bars only, then traded and scored on the test bars after them, with its signal' +
        ' warmed up on the bars just before each test block, so that it can signal on the first test bar';
    }
    return 'Walk-forward: ' + n + (n === 1 ? ' window' : ' windows') + '; each SMA crossover pair was chosen on' +
      ' its train bars only, then traded and scored on the test bars after them, with its moving averages' +
      ' warmed up on up to long bars just before each test block';
  }
  function wfNotes(s, warmup, strategy) {
    // the same notes, in the same order, as the command's text output; warmup: the reply had "warmup": true;
    // strategy: the reply's "strategy" (NO_TRADES_REASON_STRATEGY, NO_TRADES_REASON_WARMUP_STRATEGY)
    const notes = [];
    if (!s.test_blocks_contiguous) {
      notes.push('Note: the test blocks overlap or leave gaps (step is not equal to test), so the compounded' +
        ' figures do not describe one continuous stretch of prices.');
    }
    if (s.windows_without_trades && strategy) {
      notes.push('Note: ' + s.windows_without_trades + ' of ' + s.windows + ' windows made no trades in the test' +
        ' block (no BUY signal on a test bar before its last, or' + (warmup === true
          ? ', near the start of the data, too few bars before the block to warm up'
          : ' too few test bars for a first signal') + '); their 0.00% says nothing about the parameters.');
    } else if (s.windows_without_trades) {
      notes.push('Note: ' + s.windows_without_trades + ' of ' + s.windows + ' windows made no trades in the test' +
        ' block (' + (warmup === true
          ? 'no BUY crossover on a test bar before its last, or, near the start of the data, fewer than long bars' +
            ' before the block to warm up'
          : 'no crossover, or fewer than long + 2 test bars to warm up') +
        '); their 0.00% says nothing about the pair.');
    }
    return notes;
  }

  const wfForm = $('wf-form');
  const wfSourceSel = $('wf-source');
  const wfCsvArea = $('wf-csv');
  const wfFileInput = $('wf-file');
  const wfRunBtn = $('wf-run');
  const wfStatus = $('wf-status');
  const wfErrorEl = $('wf-error');
  const wfResults = $('wf-results');

  // Strategy picker: filled by loadSamples from the list the backtest and portfolio panels use. sma_cross (or an
  // empty list) shows the short and long window lists; another strategy hides them and shows one text field per
  // parameter holding its default, which takes one value or a comma list.
  let wfParamInputs = {};
  function wfCurrentStrategy() { return strategies.find((st) => st.name === wfStrategySel.value); }
  function updateWfStrategyUi() {
    const info = wfCurrentStrategy();
    const box = $('wf-strategy-params');
    clear(box);
    wfParamInputs = {};
    $('wf-strategy-hint').textContent = info ? info.description + '.' : '';
    const isSma = !info || info.name === 'sma_cross';
    $('wf-strategy-params-block').hidden = isSma;
    $('wf-short-field').hidden = !isSma;
    $('wf-long-field').hidden = !isSma;
    if (isSma) return;
    for (const key of Object.keys(info.params)) {
      const id = 'wf-param-' + key;
      const field = el('div', { className: 'field' });
      field.appendChild(el('label', { for: id }, key));
      wfParamInputs[key] = field.appendChild(el('input', { id: id, type: 'text', spellcheck: 'false', value: String(info.params[key]) }));
      box.appendChild(field);
    }
  }
  wfStrategySel.addEventListener('change', updateWfStrategyUi);

  function showWfError(message) {
    wfErrorEl.textContent = message;
    wfErrorEl.hidden = false;
    wfStatus.textContent = '';
  }
  function clearWfError() { wfErrorEl.textContent = ''; wfErrorEl.hidden = true; }
  function updateWfSourceUi() {
    const isCsv = wfSourceSel.value === 'csv';
    $('wf-csv-block').hidden = !isCsv;
    const info = samples.find((s) => s.name === wfSourceSel.value);
    $('wf-source-hint').textContent = isCsv
      ? 'Paste CSV text or upload a file. Limits: ' + limits.max_bars.toLocaleString() + ' rows, ' +
        Math.floor(limits.max_body_bytes / 1000).toLocaleString() + ' kB.'
      : (info ? info.description + '.' : '');
  }
  wfSourceSel.addEventListener('change', updateWfSourceUi);

  wfFileInput.addEventListener('change', () => {
    const file = wfFileInput.files && wfFileInput.files[0];
    if (!file) return;
    if (file.size > limits.max_body_bytes) {
      showWfError('That file is ' + file.size.toLocaleString() + ' bytes; the limit is ' +
        limits.max_body_bytes.toLocaleString() + ' bytes.');
      wfFileInput.value = '';
      return;
    }
    readFileText(file).then((text) => {
      wfCsvArea.value = text;
      $('wf-csv-hint').textContent = 'Loaded ' + file.name + ' (' + file.size.toLocaleString() + ' bytes).';
      clearWfError();
    }, (err) => showWfError(err.message));
  });

  function renderWf(data) {
    // Warm up: only a reply with "warmup": true gets the header line and the warm-up note wording; any other
    // reply leaves the line hidden and empty, so the panel shows exactly what it did before.
    const warmup = data.warmup === true;
    // Strategy: a reply with "strategy" (a name) gets the Params column header, its cells and that strategy's
    // header line and notes; any other reply is shown exactly as before.
    const wfStrategyName = typeof data.strategy === 'string' ? data.strategy : null;
    const wfHead = $('wf-table').tHead;
    if (wfHead && wfHead.rows.length) wfHead.rows[0].cells[3].textContent = wfStrategyName ? 'Params' : 'Pair';
    $('wf-warmup-line').textContent = warmup ? wfWarmupLine(data.summary.windows, wfStrategyName) : '';
    $('wf-warmup-line').hidden = !warmup;
    $('wf-count').textContent = wfCountText(data.windows.length);
    const body = $('wf-table').tBodies[0];
    clear(body);
    for (const w of data.windows) {
      const tr = el('tr');
      // value behind each cell, for the good/bad colour: none for the window, ranges, pair and trades
      const values = [null, null, null, null, w.train_return_pct, w.test_return_pct, w.buy_hold_return_pct, null];
      wfRowCells(w).forEach((text, k) => {
        if (k === 0) { tr.appendChild(el('th', { scope: 'row' }, text)); return; }
        const v = values[k];
        const numeric = k >= 4;
        tr.appendChild(el('td', { className: (numeric ? 'num' : '') + (v > 0 ? ' good' : v < 0 ? ' bad' : '') }, text));
      });
      body.appendChild(tr);
    }
    const summaryBody = $('wf-summary-table').tBodies[0];
    clear(summaryBody);
    for (const [label, value] of wfSummaryRows(data.summary)) {
      const tr = el('tr');
      tr.appendChild(el('th', { scope: 'row' }, label));
      tr.appendChild(el('td', { className: 'num' }, value));
      summaryBody.appendChild(tr);
    }
    const notes = $('wf-notes');
    clear(notes);
    for (const note of wfNotes(data.summary, warmup, wfStrategyName)) notes.appendChild(el('li', null, note));
    $('wf-overfit').textContent = data.overfit_warning;
    $('wf-disclaimer').textContent = data.disclaimer;
    wfResults.hidden = false;
  }

  wfForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearWfError();
    let payload;
    try {
      payload = buildWfPayload({
        source: wfSourceSel.value,
        csv: wfCsvArea.value,
        short: $('wf-short').value,
        long: $('wf-long').value,
        train: $('wf-train').value,
        test: $('wf-test').value,
        step: $('wf-step').value,
        cash: $('wf-cash').value,
        fee: $('wf-fee').value,
        fee_pct: $('wf-fee-pct').value,
        warmup: $('wf-warmup').checked === true,
        strategy: wfStrategySel.value,
        params: Object.fromEntries(Object.entries(wfParamInputs).map(([key, input]) => [key, input.value])),
        defaults: (wfCurrentStrategy() || {}).params,
        maxBodyBytes: limits.max_body_bytes,
      });
    } catch (err) { showWfError(err.message); return; }
    wfRunBtn.disabled = true;
    wfStatus.textContent = 'Running...';
    const started = performance.now();
    try {
      const res = await fetch('/api/walkforward', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
      });
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok || !data || !Array.isArray(data.windows)) {
        showWfError((data && data.error) ? data.error : ('Server answered ' + res.status + ' ' + res.statusText));
        return;
      }
      renderWf(data);
      wfStatus.textContent = 'Done in ' + Math.round(performance.now() - started) + ' ms.';
    } catch (err) {
      showWfError('Could not reach the server: ' + (err && err.message ? err.message : err) +
        '. Is "python -m trading_assistant.web" still running?');
    } finally {
      wfRunBtn.disabled = false;
    }
  });

  // ---------------------------------------------------------------- portfolio backtest
  // POST /api/portfolio answers with exactly the object "python -m trading_assistant.portfolio FOLDER --json"
  // prints (summary, skipped, disclaimer; no "ok" field); errors are {ok: false, error} with a non-2xx
  // status. The page computes nothing: it formats those numbers the way the command's text output does
  // (portfolio.format_portfolio), digit for digit, so the two read the same.
  function pfFixed2(x) {
    // Python's f"{x:.2f}" for any size: fixed2, and from 1e21 up (always whole numbers) every digit via BigInt
    const a = Math.abs(x);
    if (isFinite(a) && a >= 1e21) return ((x < 0 || Object.is(x, -0)) ? '-' : '') + BigInt(a).toString() + '.00';
    return fixed2(x);
  }
  function pfPct(x) {
    // portfolio._pct: f"{x:+.2f}%", but a value that rounds to zero is "+0.00%", never "-0.00%"
    const t = pfFixed2(x);
    const signed = t[0] === '-' ? t : '+' + t;
    return (signed === '-0.00' ? '+0.00' : signed) + '%';
  }
  function pfMoney(x) {
    // Python's f"{x:,.2f}": the whole part grouped by commas
    const t = pfFixed2(x);
    const negative = t[0] === '-';
    const [whole, cents] = (negative ? t.slice(1) : t).split('.');
    return (negative ? '-' : '') + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + cents;
  }
  function pyRepr(x) {
    // Python's repr(float): the shortest digits that read back as x (as JavaScript's), laid out Python's way
    if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
    if (!isFinite(x)) return isNaN(x) ? 'nan' : (x > 0 ? 'inf' : '-inf');
    const [mantissa, power] = Math.abs(x).toExponential().split('e');
    const digits = mantissa.replace('.', '');
    const exp = Number(power);
    const point = exp + 1;  // digits[0..point) are the whole part
    let text;
    if (point > -4 && point <= 16) {
      if (point <= 0) text = '0.' + '0'.repeat(-point) + digits;
      else if (point >= digits.length) text = digits + '0'.repeat(point - digits.length) + '.0';
      else text = digits.slice(0, point) + '.' + digits.slice(point);
    } else {
      text = digits[0] + (digits.length > 1 ? '.' + digits.slice(1) : '') + 'e' + (exp < 0 ? '-' : '+') +
        String(Math.abs(exp)).padStart(2, '0');
    }
    return (x < 0 ? '-' : '') + text;
  }
  function pfWeightText(x) {
    // portfolio._weight_text: 70.0 -> "70%", 33.5 -> "33.5%"
    const t = pyRepr(x);
    return (t.endsWith('.0') ? t.slice(0, -2) : t) + '%';
  }
  function pfTitle(s) {
    const n = s.symbols.length;
    const split = s.weights
      ? 'cash split by weight (' + Object.keys(s.weights).map((k) => k + ' ' + pfWeightText(s.weights[k])).join(', ') + ')'
      : 'cash split equally';
    return 'Portfolio: ' + n + ' symbol' + (n === 1 ? '' : 's') + ', ' + split + ', SMA ' + s.short + '/' + s.long +
      ' crossover, fee ' + pfMoney(s.fee) + ' + ' + pfFixed2(s.fee_pct) + '%, on the dates every file shares';
  }
  function pfSummaryRows(s) {
    return [
      ['Dates', s.start_date + ' to ' + s.end_date + ' (' + s.shared_dates + ' shared dates)'],
      ['Cash', pfMoney(s.initial_cash)],
      ['Final equity', pfMoney(s.final_equity)],
      ['Return', pfPct(s.return_pct)],
      ['Max drawdown', pfPct(s.max_drawdown_pct)],
      ['Buy & hold (' + (s.weights ? 'same weights' : 'equal weight') + ')', pfPct(s.buy_hold_return_pct)],
    ];
  }
  function pfRowCells(row, weights) {
    return [row.symbol].concat(weights ? [pfWeightText(weights[row.symbol])] : [],
      [String(row.bars_used), String(row.bars_lost), pfPct(row.return_pct), String(row.trades),
        pfPct(row.buy_hold_return_pct)]);
  }
  function pfWorstText(s) {
    const w = s.worst_symbol_drawdown;
    return 'Worst single-symbol drawdown: ' + pfPct(w.max_drawdown_pct) + ' (' + w.symbol + ')';
  }
  function pfNote(s) {
    return s.symbols.some((row) => row.bars_lost)
      ? 'Note: dates not shared by every file were dropped (see Bars lost); nothing was filled in.'
      : '';
  }
  function buildPfPayload(files, fields) {
    // files: [{name, text}]; fields: the raw control values ('' means "use the command's default").
    // Weights: "A=70 B=30" (spaces around "=" and commas are fine); empty means an equal split.
    // Strategy: fields.strategy is the picked name; '' or sma_cross sends exactly the old request. Another
    // strategy sends no short or long (the command refuses them with it) but strategy and params, the
    // "KEY=VALUE" texts of fields.params ({key: text}) that are not empty and not equal to fields.defaults[key]
    // ({key: number}): those are left to the default, so the title names them as the command does without
    // --param (threshold=0.0, not threshold=0). Anything that is not a number is sent as typed; the server
    // answers with the command's message.
    const text = (v) => String(v === undefined || v === null ? '' : v).trim();
    const payload = { files: Object.create(null) };
    if (!files.length) throw new Error('Pick two or more CSV files first.');
    for (const f of files) {
      if (Object.prototype.hasOwnProperty.call(payload.files, f.name)) {
        throw new Error('Two files are both named ' + f.name + '; pick files with different names.');
      }
      payload.files[f.name] = f.text;
    }
    const strategy = text(fields.strategy);
    const other = strategy !== '' && strategy !== 'sma_cross';
    for (const key of ['short', 'long', 'cash', 'fee', 'fee_pct']) {
      if (!(other && (key === 'short' || key === 'long'))) payload[key] = text(fields[key]);
    }
    const weights = text(fields.weights);
    if (weights) payload.weights = weights.replace(/\s*=\s*/g, '=').split(/[\s,]+/).filter(Boolean);
    if (other) {
      const defaults = fields.defaults || {};
      payload.strategy = strategy;
      payload.params = [];
      for (const key of Object.keys(fields.params || {})) {
        const value = text(fields.params[key]);
        if (value !== '' && Number(value) !== defaults[key]) payload.params.push(key + '=' + value);
      }
    }
    return payload;
  }

  const pfForm = $('pf-form');
  const pfRunBtn = $('pf-run');
  const pfStatus = $('pf-status');
  const pfErrorEl = $('pf-error');
  const pfResults = $('pf-results');

  // Strategy picker: filled by loadSamples from the list the backtest panel uses. sma_cross (or an empty list)
  // shows Short SMA and Long SMA; another strategy hides them and shows one field per parameter, holding its
  // default, like the backtest panel's.
  let pfParamInputs = {};
  function pfCurrentStrategy() { return strategies.find((st) => st.name === pfStrategySel.value); }
  function updatePfStrategyUi() {
    const info = pfCurrentStrategy();
    const box = $('pf-strategy-params');
    clear(box);
    pfParamInputs = {};
    $('pf-strategy-hint').textContent = info ? info.description + '.' : '';
    const isSma = !info || info.name === 'sma_cross';
    $('pf-strategy-params-block').hidden = isSma;
    $('pf-short-field').hidden = !isSma;
    $('pf-long-field').hidden = !isSma;
    if (isSma) return;
    for (const key of Object.keys(info.params)) {
      const id = 'pf-param-' + key;
      const field = el('div', { className: 'field' });
      field.appendChild(el('label', { for: id }, key));
      pfParamInputs[key] = field.appendChild(el('input', { id: id, type: 'number', step: 'any', value: String(info.params[key]) }));
      box.appendChild(field);
    }
  }
  pfStrategySel.addEventListener('change', updatePfStrategyUi);

  function showPfError(message) {
    pfErrorEl.textContent = message;
    pfErrorEl.hidden = false;
    pfStatus.textContent = '';
  }
  function renderPf(data) {
    const s = data.summary;
    const weights = s.weights || null;
    // A reply for a strategy other than sma_cross carries the command's own title line; otherwise the page
    // builds the same line itself.
    $('pf-title').textContent = typeof data.title === 'string' ? data.title : pfTitle(s);
    const summaryBody = $('pf-summary-table').tBodies[0];
    clear(summaryBody);
    const tones = [null, null, null, s.return_pct, s.max_drawdown_pct, s.buy_hold_return_pct];
    pfSummaryRows(s).forEach(([label, value], k) => {
      const v = tones[k];
      const tr = el('tr');
      tr.appendChild(el('th', { scope: 'row' }, label));
      tr.appendChild(el('td', { className: 'num' + (v > 0 ? ' good' : v < 0 ? ' bad' : '') }, value));
      summaryBody.appendChild(tr);
    });
    $('pf-weight-col').hidden = !weights;
    const body = $('pf-table').tBodies[0];
    clear(body);
    for (const row of s.symbols) {
      const tr = el('tr');
      const values = [null].concat(weights ? [null] : [], [null, null, row.return_pct, null, row.buy_hold_return_pct]);
      pfRowCells(row, weights).forEach((text, k) => {
        if (k === 0) { tr.appendChild(el('th', { scope: 'row' }, text)); return; }
        const v = values[k];
        tr.appendChild(el('td', { className: 'num' + (v > 0 ? ' good' : v < 0 ? ' bad' : '') }, text));
      });
      body.appendChild(tr);
    }
    $('pf-worst').textContent = pfWorstText(s);
    const note = pfNote(s);
    $('pf-note').textContent = note;
    $('pf-note').hidden = !note;
    const list = $('pf-skipped');
    clear(list);
    for (const item of data.skipped) list.appendChild(el('li', null, item.reason));
    $('pf-skipped-count').textContent = '(' + data.skipped.length + ')';
    $('pf-no-skipped').hidden = data.skipped.length > 0;
    $('pf-disclaimer').textContent = data.disclaimer;
    pfResults.hidden = false;
  }

  pfForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    pfErrorEl.textContent = '';
    pfErrorEl.hidden = true;
    const picked = Array.from($('pf-files').files || []);
    let payload;
    try {
      let total = 0;
      for (const file of picked) total += file.size;
      if (total > limits.max_body_bytes) {
        throw new Error('The files add up to ' + total.toLocaleString() + ' bytes; the limit is ' +
          limits.max_body_bytes.toLocaleString() + ' bytes.');
      }
      const files = [];
      for (const file of picked) files.push({ name: file.name, text: await readFileText(file) });
      payload = buildPfPayload(files, {
        short: $('pf-short').value,
        long: $('pf-long').value,
        cash: $('pf-cash').value,
        fee: $('pf-fee').value,
        fee_pct: $('pf-fee-pct').value,
        weights: $('pf-weights').value,
        strategy: pfStrategySel.value,
        params: Object.fromEntries(Object.entries(pfParamInputs).map(([key, input]) => [key, input.value])),
        defaults: (pfCurrentStrategy() || {}).params,
      });
    } catch (err) { showPfError(err.message); return; }
    pfRunBtn.disabled = true;
    pfStatus.textContent = 'Running...';
    const started = performance.now();
    try {
      const res = await fetch('/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
      });
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok || !data || !data.summary || !Array.isArray(data.skipped)) {
        showPfError((data && data.error) ? data.error : ('Server answered ' + res.status + ' ' + res.statusText));
        return;
      }
      renderPf(data);
      pfStatus.textContent = 'Done in ' + Math.round(performance.now() - started) + ' ms.';
    } catch (err) {
      showPfError('Could not reach the server: ' + (err && err.message ? err.message : err) +
        '. Is "python -m trading_assistant.web" still running?');
    } finally {
      pfRunBtn.disabled = false;
    }
  });

  loadSamples();
})();
"""
