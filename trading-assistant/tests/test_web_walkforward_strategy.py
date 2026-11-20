"""POST /api/walkforward with ``strategy``, ``grid`` and ``params`` (the command's --strategy, --grid, --param).

tests/data/wf_api_before_strategy.json holds 24 requests without them (or with them null, "" or []) and the raw
replies the server sent before they existed (git 924f482): 10 runs, 13 errors (400) and one 413. Each must still
get exactly those bytes.
"""

import contextlib
import io
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from trading_assistant.strategies import STRATEGIES, first_signal_bars
from trading_assistant.sweep import grid_combinations
from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.web import server as web

DATA = Path(__file__).resolve().parent / "data"
BEFORE = json.loads((DATA / "wf_api_before_strategy.json").read_text())
WF_TEXT = (DATA / "wf.csv").read_text()
# The 17 closes of the worked example, dated from 2026-05-01.
EX_TEXT = "date,close\n" + "".join(
    f"2026-05-{i + 1:02d},{c}\n" for i, c in enumerate([10, 11, 12, 13, 12, 11, 10, 11, 13, 14, 15, 13, 16, 17, 15, 14, 16]))
CHOICES = ", ".join(f"'{name}'" for name in STRATEGIES)


@pytest.fixture(scope="module")
def post():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]

    def post(payload):
        req = Request(f"http://{host}:{port}/api/walkforward", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=60) as resp:
                return resp.status, resp.headers["Content-Type"], resp.read().decode()
        except HTTPError as exc:
            return exc.code, exc.headers["Content-Type"], exc.read().decode()

    yield post
    server.shutdown()
    server.server_close()


def command(tmp_path, text, argv):
    """``(exit code, stdout, last stderr line without its prefix)`` of the command on ``text``."""
    (tmp_path / "prices.csv").write_text(text)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = walkforward_main([str(tmp_path / "prices.csv"), *argv])
        except SystemExit as exc:
            code = exc.code
    last = (err.getvalue().strip().splitlines() or [""])[-1]
    for prefix in ("trading_assistant.walkforward: error: ", "Error: "):
        last = last[len(prefix):] if last.startswith(prefix) else last
    return code, out.getvalue(), last


def test_without_strategy_every_reply_is_byte_for_byte_the_old_one(post):
    assert len(BEFORE["replies"]) == 24
    for record in BEFORE["replies"]:
        assert post(record["request"]) == (record["status"], record["content_type"], record["body"]), record["request"]


def test_strategy_replies_are_the_command_json(post, tmp_path):
    for payload, argv in [
        # The worked example: one window (17 closes), window=3 chosen at -16.60%, test +0.00% with 1 trade.
        ({"csv": EX_TEXT, "strategy": "breakout", "grid": ["window=2,3"], "train": 8, "test": 6, "cash": 1000},
         ["--strategy", "breakout", "--grid", "window=2,3", "--train", "8", "--test", "6", "--cash", "1000"]),
        ({"csv": WF_TEXT, "strategy": "momentum", "params": ["window=4"], "grid": ["threshold=0,5"], "train": "4",
          "test": 7, "cash": "1000", "warmup": True},
         ["--strategy", "momentum", "--param", "window=4", "--grid", "threshold=0,5", "--train", "4", "--test", "7",
          "--cash", "1000", "--warmup"]),
        ({"csv": WF_TEXT, "strategy": "sma_cross", "grid": ["short=1,2", "long=3,4"], "short": "", "long": [],
          "train": 7, "test": 4, "step": 3, "fee": 1},
         ["--strategy", "sma_cross", "--grid", "short=1,2", "--grid", "long=3,4", "--train", "7", "--test", "4",
          "--step", "3", "--fee", "1"]),
        ({"csv": WF_TEXT, "strategy": "zscore_reversion", "grid": ["entry=-1.5,-1.0", "window=3,4"],
          "params": ["exit=0.5"], "train": 6, "test": 6},
         ["--strategy", "zscore_reversion", "--grid", "entry=-1.5,-1.0", "--grid", "window=3,4", "--param",
          "exit=0.5", "--train", "6", "--test", "6"]),
        ({"csv": WF_TEXT, "strategy": "rsi_reversion", "train": 9, "test": 9}, ["--strategy", "rsi_reversion",
                                                                                "--train", "9", "--test", "9"]),
    ]:
        status, _, body = post(payload)
        code, out, err = command(tmp_path, payload["csv"], [*argv, "--json"])
        assert (status, code) == (200, 0), (body, err)
        reply, printed = json.loads(body), json.loads(out)
        assert reply == printed and list(reply) == list(printed), argv  # same numbers, same key order
        assert reply["strategy"] == argv[1] and all("params" in w for w in reply["windows"])
    example = json.loads(post({"csv": EX_TEXT, "strategy": "breakout", "grid": ["window=2,3"], "train": 8, "test": 6,
                               "cash": 1000})[2])
    (window,) = example["windows"]
    assert (window["params"], window["test_trades"]) == ({"window": 3}, 1)
    assert [round(window[k], 2) for k in ("train_return_pct", "test_return_pct", "buy_hold_return_pct")] == [
        -16.6, 0.0, 30.4]


COMMAND_REFUSALS = [
    # (request fields on top of train 8 / test 6, the same as command options)
    ({"strategy": "sma_cross", "short": "2"}, ["--strategy", "sma_cross", "--short", "2"]),
    ({"strategy": "breakout", "long": [5]}, ["--strategy", "breakout", "--long", "5"]),
    ({"grid": ["window=2"], "short": "1", "long": "3"}, ["--grid", "window=2", "--short", "1", "--long", "3"]),
    ({"params": ["threshold=1"], "long": "3"}, ["--param", "threshold=1", "--long", "3"]),
    ({"grid": ["window=2"]}, ["--grid", "window=2"]),
    ({"params": ["window=2"]}, ["--param", "window=2"]),
    ({"strategy": "nope"}, ["--strategy", "nope"]),
    ({"strategy": "breakout", "grid": ["window"]}, ["--strategy", "breakout", "--grid", "window"]),
    ({"strategy": "breakout", "grid": ["window=2,x"]}, ["--strategy", "breakout", "--grid", "window=2,x"]),
    ({"strategy": "breakout", "grid": ["window=2,,3"]}, ["--strategy", "breakout", "--grid", "window=2,,3"]),
    ({"strategy": "momentum", "grid": ["threshold=nan"]}, ["--strategy", "momentum", "--grid", "threshold=nan"]),
    ({"strategy": "breakout", "params": ["window=2,3"]}, ["--strategy", "breakout", "--param", "window=2,3"]),
    ({"strategy": "breakout", "params": ["window=x"]}, ["--strategy", "breakout", "--param", "window=x"]),
    ({"strategy": "breakout", "params": ["window"]}, ["--strategy", "breakout", "--param", "window"]),
    ({"strategy": "breakout", "grid": ["window=2", "window=3"]},
     ["--strategy", "breakout", "--grid", "window=2", "--grid", "window=3"]),
    ({"strategy": "breakout", "params": ["window=2", "window=3"]},
     ["--strategy", "breakout", "--param", "window=2", "--param", "window=3"]),
    ({"strategy": "breakout", "grid": ["window=2"], "params": ["window=3"]},
     ["--strategy", "breakout", "--grid", "window=2", "--param", "window=3"]),
    ({"strategy": "breakout", "grid": ["period=2"]}, ["--strategy", "breakout", "--grid", "period=2"]),
    ({"strategy": "breakout", "params": ["size=2"]}, ["--strategy", "breakout", "--param", "size=2"]),
    ({"strategy": "breakout", "grid": ["window=2,0,3"]}, ["--strategy", "breakout", "--grid", "window=2,0,3"]),
    ({"strategy": "breakout", "grid": ["window=2.5"]}, ["--strategy", "breakout", "--grid", "window=2.5"]),
    ({"strategy": "rsi_reversion", "grid": ["oversold=20,120"]}, ["--strategy", "rsi_reversion", "--grid", "oversold=20,120"]),
    ({"strategy": "zscore_reversion", "grid": ["window=1,5"]}, ["--strategy", "zscore_reversion", "--grid", "window=1,5"]),
    ({"strategy": "sma_cross", "grid": ["short=50", "long=20"]},
     ["--strategy", "sma_cross", "--grid", "short=50", "--grid", "long=20"]),
    ({"strategy": "breakout", "test": 0}, ["--strategy", "breakout", "--test", "0"]),
    ({"strategy": "breakout", "step": 0}, ["--strategy", "breakout", "--step", "0"]),
    ({"strategy": "breakout", "fee": -1}, ["--strategy", "breakout", "--fee", "-1"]),
    ({"strategy": "breakout", "train": 13}, ["--strategy", "breakout", "--train", "13"]),  # a data error (exit 1)
]


def test_every_refusal_of_the_command_is_a_400_with_its_message(post, tmp_path):
    for fields, options in COMMAND_REFUSALS:
        payload = {"csv": WF_TEXT, "train": 8, "test": 6, **fields}
        argv = ["--train", str(payload["train"]), "--test", str(payload["test"]), *options]
        code, out, message = command(tmp_path, WF_TEXT, argv)
        assert code in (1, 2) and out == "", options
        status, ctype, body = post(payload)
        assert (status, ctype, json.loads(body)) == (400, "application/json; charset=utf-8",
                                                     {"ok": False, "error": message}), options
    assert len(COMMAND_REFUSALS) == 28


def test_request_only_checks_and_limits(post, monkeypatch):
    base = {"csv": WF_TEXT, "train": 8, "test": 6, "strategy": "breakout"}
    for fields, status, message in [
        ({"strategy": 5}, 400, f"argument --strategy: invalid choice: 5 (choose from {CHOICES})"),
        ({"strategy": ["breakout"]}, 400, f"argument --strategy: invalid choice: ['breakout'] (choose from {CHOICES})"),
        ({"grid": "window=2,3"}, 400, 'grid must be a list of "KEY=LIST" strings, like ["window=10,20,30"]'),
        ({"grid": [["window=2"]]}, 400, 'grid must be a list of "KEY=LIST" strings, like ["window=10,20,30"]'),
        ({"params": {"window": 2}}, 400, 'params must be a list of "KEY=VALUE" strings, like ["threshold=0.5"]'),
        ({"grid": ["window=2,501"]}, 400, f"--grid window must be at most {web.MAX_WINDOW}, got 501"),
        ({"params": ["window=600"]}, 400, f"--param window must be at most {web.MAX_WINDOW}, got 600"),
        ({"strategy": "rsi_reversion", "grid": ["period=2,501"]}, 400, "--grid period must be at most 500, got 501"),
        ({"strategy": "sma_cross", "grid": ["short=2", "long=3,900"]}, 400, "--grid long must be at most 500, got 900"),
        ({"strategy": "momentum", "grid": ["window=" + ",".join(map(str, range(1, 101))),
                                           "threshold=" + ",".join(map(str, range(101)))]},
         413, "this walk-forward is too big for the web page (10,100 parameter sets; the limit is 10,000); use shorter"
              " --grid lists, or run python -m trading_assistant.walkforward"),
    ]:
        reply = post({**base, **fields})
        assert (reply[0], json.loads(reply[2])) == (status, {"ok": False, "error": message}), fields
    # A threshold is no window: 600 is fine. [] and "" for short/long are "not given".
    assert post({**base, "strategy": "momentum", "params": ["threshold=600"], "short": "", "long": []})[0] == 200
    # The work limit, at its boundary (see test_work_counts_every_close_read for the count).
    request = {**base, "csv": EX_TEXT, "grid": ["window=2,3"], "cash": 1000}
    work = web._strategy_work("breakout", grid_combinations("breakout", {"window": [2, 3]}), 1, 8, 6, False)
    assert work == 12  # 1 window: 8 train bars for each of window=2 (0.508) and 3 (0.512), 6 test bars at 0.512
    monkeypatch.setattr(web, "MAX_WALKFORWARD_BAR_STEPS", work)
    assert post(request)[0] == 200
    monkeypatch.setattr(web, "MAX_WALKFORWARD_BAR_STEPS", work - 1)
    status, _, body = post(request)
    assert (status, json.loads(body)["error"]) == (413, (
        "this walk-forward is too big for the web page (1 windows x 2 breakout parameter sets, 12 bar-steps; the limit"
        " is 11); use fewer parameter sets, a larger step or shorter blocks, or run python -m"
        " trading_assistant.walkforward"))


def test_work_counts_every_close_read():
    # The closed form against a plain count, bar by bar: a backtest of n bars after w warm-up bars reads w + t + 1
    # closes on bar t, and (for zscore_reversion and hull_trend) window more for each of them past the window.
    def plain(strategy, combos, windows, train, test, warmup):
        def cost(p, n, warm):
            if strategy in web.WALKFORWARD_BAR_WEIGHTS:
                base, slope, key = web.WALKFORWARD_BAR_WEIGHTS[strategy]
                return sum(base + slope * p[key] for _ in range(n))
            per_read, per_window_read = web.WALKFORWARD_READ_WEIGHTS[strategy]
            w = p.get("window", 0)
            return sum((warm + t + 1) * per_read + max(0, warm + t + 1 - w + 1) * w * per_window_read * (w > 0)
                       for t in range(n))
        return windows * (sum(cost(p, train, 0) for p in combos)
                          + max(cost(p, test, first_signal_bars(strategy, p) - 1 if warmup else 0) for p in combos))
    cases = {"sma_cross": {"short": [2, 5], "long": [10, 40]}, "breakout": {"window": [3, 30]},
             "rsi_reversion": {"period": [3, 14]}, "ema_cross": {"short": [3]}, "momentum": {"window": [2, 25]},
             "zscore_reversion": {"window": [2, 7, 60]}, "hull_trend": {"window": [4, 9, 70]}}
    for strategy, grid in cases.items():
        combos = grid_combinations(strategy, grid)
        for train, test, warmup in ((40, 20, False), (40, 20, True), (5, 50, True), (100, 3, False)):
            expected = plain(strategy, combos, 7, train, test, warmup)
            assert web._strategy_work(strategy, combos, 7, train, test, warmup) == pytest.approx(expected, abs=1), (
                strategy, train, test, warmup)
