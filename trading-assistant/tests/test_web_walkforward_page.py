"""The "Walk-forward test" panel of the web page.

Static checks on the HTML, plus the shipped APP_JS run for real in Node: its
pure helpers on their own, and the whole panel (pick a series, fill the
controls, submit) against a real local server, with a small stand-in for the
browser DOM (no browser is needed). The page must show what the walk-forward
command prints: the numbers of its --json object, formatted like its text.
"""

import json
import math
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.samples import sample_table
from trading_assistant.sweep import OVERFIT_WARNING
from trading_assistant.walkforward import format_walk_forward, summarize, walk_forward
from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")

SIDEWAYS = sample_table("sideways")[1]  # 150 seeded closes


def csv_text(closes):
    return "date,close\n" + "".join(f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes))


def text_parts(rows, summary):
    """The command's text output split into table rows (as cells), summary lines and notes."""
    lines = format_walk_forward(rows, summary).splitlines()
    table = [line.split() for line in lines[2 : 2 + len(rows)]]
    rest = lines[2 + len(rows) :]
    summary_lines = [" ".join(line.split()) for line in rest[:5]]
    notes = [line for line in rest if line.startswith("Note:")]
    return table, summary_lines, notes


# --------------------------------------------------------------------------- static page


def test_panel_and_controls_exist():
    assert '<section id="wf-panel" class="panel" aria-labelledby="wf-heading">' in INDEX_HTML
    assert '<h2 id="wf-heading">Walk-forward test</h2>' in INDEX_HTML
    for control, label in [
        ("wf-source", "Price series"),
        ("wf-csv", "CSV with a <code>close</code> column"),
        ("wf-short", "Short SMA windows"),
        ("wf-long", "Long SMA windows"),
        ("wf-train", "Train bars"),
        ("wf-test", "Test bars"),
        ("wf-step", "Step (bars)"),
        ("wf-cash", "Starting cash"),
        ("wf-fee", "Fee per trade"),
        ("wf-fee-pct", "Cost % of trade value"),
    ]:
        assert f'<label for="{control}">{label}</label>' in INDEX_HTML, control
        assert f'id="{control}"' in INDEX_HTML
    assert '<input type="file" id="wf-file" accept=".csv,text/csv,text/plain">' in INDEX_HTML
    assert '<div id="wf-error" class="error" role="alert" hidden></div>' in INDEX_HTML
    assert '<div id="wf-results" class="wf-results" hidden aria-live="polite">' in INDEX_HTML


def test_defaults_are_the_command_docstring_example():
    # python -m trading_assistant.walkforward prices.csv --short 5,10,20 --long 20,50,100 --train 250 --test 60
    for control, value in [("wf-short", "5,10,20"), ("wf-long", "20,50,100"), ("wf-train", "250"), ("wf-test", "60")]:
        assert re.search(rf'<input id="{control}"[^>]*\svalue="{re.escape(value)}"', INDEX_HTML), control
    step = re.search(r'<input id="wf-step"[^>]*>', INDEX_HTML).group(0)
    assert "value=" not in step and 'placeholder="Same as test"' in step


def test_table_headers_follow_the_text_output():
    table = INDEX_HTML.split('id="wf-table"')[1].split("</table>")[0]
    headers = re.findall(r"<th scope=\"col\"(?: class=\"num\")?>([^<]+)</th>", table)
    assert headers == ["Window", "Train bars", "Test bars", "Pair", "Train", "Test", "Buy &amp; hold", "Trades"]


def test_disclaimer_stays_visible_and_is_never_hidden():
    assert f'<p class="wf-disclaimer" id="wf-disclaimer">{DISCLAIMER}</p>' in INDEX_HTML
    assert "wf-disclaimer { display" not in STYLE_CSS
    assert "wf-disclaimer').hidden" not in APP_JS
    footer = INDEX_HTML.split("<footer>")[1].split("</footer>")[0]
    assert f'<p id="disclaimer">{DISCLAIMER}</p>' in footer


def test_ids_are_unique_and_every_id_the_script_uses_exists():
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    used = set(re.findall(r"\$\('([a-z0-9_-]+)'\)", APP_JS)) - {"param-"}
    assert {i for i in used if i.startswith("wf-")} >= {"wf-form", "wf-source", "wf-table", "wf-notes", "wf-overfit"}
    assert used <= set(ids), used - set(ids)


def test_page_rules_still_hold():
    assert not re.search(r"<script(?![^>]*\ssrc=)", INDEX_HTML)
    assert "<style" not in INDEX_HTML and ' style="' not in INDEX_HTML
    assert not re.search(r"\son\w+=", INDEX_HTML)
    assert not re.search(r"https?://", INDEX_HTML + STYLE_CSS)
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS
    assert "fetch('/api/walkforward'" in APP_JS


# --------------------------------------------------------------------------- helpers run in Node


def _extract_function(name):
    match = re.search(rf"function {name}\([^)]*\) \{{.*?\n  \}}\n", APP_JS, re.S)
    assert match, f"{name} not found in APP_JS"
    return match.group(0)


def run_node(script):
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


HELPERS = "".join(
    _extract_function(n)
    for n in ("fixed2", "pctText", "buildWfPayload", "wfRowCells", "wfCountText", "wfSummaryRows", "wfNotes")
)

# Ties at the second decimal (exact in binary: x.xx5 with a power-of-two fraction), values
# whose decimal text looks like a tie but is not (2.675 is 2.67499999...), signs, zero and -0.0,
# rounding that carries into the whole number, and large and tiny values.
PCT_VALUES = [
    0.0, -0.0, 0.125, -0.125, 0.375, 0.625, 0.875, 12.125, -12.375, 2.675, 1.005, 0.005, -0.005,
    0.0049999, -0.0049999, 0.995, 9.995, 99.995, -99.995, 0.045, 1e-20, -1e-20, 6.363199999999979,
    -5.824208526097719, 25.399999999999977, 14.816000000000006, 100.0, -100.0, 12345.675, 1e6 + 0.125,
]


@needs_node
def test_percent_text_matches_python_format_exactly():
    import random

    rng = random.Random(7)
    values = PCT_VALUES + [rng.uniform(-150, 150) for _ in range(300)]
    values += [rng.randint(-20000, 20000) / 1000 for _ in range(300)]  # three decimals: many near-ties
    script = HELPERS + f"console.log(JSON.stringify({json.dumps(values)}.map(pctText)));"
    page = run_node(script)
    expected = [f"{v:+.2f}%" for v in values]
    mismatches = [(v, p, e) for v, p, e in zip(values, page, expected) if p != e]
    assert mismatches == []
    # -0.0 keeps its sign in JSON, so the page sees it as Python does
    assert json.loads("-0.0") == 0.0 and math.copysign(1, json.loads("-0.0")) == -1


@needs_node
@pytest.mark.parametrize(
    "args",
    [
        dict(train=40, test=20),
        dict(train=40, test=20, step=10, fee=1.0, fee_pct=0.1),
        dict(train=40, test=20, step=25, cash=5000.0),
        dict(train=90, test=60),
    ],
)
def test_rows_summary_and_notes_match_the_text_output(args):
    rows = walk_forward(SIDEWAYS, [2, 3, 5], [5, 10, 20], **args)
    summary = summarize(rows)
    script = HELPERS + f"""
    const data = {json.dumps({"windows": rows, "summary": summary})};
    console.log(JSON.stringify({{
      rows: data.windows.map(wfRowCells),
      summary: wfSummaryRows(data.summary).map(([label, value]) => label + ': ' + value),
      notes: wfNotes(data.summary),
      count: wfCountText(data.windows.length),
    }}));
    """
    page = run_node(script)
    table, summary_lines, notes = text_parts(rows, summary)
    assert page["rows"] == table
    assert page["summary"] == summary_lines
    assert page["notes"] == notes
    assert page["count"] == f"({len(rows)} window{'' if len(rows) == 1 else 's'})"


@needs_node
def test_both_notes_and_one_window():
    # Hand-built summary with both notes on; and the single-window wording.
    summary = {
        "windows": 3, "compound_test_return_pct": 1.0, "compound_buy_hold_return_pct": 2.0,
        "windows_beating_buy_hold": 1, "mean_test_return_pct": 0.5, "windows_without_trades": 2,
        "test_blocks_contiguous": False,
    }
    rows = [
        {"window": k, "train_start": 0, "train_end": 10, "test_start": 10 + k, "test_end": 20 + k, "short": 2,
         "long": 5, "train_return_pct": 0.0, "test_return_pct": 0.0, "test_max_drawdown_pct": 0.0,
         "test_trades": 0, "buy_hold_return_pct": 0.0}
        for k in (1, 2, 3)
    ]
    script = HELPERS + f"console.log(JSON.stringify([wfNotes({json.dumps(summary)}), wfCountText(1), wfCountText(0)]));"
    notes, one, zero = run_node(script)
    assert notes == text_parts(rows, summary)[2]
    assert len(notes) == 2
    assert one == "(1 window)" and zero == "(0 windows)"


@needs_node
def test_payload_is_what_the_api_takes():
    script = HELPERS + """
    const sample = buildWfPayload({source: 'sideways', csv: 'ignored', short: ' 2,3 ', long: '5,10', train: '40 ',
      test: ' 20', step: '', cash: '10000', fee: undefined, fee_pct: null, maxBodyBytes: 1000});
    const csv = buildWfPayload({source: 'csv', csv: 'date,close\\n1,2\\n', short: '2', long: '5', train: '1',
      test: '1', step: '1', cash: '', fee: '0', fee_pct: '0', maxBodyBytes: 1000});
    let empty = null, big = null;
    try { buildWfPayload({source: 'csv', csv: '   ', maxBodyBytes: 1000}); } catch (e) { empty = e.message; }
    try { buildWfPayload({source: 'csv', csv: 'x'.repeat(1001), maxBodyBytes: 1000}); } catch (e) { big = e.message; }
    console.log(JSON.stringify({sample, csv, empty, big}));
    """
    out = run_node(script)
    assert out["sample"] == {
        "source": "sample", "sample": "sideways", "short": "2,3", "long": "5,10", "train": "40", "test": "20",
        "step": "", "cash": "10000", "fee": "", "fee_pct": "",
    }
    assert out["csv"] == {
        "source": "csv", "short": "2", "long": "5", "train": "1", "test": "1", "step": "1", "cash": "",
        "fee": "0", "fee_pct": "0", "csv": "date,close\n1,2\n",
    }
    assert out["empty"] == "Paste or upload a CSV first, or pick a sample series."
    assert out["big"] == f"The CSV is {1001:,} characters; the limit is {1000:,}."


# --------------------------------------------------------------------------- the whole panel in Node


FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;  // elements whose content in the HTML is plain text
const PAGE_VALUES = %(values)s;  // value="" of inputs in the HTML
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
global.fetch = (url, opts) => realFetch(BASE + url, opts);
"""

DRIVE = r"""
const settle = () => new Promise((r) => setTimeout(r, 50));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
async function submitWf(fields, upload) {
  if (upload) {
    byId['wf-file'].files = [{ name: upload[0], text: upload[1], size: upload[1].length }];
    for (const fn of byId['wf-file'].listeners.change) fn();
    await settle();
  }
  for (const [id, v] of Object.entries(fields)) byId[id].value = v;
  for (const fn of byId['wf-source'].listeners.change) fn();
  for (const fn of byId['wf-form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    resultsHidden: byId['wf-results'].hidden,
    csvBlockHidden: byId['wf-csv-block'].hidden,
    error: byId['wf-error'].hidden ? null : byId['wf-error'].textContent,
    count: byId['wf-count'].textContent,
    rows: cells('wf-table'),
    tones: byId['wf-table'].tBodies[0].children.map((tr) => tr.children.slice(1).map((c) => c.className)),
    summary: cells('wf-summary-table'),
    notes: byId['wf-notes'].children.map((li) => li.textContent),
    overfit: byId['wf-overfit'].textContent,
    disclaimer: byId['wf-disclaimer'].textContent,
    status: byId['wf-status'].textContent,
    options: byId['wf-source'].children.map((o) => o.attrs.value),
    csvValue: byId['wf-csv'].value,
    csvHint: byId['wf-csv-hint'].textContent,
  };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const [fields, upload] of %(cases)s) out.push(await submitWf(fields, upload));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def base_url():
    server = web.BacktestServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def drive_page(base_url, cases):
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
    script = (
        FAKE_DOM
        % {
            "ids": json.dumps([[i, t] for t, i in ids]),
            "texts": json.dumps(texts),
            "values": json.dumps(values),
            "base": json.dumps(base_url),
        }
        + APP_JS
        + DRIVE % {"cases": json.dumps(cases)}
    )
    return run_node(script)


FIELDS = {
    "wf-source": "sideways", "wf-short": "2,3,5", "wf-long": "5,10,20", "wf-train": "40", "wf-test": "20",
    "wf-step": "", "wf-cash": "10000", "wf-fee": "0", "wf-fee-pct": "0",
}
FLAGS = ["--short", "2,3,5", "--long", "5,10,20", "--train", "40", "--test", "20"]


def cli_json(tmp_path, capsys, text, flags):
    path = tmp_path / "prices.csv"
    path.write_text(text)
    assert walkforward_main([str(path), *flags, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def cli_error(tmp_path, capsys, text, flags):
    path = tmp_path / "prices.csv"
    path.write_text(text)
    try:
        code = walkforward_main([str(path), *flags])
    except SystemExit as exc:
        code = exc.code
    err = capsys.readouterr().err.strip().splitlines()[-1]
    assert code in (1, 2)
    for prefix in ("trading_assistant.walkforward: error: ", "Error: "):
        if err.startswith(prefix):
            return err[len(prefix) :]
    return err


@needs_node
@pytest.mark.parametrize(
    "fields, flags",
    [
        ({}, []),
        ({"wf-step": "10", "wf-fee": "1", "wf-fee-pct": "0.1"}, ["--step", "10", "--fee", "1", "--fee-pct", "0.1"]),
        ({"wf-step": "25", "wf-cash": "5000"}, ["--step", "25", "--cash", "5000"]),
        ({"wf-short": " 3, 2", "wf-long": "20,5"}, ["--short", "3,2", "--long", "20,5"]),
    ],
)
def test_panel_shows_what_the_command_prints(base_url, tmp_path, capsys, fields, flags):
    [page] = drive_page(base_url, [[{**FIELDS, **fields}, None]])
    data = cli_json(tmp_path, capsys, csv_text(SIDEWAYS), [*FLAGS, *flags])
    table, summary_lines, notes = text_parts(data["windows"], data["summary"])
    assert page["error"] is None and page["resultsHidden"] is False
    assert page["rows"] == table
    assert [f"{label}: {value}" for label, value in page["summary"]] == summary_lines
    assert page["notes"] == notes
    assert page["count"] == f"({len(data['windows'])} windows)"
    assert page["overfit"] == data["overfit_warning"] == OVERFIT_WARNING
    assert page["disclaimer"] == data["disclaimer"] == DISCLAIMER
    assert page["status"].startswith("Done in ")


@needs_node
def test_panel_colours_follow_the_sign(base_url):
    [page] = drive_page(base_url, [[FIELDS, None]])
    rows = walk_forward(SIDEWAYS, [2, 3, 5], [5, 10, 20], 40, 20)

    def tone(v):
        return "num" + (" good" if v > 0 else " bad" if v < 0 else "")

    assert page["tones"] == [
        ["", "", "", tone(r["train_return_pct"]), tone(r["test_return_pct"]), tone(r["buy_hold_return_pct"]), "num"]
        for r in rows
    ]


@needs_node
def test_panel_with_pasted_and_uploaded_csv(base_url, tmp_path, capsys):
    closes = sample_table("random_walk")[1][:300]
    text = csv_text(closes)
    settings = {"wf-short": "5,10", "wf-long": "20,50", "wf-train": "120", "wf-test": "40"}
    pasted, uploaded = drive_page(
        base_url,
        [
            [{**FIELDS, **settings, "wf-source": "csv", "wf-csv": text}, None],
            [{**FIELDS, **settings, "wf-source": "csv"}, ["prices.csv", text]],
        ],
    )
    data = cli_json(tmp_path, capsys, text, ["--short", "5,10", "--long", "20,50", "--train", "120", "--test", "40"])
    table, summary_lines, notes = text_parts(data["windows"], data["summary"])
    for page in (pasted, uploaded):
        assert page["error"] is None and page["csvBlockHidden"] is False
        assert page["rows"] == table
        assert [f"{label}: {value}" for label, value in page["summary"]] == summary_lines
        assert page["notes"] == notes
    assert uploaded["csvValue"] == text
    assert uploaded["csvHint"] == f"Loaded prices.csv ({len(text):,} bytes)."


@needs_node
def test_panel_lists_every_sample_and_own_csv(base_url):
    [page] = drive_page(base_url, [[FIELDS, None]])
    from trading_assistant.samples import SAMPLES

    assert page["options"] == [*SAMPLES, "csv"]
    assert page["csvBlockHidden"] is True


@needs_node
def test_panel_errors(base_url, tmp_path, capsys):
    cases = [
        [{**FIELDS, "wf-train": "400"}, None],  # too few bars: the command's data error
        [{**FIELDS, "wf-short": "9", "wf-long": "5"}, None],  # no pair: the command's usage error
        [{**FIELDS, "wf-short": "2,x"}, None],  # bad list: argparse's wording
        [{**FIELDS, "wf-step": "0"}, None],
        [{**FIELDS, "wf-source": "csv", "wf-csv": "  "}, None],  # nothing pasted: checked on the page
        [{**FIELDS, "wf-source": "csv", "wf-csv": "date,close\n2026-01-01,10\n2026-01-02,-1\n", "wf-train": "1",
          "wf-test": "1", "wf-short": "1", "wf-long": "2"}, None],
    ]
    few, no_pair, bad_list, step0, empty, bad_price = drive_page(base_url, cases)
    text = csv_text(SIDEWAYS)
    few_flags = ["--short", "2,3,5", "--long", "5,10,20", "--train", "400", "--test", "20"]
    assert few["error"] == cli_error(tmp_path, capsys, text, few_flags)
    assert few["error"].startswith("not enough prices for a walk-forward window")
    no_pair_flags = ["--short", "9", "--long", "5", "--train", "40", "--test", "20"]
    assert no_pair["error"] == cli_error(tmp_path, capsys, text, no_pair_flags)
    bad_list_flags = ["--short", "2,x", "--long", "5,10,20", "--train", "40", "--test", "20"]
    assert bad_list["error"] == cli_error(tmp_path, capsys, text, bad_list_flags)
    assert step0["error"] == "--step must be at least 1"
    assert empty["error"] == "Paste or upload a CSV first, or pick a sample series."
    assert bad_price["error"] == "bar 1: price must be positive, got -1.0"
    for page in (few, no_pair, bad_list, step0, empty, bad_price):
        assert page["resultsHidden"] is True
        assert page["status"] == ""
