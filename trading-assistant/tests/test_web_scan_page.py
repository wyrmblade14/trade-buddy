"""The "Scan several files" panel of the web page.

Static checks on the HTML, plus the shipped APP_JS run for real in Node: its
pure helpers on their own, and the whole panel (pick files, fill the controls,
submit) against a real local server, with a small stand-in for the browser
DOM (no browser is needed). The page must show what --scan --json prints.
"""

import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")

RISE_FLAT_JUMP = [100.0 + i for i in range(50)] + [149.0] * 9 + [155.0]  # -2
MIRROR = [300.0 - c for c in RISE_FLAT_JUMP]  # +2
RISE_LONG_FALL = [100.0 + i for i in range(43)] + [141.0 - i for i in range(17)]  # +1
FLAT_JUMP = [100.0] * 59 + [110.0]  # 0


def csv_text(closes):
    return "date,close\n" + "".join(f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes))


FILES = {
    "DOWN.csv": csv_text(RISE_FLAT_JUMP),
    "UP.csv": csv_text(MIRROR),
    "LOW.csv": csv_text(RISE_LONG_FALL),
    "zeta.csv": csv_text(FLAT_JUMP),
    "bad.csv": "date,close\n2026-01-01,10\n2026-01-02,abc\n",
    "noclose.csv": "date,price\n2026-01-01,10\n",
}


@pytest.fixture(autouse=True)
def no_config_env(monkeypatch):
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)


# --------------------------------------------------------------------------- static page


def test_scan_panel_and_controls_exist():
    assert '<section id="scan-panel" class="panel" aria-labelledby="scan-heading">' in INDEX_HTML
    assert '<input type="file" id="scan-files" multiple accept=".csv,text/csv">' in INDEX_HTML
    for control, label in [
        ("scan-files", "CSV files"),
        ("scan-min-score", "Minimum score"),
        ("scan-top", "Rows to keep"),
        ("scan-short", "Short SMA"),
        ("scan-long", "Long SMA"),
        ("scan-rsi", "RSI period"),
    ]:
        assert re.search(rf'<label for="{control}">{label}', INDEX_HTML), control
        assert f'id="{control}"' in INDEX_HTML
    for header in ("Symbol", "Bars", "Score", "Crossover", "RSI", "MACD", "Bollinger"):
        assert re.search(rf'<th scope="col"( class="num")?>{header}</th>', INDEX_HTML.split('id="scan-table"')[1])
    assert '<ul id="scan-skipped" class="scan-skipped"></ul>' in INDEX_HTML
    assert '<div id="scan-error" class="error" role="alert" hidden></div>' in INDEX_HTML


def test_research_aid_line_stays_visible():
    # the footer line is never hidden, and the scan results repeat it under the skipped list
    footer = INDEX_HTML.split("<footer>")[1].split("</footer>")[0]
    assert f'<p id="disclaimer">{DISCLAIMER}</p>' in footer and "hidden" not in footer
    assert f'<p class="scan-disclaimer" id="scan-disclaimer">{DISCLAIMER}</p>' in INDEX_HTML
    assert "#disclaimer" not in STYLE_CSS and "scan-disclaimer { display" not in STYLE_CSS
    assert "disclaimer').hidden" not in APP_JS


def test_ids_are_unique_and_every_id_the_script_uses_exists():
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    used = set(re.findall(r"\$\('([a-z0-9_-]+)'\)", APP_JS)) - {"param-"}
    assert used <= set(ids), used - set(ids)


def test_page_rules_still_hold():
    assert not re.search(r"<script(?![^>]*\ssrc=)", INDEX_HTML)
    assert "<style" not in INDEX_HTML and ' style="' not in INDEX_HTML
    assert not re.search(r"\son\w+=", INDEX_HTML)
    assert not re.search(r"https?://", INDEX_HTML + STYLE_CSS)
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS
    assert "fetch('/api/scan'" in APP_JS


# --------------------------------------------------------------------------- helpers run in Node


def _extract_function(name):
    match = re.search(rf"function {name}\([^)]*\) \{{.*?\n  \}}\n", APP_JS, re.S)
    assert match, f"{name} not found in APP_JS"
    return match.group(0)


def run_node(script):
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


HELPERS = "".join(_extract_function(n) for n in ("signed", "buildScanPayload", "scanRowCells", "scanSummaryText"))


@needs_node
def test_helpers_format_like_the_command_line():
    script = HELPERS + """
    const row = {symbol: 'UP', bars: 60, score: 2, parts: {crossover: -1, rsi: 1, macd: 0, bollinger: 1}};
    console.log(JSON.stringify({
      signed: [signed(2), signed(1), signed(0), signed(-1), signed(-4)],
      cells: scanRowCells(row),
      summary: scanSummaryText({found: 8, scored: 6, shown: 3, skipped: [{}, {}], results: []}),
    }));
    """
    assert run_node(script) == {
        "signed": ["+2", "+1", "0", "-1", "-4"],
        "cells": ["UP", "60", "+2", "-1", "+1", "0", "+1"],
        "summary": "- 8 found, 6 scored, 2 skipped, 3 shown",
    }


@needs_node
def test_payload_is_what_the_api_takes():
    script = HELPERS + """
    const p = buildScanPayload([{name: 'A.csv', text: 'x'}, {name: '__proto__.csv', text: 'y'}],
      {min_score: ' 1 ', top: '', short: '5', long: ' 12', rsi_period: undefined});
    let dup = null, none = null;
    try { buildScanPayload([{name: 'A.csv', text: 'x'}, {name: 'A.csv', text: 'z'}], {}); } catch (e) { dup = e.message; }
    try { buildScanPayload([], {}); } catch (e) { none = e.message; }
    console.log(JSON.stringify({payload: JSON.parse(JSON.stringify(p)), dup, none}));
    """
    assert run_node(script) == {
        "payload": {
            "files": {"A.csv": "x", "__proto__.csv": "y"},
            "min_score": "1", "top": "", "short": "5", "long": "12", "rsi_period": "",
        },
        "dup": "Two files are both named A.csv; pick files with different names.",
        "none": "Pick one or more CSV files first.",
    }


# --------------------------------------------------------------------------- the whole panel in Node


FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;  // elements whose content in the HTML is plain text
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
for (const [id, tag] of PAGE_IDS) { const n = new Node_(tag); n.id = id; n._text = PAGE_TEXT[id] || ''; byId[id] = n; }
for (const id of ['scan-results', 'scan-error', 'scan-none', 'scan-no-skipped', 'results', 'error', 'csv-block',
                  'candle-hint', 'strategy-params-block', 'no-trades']) byId[id].hidden = true;
byId['scan-short'].value = '20'; byId['scan-long'].value = '50'; byId['scan-rsi'].value = '14';
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
async function submitScan(files, fields) {
  byId['scan-files'].files = files.map(([name, t]) => ({ name, text: t, size: t.length }));
  for (const [id, v] of Object.entries(fields)) byId[id].value = v;
  for (const fn of byId['scan-form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  const body = byId['scan-table'].tBodies[0];
  return {
    resultsHidden: byId['scan-results'].hidden,
    error: byId['scan-error'].hidden ? null : byId['scan-error'].textContent,
    summary: byId['scan-summary'].textContent,
    rows: body.children.map((tr) => tr.children.map((c) => c.textContent)),
    tones: body.children.map((tr) => tr.children.slice(1).map((c) => c.className)),
    none: byId['scan-none'].hidden ? null : byId['scan-none'].textContent,
    skipped: byId['scan-skipped'].children.map((li) => li.textContent),
    noSkipped: !byId['scan-no-skipped'].hidden,
    disclaimer: byId['scan-disclaimer'].textContent,
    status: byId['scan-status'].textContent,
  };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const [files, fields] of %(cases)s) out.push(await submitScan(files, fields));
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
    script = (
        FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts), "base": json.dumps(base_url)}
        + APP_JS
        + DRIVE % {"cases": json.dumps(cases)}
    )
    return run_node(script)


FIELDS = {"scan-min-score": "", "scan-top": "", "scan-short": "20", "scan-long": "50", "scan-rsi": "14"}


def cli_scan_json(tmp_path, files, flags, capsys):
    folder = tmp_path / "prices"
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    assert cli_main(["--scan", str(folder), "--json", *flags]) == 0
    return json.loads(capsys.readouterr().out)


def signed(v):
    return f"{v:+d}" if v else "0"


@needs_node
@pytest.mark.parametrize(
    "fields, flags",
    [
        ({}, []),
        ({"scan-min-score": "0", "scan-top": "2"}, ["--min-score", "0", "--top", "2"]),
        ({"scan-short": "2", "scan-long": "5", "scan-rsi": "2"}, ["--short", "2", "--long", "5", "--rsi-period", "2"]),
    ],
)
def test_panel_shows_what_the_command_line_prints(base_url, tmp_path, capsys, fields, flags):
    [page] = drive_page(base_url, [[list(FILES.items()), {**FIELDS, **fields}]])
    cli = cli_scan_json(tmp_path, FILES, flags, capsys)
    assert page["error"] is None and page["resultsHidden"] is False
    assert page["rows"] == [
        [r["symbol"], str(r["bars"]), signed(r["score"])] + [signed(r["parts"][p]) for p in ("crossover", "rsi", "macd", "bollinger")]
        for r in cli["results"]
    ]
    assert page["skipped"] == [s["reason"] for s in cli["skipped"]]
    assert page["summary"] == f"- {cli['found']} found, {cli['scored']} scored, {len(cli['skipped'])} skipped, {cli['shown']} shown"
    assert page["disclaimer"] == DISCLAIMER
    assert page["status"].startswith("Done in ")


@needs_node
def test_panel_colours_follow_the_sign(base_url):
    [page] = drive_page(base_url, [[[["UP.csv", FILES["UP.csv"]]], FIELDS]])
    assert page["rows"] == [["UP", "60", "+2", "-1", "+1", "+1", "+1"]]
    assert page["tones"] == [["num", "num good", "num bad", "num good", "num good", "num good"]]
    assert page["noSkipped"] is True


@needs_node
def test_panel_nothing_matched_and_errors(base_url):
    bad_only = [["bad.csv", FILES["bad.csv"]]]
    cases = [
        [list(FILES.items()), {**FIELDS, "scan-min-score": "4"}],  # nothing matched: not an error
        [list(FILES.items()), {**FIELDS, "scan-top": "0"}],  # the server's usage message
        [bad_only, FIELDS],  # nothing could be scored
        [[], FIELDS],  # nothing picked
    ]
    matched, top0, bad, empty = drive_page(base_url, cases)
    assert matched["error"] is None and matched["rows"] == []
    assert matched["none"] == "No file matched: no score at or above the minimum score."
    assert len(matched["skipped"]) == 2
    assert top0["error"] == "--top must be at least 1, got 0"
    assert bad["error"] == "none of the 1 .csv file in the request could be scored (1 skipped)"
    assert empty["error"] == "Pick one or more CSV files first."
