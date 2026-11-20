"""Tests for --weights on the portfolio command and ``weights`` on POST /api/portfolio.

The 8-bar example with A=70 B=30, cash 1000, short 1, long 2, no fees,
worked out by hand:

  A gets 700: BUY on bar 3, filled bar 4 @ 11 -> 63 shares (693), cash 7
     equity 700 700 700 700 700, 7+756 = 763, 7+630 = 637, SELL filled bar 7 @ 8 -> 7+504 = 511
     return (511 - 700) / 700 = -27 %; drawdown 763 -> 511 = -252/763 = -33.03 %
     buy & hold 70 @ 10 -> 70 * 8 = 560 (-20 %)
  B gets 300: BUY filled bar 4 @ 22 -> 13 shares (286), cash 14
     equity 300 300 300 300 300, 14+260 = 274, SELL filled bar 6 @ 18 -> 14+234 = 248, 248
     return (248 - 300) / 300 = -17.33 %; buy & hold 15 @ 20 -> 15 * 17 = 255 (-15 %)
  Portfolio 1000 1000 1000 1000 1000 1037 885 759 -> -24.1 %
     drawdown 1037 -> 759 = -278/1037 = -26.81 %
     buy & hold with the same weights 560 + 255 = 815 -> -18.5 %
"""

import json
import math
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from trading_assistant import portfolio
from trading_assistant.cli import DISCLAIMER
from trading_assistant.web import server as web

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]


def csv_text(closes):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, closes))


A = csv_text([10, 9, 8, 9, 11, 12, 10, 8])
B = csv_text([20, 20, 19, 21, 22, 20, 18, 17])
C = csv_text([30, 29, 31, 33, 32, 30, 31, 35])
BAD = "date,close\n2026-01-02,30\n2026-01-05,abc\n"
SETTINGS = ["--short", "1", "--long", "2", "--cash", "1000"]

TEXT_70_30 = "\n".join([
    "Portfolio: 2 symbols, cash split by weight (A 70%, B 30%), SMA 1/2 crossover, fee 0.00 + 0.00%,"
    " on the dates every file shares",
    "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
    "Cash: 1,000.00  Final equity: 759.00",
    "Return: -24.10%  Max drawdown: -26.81%  Buy & hold (same weights): -18.50%",
    "Symbol  Weight  Bars used  Bars lost   Return  Trades  Buy&Hold",
    "A          70%          8          0  -27.00%       2   -20.00%",
    "B          30%          8          0  -17.33%       2   -15.00%",
    "Worst single-symbol drawdown: -33.03% (A)",
    DISCLAIMER,
]) + "\n"

SUMMARY_70_30 = {
    "short": 1, "long": 2, "fee": 0.0, "fee_pct": 0.0,
    "weights": {"A": 70.0, "B": 30.0},
    "start_date": "2026-01-02", "end_date": "2026-01-13", "shared_dates": 8,
    "initial_cash": 1000.0, "final_equity": 759.0,
    "return_pct": pytest.approx(-24.1),
    "max_drawdown_pct": pytest.approx(-278 / 1037 * 100),
    "buy_hold_return_pct": pytest.approx(-18.5),
    "worst_symbol_drawdown": {"symbol": "A", "max_drawdown_pct": pytest.approx(-252 / 763 * 100)},
    "symbols": [
        {"symbol": "A", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-27.0),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-20.0)},
        {"symbol": "B", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-52 / 300 * 100),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-15.0)},
    ],
}


def _folder(tmp_path, files):
    folder = tmp_path / f"prices{len(list(tmp_path.iterdir()))}"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text)
    return folder


def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "trading_assistant.portfolio", *map(str, args)],
                          capture_output=True, text=True, env=env)


def _usage_error(proc, message):
    assert proc.returncode == 2, proc.stderr
    assert proc.stdout == ""
    assert proc.stderr.startswith("usage: trading_assistant.portfolio")
    assert proc.stderr.endswith(f"trading_assistant.portfolio: error: {message}\n")
    assert "Traceback" not in proc.stderr


@pytest.fixture(scope="module")
def api():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]

    def post(payload):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        req = Request(f"http://{host}:{port}/api/portfolio", data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    yield post
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------- the 70 / 30 example


def test_text_output_70_30(tmp_path):
    proc = _run(_folder(tmp_path, {"A.csv": A, "B.csv": B}), *SETTINGS, "--weights", "A=70", "B=30")
    assert (proc.returncode, proc.stderr) == (0, "")
    assert proc.stdout == TEXT_70_30


def test_json_output_70_30(tmp_path):
    proc = _run(_folder(tmp_path, {"A.csv": A, "B.csv": B}), *SETTINGS, "--weights", "A=70", "B=30", "--json")
    assert (proc.returncode, proc.stderr) == (0, "")
    assert json.loads(proc.stdout) == {"summary": SUMMARY_70_30, "skipped": [], "disclaimer": DISCLAIMER}


def test_csv_output_70_30(tmp_path):
    out = tmp_path / "equity.csv"
    proc = _run(_folder(tmp_path, {"A.csv": A, "B.csv": B}), *SETTINGS, "--weights", "A=70", "B=30", "--csv", out)
    assert proc.returncode == 0
    assert out.read_text() == (
        "date,portfolio,A,B\n"
        "2026-01-02,1000.00,700.00,300.00\n2026-01-05,1000.00,700.00,300.00\n"
        "2026-01-06,1000.00,700.00,300.00\n2026-01-07,1000.00,700.00,300.00\n"
        "2026-01-08,1000.00,700.00,300.00\n2026-01-09,1037.00,763.00,274.00\n"
        "2026-01-12,885.00,637.00,248.00\n2026-01-13,759.00,511.00,248.00\n"
    )


def test_weight_order_does_not_matter_and_repeated_flags_add_up(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B})
    assert _run(folder, *SETTINGS, "--weights", "B=30", "A=70").stdout == TEXT_70_30
    assert _run(folder, *SETTINGS, "--weights", "A=70", "--weights", "B=30").stdout == TEXT_70_30


def test_without_weights_nothing_mentions_them(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B})
    text = _run(folder, *SETTINGS).stdout
    assert text.split("\n")[0].startswith("Portfolio: 2 symbols, cash split equally, SMA 1/2")
    assert "Buy & hold (equal weight): -17.50%" in text and "Weight " not in text
    assert "weights" not in json.loads(_run(folder, *SETTINGS, "--json").stdout)["summary"]


def test_weights_add_up_exactly_as_written(tmp_path):
    # 33.3 + 33.3 + 33.4 is exactly 100; each symbol gets cash * weight / 100.
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B, "C.csv": C})
    proc = _run(folder, *SETTINGS, "--weights", "A=33.3", "B=33.3", "C=33.4", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["summary"]["weights"] == {"A": 33.3, "B": 33.3, "C": 33.4}
    tables = {s: (DATES, [float(line.split(",")[1]) for line in t.split("\n")[1:-1]])
              for s, t in (("A", A), ("B", B), ("C", C))}
    result = portfolio.run_portfolio(tables, cash=1000, short=1, long=2,
                                     weights=portfolio.parse_weights(["A=33.3", "B=33.3", "C=33.4"]))
    assert [r.initial_cash for r in result.results.values()] == [1000 * 33.3 / 100, 1000 * 33.3 / 100, 1000 * 33.4 / 100]
    # 71.18 + 7.81 + 21.01 is 100 as written but 100.00000000000001 in floating point,
    # whichever way the floats are added: still accepted.
    assert 71.18 + 7.81 + 21.01 != 100 and math.fsum([71.18, 7.81, 21.01]) != 100
    proc = _run(folder, *SETTINGS, "--weights", "A=71.18", "B=7.81", "C=21.01")
    assert proc.returncode == 0, proc.stderr
    assert "cash split by weight (A 71.18%, B 7.81%, C 21.01%)" in proc.stdout


def test_symbol_with_an_equals_sign(tmp_path):
    folder = _folder(tmp_path, {"X=Y.csv": A, "B.csv": B})
    proc = _run(folder, *SETTINGS, "--weights", "X=Y=70", "B=30", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["summary"]["weights"] == {"B": 30.0, "X=Y": 70.0}


# ---------------------------------------------------------------- bad weights


def test_bad_weights_are_usage_errors(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B})
    cases = [
        (["A70", "B=30"], "--weights: 'A70' is not SYMBOL=PERCENT (like A=60)"),
        (["=70", "B=30"], "--weights: '=70' is not SYMBOL=PERCENT (like A=60)"),
        (["A=abc", "B=30"], "--weights: the weight for A must be a number like 60 or 33.5, got 'abc'"),
        (["A=", "B=100"], "--weights: the weight for A must be a number like 60 or 33.5, got ''"),
        (["A=1e2"], "--weights: the weight for A must be a number like 60 or 33.5, got '1e2'"),
        (["A=0", "B=100"], "--weights: the weight for A must be above 0, got 0"),
        (["A=-10", "B=110"], "--weights: the weight for A must be above 0, got -10"),
        (["A=50", "A=50"], "--weights: A is listed more than once"),
        (["A=70", "B=40"], "--weights must add up to 100, got 110"),
        (["A=33.33", "B=33.33", "C=33.33"], "--weights must add up to 100, got 99.99"),
    ]
    for weights, message in cases:
        _usage_error(_run(folder, *SETTINGS, "--weights", *weights), message)


def test_weights_that_do_not_match_the_files_exit_2(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B})
    _usage_error(_run(folder, *SETTINGS, "--weights", "A=70", "C=30"),
                 f"--weights: no .csv file for C in {folder}")
    _usage_error(_run(folder, *SETTINGS, "--weights", "A=100"),
                 "--weights: no weight for B; every file that is used needs one")


def test_weight_for_a_skipped_file_exits_1(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B, "BAD.csv": BAD})
    out = tmp_path / "equity.csv"
    proc = _run(folder, *SETTINGS, "--weights", "A=40", "B=30", "BAD=30", "--csv", out)
    assert (proc.returncode, proc.stdout) == (1, "")
    assert proc.stderr == ("Error: BAD.csv has a weight but was skipped: BAD.csv line 3: invalid close value 'abc'"
                           " (expected a number like 101.5)\n")
    assert not out.exists()


def test_skipped_file_without_a_weight_is_fine(tmp_path):
    folder = _folder(tmp_path, {"A.csv": A, "B.csv": B, "BAD.csv": BAD})
    proc = _run(folder, *SETTINGS, "--weights", "A=70", "B=30")
    assert proc.returncode == 0
    assert proc.stdout.replace("Skipped: 1\n  BAD.csv line 3: invalid close value 'abc' (expected a number like"
                               " 101.5)\n", "") == TEXT_70_30


# ---------------------------------------------------------------- the web page


def test_api_reply_equals_the_command_json(api, tmp_path):
    files = {"A.csv": A, "B.csv": B, "BAD.csv": BAD}
    proc = _run(_folder(tmp_path, files), *SETTINGS, "--weights", "A=70", "B=30", "--json")
    status, data = api({"files": files, "short": 1, "long": 2, "cash": 1000, "weights": ["A=70", "B=30"]})
    assert status == 200
    assert data == json.loads(proc.stdout)
    assert data["summary"] == SUMMARY_70_30


def test_api_weight_errors_are_400_with_the_command_messages(api, tmp_path, capsys):
    files = {"A.csv": A, "B.csv": B, "BAD.csv": BAD}
    folder = _folder(tmp_path, files)
    for weights in (["A=70", "B=40"], ["A=50", "A=50"], ["A=0", "B=100"], ["A=100"],
                    ["A=40", "B=30", "BAD=30"]):
        proc = _run(folder, *SETTINGS, "--weights", *weights)
        status, data = api({"files": files, "short": 1, "long": 2, "cash": 1000, "weights": weights})
        assert status == 400, weights
        assert proc.returncode in (1, 2)
        assert proc.stderr.endswith(f"{data['error']}\n"), weights


def test_api_weight_for_a_symbol_not_in_the_request(api):
    status, data = api({"files": {"A.csv": A, "B.csv": B}, "short": 1, "long": 2, "weights": ["A=70", "C=30"]})
    assert (status, data) == (400, {"ok": False, "error": "--weights: no .csv file for C in the request"})


def test_api_weights_must_be_a_list_of_strings(api):
    for weights in ({"A": 70, "B": 30}, "A=70 B=30", ["A=70", 30]):
        status, data = api({"files": {"A.csv": A, "B.csv": B}, "weights": weights})
        assert (status, data) == (400, {"ok": False, "error":
                                        'weights must be a list of "SYMBOL=PERCENT" strings, like ["A=60", "B=40"]'})
