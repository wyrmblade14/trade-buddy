"""POST /api/backtest with cooldown (the command's --cooldown N).

cooldown is read like the other whole-number fields (atr_period): a JSON whole
number, or a string holding one; null, "" or no key leave it off; true/false, a
fraction, other text or any other type is a 400. Then the command line's own
cli.check_cooldown: it needs stop_loss, trailing_stop or atr_stop true, and must
be at least 1 (a 400 with the command's one-line message). A cooldown needs a
stop, and a stop needs candle data, so a close-only CSV is the stop's 400.
With it, summary has cooldown_bars and cooldown_skipped_buys (the --json keys)
and the echo params.cooldown; a request without it gets exactly the old reply.

Hand case: the 11-bar candle file of test_cli_cooldown.py, cash 1000, short 1,
long 2, stop_loss 10: cooldown 3 skips the bar 9 buy (end 901), cooldown 2 does
not (end 916).
"""

import hashlib
import http.client
import json
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
"""
CLOSES = "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]))
BASE = {"csv": HAND, "short": 1, "long": 2, "cash": 1000}
STOP = {**BASE, "stop_loss": 10}
CLI = ["--backtest", "--short", "1", "--long", "2", "--cash", "1000", "--stop-loss", "10"]
NEEDS_STOP = "--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop"

# sha256 of the raw reply bodies, captured from the server before it took cooldown.
OLD_REPLIES = [
    (BASE, 200, "d5df99e80f04d22b85be8fdc165bf7fd3f7d305c1cba7c527d5be5caf6e06372"),  # BASE
    (STOP, 200, "08a3b1baab4f550670c08ad7a7aab569039e48d6678b6f7987e5bb05032fb757"),  # BASE+stop
    ({**STOP, "cooldown": None}, 200, "08a3b1baab4f550670c08ad7a7aab569039e48d6678b6f7987e5bb05032fb757"),  # BASE+stop+cooldown null
    ({**STOP, "cooldown": ""}, 200, "08a3b1baab4f550670c08ad7a7aab569039e48d6678b6f7987e5bb05032fb757"),  # BASE+stop+cooldown empty
    ({**STOP, "trailing_stop": 8, "take_profit": 20, "atr_stop": True, "atr_mult": 1, "atr_period": 1, "risk_pct": 0.16, "fill": "open"}, 200, "447269c884c795d6ac3d741864f96253fc9efbd0b90e9581001e0c53c2c8f34a"),  # BASE+all exits, risk, open fills
    ({"csv": CLOSES, "short": 1, "long": 2, "stop_loss": 10}, 400, "31bf266ec428ab459c6a2cf9f5391edb84cc284764c590016dcbc55c648edb36"),  # closes+stop
    ({"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 2, "strategy": "breakout"}, 200, "bab77081d878084fd7c16062b2ce6878ecd2c136e85f2d407fcf6b7232e8ea43"),  # sample
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


def ok(client, payload):
    status, data = client.post(payload)
    assert (status, data.get("error")) == (200, None)
    return data


def cli_run(capsys, tmp_path, monkeypatch, argv):
    (tmp_path / "hand.csv").write_text(HAND)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    try:
        code = cli_main(["hand.csv", *argv])
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def test_requests_without_cooldown_get_byte_for_byte_the_old_reply(client):
    for payload, old_status, old_digest in OLD_REPLIES:
        status, body = client.raw(payload)
        assert (status, hashlib.sha256(body.encode()).hexdigest()) == (old_status, old_digest), payload


@pytest.mark.parametrize("n", [3, 2])
def test_hand_case_matches_the_command(client, capsys, tmp_path, monkeypatch, n):
    data = ok(client, {**STOP, "cooldown": n})
    summary = data["summary"]
    # The report is the command's text report, line for line (without the disclaimer).
    code, out, _ = cli_run(capsys, tmp_path, monkeypatch, [*CLI, "--cooldown", str(n)])
    assert code == 0 and data["report"] == out.splitlines()[:-1]
    # The two keys and the numbers are those of --json.
    code, out, _ = cli_run(capsys, tmp_path, monkeypatch, [*CLI, "--cooldown", str(n), "--json"])
    backtest = json.loads(out)["backtest"]
    for key in ("cooldown_bars", "cooldown_skipped_buys", "trades", "buys", "sells"):
        assert summary[key] == backtest[key], key
    assert (summary["end_equity"]["value"], summary["end_cash"]["value"]) == (backtest["final_equity"], backtest["final_cash"])
    assert (summary["cooldown_bars"], summary["cooldown_skipped_buys"], summary["end_equity"]["text"]) == (
        (3, 1, "901.00") if n == 3 else (2, 0, "916.00")
    )


def test_where_the_keys_go(client):
    data = ok(client, {**STOP, "cooldown": 3})
    assert list(data["params"])[-2:] == ["stop_loss", "cooldown"]
    keys = list(data["summary"])
    assert keys[keys.index("sells") :][:4] == ["sells", "cooldown_bars", "cooldown_skipped_buys", "round_trips"]
    data = ok(client, {**BASE, "atr_stop": True, "atr_mult": 1, "atr_period": 1, "cooldown": 3})
    assert list(data["params"])[-4:] == ["atr_mult", "atr_period", "atr_stop", "cooldown"]
    keys = list(data["summary"])
    assert keys[keys.index("sells") :][:4] == ["sells", "risk_skipped_buys", "cooldown_bars", "cooldown_skipped_buys"]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({**BASE, "cooldown": 3}, NEEDS_STOP),
        ({**BASE, "take_profit": 5, "cooldown": 3}, NEEDS_STOP),
        ({**STOP, "cooldown": 0}, "--cooldown must be a whole number of at least 1, got 0"),
        ({**STOP, "cooldown": -2}, "--cooldown must be a whole number of at least 1, got -2"),
        ({"csv": CLOSES, "short": 1, "long": 2, "stop_loss": 10, "cooldown": 3},
         "CSV has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row "
         "like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'"),
    ],
    ids=["no stop", "target only", "0", "-2", "close-only csv"],
)
def test_400s_with_the_commands_messages(client, payload, message):
    assert client.post(payload) == (400, {"ok": False, "error": message})


@pytest.mark.parametrize("value", [True, False, 1.5, "1.5", "abc", "2.0", [3], {"n": 3}])
def test_bad_types_are_refused_exactly_like_atr_period(client, value):
    status, data = client.post({**STOP, "cooldown": value})
    as_atr_period = client.post({**STOP, "risk_pct": 1, "atr_period": value})
    assert (status, data) == (as_atr_period[0], {"ok": False, "error": as_atr_period[1]["error"].replace("atr_period", "cooldown")})
    assert status == 400 and data["error"].startswith("cooldown must be a whole number")


@pytest.mark.parametrize("value", ["3", " 3 ", 3.0])
def test_a_whole_number_in_a_string_or_as_3_0_is_read_like_3(client, value):
    assert client.raw({**STOP, "cooldown": value}) == client.raw({**STOP, "cooldown": 3})
