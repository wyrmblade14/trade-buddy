"""The "Add-on (%)" and "Max adds" fields of the backtest panel (the command's --add-on PCT and --max-adds N).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against a real local server with the small
stand-in for the browser DOM of test_web_scale_out_page.py (copied, not imported). The page computes nothing itself:
it shows the reply of POST /api/backtest.

The two fields sit right after "Max drawdown (%)", at the end of the fields that need no candle data, just before
the close-only hint. They are not candle controls: never greyed out or blanked for a close-only CSV, and the hint
does not name them. Each is sent only when filled in (both empty: exactly the old request); a filled Max adds is
sent even with Add-on empty, and the API's message is shown. The Trades card adds ", N add-on buys, M add-ons
skipped" only when the reply has the add-on keys. A bad value shows the API's message.

Hand cases: up.csv (closes 10 9 8 9 11 12 13 14 15 14 13 12; close-only), SMA 1/2, cash 1000, worked out in
test_add_on.py: position size 50 % with Add-on 10 gives 1,054.00 (1 add-on buy), with 20 1,024.00; all-in with
Add-on 10 gives 1,180.00 with 3 add-ons skipped. Eight tests: three plain, one parametrized over five values.
"""

import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

UP_CSV = "close\n" + "".join(f"{c}\n" for c in [10, 9, 8, 9, 11, 12, 13, 14, 15, 14, 13, 12])
U = {"source": "csv", "csv": UP_CSV, "short": "1", "long": "2", "cash": "1000"}
FIELDS_HTML = """    <div class="field">
      <label for="add_on">Add-on (%)</label>
      <input id="add_on" name="add_on" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
      <span class="hint" id="add-on-hint">While a position is held, buy more on the next bar after a close this % or more above the latest buy price, sized like any buy (with all-in sizing it usually gets 0 shares). Needs no stop; works with a close-only CSV.</span>
    </div>
    <div class="field">
      <label for="max_adds">Max adds</label>
      <input id="max_adds" name="max_adds" type="number" inputmode="numeric" min="1" step="1" placeholder="1 (default)">
      <span class="hint" id="max-adds-hint">The most add-on buys per position. Needs Add-on (%). Works with a close-only CSV.</span>
    </div>
"""

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
                   position_size: '', fill: 'close', stop_loss: '', take_profit: '', trailing_stop: '', breakeven: '',
                   scale_out: '', risk_pct: '', atr_mult: '', atr_period: '', cooldown: '', max_losses: '', min_hold: '',
                   max_hold: '', max_drawdown: '', add_on: '', max_adds: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the two fields are typed in first, then the CSV pasted (a close-only CSV must leave them alone).
  for (const id of ['add_on', 'max_adds']) if (id in fields) byId[id].value = fields[id];
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'add_on', 'max_adds'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  const state = {};
  for (const id of ['add_on', 'max_adds']) state[id] = { disabled: byId[id].disabled, value: byId[id].value };
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
    state,
  };
}
(async () => {
  await settle();
  const out = [];
  for (const fields of %(cases)s) out.push(await submit(fields));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

BAD = {
    "add_on 0": ({"add_on": "0"}, "--add-on must be above 0, got 0"),
    "add_on ten": ({"add_on": "ten"}, "add_on must be a number, got 'ten'"),
    "add_on inf": ({"add_on": "inf"}, "add_on must be a finite number"),
    "max_adds 0": ({"add_on": "10", "max_adds": "0"}, "--max-adds must be a whole number of at least 1, got 0"),
    "max_adds 2.5": ({"add_on": "10", "max_adds": "2.5"}, "max_adds must be a whole number, got '2.5'"),
}
CASES = {
    "empty, up.csv": {**U},
    "empty, up.csv, 50%": {**U, "position_size": "50"},
    "empty, sample": {"source": "uptrend"},
    "10, 50%": {**U, "position_size": "50", "add_on": "10"},
    "20, 50%": {**U, "position_size": "50", "add_on": "20"},
    "10, all-in": {**U, "add_on": "10"},
    "10, max 2, 50%": {**U, "position_size": "50", "add_on": "10", "max_adds": "2"},
    "max adds only": {**U, "position_size": "50", "max_adds": "2"},
    **{name: {**U, "position_size": "50", **fields} for name, (fields, _) in BAD.items()},
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
    """The request body the page sent before the fields existed (JSON.stringify, key order kept)."""
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


def test_fields_sit_after_max_drawdown_and_are_not_candle_controls():
    assert FIELDS_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("max_drawdown", "add_on", "max_adds", "candle-hint")]
    assert order == sorted(order)
    assert INDEX_HTML.index('id="max-drawdown-hint"') < INDEX_HTML.index('id="add_on"')
    for i in ("add_on", "max_adds"):
        tag = re.search(rf'<input id="{i}"[^>]*>', INDEX_HTML).group(0)
        assert "disabled" not in tag and "value=" not in tag  # empty and enabled
    controls = re.search(r"const CANDLE_CONTROLS = \[([^\]]*)\];", APP_JS).group(1)
    assert "add_on" not in controls and "max_adds" not in controls
    hint = re.search(r'<p class="hint" id="candle-hint" hidden>([^<]*)</p>', INDEX_HTML).group(1)
    assert "add" not in hint.lower()
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has them
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "add_on" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


def test_requests_empty_sends_the_old_request_and_close_only_keeps_the_fields(page):
    assert page["empty, up.csv"]["sent"] == [old_body(**HAND, csv=UP_CSV)]
    assert page["empty, up.csv, 50%"]["sent"] == [old_body(**{**HAND, "position_size": "0.5"}, csv=UP_CSV)]
    assert page["empty, sample"]["sent"] == [old_body()]
    for name in ("empty, up.csv", "empty, up.csv, 50%", "empty, sample"):
        assert page[name]["error"] is None and "Add-ons" not in page[name]["report"], name
        assert "add-on" not in " ".join(trades_card(page[name])), name
    sent = {
        "10, 50%": {"add_on": "10"},
        "20, 50%": {"add_on": "20"},
        "10, all-in": {"add_on": "10"},
        "10, max 2, 50%": {"add_on": "10", "max_adds": "2"},
        "max adds only": {"max_adds": "2"},
    }
    for name, extra in sent.items():
        result = page[name]
        size = {} if name == "10, all-in" else {"position_size": "0.5"}
        assert result["sent"] == [old_body(**{**HAND, **size}, **extra, csv=UP_CSV)], name
        # up.csv is close-only: the candle hint shows, but the fields are neither greyed out nor blanked.
        assert result["hint_hidden"] is False and "add" not in result["hint"].lower(), name
        for i in ("add_on", "max_adds"):
            assert result["state"][i] == {"disabled": False, "value": extra.get(i, "")}, (name, i)
    # Max adds without Add-on is sent anyway and the API's message is shown.
    assert page["max adds only"]["error"] == "--max-adds only makes sense together with --add-on"


def test_trades_card_and_report_show_the_counts(page):
    assert trades_card(page["empty, up.csv, 50%"]) == ["Trades", "2", "1 buys, 1 sells"]
    cases = {
        "10, 50%": (["Trades", "3", "2 buys, 1 sells, 1 add-on buys, 0 add-ons skipped"], 1, "10.00", "1,054.00"),
        "20, 50%": (["Trades", "3", "2 buys, 1 sells, 1 add-on buys, 0 add-ons skipped"], 1, "20.00", "1,024.00"),
        "10, all-in": (["Trades", "2", "1 buys, 1 sells, 0 add-on buys, 3 add-ons skipped"], 1, "10.00", "1,180.00"),
        "10, max 2, 50%": (["Trades", "3", "2 buys, 1 sells, 1 add-on buys, 0 add-ons skipped"], 2, "10.00", "1,054.00"),
    }
    for name, (card, n, pct, end) in cases.items():
        result = page[name]
        assert result["error"] is None, name
        assert trades_card(result) == card, name
        assert f"  Add-ons:     up to {n} per position, a buy on the next bar after a close {pct}% or more" in result["report"]
        assert f"  End equity:  {end}\n" in result["report"], name


@pytest.mark.parametrize("name", list(BAD))
def test_a_bad_value_shows_the_apis_message(page, name):
    fields, message = BAD[name]
    result = page[name]
    assert result["sent"] == [old_body(**{**HAND, "position_size": "0.5"}, **fields, csv=UP_CSV)]
    assert result["error"] == message
