"""Web API: ``trailing_stop`` in ``POST /api/backtest`` (the command line's ``--trailing-stop``).

Same rules as ``stop_loss`` and ``take_profit``: a number above 0 and below 100
(else a 400 with the command line's message), it needs candle data (a built-in
sample uses its sample candles, a pasted CSV is read as a candle file), it is
echoed in the reply's ``params`` only when given, right after ``take_profit``,
and a request without it gets exactly the old reply. The numbers come from the
same ``cli.analyse`` as the command line, so they equal ``--json``.

8-bar candle CSV (see test_cli_trailing_stop.py), cash 500, short 1, long 2, trail 10 %:
BUY 45 @ 11 on bar 4 (cash 5); bar 6 level 13 * 0.9 = 11.7, opens at 12.0 above it,
low 10.0 reaches it -> SELL 45 @ 11.70 = 526.50, cash 531.50, reason trail.
"""

import hashlib
import http.client
import json
import threading

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.samples import write_sample_csv
from trading_assistant.web import server as web

CANDLES = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.5,9.5,8.5,9,1000
2026-01-03,8.5,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,11.5,13,11.2,12,1000
2026-01-07,12.0,12.5,10.0,10,1000
2026-01-08,9,9,7.5,8,1000
"""
CLOSES_ONLY = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
BASE = {"csv": CANDLES, "short": 1, "long": 2, "cash": 500}
CLI_BASE = ["--backtest", "--short", "1", "--long", "2", "--cash", "500"]
OLD_PARAM_KEYS = ["short", "long", "rsi_period", "cash", "fee", "fee_pct"]


class Client:
    """Posts to the real server and returns the status, the raw body and the parsed JSON."""

    def __init__(self, server):
        self.host, self.port = server.server_address[:2]

    def raw(self, payload):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        conn.request(
            "POST",
            "/api/backtest",
            body=json.dumps(payload).encode(),
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
    assert status == 200, data
    return data


def cli_json(capsys, argv):
    code = cli_main(argv + ["--json"])
    out = capsys.readouterr().out
    assert code == 0
    return json.loads(out)["backtest"]


def assert_same_numbers(reply, bt):
    """Every number of the API reply equals the command's ``--json`` number (unrounded)."""
    assert [
        (t["bar"], t["side"], t["shares"], t["price"]["value"], t["value"]["value"], t["cost"]["value"],
         t["cash_after"]["value"], t["reason"])
        for t in reply["trades"]
    ] == [
        (f["bar"], f["side"], f["shares"], f["price"], f["value"], f["cost"], f["cash_after"], f["reason"])
        for f in bt["fills"]
    ]
    s, b = reply["summary"], reply["summary"]["buy_hold"]
    assert (
        s["start_cash"]["value"], s["end_equity"]["value"], s["return_pct"]["value"], s["max_drawdown_pct"]["value"],
        s["end_cash"]["value"], s["end_shares"], s["last_price"]["value"], s["trades"], s["buys"], s["sells"],
        s["round_trips"], s["winning_round_trips"], s["costs_paid"]["value"],
    ) == (
        bt["start_cash"], bt["final_equity"], bt["return_pct"], bt["max_drawdown_pct"],
        bt["final_cash"], bt["final_position"], bt["final_price"], bt["trades"], bt["buys"], bt["sells"],
        bt["round_trips"], bt["winning_round_trips"], bt["total_costs"],
    )
    bench = bt["benchmark"]
    assert (
        b["end_equity"]["value"], b["return_pct"]["value"], b["max_drawdown_pct"]["value"], b["shares"], b["trades"],
        b["costs_paid"]["value"],
    ) == (
        bench["final_equity"], bench["return_pct"], bench["max_drawdown_pct"], bench["shares"], bench["trades"],
        bench["total_costs"],
    )
    assert reply["params"]["trailing_stop"] == bt["trailing_stop_pct"]


# --------------------------------------------------------------------------- the 8-bar case


def test_8_bar_csv_reply(client):
    data = ok(client, {**BASE, "trailing_stop": 10})
    assert [(t["bar"], t["side"], t["shares"], t["price"]["text"], t["cash_after"]["text"], t["reason"])
            for t in data["trades"]] == [(4, "BUY", 45, "11.00", "5.00", "signal"), (6, "SELL", 45, "11.70", "531.50", "trail")]
    assert data["summary"]["end_equity"]["text"] == "531.50"
    assert data["summary"]["return_pct"]["text"] == "+6.30%"
    assert "  Exits:       trail 10.00% below the highest high since entry" in data["report"]


def test_8_bar_api_numbers_equal_the_commands_json(client, tmp_path, capsys):
    path = tmp_path / "c8.csv"
    path.write_text(CANDLES)
    reply = ok(client, {**BASE, "trailing_stop": 10})
    bt = cli_json(capsys, [str(path), *CLI_BASE, "--trailing-stop", "10"])
    assert_same_numbers(reply, bt)
    assert bt["final_equity"] == 531.5


@pytest.mark.parametrize(
    "source, settings",
    [
        ("csv", {"trailing_stop": 10, "stop_loss": 5, "take_profit": 20}),
        ("csv", {"trailing_stop": 10, "fill": "open", "slippage": 1, "fee": 1, "fee_pct": 0.5}),
        ("sample", {"trailing_stop": 3}),
        ("sample", {"trailing_stop": 2, "stop_loss": 4, "take_profit": 6, "fill": "open", "slippage": 0.5,
                    "position_size": 0.5, "fee": 1, "fee_pct": 0.1}),
    ],
    ids=["csv-trail-stop-target", "csv-trail-open-costs", "sample-trail", "sample-everything"],
)
def test_api_numbers_equal_the_commands_json(client, tmp_path, capsys, source, settings):
    path = tmp_path / "data.csv"
    if source == "csv":
        path.write_text(CANDLES)
        payload, argv = {**BASE, **settings}, [str(path), *CLI_BASE]
    else:
        with open(path, "w", newline="") as f:
            write_sample_csv("random_walk", f, candles=True)
        payload, argv = {"sample": "random_walk", "short": 5, "long": 20, **settings}, [
            str(path), "--backtest", "--short", "5", "--long", "20"]
    for key, value in settings.items():
        argv += ["--" + key.replace("_", "-"), str(value)]
    reply = ok(client, payload)
    bt = cli_json(capsys, argv)
    assert_same_numbers(reply, bt)
    assert "trail" in [f["reason"] for f in bt["fills"]]  # the trailing stop really fired
    code = cli_main(argv)
    assert code == 0 and reply["report"] == capsys.readouterr().out.splitlines()[:-1]  # the text report too


# --------------------------------------------------------------------------- params, columns and export


def test_trailing_stop_echoed_in_params_after_take_profit(client):
    data = ok(client, {**BASE, "trailing_stop": 10})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["trailing_stop"]
    assert data["params"]["trailing_stop"] == 10.0
    data = ok(client, {**BASE, "trailing_stop": "7.5", "take_profit": 20, "stop_loss": 5, "slippage": 0.1})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["slippage", "stop_loss", "take_profit", "trailing_stop"]
    assert data["params"]["trailing_stop"] == 7.5


def test_reason_column_rows_and_csv(client):
    data = ok(client, {**BASE, "trailing_stop": 10})
    assert data["columns"][-1] == "reason"
    assert [row[-1] for row in data["rows"]] == ["", "", "", "", "signal", "", "trail", ""]
    assert data["csv"].splitlines()[7] == (
        "6,2026-01-07,10.00,SELL,SELL,45,11.70,526.50,0.00,531.50,0,531.50,-2.48,500.00,trail"
    )


# --------------------------------------------------------------------------- bad values: 400


@pytest.mark.parametrize("bad", [0, 100, -5, 150, "0"])
def test_out_of_range_is_a_400_with_the_command_lines_message(client, tmp_path, capsys, bad):
    status, data = client.post({**BASE, "trailing_stop": bad})
    message = f"--trailing-stop must be between 0 and 100 (both exclusive), got {float(bad):g}"
    assert (status, data) == (400, {"ok": False, "error": message})
    assert client.post({"sample": "uptrend", "trailing_stop": bad}) == (status, data)  # same for a sample
    path = tmp_path / "c8.csv"
    path.write_text(CANDLES)
    with pytest.raises(SystemExit) as exc:
        cli_main([str(path), *CLI_BASE, "--trailing-stop", str(bad)])
    assert exc.value.code == 2 and capsys.readouterr().err.splitlines()[-1].endswith("error: " + message)


@pytest.mark.parametrize(
    "value, message",
    [
        ("abc", "trailing_stop must be a number, got 'abc'"),
        (True, "trailing_stop must be a number"),
        ([10], "trailing_stop must be a number"),
        ("NaN", "trailing_stop must be a finite number"),
        ("Infinity", "trailing_stop must be a finite number"),
    ],
)
def test_wrong_kind_of_value_is_a_400(client, value, message):
    assert client.post({**BASE, "trailing_stop": value}) == (400, {"ok": False, "error": message})


def test_close_only_csv_is_a_400_with_the_command_lines_message(client, tmp_path, capsys):
    status, data = client.post({"csv": CLOSES_ONLY, "short": 1, "long": 2, "trailing_stop": 10})
    assert status == 400 and "\n" not in data["error"]
    path = tmp_path / "closes.csv"
    path.write_text(CLOSES_ONLY)
    assert cli_main([str(path), *CLI_BASE, "--trailing-stop", "10"]) == 1
    assert capsys.readouterr().err.strip() == "Error: " + data["error"].replace("CSV", str(path), 1)


# --------------------------------------------------------------------------- without trailing_stop: unchanged

# sha256 of the raw reply bodies, captured before trailing_stop existed.
OLD_REPLIES = [
    ({}, 400, "af7cf5c67906fe33b5f5235804626d93e3cd2a08fef6aa5f04ed108338abc15d"),
    ({"sample": "uptrend"}, 200, "2ee07d92f8be70e1187c08ed45e6f32bdc27d6c60f3e116f3b3534ac17d0e585"),
    (BASE, 200, "842b2d52135a0689a46ae617f5bca7883d63ffa1005e1fc5ad9686c1b32d1333"),
    ({**BASE, "stop_loss": 10, "take_profit": 15}, 200, "9b6133b6bcbea1233048e6f63550333210aafcf7a3e18d65545b79c9ec5cabd4"),
    ({**BASE, "stop_loss": 0}, 400, "d51936fd7749c4ec277f269ce4ef29951039e1a2153f099a36637addad89da83"),
]


def test_old_requests_get_byte_for_byte_the_old_reply(client):
    for payload, old_status, old_digest in OLD_REPLIES:
        status, body = client.raw(payload)
        assert (status, hashlib.sha256(body.encode()).hexdigest()) == (old_status, old_digest), payload
        assert "trailing_stop" not in body and "trail" not in json.loads(body).get("params", {})


@pytest.mark.parametrize("empty", [None, ""])
def test_null_or_empty_trailing_stop_means_not_given(client, empty):
    assert client.raw({**BASE, "trailing_stop": empty}) == client.raw(BASE)
