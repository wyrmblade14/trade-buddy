"""Tests for the data summary (python -m trading_assistant.summary)."""

import math

from trading_assistant.summary import main, one_bar_changes, summarise

DISCLAIMER = "Research aid only. Not financial advice."


def write(tmp_path, text, name="p.csv"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_numbers_checked_by_hand(tmp_path, capsys):
    # Changes: 110/100 = +10%, 99/110 = -10%, 99/99 = 0%.
    # Returns 0.1, -0.1, 0: mean 0, sample variance (0.01 + 0.01) / 2 = 0.01, stdev 0.1.
    # Volatility = 0.1 * 15.8745 * 100 = 158.75%.
    path = write(
        tmp_path,
        "date,close\n2026-01-02,100\n2026-01-05,110\n2026-01-05,99\n2026-01-06,99\n",
    )
    assert main([path]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Rows:              4",
        "First date:        2026-01-02",
        "Last date:         2026-01-06",
        "Min close:         99.00",
        "Max close:         110.00",
        "Mean close:        102.00",
        "Largest rise:      +10.00% on 2026-01-05",
        "Largest fall:      -10.00% on 2026-01-05",
        "Repeated dates:    1",
        "Non-positive:      0",
        "Volatility (ann.): 158.75%",
        DISCLAIMER,
    ]


def test_volatility_value():
    info = summarise(["a", "b", "c", "d"], [100.0, 110.0, 99.0, 99.0])
    assert math.isclose(info["volatility_pct"], 0.1 * math.sqrt(252) * 100, rel_tol=1e-9)


def test_non_positive_closes_and_skipped_returns(tmp_path, capsys):
    # 10 -> 0 is -100%; the return from 0 to -5 is skipped (previous close not above zero).
    path = write(tmp_path, "date,close\n2026-01-02,10\n2026-01-03,0\n2026-01-04,-5\n")
    assert one_bar_changes([10.0, 0.0, -5.0]) == [(1, -100.0)]
    assert main([path]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "Non-positive:      2" in out
    assert "Largest rise:      none" in out
    assert "Largest fall:      -100.00% on 2026-01-03" in out
    assert "Volatility (ann.): n/a (fewer than 2 returns)" in out


def test_no_date_column(tmp_path, capsys):
    path = write(tmp_path, "close\n10\n12\n9\n")
    assert main([path]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1] == "First date:        n/a (no date column)"
    assert out[8] == "Repeated dates:    n/a (no date column)"
    assert out[6] == "Largest rise:      +20.00% on bar 2"
    assert out[7] == "Largest fall:      -25.00% on bar 3"


def test_single_row(tmp_path, capsys):
    path = write(tmp_path, "date,close\n2026-01-02,50\n")
    assert main([path]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Rows:              1"
    assert "Largest rise:      none" in out
    assert "Volatility (ann.): n/a (fewer than 2 returns)" in out


def test_does_not_report_calendar_gaps(tmp_path, capsys):
    # A week-long hole in the dates is not mentioned.
    path = write(tmp_path, "date,close\n2026-01-02,10\n2026-01-20,11\n")
    assert main([path]) == 0
    text = capsys.readouterr().out.lower()
    assert "gap" not in text and "missing" not in text and "holiday" not in text


def test_data_problems_exit_1(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 1
    assert capsys.readouterr().err.startswith("Error: ")
    assert main([write(tmp_path, "date,price\n2026-01-02,1\n", "a.csv")]) == 1
    assert "no 'close' column" in capsys.readouterr().err
    assert main([write(tmp_path, "date,close\n2026-01-02,abc\n", "b.csv")]) == 1
    assert "invalid close value" in capsys.readouterr().err
    assert main([write(tmp_path, "date,close\n", "c.csv")]) == 1
    captured = capsys.readouterr()
    assert captured.err == "No price rows found.\n" and captured.out == ""


def test_usage_problem_exits_2(capsys):
    import pytest

    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2
