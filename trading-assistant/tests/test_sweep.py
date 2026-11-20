"""Tests for trading_assistant.sweep (function and ``python -m`` command)."""

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant import sweep as sweep_module
from trading_assistant.cli import DEFAULT_CASH, DISCLAIMER
from trading_assistant.sweep import OVERFIT_WARNING, main, sweep

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Flat at 10, a dip to 9, then a jump. With a short window of 2 or 3 and a long
# window of 4, the average of the last bars rises above the long average on bar
# 8 (close 12), so the buy fills on bar 9 at 14. With 1000 cash that is 71
# shares for 994, leaving 6; at the last close of 16 the account is
# 71 * 16 + 6 = 1142, a return of 14.2%. Nothing is ever sold, so there are no
# round trips and the drawdown is 0. A long window of 12 needs 12 bars, which
# exist, but the series never gets a signal from it: no trades, return 0.
CLOSES = [10.0] * 5 + [9.0] * 3 + [12.0, 14.0, 16.0, 16.0]


def write_prices(tmp_path, closes=CLOSES, name="prices.csv"):
    path = tmp_path / name
    path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))
    return str(path)


# ------------------------------------------------------------------ sweep()


def test_best_pair_is_hand_checked():
    rows = sweep(CLOSES, [2], [4], cash=1000)
    assert len(rows) == 1
    row = rows[0]
    assert (row["short"], row["long"]) == (2, 4)
    assert row["return_pct"] == pytest.approx(14.2)
    assert row["max_drawdown_pct"] == 0.0
    assert row["trades"] == 1
    assert row["round_trips"] == 0
    assert row["win_rate_pct"] is None


def test_pairs_with_short_not_below_long_are_skipped():
    rows = sweep(CLOSES, [2, 4, 6], [4, 6], cash=1000)
    assert [(r["short"], r["long"]) for r in rows] == [(2, 4), (2, 6), (4, 6)]


def test_no_valid_pair_raises():
    with pytest.raises(ValueError, match="no .*pair"):
        sweep(CLOSES, [5, 6], [3, 5])


def test_duplicates_are_tried_once():
    assert len(sweep(CLOSES, [2, 2], [4, 4], cash=1000)) == 1


def test_sorted_by_return_then_short_then_long():
    rows = sweep(CLOSES, [3, 2], [12, 4], cash=1000)
    # (2,4) and (3,4) both return 14.2% with no drawdown; the others never trade.
    assert [(r["short"], r["long"]) for r in rows[:2]] == [(2, 4), (3, 4)]
    returns = [r["return_pct"] for r in rows]
    assert returns == sorted(returns, reverse=True)
    assert [(r["short"], r["long"]) for r in rows[2:]] == sorted((r["short"], r["long"]) for r in rows[2:])


def test_tie_break_prefers_smaller_drawdown(monkeypatch):
    class Fake:
        n_trades = 0
        n_round_trips = 0
        n_winning_round_trips = 0

        def __init__(self, ret, dd):
            self.return_pct = ret
            self.max_drawdown_pct = dd

    table = {(1, 2): Fake(5.0, -10.0), (1, 3): Fake(5.0, -2.0), (2, 3): Fake(5.0, -2.0), (1, 4): Fake(7.0, -50.0), (2, 4): Fake(1.0, 0.0)}
    monkeypatch.setattr(sweep_module, "run_backtest", lambda closes, initial_cash, short, long, fee, fee_pct: table[(short, long)])
    rows = sweep([1.0], [1, 2], [2, 3, 4])
    assert [(r["short"], r["long"]) for r in rows] == [(1, 4), (1, 3), (2, 3), (1, 2), (2, 4)]


def test_win_rate_with_round_trips():
    # Buy then sell at a lower price: one losing round trip, win rate 0.
    closes = [10.0, 10.0, 12.0, 12.0, 6.0, 6.0, 6.0]
    rows = sweep(closes, [1], [2], cash=1000)
    assert rows[0]["round_trips"] == 1
    assert rows[0]["win_rate_pct"] == 0.0


# ------------------------------------------------------------------ CLI


def test_cli_prints_table_buy_and_hold_and_footer(tmp_path, capsys):
    path = write_prices(tmp_path)
    assert main([path, "--short", "2,3", "--long", "4,12", "--cash", "1000"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("Sweep: 4 SMA crossover pairs on 12 bars")
    assert lines[1].split() == ["Short", "Long", "Return", "Max", "DD", "Trades", "RoundTrips", "Win", "rate"]
    assert lines[2].split()[:3] == ["2", "4", "+14.20%"]
    # Buy and hold: 100 shares at 10 = 1000 cash used fully, last close 16 -> +60%.
    assert "Buy & hold: +60.00% return" in out
    assert lines[-2] == OVERFIT_WARNING
    assert lines[-1] == DISCLAIMER


def test_overfit_line_text():
    assert OVERFIT_WARNING == "Best in-sample parameters overfit; check them on data they were not chosen on."


def test_cli_default_cash_matches_cli_module(tmp_path, capsys):
    assert main([write_prices(tmp_path), "--short", "2", "--long", "4"]) == 0
    assert f"start cash {DEFAULT_CASH:,.2f}" in capsys.readouterr().out


def test_cli_top_limits_table_not_csv(tmp_path, capsys):
    path = write_prices(tmp_path)
    out_csv = tmp_path / "rows.csv"
    assert main([path, "--short", "2,3", "--long", "4,12", "--cash", "1000", "--top", "1", "--csv", str(out_csv)]) == 0
    out = capsys.readouterr().out
    table_rows = [l for l in out.splitlines() if l.split()[:1] in (["2"], ["3"])]
    assert len(table_rows) == 1
    assert "(showing the best 1 of 4)" in out
    with open(out_csv, newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 5


def test_cli_csv_content(tmp_path, capsys):
    path = write_prices(tmp_path)
    out_csv = tmp_path / "rows.csv"
    assert main([path, "--short", "2", "--long", "4,12", "--cash", "1000", "--csv", str(out_csv)]) == 0
    assert f"Wrote 2 rows to {out_csv}" in capsys.readouterr().out
    with open(out_csv, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["short", "long", "return_pct", "max_drawdown_pct", "trades", "round_trips", "win_rate_pct"]
    assert rows[1] == ["2", "4", "14.2000", "0.0000", "1", "0", ""]
    assert rows[2][:2] == ["2", "12"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--short", "a,b", "--long", "10"],
        ["--short", "5,", "--long", "10"],
        ["--short", "0", "--long", "10"],
        ["--short", "-3", "--long", "10"],
        ["--short", "5", "--long", "2.5"],
        ["--short", "5", "--long", ""],
        ["--short", "5"],
        ["--short", "10,20", "--long", "5,10"],
        ["--short", "2", "--long", "4", "--cash", "0"],
        ["--short", "2", "--long", "4", "--fee", "-1"],
        ["--short", "2", "--long", "4", "--fee-pct", "100"],
        ["--short", "2", "--long", "4", "--top", "0"],
    ],
)
def test_cli_usage_errors_exit_2(tmp_path, capsys, extra):
    with pytest.raises(SystemExit) as info:
        main([write_prices(tmp_path), *extra])
    assert info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_cli_missing_file_exit_1(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv"), "--short", "2", "--long", "4"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error:")
    assert captured.err.count("\n") == 1


def test_cli_no_close_column_exit_1(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("date,price\n2026-01-02,1\n")
    assert main([str(path), "--short", "2", "--long", "4"]) == 1
    assert "no 'close' column" in capsys.readouterr().err


def test_cli_no_rows_exit_1(tmp_path, capsys):
    path = tmp_path / "empty.csv"
    path.write_text("date,close\n")
    assert main([str(path), "--short", "2", "--long", "4"]) == 1
    assert capsys.readouterr().err == "No price rows found.\n"


def test_cli_refuses_to_overwrite_input(tmp_path, capsys):
    path = write_prices(tmp_path)
    before = Path(path).read_text()
    assert main([path, "--short", "2", "--long", "4", "--csv", path]) == 1
    captured = capsys.readouterr()
    assert "refuses to overwrite the input file" in captured.err
    assert captured.out == ""
    assert Path(path).read_text() == before


def test_cli_unwritable_csv_exit_1(tmp_path, capsys):
    path = write_prices(tmp_path)
    assert main([path, "--short", "2", "--long", "4", "--csv", str(tmp_path / "no_dir" / "out.csv")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: cannot write ")
    assert err.count("\n") == 1


def test_python_m_sweep(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "trading_assistant.sweep", write_prices(tmp_path), "--short", "2", "--long", "4"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-2:] == [OVERFIT_WARNING, DISCLAIMER]
