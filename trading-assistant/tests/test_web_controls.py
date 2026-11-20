"""Web page controls for slippage, position size, fill, stop loss and take profit.

The page must not compute anything itself: every number in the results comes
from the same ``cli.analyse`` the API already uses (see
test_web_later_settings.py for the API side). These tests check the new HTML
controls, that the page's JavaScript sends them the way the API expects
(position size as a fraction, built from a "% of account" control), that the
candle-only controls are greyed out (and cleared) without candle data, and
that a hand run through the real server gives the same numbers as the CLI.
"""

import json
import re
import shutil
import subprocess
import threading

import pytest

from trading_assistant.cli import analyse
from trading_assistant.samples import sample_candles
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML

HAS_NODE = shutil.which("node") is not None

CANDLE_CSV = "date,open,high,low,close,volume\n" + "".join(
    f"2026-01-{t + 1:02d},{o},{h},{lo},{c},{(t + 1) * 1000}\n"
    for t, (o, h, lo, c) in enumerate(
        zip(
            [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0],
            [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0],
            [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5],
            [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0],
        )
    )
)
CLOSE_ONLY_CSV = "date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate([10, 10, 10, 10, 14, 14, 14, 8, 8, 8]))
SMA = {"short": "2", "long": "3"}


class Client:
    def __init__(self, server):
        host, port = server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def post(self, payload):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        req = Request(
            self.base + "/api/backtest",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Client(server)
    server.shutdown()
    server.server_close()


# --------------------------------------------------------------------------- the controls exist, with sensible defaults


def test_the_five_controls_exist_with_cli_like_ranges():
    assert '<label for="slippage">Slippage %</label>' in INDEX_HTML
    assert '<input id="slippage" name="slippage" type="number" inputmode="decimal" min="0" max="99.99" step="any" value="0">' in INDEX_HTML
    assert '<label for="position_size">Position size (% of account)</label>' in INDEX_HTML
    assert '<input id="position_size" name="position_size" type="number" inputmode="decimal" min="0" max="100" step="any" placeholder="All-in">' in INDEX_HTML
    assert '<label for="fill">Fill price</label>' in INDEX_HTML
    assert '<option value="close">' in INDEX_HTML and '<option value="open">' in INDEX_HTML
    assert '<label for="stop_loss">Stop loss %</label>' in INDEX_HTML
    assert '<label for="take_profit">Take profit %</label>' in INDEX_HTML
    # none of the new controls are disabled or filled in by default in the markup (JS decides that at runtime)
    for control in ("slippage", "position_size", "fill", "stop_loss", "take_profit"):
        tag = re.search(rf'<(?:input|select) id="{control}"[^>]*>', INDEX_HTML).group(0)
        assert "disabled" not in tag


def test_candle_hint_exists_and_starts_hidden():
    assert '<p class="hint" id="candle-hint" hidden>' in INDEX_HTML
    assert "open/high/low" in INDEX_HTML


def test_trades_table_has_a_reason_column():
    assert '<th scope="col">Reason</th>' in INDEX_HTML


# --------------------------------------------------------------------------- error box still works without the stylesheet


def test_error_box_is_shown_and_hidden_with_the_native_attribute_not_css():
    # "hidden" is a native HTML attribute the browser honours with no CSS at all; the box's
    # text is always plain textContent (never innerHTML), so it is visible even if style.css
    # fails to load. An inline style="" attribute was not added: the page's own
    # Content-Security-Policy (style-src 'self') would silently block it, and
    # test_page_has_no_inline_script_style_or_remote_resources (test_web.py) forbids it outright.
    assert '<div id="error" class="error" role="alert" hidden></div>' in INDEX_HTML
    assert ' style="' not in INDEX_HTML
    assert "errorEl.textContent = message;" in APP_JS
    assert "errorEl.innerHTML" not in APP_JS


# --------------------------------------------------------------------------- readForm wiring (source inspection)


def test_js_sends_position_size_as_a_fraction_of_the_percentage_control():
    assert "Number($('position_size').value.trim()) / 100" in APP_JS


def test_js_blanks_the_candle_only_controls_when_disabled_before_sending():
    assert "$('fill').disabled ? 'close' : $('fill').value" in APP_JS
    assert "$('stop_loss').disabled ? '' : $('stop_loss').value.trim()" in APP_JS
    assert "$('take_profit').disabled ? '' : $('take_profit').value.trim()" in APP_JS


def test_js_shows_the_reason_in_the_trades_table():
    assert "t.reason || '-'" in APP_JS


def test_js_never_uses_innerhtml_or_eval():
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS


# --------------------------------------------------------------------------- candle-column detection, run for real in Node


def _extract_function(name):
    match = re.search(rf"function {name}\([^)]*\) \{{.*?\n  \}}\n", APP_JS, re.S)
    assert match, f"{name} not found in APP_JS"
    return match.group(0)


@pytest.mark.skipif(not HAS_NODE, reason="node is not installed; the equivalent Python case below still runs")
@pytest.mark.parametrize(
    "text, expected",
    [
        ("date,open,high,low,close,volume\n2026-01-01,9,11,8,10,1\n", True),
        ("Date,Open,High,Low,Close,Volume\n", True),
        (" date , open , high , low , close , volume \n", True),
        ("close,open,date,volume,low,high\n", True),
        ("date,close\n2026-01-01,10\n", False),
        ("date,open,close\n", False),
        ("", False),
        ("date,open,high,low,close,volume\r\n9,11,8,10,1\r\n", True),
        ("just one column\n", False),
    ],
    ids=[
        "exact header", "different case", "extra spaces", "reordered columns",
        "close only", "missing high and low", "empty", "CRLF", "no commas",
    ],
)
def test_the_shipped_header_check_runs_correctly_in_a_real_js_engine(text, expected):
    script = _extract_function("pastedCsvHasCandleColumns") + f"console.log(JSON.stringify(pastedCsvHasCandleColumns({json.dumps(text)})));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


def _python_equivalent_of_pasted_csv_has_candle_columns(text):
    """Same algorithm as the shipped ``pastedCsvHasCandleColumns``, to check it without Node."""
    header = re.split(r"\r\n|\r|\n", text or "", maxsplit=1)[0] if text else ""
    columns = [c.strip().lower() for c in header.split(",")]
    return all(name in columns for name in ("open", "high", "low"))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("date,open,high,low,close,volume\n2026-01-01,9,11,8,10,1\n", True),
        ("Date,Open,High,Low,Close,Volume\n", True),
        ("date,close\n2026-01-01,10\n", False),
        ("", False),
    ],
)
def test_the_python_equivalent_agrees_with_the_algorithm_in_the_comment(text, expected):
    assert _python_equivalent_of_pasted_csv_has_candle_columns(text) == expected


# --------------------------------------------------------------------------- a hand run through the real server


def test_hand_worked_run_through_the_server_as_the_page_would_send_it(client):
    # Mimics readForm(): position size entered as "50" (% of account) -> sent as the fraction 0.5.
    payload = {
        "csv": CANDLE_CSV, **SMA, "cash": "10000", "fee": "0", "fee_pct": "0",
        "slippage": "1", "position_size": str(50 / 100), "fill": "open", "stop_loss": "10",
    }
    status, data = client.post(payload)
    assert status == 200 and data["ok"]
    trades = [(t["side"], t["shares"], t["price"]["text"], t["cash_after"]["text"], t.get("reason")) for t in data["trades"]]
    assert trades == [("BUY", 380, "13.13", "5,010.60", "signal"), ("SELL", 380, "8.91", "8,396.40", "stop")]
    assert data["summary"]["end_equity"]["text"] == "8,396.40"
    assert data["params"]["position_size"] == 0.5 and data["params"]["fill"] == "open" and data["params"]["stop_loss"] == 10.0


@pytest.mark.parametrize(
    "position_pct, slippage, fill, stop_loss, take_profit",
    [
        ("", "0", "close", "", ""),
        ("50", "1", "open", "10", ""),
        ("25", "0.5", "open", "10", "20"),
        ("", "2", "close", "", "5"),
    ],
    ids=["defaults", "stop only", "stop and target", "target only"],
)
def test_page_payload_matches_cli_analyse_for_the_same_settings(client, position_pct, slippage, fill, stop_loss, take_profit):
    """What readForm() would build from the controls, compared with cli.analyse on the same candles."""
    payload = {
        "csv": CANDLE_CSV, **SMA, "cash": "10000", "fee": "0", "fee_pct": "0", "slippage": slippage,
        "position_size": "" if position_pct == "" else str(float(position_pct) / 100),
        "fill": fill, "stop_loss": stop_loss, "take_profit": take_profit,
    }
    status, data = client.post(payload)
    assert status == 200 and data["ok"]

    opens = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0]
    highs = [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0]
    lows = [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5]
    closes = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
    lines, result = analyse(
        closes, short=2, long=3, backtest=True, fill=fill, opens=opens,
        slippage_pct=float(slippage), position_size=None if position_pct == "" else float(position_pct) / 100,
        stop_pct=None if stop_loss == "" else float(stop_loss),
        take_profit_pct=None if take_profit == "" else float(take_profit),
        highs=highs, lows=lows,
    )
    assert data["report"] == lines
    assert data["summary"]["end_equity"]["value"] == result.final_equity
    assert [t.get("reason") for t in data["trades"]] == [t.reason if result.has_exits else None for t in result.trades]


def test_sample_source_always_has_candle_data_available(client):
    # A built-in sample is never "greyed out": it has sample_candles whatever the source list shows.
    status, data = client.post({"sample": "uptrend", "short": "5", "long": "20", "fill": "open", "stop_loss": "5"})
    assert status == 200 and data["ok"]
    candles = sample_candles("uptrend")
    lines, _ = analyse(
        [c.close for c in candles], short=5, long=20, backtest=True, fill="open",
        opens=[c.open for c in candles], stop_pct=5.0, highs=[c.high for c in candles], lows=[c.low for c in candles],
    )
    assert data["report"] == lines


def test_close_only_csv_without_the_new_settings_is_unchanged(client):
    # Equivalent to the controls being greyed out and left at their defaults: no new keys sent at all.
    status, data = client.post({"csv": CLOSE_ONLY_CSV, **SMA, "cash": "10000", "fee": "0", "fee_pct": "0"})
    assert status == 200 and data["ok"]
    assert set(data["params"]) == {"short", "long", "rsi_period", "cash", "fee", "fee_pct"}
    assert all("reason" not in t for t in data["trades"])


def test_greyed_out_candle_controls_make_the_close_only_csv_request_succeed(client):
    # What the page sends once fill/stop_loss/take_profit are disabled-and-blanked for a close-only paste.
    payload = {"csv": CLOSE_ONLY_CSV, **SMA, "cash": "10000", "fee": "0", "fee_pct": "0",
               "slippage": "0.5", "position_size": "", "fill": "close", "stop_loss": "", "take_profit": ""}
    status, data = client.post(payload)
    assert status == 200 and data["ok"]
    lines, result = analyse([10, 10, 10, 10, 14, 14, 14, 8, 8, 8], short=2, long=3, backtest=True, slippage_pct=0.5)
    assert data["report"] == lines
    assert data["summary"]["end_equity"]["value"] == result.final_equity


def test_bad_value_from_a_control_is_reported_the_way_other_bad_inputs_are(client):
    status, data = client.post({"sample": "uptrend", "slippage": "101"})
    assert status == 400
    assert set(data) == {"ok", "error"} and data["ok"] is False
    assert data["error"] == "--slippage must be between 0 and 100 (exclusive), got 101"


def test_pasting_a_close_only_csv_with_a_candle_setting_is_rejected_in_one_line(client):
    status, data = client.post({"csv": CLOSE_ONLY_CSV, **SMA, "fill": "open"})
    assert status == 400 and "\n" not in data["error"]
    assert data["error"].startswith("CSV has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close')")
