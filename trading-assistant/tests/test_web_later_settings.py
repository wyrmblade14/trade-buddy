"""Web API: slippage, position_size, fill, stop_loss and take_profit in ``POST /api/backtest``.

The web layer only checks and forwards these settings; the numbers come from
the same ``cli.analyse`` the command line uses. ``fill: "open"``,
``stop_loss`` or ``take_profit`` need candle data: a built-in sample then uses
``samples.sample_candles`` and a pasted CSV is read as a candle file. A request
that does not use them gets exactly the old reply.

Hand-worked candle CSV (the series of test_stop_take_profit.py), short=2, long=3, cash 10,000:

    bar  date         open  high   low  close
     4   2026-01-05    12    15    11     14     BUY signal
     5   2026-01-06    13    15  12.9     14
     6   2026-01-07    14    17    12     14
     7   2026-01-08     9    10   7.5      8     SELL signal; opens below a 10 % stop (gap)
     8   2026-01-09     7     9   6.9      8

    slippage 1 %, close fills (needs no candles):
        BUY bar 5 @ 14 * 1.01 = 14.14 -> floor(10,000 / 14.14) = 707, cash 3.02
        SELL bar 8 @ 8 * 0.99 = 7.92 -> 707 * 7.92 = 5,599.44, cash 5,602.46
    position_size 0.5, close fills (needs no candles):
        BUY bar 5 @ 14, budget 5,000 -> 357 shares (4,998), cash 5,002
        SELL bar 8 @ 8 -> 2,856, cash 7,858
    fill open:
        BUY bar 5 @ open 13 -> 769 shares (9,997), cash 3; SELL bar 8 @ open 7 -> 5,383, cash 5,386
    fill open + slippage 1 % + position_size 0.5 + stop_loss 10:
        BUY bar 5 @ 13 * 1.01 = 13.13, budget 5,000 -> 380 shares (4,989.40), cash 5,010.60
        entry 13.13, stop 11.817; bar 6 low 12 > 11.817; bar 7 opens at 9 (gap) ->
        SELL 380 @ 9 * 0.99 = 8.91 = 3,385.80, cash 8,396.40 (reason stop)
    ... + take_profit 20: target 15.756; bar 6 high 17 reaches it (opens at 14, no gap) ->
        SELL 380 @ 15.756 * 0.99 = 15.59844 = 5,927.4072, cash 10,938.0072 (reason target)
"""

import json
import threading

import pytest

from trading_assistant.backtest import EXPORT_COLUMNS
from trading_assistant.cli import analyse, main as cli_main
from trading_assistant.samples import sample_candles, sample_table, write_sample_csv
from trading_assistant.web import server as web

OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0]
HIGHS = [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0]
LOWS = [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5]
CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
DATES = [f"2026-01-{t + 1:02d}" for t in range(10)]
CANDLE_CSV = "date,open,high,low,close,volume\n" + "".join(
    f"{DATES[t]},{OPENS[t]},{HIGHS[t]},{LOWS[t]},{CLOSES[t]},{(t + 1) * 1000}\n" for t in range(10)
)
CLOSE_CSV = "date,close\n" + "".join(f"{DATES[t]},{CLOSES[t]}\n" for t in range(10))
SMA = {"short": 2, "long": 3}
OLD_PARAM_KEYS = {"short", "long", "rsi_period", "cash", "fee", "fee_pct"}
A = pytest.approx


class Client:
    def __init__(self, server):
        host, port = server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def post(self, payload):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        req = Request(
            self.base + "/api/backtest",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())


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


def fills(data):
    return [
        (t["date"], t["side"], t["shares"], t["price"]["text"], t["cash_after"]["value"], t.get("reason"))
        for t in data["trades"]
    ]


# --------------------------------------------------------------------------- hand-worked, pasted CSV


def test_slippage_on_a_close_only_csv(client):
    data = ok(client, {"csv": CLOSE_CSV, **SMA, "slippage": 1})
    assert fills(data) == [("2026-01-06", "BUY", 707, "14.14", A(3.02), None), ("2026-01-09", "SELL", 707, "7.92", A(5602.46), None)]
    assert data["params"]["slippage"] == 1.0


def test_position_size_on_a_close_only_csv(client):
    data = ok(client, {"csv": CLOSE_CSV, **SMA, "position_size": 0.5})
    assert fills(data) == [("2026-01-06", "BUY", 357, "14.00", A(5002.0), None), ("2026-01-09", "SELL", 357, "8.00", A(7858.0), None)]
    assert data["params"]["position_size"] == 0.5


def test_fill_open_on_a_pasted_candle_csv(client):
    data = ok(client, {"csv": CANDLE_CSV, **SMA, "fill": "open"})
    assert fills(data) == [("2026-01-06", "BUY", 769, "13.00", A(3.0), None), ("2026-01-09", "SELL", 769, "7.00", A(5386.0), None)]
    assert data["summary"]["end_equity"]["value"] == A(5386.0)
    assert data["params"]["fill"] == "open"


def test_everything_together_stop_at_the_gapped_open(client):
    data = ok(client, {"csv": CANDLE_CSV, **SMA, "fill": "open", "slippage": 1, "position_size": 0.5, "stop_loss": 10})
    assert fills(data) == [
        ("2026-01-06", "BUY", 380, "13.13", A(5010.60), "signal"),
        ("2026-01-08", "SELL", 380, "8.91", A(8396.40), "stop"),
    ]
    assert data["summary"]["end_equity"]["text"] == "8,396.40"
    assert data["summary"]["buy_hold"]["end_equity"]["text"] == "8,801.00"  # 1,100 shares @ 9.09, cash 1


def test_everything_together_with_a_target(client):
    data = ok(client, {"csv": CANDLE_CSV, **SMA, "fill": "open", "slippage": 1, "position_size": 0.5, "stop_loss": 10, "take_profit": 20})
    assert fills(data)[1] == ("2026-01-07", "SELL", 380, "15.60", A(10938.0072), "target")
    assert data["params"]["take_profit"] == 20.0


# --------------------------------------------------------------------------- same analysis as the command line


@pytest.mark.parametrize(
    "settings",
    [
        {"slippage": 0.5},
        {"position_size": 0.25},
        {"fill": "open"},
        {"fill": "close"},
        {"stop_loss": 3},
        {"take_profit": 6},
        {"fill": "open", "slippage": 0.5, "position_size": 0.5, "stop_loss": 3, "take_profit": 6, "fee": 1, "fee_pct": 0.1},
    ],
    ids=lambda s: ",".join(s),
)
def test_sample_reply_equals_the_command_line_on_the_sample_candle_file(client, tmp_path, capsys, settings):
    path = tmp_path / "rw.csv"
    with open(path, "w", newline="") as f:
        write_sample_csv("random_walk", f, candles=True)
    data = ok(client, {"sample": "random_walk", "short": 5, "long": 20, **settings})
    flags = []
    for key, value in settings.items():
        flags += ["--" + key.replace("_", "-"), str(value)]
    code = cli_main([str(path), "--backtest", "--short", "5", "--long", "20", *flags])
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert data["report"] == out[:-1]  # everything but the disclaimer line


def test_reply_report_is_cli_analyse_of_the_sample_candles(client):
    candles = sample_candles("uptrend")
    data = ok(client, {"sample": "uptrend", "short": 5, "long": 20, "stop_loss": 4, "fill": "open"})
    lines, result = analyse(
        [c.close for c in candles], short=5, long=20, backtest=True, fill="open",
        opens=[c.open for c in candles], stop_pct=4.0, highs=[c.high for c in candles], lows=[c.low for c in candles],
    )
    assert data["report"] == lines
    assert data["summary"]["end_equity"]["value"] == result.final_equity
    assert data["stats"] == json.loads(json.dumps(result.stats))


def test_sample_candles_have_the_same_closes_and_dates_as_the_plain_sample():
    plain = web.parse_request({"sample": "sideways"})
    candle = web.parse_request({"sample": "sideways", "stop_loss": 5})
    assert candle["closes"] == plain["closes"] and candle["dates"] == plain["dates"]
    assert candle["opens"] == [c.open for c in sample_candles("sideways")]
    assert candle["highs"] == [c.high for c in sample_candles("sideways")]
    assert plain["opens"] is plain["highs"] is plain["lows"] is None


def test_fill_open_alone_loads_opens_but_not_highs_and_lows():
    params = web.parse_request({"csv": CANDLE_CSV, **SMA, "fill": "open"})
    assert params["opens"] == OPENS and params["highs"] is None and params["lows"] is None


# --------------------------------------------------------------------------- echo of the settings


@pytest.mark.parametrize(
    "key, raw, echoed",
    [
        ("slippage", 0.5, 0.5),
        ("slippage", "0.25", 0.25),
        ("slippage", 0, 0.0),  # given, even though it equals the default
        ("position_size", 1, 1.0),
        ("fill", "close", "close"),
        ("fill", "open", "open"),
        ("stop_loss", "7", 7.0),
        ("take_profit", 12.5, 12.5),
    ],
)
def test_given_settings_are_echoed_in_params(client, key, raw, echoed):
    data = ok(client, {"sample": "uptrend", key: raw})
    assert data["params"][key] == echoed
    assert set(data["params"]) == OLD_PARAM_KEYS | {key}


def test_all_settings_echoed_in_a_fixed_order_after_the_old_ones(client):
    data = ok(client, {"sample": "uptrend", "take_profit": 9, "fill": "open", "stop_loss": 4, "position_size": 0.5, "slippage": 0.1})
    assert list(data["params"]) == [
        "short", "long", "rsi_period", "cash", "fee", "fee_pct", "slippage", "position_size", "fill", "stop_loss", "take_profit",
    ]


# --------------------------------------------------------------------------- requests without the new settings


@pytest.mark.parametrize(
    "payload",
    [
        {"sample": "uptrend"},
        {"sample": "random_walk", "short": 5, "long": 20, "fee": 1, "fee_pct": 0.1},
        {"csv": CLOSE_CSV, **SMA},
    ],
)
def test_old_requests_keep_the_old_reply_shape(client, payload):
    data = ok(client, payload)
    assert set(data["params"]) == OLD_PARAM_KEYS
    assert data["columns"] == EXPORT_COLUMNS
    assert all("reason" not in t for t in data["trades"])
    assert not any(line.startswith(("  Slippage", "  Sizing", "  Exits")) for line in data["report"])


def test_null_or_empty_settings_mean_not_given(client):
    plain = ok(client, {"sample": "uptrend"})
    blank = ok(client, {"sample": "uptrend", "slippage": None, "position_size": "", "fill": "", "stop_loss": None, "take_profit": ""})
    assert blank == plain


def test_old_request_with_a_candle_shaped_csv_still_reads_only_the_closes(client):
    # Not a valid candle file (high below low on the first row), but without the new
    # settings it is read as a close-only CSV exactly as before.
    text = "date,open,high,low,close,volume\n2026-01-01,9,5,8,10,1\n2026-01-02,9,11,8,10,1\n2026-01-03,9,11,8,12,1\n"
    data = ok(client, {"csv": text, "short": 1, "long": 2})
    assert data["source"]["bars"] == 3
    status, err = client.post({"csv": text, "short": 1, "long": 2, "stop_loss": 5})
    assert status == 400 and "line 2" in err["error"] and "\n" not in err["error"]


# --------------------------------------------------------------------------- exits: reasons and columns


def test_reason_on_trades_and_in_columns_only_with_exits(client):
    data = ok(client, {"sample": "random_walk", "short": 5, "long": 20, "stop_loss": 3})
    assert all(t["reason"] in ("signal", "stop", "target") for t in data["trades"])
    assert any(t["reason"] == "stop" for t in data["trades"])
    assert data["columns"] == EXPORT_COLUMNS + ["reason"]
    assert all(len(row) == len(data["columns"]) for row in data["rows"])
    assert data["csv"].splitlines()[0].endswith(",reason")
    no_exits = ok(client, {"sample": "random_walk", "short": 5, "long": 20, "fill": "open"})
    assert all("reason" not in t for t in no_exits["trades"]) and no_exits["columns"] == EXPORT_COLUMNS


# --------------------------------------------------------------------------- pasted CSV without candle columns


@pytest.mark.parametrize("setting", [{"fill": "open"}, {"stop_loss": 5}, {"take_profit": 5}])
def test_close_only_csv_with_a_candle_setting_is_rejected_in_one_line(client, setting):
    status, data = client.post({"csv": CLOSE_CSV, **SMA, **setting})
    assert status == 400 and data == {"ok": False, "error": data["error"]}
    assert "\n" not in data["error"]
    assert data["error"].startswith("CSV has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected ")


def test_missing_candle_columns_message_is_the_command_lines(client, tmp_path, capsys):
    path = tmp_path / "closes.csv"
    path.write_text(CLOSE_CSV)
    _, data = client.post({"csv": CLOSE_CSV, **SMA, "stop_loss": 5})
    assert cli_main([str(path), "--backtest", "--short", "2", "--long", "3", "--stop-loss", "5"]) == 1
    cli_message = capsys.readouterr().err.strip()
    assert cli_message == "Error: " + data["error"].replace("CSV", str(path), 1)


# --------------------------------------------------------------------------- bad values: 400 with a clear message


@pytest.mark.parametrize(
    "setting, flags",
    [
        ({"slippage": 100}, ["--slippage", "100"]),
        ({"slippage": -1}, ["--slippage", "-1"]),
        ({"position_size": 0}, ["--position-size", "0"]),
        ({"position_size": 1.5}, ["--position-size", "1.5"]),
        ({"stop_loss": 0}, ["--stop-loss", "0"]),
        ({"stop_loss": 100}, ["--stop-loss", "100"]),
        ({"take_profit": 0}, ["--take-profit", "0"]),
        ({"take_profit": -5}, ["--take-profit", "-5"]),
    ],
)
def test_out_of_range_values_get_the_command_lines_message(client, tmp_path, capsys, setting, flags):
    status, data = client.post({"sample": "uptrend", **setting})
    assert status == 400 and set(data) == {"ok", "error"} and data["ok"] is False
    path = tmp_path / "p.csv"
    path.write_text(CANDLE_CSV)
    with pytest.raises(SystemExit):
        cli_main([str(path), "--backtest", *flags])
    assert capsys.readouterr().err.splitlines()[-1] == f"trading_assistant.cli: error: {data['error']}"


@pytest.mark.parametrize(
    "setting, message",
    [
        ({"fill": "midday"}, "fill must be 'close' or 'open', got 'midday'"),
        ({"fill": "Open"}, "fill must be 'close' or 'open', got 'Open'"),
        ({"fill": 5}, "fill must be 'close' or 'open', got 'int'"),
        ({"fill": ["open"]}, "fill must be 'close' or 'open', got 'list'"),
        ({"slippage": "lots"}, "slippage must be a number, got 'lots'"),
        ({"position_size": "half"}, "position_size must be a number, got 'half'"),
        ({"stop_loss": True}, "stop_loss must be a number"),
        ({"take_profit": "Infinity"}, "take_profit must be a finite number"),
        ({"take_profit": [5]}, "take_profit must be a number"),
    ],
)
def test_wrong_kind_of_value_is_rejected_like_other_bad_inputs(client, setting, message):
    status, data = client.post({"sample": "uptrend", **setting})
    assert (status, data) == (400, {"ok": False, "error": message})


def test_errors_do_not_depend_on_the_source(client):
    # the setting is checked before the data is read, so the message is the same for a sample or a CSV
    assert client.post({"sample": "uptrend", "slippage": 100}) == client.post({"csv": CLOSE_CSV, **SMA, "slippage": 100})
