"""POST /api/backtest with min_hold (the command's --min-hold N).

min_hold is read exactly like max_hold: a JSON whole number (4.0 reads as 4) or a
string holding one; null, "" or no key leave it off; true/false, a fraction,
other text ("4.0" too) or any other type is a 400. Then the command line's own
cli.check_min_hold: below 1 is a 400 with the command's message. It needs no
stop and no candle data (the CSV here is close-only). With it, summary has
min_hold_bars and min_hold_skipped_sells (the --json keys), params echoes
min_hold and the report has the "Min hold:" line; it makes no fill, so trades
and the export get no reason. A request without it gets exactly the old reply.

Hand case: the close-only series of test_min_hold.py, cash 1000, short 1, long 2.
"""

import hashlib
import http.client
import json
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
BASE = {"csv": CLOSES, "short": 1, "long": 2, "cash": 1000}
CLI = ["closes.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000"]

# sha256 of the raw reply bodies, captured from the server before it took min_hold (git HEAD).
PLAIN = "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"
OLD_REPLIES = [
    (BASE, PLAIN),
    ({**BASE, "min_hold": None}, PLAIN),
    ({**BASE, "min_hold": ""}, PLAIN),
    ({**BASE, "max_hold": 2}, "e5ba28a8c73037ffa08c9022cbb5ccf1bf5d49a4bf48557e48e2fc76d6c1e7e5"),
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "cooldown": 3, "fill": "open"},
     "6dfa7b27cf3624301c4315facb7b493ade9f69fd27ae1ae6cbc8912340276f16"),
]


class Client:
    def __init__(self, server):
        self.host, self.port = server.server_address[:2]

    def raw(self, payload):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        conn.request(
            "POST", "/api/backtest", body=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
        )
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, body

    def post(self, payload):
        status, body = self.raw(payload)
        return status, json.loads(body)


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Client(server)
    server.shutdown()
    server.server_close()


def cli_run(capsys, tmp_path, monkeypatch, argv):
    (tmp_path / "closes.csv").write_text(CLOSES)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    code = cli_main([*CLI, *argv])
    out, err = capsys.readouterr()
    assert (code, err) == (0, "")
    return out


@pytest.mark.parametrize("payload, digest", OLD_REPLIES)
def test_requests_without_min_hold_get_byte_for_byte_the_old_reply(client, payload, digest):
    status, body = client.raw(payload)
    assert status == 200
    assert hashlib.sha256(body.encode()).hexdigest() == digest


@pytest.mark.parametrize(
    "extra, flags, skipped, equity",
    [
        ({"min_hold": 3}, ["--min-hold", "3"], 0, 925.0),
        ({"min_hold": 4}, ["--min-hold", "4"], 1, 1108.0),
        ({"min_hold": 1}, ["--min-hold", "1"], 0, 925.0),
        ({"min_hold": 4, "max_hold": 2}, ["--min-hold", "4", "--max-hold", "2"], 0, 925.0),
    ],
)
def test_hand_case_matches_the_command(client, capsys, tmp_path, monkeypatch, extra, flags, skipped, equity):
    status, reply = client.post({**BASE, **extra})
    assert status == 200
    summary = reply["summary"]
    assert (summary["min_hold_bars"], summary["min_hold_skipped_sells"]) == (extra["min_hold"], skipped)
    assert summary["end_equity"]["value"] == pytest.approx(equity)
    assert reply["params"]["min_hold"] == extra["min_hold"]
    # The report is the command's text report line for line; the summary keys are its --json values.
    text = cli_run(capsys, tmp_path, monkeypatch, flags)
    assert text == "\n".join(reply["report"]) + "\n" + reply["disclaimer"] + "\n"
    backtest = json.loads(cli_run(capsys, tmp_path, monkeypatch, [*flags, "--json"]))["backtest"]
    keys = ["trades", "buys", "sells", "min_hold_bars", "min_hold_skipped_sells"]
    keys += ["max_hold_bars", "time_exits"] if "max_hold" in extra else []
    assert {k: summary[k] for k in keys} == {k: backtest[k] for k in keys}
    # Next to the max-hold keys, right before them.
    order = list(summary)
    assert order[order.index("min_hold_bars") + 1] == "min_hold_skipped_sells"
    if "max_hold" in extra:
        assert order[order.index("min_hold_skipped_sells") + 1] == "max_hold_bars"


def test_min_hold_alone_adds_no_reason_to_trades_or_export(client):
    _, plain = client.post(BASE)
    _, reply = client.post({**BASE, "min_hold": 4})
    assert reply["columns"] == plain["columns"] and "reason" not in reply["columns"]
    assert all("reason" not in trade for trade in reply["trades"])
    assert len(reply["rows"]) == len(plain["rows"]) == 11


@pytest.mark.parametrize("value", [4, 4.0, "4", " 4 "])
def test_accepted_forms(client, value):
    status, reply = client.post({**BASE, "min_hold": value})
    assert status == 200
    assert reply["summary"]["min_hold_bars"] == 4 and reply["params"]["min_hold"] == 4


@pytest.mark.parametrize(
    "value, message",
    [
        (True, "min_hold must be a whole number"),
        (False, "min_hold must be a whole number"),
        (4.5, "min_hold must be a whole number, got 4.5"),
        ("4.0", "min_hold must be a whole number, got '4.0'"),
        ("abc", "min_hold must be a whole number, got 'abc'"),
        ([4], "min_hold must be a whole number"),
        (0, "--min-hold must be a whole number of at least 1, got 0"),
        (-1, "--min-hold must be a whole number of at least 1, got -1"),
        ("0", "--min-hold must be a whole number of at least 1, got 0"),
    ],
)
def test_bad_values_are_400(client, value, message):
    status, reply = client.post({**BASE, "min_hold": value})
    assert (status, reply) == (400, {"ok": False, "error": message})
