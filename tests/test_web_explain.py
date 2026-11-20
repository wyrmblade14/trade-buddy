"""POST /api/backtest with explain (the command's --explain).

explain is read exactly like atr_stop and trade_list (_as_bool): true turns it on; false, null, "" or no key leave it
off; any string, any number, a list or an object is a 400. With true the reply has "explanation" right after
"report": the decision of the report's Signal line, the command's --explain sentence word for word, and the short and
long SMA on the last bar and the bar before; report gets the sentence as its own line right after the Signal line,
so it is the command's --backtest --explain output line for line. params echoes explain when sent. It needs no candle
data. A request without it gets exactly the old reply.

Hand case: tests/data/c.csv (closes 10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2), short 1, long 3; the 3-bar SMA from
the third bar is 9, 26/3, 28/3, 32/3, 11, 32/3, 31/3, 11, 35.2/3.
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
ROWS = C.splitlines()
CLOSE_ONLY = "date,close\n" + "".join(f"{r.split(',')[0]},{r.split(',')[4]}\n" for r in ROWS[1:])
BASE = {"csv": C, "short": 1, "long": 3}

# sha256 of the raw reply bodies, recorded from the server as it was before it took explain (the baseline commit,
# run in a separate worktree). The old server ignored an unknown explain key, so null gives the plain reply too.
OLD_REPLIES = [
    (BASE, "d4eb8d7a2874619717882b53362f04294ec14dd968301b1e6c6a02ee6d8687ff"),
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "fill": "open", "trade_list": True},
     "eaf6b0e4c03690427b18c17a50c2ba377c8a30b7cee10699e9b942a1480a4cb8"),
    ({**BASE, "explain": None}, "d4eb8d7a2874619717882b53362f04294ec14dd968301b1e6c6a02ee6d8687ff"),
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


def cli_lines(tmp_path, monkeypatch, text):
    """The output lines of ``--backtest --explain`` on ``text`` with --short 1 --long 3 (the disclaimer is last)."""
    (tmp_path / "p.csv").write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli_main(["p.csv", "--short", "1", "--long", "3", "--backtest", "--explain"]) == 0
    return out.getvalue().splitlines()


@pytest.mark.parametrize("payload, digest", OLD_REPLIES, ids=["c-csv", "sample-with-exits", "explain-null"])
def test_requests_without_explain_get_byte_for_byte_the_old_reply(client, payload, digest):
    status, body = client.raw(payload)
    assert (status, hashlib.sha256(body.encode()).hexdigest()) == (200, digest)


@pytest.mark.parametrize(
    "text, decision, last, previous, words",
    [
        (CLOSE_ONLY, "HOLD", (12.2, 35.2 / 3), (12, 11), "stayed above"),  # all 11 bars, as a close-only CSV
        ("\n".join(ROWS[:5]) + "\n", "BUY", (9, 26 / 3), (8, 9), "crossed above"),
        ("\n".join(ROWS[:8]) + "\n", "SELL", (10, 11), (12, 32 / 3), "crossed below"),
        ("\n".join(ROWS[:4]) + "\n", "HOLD", (8, 9), (9, None), "needs at least 4 bars and there are 3"),
    ],
    ids=["11-close-only", "first-4", "first-7", "first-3-too-few"],
)
def test_true_adds_the_explanation_after_report(client, tmp_path, monkeypatch, text, decision, last, previous, words):
    status, reply = client.post({**BASE, "csv": text, "explain": True})
    assert status == 200
    explanation = reply["explanation"]
    assert list(explanation) == ["decision", "sentence", "last_bar", "previous_bar"]
    assert explanation["decision"] == decision and reply["report"][2] == f"Signal:  {decision}"
    assert explanation["last_bar"] == {"short": pytest.approx(last[0]), "long": pytest.approx(last[1])}
    assert explanation["previous_bar"] == {
        "short": pytest.approx(previous[0]), "long": None if previous[1] is None else pytest.approx(previous[1])
    }
    cli = cli_lines(tmp_path, monkeypatch, text)
    assert reply["report"] == cli[:-1]  # the command's --backtest --explain output line for line, minus the disclaimer
    assert explanation["sentence"] == cli[3]  # the command's line, word for word
    assert explanation["sentence"].startswith(decision + " because ") and words in explanation["sentence"]
    # Right after report; everything else is the reply without it, apart from the params echo (the last key).
    keys = list(reply)
    assert keys[keys.index("report") + 1] == "explanation"
    _, without = client.post({**BASE, "csv": text})
    reply.pop("explanation")
    assert list(reply["params"])[-1] == "explain" and reply["params"].pop("explain") is True
    assert reply["report"].pop(3) == explanation["sentence"]  # the line right after Signal:, and no other change
    assert reply == without


def test_false_and_bad_values(client):
    status, reply = client.post({**BASE, "explain": False})
    _, without = client.post(BASE)
    assert status == 200 and "explanation" not in reply
    assert reply["params"].pop("explain") is False  # echoed when sent, like trade_list: false
    assert reply == without
    assert client.post({**BASE, "explain": ""})[1] == without  # "" is off, like null, and not echoed
    # Exactly trade_list's rules and message form: strings (even "true") and numbers (even 1) are refused.
    for value, shown in [("true", "'true'"), (" no ", "'no'"), (1, "1"), (0, "0")]:
        assert client.post({**BASE, "explain": value}) == (
            400, {"ok": False, "error": f"explain must be true or false, got {shown}"}
        ), value
    for value in ([True], {"on": True}):
        assert client.post({**BASE, "explain": value}) == (400, {"ok": False, "error": "explain must be true or false"})
