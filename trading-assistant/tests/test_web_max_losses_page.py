"""The "Max losses" field of the backtest panel (the command's --max-losses N).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against a real local server with the small
stand-in for the browser DOM of test_web_min_hold_page.py. The page computes nothing itself: it shows the reply of
POST /api/backtest.

The field sits right before Min hold and is sent only when filled in (empty: exactly the old request). It needs no
candle data: it is never greyed out or blanked, and the close-only hint does not name it. The Trades card adds
", N buys skipped by losing streak" only when the reply has the max losses keys, and a bad value shows the API's
message.

Hand case: losses.csv of test_cli_max_losses.py (close-only), cash 1000, short 1, long 2: two losing round trips,
then a buy on bar 15; end 799 without the option.
"""

import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

LOSSES = [10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13]
CSV = "date,close\n" + "".join(f"2026-01-{d:02d},{c}\n" for d, c in enumerate(LOSSES, 1))
H = {"source": "csv", "csv": CSV, "short": "1", "long": "2", "cash": "1000"}


def test_field_sits_right_before_min_hold_and_is_not_a_candle_control():
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("cooldown", "max_losses", "min_hold", "max_hold", "candle-hint")]
    assert order == sorted(order)
    assert '<label for="max_losses">Max losses</label>' in INDEX_HTML
    controls = re.search(r"const CANDLE_CONTROLS = \[([^\]]*)\];", APP_JS).group(1)
    assert "max_losses" not in controls
    hint = re.search(r'<p class="hint" id="candle-hint" hidden>([^<]*)</p>', INDEX_HTML).group(1)
    assert "max losses" not in hint.lower() and "losing" not in hint.lower()
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "max_losses" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
                   risk_pct: '', atr_mult: '', atr_period: '', cooldown: '', min_hold: '', max_hold: '',
                   max_losses: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the max losses is typed in first, then the CSV pasted (a close-only CSV must leave it alone).
  if ('max_losses' in fields) byId['max_losses'].value = fields.max_losses;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'max_losses'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    field: { disabled: byId['max_losses'].disabled, value: byId['max_losses'].value },
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
    "max losses 1": {**H, "max_losses": "1"},
    "max losses 2": {**H, "max_losses": "2"},
    "max losses 3": {**H, "max_losses": "3"},
    "empty, close-only csv": {**H},
    "empty, sample": {"source": "uptrend"},
    "max losses 0": {**H, "max_losses": "0"},
    "max losses 2.5": {**H, "max_losses": "2.5"},
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


def test_empty_field_sends_exactly_the_old_request_and_shows_nothing_extra(page):
    assert page["empty, close-only csv"]["sent"] == [old_body(**HAND, csv=CSV)]
    assert page["empty, sample"]["sent"] == [old_body()]
    assert trades_card(page["empty, close-only csv"]) == ["Trades", "5", "3 buys, 2 sells"]
    for name in ("empty, close-only csv", "empty, sample"):
        assert page[name]["error"] is None and "Max losses" not in page[name]["report"], name
        assert "losing streak" not in " ".join(trades_card(page[name])), name


@pytest.mark.parametrize("n, card, end", [
    ("1", ["Trades", "2", "1 buys, 1 sells, 2 buys skipped by losing streak"], "820.00"),
    ("2", ["Trades", "4", "2 buys, 2 sells, 1 buys skipped by losing streak"], "738.00"),
    ("3", ["Trades", "5", "3 buys, 2 sells, 0 buys skipped by losing streak"], "799.00"),
])
def test_close_only_hand_case_sends_it_and_shows_the_skipped_buys(page, n, card, end):
    result = page[f"max losses {n}"]
    # Sent after the other settings, before the CSV; the field stays enabled and filled for a close-only CSV.
    assert result["sent"] == [old_body(**HAND, max_losses=n, csv=CSV)]
    assert result["field"] == {"disabled": False, "value": n}
    assert result["hint_hidden"] is False  # the close-only hint is shown (for the stops), and does not name it
    assert result["error"] is None
    assert trades_card(result) == card
    assert f"  Max losses:  halt after {n} losing" in result["report"] and f"  End equity:  {end}\n" in result["report"]


@pytest.mark.parametrize("n, message", [
    ("0", "--max-losses must be a whole number of at least 1, got 0"),
    ("2.5", "max_losses must be a whole number, got '2.5'"),
])
def test_a_bad_value_shows_the_apis_message(page, n, message):
    assert page[f"max losses {n}"]["error"] == message
