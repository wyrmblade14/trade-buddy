"""POST /api/backtest with max_hold (the command's --max-hold N).

max_hold is read like cooldown and the other whole-number fields: a JSON whole
number, or a string holding one; null, "" or no key leave it off; true/false, a
fraction, other text or any other type is a 400. Then the command line's own
cli.check_max_hold: below 1 is a 400 with the command's message. It needs no
stop and no candle data. With it, summary has max_hold_bars and time_exits (the
--json keys), params echoes max_hold, and trades and the export carry a reason;
a request without it gets exactly the old reply.

Hand case: the close-only series of test_cli_max_hold.py, cash 1000, short 1, long 2.
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

# sha256 of the raw reply bodies, captured from the server before it took max_hold.
OLD_REPLIES = [
    (BASE, 200, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "max_hold": None}, 200, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "max_hold": ""}, 200, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "slippage": 0.5, "position_size": 0.5, "fee": 1}, 200,
     "0411bbbe9638b514f19563b27b43b3c47ad56a6f93ebd24d661f735ce96dc5ce"),
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "cooldown": 3, "fill": "open"}, 200,
     "6dfa7b27cf3624301c4315facb7b493ade9f69fd27ae1ae6cbc8912340276f16"),
    ({**BASE, "stop_loss": 10}, 400, "31bf266ec428ab459c6a2cf9f5391edb84cc284764c590016dcbc55c648edb36"),
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


def test_requests_without_max_hold_get_byte_for_byte_the_old_reply(client):
    for payload, old_status, old_digest in OLD_REPLIES:
        status, body = client.raw(payload)
        assert (status, hashlib.sha256(body.encode()).hexdigest()) == (old_status, old_digest), payload


@pytest.mark.parametrize("n", [1, 2, 3])
def test_hand_case_equals_the_command(client, capsys, tmp_path, monkeypatch, n):
    status, data = client.post({**BASE, "max_hold": n})
    assert status == 200
    text = cli_run(capsys, tmp_path, monkeypatch, ["--max-hold", str(n)])
    assert data["report"] + [data["disclaimer"]] == text.splitlines()
    b = json.loads(cli_run(capsys, tmp_path, monkeypatch, ["--max-hold", str(n), "--json"]))["backtest"]
    s = data["summary"]
    keys = list(s)
    assert keys[keys.index("sells") + 1 : keys.index("sells") + 3] == ["max_hold_bars", "time_exits"]
    assert (s["max_hold_bars"], s["time_exits"]) == (b["max_hold_bars"], b["time_exits"]) == (n, {1: 2, 2: 1, 3: 0}[n])
    assert [(t["bar"], t["side"], t["price"]["value"], t["reason"]) for t in data["trades"]] == [
        (f["bar"], f["side"], f["price"], f["reason"]) for f in b["fills"]
    ]
    assert s["end_equity"]["value"] == b["final_equity"]
    assert data["params"]["max_hold"] == n
    cli_run(capsys, tmp_path, monkeypatch, ["--max-hold", str(n), "--export", "e.csv"])
    assert data["columns"][-1] == "reason"
    assert data["csv"].replace("\r\n", "\n") == (tmp_path / "e.csv").read_text().replace("\r\n", "\n")


@pytest.mark.parametrize(
    "value, message",
    [
        (0, "--max-hold must be a whole number of at least 1, got 0"),
        ("-1", "--max-hold must be a whole number of at least 1, got -1"),
        (1.5, "max_hold must be a whole number, got 1.5"),
        ("abc", "max_hold must be a whole number, got 'abc'"),
        (True, "max_hold must be a whole number"),
        ([2], "max_hold must be a whole number"),
    ],
)
def test_bad_values_are_400s(client, value, message):
    assert client.post({**BASE, "max_hold": value}) == (400, {"ok": False, "error": message})


@pytest.mark.parametrize("value", [2, 2.0, "2", " 2 "])
def test_whole_numbers_and_strings_holding_one_are_read(client, value):
    status, data = client.post({**BASE, "max_hold": value})
    assert status == 200 and data["params"]["max_hold"] == 2 and data["summary"]["time_exits"] == 1
