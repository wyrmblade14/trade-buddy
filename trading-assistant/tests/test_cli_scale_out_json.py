"""--json with --scale-out: backtest.scale_out_pct and backtest.scale_out_exits, only when the option is used.

The c.csv hand case (cash 1000, --short 1 --long 2; arithmetic in test_scale_out.py) must give the same numbers as
the text report. Runs without the option must print exactly the JSON they printed before: JSON_RUNS is checked
against a SHA-256 of [exit code, stdout, stderr] recorded from the code before --scale-out existed (git HEAD
9ab3743, in a folder like the one ``folder`` makes); the same hashes came from the CLI before the JSON keys.
"""

import contextlib
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import main

DATA = Path(__file__).parent / "data"
H = ["c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CL = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
J = [*H, "--json"]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, as a close-only file


def run(argv):
    """(exit code, stdout, stderr) of ``main(argv)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def folder(tmp_path, monkeypatch):
    shutil.copy(DATA / "c.csv", tmp_path / "c.csv")
    (tmp_path / "closes.csv").write_text(
        "date,close\n" + "".join(f"2026-01-{i:02d},{c}\n" for i, c in enumerate(CLOSES, 1))
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.mark.parametrize(
    "extra, pct, exits, fills, equity",
    [
        (["--scale-out", "5"], 5.0, 1, [(4, 90, "signal"), (5, 45, "scale_out"), (7, 45, "signal"), (9, 81, "signal")], 995.95),
        (["--scale-out", "9"], 9.0, 1, [(4, 90, "signal"), (5, 45, "scale_out"), (7, 45, "signal"), (9, 83, "signal")], 1016.15),
        (["--scale-out", "10"], 10.0, 0, [(4, 90, "signal"), (7, 90, "signal"), (9, 75, "signal")], 925.0),
        (["--scale-out", "5", "--stop-loss", "10"], 5.0, 1,
         [(4, 90, "signal"), (5, 45, "scale_out"), (6, 45, "stop"), (9, 81, "signal")], 991.45),
    ],
    ids=["5", "9", "10", "5 stop 10"],
)
def test_hand_case_matches_the_text_report(folder, extra, pct, exits, fills, equity):
    code, out, err = run([*J, *extra])
    assert (code, err) == (0, "")
    d = json.loads(out)["backtest"]
    assert (d["scale_out_pct"], d["scale_out_exits"]) == (pct, exits)
    assert [(f["bar"], f["shares"], f["reason"]) for f in d["fills"]] == fills
    assert d["final_equity"] == pytest.approx(equity)
    # The text report of the same run says the same.
    text = run([*H, *extra])[1]
    assert f"when a high reaches {pct:.2f}% above the average entry; {exits} partial sell{'' if exits == 1 else 's'}," in text
    rows = re.findall(r"bar (\d+)\s+(BUY|SELL)\s+(\d+) @\s+([\d,.]+)\s+value.*cash\s+([\d,.]+)\s+(\w+)", text)
    assert rows == [
        (str(f["bar"]), f["side"], str(f["shares"]), f"{f['price']:,.2f}", f"{f['cash_after']:,.2f}", f["reason"])
        for f in d["fills"]
    ]
    for line in (
        f"  Trades:      {d['trades']} ({d['buys']} buy, {d['sells']} sell)",
        f"  Round trips: {d['round_trips']} completed, {d['winning_round_trips']} made money",
        f"  End cash:    {d['final_cash']:,.2f}",
        f"  End shares:  {d['final_position']} @ {d['final_price']:,.2f}",
        f"  End equity:  {d['final_equity']:,.2f}",
        f"  Return:      {d['return_pct']:+.2f}%",
    ):
        assert line in text, line


def test_key_places(folder):
    d = json.loads(run([*J, "--scale-out", "5"])[1])["backtest"]
    keys = list(d)
    assert keys[keys.index("take_profit_pct") : keys.index("fills")] == [
        "take_profit_pct", "scale_out_pct", "trades", "buys", "sells", "scale_out_exits",
    ]
    # Next to the other exit keys: after the breakeven ones, before the cooldown ones.
    argv = [*J, "--trailing-stop", "20", "--atr-stop", "--atr-period", "2", "--breakeven", "50", "--scale-out", "5",
            "--cooldown", "2", "--max-hold", "9"]
    keys = list(json.loads(run(argv)[1])["backtest"])
    assert keys[keys.index("stop_loss_pct") : keys.index("fills")] == [
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "atr_stop", "breakeven_pct", "scale_out_pct",
        "cooldown_bars", "max_hold_bars", "trades", "buys", "sells", "risk_skipped_buys", "breakeven_exits",
        "scale_out_exits", "cooldown_skipped_buys", "time_exits",
    ]


# Recorded before --scale-out existed; see the module docstring.
JSON_RUNS = [
    (["c.csv", "--json"], "241275c49c344c2be7e63b407164f768184a7a3ab75cc1483cf6f64fea58fa83"),
    (J, "2cdb032bcd246fa9c0a7d46d46985279a3c113a0cc6583611b399ccf02fa43f9"),
    ([*J, "--trailing-stop", "10"], "23f51d227b3d556c591bd0485dc56def4aa2f00d99f72153587cc2b69a887039"),
    ([*J, "--atr-stop", "--atr-period", "2"], "63bd109aa2c25095f95b396dc7d030dccca164253a14d7a3e6bb2cadd9d6c375"),
    ([*J, "--risk-pct", "1", "--atr-period", "2"], "8b8454b143b27d84ef901aaa09206240bebd9619b34c12682aa586948d3c15de"),
    ([*J, "--breakeven", "5"], "5725c9bd1af1b1c5939aac2ac5426e7c6dfc80350922345dbedb3b51270e366a"),
    ([*J, "--breakeven", "5", "--stop-loss", "10", "--cooldown", "2"],
     "6d87dd8b56b7476552fe5e1ea9b88b9cf699111cb7f4ed93120b3aa832e74754"),
    ([*J, "--take-profit", "5", "--fill", "open", "--stats"],
     "9b318463693ffc5bb91675e246fb048dc76d46e96eacc377f8f25fb111a1c902"),
    ([*J, "--max-hold", "1", "--min-hold", "2"], "b6620c013b5da8c4b3cbf542bc0d22b2eb372459ee3b12c537a202ba150ce1cf"),
    ([*J, "--max-drawdown", "5", "--max-losses", "1"], "92ff9b16a2ede1b47e468b552abcb7f4ff842a15056d2e4d086c6fccf3b11ef0"),
    ([*J, "--fee", "1", "--slippage", "0.5", "--position-size", "0.5", "--export", "E.csv"],
     "e22cd8448e0178a9af9ecd8b26ef5ca98c19a0d5f3908b81461274ea551227e3"),
    ([*CL, "--json", "--resample", "weekly", "--strategy", "breakout", "--param", "window=1"],
     "56b4c01df31ad54f7632a440dceb67f605e428eb9a35d54f213eccd11a862a3f"),
]


@pytest.mark.parametrize("argv, digest", JSON_RUNS, ids=[" ".join(a[8:]) or " ".join(a) for a, _ in JSON_RUNS])
def test_runs_without_it_give_exactly_the_same_json(folder, argv, digest):
    code, out, err = run(argv)
    assert "scale_out" not in out
    assert hashlib.sha256(json.dumps([code, out, err]).encode()).hexdigest() == digest


def test_export_is_not_affected(folder):
    # The same file with or without --json; backtest.export is {path, rows} as before.
    assert run([*H, "--scale-out", "5", "--export", "T.csv"])[0] == 0
    d = json.loads(run([*J, "--scale-out", "5", "--export", "E.csv"])[1])["backtest"]
    assert d["export"] == {"path": "E.csv", "rows": 11}
    assert (folder / "E.csv").read_text() == (folder / "T.csv").read_text()
