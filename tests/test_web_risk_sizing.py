"""Web API: risk_pct, atr_mult and atr_period in POST /api/backtest (the command's --risk-pct, --atr-mult, --atr-period).

They are checked by the command line's own ``cli.check_risk`` (a 400 with the
command's one-line message), risk_pct needs candle data, and the numbers come
from the same ``cli.analyse`` as the command, so they equal ``--json``.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2, risk 2, atr_mult 2, atr_period 3: BUY signal on bar 3, ATR(3) = 25/18,
20 / (2 * 25/18) = 7.2 -> 7 shares @ 11 on bar 4, sold @ 8 on bar 7, end
equity 979. With atr_period 5 the buy is skipped (no ATR yet on bar 3).
"""

import hashlib
import http.client
import json
import threading

import pytest

from trading_assistant import cli
from trading_assistant.cli import main as cli_main
from trading_assistant.samples import write_sample_csv
from trading_assistant.web import server as web

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-03,8.3,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,12.2,13,11.2,12,1000
2026-01-07,11.5,12.5,9.8,10,1000
2026-01-08,8.6,9,7.5,8,1000
"""
CLOSES = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
BASE = {"csv": HAND, "short": 1, "long": 2, "cash": 1000}
RISK = {"risk_pct": 2, "atr_mult": 2, "atr_period": 3}
CLI_BASE = ["--backtest", "--short", "1", "--long", "2", "--cash", "1000"]


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
    assert status == 200, data
    return data


def cli_run(capsys, argv):
    try:
        code = cli_main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def assert_same_numbers(reply, bt):
    """Every number of the reply equals the command's --json number (unrounded)."""
    assert [
        (t["bar"], t["side"], t["shares"], t["price"]["value"], t["value"]["value"], t["cost"]["value"],
         t["cash_after"]["value"])
        for t in reply["trades"]
    ] == [(f["bar"], f["side"], f["shares"], f["price"], f["value"], f["cost"], f["cash_after"]) for f in bt["fills"]]
    s, b, bench = reply["summary"], reply["summary"]["buy_hold"], bt["benchmark"]
    assert (
        s["start_cash"]["value"], s["end_equity"]["value"], s["return_pct"]["value"], s["max_drawdown_pct"]["value"],
        s["end_cash"]["value"], s["end_shares"], s["trades"], s["buys"], s["sells"], s["round_trips"],
        s["costs_paid"]["value"], b["end_equity"]["value"], b["shares"],
    ) == (
        bt["start_cash"], bt["final_equity"], bt["return_pct"], bt["max_drawdown_pct"],
        bt["final_cash"], bt["final_position"], bt["trades"], bt["buys"], bt["sells"], bt["round_trips"],
        bt["total_costs"], bench["final_equity"], bench["shares"],
    )


# --------------------------------------------------------------------------- the hand case


def test_hand_case_reply(client):
    data = ok(client, {**BASE, **RISK})
    assert [(t["bar"], t["side"], t["shares"], t["price"]["text"], t["cash_after"]["text"]) for t in data["trades"]] == [
        (4, "BUY", 7, "11.00", "923.00"),
        (7, "SELL", 7, "8.00", "979.00"),
    ]
    assert data["summary"]["end_equity"]["text"] == "979.00"
    assert (
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
        "(this only sets the number of shares; no stop is placed)" in data["report"]
    )


@pytest.mark.parametrize(
    "source, settings",
    [
        ("csv", {"risk_pct": 2, "atr_mult": 2, "atr_period": 3}),
        ("csv", {"risk_pct": 2, "atr_mult": 2, "atr_period": 5}),  # skipped
        ("csv", {"risk_pct": 2, "atr_period": 3, "position_size": 0.05, "trailing_stop": 8, "fill": "open"}),
        ("sample", {"risk_pct": 1, "atr_mult": 3}),
        ("sample", {"risk_pct": 0.5, "atr_period": 10, "stop_loss": 4, "fee": 1, "slippage": 0.2}),
    ],
    ids=["hand", "hand-period-5", "hand-with-others", "sample", "sample-with-others"],
)
def test_reply_numbers_and_report_equal_the_commands(client, tmp_path, capsys, source, settings):
    path = tmp_path / "data.csv"
    if source == "csv":
        path.write_text(HAND)
        payload, argv = {**BASE, **settings}, [str(path), *CLI_BASE]
    else:
        with open(path, "w", newline="") as f:
            write_sample_csv("random_walk", f, candles=True)
        payload, argv = {"sample": "random_walk", "short": 5, "long": 20, **settings}, [
            str(path), "--backtest", "--short", "5", "--long", "20"]
    for key, value in settings.items():
        argv += ["--" + key.replace("_", "-"), str(value)]
    reply = ok(client, payload)
    code, out, _ = cli_run(capsys, argv + ["--json"])
    assert code == 0
    bt = json.loads(out)["backtest"]
    assert_same_numbers(reply, bt)
    assert bt["risk_pct"] == settings["risk_pct"]
    code, out, _ = cli_run(capsys, argv)
    assert code == 0 and reply["report"] == out.splitlines()[:-1]  # the text report, Risk sizing line included


# --------------------------------------------------------------------------- 400s with the command's message


@pytest.mark.parametrize(
    "settings, flags",
    [
        ({"risk_pct": 0}, ["--risk-pct", "0"]),
        ({"risk_pct": -1}, ["--risk-pct", "-1"]),
        ({"risk_pct": 100.5}, ["--risk-pct", "100.5"]),
        ({"risk_pct": 2, "atr_mult": 0}, ["--risk-pct", "2", "--atr-mult", "0"]),
        ({"risk_pct": 2, "atr_period": 0}, ["--risk-pct", "2", "--atr-period", "0"]),
        ({"atr_mult": 3}, ["--atr-mult", "3"]),
        ({"atr_period": 5}, ["--atr-period", "5"]),
        ({"atr_mult": 0, "atr_period": 0}, ["--atr-mult", "0", "--atr-period", "0"]),
    ],
)
def test_bad_settings_are_a_400_with_the_commands_message(client, tmp_path, capsys, settings, flags):
    path = tmp_path / "hand.csv"
    path.write_text(HAND)
    code, out, err = cli_run(capsys, [str(path), *CLI_BASE, *flags])
    assert (code, out) == (2, "")
    message = err.splitlines()[-1].split("error: ", 1)[1]
    assert client.post({**BASE, **settings}) == (400, {"ok": False, "error": message})
    assert client.post({"sample": "uptrend", **settings}) == (400, {"ok": False, "error": message})


@pytest.mark.parametrize(
    "settings, message",
    [
        ({"risk_pct": "abc"}, "risk_pct must be a number, got 'abc'"),
        ({"risk_pct": True}, "risk_pct must be a number"),
        ({"risk_pct": "NaN"}, "risk_pct must be a finite number"),
        ({"risk_pct": 2, "atr_mult": "Infinity"}, "atr_mult must be a finite number"),
        ({"risk_pct": 2, "atr_period": 1.5}, "atr_period must be a whole number, got 1.5"),
        ({"risk_pct": 2, "atr_period": "x"}, "atr_period must be a whole number, got 'x'"),
    ],
)
def test_wrong_kind_of_value_is_a_400(client, settings, message):
    assert client.post({**BASE, **settings}) == (400, {"ok": False, "error": message})


def test_close_only_csv_is_a_400_with_the_commands_message(client, tmp_path, capsys):
    status, data = client.post({"csv": CLOSES, "short": 1, "long": 2, "risk_pct": 2})
    assert status == 400 and "\n" not in data["error"]
    path = tmp_path / "closes.csv"
    path.write_text(CLOSES)
    code, _, err = cli_run(capsys, [str(path), *CLI_BASE, "--risk-pct", "2"])
    assert code == 1 and err.strip() == "Error: " + data["error"].replace("CSV", str(path), 1)


def test_the_server_uses_the_commands_shared_check(monkeypatch, client):
    assert web.check_risk is cli.check_risk
    calls = []
    monkeypatch.setattr(web, "check_risk", lambda *args: calls.append(args))
    web._parse_later_settings({"risk_pct": 2, "atr_mult": 1.5, "atr_period": 3})
    assert calls == [(2.0, 1.5, 3)]


# --------------------------------------------------------------------------- without the new settings: unchanged

# sha256 of the raw reply bodies, captured before the server took the risk settings.
OLD_REPLIES = [
    ({}, 400, "af7cf5c67906fe33b5f5235804626d93e3cd2a08fef6aa5f04ed108338abc15d"),
    ({"sample": "uptrend"}, 200, "2ee07d92f8be70e1187c08ed45e6f32bdc27d6c60f3e116f3b3534ac17d0e585"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),
    ({"csv": CLOSES, "short": 1, "long": 2}, 200, "e357af655edd3a5630d9cd81ed1e60ae7733539a76c1892db5f13fa9a2bb11d4"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "stop_loss": 5, "take_profit": 20, "trailing_stop": 8}, 200, "2f504fc45b1d90577ab2b3f0a1070c3305c15167d5b20e5a562fc9425516f318"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "fill": "open", "slippage": 0.5, "position_size": 0.5, "fee": 1, "fee_pct": 0.1}, 200, "a5375020f37cf304766ba9afcd0894245c6abefe0bc693b799a832a5e7a06ef5"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "stop_loss": 0}, 400, "d51936fd7749c4ec277f269ce4ef29951039e1a2153f099a36637addad89da83"),
    ({"csv": CLOSES, "short": 1, "long": 2, "stop_loss": 5}, 400, "31bf266ec428ab459c6a2cf9f5391edb84cc284764c590016dcbc55c648edb36"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "risk_pct": None}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "risk_pct": ""}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),
    ({"csv": HAND, "short": 1, "long": 2, "cash": 1000, "atr_mult": None, "atr_period": ""}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),
]


def test_old_requests_get_byte_for_byte_the_old_reply(client):
    for payload, old_status, old_digest in OLD_REPLIES:
        status, body = client.raw(payload)
        assert (status, hashlib.sha256(body.encode()).hexdigest()) == (old_status, old_digest), payload


# --------------------------------------------------------------------------- params echo and summary

OLD_PARAM_KEYS = ["short", "long", "rsi_period", "cash", "fee", "fee_pct"]


def test_risk_settings_echoed_in_params_only_when_sent(client):
    data = ok(client, {**BASE, "risk_pct": 2})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["risk_pct"]  # defaults are not echoed
    data = ok(client, {**BASE, "atr_period": "3", "trailing_stop": 8, "atr_mult": 2, "risk_pct": "2"})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["trailing_stop", "risk_pct", "atr_mult", "atr_period"]
    assert (data["params"]["risk_pct"], data["params"]["atr_mult"], data["params"]["atr_period"]) == (2.0, 2.0, 3)


def test_risk_skipped_buys_in_summary_right_after_sells(client, tmp_path, capsys):
    for period, skipped in ((3, 0), (5, 1)):
        summary = ok(client, {**BASE, **RISK, "atr_period": period})["summary"]
        keys = list(summary)
        assert keys[keys.index("sells") + 1] == "risk_skipped_buys"
        assert summary["risk_skipped_buys"] == skipped
    assert "risk_skipped_buys" not in ok(client, BASE)["summary"]
