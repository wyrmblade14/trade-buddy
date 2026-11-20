"""POST /api/backtest with breakeven (the command's --breakeven PCT).

breakeven is read exactly like take_profit: a JSON number or a string holding one; null, "" or no key leave it
off; true/false, other text, a list or an object is a 400; nan and infinity are a 400 (unlike the flag, the API
never takes infinity). Then the command's rule and message: above 0. It is a stop: it needs candle data and
counts as a stop for cooldown. With it, summary has the two --json keys, params echoes it, and trades and the
export carry a reason; a request without it gets exactly the old reply.
"""

import hashlib
import http.client
import json
import shutil
import threading
from pathlib import Path

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

DATA = Path(__file__).resolve().parent / "data"
C_CSV = (DATA / "c.csv").read_text()
BASE = {"csv": C_CSV, "short": 1, "long": 2, "cash": 1000}

# sha256 of the raw reply bodies from the server before it took breakeven (captured from the unchanged code).
OLD_REPLIES = [
    (BASE, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "breakeven": None}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "breakeven": ""}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "stop_loss": 5, "cooldown": 3}, "b8239effcbf497961c8bdb12d4ee006687dec18dde89869d6b7463ace1586dc5"),
    ({**BASE, "trailing_stop": 10, "take_profit": 20, "fill": "open"},
     "b177134af57aaa935a677202994da6cd34a05fbeec4f4a282d8b3a89537b9842"),
]


class Client:
    def __init__(self, server):
        self.host, self.port = server.server_address[:2]

    def raw(self, payload):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        conn.request(
            "POST", "/api/backtest", body=body.encode(),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
        )
        resp = conn.getresponse()
        text = resp.read().decode()
        conn.close()
        return resp.status, text

    def post(self, payload):
        status, text = self.raw(payload)
        return status, json.loads(text)


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Client(server)
    server.shutdown()
    server.server_close()


def cli_run(capsys, tmp_path, monkeypatch, argv):
    shutil.copy(DATA / "c.csv", tmp_path / "c.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    code = cli_main(["c.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000", *argv])
    out, _ = capsys.readouterr()
    assert code == 0
    return out


@pytest.mark.parametrize(
    "extra, flags, exits, equity",
    [
        ({"breakeven": 5}, ["--breakeven", "5"], 1, "1,016.60"),
        ({"breakeven": 9}, ["--breakeven", "9"], 1, "1,016.60"),
        ({"breakeven": 10}, ["--breakeven", "10"], 0, "925.00"),
        ({"breakeven": 5, "cooldown": 3}, ["--breakeven", "5", "--cooldown", "3"], 1, "1,000.00"),
    ],
)
def test_c_csv_cases_match_the_command_line(client, capsys, tmp_path, monkeypatch, extra, flags, exits, equity):
    status, data = client.post({**BASE, **extra})
    assert status == 200
    summary = data["summary"]
    keys = list(summary)
    assert keys[keys.index("sells") + 1 : keys.index("sells") + 3] == ["breakeven_pct", "breakeven_exits"]
    assert (summary["breakeven_pct"], summary["breakeven_exits"]) == (float(extra["breakeven"]), exits)
    assert summary["end_equity"]["text"] == equity
    assert data["params"]["breakeven"] == float(extra["breakeven"]) and list(data["params"])[-1] == "breakeven"
    assert data["columns"][-1] == "reason"
    # The report is the command line's text report line for line (the CLI adds only the disclaimer) ...
    text = cli_run(capsys, tmp_path, monkeypatch, flags)
    assert data["report"] == text.splitlines()[:-1]
    # ... and the numbers are its --json numbers.
    bt = json.loads(cli_run(capsys, tmp_path, monkeypatch, [*flags, "--json"]))["backtest"]
    assert [(t["bar"], t["side"], t["shares"], t["price"]["value"], t["reason"]) for t in data["trades"]] == [
        (f["bar"], f["side"], f["shares"], f["price"], f["reason"]) for f in bt["fills"]
    ]
    for key in ("breakeven_pct", "breakeven_exits", "trades", "buys", "sells", "cooldown_bars", "cooldown_skipped_buys"):
        assert summary.get(key) == bt.get(key), key
    assert summary["end_equity"]["value"] == bt["final_equity"]


CLOSE_ONLY = "date,close\n2026-01-01,10\n2026-01-02,9\n2026-01-03,8\n2026-01-04,9\n2026-01-05,11\n"


@pytest.mark.parametrize(
    "raw, error",
    [
        ("0", "--breakeven must be above 0, got 0"),
        ('"-1"', "--breakeven must be above 0, got -1"),
        ("NaN", "breakeven must be a finite number"),
        ('"nan"', "breakeven must be a finite number"),
        ("Infinity", "breakeven must be a finite number"),
        ('"inf"', "breakeven must be a finite number"),  # the flag takes inf; the API, like take_profit, does not
        ("true", "breakeven must be a number"),
        ('"abc"', "breakeven must be a number, got 'abc'"),
        ("[5]", "breakeven must be a number"),
    ],
)
def test_bad_values_are_400(client, raw, error):
    body = json.dumps(BASE)[:-1] + f', "breakeven": {raw}}}'
    status, data = client.post(body)
    assert (status, data) == (400, {"ok": False, "error": error})


def test_close_only_csv_is_400_like_the_other_stops(client):
    status, data = client.post({"csv": CLOSE_ONLY, "short": 1, "long": 2, "breakeven": 5})
    _, stop = client.post({"csv": CLOSE_ONLY, "short": 1, "long": 2, "stop_loss": 5})
    assert status == 400 and data == stop
    assert data["error"].startswith("CSV has no 'open', 'high', 'low', 'volume' columns")


@pytest.mark.parametrize("payload, digest", OLD_REPLIES)
def test_requests_without_breakeven_get_exactly_the_old_reply(client, payload, digest):
    status, text = client.raw(payload)
    assert status == 200 and hashlib.sha256(text.encode()).hexdigest() == digest
