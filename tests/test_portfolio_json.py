"""Tests for ``python -m trading_assistant.portfolio FOLDER --json``.

Uses the 8-bar two-file example; expected values are worked out by hand (see
test_portfolio_summary.py). The disclaimer is taken from cli.DISCLAIMER.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.portfolio import run_portfolio, summarize

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
A_CLOSES = [10, 9, 8, 9, 11, 12, 10, 8]
B_CLOSES = [20, 20, 19, 21, 22, 20, 18, 17]
SETTINGS = ["--short", "1", "--long", "2", "--cash", "1000"]
BAD_REASON = "BAD.csv line 3: invalid close value 'abc' (expected a number like 101.5)"

# Hand-worked summary of the 8-bar example (short 1, long 2, cash 1000, no fees):
#   portfolio 1000 1000 1000 1000 1000 1001 867 777
#   return (777 - 1000) / 1000 = -22.3 %; drawdown (777 - 1001) / 1001 = -22.3776... %
#   buy & hold A 400 + B 425 = 825 -> -17.5 %; worst drawdown A (365 - 545) / 545 = -33.0275... %
#   A -27 % (B&H -20 %), B -17.6 % (B&H -15 %), 2 trades each, 8 bars used, 0 lost
HAND_SUMMARY = {
    "short": 1,
    "long": 2,
    "fee": 0.0,
    "fee_pct": 0.0,
    "start_date": "2026-01-02",
    "end_date": "2026-01-13",
    "shared_dates": 8,
    "initial_cash": 1000.0,
    "final_equity": 777.0,
    "return_pct": pytest.approx(-22.3),
    "max_drawdown_pct": pytest.approx(-224 / 1001 * 100),
    "buy_hold_return_pct": pytest.approx(-17.5),
    "worst_symbol_drawdown": {"symbol": "A", "max_drawdown_pct": pytest.approx(-180 / 545 * 100)},
    "symbols": [
        {"symbol": "A", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-27.0),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-20.0)},
        {"symbol": "B", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-17.6),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-15.0)},
    ],
}

# The text report of the same run, unchanged by --json existing.
TEXT = [
    "Portfolio: 2 symbols, cash split equally, SMA 1/2 crossover, fee 0.00 + 0.00%, on the dates every file shares",
    "Dates: 2026-01-02 to 2026-01-13 (8 shared dates)",
    "Cash: 1,000.00  Final equity: 777.00",
    "Return: -22.30%  Max drawdown: -22.38%  Buy & hold (equal weight): -17.50%",
    "Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold",
    "A               8          0  -27.00%       2   -20.00%",
    "B               8          0  -17.60%       2   -15.00%",
    "Worst single-symbol drawdown: -33.03% (A)",
]


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


def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.portfolio", *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )


def _only_json(stdout):
    """The one JSON object on stdout; fails if anything else is printed."""
    data, end = json.JSONDecoder().raw_decode(stdout)
    assert stdout[end:] == "\n"
    return data


def test_8_bar_example_json(tmp_path):
    proc = _run(_example(tmp_path), *SETTINGS, "--json")
    assert proc.returncode == 0
    assert proc.stderr == ""
    data = _only_json(proc.stdout)
    assert list(data) == ["summary", "skipped", "disclaimer"]
    assert data["summary"] == HAND_SUMMARY
    assert data["skipped"] == []
    assert data["disclaimer"] == DISCLAIMER


def test_summary_is_the_summarize_dict_as_it_is(tmp_path):
    # Exactly equal (no approx) to summarize() run in-process on the same data.
    proc = _run(_example(tmp_path), *SETTINGS, "--json")
    tables = {"A": (DATES, [float(c) for c in A_CLOSES]), "B": (DATES, [float(c) for c in B_CLOSES])}
    assert _only_json(proc.stdout)["summary"] == summarize(run_portfolio(tables, cash=1000, short=1, long=2))


def test_numbers_are_not_rounded(tmp_path):
    summary = _only_json(_run(_example(tmp_path), *SETTINGS, "--json").stdout)["summary"]
    # -224 / 1001 * 100 = -22.377622377...; the text shows -22.38, the JSON keeps every digit.
    assert summary["max_drawdown_pct"] == pytest.approx(-22.377622377622377, abs=1e-12)
    assert summary["max_drawdown_pct"] != round(summary["max_drawdown_pct"], 2)
    worst = summary["worst_symbol_drawdown"]["max_drawdown_pct"]
    assert worst == pytest.approx(-33.02752293577982, abs=1e-12)
    assert worst != round(worst, 2)


def test_skipped_file_is_listed_with_file_and_reason(tmp_path):
    folder = _example(tmp_path, **{"BAD.csv": "date,close\n2026-01-02,30\n2026-01-05,abc\n"})
    proc = _run(folder, *SETTINGS, "--json")
    assert proc.returncode == 0
    assert proc.stderr == ""
    data = _only_json(proc.stdout)
    assert data["skipped"] == [{"file": "BAD.csv", "reason": BAD_REASON}]
    assert data["summary"] == HAND_SUMMARY
    assert data["disclaimer"] == DISCLAIMER


def test_text_output_is_unchanged_without_json(tmp_path):
    folder = _example(tmp_path, **{"BAD.csv": "date,close\n2026-01-02,30\n2026-01-05,abc\n"})
    proc = _run(folder, *SETTINGS)
    assert proc.returncode == 0
    assert proc.stdout == "\n".join(TEXT + ["Skipped: 1", f"  {BAD_REASON}", DISCLAIMER]) + "\n"
    assert proc.stderr == ""


# Each error case: (folder files, extra args, exit code). None for files means a missing folder.
ERRORS = {
    "missing folder": (None, SETTINGS, 1),
    "no csv files": ({"notes.txt": "hello\n"}, SETTINGS, 1),
    "fewer than 2 usable": ({"A.csv": _csv(DATES, A_CLOSES), "BAD.csv": "date,close\n2026-01-02,abc\n"}, SETTINGS, 1),
    "too few shared dates": ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)},
                             ["--short", "1", "--long", "7"], 1),
    "duplicate date": ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES[:2] + DATES[1:], [20] + B_CLOSES)},
                       SETTINGS, 1),
    "short not below long": ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)},
                             ["--short", "3", "--long", "2"], 2),
    "cash 0": ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)}, ["--cash", "0"], 2),
    "negative fee": ({"A.csv": _csv(DATES, A_CLOSES), "B.csv": _csv(DATES, B_CLOSES)}, ["--fee", "-1"], 2),
}


@pytest.mark.parametrize("case", list(ERRORS))
def test_errors_are_the_same_with_json(tmp_path, case):
    files, args, code = ERRORS[case]
    folder = tmp_path / "nope" if files is None else _folder(tmp_path, files)
    plain = _run(folder, *args)
    with_json = _run(folder, *args, "--json")
    assert plain.returncode == with_json.returncode == code
    assert plain.stdout == with_json.stdout == ""
    assert with_json.stderr == plain.stderr
    assert "Traceback" not in with_json.stderr
    if code == 1:
        assert with_json.stderr.startswith("Error: ") and with_json.stderr.count("\n") == 1
