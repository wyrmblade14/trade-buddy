"""The "ATR stop" checkbox of the backtest panel (the command's --atr-stop).

Static checks on the HTML and script, plus the shipped APP_JS run for real in
Node against a real local server with a small stand-in for the browser DOM
(the approach of test_web_risk_sizing_page.py). The page computes nothing
itself: it shows the reply of the same ``cli.analyse`` the command line uses.

The box is a candle-only control like the stops: greyed out (and unticked)
for a close-only CSV. Ticked, the page sends ``"atr_stop": true`` after the
ATR fields, and the ATR multiplier and period fields are sent with it even
without Risk %. Unticked or untouched, the page sends exactly the request it
sent before the box existed.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2, ATR stop, multiplier 2, period 3: BUY 90 @ 11 on bar 4; level
11 - 2 * 25/18 = 8.22; bar 7 -> SELL 90 @ 8.22, reason atr, end equity 750.
With ATR period 5 the buy is skipped (1 skipped). With Risk % 2 as well:
7 shares, end equity 980.56.
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

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-03,8.3,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,12.2,13,11.2,12,1000
2026-01-07,11.5,12.5,9.8,10,1000
2026-01-08,8.6,9,7.5,8,1000
"""
CLOSES = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
H = {"source": "csv", "csv": HAND, "short": "1", "long": "2", "cash": "1000"}
HAND_FIELDS = dict(source="csv", sample="csv", short="1", long="2", cash="1000", csv=HAND)

# sha256 of the page before the ATR stop checkbox was added.
OLD_SHA256 = {
    "INDEX_HTML": "7be6b3b60bf5f05a3d14da75021861398b668a0a814f671f527f2493c9c16b0f",
    "APP_JS": "c14f6099a3f181e3535d6793632c794d2d0398ce023b593ac19687eecd79469a",
    "STYLE_CSS": "65885973a502760713898a2f6d6a5da42f55927ab38abedcf9daf901d6738550",
}
FIELD_HTML = """    <div class="field">
      <label for="atr_stop">ATR stop</label>
      <div class="row">
        <input id="atr_stop" name="atr_stop" type="checkbox">
        <span class="hint" id="atr-stop-hint">Sell when the price falls ATR multiplier &times; ATR below the entry price. The two ATR fields apply to Risk % and to this.</span>
      </div>
    </div>
"""
SEND_JS = """    // ATR stop: sent (as true) only when ticked, so an unticked box sends exactly the old request; the ATR
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
"""
UNTICK_JS = """      if (!available && field.type === 'checkbox') field.checked = false;
      else if (!available) field.value = id === 'fill' ? 'close' : '';"""
OLD_UNTICK_JS = """      if (!available) field.value = id === 'fill' ? 'close' : '';"""
SKIPPED_JS = """    cards.appendChild(card('Trades', String(s.trades), s.buys + ' buys, ' + s.sells + ' sells' +
      (s.risk_skipped_buys === undefined ? '' : ', ' + s.risk_skipped_buys + ' skipped') +
      (s.breakeven_exits === undefined ? '' : ', ' + s.breakeven_exits + ' sold at breakeven') +
      (s.scale_out_exits === undefined ? '' : ', ' + s.scale_out_exits + ' partial sells by scale-out') +
      (s.add_on_buys === undefined ? '' : ', ' + s.add_on_buys + ' add-on buys, ' + s.add_on_skipped_buys + ' add-ons skipped') +
      (s.cooldown_skipped_buys === undefined ? '' : ', ' + s.cooldown_skipped_buys + ' skipped by cooldown') +
      (s.min_hold_skipped_sells === undefined ? '' : ', ' + s.min_hold_skipped_sells + ' signal sells skipped by min hold') +
      (s.time_exits === undefined ? '' : ', ' + s.time_exits + ' sold by max hold') +
      (s.drawdown_skipped_buys === undefined ? '' : ', ' + s.drawdown_skipped_buys + ' skipped by drawdown') +
      (s.loss_skipped_buys === undefined ? '' : ', ' + s.loss_skipped_buys + ' buys skipped by losing streak')));"""
OLD_SKIPPED_JS = """    cards.appendChild(card('Trades', String(s.trades), s.buys + ' buys, ' + s.sells + ' sells'));"""
OLD_HINT = "Fill price, stop loss, take profit, trailing stop and risk sizing need open/high/low columns"
NEW_HINT = "Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need open/high/low columns"
OLD_CONTROLS = "['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'risk_pct', 'atr_mult', 'atr_period']"
NEW_CONTROLS = "['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown']"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# --------------------------------------------------------------------------- static page


def test_checkbox_sits_after_the_atr_fields_unticked_and_enabled():
    assert FIELD_HTML in INDEX_HTML
    tag = re.search(r'<input id="atr_stop"[^>]*>', INDEX_HTML).group(0)
    assert tag == '<input id="atr_stop" name="atr_stop" type="checkbox">'  # not checked, not disabled
    order = [INDEX_HTML.index(f'id="{i}"') for i in
             ("trailing_stop", "risk_pct", "atr_mult", "atr_period", "atr_stop", "candle-hint")]
    assert order == sorted(order)
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))


def test_candle_only_like_the_stops_and_the_hint_names_the_atr_stop():
    assert f"const CANDLE_CONTROLS = {NEW_CONTROLS[:-1]}, 'scale_out'];" in APP_JS
    assert NEW_HINT in INDEX_HTML
    assert UNTICK_JS in APP_JS  # greyed out -> unticked, not just blanked


def test_atr_field_labels_fit_both_uses():
    # The ATR fields apply to Risk % and to the ATR stop: their labels name neither, and the box's hint says so.
    assert '<label for="atr_mult">ATR multiplier</label>' in INDEX_HTML
    assert '<label for="atr_period">ATR period</label>' in INDEX_HTML
    assert 'placeholder="2 (default)"' in INDEX_HTML and 'placeholder="14 (default)"' in INDEX_HTML
    assert "The two ATR fields apply to Risk % and to this." in INDEX_HTML


def test_results_show_the_reason_and_the_skipped_count():
    assert "t.reason || '-'" in APP_JS
    assert SKIPPED_JS in APP_JS


def test_nothing_else_changed_since_before_the_checkbox():
    old_html = INDEX_HTML.replace(FIELD_HTML, "", 1).replace(NEW_HINT, OLD_HINT, 1)
    old_js = (
        APP_JS.replace(SEND_JS, "", 1)
        .replace(NEW_CONTROLS, OLD_CONTROLS, 1)
        .replace(UNTICK_JS, OLD_UNTICK_JS, 1)
        .replace(SKIPPED_JS, OLD_SKIPPED_JS, 1)
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
    old_js = old_js.replace(", 'cooldown', 'scale_out']", ", 'cooldown']", 1).replace(NEW_CONTROLS, OLD_CONTROLS, 1)
    # Undo the max losses field (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="max_losses">.*?</div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // max losses: .*?payload\.max_losses = maxLosses;\n", "", old_js, count=1, flags=re.S)
    # Undo the breakeven field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="breakeven">Breakeven (%)</label>\n'
        '      <input id="breakeven" name="breakeven" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">\n'
        '      <span class="hint" id="breakeven-hint">Once a later bar\'s high is this % above the entry price, sell at the entry price if the price falls back to it.</span>\n'
        '    </div>\n', "", 1)
    old_js = old_js.replace(
        "    // breakeven: sent only when filled in (empty: the old request); a stop, so blanked without candle data\n"
        "    const breakeven = $('breakeven').disabled ? '' : $('breakeven').value.trim();\n"
        "    if (breakeven !== '') payload.breakeven = breakeven;\n", "", 1)
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
    # Undo the cooldown field (added after this test was written).
    old_html = old_html.replace(
        '    <div class="field">\n      <label for="cooldown">Cooldown (bars)</label>\n'
        '      <input id="cooldown" name="cooldown" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">\n'
        '      <span class="hint" id="cooldown-hint">After a sell by the stop loss, trailing stop or ATR stop, no buy for this many bars. Needs one of them.</span>\n'
        '    </div>\n', "", 1)
    old_js = old_js.replace(
        "    // cooldown: sent only when filled in, so an empty field sends exactly the old request; the server checks\n"
        "    // it (a stop must be on, a whole number of at least 1) and its message is shown as for the other fields.\n"
        "    // Disabled and blanked without candle data like the stops.\n"
        "    const cooldown = $('cooldown').disabled ? '' : $('cooldown').value.trim();\n"
        "    if (cooldown !== '') payload.cooldown = cooldown;\n", "", 1)
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
    # Undo the add-on fields (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="add_on">.*?<label for="max_adds">.*?</div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // add-on and max adds: .*?payload\.max_adds = maxAdds;\n", "", old_js, count=1, flags=re.S)
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
    assert sha(STYLE_CSS) == OLD_SHA256["STYLE_CSS"]  # no new CSS: the .row/.hint of the upload row
    for panel in ("scan", "wf", "pf"):  # the scan, walk-forward and portfolio panels never mention it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "atr_stop" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


# --------------------------------------------------------------------------- the form run in Node

FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;
const PAGE_VALUES = %(values)s;
const PAGE_TYPES = %(types)s;
class Node_ {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.attrs = {}; this.listeners = {};
    this.hidden = false; this.value = ''; this.disabled = false; this.checked = false; this.files = [];
    this.style = {}; this.className = ''; this._text = '';
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
  const n = new Node_(tag); n.id = id; n._text = PAGE_TEXT[id] || ''; n.value = PAGE_VALUES[id] || '';
  if (PAGE_TYPES[id]) n.type = PAGE_TYPES[id];
  byId[id] = n;
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
global.SENT = [];
global.fetch = (url, opts) => { if (url === '/api/backtest') SENT.push(opts.body); return realFetch(BASE + url, opts); };
"""

DRIVE = r"""
const settle = () => new Promise((r) => setTimeout(r, 80));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
const DEFAULTS = { short: '20', long: '50', cash: '10000', rsi: '14', fee: '0', fee_pct: '0', slippage: '0',
                   position_size: '', fill: 'close', stop_loss: '', take_profit: '', trailing_stop: '',
                   risk_pct: '', atr_mult: '', atr_period: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['trades-table'].tBodies[0].children = []; byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: with a CSV source, a candle CSV is pasted first, the box is ticked, and then the case's own
  // CSV is pasted (so a close-only CSV pasted after ticking must grey the box out and untick it).
  if ('csv' in fields) { byId['csv'].value = %(hand)s; for (const fn of byId['csv'].listeners.input) fn(); }
  if ('atr_stop' in fields && !byId['atr_stop'].disabled) byId['atr_stop'].checked = fields.atr_stop;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'atr_stop'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    trades: cells('trades-table'),
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
    box: { disabled: byId['atr_stop'].disabled, checked: byId['atr_stop'].checked },
  };
}
(async () => {
  await settle();
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


def drive_page(base_url, cases, tmp_path):
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
    types = dict(re.findall(r'<input id="([^"]+)"[^>]*\stype="([^"]+)"', INDEX_HTML))
    script = (
        FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                    "values": json.dumps(values), "types": json.dumps(types), "base": json.dumps(base_url)}
        + APP_JS
        + DRIVE % {"cases": json.dumps(cases), "hand": json.dumps(HAND)}
    )
    path = tmp_path / "page.js"
    path.write_text(script)
    done = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def old_body(**fields):
    """The request body the page sent before the checkbox existed (JSON.stringify, key order kept)."""
    body = {"source": "sample", "sample": "uptrend", "short": "20", "long": "50", "rsi_period": "14", "cash": "10000",
            "fee": "0", "fee_pct": "0", "slippage": "0", "position_size": "", "fill": "close", "stop_loss": "",
            "take_profit": ""}
    csv = fields.pop("csv", None)
    body.update(fields)
    if csv is not None:
        body["csv"] = csv
    return json.dumps(body, separators=(",", ":"))


@needs_node
def test_unticked_or_untouched_sends_exactly_the_request_the_page_sent_before(base_url, tmp_path):
    cases = [
        {"source": "uptrend"},
        {**H},
        {**H, "stop_loss": "10", "trailing_stop": "8"},
        {**H, "atr_mult": "3", "atr_period": "5"},  # ATR fields without Risk % or the box: not sent
        {**H, "risk_pct": "2", "atr_mult": "3"},
    ]
    expected = [
        [old_body()],
        [old_body(**HAND_FIELDS)],
        [old_body(**HAND_FIELDS, stop_loss="10", trailing_stop="8")],
        [old_body(**HAND_FIELDS)],
        [old_body(**HAND_FIELDS, risk_pct="2", atr_mult="3")],
    ]
    untouched = drive_page(base_url, cases, tmp_path)
    unticked = drive_page(base_url, [{**c, "atr_stop": False} for c in cases], tmp_path)
    assert [r["sent"] for r in untouched] == expected
    assert [r["sent"] for r in unticked] == expected


@needs_node
def test_ticked_sends_atr_stop_true_after_the_atr_fields(base_url, tmp_path):
    alone, fields, with_risk, with_trail = drive_page(base_url, [
        {**H, "atr_stop": True},
        {**H, "atr_stop": True, "atr_mult": " 2 ", "atr_period": "3"},
        {**H, "atr_stop": True, "risk_pct": "2", "atr_mult": "2", "atr_period": "3"},
        {**H, "atr_stop": True, "trailing_stop": "8", "atr_period": "3"},
    ], tmp_path)
    assert alone["sent"] == [old_body(**HAND_FIELDS, atr_stop=True)]  # the server's defaults 2 and 14
    body = json.loads(fields["sent"][0])
    assert list(body)[-4:] == ["atr_mult", "atr_period", "atr_stop", "csv"]
    assert (body["atr_mult"], body["atr_period"], body["atr_stop"]) == ("2", "3", True)  # trimmed, as typed
    body = json.loads(with_risk["sent"][0])
    assert list(body)[-6:] == ["take_profit", "risk_pct", "atr_mult", "atr_period", "atr_stop", "csv"]
    body = json.loads(with_trail["sent"][0])
    assert list(body)[-5:] == ["take_profit", "trailing_stop", "atr_period", "atr_stop", "csv"]


@needs_node
def test_page_numbers_and_report_equal_the_commands(base_url, tmp_path, capsys):
    rw = tmp_path / "rw.csv"
    with open(rw, "w", newline="") as f:
        write_sample_csv("random_walk", f, candles=True)
    hand = tmp_path / "hand.csv"
    hand.write_text(HAND)
    page = drive_page(base_url, [
        {**H, "atr_stop": True, "atr_mult": "2", "atr_period": "3"},
        {**H, "atr_stop": True, "atr_mult": "2", "atr_period": "5"},
        {**H, "atr_stop": True, "risk_pct": "2", "atr_mult": "2", "atr_period": "3"},
        {"source": "random_walk", "short": "5", "long": "20", "atr_stop": True, "atr_period": "5"},
    ], tmp_path)
    base = ["--short", "1", "--long", "2", "--cash", "1000"]
    runs = [
        [str(hand), *base, "--atr-stop", "--atr-mult", "2", "--atr-period", "3"],
        [str(hand), *base, "--atr-stop", "--atr-mult", "2", "--atr-period", "5"],
        [str(hand), *base, "--atr-stop", "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3"],
        [str(rw), "--short", "5", "--long", "20", "--atr-stop", "--atr-period", "5"],
    ]
    for p, argv in zip(page, runs):
        assert p["error"] is None
        assert cli_main([argv[0], "--backtest", *argv[1:], "--json"]) == 0
        bt = json.loads(capsys.readouterr().out)["backtest"]
        assert [[row[3], row[4], row[5], row[9]] for row in p["trades"]] == [
            [f["side"], str(f["shares"]), f"{f['price']:,.2f}", f["reason"]] for f in bt["fills"]
        ]
        cards = {c[0]: c[1:] for c in p["cards"]}
        assert cards["End equity"][0] == f"{bt['final_equity']:,.2f}"
        assert cards["Trades"] == [str(bt["trades"]), f"{bt['buys']} buys, {bt['sells']} sells, {bt['risk_skipped_buys']} skipped"]
        assert cli_main([argv[0], "--backtest", *argv[1:]]) == 0
        assert p["report"] == capsys.readouterr().out.rstrip("\n")  # the text report, Exits line included
    hand_case, skipped, with_risk, sample = page
    assert [[row[3], row[4], row[5], row[9]] for row in hand_case["trades"]] == [
        ["BUY", "90", "11.00", "signal"], ["SELL", "90", "8.22", "atr"]]
    assert "  Exits:       atr 2 x ATR(3) below entry" in hand_case["report"]
    assert skipped["trades"] == [] and "  Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)" in skipped["report"]
    assert {c[0]: c for c in skipped["cards"]}["Trades"][2] == "0 buys, 0 sells, 1 skipped"
    assert {c[0]: c[1] for c in with_risk["cards"]}["End equity"] == "980.56"
    assert "atr" in [row[9] for row in sample["trades"]]


@needs_node
def test_without_risk_or_the_box_the_trades_card_is_as_before(base_url, tmp_path):
    (plain,) = drive_page(base_url, [{**H}], tmp_path)
    assert {c[0]: c for c in plain["cards"]}["Trades"] == ["Trades", "2", "1 buys, 1 sells"]


@needs_node
def test_bad_values_show_the_servers_message(base_url, tmp_path):
    out = drive_page(base_url, [
        {**H, "atr_stop": True, "atr_mult": "0"},
        {**H, "atr_stop": True, "atr_period": "0"},
        {**H, "atr_stop": True, "atr_period": "1.5"},
    ], tmp_path)
    assert [r["error"] for r in out] == [
        "--atr-mult must be above 0, got 0",
        "--atr-period must be a whole number of at least 1, got 0",
        "atr_period must be a whole number, got '1.5'",
    ]


@needs_node
def test_close_only_csv_greys_out_unticks_and_does_not_send_it(base_url, tmp_path):
    closes, candles = drive_page(base_url, [
        {**H, "csv": CLOSES, "atr_stop": True, "atr_mult": "2", "atr_period": "3"},
        {**H, "atr_stop": True, "atr_mult": "2", "atr_period": "3"},
    ], tmp_path)
    assert closes["box"] == {"disabled": True, "checked": False}
    assert closes["hint_hidden"] is False and NEW_HINT in closes["hint"]
    assert closes["sent"] == [old_body(source="csv", sample="csv", short="1", long="2", cash="1000", csv=CLOSES)]
    assert closes["error"] is None and "atr" not in closes["report"]
    assert candles["box"] == {"disabled": False, "checked": True} and candles["hint_hidden"] is True
    assert json.loads(candles["sent"][0])["atr_stop"] is True
