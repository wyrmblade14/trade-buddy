"""The "Explain signal" checkbox of the backtest panel (the command's --explain).

Static checks on the HTML, plus the shipped APP_JS run for real in Node against a real local server with the
small stand-in for the browser DOM of test_web_trade_list_page.py (copied, not imported). The page works out no
signal itself: it shows the reply of POST /api/backtest.

The box sits right after the "Trade list" box, the other switch that changes no trade and only adds to what is shown.
It needs no candle data: never greyed out, and the close-only hint does not name it. It is sent (as true) only when
ticked, so an unticked box sends exactly the old request. The page has no Signal line of its own outside the text
report, and with explain the reply's report already has the sentence right under its Signal line, so the page shows
the report as it is: the sentence appears once, under Signal, and nothing else on the page changes. A bad reply
shows the API's message.

Hand cases: tests/data/c.csv with short 1, long 3 (sentences worked out in test_explain_crossover.py). Seven tests,
counting each parametrized case.
"""

import contextlib
import io
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

ROWS = (Path(__file__).resolve().parent / "data" / "c.csv").read_text().splitlines()
FIRST = {n: "\n".join(ROWS[: n + 1]) + "\n" for n in (3, 4, 7)}  # candle CSVs: c.csv's first n rows
CLOSES = "date,close\n" + "".join(f"{r.split(',')[0]},{r.split(',')[4]}\n" for r in ROWS[1:])  # all 11, close-only
FIELD_HTML = """    <div class="field">
      <label for="explain">Explain signal</label>
      <div class="row">
        <input id="explain" name="explain" type="checkbox">
        <span class="hint" id="explain-hint">Also say why the Signal line of the text report is BUY, SELL or HOLD: one sentence right under it, with the short and long SMA on the last bar and the bar before (the command's --explain). Changes no trade. Works with a close-only CSV.</span>
      </div>
    </div>
"""


def test_checkbox_sits_after_trade_list_and_needs_no_candle_data():
    assert FIELD_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("trade_list", "trade-list-hint", "explain", "cooldown", "candle-hint")]
    assert order == sorted(order)
    tag = re.search(r'<input id="explain"[^>]*>', INDEX_HTML).group(0)
    assert "checked" not in tag and "disabled" not in tag
    assert "'explain'" not in re.search(r"const CANDLE_CONTROLS = \[([^\]]*)\];", APP_JS).group(1)
    hint = re.search(r'<p class="hint" id="candle-hint" hidden>([^<]*)</p>', INDEX_HTML).group(1)
    assert "explain" not in hint.lower()
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "explain" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
                  'csv-block', 'candle-hint', 'strategy-params-block', 'no-trades', 'trade-list-panel']) byId[id].hidden = true;
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
  byId['atr_stop'].checked = false; byId['trade_list'].checked = false;
  byId['error'].hidden = true;
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the box is ticked first, then the CSV pasted (a close-only CSV must leave it ticked).
  byId['explain'].checked = fields.explain === true;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'explain'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  const box = { disabled: byId['explain'].disabled, checked: byId['explain'].checked };
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  // Everything the page shows, element by element (the stand-in DOM does not nest the page's own elements).
  const shown = {};
  for (const [id, node] of Object.entries(byId)) if (!node.hidden) shown[id] = node.textContent;
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
    shown,
    box,
  };
}
(async () => {
  await settle();
  const out = [];
  for (const fields of %(cases)s) out.push(await submit(fields));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

HAND = dict(source="csv", short="1", long="3")  # the form's fields; the request also has "sample": "csv"
CASES = {  # submitted in this order, one after the other on the same page
    "ticked first 4": {**HAND, "csv": FIRST[4], "explain": True},
    "unticked after ticked": {**HAND, "csv": FIRST[4]},
    "ticked close-only": {**HAND, "csv": CLOSES, "explain": True},
    "ticked first 7": {**HAND, "csv": FIRST[7], "explain": True},
    "ticked first 3": {**HAND, "csv": FIRST[3], "explain": True},
    "unticked sample": {"source": "uptrend"},
    "ticked bad": {**HAND, "csv": FIRST[4], "short": "3", "explain": True},
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
    """The request body the page sent before the box existed (JSON.stringify, key order kept)."""
    body = {"source": "sample", "sample": "uptrend", "short": "20", "long": "50", "rsi_period": "14", "cash": "10000",
            "fee": "0", "fee_pct": "0", "slippage": "0", "position_size": "", "fill": "close", "stop_loss": "",
            "take_profit": ""}
    csv = fields.pop("csv", None)
    body.update(fields)
    if csv is not None:
        body["csv"] = csv
    return json.dumps(body, separators=(",", ":"))


def cli_output(tmp_path, monkeypatch, text, *flags):
    """stdout of ``--backtest --short 1 --long 3`` plus ``flags`` on ``text``."""
    (tmp_path / "p.csv").write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli_main(["p.csv", "--backtest", "--short", "1", "--long", "3", *flags]) == 0
    return out.getvalue()


def test_unticked_sends_exactly_the_old_request_and_shows_nothing_extra(page, tmp_path, monkeypatch):
    assert page["unticked after ticked"]["sent"] == [old_body(source="csv", sample="csv", short="1", long="3",
                                                              csv=FIRST[4])]
    assert page["unticked sample"]["sent"] == [old_body()]
    result = page["unticked after ticked"]  # the run before it was ticked: its sentence is gone
    assert result["error"] is None and result["box"] == {"disabled": False, "checked": False}
    assert result["report"] == cli_output(tmp_path, monkeypatch, FIRST[4]).rstrip("\n")
    assert not any(" because " in text for text in page["unticked after ticked"]["shown"].values())
    assert not any(" because " in text for text in page["unticked sample"]["shown"].values())
    # Ticked and unticked on the same CSV: the page differs only by the report's sentence line (and the timing).
    ticked, unticked = page["ticked first 4"]["shown"], page["unticked after ticked"]["shown"]
    assert ticked.keys() == unticked.keys()
    assert {k: v for k, v in ticked.items() if k not in ("report", "status")} == {
        k: v for k, v in unticked.items() if k not in ("report", "status")}
    lines = ticked["report"].splitlines()
    assert lines.pop(3).startswith("BUY because ") and lines == unticked["report"].splitlines()


@pytest.mark.parametrize(
    "name, csv, decision",
    [("ticked close-only", CLOSES, "HOLD"), ("ticked first 4", FIRST[4], "BUY"), ("ticked first 7", FIRST[7], "SELL"),
     ("ticked first 3", FIRST[3], "HOLD")],
    ids=["all-11-close-only", "first-4", "first-7", "first-3-too-few"],
)
def test_ticked_shows_the_sentence_once_right_under_signal(page, tmp_path, monkeypatch, name, csv, decision):
    result = page[name]
    body = json.loads(old_body(source="csv", sample="csv", short="1", long="3", csv=csv))
    csv_text = body.pop("csv")
    assert result["sent"] == [json.dumps({**body, "explain": True, "csv": csv_text}, separators=(",", ":"))]
    assert result["box"] == {"disabled": False, "checked": True} and result["error"] is None
    # The text report is the command's --backtest --explain output, line for line (disclaimer included).
    assert result["report"] == cli_output(tmp_path, monkeypatch, csv, "--explain").rstrip("\n")
    lines = result["report"].splitlines()
    sentence = lines[3]
    assert lines[2] == f"Signal:  {decision}" and sentence.startswith(f"{decision} because ")
    # Shown once on the whole page, and nothing else differs from the same run unticked.
    assert sum(text.count(sentence) for text in result["shown"].values()) == 1
    if name == "ticked close-only":  # no candle data: the hint shows, the box stays enabled and ticked
        assert result["hint_hidden"] is False and "explain" not in result["hint"].lower()


def test_a_bad_reply_shows_the_apis_message(page):
    result = page["ticked bad"]
    with pytest.raises(web.WebError) as excinfo:  # what the API answers to exactly that body
        web.parse_request(json.loads(result["sent"][0]))
    assert json.loads(result["sent"][0])["explain"] is True and excinfo.value.status == 400
    assert result["error"] == excinfo.value.message == "--short (3) must be smaller than --long (3)"
