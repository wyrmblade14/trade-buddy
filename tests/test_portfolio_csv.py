"""Tests for ``python -m trading_assistant.portfolio FOLDER --csv OUT``.

Expected rows are worked out by hand. Every money cell is rounded to 2
decimals on its own, so the portfolio cell is the true summed equity to the
cent and may differ by at most a cent from the sum of the rounded symbol cells.
"""

import csv
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from trading_assistant import portfolio
from trading_assistant.cli import DISCLAIMER

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
A_CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]
B_CLOSES = [20, 20, 19, 21, 22, 20, 18, 17]
C_CLOSES = [30, 29, 31, 33, 32, 30, 31, 35]
SETTINGS = ["--short", "1", "--long", "2", "--cash", "1000"]
BAD = "date,close\n2026-01-02,30\n2026-01-05,abc\n"

# 8-bar example, 500 each (see test_portfolio_run.py):
#   A equity 500 500 500 500 500 545 455 365, B equity 500 500 500 500 500 456 412 412
EIGHT_BAR_ROWS = [
    ["date", "portfolio", "A", "B"],
    ["2026-01-02", "1000.00", "500.00", "500.00"],
    ["2026-01-05", "1000.00", "500.00", "500.00"],
    ["2026-01-06", "1000.00", "500.00", "500.00"],
    ["2026-01-07", "1000.00", "500.00", "500.00"],
    ["2026-01-08", "1000.00", "500.00", "500.00"],
    ["2026-01-09", "1001.00", "545.00", "456.00"],
    ["2026-01-12", "867.00", "455.00", "412.00"],
    ["2026-01-13", "777.00", "365.00", "412.00"],
]

# Three symbols, cash 1000 -> 1000/3 = 333.333... each (short 1, long 2).
#   A: buy bar 4 @ 11: 30 shares = 330, cash 3.333; sell bar 7 @ 8
#      333.33 x5, 3.333+360 = 363.33, 3.333+300 = 303.33, 3.333+240 = 243.33
#   B: buy bar 4 @ 22: 15 shares = 330, cash 3.333; sell bar 6 @ 18
#      333.33 x5, 3.333+300 = 303.33, 3.333+270 = 273.33, 273.33
#   C: 30 29 31 33 32 30 31 35; BUY on bar 2 (31 > 30), filled bar 3 @ 33:
#      10 shares = 330, cash 3.333; SELL on bar 4 (32 < 32.5), filled bar 5 @ 30
#      -> cash 303.333; BUY on bar 6 (31 > 30.5), filled bar 7 @ 35: 8 shares
#      333.33 x4, 3.333+320 = 323.33, 303.33, 303.33, 23.333+280 = 303.33
#   Portfolio: the cash parts add to 10 exactly, so 1000, ..., 990, 970, 880, 820.
# The three symbol cells add to 999.99 on the first row, the portfolio cell
# says 1000.00: each cell is correctly rounded on its own.
THREE_ROWS = [
    ["date", "portfolio", "A", "B", "C"],
    ["2026-01-02", "1000.00", "333.33", "333.33", "333.33"],
    ["2026-01-05", "1000.00", "333.33", "333.33", "333.33"],
    ["2026-01-06", "1000.00", "333.33", "333.33", "333.33"],
    ["2026-01-07", "1000.00", "333.33", "333.33", "333.33"],
    ["2026-01-08", "990.00", "333.33", "333.33", "323.33"],
    ["2026-01-09", "970.00", "363.33", "303.33", "303.33"],
    ["2026-01-12", "880.00", "303.33", "273.33", "303.33"],
    ["2026-01-13", "820.00", "243.33", "273.33", "303.33"],
]

TEXT = "\n".join([
    "Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.00 + 0.00%, on the dates every file shares",
    "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
    "Cash: 1,000.00  Final equity: 777.00",
    "Return: -22.30%  Max drawdown: -22.38%  Buy & hold (equal weight): -17.50%",
    "Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold",
    "A               8          0  -27.00%       2   -20.00%",
    "B               8          0  -17.60%       2   -15.00%",
    "Worst single-symbol drawdown: -33.03% (A)",
    DISCLAIMER,
]) + "\n"


def _csv(dates, closes):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(dates, closes))


def _folder(tmp_path, files):
    folder = tmp_path / "prices"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text)
    return folder


def _example(tmp_path, **extra):
    return _folder(tmp_path, {"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES), **extra})


def _run(*args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.portfolio", *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def _read(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def _cents(text):
    return Decimal(text)


def _assert_exit_1(proc):
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr.startswith("Error: ") and proc.stderr.count("\n") == 1
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------- writing


def test_8_bar_example_csv(tmp_path):
    out = tmp_path / "equity.csv"
    proc = _run(_example(tmp_path), *SETTINGS, "--csv", out)
    assert proc.returncode == 0
    assert proc.stdout == TEXT  # normal output unchanged, no "Wrote" line
    assert proc.stderr == ""
    rows = _read(out)
    assert rows[1] == ["2026-01-02", "1000.00", "500.00", "500.00"]
    assert rows[-1] == ["2026-01-13", "777.00", "365.00", "412.00"]
    assert rows == EIGHT_BAR_ROWS
    for row in rows[1:]:
        assert _cents(row[1]) == _cents(row[2]) + _cents(row[3])
    assert out.read_bytes().count(b"\r") == 0  # plain "\n" line endings, as walk-forward's CSV


def test_three_symbols_portfolio_is_the_sum_to_the_cent(tmp_path):
    folder = _example(tmp_path, **{"C.csv": _csv(DATES, C_CLOSES)})
    out = tmp_path / "equity.csv"
    proc = _run(folder, *SETTINGS, "--csv", out)
    assert proc.returncode == 0
    rows = _read(out)
    assert rows == THREE_ROWS
    for row in rows[1:]:
        portfolio_cell = _cents(row[1])
        symbol_sum = sum(_cents(cell) for cell in row[2:])
        # Four cells each rounded by less than half a cent: at most 1 cent apart.
        assert abs(portfolio_cell - symbol_sum) <= Decimal("0.01")


def test_three_symbols_every_cell_is_correctly_rounded(tmp_path):
    # Each cell is the run's own value to the cent, not nudged to make sums match.
    folder = _example(tmp_path, **{"C.csv": _csv(DATES, C_CLOSES)})
    out = tmp_path / "equity.csv"
    _run(folder, *SETTINGS, "--csv", out)
    tables = {s: (DATES, [float(c) for c in closes]) for s, closes in
              (("A", A_CLOSES), ("B", B_CLOSES), ("C", C_CLOSES))}
    result = portfolio.run_portfolio(tables, cash=1000, short=1, long=2)
    rows = _read(out)
    for i, row in enumerate(rows[1:]):
        assert row[1] == f"{result.equity[i]:.2f}"
        assert row[2:] == [f"{result.results[s].equity_curve[i]:.2f}" for s in ("A", "B", "C")]


def test_odd_symbol_names_are_quoted(tmp_path):
    folder = _folder(tmp_path, {'x,"y".csv': _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)})
    out = tmp_path / "equity.csv"
    assert _run(folder, *SETTINGS, "--csv", out).returncode == 0
    assert out.read_text().split("\n")[0] == 'date,portfolio,B,"x,""y"""'
    assert _read(out)[0] == ["date", "portfolio", "B", 'x,"y"']


def test_csv_with_json(tmp_path):
    out = tmp_path / "equity.csv"
    folder = _example(tmp_path)
    plain_json = _run(folder, *SETTINGS, "--json")
    proc = _run(folder, *SETTINGS, "--json", "--csv", out)
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert proc.stdout == plain_json.stdout  # still exactly the one JSON object
    data, end = json.JSONDecoder().raw_decode(proc.stdout)
    assert proc.stdout[end:] == "\n"
    assert data["summary"]["final_equity"] == 777.0
    assert _read(out) == EIGHT_BAR_ROWS


def test_existing_output_file_is_replaced(tmp_path):
    out = tmp_path / "equity.csv"
    out.write_text("old contents\n")
    assert _run(_example(tmp_path), *SETTINGS, "--csv", out).returncode == 0
    assert _read(out) == EIGHT_BAR_ROWS


# ---------------------------------------------------------------- never overwrite an input


@pytest.mark.parametrize(
    "spelling",
    ["prices/A.csv", "prices/./A.csv", "prices/../prices/B.csv", "./prices//A.csv", "prices/BAD.csv", "prices/./BAD.csv"],
)
def test_same_file_as_an_input_exits_1_and_changes_nothing(tmp_path, spelling):
    # BAD.csv is skipped by the run but is still an input and must not be overwritten.
    folder = _example(tmp_path, **{"BAD.csv": BAD})
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    proc = _run("prices", *SETTINGS, "--csv", spelling, cwd=tmp_path)
    _assert_exit_1(proc)
    assert "--csv refuses to overwrite the input file" in proc.stderr
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before  # no change, no temp file


def test_symlink_to_an_input_exits_1(tmp_path):
    folder = _example(tmp_path)
    link = tmp_path / "link.csv"
    link.symlink_to(folder / "A.csv")
    before = (folder / "A.csv").read_bytes()
    proc = _run(folder, *SETTINGS, "--csv", link)
    _assert_exit_1(proc)
    assert (folder / "A.csv").read_bytes() == before


def test_hard_link_to_an_input_exits_1(tmp_path):
    folder = _example(tmp_path)
    link = tmp_path / "hard.csv"
    os.link(folder / "A.csv", link)
    before = (folder / "A.csv").read_bytes()
    proc = _run(folder, *SETTINGS, "--csv", link)
    _assert_exit_1(proc)
    assert (folder / "A.csv").read_bytes() == before


# ---------------------------------------------------------------- cannot write


def test_missing_output_folder_exits_1(tmp_path):
    out = tmp_path / "nope" / "equity.csv"
    proc = _run(_example(tmp_path), *SETTINGS, "--csv", out)
    _assert_exit_1(proc)
    assert proc.stderr == f"Error: cannot write {out}: folder {out.parent} does not exist\n"
    assert not out.parent.exists()


def test_output_that_is_a_folder_exits_1(tmp_path):
    out = tmp_path / "outdir"
    out.mkdir()
    proc = _run(_example(tmp_path), *SETTINGS, "--csv", out)
    _assert_exit_1(proc)
    assert proc.stderr == f"Error: cannot write {out}: it is a folder\n"
    assert list(out.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["outdir", "prices"]  # no temp file


def test_empty_csv_name_is_a_usage_error(tmp_path):
    proc = _run(_example(tmp_path), *SETTINGS, "--csv", "")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.endswith("trading_assistant.portfolio: error: --csv needs a file name\n")
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------- failures leave no file


@pytest.mark.parametrize(
    "files, args",
    [
        ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)}, ["--short", "1", "--long", "7"]),
        ({"A.csv": _csv(DATES, A_CLOSES), "BAD.csv": BAD}, SETTINGS),
        ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES[:2] + DATES[1:], [20] + B_CLOSES)}, SETTINGS),
    ],
    ids=["too few shared dates", "fewer than 2 usable", "duplicate date"],
)
def test_failing_run_leaves_no_csv(tmp_path, files, args):
    folder = _folder(tmp_path, files)
    out = tmp_path / "equity.csv"
    _assert_exit_1(_run(folder, *args, "--csv", out))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prices"]  # no OUT, no temp file


def test_failing_run_keeps_an_existing_output_untouched(tmp_path):
    folder = _folder(tmp_path, {"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)})
    out = tmp_path / "equity.csv"
    out.write_text("from an earlier run\n")
    _assert_exit_1(_run(folder, "--short", "1", "--long", "7", "--csv", out))
    assert out.read_text() == "from an earlier run\n"


def test_failed_write_removes_the_temporary_file(tmp_path, monkeypatch, capsys):
    # In-process: the rename onto OUT fails (as a full disk or lost folder would).
    folder = _example(tmp_path)
    out = tmp_path / "equity.csv"

    def broken_replace(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(portfolio.os, "replace", broken_replace)
    assert portfolio.main([str(folder), *SETTINGS, "--csv", str(out)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"Error: cannot write {out}: No space left on device\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prices"]
