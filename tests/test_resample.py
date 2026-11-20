"""Tests for trading_assistant.resample and the cli --resample option."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import main
from trading_assistant.resample import resample

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def test_weekly_groups_by_iso_week():
    # 2026-01-05 is a Monday. Week of Jan 5: Mon-Wed; week of Jan 12: Mon, Fri.
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-12", "2026-01-16"]
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert resample(dates, closes, "weekly") == (["2026-01-07", "2026-01-16"], [3.0, 5.0])


def test_weekly_week_split_by_weekend_gap():
    # Friday and the next Monday are different weeks.
    dates = ["2026-01-08", "2026-01-09", "2026-01-12"]
    assert resample(dates, [1.0, 2.0, 3.0], "weekly") == (["2026-01-09", "2026-01-12"], [2.0, 3.0])


def test_weekly_iso_week_one_starts_in_late_december():
    # 2025-12-29 (Mon) belongs to ISO week 1 of 2026, together with 2026-01-02.
    dates = ["2025-12-26", "2025-12-29", "2025-12-31", "2026-01-02", "2026-01-05"]
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert resample(dates, closes, "weekly") == (
        ["2025-12-26", "2026-01-02", "2026-01-05"],
        [1.0, 4.0, 5.0],
    )


def test_weekly_same_week_number_in_different_years_is_not_merged():
    # 2024-01-03 and 2025-01-01 are both ISO week 1, of different years.
    assert resample(["2024-01-03", "2025-01-01"], [1.0, 2.0], "weekly") == (
        ["2024-01-03", "2025-01-01"],
        [1.0, 2.0],
    )


def test_monthly_groups_by_month():
    dates = ["2026-01-02", "2026-01-30", "2026-02-02", "2026-02-27", "2026-03-02"]
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert resample(dates, closes, "monthly") == (
        ["2026-01-30", "2026-02-27", "2026-03-02"],
        [2.0, 4.0, 5.0],
    )


def test_monthly_year_boundary_and_same_month_other_year():
    dates = ["2025-12-30", "2025-12-31", "2026-01-02", "2026-12-01"]
    closes = [1.0, 2.0, 3.0, 4.0]
    assert resample(dates, closes, "monthly") == (
        ["2025-12-31", "2026-01-02", "2026-12-01"],
        [2.0, 3.0, 4.0],
    )


def test_empty_input_gives_empty_output():
    assert resample([], [], "weekly") == ([], [])


def test_single_bar_is_unchanged():
    assert resample(["2026-01-05"], [7.5], "monthly") == (["2026-01-05"], [7.5])


def test_unknown_period():
    with pytest.raises(ValueError, match="unknown period 'daily'"):
        resample(["2026-01-05"], [1.0], "daily")


def test_unparseable_date_names_row():
    with pytest.raises(ValueError, match=r"row 3: invalid date 'yesterday'"):
        resample(["2026-01-05", "2026-01-06", "yesterday"], [1.0, 2.0, 3.0], "weekly")


def test_empty_date_names_row():
    with pytest.raises(ValueError, match=r"row 1: invalid date ''"):
        resample([""], [1.0], "weekly")


def test_impossible_date_names_row():
    with pytest.raises(ValueError, match=r"row 2: invalid date '2026-02-30'"):
        resample(["2026-02-27", "2026-02-30"], [1.0, 2.0], "monthly")


def test_repeated_date_names_row():
    with pytest.raises(ValueError, match=r"row 2: date 2026-01-05 is not after"):
        resample(["2026-01-05", "2026-01-05"], [1.0, 2.0], "weekly")


def test_descending_date_names_row():
    with pytest.raises(ValueError, match=r"row 3: date 2026-01-06 is not after the previous date 2026-01-07"):
        resample(["2026-01-05", "2026-01-07", "2026-01-06"], [1.0, 2.0, 3.0], "weekly")


# ------------------------------------------------------------------ CLI


def write(tmp_path, text, name="prices.csv"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


# Mon-Wed of one week, Mon-Tue of the next: weekly closes are 12 and 20.
DAILY = "date,close\n2026-01-05,10\n2026-01-06,11\n2026-01-07,12\n2026-01-12,19\n2026-01-13,20\n"


def test_cli_resample_weekly(tmp_path, capsys):
    assert main([write(tmp_path, DAILY), "--resample", "weekly"]) == 0
    out = capsys.readouterr().out
    assert "Bars:    2\n" in out
    assert "Last:    20.00\n" in out


def test_cli_resample_monthly_backtest_uses_resampled_bars(tmp_path, capsys):
    text = "date,close\n2026-01-02,10\n2026-01-30,12\n2026-02-27,14\n2026-03-31,16\n"
    assert main([write(tmp_path, text), "--resample", "monthly", "--backtest", "--short", "1", "--long", "2"]) == 0
    out = capsys.readouterr().out
    assert "Bars:    3\n" in out  # four daily rows, January's two merge into one
    assert "End shares:  0 @ 16.00" in out


def test_cli_without_flag_is_unchanged(tmp_path, capsys):
    assert main([write(tmp_path, DAILY)]) == 0
    assert "Bars:    5\n" in capsys.readouterr().out


def test_cli_resample_needs_date_column(tmp_path, capsys):
    assert main([write(tmp_path, "close\n1\n2\n"), "--resample", "weekly"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: --resample needs a 'date' column")
    assert captured.err.count("\n") == 1


def test_cli_resample_bad_date_is_data_problem(tmp_path, capsys):
    text = "date,close\n2026-01-05,1\nnope,2\n"
    assert main([write(tmp_path, text), "--resample", "weekly"]) == 1
    err = capsys.readouterr().err
    assert "row 2: invalid date 'nope'" in err
    assert err.count("\n") == 1


def test_cli_resample_bad_choice_is_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        main([write(tmp_path, DAILY), "--resample", "daily"])
    assert info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_resample_python_m(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "trading_assistant.cli", write(tmp_path, DAILY), "--resample", "weekly"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "Bars:    2\n" in result.stdout
