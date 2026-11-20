"""The walk-forward panel's strategy picker: the shipped APP_JS run in Node against a real local server.

Uses the stand-in DOM of test_web_walkforward_page.py, plus the table's header row (to see the Pair/Params
switch) and input values set through attributes (the parameter fields are built with el()).
tests/data/wf_page_requests_before_strategy.json holds the request bodies the panel sent, byte for byte, for six
sets of fields before the picker existed (git 924f482).
"""

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from test_web_walkforward_page import FAKE_DOM
from trading_assistant.strategies import STRATEGIES
from trading_assistant.walkforward import format_walk_forward, param_value_text
from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
DATA = Path(__file__).resolve().parent / "data"
BEFORE = json.loads((DATA / "wf_page_requests_before_strategy.json").read_text())
WF_TEXT = (DATA / "wf.csv").read_text()
# The worked example: 20 closes dated from 2026-05-01.
EX20 = "date,close\n" + "".join(f"2026-05-{i + 1:02d},{c}\n" for i, c in enumerate(
    [10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 13, 12, 11, 13, 16, 17, 15, 14, 16]))

EXTRA_DOM = r"""
const setAttr = Node_.prototype.setAttribute;
Node_.prototype.setAttribute = function (k, v) { setAttr.call(this, k, v); if (k === 'value') this.value = String(v); };
byId['wf-table'].tHead = { rows: [{ cells: ['Window', 'Train bars', 'Test bars', 'Pair', 'Train', 'Test', 'Buy & hold',
  'Trades'].map((t) => { const n = new Node_('th'); n._text = t; return n; }) }] };
const SENT = [];
const forward = global.fetch;
global.fetch = (url, opts) => { if (url === '/api/walkforward') SENT.push(opts.body); return forward(url, opts); };
const settle = () => new Promise((r) => setTimeout(r, 50));
const paramInputs = () => Object.fromEntries(byId['wf-strategy-params'].children.map((f) => [f.children[0].textContent, f.children[1]]));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
async function step({ strategies, fields, params, warmup }) {
  for (const name of strategies || []) {
    byId['wf-strategy'].value = name;
    for (const fn of byId['wf-strategy'].listeners.change) fn();
  }
  const inputs = paramInputs();
  const ui = {
    options: byId['wf-strategy'].children.map((o) => o.attrs.value), hint: byId['wf-strategy-hint'].textContent,
    blockHidden: byId['wf-strategy-params-block'].hidden, shortHidden: byId['wf-short-field'].hidden,
    longHidden: byId['wf-long-field'].hidden,
    fields: Object.fromEntries(Object.entries(inputs).map(([k, input]) => [k, input.value])),
    ids: Object.fromEntries(Object.entries(inputs).map(([k, input]) => [k, input.attrs.id])),
  };
  for (const [key, v] of Object.entries(params || {})) inputs[key].value = v;
  for (const [id, v] of Object.entries(fields || {})) byId[id].value = v;
  byId['wf-warmup'].checked = warmup === true;
  SENT.length = 0;
  for (const fn of byId['wf-source'].listeners.change) fn();
  for (const fn of byId['wf-form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return { ui, sent: SENT.slice(), error: byId['wf-error'].hidden ? null : byId['wf-error'].textContent,
    resultsHidden: byId['wf-results'].hidden, head: byId['wf-table'].tHead.rows[0].cells[3].textContent,
    rows: cells('wf-table'), summary: cells('wf-summary-table'), notes: byId['wf-notes'].children.map((li) => li.textContent),
    line: byId['wf-warmup-line'].hidden ? null : byId['wf-warmup-line'].textContent, status: byId['wf-status'].textContent };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const s of %(steps)s) out.push(await step(s));
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


def drive(base_url, steps):
    """Run the page once and take each step in turn (pick strategies, fill fields, submit); what it showed."""
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
    script = FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                         "values": json.dumps(values), "base": json.dumps(base_url)}
    done = subprocess.run(["node", "-e", script + APP_JS + EXTRA_DOM % {"steps": json.dumps(steps)}],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def command_text(tmp_path, text, argv):
    path = tmp_path / "prices.csv"
    path.write_text(text)
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert walkforward_main([str(path), *argv]) == 0
    return out.getvalue().splitlines()


def shown_like_the_text(page, lines):
    """The panel's header cell, rows, summary and notes against the command's text lines."""
    rows = [line.split() for line in lines[2:] if re.match(r"\s+\d+\s+\d+-\d+", line)]
    assert lines[1].split()[5] == page["head"]  # Window, Train bars, Test bars, then Pair or Params
    assert page["rows"] == rows
    rest = lines[2 + len(rows):]
    assert [f"{label}: {value}" for label, value in page["summary"]] == [" ".join(line.split()) for line in rest[:5]]
    assert page["notes"] == [line for line in rest if line.startswith("Note:")]


@needs_node
def test_sma_cross_sends_exactly_the_old_requests(base_url):
    # Each recorded set of fields, with the picker untouched, with sma_cross picked, and with another strategy
    # picked and then sma_cross again: the bodies are the old ones, byte for byte.
    cases = BEFORE["cases"]
    for way in ([], ["sma_cross"], ["hull_trend", "sma_cross"]):
        steps = [{"strategies": way, "fields": {k: v for k, v in c.items() if k != "wf-warmup"},
                  "warmup": c.get("wf-warmup") is True} for c in cases]
        pages = drive(base_url, steps)
        assert [p["sent"] for p in pages] == [[body] for body in BEFORE["requests"]], way
        assert all(p["head"] == "Pair" for p in pages if p["error"] is None)


@needs_node
def test_picking_a_strategy_swaps_the_fields(base_url):
    zscore, back = drive(base_url, [{"strategies": ["zscore_reversion"], "fields": {"wf-source": "sideways"}},
                                    {"strategies": ["sma_cross"]}])
    ui = zscore["ui"]
    assert ui["options"] == list(STRATEGIES)
    assert ui["hint"] == STRATEGIES["zscore_reversion"][2] + "."
    assert (ui["blockHidden"], ui["shortHidden"], ui["longHidden"]) == (False, True, True)
    # One text field per parameter holding its default (as JSON gives it to the page: -2.0 is -2).
    assert ui["fields"] == {"window": "20", "entry": "-2", "exit": "0"}
    assert ui["ids"] == {"window": "wf-param-window", "entry": "wf-param-entry", "exit": "wf-param-exit"}
    assert json.loads(zscore["sent"][0]) == {"source": "sample", "sample": "sideways", "train": "250", "test": "60",
                                             "step": "", "cash": "10000", "fee": "0", "fee_pct": "0",
                                             "strategy": "zscore_reversion"}  # all defaults: no grid, no params
    assert (back["ui"]["blockHidden"], back["ui"]["shortHidden"], back["ui"]["fields"]) == (True, False, {})
    assert '<div class="field" id="wf-short-field">' in INDEX_HTML and '<select id="wf-strategy" name="strategy">' in INDEX_HTML


@needs_node
def test_payload_lists_go_in_grid_and_other_changes_in_params():
    fn = re.search(r"function buildWfPayload\([^)]*\) \{.*?\n  \}\n", APP_JS, re.S).group(0)
    script = fn + """
    const base = {source: 'sideways', short: '5', long: '9', train: '40', test: '20', step: '', cash: '', fee: '',
      fee_pct: '', maxBodyBytes: 1000};
    console.log(JSON.stringify([
      buildWfPayload({...base, strategy: 'momentum', warmup: true, defaults: {window: 20, threshold: 0},
                      params: {window: ' 3, 6 ', threshold: '0.0'}}),
      buildWfPayload({...base, strategy: 'zscore_reversion', defaults: {window: 20, entry: -2, exit: 0},
                      params: {window: '', entry: '-1.5', exit: 'x'}}),
      buildWfPayload({...base, strategy: 'sma_cross', params: {short: '1,2'}}),
      buildWfPayload({...base, strategy: '', params: {short: '1,2'}, warmup: true}),
    ]));
    """
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    momentum, zscore, sma, none = json.loads(done.stdout)
    common = {"source": "sample", "sample": "sideways", "train": "40", "test": "20", "step": "", "cash": "", "fee": "",
              "fee_pct": ""}
    assert momentum == {**common, "strategy": "momentum", "grid": ["window=3, 6"], "warmup": True}
    assert list(momentum)[-1] == "warmup"  # threshold 0.0 equals the default 0: left out
    assert zscore == {**common, "strategy": "zscore_reversion", "params": ["entry=-1.5", "exit=x"]}  # x: the server's message
    assert sma == {**common, "short": "5", "long": "9"}  # sma_cross (or nothing picked): the old request
    assert none == {**common, "short": "5", "long": "9", "warmup": True}


@needs_node
def test_panel_shows_what_the_command_prints_for_a_strategy(base_url, tmp_path):
    example, momentum = drive(base_url, [
        {"strategies": ["breakout"], "params": {"window": "2,3"},
         "fields": {"wf-source": "csv", "wf-csv": EX20, "wf-train": "8", "wf-test": "6", "wf-cash": "1000"}},
        {"strategies": ["momentum"], "params": {"window": "4", "threshold": "0,5"}, "warmup": True,
         "fields": {"wf-source": "csv", "wf-csv": WF_TEXT, "wf-train": "4", "wf-test": "7", "wf-cash": "1000"}},
    ])
    assert json.loads(example["sent"][0])["grid"] == ["window=2,3"] and "params" not in json.loads(example["sent"][0])
    lines = command_text(tmp_path, EX20, ["--strategy", "breakout", "--grid", "window=2,3", "--train", "8", "--test",
                                          "6", "--cash", "1000"])
    shown_like_the_text(example, lines)
    assert example["head"] == "Params" and [r[3] for r in example["rows"]] == ["window=3", "window=2"]
    assert example["line"] is None  # no header line without warm-up, as for the SMA pairs
    assert json.loads(momentum["sent"][0])["params"] == ["window=4"] and json.loads(momentum["sent"][0])["grid"] == [
        "threshold=0,5"]
    lines = command_text(tmp_path, WF_TEXT, ["--strategy", "momentum", "--param", "window=4", "--grid", "threshold=0,5",
                                             "--train", "4", "--test", "7", "--cash", "1000", "--warmup"])
    shown_like_the_text(momentum, lines)
    assert momentum["line"] == lines[0]


@needs_node
def test_params_cells_write_numbers_as_the_command_does():
    import random

    rng = random.Random(3)
    values = [0, 0.0, -0.0, -2.0, 0.5, 1e-05, 0.0001, 2.5e-7, 1e15, 1e16, 12345.678, -0.1, 3, 70, 1.5e16, 123456789.125]
    values += [rng.uniform(-100, 100) for _ in range(200)] + [rng.randint(-5, 5) / 4 for _ in range(50)]
    fn = re.search(r"function wfNum\([^)]*\) \{.*?\n  \}\n", APP_JS, re.S).group(0)
    done = subprocess.run(["node", "-e", fn + f"console.log(JSON.stringify({json.dumps(values)}.map(wfNum)));"],
                          capture_output=True, text=True, timeout=60)
    assert json.loads(done.stdout) == [param_value_text(v) for v in values]
    rows = [{"window": 1, "train_start": 0, "train_end": 4, "test_start": 4, "test_end": 8, "params": {"window": 4,
             "threshold": 0.0}, "train_return_pct": 0.0, "test_return_pct": 0.0, "test_max_drawdown_pct": 0.0,
             "test_trades": 0, "buy_hold_return_pct": 0.0}]
    text = format_walk_forward(rows, {"windows": 1, "compound_test_return_pct": 0, "compound_buy_hold_return_pct": 0,
                                      "mean_test_return_pct": 0, "windows_beating_buy_hold": 0, "windows_without_trades": 0,
                                      "test_blocks_contiguous": True}, strategy="momentum")
    assert text.splitlines()[2].split()[3] == "window=4,threshold=0"


@needs_node
def test_panel_shows_the_400_and_413_messages_then_an_sma_run_as_before(base_url):
    bad, big, sma = drive(base_url, [
        {"strategies": ["breakout"], "params": {"window": "2,0,3"}, "fields": {"wf-source": "sideways", "wf-train": "40",
                                                                              "wf-test": "20"}},
        {"strategies": ["zscore_reversion"], "params": {"window": "5,10,20"}, "warmup": True,
         "fields": {"wf-source": "random_walk", "wf-train": "240", "wf-test": "60"}},
        {"strategies": ["sma_cross"], "fields": {"wf-source": "sideways", "wf-short": "2,3", "wf-long": "5,10",
                                                 "wf-train": "40", "wf-test": "20"}},
    ])
    assert bad["error"] == "window must be a whole number of at least 1, got 0"
    assert big["error"] == (
        "this walk-forward is too big for the web page (8 windows x 3 zscore_reversion parameter sets, 301,867"
        " bar-steps; the limit is 300,000); use fewer parameter sets, a larger step or shorter blocks, or run"
        " python -m trading_assistant.walkforward")
    for page in (bad, big):
        assert page["resultsHidden"] is True and page["status"] == ""
    assert sma["error"] is None and sma["head"] == "Pair" and all("/" in r[3] for r in sma["rows"])
    assert "strategy" not in json.loads(sma["sent"][0])
