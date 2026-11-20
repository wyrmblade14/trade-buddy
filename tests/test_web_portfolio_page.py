"""The "Portfolio backtest" panel of the web page.

Static checks on the HTML, plus the shipped APP_JS run for real in Node: its
pure helpers against Python's own formatting, and the whole panel (pick files,
fill the controls, submit) against a real local server, with a small stand-in
for the browser DOM. The page must show what
``python -m trading_assistant.portfolio FOLDER`` prints, digit for digit.
"""

import json
import math
import random
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant import portfolio
from trading_assistant.cli import DISCLAIMER
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]


def csv_text(closes, dates=DATES):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(dates, closes))


A = csv_text([10, 9, 8, 9, 11, 12, 10, 8])
B = csv_text([20, 20, 19, 21, 22, 20, 18, 17])
BAD = "date,close\n2026-01-02,30\n2026-01-05,abc\n"


# --------------------------------------------------------------------------- static page


def test_panel_and_controls_exist_below_the_other_panels():
    panel = '<section id="pf-panel" class="panel" aria-labelledby="pf-heading">'
    assert panel in INDEX_HTML
    assert '<h2 id="pf-heading">Portfolio backtest</h2>' in INDEX_HTML
    main = INDEX_HTML.split("<main")[1].split("</main>")[0]
    sections = re.findall(r'<section id="([^"]+)"', main)
    assert sections[-1] == "pf-panel" and sections.index("pf-panel") > sections.index("wf-panel")
    for control, label in [
        ("pf-files", "CSV files (the file name without .csv is the symbol)"),
        ("pf-short", "Short SMA"), ("pf-long", "Long SMA"), ("pf-cash", "Starting cash"),
        ("pf-fee", "Fee per trade"), ("pf-fee-pct", "Cost % of trade value"), ("pf-weights", "Weights"),
    ]:
        assert f'<label for="{control}">{label}</label>' in INDEX_HTML, control
    assert '<input type="file" id="pf-files" multiple accept=".csv,text/csv">' in INDEX_HTML
    assert '<button type="submit" id="pf-run" class="primary">Run portfolio backtest</button>' in INDEX_HTML
    assert '<span id="pf-status" class="status" role="status" aria-live="polite"></span>' in INDEX_HTML
    assert '<div id="pf-error" class="error" role="alert" hidden></div>' in INDEX_HTML
    assert '<div id="pf-results" class="pf-results" hidden aria-live="polite">' in INDEX_HTML


def test_defaults_are_the_command_defaults():
    args = portfolio.build_parser().parse_args(["folder"])
    for control, value in [("pf-short", args.short), ("pf-long", args.long), ("pf-cash", args.cash),
                           ("pf-fee", args.fee), ("pf-fee-pct", args.fee_pct)]:
        shown = re.search(rf'<input id="{control}"[^>]*\svalue="([^"]*)"', INDEX_HTML).group(1)
        assert float(shown) == value, control
    weights = re.search(r'<input id="pf-weights"[^>]*>', INDEX_HTML).group(0)
    assert "value=" not in weights and args.weights is None  # empty box = equal split, as without --weights


def test_table_headers_follow_the_text_output_and_weight_starts_hidden():
    table = INDEX_HTML.split('id="pf-table"')[1].split("</table>")[0]
    headers = re.findall(r'<th scope="col"(?: class="num")?(?: id="[^"]+")?(?: hidden)?>([^<]+)</th>', table)
    assert headers == ["Symbol", "Weight", "Bars used", "Bars lost", "Return", "Trades", "Buy &amp; hold"]
    assert '<th scope="col" class="num" id="pf-weight-col" hidden>Weight</th>' in table


def test_page_rules_and_ids_still_hold():
    ids = re.findall(r'\sid="([^"]+)"', INDEX_HTML)
    assert len(ids) == len(set(ids))
    used = set(re.findall(r"\$\('([a-z0-9_-]+)'\)", APP_JS)) - {"param-"}
    assert used <= set(ids), used - set(ids)
    assert {i for i in used if i.startswith("pf-")} >= {"pf-form", "pf-files", "pf-table", "pf-weights", "pf-skipped"}
    assert f'<p class="pf-disclaimer" id="pf-disclaimer">{DISCLAIMER}</p>' in INDEX_HTML
    assert "pf-disclaimer').hidden" not in APP_JS and "pf-disclaimer { display" not in STYLE_CSS
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS
    assert "fetch('/api/portfolio'" in APP_JS  # relative: only ever this local server
    assert not re.search(r"https?://", INDEX_HTML + STYLE_CSS)


# --------------------------------------------------------------------------- helpers run in Node


def _extract_function(name):
    match = re.search(rf"function {name}\([^)]*\) \{{.*?\n  \}}\n", APP_JS, re.S)
    assert match, f"{name} not found in APP_JS"
    return match.group(0)


def run_node(script):
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


HELPERS = "".join(_extract_function(n) for n in (
    "fixed2", "pctText", "pfFixed2", "pfPct", "pfMoney", "pyRepr", "pfWeightText", "pfTitle", "pfSummaryRows",
    "pfRowCells", "pfWorstText", "pfNote", "buildPfPayload"))

# Exact ties at the second decimal (odd multiples of 1/8), decimal texts that only look like
# ties (2.675 is 2.67499999...), -0.0, tiny negatives, carries into the whole number, big values.
TRICKY = [0.0, -0.0, 0.125, -0.125, 0.375, -0.625, 0.875, 12.125, -12.375, 2.675, 1.005, 0.005, -0.005,
          -0.0049999, 0.0049999, -1e-12, -1e-300, 0.995, 9.995, -99.995, 999.995, 1234567.125, 1e6 + 0.125,
          -22.377622377622377, -17.599999999999998, 123456789012.345, 1e15 + 0.5, 2.0 ** 60, 1e21, 3e22]


@needs_node
def test_percent_and_money_text_match_the_command_exactly():
    rng = random.Random(11)
    values = TRICKY + [rng.uniform(-150, 150) for _ in range(300)] + [rng.randint(-20000, 20000) / 1000
                                                                     for _ in range(300)]
    values += [rng.randint(-10 ** 9, 10 ** 9) / 8 for _ in range(200)]  # many exact ties
    page = run_node(HELPERS + f"const v = {json.dumps(values)};"
                    "console.log(JSON.stringify([v.map(pfPct), v.map(pfMoney)]));")
    assert [(x, p) for x, p in zip(values, page[0]) if p != portfolio._pct(x)] == []
    assert [(x, p) for x, p in zip(values, page[1]) if p != f"{x:,.2f}"] == []


@needs_node
def test_weight_text_matches_the_command_exactly():
    rng = random.Random(5)
    values = [70.0, 30.0, 33.3, 33.4, 0.1, 1e-4, 1e-5, 1.5e-7, 99.99999999999999, 12.5, 1e15, 1e16, 1.25e17,
              71.18, 7.81, 21.01, 1 / 3]
    values += [rng.uniform(0, 100) for _ in range(200)] + [10 ** rng.uniform(-9, 18) for _ in range(200)]
    values += [rng.randint(1, 10000) / 100 for _ in range(200)]
    page = run_node(HELPERS + f"console.log(JSON.stringify({json.dumps(values)}.map(pfWeightText)));")
    assert [(x, p) for x, p in zip(values, page) if p != portfolio._weight_text(x)] == []


def _summary(**changes):
    """A summarize() dict (8-bar example) with some values replaced."""
    base = {
        "short": 1, "long": 2, "fee": 0.0, "fee_pct": 0.0, "start_date": "2026-01-02", "end_date": "2026-01-13",
        "shared_dates": 8, "initial_cash": 1000.0, "final_equity": 777.0, "return_pct": -22.3,
        "max_drawdown_pct": -22.377622377622377, "buy_hold_return_pct": -17.5,
        "worst_symbol_drawdown": {"symbol": "A", "max_drawdown_pct": -33.02752293577982},
        "symbols": [
            {"symbol": "A", "bars_used": 8, "bars_lost": 0, "return_pct": -27.0, "trades": 2,
             "buy_hold_return_pct": -20.0},
            {"symbol": "B", "bars_used": 8, "bars_lost": 0, "return_pct": -17.599999999999998, "trades": 2,
             "buy_hold_return_pct": -15.0},
        ],
    }
    base.update(changes)
    return base


def _page_lines(title, summary_rows, table, worst, note, skipped, disclaimer):
    """The command's text lines rebuilt from what the panel shows (table rows as single-spaced cells)."""
    values = dict(summary_rows)
    buy_hold = next(label for label, _ in summary_rows if label.startswith("Buy & hold"))
    lines = [title, f"Dates: {values['Dates']}", f"Cash: {values['Cash']}  Final equity: {values['Final equity']}",
             f"Return: {values['Return']}  Max drawdown: {values['Max drawdown']}  {buy_hold}: {values[buy_hold]}"]
    lines += [" ".join(cells) for cells in table] + [worst] + ([note] if note else [])
    if skipped:
        lines += [f"Skipped: {len(skipped)}"] + [f"  {reason}" for reason in skipped]
    return lines + [disclaimer]


def _command_lines(text):
    """format_portfolio text without the table header, table rows single-spaced."""
    lines = text.rstrip("\n").split("\n")
    header = next(i for i, line in enumerate(lines) if line.startswith("Symbol "))
    rows = [i for i in range(header + 1, len(lines)) if not lines[i].startswith("Worst single-symbol")]
    first_after = next(i for i in range(header + 1, len(lines)) if lines[i].startswith("Worst single-symbol"))
    return lines[:header] + [" ".join(lines[i].split()) for i in range(header + 1, first_after)] + lines[first_after:]


@needs_node
def test_every_line_matches_format_portfolio_on_tricky_summaries():
    cases = [
        (_summary(), []),
        (_summary(return_pct=0.125, max_drawdown_pct=-0.0, buy_hold_return_pct=-0.125, initial_cash=1234567.125,
                  final_equity=0.005, fee=1234.565, fee_pct=0.125), []),
        (_summary(return_pct=-1e-12, max_drawdown_pct=-0.004999, buy_hold_return_pct=2.675,
                  worst_symbol_drawdown={"symbol": "B", "max_drawdown_pct": -0.001},
                  symbols=[{"symbol": "A", "bars_used": 8, "bars_lost": 3, "return_pct": -0.0, "trades": 0,
                            "buy_hold_return_pct": 0.375},
                           {"symbol": "B", "bars_used": 8, "bars_lost": 0, "return_pct": -0.00499, "trades": 1,
                            "buy_hold_return_pct": -12.125}]),
         [("BAD.csv", "BAD.csv line 3: invalid close value 'abc' (expected a number like 101.5)")]),
        (_summary(weights={"A": 33.3, "B": 66.7}), []),
        (_summary(weights={"A": 1e-05, "B": 99.99999}, fee=1e12, initial_cash=1e12, final_equity=999999999999.995), []),
    ]
    script = HELPERS + f"""
    const cases = {json.dumps([s for s, _ in cases])};
    console.log(JSON.stringify(cases.map((s) => [pfTitle(s), pfSummaryRows(s),
      s.symbols.map((row) => pfRowCells(row, s.weights || null)), pfWorstText(s), pfNote(s)])));
    """
    for (summary, skipped), parts in zip(cases, run_node(script)):
        page = _page_lines(*parts, [reason for _, reason in skipped], DISCLAIMER)
        assert page == _command_lines(portfolio.format_portfolio(summary, skipped)), summary


@needs_node
def test_payload_is_what_the_api_takes():
    script = HELPERS + """
    const files = [{name: 'A.csv', text: 'a'}, {name: 'B.csv', text: 'b'}];
    const plain = buildPfPayload(files, {short: ' 1 ', long: '2', cash: '', fee: undefined, fee_pct: null, weights: '  '});
    const weighted = buildPfPayload(files, {short: '', long: '', cash: '1000', fee: '0', fee_pct: '0',
                                            weights: ' A = 70, B=30\\nX=Y=0 '});
    const errors = [];
    for (const f of [[], [{name: 'A.csv', text: 'a'}, {name: 'A.csv', text: 'b'}]]) {
      try { buildPfPayload(f, {}); } catch (e) { errors.push(e.message); }
    }
    console.log(JSON.stringify({plain, weighted, errors}));
    """
    out = run_node(script)
    assert out["plain"] == {"files": {"A.csv": "a", "B.csv": "b"}, "short": "1", "long": "2", "cash": "",
                            "fee": "", "fee_pct": ""}  # '' = the command's default; no weights = equal split
    assert out["weighted"]["weights"] == ["A=70", "B=30", "X=Y=0"]  # checked by the server, as --weights
    assert out["errors"] == ["Pick two or more CSV files first.",
                             "Two files are both named A.csv; pick files with different names."]


# --------------------------------------------------------------------------- the whole panel in Node


FAKE_DOM = r"""
const PAGE_IDS = %(ids)s;
const PAGE_TEXT = %(texts)s;
const PAGE_VALUES = %(values)s;
const PAGE_HIDDEN = %(hidden)s;
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
  const n = new Node_(tag); n.id = id; n._text = PAGE_TEXT[id] || ''; n.value = PAGE_VALUES[id] || '';
  n.hidden = PAGE_HIDDEN.includes(id); byId[id] = n;
}
global.document = {
  getElementById: (id) => byId[id] || null,
  createElement: (t) => new Node_(t), createElementNS: (ns, t) => new Node_(t),
  createTextNode: (t) => { const n = new Node_('#text'); n._text = String(t); return n; },
  documentElement: new Node_('html'), body: new Node_('body'),
};
global.window = { matchMedia: () => ({ matches: false }), addEventListener() {} };
global.localStorage = { getItem: () => null, setItem() {} };
class FR { readAsText(f) { setTimeout(() => { this.result = f.text; this.onload(); }, 0); } }
global.FileReader = FR;
const BASE = %(base)s;
const realFetch = fetch;
const posted = [];
global.fetch = (url, opts) => { posted.push(url); return realFetch(BASE + url, opts); };
"""

DRIVE = r"""
const settle = () => new Promise((r) => setTimeout(r, 50));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
const OTHER = ['results', 'scan-results', 'wf-results', 'error', 'scan-error', 'wf-error'];
async function submitPf(fields, files) {
  byId['pf-files'].files = files.map(([name, text]) => ({ name, text, size: text.length }));
  for (const [id, v] of Object.entries(fields)) byId[id].value = v;
  const before = OTHER.map((id) => [byId[id].hidden, byId[id].textContent]);
  posted.length = 0;
  for (const fn of byId['pf-form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    error: byId['pf-error'].hidden ? null : byId['pf-error'].textContent,
    resultsHidden: byId['pf-results'].hidden,
    title: byId['pf-title'].textContent,
    summary: cells('pf-summary-table'),
    weightColumnHidden: byId['pf-weight-col'].hidden,
    table: cells('pf-table'),
    worst: byId['pf-worst'].textContent,
    note: byId['pf-note'].hidden ? '' : byId['pf-note'].textContent,
    skipped: byId['pf-skipped'].children.map((li) => li.textContent),
    skippedCount: byId['pf-skipped-count'].textContent,
    noSkippedHidden: byId['pf-no-skipped'].hidden,
    disclaimer: byId['pf-disclaimer'].textContent,
    status: byId['pf-status'].textContent,
    posted: posted.slice(),
    othersUnchanged: JSON.stringify(before) === JSON.stringify(OTHER.map((id) => [byId[id].hidden, byId[id].textContent])),
  };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const [fields, files] of %(cases)s) out.push(await submitPf(fields, files));
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


def drive_page(base_url, cases):
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', INDEX_HTML)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', INDEX_HTML))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', INDEX_HTML))
    hidden = [re.search(r'\sid="([^"]+)"', tag).group(1) for tag in re.findall(r"<\w+[^>]*>", INDEX_HTML)
              if re.search(r'\sid="', tag) and re.search(r"\shidden[\s>]", tag)]
    script = FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                         "values": json.dumps(values), "hidden": json.dumps(hidden), "base": json.dumps(base_url)}
    return run_node(script + APP_JS + DRIVE % {"cases": json.dumps(cases)})


FIELDS = {"pf-short": "1", "pf-long": "2", "pf-cash": "1000", "pf-fee": "0", "pf-fee-pct": "0", "pf-weights": ""}
FLAGS = ["--short", "1", "--long", "2", "--cash", "1000"]


def command(tmp_path, capsys, files, flags):
    """``(exit code, stdout, the one-line message)`` of the portfolio command on ``files`` in a fresh folder."""
    folder = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text)
    try:
        code = portfolio.main([str(folder), *flags])
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    message = err.strip().splitlines()[-1] if err.strip() else ""
    for prefix in ("trading_assistant.portfolio: error: ", "Error: "):
        message = message[len(prefix):] if message.startswith(prefix) else message
    return code, out, message


def shown_lines(page):
    return _page_lines(page["title"], page["summary"], page["table"], page["worst"], page["note"],
                       page["skipped"], page["disclaimer"])


@needs_node
def test_panel_shows_what_the_command_prints(base_url, tmp_path, capsys):
    # 1. the 8-bar example; 2. A=70 B=30 typed loosely; 3. a bad file and two dates only B has;
    # 4. flat prices and a 0.01 fee: tiny negative returns show as +0.00%.
    flat = {"A.csv": csv_text([10, 9, 8, 9, 9, 9, 9, 9]), "B.csv": csv_text([20] * 8)}
    lost = {"A.csv": A, "B.csv": csv_text([99] + [20, 20, 19, 21, 22, 20, 18, 17] + [99],
                                          ["2025-12-31"] + DATES + ["2026-01-14"]), "BAD.csv": BAD}
    runs = [
        ({"A.csv": A, "B.csv": B}, {}, []),
        ({"A.csv": A, "B.csv": B}, {"pf-weights": " A = 70, B=30 "}, ["--weights", "A=70", "B=30"]),
        (lost, {}, []),
        (flat, {"pf-fee": "0.01"}, ["--fee", "0.01"]),
    ]
    pages = drive_page(base_url, [[{**FIELDS, **fields}, list(files.items())] for files, fields, _ in runs])
    for (files, fields, flags), page in zip(runs, pages):
        code, out, _ = command(tmp_path, capsys, files, [*FLAGS, *flags])
        assert code == 0 and page["error"] is None and page["resultsHidden"] is False
        assert shown_lines(page) == _command_lines(out), fields
        assert page["posted"] == ["/api/portfolio"] and page["status"].startswith("Done in ")
        assert page["othersUnchanged"] is True
    eight, weighted, with_lost, tiny = pages
    assert eight["title"] == ("Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.00 + 0.00%,"
                              " on the dates every file shares")
    assert eight["summary"] == [["Dates", "2026-01-02 to 2026-01-13 (8 shared dates)"], ["Cash", "1,000.00"],
                                ["Final equity", "777.00"], ["Return", "-22.30%"], ["Max drawdown", "-22.38%"],
                                ["Buy & hold (equal weight)", "-17.50%"]]
    assert eight["table"] == [["A", "8", "0", "-27.00%", "2", "-20.00%"], ["B", "8", "0", "-17.60%", "2", "-15.00%"]]
    assert eight["weightColumnHidden"] is True and eight["skipped"] == [] and eight["noSkippedHidden"] is False
    assert eight["worst"] == "Worst single-symbol drawdown: -33.03% (A)" and eight["disclaimer"] == DISCLAIMER
    assert weighted["weightColumnHidden"] is False
    assert weighted["table"] == [["A", "70%", "8", "0", "-27.00%", "2", "-20.00%"],
                                 ["B", "30%", "8", "0", "-17.33%", "2", "-15.00%"]]
    assert with_lost["skipped"] == ["BAD.csv line 3: invalid close value 'abc' (expected a number like 101.5)"]
    assert with_lost["skippedCount"] == "(1)" and with_lost["note"].startswith("Note: dates not shared")
    assert [row[2] for row in with_lost["table"]] == ["0", "2"]
    assert ["Return", "+0.00%"] in tiny["summary"] and "-0.00" not in json.dumps(tiny)


@needs_node
def test_server_errors_show_the_command_message(base_url, tmp_path, capsys):
    runs = [
        ({"A.csv": A, "B.csv": B}, {"pf-short": "3", "pf-long": "2"}, ["--short", "3", "--long", "2"]),
        ({"A.csv": A, "B.csv": B}, {"pf-weights": "A=70 B=40"}, ["--weights", "A=70", "B=40"]),
        ({"A.csv": A, "B.csv": B}, {"pf-weights": "A=100"}, ["--weights", "A=100"]),
        ({"A.csv": A, "B.csv": B}, {"pf-long": "7"}, ["--long", "7"]),
        ({"A.csv": A, "B.csv": B, "BAD.csv": BAD}, {"pf-weights": "A=40 B=30 BAD=30"},
         ["--weights", "A=40", "B=30", "BAD=30"]),
    ]
    pages = drive_page(base_url, [[{**FIELDS, **fields}, list(files.items())] for files, fields, _ in runs]
                       + [[FIELDS, [["A.csv", A]]], [FIELDS, []]])
    for (files, fields, flags), page in zip(runs, pages):
        code, _, message = command(tmp_path, capsys, files, [*FLAGS, *flags])
        assert code in (1, 2) and page["error"] == message, fields
        assert page["resultsHidden"] is True and page["othersUnchanged"] is True
    one_file, no_files = pages[-2:]
    assert one_file["error"] == ("only 1 of the 1 .csv files in the request could be used (0 skipped);"
                                 " a portfolio needs at least 2")
    assert no_files["error"] == "Pick two or more CSV files first." and no_files["posted"] == []
