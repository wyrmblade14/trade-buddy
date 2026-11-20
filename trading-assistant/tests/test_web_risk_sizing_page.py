"""The "Risk % per buy", "ATR multiplier" and "ATR period" controls of the backtest panel.

Static checks on the HTML and script, plus the shipped APP_JS run for real in
Node against a real local server with a small stand-in for the browser DOM
(the approach of test_web_trailing_stop_page.py). The page computes nothing
itself: it shows the reply of the same ``cli.analyse`` the command line uses.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2, risk 2, ATR multiplier 2, ATR period 3: 7 shares @ 11 on bar 4, sold
@ 8 on bar 7, end equity 979. With ATR period 5 the buy is skipped.
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
RISK_IDS = ["risk_pct", "atr_mult", "atr_period"]

# sha256 of the page before these three controls were added.
OLD_SHA256 = {
    "INDEX_HTML": "aeeac9e7210c4f3f52ae9e1df73d514034bdc5b4e2b00e04604276b5bb554856",
    "APP_JS": "ff683cf4635d6011b6c48693a61a2087b6b0e569d7455ecc9f3fce442a533077",
    "STYLE_CSS": "65885973a502760713898a2f6d6a5da42f55927ab38abedcf9daf901d6738550",
}
FIELDS_HTML = """    <div class="field">
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
"""
SEND_JS = """    // risk sizing: sent only when Risk % has a value, and the ATR fields only count (and are only sent)
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
"""
OLD_HINT = "Fill price, stop loss, take profit and trailing stop need open/high/low columns"
NEW_HINT = "Fill price, stop loss, take profit, trailing stop and risk sizing need open/high/low columns"
OLD_CONTROLS = "['fill', 'stop_loss', 'take_profit', 'trailing_stop']"
NEW_CONTROLS = "['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'risk_pct', 'atr_mult', 'atr_period']"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# --------------------------------------------------------------------------- static page (tests 1-3)


def test_fields_sit_after_trailing_stop_in_its_style():
    trail = re.search(r'<input id="trailing_stop"[^>]*>', INDEX_HTML).group(0)
    risk = re.search(r'<input id="risk_pct"[^>]*>', INDEX_HTML).group(0)
    assert risk == trail.replace("trailing_stop", "risk_pct").replace('max="99.99"', 'max="100"')  # 100 is allowed
    assert FIELDS_HTML in INDEX_HTML
    for tag in re.findall(r'<input id="(?:risk_pct|atr_mult|atr_period)"[^>]*>', INDEX_HTML):
        assert 'type="number"' in tag and "disabled" not in tag and "value=" not in tag  # empty: not used
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("trailing_stop", *RISK_IDS, "candle-hint")]
    assert order == sorted(order)
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))


def test_candle_only_like_stop_loss_and_hint_names_risk_sizing():
    assert "const CANDLE_CONTROLS = ['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown', 'scale_out'];" in APP_JS
    assert "Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need open/high/low columns" in INDEX_HTML


def test_nothing_else_changed_since_before_these_controls():
    old_html = INDEX_HTML.replace(FIELDS_HTML, "", 1).replace(NEW_HINT, OLD_HINT, 1)
    old_js = APP_JS.replace(SEND_JS, "", 1).replace(NEW_CONTROLS, OLD_CONTROLS, 1)
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
        OLD_HINT, 1)
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
        .replace("['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop']", OLD_CONTROLS, 1)
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


# --------------------------------------------------------------------------- the form run in Node (tests 4-8)

FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;
const PAGE_VALUES = %(values)s;
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
  byId['trades-table'].tBodies[0].children = []; byId['error'].hidden = true; byId['report'].textContent = '';
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
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    disabled: ['risk_pct', 'atr_mult', 'atr_period'].map((id) => byId[id].disabled),
    values: ['risk_pct', 'atr_mult', 'atr_period'].map((id) => byId[id].value),
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
    """The request body the page sent before these controls existed (JSON.stringify, key order kept)."""
    body = {"source": "sample", "sample": "uptrend", "short": "20", "long": "50", "rsi_period": "14", "cash": "10000",
            "fee": "0", "fee_pct": "0", "slippage": "0", "position_size": "", "fill": "close", "stop_loss": "",
            "take_profit": ""}
    csv = fields.pop("csv", None)
    body.update(fields)
    if csv is not None:
        body["csv"] = csv
    return json.dumps(body, separators=(",", ":"))


@needs_node
def test_empty_fields_send_exactly_the_request_the_page_sends_today(base_url):
    hand = dict(source="csv", sample="csv", short="1", long="2", cash="1000", csv=HAND)
    out = drive_page(base_url, [
        {"source": "uptrend"},
        {**H, "stop_loss": "10", "trailing_stop": "8"},
        {**H, "atr_mult": "3", "atr_period": "5"},  # ATR fields count only with Risk %
        {**H, "risk_pct": "   ", "atr_mult": "3"},  # only spaces: not used
    ])
    assert [r["sent"] for r in out] == [
        [old_body()],
        [old_body(**hand, stop_loss="10", trailing_stop="8")],
        [old_body(**hand)],
        [old_body(**hand)],
    ]


@needs_node
def test_risk_sends_its_keys_right_after_trailing_stop(base_url):
    full, only_risk = drive_page(base_url, [
        {**H, "trailing_stop": "8", "risk_pct": " 2 ", "atr_mult": "2", "atr_period": "3"},
        {**H, "risk_pct": "2"},
    ])
    body = json.loads(full["sent"][0])
    assert list(body) == ["source", "sample", "short", "long", "rsi_period", "cash", "fee", "fee_pct", "slippage",
                          "position_size", "fill", "stop_loss", "take_profit", "trailing_stop", "risk_pct",
                          "atr_mult", "atr_period", "csv"]
    assert (body["risk_pct"], body["atr_mult"], body["atr_period"]) == ("2", "2", "3")  # trimmed, as typed
    body = json.loads(only_risk["sent"][0])
    assert "risk_pct" in body and "atr_mult" not in body and "atr_period" not in body  # server defaults 2 and 14


@needs_node
def test_page_numbers_and_report_equal_the_commands(base_url, tmp_path, capsys):
    rw = tmp_path / "rw.csv"
    with open(rw, "w", newline="") as f:
        write_sample_csv("random_walk", f, candles=True)
    hand = tmp_path / "hand.csv"
    hand.write_text(HAND)
    page = drive_page(base_url, [
        {**H, "risk_pct": "2", "atr_mult": "2", "atr_period": "3"},
        {**H, "risk_pct": "2", "atr_mult": "2", "atr_period": "5"},
        {"source": "random_walk", "short": "5", "long": "20", "risk_pct": "1", "atr_mult": "3"},
    ])
    runs = [
        [str(hand), "--short", "1", "--long", "2", "--cash", "1000", "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3"],
        [str(hand), "--short", "1", "--long", "2", "--cash", "1000", "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "5"],
        [str(rw), "--short", "5", "--long", "20", "--risk-pct", "1", "--atr-mult", "3"],
    ]
    for p, argv in zip(page, runs):
        assert cli_main([argv[0], "--backtest", *argv[1:], "--json"]) == 0
        bt = json.loads(capsys.readouterr().out)["backtest"]
        assert [row[3:6] for row in p["trades"]] == [[f["side"], str(f["shares"]), f"{f['price']:,.2f}"] for f in bt["fills"]]
        cards = {c[0]: c[1] for c in p["cards"]}
        assert cards["End equity"] == f"{bt['final_equity']:,.2f}"
        assert cli_main([argv[0], "--backtest", *argv[1:]]) == 0
        assert p["report"] == capsys.readouterr().out.rstrip("\n")  # text report with the Risk sizing line
    assert [row[3:6] for row in page[0]["trades"]] == [["BUY", "7", "11.00"], ["SELL", "7", "8.00"]]
    assert "  Skipped:     1 buy " in page[1]["report"] and page[1]["trades"] == []


@needs_node
def test_bad_values_show_the_servers_message(base_url):
    out = drive_page(base_url, [
        {**H, "risk_pct": "0"},
        {**H, "risk_pct": "150"},
        {**H, "risk_pct": "2", "atr_mult": "0"},
        {**H, "risk_pct": "2", "atr_period": "0"},
        {**H, "risk_pct": "2", "atr_period": "1.5"},
    ])
    assert [r["error"] for r in out] == [
        "--risk-pct must be above 0 and at most 100, got 0",
        "--risk-pct must be above 0 and at most 100, got 150",
        "--atr-mult must be above 0, got 0",
        "--atr-period must be a whole number of at least 1, got 0",
        "atr_period must be a whole number, got '1.5'",
    ]


@needs_node
def test_close_only_csv_greys_out_blanks_and_does_not_send_the_fields(base_url):
    closes, candles = drive_page(base_url, [
        {**H, "csv": CLOSES, "risk_pct": "2", "atr_mult": "2", "atr_period": "3"},
        {**H, "risk_pct": "2", "atr_mult": "2", "atr_period": "3"},
    ])
    assert (closes["disabled"], closes["values"], closes["hint_hidden"]) == ([True] * 3, [""] * 3, False)
    assert closes["sent"] == [old_body(source="csv", sample="csv", short="1", long="2", cash="1000", csv=CLOSES)]
    assert closes["error"] is None and "Risk sizing" not in closes["report"]
    assert (candles["disabled"], candles["hint_hidden"]) == ([False] * 3, True)
