"""POST /api/backtest with scale_out (the command's --scale-out PCT).

scale_out is read exactly like breakeven: a JSON number or a string holding one; null, "" or no key leave it off;
true/false, other text, a list or an object is a 400; nan and infinity are a 400. Then the command's rule and
message: above 0. It needs candle data but is not a stop (no cooldown with it alone). With it, summary has the
two --json keys (scale_out_pct, scale_out_exits) after the breakeven keys, params echoes it, and trades and the
export carry a reason; a request without it gets exactly the old reply (OLD_REPLIES: sha256 of the raw reply
bodies from the server before it took scale_out, git HEAD 9ab3743; the server just before this change gave the
same). Five tests, none parametrized.
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
CLOSES_CSV = "date,close\n" + "".join(
    f"2026-01-{i:02d},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2], 1)
)
BASE = {"csv": C_CSV, "short": 1, "long": 2, "cash": 1000}
CL = {"csv": CLOSES_CSV, "short": 1, "long": 2, "cash": 1000}


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


def cli_run(capsys, folder, argv):
    code = cli_main(["c.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000", *argv])
    out, _ = capsys.readouterr()
    assert code == 0
    return out


def test_hand_case_matches_the_text_report_and_json(client, capsys, tmp_path, monkeypatch):
    shutil.copy(DATA / "c.csv", tmp_path / "c.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    cases = [
        ({"scale_out": 5}, ["--scale-out", "5"], 1, "995.95"),
        ({"scale_out": 9}, ["--scale-out", "9"], 1, "1,016.15"),
        ({"scale_out": 10}, ["--scale-out", "10"], 0, "925.00"),
        ({"scale_out": 5, "stop_loss": 10}, ["--scale-out", "5", "--stop-loss", "10"], 1, "991.45"),
    ]
    for extra, flags, exits, equity in cases:
        status, reply = client.post({**BASE, **extra})
        assert status == 200 and reply["ok"], extra
        s = reply["summary"]
        assert reply["report"] == cli_run(capsys, tmp_path, flags).splitlines()[:-1], extra  # the text report
        js = json.loads(cli_run(capsys, tmp_path, [*flags, "--json"]))["backtest"]
        assert (s["scale_out_pct"], s["scale_out_exits"]) == (js["scale_out_pct"], js["scale_out_exits"])
        assert (s["scale_out_pct"], s["scale_out_exits"], s["end_equity"]["text"]) == (extra["scale_out"], exits, equity)
        assert (s["trades"], s["buys"], s["sells"], s["round_trips"], s["winning_round_trips"]) == (
            js["trades"], js["buys"], js["sells"], js["round_trips"], js["winning_round_trips"])
        assert (s["end_equity"]["value"], s["end_cash"]["value"], s["end_shares"]) == (
            js["final_equity"], js["final_cash"], js["final_position"])
        assert [(t["bar"], t["side"], t["shares"], t["price"]["value"], t["cash_after"]["value"], t["reason"])
                for t in reply["trades"]] == [
            (f["bar"], f["side"], f["shares"], f["price"], f["cash_after"], f["reason"]) for f in js["fills"]]
        assert reply["columns"][-1] == "reason"
        assert reply["params"]["scale_out"] == extra["scale_out"]


def test_values_are_read_exactly_like_breakeven(client):
    # Each value gives the same status and, with the name swapped, the same message or setting as breakeven.
    values = ["5", '"5"', '" 5 "', "5.0", '"5.0"', "2.5", '"1,5"', "null", '""', "true", "false", '"abc"', "[5]",
              "{}", "NaN", "Infinity", "-Infinity", '"nan"', '"inf"', "0", "-1", '"0"', '"-0.5"', "1e-9"]
    csv = json.dumps(C_CSV)
    seen = set()
    for value in values:
        got = {}
        for key in ("scale_out", "breakeven"):
            status, text = client.raw('{"csv": %s, "short": 1, "long": 2, "cash": 1000, "%s": %s}' % (csv, key, value))
            reply = json.loads(text)
            shown = reply["error"] if status != 200 else reply["params"].get(key, "off")
            if isinstance(shown, str):
                shown = shown.replace("--breakeven", "--scale-out").replace("breakeven", "scale_out")
            got[key] = (status, shown)
        assert got["scale_out"] == got["breakeven"], value
        seen.add(got["scale_out"][1] if got["scale_out"][0] == 400 else got["scale_out"])
    assert {
        (200, 5.0), (200, 2.5), (200, 15.0), (200, "off"), (200, 1e-9),
        "scale_out must be a number", "scale_out must be a number, got 'abc'", "scale_out must be a finite number",
        "--scale-out must be above 0, got 0", "--scale-out must be above 0, got -1", "--scale-out must be above 0, got -0.5",
    } == seen


def test_needs_candle_data_but_is_not_a_stop(client):
    status, reply = client.post({**CL, "scale_out": 5})
    assert status == 400
    assert reply["error"].startswith("CSV has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close')")
    assert client.post({**CL, "take_profit": 5})[1]["error"] == reply["error"]  # the same as the other exits
    status, reply = client.post({"source": "sample", "sample": "random_walk", "scale_out": 5})
    assert status == 200 and reply["summary"]["scale_out_exits"] >= 1  # a sample uses its candles
    status, reply = client.post({**BASE, "scale_out": 5, "cooldown": 2})
    assert (status, reply["error"]) == (
        400, "--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop")


def test_key_places(client):
    status, reply = client.post({**BASE, "trailing_stop": 20, "atr_stop": True, "atr_period": 2, "breakeven": 50,
                                 "scale_out": 5, "cooldown": 2, "max_hold": 9, "max_losses": 3})
    assert status == 200
    keys = list(reply["summary"])
    assert keys[keys.index("sells"): keys.index("round_trips")] == [
        "sells", "risk_skipped_buys", "breakeven_pct", "breakeven_exits", "scale_out_pct", "scale_out_exits",
        "cooldown_bars", "cooldown_skipped_buys", "max_hold_bars", "time_exits", "max_losses", "loss_halt_bar",
        "loss_skipped_buys",
    ]
    assert list(reply["params"])[-3:] == ["breakeven", "max_losses", "scale_out"]
    assert reply["summary"]["scale_out_exits"] == sum(t["reason"] == "scale_out" for t in reply["trades"])


# sha256 of the raw reply bodies from the server before it took scale_out (see the module docstring).
OLD_REPLIES = [
    (BASE, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "scale_out": None}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "scale_out": ""}, "307921632b8e7e06e2f7ada7dbf935a8caf61d270ea186d778573ef41dc206b1"),
    ({**BASE, "stop_loss": 5, "cooldown": 3}, "b8239effcbf497961c8bdb12d4ee006687dec18dde89869d6b7463ace1586dc5"),
    ({**BASE, "trailing_stop": 10, "take_profit": 20, "fill": "open"},
     "b177134af57aaa935a677202994da6cd34a05fbeec4f4a282d8b3a89537b9842"),
    ({**BASE, "risk_pct": 1, "atr_period": 2, "atr_stop": True},
     "8be75e1a4f43c080a4a0912b96e74c551854781e56de4a48a93ccf27fb4adc9b"),
    ({**BASE, "breakeven": 5, "stop_loss": 10, "slippage": 0.5, "fee": 1},
     "82b752ff32f13bcfe22be89866ec8970da40204b76dbec1a769890da04d53a56"),
    ({**CL, "min_hold": 2, "max_hold": 3, "max_drawdown": 5, "max_losses": 1},
     "6f9db23ac7a89a8239ecc0da0649d9fa4564b5346c6885e07514512bf7f2e5a6"),
    ({**CL, "strategy": "breakout", "params": {"window": 1}, "position_size": 0.5},
     "982d9841b33a05eddc25d41e58805e1ad22d758155694da0b8d98be98a4d2b84"),
    ({"source": "sample", "sample": "uptrend", "stop_loss": 5},
     "413eb54f359dee899e00ee4498a2c00f9348468a3fc3dbab09c178fbfc888668"),
    ({**BASE, "stop_loss": 0}, "d51936fd7749c4ec277f269ce4ef29951039e1a2153f099a36637addad89da83"),
    ({**CL, "take_profit": 5}, "31bf266ec428ab459c6a2cf9f5391edb84cc284764c590016dcbc55c648edb36"),
    ({**BASE, "breakeven": "inf"}, "6fd6e60fde16b4efd817da7ecb0afab38c6586b02a81a32dc581e8fa22d994fe"),
]


def test_requests_without_it_get_exactly_the_old_reply(client):
    for payload, digest in OLD_REPLIES:
        status, text = client.raw(payload)
        assert "scale_out" not in text, payload
        assert hashlib.sha256(text.encode()).hexdigest() == digest, payload
