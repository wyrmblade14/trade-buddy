"""``--json`` with ``--trailing-stop``: ``backtest.trailing_stop_pct`` and the ``trail`` fills.

Same 8-bar candle file as test_cli_trailing_stop.py, --cash 500 --short 1 --long 2:
BUY 45 @ 11 on bar 4 (cash 5); trail 10 %: bar 6 level 13 * 0.9 = 11.7, opens at 12.0
above it, low 10.0 reaches it -> SELL 45 @ 11.70, cash 531.50, reason trail.
Gap variant (bar 6 opens at 11.0): SELL 45 @ 11.00, cash 500.00.

``trailing_stop_pct`` is in the backtest object only when --trailing-stop is given,
right after ``take_profit_pct``; without it the JSON is byte for byte what it was.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import main

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

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
CANDLES_GAP = CANDLES.replace("2026-01-07,12.0,", "2026-01-07,11.0,")
BASE = ["c8.csv", "--backtest", "--cash", "500", "--short", "1", "--long", "2"]
TRAIL = ["--trailing-stop", "10"]
A = pytest.approx

# Captured from the command before trailing_stop_pct was added to the JSON.
OLD_PLAIN_JSON = """\
{
  "bars": 8,
  "last_close": 8.0,
  "signal": "HOLD",
  "rsi": null,
  "rsi_label": null,
  "backtest": {
    "strategy": "sma_cross",
    "params": {
      "short": 1,
      "long": 2
    },
    "fill": "close",
    "start_cash": 500.0,
    "fee": 0.0,
    "fee_pct": 0.0,
    "slippage_pct": 0.0,
    "position_size": null,
    "stop_loss_pct": null,
    "take_profit_pct": null,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "fills": [
      {
        "bar": 4,
        "side": "BUY",
        "shares": 45,
        "price": 11.0,
        "value": 495.0,
        "cost": 0.0,
        "cash_after": 5.0,
        "reason": "signal"
      },
      {
        "bar": 7,
        "side": "SELL",
        "shares": 45,
        "price": 8.0,
        "value": 360.0,
        "cost": 0.0,
        "cash_after": 365.0,
        "reason": "signal"
      }
    ],
    "total_costs": 0.0,
    "round_trips": 1,
    "winning_round_trips": 0,
    "final_cash": 365.0,
    "final_position": 0,
    "final_price": 8.0,
    "final_equity": 365.0,
    "return_pct": -27.0,
    "max_drawdown_pct": -33.02752293577982,
    "benchmark": {
      "shares": 50,
      "final_cash": 0.0,
      "final_equity": 400.0,
      "return_pct": -20.0,
      "max_drawdown_pct": -33.33333333333333,
      "trades": 1,
      "total_costs": 0.0
    }
  },
  "disclaimer": "Research aid only. Not financial advice."
}
"""

OLD_STOP_TARGET_STATS_EXPORT_JSON = """\
{
  "bars": 8,
  "last_close": 8.0,
  "signal": "HOLD",
  "rsi": null,
  "rsi_label": null,
  "backtest": {
    "strategy": "sma_cross",
    "params": {
      "short": 1,
      "long": 2
    },
    "fill": "close",
    "start_cash": 500.0,
    "fee": 0.0,
    "fee_pct": 0.0,
    "slippage_pct": 0.0,
    "position_size": null,
    "stop_loss_pct": 10.0,
    "take_profit_pct": 15.0,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "fills": [
      {
        "bar": 4,
        "side": "BUY",
        "shares": 45,
        "price": 11.0,
        "value": 495.0,
        "cost": 0.0,
        "cash_after": 5.0,
        "reason": "signal"
      },
      {
        "bar": 5,
        "side": "SELL",
        "shares": 45,
        "price": 12.649999999999999,
        "value": 569.2499999999999,
        "cost": 0.0,
        "cash_after": 574.2499999999999,
        "reason": "target"
      }
    ],
    "total_costs": 0.0,
    "round_trips": 1,
    "winning_round_trips": 1,
    "final_cash": 574.2499999999999,
    "final_position": 0,
    "final_price": 8.0,
    "final_equity": 574.2499999999999,
    "return_pct": 14.849999999999977,
    "max_drawdown_pct": 0.0,
    "benchmark": {
      "shares": 50,
      "final_cash": 0.0,
      "final_equity": 400.0,
      "return_pct": -20.0,
      "max_drawdown_pct": -33.33333333333333,
      "trades": 1,
      "total_costs": 0.0
    },
    "export": {
      "path": "E.csv",
      "rows": 8
    },
    "stats": {
      "total_return_pct": 14.849999999999985,
      "cagr_pct": 14512.212626099476,
      "annualized_volatility_pct": 89.09999999999991,
      "sharpe_ratio": 6.0,
      "sortino_ratio": null,
      "exposure_pct": 12.5,
      "profit_factor": null,
      "average_win": 74.24999999999989,
      "average_loss": null,
      "longest_drawdown_bars": 0
    }
  },
  "disclaimer": "Research aid only. Not financial advice."
}
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "c8.csv").write_text(CANDLES)
    (tmp_path / "gap.csv").write_text(CANDLES_GAP)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    return tmp_path


def run_cli(cwd, *argv):
    """The real command: ``python -m trading_assistant.cli`` in a child process."""
    env = dict(os.environ, COLUMNS="80")
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.cli", *argv], capture_output=True, text=True, env=env, cwd=cwd
    )


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:  # parser.error exits with 2
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def backtest_json(argv, capsys):
    code, out, err = run(argv + ["--json"], capsys)
    assert code == 0 and err == "", err
    return json.loads(out)["backtest"], out


# --------------------------------------------------------------------------- the 8-bar case


def test_real_command_8_bar_json(folder):
    proc = run_cli(folder, *BASE, *TRAIL, "--json")
    assert proc.returncode == 0 and proc.stderr == ""
    data = json.loads(proc.stdout)
    assert list(data) == ["bars", "last_close", "signal", "rsi", "rsi_label", "backtest", "disclaimer"]
    bt = data["backtest"]
    assert bt["trailing_stop_pct"] == 10.0
    assert (bt["final_cash"], bt["final_equity"], bt["final_position"]) == (A(531.5), A(531.5), 0)


def test_trailing_stop_pct_right_after_take_profit_as_a_plain_number(folder, capsys):
    bt, out = backtest_json(BASE + TRAIL, capsys)
    keys = list(bt)
    i = keys.index("take_profit_pct")
    assert keys[i + 1] == "trailing_stop_pct" and keys[i + 2] == "trades"
    assert bt["trailing_stop_pct"] == 10.0 and type(bt["trailing_stop_pct"]) is float
    assert (bt["stop_loss_pct"], bt["take_profit_pct"]) == (None, None)
    assert '    "take_profit_pct": null,\n    "trailing_stop_pct": 10.0,\n    "trades": 2,\n' in out


def test_fractional_pct(folder, capsys):
    bt, out = backtest_json(BASE + ["--trailing-stop", "7.5"], capsys)
    assert bt["trailing_stop_pct"] == 7.5 and '"trailing_stop_pct": 7.5,' in out


def test_sell_reason_is_trail(folder, capsys):
    bt, _ = backtest_json(BASE + TRAIL, capsys)
    assert [(f["bar"], f["side"], f["shares"], f["reason"]) for f in bt["fills"]] == [
        (4, "BUY", 45, "signal"),
        (6, "SELL", 45, "trail"),
    ]
    sell = bt["fills"][1]
    assert sell["price"] == A(11.7) and sell["value"] == A(526.5) and sell["cash_after"] == A(531.5)


def test_gap_sells_at_the_open(folder, capsys):
    bt, _ = backtest_json(["gap.csv"] + BASE[1:] + TRAIL, capsys)
    sell = bt["fills"][1]
    assert (sell["bar"], sell["price"], sell["reason"]) == (6, 11.0, "trail")
    assert bt["final_equity"] == A(500.0)


def test_with_stop_loss_and_take_profit(folder, capsys):
    bt, _ = backtest_json(BASE + TRAIL + ["--stop-loss", "5", "--take-profit", "20"], capsys)
    keys = list(bt)
    i = keys.index("stop_loss_pct")
    assert keys[i : i + 3] == ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct"]
    assert (bt["stop_loss_pct"], bt["take_profit_pct"], bt["trailing_stop_pct"]) == (5.0, 20.0, 10.0)
    assert bt["fills"][1]["reason"] == "trail"  # the trail level 11.7 is above the stop level 10.45


def test_json_numbers_equal_the_text_report(folder, capsys):
    bt, _ = backtest_json(BASE + TRAIL, capsys)
    code, text, _ = run(BASE + TRAIL, capsys)
    assert code == 0
    lines = text.splitlines()
    for n, f in enumerate(bt["fills"], start=1):
        expected = (
            f"    #{n:<3d} bar {f['bar']:<5d} {f['side']:<4s} {f['shares']:>8d} @ {f['price']:>10,.2f}"
            f"  value {f['value']:>12,.2f}  cost {f['cost']:>8,.2f}  cash {f['cash_after']:>12,.2f}  {f['reason']}"
        )
        assert expected in lines
    assert f"  Exits:       trail {bt['trailing_stop_pct']:.2f}% below the highest high since entry" in lines
    assert f"  Trades:      {bt['trades']} ({bt['buys']} buy, {bt['sells']} sell)" in lines
    assert f"  End cash:    {bt['final_cash']:,.2f}" in lines
    assert f"  End equity:  {bt['final_equity']:,.2f}" in lines
    assert f"  Return:      {bt['return_pct']:+.2f}%" in lines
    bench = bt["benchmark"]
    for label, a, b in [
        ("End equity", f"{bt['final_equity']:,.2f}", f"{bench['final_equity']:,.2f}"),
        ("Return", f"{bt['return_pct']:+.2f}%", f"{bench['return_pct']:+.2f}%"),
        ("Max drawdown", f"{bt['max_drawdown_pct']:.2f}%", f"{bench['max_drawdown_pct']:.2f}%"),
        ("Trades", str(bt["trades"]), str(bench["trades"])),
        ("Costs paid", f"{bt['total_costs']:,.2f}", f"{bench['total_costs']:,.2f}"),
    ]:
        assert f"    {label:<16s}{a:>14s}{b:>14s}" in lines  # the comparison table rows
    assert f"  Round trips: {bt['round_trips']} completed, {bt['winning_round_trips']} made money (100%)" in lines


def test_with_export_and_stats(folder, capsys):
    bt, _ = backtest_json(BASE + TRAIL + ["--export", "E.csv", "--stats"], capsys)
    assert bt["export"] == {"path": "E.csv", "rows": 8}
    assert list(bt)[-2:] == ["export", "stats"]
    assert bt["stats"]["total_return_pct"] == A(6.3)
    assert (folder / "E.csv").read_text().splitlines()[7].endswith(",trail")


def test_usage_error_with_json_prints_no_json(folder, capsys):
    code, out, err = run(BASE + ["--trailing-stop", "0", "--json"], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1].endswith("--trailing-stop must be between 0 and 100 (both exclusive), got 0")


# --------------------------------------------------------------------------- without --trailing-stop: unchanged


def test_old_json_runs_print_the_same(folder):
    proc = run_cli(folder, *BASE, "--json")
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, OLD_PLAIN_JSON, "")
    proc = run_cli(
        folder, *BASE, "--json", "--stop-loss", "10", "--take-profit", "15", "--stats", "--export", "E.csv"
    )
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, OLD_STOP_TARGET_STATS_EXPORT_JSON, "")
    assert "trailing_stop_pct" not in OLD_PLAIN_JSON + OLD_STOP_TARGET_STATS_EXPORT_JSON
