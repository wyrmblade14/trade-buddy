"""POST /api/backtest with add_on and max_adds (the command's --add-on PCT and --max-adds N).

add_on is read exactly like scale_out (_as_float): a JSON number or a string holding one ("10", " 10 ", "1,000");
null, "" or no key leave it off; true/false, other text, a list or an object is a 400 ("add_on must be a number"),
nan or infinity a 400 ("add_on must be a finite number"). max_adds is read exactly like max_hold (_as_int): a JSON
whole number (2, or 2.0) or a string holding one ("2"); null, "" or no key mean it was not sent; true/false, a
fraction or other text is a 400 ("max_adds must be a whole number..."). Then cli.check_add_on with the command's
messages: add_on above 0, max_adds only with add_on, max_adds at least 1. No candle data is needed.

When add_on is sent, params echoes add_on and max_adds (1 when not sent) after scale_out; summary has the four
--json keys after the scale-out keys; trades and the export carry reason add_on; report has the Add-ons line, and
is the command's report line for line. up.csv (closes 10 9 8 9 11 12 13 14 15 14 13 12, short 1, long 2, cash
1000): position_size 0.5 with add_on 10 gives 1054.00, with 20 1024.00; add_on 10 with all-cash sizing 1180.00
with 3 add-ons skipped (arithmetic in test_add_on.py).

OLD_REPLIES: sha256 of the raw reply bodies of OLD_REQUESTS, recorded from the server before it took add_on (its
code as in the baseline commit; the engine and command line already had the add-ons, which the server could not
reach). Some of those requests send add_on and max_adds as null or "", which must change nothing.
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

DATA = Path(__file__).resolve().parent / "data"
C_CSV = (DATA / "c.csv").read_text()
UP_VALUES = [10, 9, 8, 9, 11, 12, 13, 14, 15, 14, 13, 12]
UP_CSV = "close\n" + "".join(f"{c}\n" for c in UP_VALUES)
UP = {"csv": UP_CSV, "short": 1, "long": 2, "cash": 1000}
C = {"csv": C_CSV, "short": 1, "long": 2, "cash": 1000}
PS = {**UP, "position_size": 0.5}

OLD_REQUESTS = {
    "up": UP,
    "up ps": {**UP, "position_size": 0.5},
    "up ps nulls": {**UP, "position_size": 0.5, "add_on": None, "max_adds": None},
    "up ps empty": {**UP, "position_size": 0.5, "add_on": "", "max_adds": ""},
    "up holds halts": {**UP, "position_size": 0.5, "min_hold": 3, "max_hold": 4, "max_drawdown": 5, "max_losses": 1,
                       "trade_list": True, "explain": True},
    "up fees": {**UP, "fee": 1, "fee_pct": 0.1, "slippage": 1, "position_size": 0.5},
    "c stops": {**C, "stop_loss": 5, "take_profit": 8, "trailing_stop": 6, "position_size": 0.5},
    "c atr": {**C, "risk_pct": 2, "atr_period": 3, "atr_stop": True, "cooldown": 2},
    "c be so open": {**C, "fill": "open", "breakeven": 3, "scale_out": 5, "position_size": 0.5},
    "sample": {"source": "sample", "sample": "random_walk", "short": 10, "long": 30},
    "sample breakout": {"source": "sample", "sample": "random_walk", "strategy": "breakout", "params": {"window": 5},
                        "max_hold": 10, "trade_list": True},
    "bad scale_out": {**C, "scale_out": 0},
    "bad max_hold": {**UP, "max_hold": "x"},
}
OLD_REPLIES = {
    'up': (200, '959604e5cd40ada4d5b2bfa6ea8e5bebce8991235250bab2bff9d851603bc0e5'),
    'up ps': (200, '84cca7302c910a09823df9cd8db8327afda97df554ae9ae2d037d5dfa2cb4e95'),
    'up ps nulls': (200, '84cca7302c910a09823df9cd8db8327afda97df554ae9ae2d037d5dfa2cb4e95'),
    'up ps empty': (200, '84cca7302c910a09823df9cd8db8327afda97df554ae9ae2d037d5dfa2cb4e95'),
    'up holds halts': (200, '3bcedddd9713ac8d9308b5585684c7059592a7a01b5c88108c6b2077b3c386f7'),
    'up fees': (200, '9acce3f9e26a0e265b24f72f390e0370cbd3aebc5837a3acb325b8d44f8dcb47'),
    'c stops': (200, '63b32259eea21f733f32b84e1d3859222f67b13e53caa7321ffc17b8034c9cf2'),
    'c atr': (200, '8844ecbf20192292dc83278dd15ebb50783e11b91fc7d4fb8f19dbfc4572d443'),
    'c be so open': (200, '65c2980516b951b3a33266bcd3da15d37242e194d3f6de5f44c1b559e4e9f29b'),
    'sample': (200, '01af92e59c92c9b13a069ed7fd1a714599579857f849c62d090213e2689afb72'),
    'sample breakout': (200, 'd01d1c97a238e4e4458d925894989175b25ed990164790f47aee966a9e9ca96f'),
    'bad scale_out': (400, 'd141b1cd58b2c8f57f9acf1f6d27de02c2566abd60c80e60dfd754153581d00d'),
    'bad max_hold': (400, '26dd15baa2fad0a1b65b0be964724498d7cf201ebe11cef03cb62626b1fe1afc'),
}


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


def cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli_main(list(argv))
    assert code == 0
    return out.getvalue()


@pytest.mark.parametrize("name", list(OLD_REQUESTS))
def test_requests_without_add_on_get_byte_for_byte_the_old_reply(client, name):
    status, body = client.raw(OLD_REQUESTS[name])
    assert (status, hashlib.sha256(body.encode()).hexdigest()) == OLD_REPLIES[name]


@pytest.mark.parametrize(
    "extra, flags, buys, skipped, equity",
    [
        ({"position_size": 0.5, "add_on": 10}, ["--position-size", "0.5", "--add-on", "10"], 1, 0, "1,054.00"),
        ({"position_size": 0.5, "add_on": "20"}, ["--position-size", "0.5", "--add-on", "20"], 1, 0, "1,024.00"),
        ({"add_on": 10, "max_adds": None}, ["--add-on", "10"], 0, 3, "1,180.00"),
    ],
    ids=["10", "20 as a string", "10 all cash, max_adds null"],
)
def test_reply_matches_the_command(client, tmp_path, monkeypatch, extra, flags, buys, skipped, equity):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    (tmp_path / "up.csv").write_text(UP_CSV)
    argv = ["up.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000", *flags]
    status, reply = client.post({**UP, **extra})
    assert status == 200
    # report: the command's text report, line for line (without the disclaimer).
    assert reply["report"] == cli(argv).splitlines()[:-1]
    # params echoes both (max_adds 1 when not sent), right after the settings sent before them.
    assert list(reply["params"])[-2:] == ["add_on", "max_adds"]
    assert (reply["params"]["add_on"], reply["params"]["max_adds"]) == (float(extra["add_on"]), 1)
    # summary: the four --json keys, with the --json values, after sells (no scale-out keys here).
    data = json.loads(cli(argv + ["--json"]))["backtest"]
    four = ["add_on_pct", "max_adds", "add_on_buys", "add_on_skipped_buys"]
    keys = list(reply["summary"])
    assert keys[keys.index("sells") + 1: keys.index("sells") + 5] == four
    assert [reply["summary"][k] for k in four] == [data[k] for k in four] == [float(extra["add_on"]), 1, buys, skipped]
    assert reply["summary"]["end_equity"]["text"] == equity
    # trades and the export carry the reason; the export is the command's --export file.
    assert [t["reason"] for t in reply["trades"]] == [f["reason"] for f in data["fills"]]
    assert ("add_on" in [t["reason"] for t in reply["trades"]]) == (buys == 1)
    assert reply["columns"][-1] == "reason"
    cli(argv + ["--export", "e.csv"])
    assert reply["csv"] == (tmp_path / "e.csv").read_bytes().decode()  # both written by the csv module, \r\n


@pytest.mark.parametrize(
    "extra, status, outcome",
    [
        ({"add_on": " 10 "}, 200, (10.0, 1)),
        ({"add_on": "1,000"}, 200, (1000.0, 1)),
        ({"add_on": 10, "max_adds": "2"}, 200, (10.0, 2)),
        ({"add_on": 10, "max_adds": 2.0}, 200, (10.0, 2)),
        ({"add_on": 10, "max_adds": ""}, 200, (10.0, 1)),
        ({"add_on": 0}, 400, "--add-on must be above 0, got 0"),
        ({"add_on": -1.5}, 400, "--add-on must be above 0, got -1.5"),
        ({"add_on": True}, 400, "add_on must be a number"),
        ({"add_on": "abc"}, 400, "add_on must be a number, got 'abc'"),
        ({"add_on": "inf"}, 400, "add_on must be a finite number"),
        ({"add_on": 10, "max_adds": 0}, 400, "--max-adds must be a whole number of at least 1, got 0"),
        ({"add_on": 10, "max_adds": 2.5}, 400, "max_adds must be a whole number, got 2.5"),
        ({"add_on": 10, "max_adds": "abc"}, 400, "max_adds must be a whole number, got 'abc'"),
        ({"max_adds": 2}, 400, "--max-adds only makes sense together with --add-on"),
    ],
)
def test_reading_and_rules(client, extra, status, outcome):
    got_status, reply = client.post({**PS, **extra})
    assert got_status == status
    if status == 200:
        assert (reply["params"]["add_on"], reply["params"]["max_adds"]) == outcome
        assert reply["summary"]["max_adds"] == outcome[1]
    else:
        assert reply == {"ok": False, "error": outcome}


def test_nan_written_raw_and_a_candle_file_with_max_adds(client):
    # JSON NaN (not a string) is a 400 too, as for scale_out.
    body = json.dumps(PS)[:-1] + ', "add_on": NaN}'
    assert client.raw(body) == (400, json.dumps({"ok": False, "error": "add_on must be a finite number"}))
    # With candle data and other options it still works; max_adds 2 shows in params, summary and report.
    status, reply = client.post({**C, "add_on": 5, "max_adds": 2, "scale_out": 5, "position_size": 0.5})
    assert status == 200
    keys = list(reply["summary"])
    i = keys.index("scale_out_exits")
    assert keys[i + 1: i + 5] == ["add_on_pct", "max_adds", "add_on_buys", "add_on_skipped_buys"]
    assert list(reply["params"])[-3:] == ["scale_out", "add_on", "max_adds"] and reply["params"]["max_adds"] == 2
    assert any(line.startswith("  Add-ons:     up to 2 per position") for line in reply["report"])
