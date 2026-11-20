"""Tests for the command line of trading_assistant.portfolio.

Runs ``python -m trading_assistant.portfolio`` for real on temporary folders.
The expected text is written out by hand; the disclaimer is taken from
cli.DISCLAIMER rather than retyped.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant import portfolio
from trading_assistant.cli import DISCLAIMER

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
A_CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]
B_CLOSES = [20, 20, 19, 21, 22, 20, 18, 17]

# The 8-bar example (figures worked out in test_portfolio_summary.py), run
# with --short 1 --long 2 --cash 1000.
REPORT = [
    "Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.00 + 0.00%, on the dates every file shares",
    "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
    "Cash: 1,000.00  Final equity: 777.00",
    "Return: -22.30%  Max drawdown: -22.38%  Buy & hold (equal weight): -17.50%",
    "Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold",
    "A               8          0  -27.00%       2   -20.00%",
    "B               8          0  -17.60%       2   -15.00%",
    "Worst single-symbol drawdown: -33.03% (A)",
]
SETTINGS = ["--short", "1", "--long", "2", "--cash", "1000"]


def _csv(dates, closes):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(dates, closes))


def _folder(tmp_path, files):
    folder = tmp_path / "prices"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text)
    return folder


def _example(tmp_path, **extra):
    """The 8-bar example as A.csv and B.csv, plus any ``extra`` files."""
    return _folder(tmp_path, {"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES), **extra})


def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.portfolio", *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------- exit 0


def test_8_bar_example_as_two_files(tmp_path):
    proc = _run(_example(tmp_path), *SETTINGS)
    assert proc.returncode == 0
    assert proc.stdout == "\n".join(REPORT + [DISCLAIMER]) + "\n"
    assert proc.stderr == ""


def test_bad_file_is_skipped_and_the_rest_carry_on(tmp_path):
    folder = _example(tmp_path, **{"BAD.csv": "date,close\n2026-01-02,30\n2026-01-05,abc\n"})
    proc = _run(folder, *SETTINGS)
    assert proc.returncode == 0
    assert proc.stdout == "\n".join(REPORT + [
        "Skipped: 1",
        "  BAD.csv line 3: invalid close value 'abc' (expected a number like 101.5)",
        DISCLAIMER,
    ]) + "\n"
    assert proc.stderr == ""


@pytest.mark.parametrize(
    "name, text, reason",
    [
        ("NOROWS.csv", "date,close\n", "NOROWS.csv: no price rows found"),
        ("NODATE.csv", "close\n30\n31\n", "NODATE.csv: no 'date' column; the portfolio lines files up by date"),
        ("BLANK.csv", "date,close\n2026-01-02,30\n,31\n", "BLANK.csv data row 2: blank date"),
        ("ZERO.csv", "date,close\n2026-01-02,30\n2026-01-05,0\n", "ZERO.csv data row 2: close must be positive, got 0"),
        ("A.CSV", _csv(DATES, A_CLOSES), "A.csv: symbol A is already read from A.CSV"),
    ],
)
def test_other_skip_reasons(tmp_path, name, text, reason):
    # Files are read in name order, so A.CSV comes before A.csv and A.csv is the repeat.
    folder = _example(tmp_path, **{name: text})
    if len(os.listdir(folder)) < 3:
        pytest.skip("case-insensitive file system: A.CSV and A.csv are the same file")
    proc = _run(folder, *SETTINGS)
    assert proc.returncode == 0
    lines = proc.stdout.split("\n")
    assert lines[-4:] == ["Skipped: 1", f"  {reason}", DISCLAIMER, ""]
    assert proc.stderr == ""


def test_unreadable_file_is_skipped(tmp_path, monkeypatch, capsys):
    # Runs main() in-process: file permissions cannot make a file unreadable
    # for root, so ``open`` inside portfolio fails for C.csv instead.
    folder = _example(tmp_path, **{"C.csv": _csv(DATES, A_CLOSES)})

    def fake_open(path, *args, **kwargs):
        if os.path.basename(path) == "C.csv":
            raise PermissionError(13, "Permission denied", path)
        return open(path, *args, **kwargs)

    monkeypatch.setattr(portfolio, "open", fake_open, raising=False)
    assert portfolio.main([str(folder), *SETTINGS]) == 0
    out = capsys.readouterr().out
    assert out.split("\n")[-4:] == ["Skipped: 1", "  C.csv: cannot read the file (Permission denied)", DISCLAIMER, ""]


def test_help_exits_0():
    proc = _run("--help")
    assert proc.returncode == 0
    assert proc.stdout.startswith("usage: trading_assistant.portfolio")
    assert "--fee-pct" in proc.stdout
    assert proc.stderr == ""


# ---------------------------------------------------------------- exit 1


def _assert_exit_1(proc, message):
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == f"Error: {message}\n"  # exactly one line
    assert "Traceback" not in proc.stderr


def test_missing_folder_exits_1(tmp_path):
    missing = tmp_path / "nope"
    _assert_exit_1(_run(missing, *SETTINGS), f"portfolio folder {missing} does not exist")


def test_folder_that_is_a_file_exits_1(tmp_path):
    path = tmp_path / "A.csv"
    path.write_text(_csv(DATES, A_CLOSES))
    _assert_exit_1(_run(path, *SETTINGS), f"portfolio folder {path} is not a folder")


def test_no_csv_files_exits_1(tmp_path):
    folder = _folder(tmp_path, {"notes.txt": "hello\n"})
    _assert_exit_1(_run(folder, *SETTINGS), f"no .csv files directly inside {folder}")


def test_fewer_than_two_usable_files_exits_1(tmp_path):
    folder = _folder(tmp_path, {"A.csv": _csv(DATES, A_CLOSES), "BAD.csv": "date,close\n2026-01-02,abc\n"})
    _assert_exit_1(
        _run(folder, *SETTINGS),
        f"only 1 of the 2 .csv files in {folder} could be used (1 skipped); a portfolio needs at least 2",
    )


def test_too_few_shared_dates_exits_1(tmp_path):
    # 8 shared dates; --long 7 needs long + 2 = 9.
    _assert_exit_1(
        _run(_example(tmp_path), "--short", "1", "--long", "7", "--cash", "1000"),
        "only 8 dates shared by all 2 symbols; need at least 9 (long window 7 + 2)",
    )


def test_duplicate_date_in_a_file_exits_1(tmp_path):
    dup = _csv(DATES[:2] + DATES[1:], [20] + B_CLOSES)  # 2026-01-05 twice
    folder = _folder(tmp_path, {"A.csv": _csv(DATES, A_CLOSES), "B.csv": dup})
    _assert_exit_1(_run(folder, *SETTINGS), "B: date '2026-01-05' appears more than once")


# ---------------------------------------------------------------- exit 2


@pytest.mark.parametrize(
    "args, message",
    [
        (["--short", "0", "--long", "2"], "--short must be at least 1"),
        (["--short", "1", "--long", "0"], "--long must be at least 1"),
        (["--short", "2", "--long", "2"], "--short (2) must be smaller than --long (2)"),
        (["--short", "3", "--long", "2"], "--short (3) must be smaller than --long (2)"),
        (["--cash", "0"], "--cash must be positive, got 0"),
        (["--cash", "-5"], "--cash must be positive, got -5"),
        (["--fee", "-1"], "--fee must not be negative, got -1"),
        (["--fee-pct", "-1"], "--fee-pct must be between 0 and 100 (exclusive), got -1"),
        (["--fee-pct", "100"], "--fee-pct must be between 0 and 100 (exclusive), got 100"),
        (["--cash", "inf"], "--cash must be a finite number, got inf"),
        (["--fee", "nan"], "--fee must be a finite number, got nan"),
        (["--fee", "inf"], "--fee must be a finite number, got inf"),
        (["--fee-pct", "nan"], "--fee-pct must be a finite number, got nan"),
    ],
)
def test_usage_errors_exit_2(tmp_path, args, message):
    proc = _run(_example(tmp_path), *args)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("usage: trading_assistant.portfolio")
    assert proc.stderr.endswith(f"trading_assistant.portfolio: error: {message}\n")
    assert "Traceback" not in proc.stderr
