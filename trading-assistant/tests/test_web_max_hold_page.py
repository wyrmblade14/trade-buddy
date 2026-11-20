"""The "Max hold (bars)" field of the backtest panel (the command's --max-hold N).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against
a real local server with the small stand-in for the browser DOM of
test_web_cooldown_page.py. The page computes nothing itself: it shows the reply
of POST /api/backtest.

The field is sent only when filled in (empty: exactly the old request). Unlike
the stops it needs no candle data: it is never greyed out or blanked, and the
close-only hint does not name it. The Trades card adds ", N sold by max hold"
only when the reply has the max hold keys, and a bad value shows the API's message.

Hand case: the close-only series of test_cli_max_hold.py, cash 1000, short 1, long 2.
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

CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
H = {"source": "csv", "csv": CLOSES, "short": "1", "long": "2", "cash": "1000"}
FIELD_HTML = """    <div class="field">
      <label for="max_hold">Max hold (bars)</label>
      <input id="max_hold" name="max_hold" type="number" inputmode="numeric" min="1" step="1" placeholder="Optional">
      <span class="hint" id="max-hold-hint">Sell a position this many bars after the buy that opened it, at that bar's fill price. Needs no stop; works with a close-only CSV.</span>
    </div>
"""
CANDLE_CONTROLS = "const CANDLE_CONTROLS = ['fill', 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven', 'risk_pct', 'atr_mult', 'atr_period', 'atr_stop', 'cooldown', 'scale_out'];"
HINT = ("Fill price, stop loss, take profit, trailing stop, breakeven, risk sizing, the ATR stop and the cooldown need "
        "open/high/low columns (pasted as a candle CSV, or pick a built-in sample, which always has them).")


def test_field_sits_after_the_cooldown_and_is_not_a_candle_control():
    assert FIELD_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("cooldown", "max_hold", "candle-hint")]
    assert order == sorted(order)
    assert CANDLE_CONTROLS in APP_JS  # unchanged: max_hold is not in it
    assert HINT in INDEX_HTML and "max hold" not in HINT.lower()  # the close-only hint is unchanged
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "max_hold" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
                   risk_pct: '', atr_mult: '', atr_period: '', cooldown: '', max_hold: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the max hold is typed in first, then the CSV pasted (a close-only CSV must leave it alone).
  if ('max_hold' in fields) byId['max_hold'].value = fields.max_hold;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'max_hold'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    field: { disabled: byId['max_hold'].disabled, value: byId['max_hold'].value },
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
    "max hold 1": {**H, "max_hold": "1"},
    "max hold 2": {**H, "max_hold": "2"},
    "max hold 3": {**H, "max_hold": "3"},
    "empty, close-only csv": {**H},
    "empty, sample": {"source": "uptrend"},
    "max hold 0": {**H, "max_hold": "0"},
    "max hold 1.5": {**H, "max_hold": "1.5"},
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
            + DRIVE % {"cases": json.dumps(list(CASES.values()))}
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
    csv = fields.pop("csv", None)
    body.update(fields)
    if csv is not None:
        body["csv"] = csv
    return json.dumps(body, separators=(",", ":"))


def trades_card(result):
    return next(c for c in result["cards"] if c[0] == "Trades")


HAND = dict(source="csv", sample="csv", short="1", long="2", cash="1000")


@needs_node
def test_empty_field_sends_exactly_the_old_request_and_shows_nothing_extra(page):
    assert page["empty, close-only csv"]["sent"] == [old_body(**HAND, csv=CLOSES)]
    assert page["empty, sample"]["sent"] == [old_body()]
    assert trades_card(page["empty, close-only csv"]) == ["Trades", "3", "2 buys, 1 sells"]
    for name in ("empty, close-only csv", "empty, sample"):
        assert page[name]["error"] is None and "Max hold" not in page[name]["report"], name
        assert "max hold" not in " ".join(trades_card(page[name])), name


@needs_node
@pytest.mark.parametrize("n, card, end", [
    ("1", ["Trades", "4", "2 buys, 2 sells, 2 sold by max hold"], "1,108.00"),
    ("2", ["Trades", "3", "2 buys, 1 sells, 1 sold by max hold"], "925.00"),
    ("3", ["Trades", "3", "2 buys, 1 sells, 0 sold by max hold"], "925.00"),
])
def test_close_only_hand_case_sends_it_and_shows_the_time_exits(page, n, card, end):
    result = page[f"max hold {n}"]
    # Sent after the other settings, before the CSV; the field stays enabled and filled for a close-only CSV.
    body = json.loads(old_body(**HAND, max_hold=n, csv=CLOSES))
    assert result["sent"] == [json.dumps(body, separators=(",", ":"))]
    assert result["field"] == {"disabled": False, "value": n}
    assert result["hint_hidden"] is False  # the close-only hint is shown (for the stops), and does not name it
    assert result["error"] is None
    assert trades_card(result) == card
    assert f"  Max hold:    {n} bar" in result["report"] and f"  End equity:  {end}\n" in result["report"]


@needs_node
@pytest.mark.parametrize("n, message", [
    ("0", "--max-hold must be a whole number of at least 1, got 0"),
    ("1.5", "max_hold must be a whole number, got '1.5'"),
])
def test_a_bad_value_shows_the_apis_message(page, n, message):
    assert page[f"max hold {n}"]["error"] == message
