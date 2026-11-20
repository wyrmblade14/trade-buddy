"""The "Trailing stop %" control of the backtest panel on the web page.

Static checks on the HTML and script, plus the shipped APP_JS run for real in
Node against a real local server with a small stand-in for the browser DOM (the
same approach as test_web_walkforward_page.py; no browser is needed). The page
computes nothing itself: the trades table shows the reply of the same
``cli.analyse`` the command line uses.

8-bar candle CSV (see test_cli_trailing_stop.py), cash 500, short 1, long 2, trail 10 %:
BUY 45 @ 11 on bar 4; bar 6 level 13 * 0.9 = 11.7 -> SELL 45 @ 11.70, reason trail, end equity 531.50.
"""

import hashlib
import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.samples import write_sample_csv
from trading_assistant.web import server as web
from test_web_walkforward_warmup_page import FIELD_HTML as WARMUP_FIELD_HTML, JS_CHANGES as WARMUP_JS_CHANGES, LINE_HTML as WARMUP_LINE_HTML
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")

CANDLES = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.5,9.5,8.5,9,1000
2026-01-03,8.5,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,11.5,13,11.2,12,1000
2026-01-07,12.0,12.5,10.0,10,1000
2026-01-08,9,9,7.5,8,1000
"""
CLOSES_ONLY = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
C8 = {"source": "csv", "csv": CANDLES, "short": "1", "long": "2", "cash": "500"}

# sha256 of the page before the trailing stop control was added.
OLD_SHA256 = {
    "INDEX_HTML": "82c3c3887b37e9011014adc9f35b6f35d6930eb5b2e5ffd6f513c2c9fe6e074a",
    "APP_JS": "d0c0847b132278ca74a6824e6afd5ddee4426d22e8591d77c3a8ab6ff2749260",
    "STYLE_CSS": "65885973a502760713898a2f6d6a5da42f55927ab38abedcf9daf901d6738550",
}
FIELD_HTML = """    <div class="field">
      <label for="trailing_stop">Trailing stop %</label>
      <input id="trailing_stop" name="trailing_stop" type="number" inputmode="decimal" min="0" max="99.99" step="any" placeholder="Optional">
    </div>
"""
SEND_JS = """    // trailing_stop is sent only when it has a value, so a request without it is exactly the old one
    // (like the others, it is disabled and blanked without candle data)
    const trailingStop = $('trailing_stop').disabled ? '' : $('trailing_stop').value.trim();
    if (trailingStop !== '') payload.trailing_stop = trailingStop;
"""


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# --------------------------------------------------------------------------- static page


def test_field_sits_after_take_profit_in_the_stop_loss_style():
    stop = re.search(r'<input id="stop_loss"[^>]*>', INDEX_HTML).group(0)
    trail = re.search(r'<input id="trailing_stop"[^>]*>', INDEX_HTML).group(0)
    assert trail == stop.replace("stop_loss", "trailing_stop")  # same type, range, step and "Optional"
    assert '<label for="trailing_stop">Trailing stop %</label>' in INDEX_HTML
    assert "disabled" not in trail and "value=" not in trail  # empty by default: not used
    order = [INDEX_HTML.index(s) for s in ('id="stop_loss"', 'id="take_profit"', 'id="trailing_stop"', 'id="candle-hint"')]
    assert order == sorted(order)
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))


def test_candle_only_like_stop_loss_and_hint_names_it():
    assert "const CANDLE_CONTROLS = ['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown', 'scale_out'];" in APP_JS
    assert "Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need open/high/low columns" in INDEX_HTML
    assert "t.reason || '-'" in APP_JS  # the trades table shows any reason, trail included


def test_nothing_else_on_the_page_changed():
    old_html = INDEX_HTML.replace(FIELD_HTML, "", 1).replace(
        "Fill price, stop loss, take profit, trailing stop and risk sizing need", "Fill price, stop loss and take profit need", 1)
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="risk_pct">Risk % per buy</label>\n'
        '      <input id="risk_pct" name="risk_pct" type="number" inputmode="decimal" min="0" max="100" step="any" placeholder="Optional">\n'
        '    </div>\n    <div class="field">\n      <label for="atr_mult">ATR multiplier</label>\n'
        '      <input id="atr_mult" name="atr_mult" type="number" inputmode="decimal" min="0" step="any" placeholder="2 (default)">\n'
        '    </div>\n    <div class="field">\n      <label for="atr_period">ATR period</label>\n'
        '      <input id="atr_period" name="atr_period" type="number" inputmode="numeric" min="1" step="1" placeholder="14 (default)">\n'
        '    </div>\n', "", 1)
    old_js = (
        APP_JS.replace(SEND_JS, "", 1)
        .replace(
            "    // risk sizing: sent only when Risk % has a value, and the ATR fields only count (and are only sent)\n"
            "    // together with it, so a request without it is exactly the old one; disabled and blanked without\n"
            "    // candle data like the stops\n"
            "    const riskPct = $('risk_pct').disabled ? '' : $('risk_pct').value.trim();\n"
            "    if (riskPct !== '') {\n"
            "      payload.risk_pct = riskPct;\n"
            "      const atrMult = $('atr_mult').value.trim();\n"
            "      const atrPeriod = $('atr_period').value.trim();\n"
            "      if (atrMult !== '') payload.atr_mult = atrMult;\n"
            "      if (atrPeriod !== '') payload.atr_period = atrPeriod;\n"
            "    }\n", "", 1)
        .replace("  // fill=open, stop loss, take profit and trailing stop need candle data",
                 "  // fill=open, stop loss and take profit need candle data", 1)
        .replace("['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'risk_pct', 'atr_mult', 'atr_period']",
                 "['fill', 'stop_loss', 'take_profit']", 1)
    )
    # Undo the walk-forward panel's strategy picker (added after this test was written). First, before the
    # older undo steps below, whose patterns would otherwise also match its code.
    old_html = old_html.replace("SMA crossover pair (or the parameter set of the strategy you pick) with", "SMA crossover pair with", 1)
    old_html = re.sub(r'      <div class="field span2">\n        <label for="wf-strategy">.*?id="wf-strategy-params"></div>\n      </div>\n', "", old_html, count=1, flags=re.S)
    old_html = old_html.replace('<div class="field" id="wf-short-field">', '<div class="field">', 1).replace('<div class="field" id="wf-long-field">', '<div class="field">', 1)
    old_js = old_js.replace("  const wfStrategySel = $('wf-strategy');\n", "", 1)
    old_js = re.sub(r"    clear\(wfStrategySel\);\n.*?    updateWfStrategyUi\(\);\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    // Strategy: fields\.strategy is the picked name; '' or sma_cross sends exactly the old request\. Another strategy\n.*?      if \(fixed\.length\) payload\.params = fixed;\n    }\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"  function wfNum\(v\) \{\n.*?\n  }\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace("    // a row with \"params\" (a reply with \"strategy\") shows every parameter in the Params column, as the command does\n", "", 1)
    old_js = old_js.replace("      w.params ? Object.keys(w.params).map((k) => k + '=' + wfNum(w.params[k])).join(',') : w.short + '/' + w.long,\n      pctText(w.train_return_pct),", "      w.short + '/' + w.long, pctText(w.train_return_pct),", 1)
    old_js = old_js.replace("  function wfWarmupLine(n, strategy) {", "  function wfWarmupLine(n) {", 1)
    old_js = re.sub(r"    if \(strategy\) \{\n      // with the reply's \"strategy\": HEADER_RUN_WARMUP_STRATEGY\n.*?\n    }\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace("  function wfNotes(s, warmup, strategy) {\n    // the same notes, in the same order, as the command's text output; warmup: the reply had \"warmup\": true;\n    // strategy: the reply's \"strategy\" (NO_TRADES_REASON_STRATEGY, NO_TRADES_REASON_WARMUP_STRATEGY)\n",
                            "  function wfNotes(s, warmup) {\n    // the same notes, in the same order, as the command's text output; warmup: the reply had \"warmup\": true\n", 1)
    old_js = re.sub(r"    if \(s\.windows_without_trades && strategy\) \{\n.*?    } else if \(s\.windows_without_trades\) \{\n", "    if (s.windows_without_trades) {\n", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    // Strategy: a reply with \"strategy\" \(a name\).*?'Params' : 'Pair';\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace("wfWarmupLine(data.summary.windows, wfStrategyName)", "wfWarmupLine(data.summary.windows)", 1).replace("wfNotes(data.summary, warmup, wfStrategyName)", "wfNotes(data.summary, warmup)", 1)
    old_js = re.sub(r"        strategy: wfStrategySel\.value,\n.*?        defaults: \(wfCurrentStrategy\(\) \|\| \{\}\)\.params,\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"  // Strategy picker: filled by loadSamples from the list the backtest and portfolio panels use\..*?wfStrategySel\.addEventListener\('change', updateWfStrategyUi\);\n\n", "", old_js, count=1, flags=re.S)
    # Undo the add-on fields (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="add_on">.*?<label for="max_adds">.*?</div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // add-on and max adds: .*?payload\.max_adds = maxAdds;\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace("      (s.add_on_buys === undefined ? '' : ', ' + s.add_on_buys + ' add-on buys, ' + s.add_on_skipped_buys + ' add-ons skipped') +\n", "", 1)
    # Undo the scale-out field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="scale_out">Scale out (%)</label>\n'
        '      <input id="scale_out" name="scale_out" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">\n'
        '      <span class="hint" id="scale-out-hint">Once a later bar\'s high is this % above the entry price, sell half the shares held (rounded down), once per position; the rest stays open.</span>\n'
        '    </div>\n', "", 1).replace(" The scale-out needs them too.", "", 1)
    old_js = old_js.replace(
        "    // scale-out: sent only when filled in, so an empty field sends exactly the old request; the server checks it\n"
        "    // (above 0, a finite number) and its message is shown as for the other fields. It needs candle data like the\n"
        "    // stops, so it is in CANDLE_CONTROLS: disabled and blanked without it.\n"
        "    const scaleOut = $('scale_out').disabled ? '' : $('scale_out').value.trim();\n"
        "    if (scaleOut !== '') payload.scale_out = scaleOut;\n", "", 1)
    old_js = old_js.replace(
        "      (s.scale_out_exits === undefined ? '' : ', ' + s.scale_out_exits + ' partial sells by scale-out') +\n", "", 1)
    old_js = old_js.replace(", 'cooldown', 'scale_out']", ", 'cooldown']", 1)
    # Undo the max losses field (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="max_losses">.*?</div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // max losses: .*?payload\.max_losses = maxLosses;\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace(" +\n      (s.loss_skipped_buys === undefined ? '' : ', ' + s.loss_skipped_buys + ' buys skipped by losing streak')", "", 1)
    # Undo the breakeven field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="breakeven">Breakeven (%)</label>\n'
        '      <input id="breakeven" name="breakeven" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">\n'
        '      <span class="hint" id="breakeven-hint">Once a later bar\'s high is this % above the entry price, sell at the entry price if the price falls back to it.</span>\n'
        '    </div>\n', "", 1).replace("stop, breakeven, risk", "stop, risk", 1)
    old_js = old_js.replace(
        "    // breakeven: sent only when filled in (empty: the old request); a stop, so blanked without candle data\n"
        "    const breakeven = $('breakeven').disabled ? '' : $('breakeven').value.trim();\n"
        "    if (breakeven !== '') payload.breakeven = breakeven;\n", "", 1).replace("'breakeven', ", "", 1).replace(
        "      (s.breakeven_exits === undefined ? '' : ', ' + s.breakeven_exits + ' sold at breakeven') +\n", "", 1)
    # Undo the max drawdown field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="max_drawdown">Max drawdown (%)</label>\n'
        '      <input id="max_drawdown" name="max_drawdown" type="number" inputmode="decimal" min="0" max="99.99" step="any" placeholder="Optional">\n'
        '      <span class="hint" id="max-drawdown-hint">When the account value at a close is this % or more below its peak, sell the position on the next bar and buy nothing more. Needs no stop; works with a close-only CSV.</span>\n'
        '    </div>\n', "", 1)
    old_js = old_js.replace(
        "    // max drawdown: sent only when filled in, so an empty field sends exactly the old request; the server checks\n"
        "    // it (above 0 and below 100) and its message is shown as for the other fields. Like max hold it needs no\n"
        "    // candle data, so it is not in CANDLE_CONTROLS: never greyed out or blanked.\n"
        "    const maxDrawdown = $('max_drawdown').value.trim();\n"
        "    if (maxDrawdown !== '') payload.max_drawdown = maxDrawdown;\n", "", 1)
    old_js = old_js.replace(" +\n      (s.drawdown_skipped_buys === undefined ? '' : ', ' + s.drawdown_skipped_buys + ' skipped by drawdown')", "", 1)
    # Undo the min hold field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="min_hold">Min hold (bars)</label>\n'
        '      <input id="min_hold" name="min_hold" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">\n'
        '      <span class="hint" id="min-hold-hint">Skip a signal sell until the position has been held this many bars since the buy that opened it; the other exits still sell. Needs no stop; works with a close-only CSV.</span>\n'
        '    </div>\n', "", 1)
    old_js = old_js.replace(
        "    // min hold: sent only when filled in, so an empty field sends exactly the old request; the server checks\n"
        "    // it (a whole number of at least 1) and its message is shown as for the other fields. Like max hold it needs\n"
        "    // no candle data, so it is not in CANDLE_CONTROLS: never greyed out or blanked.\n"
        "    const minHold = $('min_hold').value.trim();\n"
        "    if (minHold !== '') payload.min_hold = minHold;\n", "", 1)
    old_js = old_js.replace(" +\n      (s.min_hold_skipped_sells === undefined ? '' : ', ' + s.min_hold_skipped_sells + ' signal sells skipped by min hold')", "", 1)
    # Undo the max hold field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="max_hold">Max hold (bars)</label>\n'
        '      <input id="max_hold" name="max_hold" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">\n'
        '      <span class="hint" id="max-hold-hint">Sell a position this many bars after the buy that opened it, at that bar\'s fill price. Needs no stop; works with a close-only CSV.</span>\n'
        '    </div>\n', "", 1)
    old_js = old_js.replace(
        "    // max hold: sent only when filled in, so an empty field sends exactly the old request; the server checks\n"
        "    // it (a whole number of at least 1) and its message is shown as for the other fields. It needs no candle\n"
        "    // data, so unlike the stops it is not in CANDLE_CONTROLS: never greyed out or blanked.\n"
        "    const maxHold = $('max_hold').value.trim();\n"
        "    if (maxHold !== '') payload.max_hold = maxHold;\n", "", 1)
    old_js = old_js.replace(" +\n      (s.time_exits === undefined ? '' : ', ' + s.time_exits + ' sold by max hold')", "", 1)
    # Undo the cooldown field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="cooldown">Cooldown (bars)</label>\n'
        '      <input id="cooldown" name="cooldown" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">\n'
        '      <span class="hint" id="cooldown-hint">After a sell by the stop loss, trailing stop or ATR stop, no buy for this many bars. Needs one of them.</span>\n'
        '    </div>\n', "", 1).replace(
        "risk sizing, the ATR stop and the cooldown need", "risk sizing and the ATR stop need", 1)
    old_js = (
        old_js.replace(
            "    // cooldown: sent only when filled in, so an empty field sends exactly the old request; the server checks\n"
            "    // it (a stop must be on, a whole number of at least 1) and its message is shown as for the other fields.\n"
            "    // Disabled and blanked without candle data like the stops.\n"
            "    const cooldown = $('cooldown').disabled ? '' : $('cooldown').value.trim();\n"
            "    if (cooldown !== '') payload.cooldown = cooldown;\n", "", 1)
        .replace(", 'atr_stop', 'cooldown']", ", 'atr_stop']", 1)
        .replace(" +\n      (s.cooldown_skipped_buys === undefined ? '' : ', ' + s.cooldown_skipped_buys + ' skipped by cooldown')", "", 1)
    )
    # Undo the ATR stop checkbox (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n'
        '      <label for="atr_stop">ATR stop</label>\n'
        '      <div class="row">\n'
        '        <input id="atr_stop" name="atr_stop" type="checkbox">\n'
        '        <span class="hint" id="atr-stop-hint">Sell when the price falls ATR multiplier &times; ATR below the entry price. The two ATR fields apply to Risk % and to this.</span>\n'
        '      </div>\n'
        '    </div>\n'
        , "", 1).replace(
        'Fill price, stop loss, take profit, trailing stop, risk sizing and the ATR stop need open/high/low columns',
        "Fill price, stop loss and take profit need open/high/low columns", 1)
    old_js = (
        old_js.replace(
            "    // ATR stop: sent (as true) only when ticked, so an unticked box sends exactly the old request; the ATR\n"
            "    // fields count with it too, so they are sent with it when Risk % did not send them already. Disabled\n"
            "    // and unticked without candle data like the stops.\n"
            "    if (!$('atr_stop').disabled && $('atr_stop').checked === true) {\n"
            "      if (riskPct === '') {\n"
            "        const atrMult = $('atr_mult').value.trim();\n"
            "        const atrPeriod = $('atr_period').value.trim();\n"
            "        if (atrMult !== '') payload.atr_mult = atrMult;\n"
            "        if (atrPeriod !== '') payload.atr_period = atrPeriod;\n"
            "      }\n"
            "      payload.atr_stop = true;\n"
            "    }\n", "", 1)
        .replace("['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop']", "['fill', 'stop_loss', 'take_profit']", 1)
        .replace(
            "      if (!available && field.type === 'checkbox') field.checked = false;\n"
            "      else if (!available) field.value = id === 'fill' ? 'close' : '';",
            "      if (!available) field.value = id === 'fill' ? 'close' : '';", 1)
        .replace(
            "    cards.appendChild(card('Trades', String(s.trades), s.buys + ' buys, ' + s.sells + ' sells' +\n"
            "      (s.risk_skipped_buys === undefined ? '' : ', ' + s.risk_skipped_buys + ' skipped')));",
            "    cards.appendChild(card('Trades', String(s.trades), s.buys + ' buys, ' + s.sells + ' sells'));", 1)
    )
    # Undo the trade list checkbox and results panel (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="trade_list">.*?</div>\n    </div>\n', "", old_html, count=1, flags=re.S)
    old_html = re.sub(r'\n  <div class="panel" id="trade-list-panel" hidden>.*?\n  </div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // trade list: sent \(as true\).*?payload\.trade_list = true;\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"\n    // Trade list: only when the reply has trade_list.*?\n    }\n", "", old_js, count=1, flags=re.S)
    old_html = re.sub(r'    <div class="field">\n      <label for="explain">.*?</div>\n    </div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // explain: sent \(as true\).*?payload\.explain = true;\n", "", old_js, count=1, flags=re.S)
    # Undo the walk-forward "Warm up" box (added after this test was written; its pieces are listed once, in
    # test_web_walkforward_warmup_page.py).
    old_html = old_html.replace(WARMUP_FIELD_HTML, "", 1).replace(WARMUP_LINE_HTML, "", 1)
    for new, old in WARMUP_JS_CHANGES:
        old_js = old_js.replace(new, old, 1)
    # Undo the portfolio panel's strategy picker (added after this test was written).
    old_html = old_html.replace("Runs the SMA crossover (or the strategy you pick) on every file", "Runs the SMA crossover on every file", 1)
    old_html = re.sub(r'      <div class="field span2">\n        <label for="pf-strategy">.*?id="pf-strategy-params"></div>\n      </div>\n', "", old_html, count=1, flags=re.S)
    old_html = old_html.replace('<div class="field" id="pf-short-field">', '<div class="field">', 1).replace('<div class="field" id="pf-long-field">', '<div class="field">', 1)
    old_js = old_js.replace("  const pfStrategySel = $('pf-strategy');\n", "", 1)
    old_js = re.sub(r"    clear\(pfStrategySel\);\n.*?    updatePfStrategyUi\(\);\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    // Strategy: fields\.strategy is the picked name.*?answers with the command's message\.\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    const strategy = text\(fields\.strategy\);\n.*?payload\[key\] = text\(fields\[key\]\);\n    }\n",
                    "    for (const key of ['short', 'long', 'cash', 'fee', 'fee_pct']) payload[key] = text(fields[key]);\n", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    if \(other\) \{\n.*?\n    }\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"\n  // Strategy picker: filled by loadSamples.*?pfStrategySel\.addEventListener\('change', updatePfStrategyUi\);\n", "", old_js, count=1, flags=re.S)
    old_js = re.sub(r"    // A reply for a strategy other than sma_cross.*?: pfTitle\(s\);\n", "    $('pf-title').textContent = pfTitle(s);\n", old_js, count=1, flags=re.S)
    old_js = re.sub(r"        strategy: pfStrategySel\.value,\n.*?        defaults: \(pfCurrentStrategy\(\) \|\| \{\}\)\.params,\n", "", old_js, count=1, flags=re.S)
    assert sha(old_html) == OLD_SHA256["INDEX_HTML"]
    assert sha(old_js) == OLD_SHA256["APP_JS"]
    assert sha(STYLE_CSS) == OLD_SHA256["STYLE_CSS"]
    for panel in ("scan", "wf", "pf"):  # the scan, walk-forward and portfolio panels never mention it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "trailing" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


def test_page_rules_still_hold():
    assert "<style" not in INDEX_HTML and ' style="' not in INDEX_HTML
    assert not re.search(r"\son\w+=", INDEX_HTML)
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS


# --------------------------------------------------------------------------- the backtest form run in Node

FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;  // elements whose content in the HTML is plain text
const PAGE_VALUES = %(values)s;  // value="" of inputs in the HTML
class Node_ {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.attrs = {}; this.listeners = {};
    this.hidden = false; this.value = ''; this.disabled = false; this.files = []; this.style = {};
    this.className = ''; this._text = '';
    if (this.tagName === 'TABLE') { const tb = new Node_('tbody'); this.children.push(tb); this.tBodies = [tb]; }
  }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { this.children.push(c); return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'hidden') this.hidden = true; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get clientWidth() { return 640; }
  getBoundingClientRect() { return {left: 0, top: 0, width: 640, height: 300}; }
  get offsetWidth() { return 100; }
  focus() {}
}
const byId = {};
for (const [id, tag] of PAGE_IDS) {
  const n = new Node_(tag); n.id = id; n._text = PAGE_TEXT[id] || ''; n.value = PAGE_VALUES[id] || ''; byId[id] = n;
}
for (const id of ['wf-results', 'wf-error', 'wf-csv-block', 'scan-results', 'scan-error', 'results', 'error',
                  'csv-block', 'candle-hint', 'strategy-params-block', 'no-trades']) byId[id].hidden = true;
const text = (t) => { const n = new Node_('#text'); n._text = String(t); return n; };
global.document = {
  getElementById: (id) => byId[id] || null,
  createElement: (t) => new Node_(t), createElementNS: (ns, t) => new Node_(t), createTextNode: text,
  documentElement: new Node_('html'), body: new Node_('body'),
};
global.window = { matchMedia: () => ({ matches: false }), addEventListener() {} };
global.localStorage = { getItem: () => null, setItem() {} };
class FR { readAsText(f) { setTimeout(() => { this.result = f.text; this.onload(); }, 0); } }
global.FileReader = FR;
const BASE = %(base)s;
const realFetch = fetch;
global.SENT = [];  // every /api/backtest request body the page sends
global.fetch = (url, opts) => { if (url === '/api/backtest') SENT.push(opts.body); return realFetch(BASE + url, opts); };
"""

DRIVE = r"""
const settle = () => new Promise((r) => setTimeout(r, 80));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
const DEFAULTS = { short: '20', long: '50', cash: '10000', rsi: '14', fee: '0', fee_pct: '0', slippage: '0',
                   position_size: '', fill: 'close', stop_loss: '', take_profit: '', trailing_stop: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;  // a freshly loaded page
  // like a user: pick the source, paste the CSV, then fill in the (enabled) controls and press Run
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) if (id !== 'source' && id !== 'csv' && !byId[id].disabled) byId[id].value = v;
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    trades: cells('trades-table'),
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    hint_hidden: byId['candle-hint'].hidden,
    trailing_disabled: byId['trailing_stop'].disabled,
    trailing_value: byId['trailing_stop'].value,
  };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const fields of %(cases)s) out.push(await submit(fields));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def base_url():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def drive_page(base_url, cases):
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
    script = (
        FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                    "values": json.dumps(values), "base": json.dumps(base_url)}
        + APP_JS
        + DRIVE % {"cases": json.dumps(cases)}
    )
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def old_body(**fields):
    """The request body the page sent before the trailing stop existed (JSON.stringify, key order kept)."""
    body = {"source": "sample", "sample": "uptrend", "short": "20", "long": "50", "rsi_period": "14", "cash": "10000",
            "fee": "0", "fee_pct": "0", "slippage": "0", "position_size": "", "fill": "close", "stop_loss": "",
            "take_profit": ""}
    csv = fields.pop("csv", None)
    body.update(fields)
    if csv is not None:
        body["csv"] = csv
    return json.dumps(body, separators=(",", ":"))


def cli_json(tmp_path, capsys, path_text, flags):
    path = tmp_path / "data.csv"
    path.write_text(path_text)
    assert cli_main([str(path), "--backtest", *flags, "--json"]) == 0
    return json.loads(capsys.readouterr().out)["backtest"]


@needs_node
def test_payload_with_the_field_empty_is_exactly_the_old_one(base_url):
    out = drive_page(base_url, [
        {"source": "uptrend"},
        {**C8, "stop_loss": "10"},
        {**C8, "stop_loss": "10", "take_profit": "15", "fill": "open", "slippage": "1", "position_size": "50"},
        {**C8, "csv": CLOSES_ONLY, "trailing_stop": "10"},  # greyed out: nothing is sent
        {**C8, "trailing_stop": "   "},  # only spaces: not used
    ])
    csv8 = dict(source="csv", sample="csv", short="1", long="2", cash="500", csv=CANDLES)
    assert [r["sent"] for r in out] == [
        [old_body()],
        [old_body(**csv8, stop_loss="10")],
        [old_body(**csv8, stop_loss="10", take_profit="15", fill="open", slippage="1", position_size="0.5")],
        [old_body(**{**csv8, "csv": CLOSES_ONLY})],
        [old_body(**csv8)],
    ]
    assert all("trailing_stop" not in r["sent"][0] for r in out)


@needs_node
def test_payload_with_a_value_adds_trailing_stop_after_take_profit(base_url):
    (r,) = drive_page(base_url, [{**C8, "trailing_stop": " 10 "}])
    body = json.loads(r["sent"][0])
    assert list(body) == ["source", "sample", "short", "long", "rsi_period", "cash", "fee", "fee_pct", "slippage",
                          "position_size", "fill", "stop_loss", "take_profit", "trailing_stop", "csv"]
    assert body["trailing_stop"] == "10"  # trimmed, sent as typed like the other controls


@needs_node
def test_trades_table_shows_trail_like_stop_and_target(base_url):
    trail, stop, target = drive_page(base_url, [
        {**C8, "trailing_stop": "10"}, {**C8, "stop_loss": "10"}, {**C8, "take_profit": "15"},
    ])
    assert [row[-1] for row in trail["trades"]] == ["signal", "trail"]
    assert [row[-1] for row in stop["trades"]] == ["signal", "stop"]
    assert [row[-1] for row in target["trades"]] == ["signal", "target"]
    assert trail["trades"][1] == ["2", "6", "2026-01-07", "SELL", "45", "11.70", "526.50", "0.00", "531.50", "trail"]
    assert trail["error"] is None


@needs_node
def test_page_numbers_equal_the_commands_json(base_url, tmp_path, capsys):
    rw = tmp_path / "rw.csv"
    with open(rw, "w", newline="") as f:
        write_sample_csv("random_walk", f, candles=True)
    page = drive_page(base_url, [
        {**C8, "trailing_stop": "10"},
        {**C8, "trailing_stop": "10", "stop_loss": "5", "take_profit": "20"},
        {"source": "random_walk", "short": "5", "long": "20", "trailing_stop": "3"},
    ])
    cli = [
        cli_json(tmp_path, capsys, CANDLES, ["--short", "1", "--long", "2", "--cash", "500", "--trailing-stop", "10"]),
        cli_json(tmp_path, capsys, CANDLES, ["--short", "1", "--long", "2", "--cash", "500", "--trailing-stop", "10",
                                             "--stop-loss", "5", "--take-profit", "20"]),
        cli_json(tmp_path, capsys, rw.read_text(), ["--short", "5", "--long", "20", "--trailing-stop", "3"]),
    ]
    for p, bt in zip(page, cli):
        assert p["trades"] == [
            [str(n), str(f["bar"]), p["trades"][n - 1][2], f["side"], str(f["shares"]), f"{f['price']:,.2f}",
             f"{f['value']:,.2f}", f"{f['cost']:,.2f}", f"{f['cash_after']:,.2f}", f["reason"]]
            for n, f in enumerate(bt["fills"], start=1)
        ]
        cards = {c[0]: c[1] for c in p["cards"]}
        assert cards["End equity"] == f"{bt['final_equity']:,.2f}"
        assert cards["Return"] == f"{bt['return_pct']:+.2f}%"
        assert cards["Max drawdown"] == f"{bt['max_drawdown_pct']:.2f}%"
        assert "trail" in [f["reason"] for f in bt["fills"]]


@needs_node
@pytest.mark.parametrize("bad", ["0", "100", "-5", "150"])
def test_out_of_range_shows_the_servers_message_like_stop_loss(base_url, bad):
    trail, stop = drive_page(base_url, [{**C8, "trailing_stop": bad}, {**C8, "stop_loss": bad}])
    assert trail["error"] == f"--trailing-stop must be between 0 and 100 (both exclusive), got {bad}"
    assert stop["error"] == f"--stop-loss must be between 0 and 100 (both exclusive), got {bad}"


@needs_node
def test_close_only_csv_greys_out_and_blanks_the_field(base_url):
    closes, candles = drive_page(base_url, [
        {**C8, "csv": CLOSES_ONLY, "trailing_stop": "10"},
        {**C8, "trailing_stop": "10"},
    ])
    assert (closes["trailing_disabled"], closes["trailing_value"], closes["hint_hidden"]) == (True, "", False)
    assert closes["error"] is None and [row[-1] for row in closes["trades"]] == ["-", "-"]
    assert (candles["trailing_disabled"], candles["hint_hidden"]) == (False, True)
