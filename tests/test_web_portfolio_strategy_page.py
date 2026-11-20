"""The portfolio panel's strategy picker: the shipped APP_JS run in Node against a real local server.

Uses the stand-in DOM and helpers of test_web_portfolio_page.py. ``tests/data/portfolio_page_requests_before_strategy.json``
holds the request bodies the panel sent before it had the picker (the page at the commit before it, run in this
same driver); with sma_cross, or the picker untouched, the panel must send exactly those.
"""

import json
import re
import threading
from pathlib import Path

import pytest

from test_web_portfolio_page import FAKE_DOM, _command_lines, _page_lines, command, needs_node, run_node
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

DATES = [f"2026-04-{i:02d}" for i in range(1, 11)]
HAND = {"AAA": [10, 11, 12, 13, 12, 11, 10, 11, 13, 14], "BBB": [20, 19, 18, 19, 21, 22, 21, 19, 18, 20]}
FILES = [[f"{s}.csv", "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, cs))] for s, cs in HAND.items()]
BEFORE = json.loads((Path(__file__).parent / "data" / "portfolio_page_requests_before_strategy.json").read_text())

# The default-strategy runs: the panel's own values, typed values, and every field emptied.
DEFAULT_FIELDS = [
    {},
    {"pf-short": "2", "pf-long": "3", "pf-cash": "1000", "pf-fee": "0.5", "pf-fee-pct": "0.1",
     "pf-weights": " AAA = 60, BBB=40 "},
    {"pf-short": "", "pf-long": "", "pf-cash": "", "pf-fee": "", "pf-fee-pct": "", "pf-weights": ""},
]

DRIVE = r"""
const bodies = [];
const sendOn = global.fetch;
global.fetch = (url, opts) => { if (opts && opts.body) bodies.push(opts.body); return sendOn(url, opts); };
%(app)s
const settle = () => new Promise((r) => setTimeout(r, 50));
const cells = (table) => byId[table].tBodies[0].children.map((tr) => tr.children.map((c) => c.textContent));
function paramInputs() {
  const out = {};
  for (const field of byId['pf-strategy-params'].children) {
    const input = field.children[1];
    out[input.attrs.id] = input;
  }
  return out;
}
async function step({ strategies, params, fields, files }) {
  for (const name of strategies || []) {
    byId['pf-strategy'].value = name;
    for (const fn of byId['pf-strategy'].listeners.change || []) fn();
  }
  const inputs = byId['pf-strategy-params'] ? paramInputs() : {};
  const ui = byId['pf-strategy'] ? {
    options: byId['pf-strategy'].children.map((o) => o.attrs.value),
    hint: byId['pf-strategy-hint'].textContent,
    shortHidden: byId['pf-short-field'].hidden, longHidden: byId['pf-long-field'].hidden,
    paramsHidden: byId['pf-strategy-params-block'].hidden,
    params: Object.entries(inputs).map(([id, input]) => [id, input.attrs.value, input.attrs.type, input.attrs.step,
      byId['pf-strategy-params'].children.find((f) => f.children[1] === input).children[0].attrs.for]),
  } : null;
  for (const [id, v] of Object.entries(params || {})) inputs[id].value = v;
  byId['pf-files'].files = files.map(([name, text]) => ({ name, text, size: text.length }));
  for (const [id, v] of Object.entries(fields || {})) byId[id].value = v;
  bodies.length = 0;
  for (const fn of byId['pf-form'].listeners.submit) await fn({ preventDefault() {} });
  await settle();
  return {
    ui, bodies: bodies.slice(),
    error: byId['pf-error'].hidden ? null : byId['pf-error'].textContent,
    resultsHidden: byId['pf-results'].hidden,
    title: byId['pf-title'].textContent, summary: cells('pf-summary-table'), table: cells('pf-table'),
    worst: byId['pf-worst'].textContent, note: byId['pf-note'].hidden ? '' : byId['pf-note'].textContent,
    skipped: byId['pf-skipped'].children.map((li) => li.textContent), disclaimer: byId['pf-disclaimer'].textContent,
  };
}
(async () => {
  await settle();  // loadSamples()
  const out = [];
  for (const s of %(steps)s) out.push(await step(s));
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def drive(base_url, steps, html=INDEX_HTML, js=APP_JS):
    """Load the page (``html`` and ``js``) in Node, then run each step on it in turn; one result per step."""
    ids = re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', html)
    texts = dict(re.findall(r'<\w+[^>]*\sid="([^"]+)"[^>]*>([^<]+)</', html))
    values = dict(re.findall(r'<input id="([^"]+)"[^>]*\svalue="([^"]*)"', html))
    hidden = [re.search(r'\sid="([^"]+)"', tag).group(1) for tag in re.findall(r"<\w+[^>]*>", html)
              if re.search(r'\sid="', tag) and re.search(r"\shidden[\s>]", tag)]
    dom = FAKE_DOM % {"ids": json.dumps([[i, t] for t, i in ids]), "texts": json.dumps(texts),
                      "values": json.dumps(values), "hidden": json.dumps(hidden), "base": json.dumps(base_url)}
    return run_node(dom + DRIVE % {"app": js, "steps": json.dumps(steps)})


@pytest.fixture(scope="module")
def base_url():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def shown_lines(page):
    return _page_lines(page["title"], page["summary"], page["table"], page["worst"], page["note"], page["skipped"],
                       page["disclaimer"])


@needs_node
def test_default_strategy_sends_exactly_the_old_requests(base_url):
    # Picker untouched, sma_cross picked, and another strategy picked then sma_cross again: each sends, byte for
    # byte, what the panel sent before the picker existed.
    assert len(BEFORE) == len(DEFAULT_FIELDS) == 3
    ways = [[], ["sma_cross"], ["hull_trend", "sma_cross"]]
    steps = [{"strategies": way, "fields": fields, "files": FILES} for fields in DEFAULT_FIELDS for way in ways]
    pages = drive(base_url, steps)
    for i, page in enumerate(pages):
        assert page["bodies"] == [BEFORE[i // len(ways)]], steps[i]
        assert page["ui"]["shortHidden"] is False and page["ui"]["paramsHidden"] is True
    assert pages[3]["error"] is None and pages[3]["title"].startswith("Portfolio: 2 symbols, cash split by weight")


@needs_node
def test_picking_a_strategy_swaps_the_fields(base_url):
    page, = drive(base_url, [{"strategies": ["zscore_reversion"], "files": []}])
    ui = page["ui"]
    assert ui["options"] == ["sma_cross", "rsi_reversion", "breakout", "ema_cross", "momentum", "zscore_reversion",
                             "hull_trend"]  # the list the backtest panel gets from /api/samples, in its order
    assert ui["hint"] == "BUY when the z-score crosses up through entry, SELL when it crosses up through exit."
    assert (ui["shortHidden"], ui["longHidden"], ui["paramsHidden"]) == (True, True, False)
    assert ui["params"] == [[f"pf-param-{k}", v, "number", "any", f"pf-param-{k}"]
                            for k, v in (("window", "20"), ("entry", "-2"), ("exit", "0"))]
    assert page["error"] == "Pick two or more CSV files first." and page["bodies"] == []


@needs_node
def test_strategy_runs_show_what_the_command_prints(base_url, tmp_path, capsys):
    # Short and long are hidden with another strategy, so not sent; the steps share one page, so every run sets
    # the weights box.
    fields = {"pf-cash": "1000", "pf-short": "7", "pf-long": "9", "pf-weights": ""}
    runs = [
        ({"pf-param-window": "3"}, {}, ["--strategy", "breakout", "--param", "window=3"]),
        ({"pf-param-window": " 3 "}, {"pf-weights": "AAA=60 BBB=40"},
         ["--strategy", "breakout", "--param", "window=3", "--weights", "AAA=60", "BBB=40"]),
        # Untouched threshold (and a typed value equal to its default) is left to the default: threshold=0.0.
        ({"pf-param-window": "3", "pf-param-threshold": "0"}, {}, ["--strategy", "momentum", "--param", "window=3"]),
    ]
    names = ["breakout", "breakout", "momentum"]
    pages = drive(base_url, [{"strategies": [name], "params": params, "fields": {**fields, **extra}, "files": FILES}
                             for name, (params, extra, _) in zip(names, runs)])
    bodies = [json.loads(page["bodies"][0]) for page in pages]
    assert [{k: v for k, v in body.items() if k != "files"} for body in bodies] == [
        {"cash": "1000", "fee": "0", "fee_pct": "0", "strategy": "breakout", "params": ["window=3"]},
        {"cash": "1000", "fee": "0", "fee_pct": "0", "weights": ["AAA=60", "BBB=40"], "strategy": "breakout",
         "params": ["window=3"]},
        {"cash": "1000", "fee": "0", "fee_pct": "0", "strategy": "momentum", "params": ["window=3"]},
    ]
    for (params, extra, flags), page in zip(runs, pages):
        code, out, _ = command(tmp_path, capsys, dict(FILES), ["--cash", "1000", *flags])
        assert code == 0 and page["error"] is None and page["resultsHidden"] is False
        assert shown_lines(page) == _command_lines(out), flags  # the title is the server's, from the reply
    assert pages[0]["title"] == ("Portfolio: 2 symbols, cash split equally, breakout (window=3), fee 0.00 + 0.00%,"
                                 " on the dates every file shares")
    assert pages[2]["title"].startswith("Portfolio: 2 symbols, cash split equally, momentum (window=3, threshold=0.0),")


BAD = [
    ("0", "window must be a whole number of at least 1, got 0"),
    ("2.5", "window must be a whole number of at least 1, got 2.5"),
    ("600", "--param window must be at most 500, got 600"),
    ("9", "only 10 dates shared by all 2 symbols; need at least 11 for breakout (window=9): 10 for its first signal"
          " + 1 to fill it"),
]


@needs_node
@pytest.mark.parametrize("window, message", BAD, ids=[w for w, _ in BAD])
def test_bad_values_show_the_api_message(base_url, tmp_path, capsys, window, message):
    page, = drive(base_url, [{"strategies": ["breakout"], "params": {"pf-param-window": window}, "files": FILES}])
    assert page["error"] == message and page["resultsHidden"] is True
    if window != "600":  # the command has no MAX_WINDOW; the rest are its messages too
        code, _, command_message = command(tmp_path, capsys, dict(FILES),
                                           ["--strategy", "breakout", "--param", f"window={window}"])
        assert code in (1, 2) and command_message == message
