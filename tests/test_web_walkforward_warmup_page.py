"""The walk-forward panel's "Warm up" box (``warmup: true``, the command's ``--warmup``).

Static checks on the page, the panel's helpers run in Node, and the whole panel driven in Node against a
real local server (as in test_web_walkforward_page.py). The page must show what the command prints: with
a ticked box its --warmup header line and no-trades note, unticked exactly what it showed before.
Case: tests/data/wf.csv, short 2, long 3, train 7, test 4, cash 1000: two 4-bar test blocks. Without
warm-up neither can trade (2 of 2 without trades, the old note); with it window 1 trades and window 2
does not (its only BUY crossing is on bar 14, its last bar): 1 of 2, the warm-up note.
"""

import hashlib
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from trading_assistant.cli import load_price_table
from trading_assistant.walkforward import format_walk_forward, json_data, main as walkforward_main, summarize, walk_forward
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
DATA = Path(__file__).resolve().parent / "data"
WF = str(DATA / "wf.csv")
WF_TEXT = (DATA / "wf.csv").read_text()
CLOSES = load_price_table(WF)[1]

# sha256 of the page, script and stylesheet just before the box was added.
OLD_SHA256 = {
    "INDEX_HTML": "73e9bf57143d59acd4b610ee05537c489e439f4132acd6e991747639ce467e71",
    "APP_JS": "933592223ec0617da4e025c60c6f7be7bbd8bd0eaf10674ff3f42dd102ae3801",
    "STYLE_CSS": "65885973a502760713898a2f6d6a5da42f55927ab38abedcf9daf901d6738550",
}
FIELD_HTML = """      <div class="field">
        <label for="wf-warmup">Warm up</label>
        <div class="row">
          <input id="wf-warmup" name="warmup" type="checkbox">
          <span class="hint" id="wf-warmup-hint">Warm the moving averages up on the chosen pair's long bars just before each test block (the command's --warmup). The pair is still chosen on the train bars only; trades and scores still count only inside the test block.</span>
        </div>
      </div>
"""
LINE_HTML = """    <p class="hint" id="wf-warmup-line" hidden></p>
"""
# (new, old) pieces of the script: undoing them must give back the old script exactly.
JS_CHANGES = [
    ("""    // Warm up: sent (as true) only when ticked, so an unticked box sends exactly the old request.
    if (fields.warmup === true) payload.warmup = true;
""", ""),
    ("""  function wfWarmupLine(n) {
    // the command's header line with --warmup (format_walk_forward, HEADER_RUN_WARMUP), word for word
    return 'Walk-forward: ' + n + (n === 1 ? ' window' : ' windows') + '; each SMA crossover pair was chosen on' +
      ' its train bars only, then traded and scored on the test bars after them, with its moving averages' +
      ' warmed up on up to long bars just before each test block';
  }
  function wfNotes(s, warmup) {
    // the same notes, in the same order, as the command's text output; warmup: the reply had "warmup": true
""", """  function wfNotes(s) {
    // the same notes, in the same order, as the command's text output
"""),
    ("""        ' block (' + (warmup === true
          ? 'no BUY crossover on a test bar before its last, or, near the start of the data, fewer than long bars' +
            ' before the block to warm up'
          : 'no crossover, or fewer than long + 2 test bars to warm up') +
        '); their 0.00% says nothing about the pair.');""",
     """        ' block (no crossover, or fewer than long + 2 test bars to warm up); their 0.00% says nothing about the pair.');"""),
    ("""    // Warm up: only a reply with "warmup": true gets the header line and the warm-up note wording; any other
    // reply leaves the line hidden and empty, so the panel shows exactly what it did before.
    const warmup = data.warmup === true;
    $('wf-warmup-line').textContent = warmup ? wfWarmupLine(data.summary.windows) : '';
    $('wf-warmup-line').hidden = !warmup;
""", ""),
    ("wfNotes(data.summary, warmup)", "wfNotes(data.summary)"),
    ("""        warmup: $('wf-warmup').checked === true,
""", ""),
]
ARGS = ["--short", "2", "--long", "3", "--train", "7", "--test", "4", "--cash", "1000"]
FIELDS = {"wf-source": "csv", "wf-csv": WF_TEXT, "wf-short": "2", "wf-long": "3", "wf-train": "7", "wf-test": "4",
          "wf-step": "", "wf-cash": "1000", "wf-fee": "0", "wf-fee-pct": "0"}
REQUEST = {"source": "csv", "short": "2", "long": "3", "train": "7", "test": "4", "step": "", "cash": "1000",
           "fee": "0", "fee_pct": "0", "csv": WF_TEXT}  # what the unticked panel sent before the box existed


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def command_text(capsys, *extra):
    assert walkforward_main([WF, *ARGS, *extra]) == 0
    return capsys.readouterr().out.splitlines()


def run_node(script):
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def helpers(*names):
    return "".join(re.search(rf"function {n}\([^)]*\) \{{.*?\n  \}}\n", APP_JS, re.S).group(0) for n in names)


# --------------------------------------------------------------------------- static page


def test_box_is_the_last_setting_unticked_and_nothing_else_changed():
    assert FIELD_HTML in INDEX_HTML and LINE_HTML in INDEX_HTML
    order = [INDEX_HTML.index(f'id="{i}"') for i in ("wf-fee-pct", "wf-warmup", "wf-run", "wf-warmup-line", "wf-count")]
    assert order == sorted(order)  # after the costs, before Run; the line above the windows
    # Take the box, the line and the script's warm-up pieces out again: the old page, script and style exactly.
    old_html = INDEX_HTML.replace(FIELD_HTML, "", 1).replace(LINE_HTML, "", 1)
    old_js = APP_JS
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
    old_html = re.sub(r'    <div class="field">\n      <label for="explain">.*?</div>\n    </div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // explain: sent \(as true\).*?payload\.explain = true;\n", "", old_js, count=1, flags=re.S)
    # Undo the add-on fields (added after this test was written).
    old_html = re.sub(r'    <div class="field">\n      <label for="add_on">.*?<label for="max_adds">.*?</div>\n', "", old_html, count=1, flags=re.S)
    old_js = re.sub(r"    // add-on and max adds: .*?payload\.max_adds = maxAdds;\n", "", old_js, count=1, flags=re.S)
    old_js = old_js.replace("      (s.add_on_buys === undefined ? '' : ', ' + s.add_on_buys + ' add-on buys, ' + s.add_on_skipped_buys + ' add-ons skipped') +\n", "", 1)
    for new, old in JS_CHANGES:
        assert old_js.count(new) == 1, new
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
    assert (sha(old_html), sha(old_js), sha(STYLE_CSS)) == (
        OLD_SHA256["INDEX_HTML"], OLD_SHA256["APP_JS"], OLD_SHA256["STYLE_CSS"])


# --------------------------------------------------------------------------- helpers run in Node


@needs_node
def test_payload_has_warmup_only_when_ticked():
    script = helpers("buildWfPayload") + """
    const base = {source: 'sideways', short: '2', long: '5', train: '40', test: '20', step: '', cash: '', fee: '',
      fee_pct: '', maxBodyBytes: 1000};
    console.log(JSON.stringify([true, false, undefined, 'true', 1].map((w) => buildWfPayload({...base, warmup: w}))));
    """
    ticked, *others = run_node(script)
    old = {"source": "sample", "sample": "sideways", "short": "2", "long": "5", "train": "40", "test": "20",
           "step": "", "cash": "", "fee": "", "fee_pct": ""}
    assert ticked == {**old, "warmup": True} and list(ticked)[-1] == "warmup"
    assert others == [old] * 4  # only a real true (a ticked box) sends it


@needs_node
def test_header_line_and_notes_are_the_command_words(capsys):
    warm = walk_forward(CLOSES, [2], [3], 7, 4, cash=1000, warmup=True)
    cold = walk_forward(CLOSES, [2], [3], 7, 4, cash=1000)
    one = walk_forward(CLOSES, [1], [3], 12, 6, cash=1000, warmup=True)
    cases = [(warm, True), (cold, False), (cold, None), (one, True)]
    script = helpers("wfWarmupLine", "wfNotes") + f"""
    const cases = {json.dumps([[summarize(rows), w] for rows, w in cases])};
    console.log(JSON.stringify(cases.map(([s, w]) => [wfWarmupLine(s.windows), w === null ? wfNotes(s) : wfNotes(s, w)])));
    """
    page = run_node(script)
    for (rows, w), (line, notes) in zip(cases, page):
        text = format_walk_forward(rows, summarize(rows), warmup=bool(w)).splitlines()
        assert notes == [t for t in text if t.startswith("Note:")]
        if w:
            assert line == text[0]
    assert [len(n) for _, n in page] == [1, 1, 1, 0]  # the no-trades note in the two-window cases only
    assert "no BUY crossover" in page[0][1][0] and "fewer than long + 2" in page[1][1][0] == page[2][1][0]


# --------------------------------------------------------------------------- the whole panel in Node

FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;
const PAGE_VALUES = %(values)s;
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
  const n = new Node_(tag); n.id = id; n._text = PAGE_TEXT[id] || ''; n.value = PAGE_VALUES[id] || ''; byId[id] = n;
}
for (const id of %(hidden)s) byId[id].hidden = true;  // hidden in the HTML
const text = (t) => { const n = new Node_('#text'); n._text = String(t); return n; };
global.document = {
  getElementById: (id) => byId[id] || null,
  createElement: (t) => new Node_(t), createElementNS: (ns, t) => new Node_(t), createTextNode: text,
  documentElement: new Node_('html'), body: new Node_('body'),
};
global.window = { matchMedia: () => ({ matches: false }), addEventListener() {} };
global.localStorage = { getItem: () => null, setItem() {} };
const BASE = %(base)s;
const realFetch = fetch;
const sent = [];
global.fetch = (url, opts) => { if (url === '/api/walkforward') sent.push(opts.body); return realFetch(BASE + url, opts); };
"""

DRIVE = r"""
const settle = () => new Promise((r) => setTimeout(r, 50));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const [fields, ticked] of %(cases)s) {
    sent.length = 0;
    for (const [id, v] of Object.entries(fields)) byId[id].value = v;
    byId['wf-warmup'].checked = ticked;
    for (const fn of byId['wf-source'].listeners.change) fn();
    for (const fn of byId['wf-form'].listeners.submit) await fn({ preventDefault() {} });
    await settle();
    out.push({
      sent: sent.slice(),
      error: byId['wf-error'].hidden ? null : byId['wf-error'].textContent,
      resultsHidden: byId['wf-results'].hidden,
      line: byId['wf-warmup-line'].textContent, lineHidden: byId['wf-warmup-line'].hidden,
      rows: cells('wf-table'), summary: cells('wf-summary-table'),
      notes: byId['wf-notes'].children.map((li) => li.textContent),
    });
  }
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


def drive_page(base_url, cases, replies=None):
    """Drive the panel; with ``replies``, POST /api/walkforward answers them in turn (200) instead of the server."""
    tags = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    hidden = re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*\shidden[\s>]', INDEX_HTML)
    script = FAKE_DOM % {
        "ids": json.dumps([[i, t] for t, i in tags]),
        "texts": json.dumps(dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))),
        "values": json.dumps(dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))),
        "hidden": json.dumps(hidden),
        "base": json.dumps(base_url),
    }
    if replies is not None:
        script += f"""
const REPLIES = {json.dumps(replies)};
const serverFetch = global.fetch;
global.fetch = (url, opts) => url === '/api/walkforward'
  ? Promise.resolve(new Response(JSON.stringify(REPLIES.shift()), {{status: 200}}))
  : serverFetch(url, opts);
"""
    script += APP_JS + DRIVE % {"cases": json.dumps(cases)}
    return run_node(script)


@needs_node
@pytest.mark.parametrize("ticked", [False, True], ids=["unticked", "ticked"])
def test_panel_shows_what_the_command_prints(base_url, capsys, ticked):
    [page] = drive_page(base_url, [[FIELDS, ticked]])
    text = command_text(capsys, *(["--warmup"] if ticked else []))
    [body] = page["sent"]
    request = json.loads(body)
    assert request == ({**REQUEST, "warmup": True} if ticked else REQUEST)
    assert list(request) == list(REQUEST) + (["warmup"] if ticked else [])
    assert page["error"] is None and page["resultsHidden"] is False
    assert page["rows"] == [line.split() for line in text[2:4]]
    assert [f"{label}: {value}" for label, value in page["summary"]] == [" ".join(t.split()) for t in text[4:9]]
    assert page["notes"] == [t for t in text if t.startswith("Note:")]
    if ticked:
        assert page["lineHidden"] is False and page["line"] == text[0]
        assert [r[-1] for r in page["rows"]] == ["1", "0"] and "no BUY crossover" in page["notes"][0]
    else:
        assert page["lineHidden"] is True and page["line"] == ""
        assert [r[-1] for r in page["rows"]] == ["0", "0"] and "fewer than long + 2" in page["notes"][0]


@needs_node
def test_ticked_panel_shows_the_api_error_and_a_later_unticked_run_drops_the_line(base_url):
    ticked, bad, unticked = drive_page(base_url, [[FIELDS, True], [{**FIELDS, "wf-train": "0"}, True], [FIELDS, False]])
    assert ticked["lineHidden"] is False
    # The API's own message, shown in the panel's error box as for any other field.
    assert json.loads(bad["sent"][0])["warmup"] is True
    assert bad["error"] == "--train must be at least 1"
    # A later unticked run: the line from the ticked run goes away and the old note wording comes back.
    assert unticked["error"] is None and unticked["lineHidden"] is True and unticked["line"] == ""
    assert "fewer than long + 2" in unticked["notes"][0]


@needs_node
def test_a_reply_whose_warmup_is_not_exactly_true_is_shown_as_without_it(base_url, capsys):
    # The warmed-up reply of the ticked case, with "warmup" swapped for anything but true: the page shows its
    # numbers, but neither the header line nor the warm-up note wording (data.warmup === true only).
    rows = walk_forward(CLOSES, [2], [3], 7, 4, cash=1000, warmup=True)
    values = [1, "true", "yes", 0, False, None]
    replies = [{**json_data(rows, summarize(rows), warmup=True), "warmup": v} for v in values]
    pages = drive_page(base_url, [[FIELDS, True]] * len(values), replies=replies)
    cold_note = [t for t in format_walk_forward(rows, summarize(rows)).splitlines() if t.startswith("Note:")]
    for value, page in zip(values, pages):
        assert page["error"] is None and page["resultsHidden"] is False, value
        assert (page["lineHidden"], page["line"]) == (True, ""), value
        assert [r[-1] for r in page["rows"]] == ["1", "0"], value  # the reply's own (warmed-up) numbers
        assert page["notes"] == cold_note, value
        assert "fewer than long + 2" in page["notes"][0], value
