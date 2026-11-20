"""The "Trade list" checkbox of the backtest panel (the command's --trade-list) and its results table.

Static checks on the HTML, plus the shipped APP_JS run for real in Node against a real local server with the
small stand-in for the browser DOM of test_web_scale_out_page.py (copied, not imported). The page computes no trade
itself: it shows the reply of POST /api/backtest.

The box sits right after the "ATR stop" box, the only other checkbox. It needs no candle data: never greyed out,
and the close-only hint does not name it. It is sent (as true) only when ticked, so an unticked box sends exactly
the old request. When the reply has trade_list the "Trade list" panel shows it with the text table's columns and
cells, the open row marked unrealized, and the footer; otherwise the panel stays hidden. A bad reply shows the API's
message.

Hand cases: tests/data/c.csv (SMA 1/2, cash 1000), worked out in test_trade_list.py. Nine tests, counting each
parametrized case.
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

C_CSV = (Path(__file__).resolve().parent / "data" / "c.csv").read_text()
CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
H = {"source": "csv", "csv": C_CSV, "short": "1", "long": "2", "cash": "1000"}
FIELD_HTML = """    <div class="field">
      <label for="trade_list">Trade list</label>
      <div class="row">
        <input id="trade_list" name="trade_list" type="checkbox">
        <span class="hint" id="trade-list-hint">Also show every round trip, and a position still held at the end, as a table (the command's --trade-list). Changes no trade. Works with a close-only CSV.</span>
      </div>
    </div>
"""


def test_checkbox_sits_after_atr_stop_and_needs_no_candle_data():
    assert FIELD_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("atr_stop", "trade_list", "cooldown", "candle-hint")]
    assert order == sorted(order)
    assert INDEX_HTML.index("atr-stop-hint") < INDEX_HTML.index('<div class="field">\n      <label for="trade_list">')
    tag = re.search(r'<input id="trade_list"[^>]*>', INDEX_HTML).group(0)
    assert "checked" not in tag and "disabled" not in tag
    assert "'trade_list'" not in re.search(r"const CANDLE_CONTROLS = \[([^\]]*)\];", APP_JS).group(1)
    hint = re.search(r'<p class="hint" id="candle-hint" hidden>([^<]*)</p>', INDEX_HTML).group(1)
    assert "trade" not in hint.lower()
    assert re.search(r'<div class="panel" id="trade-list-panel" hidden>', INDEX_HTML)
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    for panel in ("scan", "wf", "pf"):  # only the backtest panel has it
        start = INDEX_HTML.index(f'<section id="{panel}-panel"')
        assert "trade_list" not in INDEX_HTML[start : INDEX_HTML.index("</section>", start)]


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
  byId['atr_stop'].checked = false;
  byId['error'].hidden = true; byId['report'].textContent = '';
  byId['source'].value = fields.source;
  for (const fn of byId['source'].listeners.change) fn();
  // Like a user: the box is ticked first, then the CSV pasted (a close-only CSV must leave it ticked).
  byId['trade_list'].checked = fields.trade_list === true;
  if ('csv' in fields) { byId['csv'].value = fields.csv; for (const fn of byId['csv'].listeners.input) fn(); }
  for (const [id, v] of Object.entries(fields)) {
    if (!['source', 'csv', 'trade_list'].includes(id) && !byId[id].disabled) byId[id].value = v;
  }
  const box = { disabled: byId['trade_list'].disabled, checked: byId['trade_list'].checked };
  for (const fn of byId['form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  const table = byId['trade-list-table'];
  return {
    sent: SENT.slice(),
    error: byId['error'].hidden ? null : byId['error'].textContent,
    panel_hidden: byId['trade-list-panel'].hidden,
    table_hidden: table.hidden,
    rows: table.tBodies[0].children.map((tr) => ({ cls: tr.className, cells: tr.children.map((td) => td.textContent) })),
    footer: byId['trade-list-footer'].textContent,
    report: byId['report'].textContent,
    hint_hidden: byId['candle-hint'].hidden,
    hint: byId['candle-hint'].textContent,
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

CASES = {  # submitted in this order, one after the other on the same page
    "ticked": {**H, "trade_list": True},
    "unticked after ticked": {**H},
    "unticked sample": {"source": "uptrend"},
    "ticked scale-out 5": {**H, "scale_out": "5", "trade_list": True},
    "ticked stop 10": {**H, "stop_loss": "10", "trade_list": True},
    "ticked close-only": {**H, "csv": CLOSES, "trade_list": True},
    "ticked fee 0.125": {**H, "fee": "0.125", "trade_list": True},  # outlay 990.125: the text says 990.12
    "ticked no trades": {**H, "cash": "5", "trade_list": True},
    "ticked bad": {**H, "short": "2", "long": "2", "trade_list": True},
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


def with_box(**fields):
    """old_body plus "trade_list": true where the page puts it (after the settings, before the CSV)."""
    csv = fields.pop("csv")
    return old_body(**fields, trade_list=True, csv=csv)


HAND = dict(source="csv", sample="csv", short="1", long="2", cash="1000")


def cli_table(tmp_path, monkeypatch, text, argv):
    """(table rows split into cells, footer) of the command's trade list for ``text`` with ``argv``."""
    (tmp_path / "p.csv").write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli_main(["p.csv", "--backtest", "--short", "1", "--long", "2", *argv, "--trade-list"]) == 0
    lines = out.getvalue().split("Trade list (bar index is 0-based)\n", 1)[1].splitlines()
    rows = lines[1:lines.index("Research aid only. Not financial advice.") - 1]
    return [line.split() for line in rows], lines[len(rows) + 1].strip()


def test_unticked_sends_exactly_the_old_request_and_shows_nothing_extra(page):
    assert page["unticked after ticked"]["sent"] == [old_body(**HAND, csv=C_CSV)]
    assert page["unticked sample"]["sent"] == [old_body()]
    for name in ("unticked after ticked", "unticked sample"):
        result = page[name]
        assert result["error"] is None and result["panel_hidden"] is True and result["rows"] == [], name
        assert "Trade list" not in result["report"], name


@pytest.mark.parametrize(
    "name, sent, csv, argv",
    [
        ("ticked", {}, C_CSV, ["--cash", "1000"]),
        ("ticked scale-out 5", {"scale_out": "5"}, C_CSV, ["--cash", "1000", "--scale-out", "5"]),
        ("ticked stop 10", {"stop_loss": "10"}, C_CSV, ["--cash", "1000", "--stop-loss", "10"]),
        ("ticked close-only", {}, CLOSES, ["--cash", "1000"]),
        ("ticked fee 0.125", {"fee": "0.125"}, C_CSV, ["--cash", "1000", "--fee", "0.125"]),
    ],
    ids=["c-csv", "scale-out-5", "stop-loss-10", "close-only", "fee-0.125-tie"],
)
def test_ticked_shows_the_command_table(page, tmp_path, monkeypatch, name, sent, csv, argv):
    result = page[name]
    assert result["sent"] == [with_box(**HAND, **sent, csv=csv)]
    assert result["box"] == {"disabled": False, "checked": True} and result["error"] is None
    assert result["panel_hidden"] is False and result["table_hidden"] is False
    rows, footer = cli_table(tmp_path, monkeypatch, csv, argv)
    assert [" ".join(r["cells"]).split() for r in result["rows"]] == rows  # the text table's cells, one for one
    assert result["footer"] == footer == "1 completed, 0 made money (0%), 1 open (unrealized)"
    open_row = result["rows"][-1]
    assert open_row["cls"] == "unrealized" and open_row["cells"][0] == open_row["cells"][2] == "open"
    assert open_row["cells"][9].endswith("(unrealized: marked at the last close, no selling costs)")
    assert all(r["cls"] == "" for r in result["rows"][:-1])
    assert "Trade list (bar index is 0-based)" in result["report"]
    if name == "ticked close-only":  # no candle data: the hint shows, the box stays enabled and ticked
        assert result["hint_hidden"] is False and "trade" not in result["hint"].lower()
    if name == "ticked fee 0.125":
        assert result["rows"][0]["cells"][5] == "990.12"  # Python's tie to even, not toFixed's 990.13


def test_no_trades_shows_the_panel_with_one_line(page):
    result = page["ticked no trades"]
    assert result["sent"] == [with_box(**{**HAND, "cash": "5"}, csv=C_CSV)]
    assert result["panel_hidden"] is False and result["table_hidden"] is True and result["rows"] == []
    assert result["footer"] == "No trades."
    assert "Trade list: no trades" in result["report"]


def test_a_bad_reply_shows_the_apis_message(page):
    result = page["ticked bad"]
    assert result["sent"] == [with_box(**{**HAND, "short": "2", "long": "2"}, csv=C_CSV)]
    with pytest.raises(web.WebError) as excinfo:  # what the API answers to exactly that body
        web.parse_request(json.loads(result["sent"][0]))
    assert excinfo.value.status == 400
    assert result["error"] == excinfo.value.message == "--short (2) must be smaller than --long (2)"
