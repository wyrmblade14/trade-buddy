"""POST /api/backtest with max_drawdown (the command's --max-drawdown PCT).

max_drawdown is read like the other number fields (stop_loss): a JSON number or a string holding one; null, ""
or no key leave it off; true/false, other text or any other type is a 400. Then the command line's own
cli.check_max_drawdown: not above 0 and below 100 is a 400 with the command's message. It needs no stop and no
candle data. With it, summary has the three --json keys, params echoes it, and trades and the export carry a
reason; a request without it gets exactly the old reply.
"""

import hashlib
import http.client
import json
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web


def close_file(closes):
    return "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes))


CLOSES = close_file([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2])  # closes.csv of docs/cli.md
RALLY = close_file([10, 10, 10, 10, 11, 20, 32, 28, 30, 25, 35, 36])  # worked out in test_max_drawdown.py
BASE = {"csv": CLOSES, "short": 1, "long": 2, "cash": 1000}

# sha256 of the raw reply bodies from the server before it took max_drawdown (the same bodies and hashes as
# OLD_REPLIES in test_web_max_hold.py, captured before max_hold existed and unchanged by it).
OLD_REPLIES = [
    (BASE, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "max_drawdown": None}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "max_drawdown": ""}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
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


def cli_run(capsys, tmp_path, monkeypatch, text, argv):
    (tmp_path / "prices.csv").write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    code = cli_main(["prices.csv", "--backtest", "--cash", "1000", *argv])
    out, err = capsys.readouterr()
    assert (code, err) == (0, "")
    return out


@pytest.mark.parametrize("payload, expected", OLD_REPLIES)
def test_requests_without_max_drawdown_get_byte_for_byte_the_old_reply(client, payload, expected):
    status, body = client.raw(payload)
    assert status == 200 and hashlib.sha256(body.encode()).hexdigest() == expected


@pytest.mark.parametrize(
    "text, long, pct, halt_bar, skipped",
    [(CLOSES, 2, 16, 6, 1), (CLOSES, 2, 17, None, 0), (RALLY, 3, 12.5, 7, 1)],
)
def test_hand_cases_equal_the_command(client, capsys, tmp_path, monkeypatch, text, long, pct, halt_bar, skipped):
    status, reply = client.post({"csv": text, "short": 1, "long": long, "cash": 1000, "max_drawdown": pct})
    assert status == 200
    argv = ["--short", "1", "--long", str(long), "--max-drawdown", str(pct)]
    assert reply["report"] + [web.DISCLAIMER] == cli_run(capsys, tmp_path, monkeypatch, text, argv).splitlines()
    data = json.loads(cli_run(capsys, tmp_path, monkeypatch, text, [*argv, "--json"]))["backtest"]
    summary = reply["summary"]
    keys = list(summary)
    assert keys[keys.index("sells") + 1 : keys.index("round_trips")] == [
        "max_drawdown_limit_pct", "drawdown_halt_bar", "drawdown_skipped_buys",
    ]
    for key in ("max_drawdown_limit_pct", "drawdown_halt_bar", "drawdown_skipped_buys"):
        assert summary[key] == data[key]
    assert (summary["drawdown_halt_bar"], summary["drawdown_skipped_buys"]) == (halt_bar, skipped)
    assert [(t["bar"], t["side"], t["price"]["value"], t["reason"]) for t in reply["trades"]] == [
        (f["bar"], f["side"], f["price"], f["reason"]) for f in data["fills"]
    ]
    assert summary["end_equity"]["value"] == data["final_equity"]
    assert reply["params"]["max_drawdown"] == pct
    # The export rule of the command: a reason column, filled on the rows with a fill.
    assert reply["columns"][-1] == "reason"
    assert [(r[0], r[4], r[-1]) for r in reply["rows"] if r[4]] == [(str(f["bar"]), f["side"], f["reason"]) for f in data["fills"]]


@pytest.mark.parametrize(
    "value, message",
    [
        (0, "--max-drawdown must be above 0 and below 100, got 0"),
        (100, "--max-drawdown must be above 0 and below 100, got 100"),
        ("0", "--max-drawdown must be above 0 and below 100, got 0"),
        (True, "max_drawdown must be a number"),
        ("ten", "max_drawdown must be a number, got 'ten'"),
    ],
)
def test_bad_values_are_400s(client, value, message):
    assert client.post({**BASE, "max_drawdown": value}) == (400, {"ok": False, "error": message})


def test_a_string_holding_a_number_is_read_as_that_number(client):
    assert client.raw({**BASE, "max_drawdown": " 16 "}) == client.raw({**BASE, "max_drawdown": 16})
