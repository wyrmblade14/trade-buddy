"""POST /api/portfolio with ``strategy`` and ``params``: the command's --strategy and --param.

``tests/data/portfolio_api_before_strategy.json`` holds 16 replies (status, Content-Type, raw body) recorded
before the API read ``strategy`` or ``params``; the files are AAA and BBB below ("hand"), AAA alone ("one")
or the downtrend, sideways and uptrend samples ("samples").
"""

import contextlib
import io
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from trading_assistant import portfolio
from trading_assistant.samples import sample_csv_rows
from trading_assistant.web import server as web

DATES = [f"2026-04-{i:02d}" for i in range(1, 11)]
HAND = {"AAA": [10, 11, 12, 13, 12, 11, 10, 11, 13, 14], "BBB": [20, 19, 18, 19, 21, 22, 21, 19, 18, 20]}


def _csv(closes):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, closes))


FILES = {
    "hand": {f"{s}.csv": _csv(cs) for s, cs in HAND.items()},
    "one": {"AAA.csv": _csv(HAND["AAA"])},
    "samples": {f"{s}.csv": "".join(",".join(r) + "\n" for r in sample_csv_rows(s))
                for s in ("downtrend", "sideways", "uptrend")},
}
BEFORE = json.loads((Path(__file__).parent / "data" / "portfolio_api_before_strategy.json").read_text())
LIST_MESSAGE = 'params must be a list of "KEY=VALUE" strings, like ["window=10"]'
UNKNOWN = "; choose from: sma_cross, rsi_reversion, breakout, ema_cross, momentum, zscore_reversion, hull_trend"


@pytest.fixture(scope="module")
def post():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]

    def send(settings, files="hand"):
        """``(status, Content-Type, raw body text)`` for the files and settings."""
        body = json.dumps({"files": FILES[files], **settings}).encode()
        request = Request(f"http://{host}:{port}/api/portfolio", data=body, method="POST",
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10) as reply:
                return reply.status, reply.headers["Content-Type"], reply.read().decode()
        except HTTPError as exc:
            return exc.code, exc.headers["Content-Type"], exc.read().decode()

    yield send
    server.shutdown()
    server.server_close()


@pytest.fixture
def command(tmp_path, monkeypatch):
    """Run the portfolio command on the hand files: ``(exit code, stdout, last stderr line)``."""
    (tmp_path / "pf").mkdir()
    for name, text in FILES["hand"].items():
        (tmp_path / "pf" / name).write_text(text)
    monkeypatch.chdir(tmp_path)

    def run(args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = portfolio.main(["pf", *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), (err.getvalue().splitlines() or [""])[-1]

    return run


def test_replies_without_another_strategy_are_unchanged(post):
    # Every recorded request, as it was and with each way of asking for the default strategy, byte for byte.
    assert len(BEFORE) == 16
    defaults = [{}, {"strategy": "sma_cross"}, {"strategy": None}, {"strategy": ""}, {"params": None},
                {"params": []}, {"strategy": "sma_cross", "params": []}, {"strategy": None, "params": None}]
    for record in BEFORE:
        for extra in defaults:
            got = post({**record["settings"], **extra}, files=record["files"])
            assert got == (record["status"], record["content_type"], record["body"]), (record["settings"], extra)


def test_breakout_replies_are_the_command_json(post, command):
    for settings, args in (
        ({"strategy": "breakout", "params": ["window=3"], "cash": 1000}, []),
        ({"strategy": "breakout", "params": ["window=3"], "cash": 1000, "weights": ["AAA=60", "BBB=40"]},
         ["--weights", "AAA=60", "BBB=40"]),
    ):
        status, _, body = post(settings)
        code, out, _ = command(["--strategy", "breakout", "--param", "window=3", "--cash", "1000", *args, "--json"])
        assert (status, code) == (200, 0)
        assert body == json.dumps(json.loads(out))  # same keys, same order, same numbers
        assert list(json.loads(body)) == ["title", "summary", "skipped", "disclaimer"]
    data = json.loads(body)
    assert data["title"].startswith("Portfolio: 2 symbols, cash split by weight (AAA 60%, BBB 40%), breakout (window=3),")
    assert data["summary"]["final_equity"] == 828.0 and data["summary"]["buy_hold_return_pct"] == 24.0


def test_params_alone_and_sma_cross_params_are_short_and_long(post):
    plain = post({"short": 2, "long": 3, "cash": 1000})
    assert plain[0] == 200
    for settings in (
        {"params": ["short=2", "long=3"], "cash": 1000},
        {"strategy": "sma_cross", "params": ["long=3", "short=2"], "cash": 1000},
        {"strategy": "sma_cross", "short": 2, "params": ["short=2", "long=3"], "cash": 1000},
        {"short": "", "long": None, "params": ["short=2", "long=3"], "cash": 1000},  # "" and null: not given
    ):
        assert post(settings) == plain, settings


def test_how_strategy_and_params_values_are_read(post):
    ok = post({"strategy": "breakout", "params": ["window=3"]})
    assert ok[0] == 200
    for settings, expected in (
        ({"strategy": True}, "unknown strategy 'bool'" + UNKNOWN),
        ({"strategy": 5}, "unknown strategy 'int'" + UNKNOWN),
        ({"strategy": []}, "unknown strategy 'list'" + UNKNOWN),
        ({"strategy": {}}, "unknown strategy 'dict'" + UNKNOWN),
        ({"strategy": "Breakout"}, "unknown strategy 'Breakout'" + UNKNOWN),
        ({"strategy": "breakout", "params": ""}, LIST_MESSAGE),
        ({"strategy": "breakout", "params": True}, LIST_MESSAGE),
        ({"strategy": "breakout", "params": 3}, LIST_MESSAGE),
        ({"strategy": "breakout", "params": {"window": 3}}, LIST_MESSAGE),
        ({"strategy": "breakout", "params": ["window=3", 3]}, LIST_MESSAGE),
        ({"strategy": "breakout", "params": [" window = 3 "]}, None),  # spaces as the command allows
        ({"strategy": "breakout", "params": ["window=3"], "short": "", "long": None}, None),  # not given
        ({"strategy": "breakout", "params": ["window=3"], "weights": []}, "--weights must add up to 100, got 0"),
    ):
        status, _, body = post(settings)
        if expected is None:
            assert (status, body) == ok[:1] + ok[2:], settings
        else:
            assert (status, json.loads(body)) == (400, {"ok": False, "error": expected}), settings


ERRORS = [
    # (request settings, the same thing as command arguments); the command gives the same message (exit 1 or 2)
    ({"strategy": "breakout", "params": ["window=3"], "short": 5}, ["--strategy", "breakout", "--short", "5"]),
    ({"strategy": "hull_trend", "long": "9"}, ["--strategy", "hull_trend", "--long", "9"]),
    ({"short": 5, "params": ["short=6"]}, ["--short", "5", "--param", "short=6"]),
    ({"params": ["short=2", "short=2"]}, ["--param", "short=2", "--param", "short=2"]),
    ({"params": ["window"]}, ["--param", "window"]),
    ({"params": ["window=x"]}, ["--param", "window=x"]),
    ({"strategy": "breakout", "params": ["period=3"]}, ["--strategy", "breakout", "--param", "period=3"]),
    ({"strategy": "breakout", "params": ["window=0"]}, ["--strategy", "breakout", "--param", "window=0"]),
    ({"params": ["short=60"]}, ["--param", "short=60"]),
    ({"short": 30, "params": ["long=25"]}, ["--short", "30", "--param", "long=25"]),
    ({"strategy": "breakout", "params": ["window=9"]}, ["--strategy", "breakout", "--param", "window=9"]),
    ({"strategy": "hull_trend", "params": ["window=500"]}, ["--strategy", "hull_trend", "--param", "window=500"]),
]


@pytest.mark.parametrize("settings, args", ERRORS, ids=[" ".join(a) for _, a in ERRORS])
def test_errors_are_400_with_the_command_message(post, command, settings, args):
    status, _, body = post(settings)
    code, out, last = command(args)
    assert status == 400 and code in (1, 2) and out == ""
    message = json.loads(body)["error"]
    assert last in (f"trading_assistant.portfolio: error: {message}", f"Error: {message}")


def test_api_only_messages(post, command):
    # MAX_WINDOW holds for window parameters in params too, named as sent; the command has no such limit.
    for settings, message in (
        ({"params": ["long=600"]}, "--param long must be at most 500, got 600"),
        ({"strategy": "breakout", "params": ["window=501"]}, "--param window must be at most 500, got 501"),
        ({"strategy": "rsi_reversion", "params": ["period=600"]}, "--param period must be at most 500, got 600"),
        ({"long": 600, "params": ["long=600"]}, "--long must be at most 500, got 600"),  # the top-level one first
    ):
        status, _, body = post(settings)
        assert (status, json.loads(body)["error"]) == (400, message), settings
    # An unknown strategy is worded as in POST /api/backtest; the command's is argparse's.
    status, _, body = post({"strategy": "nope"})
    assert (status, json.loads(body)["error"]) == (400, "unknown strategy 'nope'" + UNKNOWN)
    assert command(["--strategy", "nope"])[2].startswith(
        "trading_assistant.portfolio: error: argument --strategy: invalid choice: 'nope'")
