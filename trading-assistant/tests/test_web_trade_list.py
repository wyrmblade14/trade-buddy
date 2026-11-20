"""POST /api/backtest with trade_list (the command's --trade-list).

trade_list is read exactly like atr_stop, the only other switch field (_as_bool): true turns it on; false, null, ""
or no key leave it off; any string, any number, a list or an object is a 400. With true, report ends with the
command's trade list table and the reply ends with trade_list, the --json array; params echoes trade_list when sent.
It needs no candle data. A request without it gets exactly the old reply.

Hand case: tests/data/c.csv, cash 1000, short 1, long 2 (see test_trade_list.py for the arithmetic).
"""

import contextlib
import hashlib
import http.client
import io
import json
import threading
from pathlib import Path

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

DATA = Path(__file__).parent / "data"
C = (DATA / "c.csv").read_text()
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, as a close-only file
CLOSE_ONLY = "date,close\n" + "".join(f"2026-01-{i:02d},{c}\n" for i, c in enumerate(CLOSES, 1))
BASE = {"csv": C, "short": 1, "long": 2, "cash": 1000}
FLAGS = ["--backtest", "--short", "1", "--long", "2", "--cash", "1000"]

# sha256 of the raw reply bodies, recorded from the server as it was before it took trade_list (git HEAD 145253b,
# run in a separate worktree).
OLD_REPLIES = [
    (BASE, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "cooldown": 3, "fill": "open", "breakeven": 5,
      "scale_out": 4}, "2a1ed970e8a6921b9335ca965dcbf12ef8c26c95c037d36b76b864782300f29f"),
    ({**BASE, "trade_list": None}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
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


def cli_run(tmp_path, monkeypatch, name, text, argv):
    (tmp_path / name).write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main([name, *FLAGS, *argv])
    assert (code, err.getvalue()) == (0, "")
    return out.getvalue()


@pytest.mark.parametrize("payload, digest", OLD_REPLIES, ids=["c-csv", "sample-with-exits", "trade-list-null"])
def test_requests_without_trade_list_get_byte_for_byte_the_old_reply(client, payload, digest):
    status, body = client.raw(payload)
    assert (status, hashlib.sha256(body.encode()).hexdigest()) == (200, digest)


@pytest.mark.parametrize(
    "name, text, extra, flags",
    [
        ("c.csv", C, {}, []),
        ("c.csv", C, {"scale_out": 5}, ["--scale-out", "5"]),
        ("closes.csv", CLOSE_ONLY, {}, []),  # no candle data needed
    ],
    ids=["c-csv", "scale-out-5", "close-only"],
)
def test_true_gives_the_command_table_and_json_rows(client, tmp_path, monkeypatch, name, text, extra, flags):
    status, reply = client.post({**BASE, "csv": text, **extra, "trade_list": True})
    assert status == 200
    # The report is the command's text, line for line, the trade list table included.
    table_text = cli_run(tmp_path, monkeypatch, name, text, [*flags, "--trade-list"])
    assert reply["report"] + [reply["disclaimer"]] == table_text.splitlines()
    assert "Trade list (bar index is 0-based)" in reply["report"]
    # The array is the --json array; the round trip numbers are untouched.
    backtest = json.loads(cli_run(tmp_path, monkeypatch, name, text, [*flags, "--trade-list", "--json"]))["backtest"]
    assert reply["trade_list"] == backtest["trade_list"]
    assert len(reply["trade_list"]) == 2 and reply["trade_list"][1]["open"] is True
    # Everything else is the reply without it, apart from the params echo (the last key) and the table.
    _, without = client.post({**BASE, "csv": text, **extra})
    assert list(reply)[-1] == "trade_list" and list(reply["params"])[-1] == "trade_list"
    reply.pop("trade_list")
    assert reply["params"].pop("trade_list") is True
    n = len(without["report"])
    assert reply["report"][n:] == table_text.splitlines()[n:-1]
    reply["report"] = reply["report"][:n]
    assert reply == without


def test_false_changes_nothing_but_the_params_echo(client):
    status, reply = client.post({**BASE, "trade_list": False})
    assert status == 200
    _, without = client.post(BASE)
    assert "trade_list" not in reply
    assert reply["params"].pop("trade_list") is False  # echoed when sent, like atr_stop: false
    assert reply == without


def test_anything_but_true_false_null_or_empty_is_a_400(client):
    # Exactly atr_stop's rules and message form: strings (even "true") and numbers (even 1) are refused.
    for value, shown in [("true", "'true'"), ("yes", "'yes'"), (" no ", "'no'"), (1, "1"), (0, "0"), (1.5, "1.5")]:
        assert client.post({**BASE, "trade_list": value}) == (
            400, {"ok": False, "error": f"trade_list must be true or false, got {shown}"}
        ), value
        assert client.post({**BASE, "atr_stop": value}) == (
            400, {"ok": False, "error": f"atr_stop must be true or false, got {shown}"}
        ), value
    for value in ([True], {"on": True}):
        assert client.post({**BASE, "trade_list": value}) == (400, {"ok": False, "error": "trade_list must be true or false"})
    assert client.post({**BASE, "trade_list": ""})[1] == client.post(BASE)[1]  # "" is off, like null
