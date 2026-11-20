"""Web API: atr_stop in POST /api/backtest (the command's --atr-stop), with atr_mult and atr_period.

atr_stop is JSON true or false; false, null, "" or no key leave the ATR stop
off, and anything else is a 400. With it on, atr_mult and atr_period count
without risk_pct; they are checked by the command line's own
``cli.check_risk`` (a 400 with the command's one-line message), the ATR stop
needs candle data, and the numbers come from the same ``cli.analyse`` as the
command, so they equal ``--json``. It is echoed in ``params`` only when sent,
right after atr_period, and ``summary.risk_skipped_buys`` (right after
``sells``) is there with risk_pct or atr_stop.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2, atr_stop, atr_mult 2, atr_period 3: BUY signal on bar 3, ATR(3) = 25/18,
BUY 90 @ 11 on bar 4; level 11 - 2 * 25/18 = 8.2222; bar 7 (open 8.6, low 7.5)
-> SELL 90 @ 8.22, reason atr, end equity 750. With risk_pct 2 as well: 7 shares,
end equity 980.56. With atr_period 5 the buy is skipped (no ATR yet on bar 3).
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
ATR = {"atr_stop": True, "atr_mult": 2, "atr_period": 3}
CLI_BASE = ["--backtest", "--short", "1", "--long", "2", "--cash", "1000"]
OLD_PARAM_KEYS = ["short", "long", "rsi_period", "cash", "fee", "fee_pct"]


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


def flags_for(settings):
    """The command-line flags for request settings (atr_stop true is the bare switch)."""
    argv = []
    for key, value in settings.items():
        if key == "atr_stop":
            argv += ["--atr-stop"] if value else []
        else:
            argv += ["--" + key.replace("_", "-"), str(value)]
    return argv


def assert_same_numbers(reply, bt):
    """Every number of the reply equals the command's --json number (unrounded)."""
    assert [
        (t["bar"], t["side"], t["shares"], t["price"]["value"], t["value"]["value"], t["cost"]["value"],
         t["cash_after"]["value"], t["reason"])
        for t in reply["trades"]
    ] == [
        (f["bar"], f["side"], f["shares"], f["price"], f["value"], f["cost"], f["cash_after"], f["reason"])
        for f in bt["fills"]
    ]
    s, b, bench = reply["summary"], reply["summary"]["buy_hold"], bt["benchmark"]
    assert (
        s["start_cash"]["value"], s["end_equity"]["value"], s["return_pct"]["value"], s["max_drawdown_pct"]["value"],
        s["end_cash"]["value"], s["end_shares"], s["trades"], s["buys"], s["sells"], s["risk_skipped_buys"],
        s["round_trips"], s["costs_paid"]["value"], b["end_equity"]["value"], b["shares"],
    ) == (
        bt["start_cash"], bt["final_equity"], bt["return_pct"], bt["max_drawdown_pct"],
        bt["final_cash"], bt["final_position"], bt["trades"], bt["buys"], bt["sells"], bt["risk_skipped_buys"],
        bt["round_trips"], bt["total_costs"], bench["final_equity"], bench["shares"],
    )


# --------------------------------------------------------------------------- the hand case


def test_hand_case_reply(client):
    data = ok(client, {**BASE, **ATR})
    assert [
        (t["bar"], t["side"], t["shares"], t["price"]["text"], t["cash_after"]["text"], t["reason"])
        for t in data["trades"]
    ] == [
        (4, "BUY", 90, "11.00", "10.00", "signal"),
        (7, "SELL", 90, "8.22", "750.00", "atr"),
    ]
    assert data["trades"][1]["price"]["value"] == pytest.approx(74 / 9)
    assert data["summary"]["end_equity"]["text"] == "750.00"
    assert data["summary"]["risk_skipped_buys"] == 0
    assert "  Exits:       atr 2 x ATR(3) below entry" in data["report"]
    assert data["columns"][-1] == "reason" and data["rows"][7][-1] == "atr"
    assert data["csv"].splitlines()[-1].endswith(",atr")


def test_hand_case_with_risk_pct(client):
    data = ok(client, {**BASE, **ATR, "risk_pct": 2})
    assert [(t["side"], t["shares"], t["price"]["text"], t["reason"]) for t in data["trades"]] == [
        ("BUY", 7, "11.00", "signal"),
        ("SELL", 7, "8.22", "atr"),
    ]
    assert data["summary"]["end_equity"]["text"] == "980.56"
    assert (
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
        "(the ATR stop sells at this distance, as of the buy that opened the position, below the average entry price; a gap, slippage, fees or a later buy can lose more)"
    ) in data["report"]


def test_atr_mult_and_atr_period_count_without_risk_pct(client):
    # atr_mult 1: level 9.6111; bar 7 opens at 8.6 below it -> sold at the open.
    data = ok(client, {**BASE, "atr_stop": True, "atr_mult": 1, "atr_period": 3})
    assert [(t["price"]["text"], t["reason"]) for t in data["trades"]][1] == ("8.60", "atr")
    assert data["summary"]["end_equity"]["text"] == "784.00"


@pytest.mark.parametrize(
    "source, settings",
    [
        ("csv", {"atr_stop": True, "atr_mult": 2, "atr_period": 3}),
        ("csv", {"atr_stop": True, "atr_mult": 1, "atr_period": 3}),  # gap at the open
        ("csv", {"atr_stop": True, "atr_period": 5}),  # skipped
        ("csv", {"atr_stop": True}),  # defaults 2 and 14: skipped
        ("csv", {"risk_pct": 2, "atr_mult": 2, "atr_period": 3, "atr_stop": True}),
        ("csv", {"atr_stop": True, "atr_period": 3, "stop_loss": 20, "trailing_stop": 30, "take_profit": 25}),
        ("csv", {"atr_stop": True, "atr_period": 3, "fill": "open", "position_size": 0.5, "slippage": 0.5}),
        ("sample", {"atr_stop": True, "atr_mult": 3}),
        ("sample", {"atr_stop": True, "risk_pct": 0.5, "atr_period": 10, "stop_loss": 4, "fee": 1, "slippage": 0.2}),
    ],
    ids=["hand", "hand-gap", "hand-period-5", "hand-defaults", "hand-risk", "hand-other-exits", "hand-open-fills",
         "sample", "sample-with-others"],
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
    argv += flags_for(settings)
    reply = ok(client, payload)
    code, out, _ = cli_run(capsys, argv + ["--json"])
    assert code == 0
    bt = json.loads(out)["backtest"]
    assert_same_numbers(reply, bt)
    assert bt["atr_stop"] is True
    code, out, _ = cli_run(capsys, argv)
    assert code == 0 and reply["report"] == out.splitlines()[:-1]  # the text report, Exits line included


# --------------------------------------------------------------------------- 400s with the command's message


@pytest.mark.parametrize(
    "settings, flags",
    [
        ({"atr_stop": True, "atr_mult": 0}, ["--atr-stop", "--atr-mult", "0"]),
        ({"atr_stop": True, "atr_mult": -2}, ["--atr-stop", "--atr-mult", "-2"]),
        ({"atr_stop": True, "atr_period": 0}, ["--atr-stop", "--atr-period", "0"]),
        ({"atr_stop": False, "atr_mult": 3}, ["--atr-mult", "3"]),
        ({"atr_stop": False, "atr_period": 5}, ["--atr-period", "5"]),
        ({"atr_stop": None, "atr_mult": 3}, ["--atr-mult", "3"]),
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
    "value, message",
    [
        ("yes", "atr_stop must be true or false, got 'yes'"),
        ("true", "atr_stop must be true or false, got 'true'"),
        (" no ", "atr_stop must be true or false, got 'no'"),
        (1, "atr_stop must be true or false, got 1"),
        (0, "atr_stop must be true or false, got 0"),
        (1.5, "atr_stop must be true or false, got 1.5"),
        ([], "atr_stop must be true or false"),
        ({}, "atr_stop must be true or false"),
    ],
)
def test_wrong_kind_of_value_is_a_400(client, value, message):
    assert client.post({**BASE, "atr_stop": value}) == (400, {"ok": False, "error": message})


def test_close_only_csv_is_a_400_with_the_commands_message(client, tmp_path, capsys):
    status, data = client.post({"csv": CLOSES, "short": 1, "long": 2, "atr_stop": True})
    assert status == 400 and "\n" not in data["error"]
    path = tmp_path / "closes.csv"
    path.write_text(CLOSES)
    code, _, err = cli_run(capsys, [str(path), *CLI_BASE, "--atr-stop"])
    assert code == 1 and err.strip() == "Error: " + data["error"].replace("CSV", str(path), 1)


def test_atr_stop_false_needs_no_candles(client):
    data = ok(client, {"csv": CLOSES, "short": 1, "long": 2, "atr_stop": False})
    assert data["params"]["atr_stop"] is False and "reason" not in data["trades"][0]


def test_sample_uses_its_candles(client):
    data = ok(client, {"sample": "random_walk", "short": 5, "long": 20, "atr_stop": True, "atr_period": 5})
    assert "atr" in {t["reason"] for t in data["trades"]}


def test_the_server_uses_the_commands_shared_check(monkeypatch, client):
    assert web.check_risk is cli.check_risk
    calls = []
    monkeypatch.setattr(web, "check_risk", lambda *args: calls.append(args))
    web._parse_later_settings({"atr_stop": True, "atr_mult": 1.5, "atr_period": 3})
    web._parse_later_settings({"atr_stop": False, "risk_pct": 2, "atr_mult": 1.5})
    assert calls == [(None, 1.5, 3, True), (2.0, 1.5, None)]  # without atr_stop: the call it always made


# --------------------------------------------------------------------------- without atr_stop: unchanged

# sha256 of the raw reply bodies, captured before the server took atr_stop.
OLD_REPLIES = [
    (dict(BASE), 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),  # BASE
    ({**BASE, "risk_pct": 2, "atr_mult": 2, "atr_period": 3}, 200, "64d206df090beb36c4901cf1fc111715f9643d7adb631a9d1588fc23addd3070"),  # BASE+risk
    ({**BASE, "risk_pct": 2, "atr_mult": 2, "atr_period": 5}, 200, "88b08d9063b10505df1a6a111ae3d054e2145659b23b022ddd81263adee5c171"),  # BASE+risk period 5
    ({**BASE, "stop_loss": 5, "take_profit": 20, "trailing_stop": 8, "fill": "open"}, 200, "855d7b0528c3c182ce18a3369fc888e2ec982da5a6a4027cf0da7358ea814d5d"),  # BASE+exits
    ({**BASE, "risk_pct": 2, "atr_period": 3, "trailing_stop": 8, "position_size": 0.5}, 200, "94a801e7a19c5da305f1dcc9e6f6b637ebe5c19f5fcf2bb0b2705e731d284300"),  # BASE+risk+exits
    ({**BASE, "atr_mult": 3}, 400, "47a6fa32a907cd6c000424329454786e878a65ad53beb8388c9688e38f2b86e9"),  # BASE+atr_mult without risk
    ({**BASE, "atr_period": 5}, 400, "7662b9ecd436211e5f3ab3f9f1097ee03807e75865fa965fb50b931dc8472558"),  # BASE+atr_period without risk
    ({**BASE, "risk_pct": 2, "atr_mult": 0}, 400, "83cc6fbd3bffe5a26ef0111809c97178c386df39aa402c60f61cf1ce3d7689cf"),  # BASE+atr_mult 0 with risk
    ({"csv": CLOSES, "short": 1, "long": 2, "risk_pct": 2}, 400, "31bf266ec428ab459c6a2cf9f5391edb84cc284764c590016dcbc55c648edb36"),  # closes+risk
    ({"csv": CLOSES, "short": 1, "long": 2}, 200, "e357af655edd3a5630d9cd81ed1e60ae7733539a76c1892db5f13fa9a2bb11d4"),  # closes
    ({"sample": "uptrend"}, 200, "2ee07d92f8be70e1187c08ed45e6f32bdc27d6c60f3e116f3b3534ac17d0e585"),  # sample uptrend
    ({"sample": "random_walk", "short": 5, "long": 20, "risk_pct": 1, "atr_mult": 3}, 200, "0967ddf198f2b924f6fbf4f13c9c28b168ebe69b6c57aab9aa1fba6bfcde8c91"),  # sample random_walk+risk
    ({**BASE, "atr_stop": None}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),  # BASE+atr_stop null
    ({**BASE, "atr_stop": ""}, 200, "791ca1323799f879a31ac1ddfaab6be911c13ac899584f3d3e3526bd393ff0c5"),  # BASE+atr_stop empty
]


def test_old_requests_get_byte_for_byte_the_old_reply(client):
    for payload, old_status, old_digest in OLD_REPLIES:
        status, body = client.raw(payload)
        assert (status, hashlib.sha256(body.encode()).hexdigest()) == (old_status, old_digest), payload


def test_atr_stop_false_is_the_old_reply_plus_the_echo(client):
    for extra in ({}, {"risk_pct": 2, "atr_period": 3}, {"stop_loss": 5, "fill": "open"}):
        old, new = ok(client, {**BASE, **extra}), ok(client, {**BASE, **extra, "atr_stop": False})
        assert list(new["params"])[-1] == "atr_stop" and new["params"].pop("atr_stop") is False
        assert new == old


# --------------------------------------------------------------------------- params echo and summary


def test_atr_stop_echoed_in_params_only_when_sent(client):
    assert list(ok(client, BASE)["params"]) == OLD_PARAM_KEYS
    for value in (None, ""):
        assert "atr_stop" not in ok(client, {**BASE, "atr_stop": value})["params"]
    data = ok(client, {**BASE, "atr_stop": True})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["atr_stop"]  # the defaults 2 and 14 are not echoed
    assert data["params"]["atr_stop"] is True
    data = ok(client, {**BASE, "atr_stop": True, "atr_period": "3", "trailing_stop": 8, "atr_mult": 2, "risk_pct": "2"})
    assert list(data["params"]) == OLD_PARAM_KEYS + ["trailing_stop", "risk_pct", "atr_mult", "atr_period", "atr_stop"]
    assert list(ok(client, {**BASE, "atr_stop": False})["params"]) == OLD_PARAM_KEYS + ["atr_stop"]


def test_risk_skipped_buys_in_summary_right_after_sells(client):
    for settings, skipped in (
        ({"atr_stop": True, "atr_period": 3}, 0),
        ({"atr_stop": True, "atr_period": 5}, 1),
        ({"atr_stop": True, "risk_pct": 2, "atr_period": 5}, 1),  # counted once
    ):
        summary = ok(client, {**BASE, **settings})["summary"]
        keys = list(summary)
        assert keys[keys.index("sells") + 1] == "risk_skipped_buys"
        assert summary["risk_skipped_buys"] == skipped
    assert "risk_skipped_buys" not in ok(client, BASE)["summary"]
    assert "risk_skipped_buys" not in ok(client, {**BASE, "atr_stop": False})["summary"]
