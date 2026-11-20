"""The "Scale out (%)" field of the backtest panel (the command's --scale-out PCT).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against a real local server with the
small stand-in for the browser DOM of test_web_breakeven_page.py (copied, not imported). The page computes nothing
itself: it shows the reply of POST /api/backtest.

The field sits right after "Breakeven (%)". Like the stops it needs candle data: greyed out and blanked for a
close-only CSV, and the close-only hint names it. It is sent only when filled in (empty: exactly the old request).
The Trades card adds ", N partial sells by scale-out" only when the reply has the scale-out keys, and a bad value
shows the API's message.

Hand cases: tests/data/c.csv (SMA 1/2, cash 1000), worked out in test_scale_out.py. Five tests, none parametrized.
"""

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

C_CSV = (Path(__file__).resolve().parent / "data" / "c.csv").read_text()
CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
H = {"source": "csv", "csv": C_CSV, "short": "1", "long": "2", "cash": "1000"}
FIELD_HTML = """    <div class="field">
      <label for="scale_out">Scale out (%)</label>
      <input id="scale_out" name="scale_out" type="number" inputmode="decimal" min="0" step="any" placeholder="Optional">
      <span class="hint" id="scale-out-hint">Once a later bar's high is this % above the entry price, sell half the shares held (rounded down), once per position; the rest stays open.</span>
    </div>
"""


def test_field_sits_after_breakeven_and_is_a_candle_control():
    assert FIELD_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("breakeven", "scale_out", "risk_pct", "candle-hint")]
    assert order == sorted(order)
    tag = re.search(r'<input id="scale_out"[^>]*>', INDEX_HTML).group(0)
    assert "disabled" not in tag and "value=" not in tag  # empty and enabled until the script decides
    controls = re.search(r"const CANDLE_CONTROLS = \[([^\]]*)\];", APP_JS).group(1)
    assert "'scale_out'" in controls
    hint = re.search(r'<p class="hint" id="candle-hint" hidden>([^<]*)</p>', INDEX_HTML).group(1)
    assert hint.endswith("which always has them). The scale-out needs them too.")
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "scale_out" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
                   position_size: '', fill: 'close', stop_loss: '', take_profit: '', trailing_stop: '', breakeven: '',
                   scale_out: '', risk_pct: '', atr_mult: '', atr_period: '', cooldown: '', max_losses: '', min_hold: '',
                   max_hold: '', max_drawdown: '' };
async function submit(fields) {
  SENT.length = 0;
  for (const [id, v] of Object.entries(DEFAULTS)) byId[id].value = v;
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the scale-out is typed in first, then the CSV pasted (a close-only CSV must blank it).
  if ('scale_out' in fields) byId['scale_out'].value = fields.scale_out;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'scale_out'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  const field = { disabled: byId['scale_out'].disabled, value: byId['scale_out'].value };
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    cards: byId['cards'].children.map((c) => c.children.map((x) => x.textContent)),
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
    field,
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
    "5": {**H, "scale_out": "5"},
    "9": {**H, "scale_out": "9"},
    "10": {**H, "scale_out": "10"},
    "5, stop 10": {**H, "scale_out": "5", "stop_loss": "10"},
    "5, breakeven 5": {**H, "scale_out": "5", "breakeven": "5"},
    "empty, c.csv": {**H},
    "empty, sample": {"source": "uptrend"},
    "5, close-only csv": {**H, "csv": CLOSES, "scale_out": "5"},
    "0": {**H, "scale_out": "0"},
    "-1": {**H, "scale_out": "-1"},
    "ten": {**H, "scale_out": "ten"},
    "inf": {**H, "scale_out": "inf"},
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


def trades_card(result):
    return next(c for c in result["cards"] if c[0] == "Trades")


HAND = dict(source="csv", sample="csv", short="1", long="2", cash="1000")


@needs_node
def test_empty_field_sends_exactly_the_old_request_and_shows_nothing_extra(page):
    assert page["empty, c.csv"]["sent"] == [old_body(**HAND, csv=C_CSV)]
    assert page["empty, sample"]["sent"] == [old_body()]
    assert trades_card(page["empty, c.csv"]) == ["Trades", "3", "2 buys, 1 sells"]
    for name in ("empty, c.csv", "empty, sample"):
        assert page[name]["error"] is None and "Scale out" not in page[name]["report"], name
        assert "scale-out" not in " ".join(trades_card(page[name])), name


@needs_node
def test_hand_cases_send_it_and_show_the_count(page):
    # name: (extra fields sent, Trades card, "Scale out:" count text, end equity)
    cases = {
        "5": ({"scale_out": "5"}, ["Trades", "4", "2 buys, 2 sells, 1 partial sells by scale-out"], "1 partial sell,", "995.95"),
        "9": ({"scale_out": "9"}, ["Trades", "4", "2 buys, 2 sells, 1 partial sells by scale-out"], "1 partial sell,", "1,016.15"),
        "10": ({"scale_out": "10"}, ["Trades", "3", "2 buys, 1 sells, 0 partial sells by scale-out"], "0 partial sells,", "925.00"),
        "5, stop 10": ({"stop_loss": "10", "scale_out": "5"},
                       ["Trades", "4", "2 buys, 2 sells, 1 partial sells by scale-out"], "1 partial sell,", "991.45"),
        # Bar 6 sells the other 45 at breakeven (11.00): 529.75 + 495 = 1,024.75; bar 9 buys 85; end 1,041.75.
        "5, breakeven 5": ({"breakeven": "5", "scale_out": "5"},
                           ["Trades", "4", "2 buys, 2 sells, 1 sold at breakeven, 1 partial sells by scale-out"],
                           "1 partial sell,", "1,041.75"),
    }
    for name, (sent, card, count, end) in cases.items():
        result = page[name]
        assert result["sent"] == [old_body(**HAND, **sent, csv=C_CSV)], name
        assert result["field"] == {"disabled": False, "value": sent["scale_out"]} and result["hint_hidden"] is True
        assert result["error"] is None, name
        assert trades_card(result) == card, name
        pct = float(sent["scale_out"])
        assert f"when a high reaches {pct:.2f}% above the average entry; {count}" in result["report"], name
        assert f"  End equity:  {end}\n" in result["report"], name


@needs_node
def test_close_only_csv_greys_it_out_blanks_it_and_does_not_send_it(page):
    result = page["5, close-only csv"]
    assert result["field"] == {"disabled": True, "value": ""}
    assert result["hint_hidden"] is False and result["hint"].endswith("The scale-out needs them too.")
    assert result["sent"] == [old_body(**HAND, csv=CLOSES)]
    assert result["error"] is None and "scale-out" not in " ".join(trades_card(result))


@needs_node
def test_a_bad_value_shows_the_apis_message(page):
    for name, message in (
        ("0", "--scale-out must be above 0, got 0"),
        ("-1", "--scale-out must be above 0, got -1"),
        ("ten", "scale_out must be a number, got 'ten'"),
        ("inf", "scale_out must be a finite number"),
    ):
        result = page[name]
        assert result["sent"] == [old_body(**HAND, scale_out=name, csv=C_CSV)], name
        assert result["error"] == message, name
