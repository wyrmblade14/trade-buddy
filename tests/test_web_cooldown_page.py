"""The "Cooldown (bars)" field of the backtest panel (the command's --cooldown N).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against
a real local server with a small stand-in for the browser DOM (the approach of
test_web_atr_stop_page.py). The page computes nothing itself: it shows the reply
of POST /api/backtest.

The field is sent only when filled in (empty: exactly the old request), it is a
candle-only control (greyed out and blanked for a close-only CSV, and the hint
names it), the Trades card adds ", N skipped by cooldown" only when the reply
has the cooldown keys, and a bad value or a missing stop shows the API's message.

Hand case: the 11-bar candle file of test_cli_cooldown.py, cash 1000, short 1,
long 2, stop loss 10: cooldown 3 skips the bar 9 buy (end 901), cooldown 2 does
not (end 916).
"""

import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HAND = """\
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
"""
CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
H = {"source": "csv", "csv": HAND, "short": "1", "long": "2", "cash": "1000"}
FIELD_HTML = """    <div class="field">
      <label for="cooldown">Cooldown (bars)</label>
      <input id="cooldown" name="cooldown" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="cooldown-hint">After a sell by the stop loss, trailing stop or ATR stop, no buy for this many bars. Needs one of them.</span>
    </div>
"""
HINT = "Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need open/high/low columns"


def test_field_sits_after_the_atr_stop_box_empty_and_enabled():
    assert FIELD_HTML in INDEX_HTML and HINT in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("atr_stop", "cooldown", "candle-hint")]
    assert order == sorted(order)
    assert "const CANDLE_CONTROLS = ['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown', 'scale_out'];" in APP_JS
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "cooldown" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
const DEFAULTS = { short: '20', long: '50', cash: '10000', rsi: '14', fee: '0', fee_pct: '0', slippage: '0',
                   position_size: '', fill: 'close', stop_loss: '', take_profit: '', trailing_stop: '',
                   risk_pct: '', atr_mult: '', atr_period: '', cooldown: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: with a CSV source a candle CSV is pasted first and the cooldown typed in, then the case's own
  // CSV is pasted (so a close-only CSV pasted after typing must grey the field out and blank it).
  if ('csv' in fields) { byId['csv'].value = %(hand)s; for (const fn of byId['csv'].listeners.input) fn(); }
  if ('cooldown' in fields) byId['cooldown'].value = fields.cooldown;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (id === 'atr_stop') byId[id].checked = v;
    else if (!['source', 'csv', 'cooldown'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
    field: { disabled: byId['cooldown'].disabled, value: byId['cooldown'].value },
  };
}
(async () => {
  await settle();
  const out = [];
  for (const fields of %(cases)s) out.push(await submit(fields));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

CASES = {
    "cooldown 3": {**H, "stop_loss": "10", "cooldown": "3"},
    "cooldown 2": {**H, "stop_loss": "10", "cooldown": "2"},
    "empty, stop": {**H, "stop_loss": "10"},
    "empty, atr stop": {**H, "atr_stop": True, "atr_mult": "1", "atr_period": "1"},
    "empty, sample": {"source": "uptrend"},
    "close-only csv": {**H, "csv": CLOSES, "cooldown": "3"},
    "cooldown 0": {**H, "stop_loss": "10", "cooldown": "0"},
    "cooldown 1.5": {**H, "stop_loss": "10", "cooldown": "1.5"},
    "no stop": {**H, "cooldown": "3"},
}


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """Every case of CASES submitted once through the real page script, in one Node run."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
        texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
        values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
        types = dict(re.findall(r'<input id="([^"]+)"[^>]*\stype="([^"]+)"', INDEX_HTML))
        script = (
            FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                        "values": json.dumps(values), "types": json.dumps(types),
                        "base": json.dumps(f"http://127.0.0.1:{server.server_address[1]}")}
            + APP_JS
            + DRIVE % {"cases": json.dumps(list(CASES.values())), "hand": json.dumps(HAND)}
        )
        path = tmp_path_factory.mktemp("page") / "page.js"
        path.write_text(script)
        done = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        return dict(zip(CASES, json.loads(done.stdout)))
    finally:
        server.shutdown()
        server.server_close()


def old_body(**fields):
    """The request body the page sent before the field existed (JSON.stringify, key order kept)."""
    body = {"source": "sample", "sample": "uptrend", "short": "20", "long": "50", "rsi_period": "14", "cash": "10000",
            "fee": "0", "fee_pct": "0", "slippage": "0", "position_size": "", "fill": "close", "stop_loss": "",
            "take_profit": ""}
    extra = {k: fields.pop(k) for k in ("atr_mult", "atr_period", "atr_stop", "csv") if k in fields}
    body.update(fields)
    body.update(extra)
    return json.dumps(body, separators=(",", ":"))


def trades_card(result):
    return next(c for c in result["cards"] if c[0] == "Trades")


@needs_node
def test_empty_field_sends_exactly_the_old_request_and_shows_nothing_extra(page):
    hand = dict(source="csv", sample="csv", short="1", long="2", cash="1000")
    assert page["empty, stop"]["sent"] == [old_body(**hand, stop_loss="10", csv=HAND)]
    assert page["empty, atr stop"]["sent"] == [old_body(**hand, atr_mult="1", atr_period="1", atr_stop=True, csv=HAND)]
    assert page["empty, sample"]["sent"] == [old_body()]
    assert trades_card(page["empty, stop"]) == ["Trades", "3", "2 buys, 1 sells"]
    assert trades_card(page["empty, atr stop"]) == ["Trades", "3", "2 buys, 1 sells, 0 skipped"]
    for name in ("empty, stop", "empty, atr stop", "empty, sample"):
        assert page[name]["error"] is None and "ooldown" not in page[name]["report"], name


@needs_node
@pytest.mark.parametrize("n, card, line, end", [
    ("3", ["Trades", "2", "1 buys, 1 sells, 1 skipped by cooldown"], "Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped", "901.00"),
    ("2", ["Trades", "3", "2 buys, 1 sells, 0 skipped by cooldown"], "Cooldown:    2 bars after a stop, trail or atr exit; 0 buys skipped", "916.00"),
])
def test_hand_case_sends_it_and_shows_the_skipped_count(page, n, card, line, end):
    result = page[f"cooldown {n}"]
    sent = json.loads(result["sent"][0])
    assert list(sent)[-3:] == ["take_profit", "cooldown", "csv"] and sent["cooldown"] == n
    assert result["error"] is None
    assert trades_card(result) == card
    assert line in result["report"]
    assert next(c for c in result["cards"] if c[0] == "End equity")[1] == end


@needs_node
def test_close_only_csv_greys_it_out_blanks_it_and_does_not_send_it(page):
    result = page["close-only csv"]
    assert result["field"] == {"disabled": True, "value": ""}
    assert result["hint_hidden"] is False and HINT in result["hint"]
    assert "cooldown" not in json.loads(result["sent"][0])
    assert page["cooldown 3"]["field"] == {"disabled": False, "value": "3"} and page["cooldown 3"]["hint_hidden"] is True


@needs_node
@pytest.mark.parametrize("name, message", [
    ("cooldown 0", "--cooldown must be a whole number of at least 1, got 0"),
    ("cooldown 1.5", "cooldown must be a whole number, got '1.5'"),
    ("no stop", "--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop"),
])
def test_a_bad_value_or_no_stop_shows_the_apis_message(page, name, message):
    result = page[name]
    assert len(result["sent"]) == 1 and "cooldown" in json.loads(result["sent"][0])
    assert result["error"] == message
