"""POST /api/backtest with max_losses (the command's --max-losses N).

max_losses is read exactly like max_hold and min_hold: a JSON whole number (2, or 2.0, which reads as 2) or a string
holding one ("2", " 2 "); null, "" or no key leave it off; true/false, a fraction, other text ("2.0", "abc"), a list
or an object is a 400. Then the command line's own cli.check_max_losses: below 1 is a 400 with the command's
message. It needs no stop and no candle data. With it, summary has max_losses, loss_halt_bar and loss_skipped_buys
(the --json keys) and params echoes max_losses; a request without it gets exactly the old reply.

Hand case: losses.csv of test_cli_max_losses.py (close-only), cash 1000, short 1, long 2.
"""

import contextlib
import hashlib
import http.client
import io
import json
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

LOSSES = [10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13]
CSV = "date,close\n" + "".join(f"2026-01-{d:02d},{c}\n" for d, c in enumerate(LOSSES, 1))
BASE = {"csv": CSV, "short": 1, "long": 2, "cash": 1000}
CLI = ["losses.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000"]

# sha256 of the raw reply bodies, recorded from the server as it was before it took max_losses (git HEAD, run in a
# separate worktree).
OLD_REPLIES = [
    (BASE, 200, "688b4e64fcc018516330e91d6e348e73c4073e99b873e54f99905b8aba8caf94"),
    ({**BASE, "max_losses": None}, 200, "688b4e64fcc018516330e91d6e348e73c4073e99b873e54f99905b8aba8caf94"),
    ({**BASE, "max_losses": ""}, 200, "688b4e64fcc018516330e91d6e348e73c4073e99b873e54f99905b8aba8caf94"),
    ({**BASE, "min_hold": 4, "max_hold": 3, "max_drawdown": 17, "fee": 1}, 200,
     "db2c596331a085f5707e6f223626b59d9b5de871a368f7b0469d43f1376e4efd"),
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "cooldown": 3, "fill": "open",
      "breakeven": 5}, 200, "e014c4f0c6019c1cb1a4f7559599e2fdeeb88ca6afa50535d77b14a493819616"),
    ({**BASE, "max_hold": 0}, 400, "84d01ee4fa7a98477fc50ab0b30cb33a9a380cdc9c709a7976782491850175ec"),
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


def cli_run(tmp_path, monkeypatch, argv):
    (tmp_path / "losses.csv").write_text(CSV)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main([*CLI, *argv])
    assert (code, err.getvalue()) == (0, "")
    return out.getvalue()


@pytest.mark.parametrize("payload, status, digest", OLD_REPLIES)
def test_requests_without_max_losses_get_byte_for_byte_the_old_reply(client, payload, status, digest):
    got_status, body = client.raw(payload)
    assert (got_status, hashlib.sha256(body.encode()).hexdigest()) == (status, digest)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_hand_case_equals_the_command(client, tmp_path, monkeypatch, n):
    status, reply = client.post({**BASE, "max_losses": n})
    assert status == 200
    backtest = json.loads(cli_run(tmp_path, monkeypatch, ["--max-losses", str(n), "--json"]))["backtest"]
    keys = ("max_losses", "loss_halt_bar", "loss_skipped_buys", "trades", "buys", "sells")
    assert {k: reply["summary"][k] for k in keys} == {k: backtest[k] for k in keys}
    assert reply["summary"]["end_equity"]["value"] == backtest["final_equity"]
    text = cli_run(tmp_path, monkeypatch, ["--max-losses", str(n)])
    assert reply["report"] + [reply["disclaimer"]] == text.splitlines()
    # It makes no fill of its own: no reason on the trades and no reason column.
    assert all("reason" not in trade for trade in reply["trades"]) and "reason" not in reply["columns"]


def test_params_echo_and_summary_keys_come_after_the_others(client):
    status, reply = client.post({**BASE, "max_hold": 3, "max_drawdown": 50, "max_losses": "2"})
    assert status == 200
    assert list(reply["params"])[-3:] == ["max_hold", "max_drawdown", "max_losses"]
    assert reply["params"]["max_losses"] == 2
    keys = list(reply["summary"])
    i = keys.index("max_losses")
    assert keys[i - 3 : i + 4] == [
        "max_drawdown_limit_pct", "drawdown_halt_bar", "drawdown_skipped_buys",
        "max_losses", "loss_halt_bar", "loss_skipped_buys", "round_trips",
    ]


@pytest.mark.parametrize("value", [2, 2.0, "2", " 2 "])
def test_accepted_forms(client, value):
    status, reply = client.post({**BASE, "max_losses": value})
    assert status == 200
    assert reply["params"]["max_losses"] == 2 and reply["summary"]["max_losses"] == 2


@pytest.mark.parametrize(
    "value, message",
    [
        (True, "max_losses must be a whole number"),
        (False, "max_losses must be a whole number"),
        (2.5, "max_losses must be a whole number, got 2.5"),
        ("2.0", "max_losses must be a whole number, got '2.0'"),
        ("abc", "max_losses must be a whole number, got 'abc'"),
        ([2], "max_losses must be a whole number"),
        (0, "--max-losses must be a whole number of at least 1, got 0"),
        (-1, "--max-losses must be a whole number of at least 1, got -1"),
        ("0", "--max-losses must be a whole number of at least 1, got 0"),
    ],
)
def test_bad_values_are_400(client, value, message):
    status, reply = client.post({**BASE, "max_losses": value})
    assert (status, reply) == (400, {"ok": False, "error": message})
