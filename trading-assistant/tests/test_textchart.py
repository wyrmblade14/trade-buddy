"""Tests for the plain-text chart (trading_assistant.textchart) and the --chart flag."""

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.cli import analyse, main
from trading_assistant.textchart import line_chart


def test_rising_three_bars_exact_text():
    # lo=1, hi=3, height 3: rows 0, 1 (0.5 * 2 = 1) and 2 from the bottom.
    assert line_chart([1, 2, 3], width=60, height=3) == [
        "3.00 |  *",
        "     | *",
        "1.00 |*",
        "     +---",
    ]


def test_flat_series_sits_on_the_middle_row():
    assert line_chart([5, 5, 5], width=10, height=3) == [
        "5.00 |",
        "     |***",
        "5.00 |",
        "     +---",
    ]


def test_single_value_is_flat():
    assert line_chart([7.5], width=10, height=3) == ["7.50 |", "     |*", "7.50 |", "     +-"]


def test_markers_replace_the_star():
    assert line_chart([1, 2, 3], width=60, height=3, markers={0: "B", 2: "S"}) == [
        "3.00 |  S",
        "     | *",
        "1.00 |B",
        "     +---",
    ]


def test_downsample_takes_last_value_of_each_bucket():
    # width 3 over 6 bars: buckets (0,1) (2,3) (4,5) give 2, 4, 6.
    assert line_chart([1, 2, 3, 4, 5, 6], width=3, height=3) == [
        "6.00 |  *",
        "     | *",
        "2.00 |*",
        "     +---",
    ]


def test_marker_goes_to_the_column_of_its_bucket():
    # bar 3 is in the middle bucket, so the S replaces the middle star.
    lines = line_chart([1, 2, 3, 4, 5, 6], width=3, height=3, markers={3: "S"})
    assert lines[1] == "     | S"


def test_later_marker_wins_in_a_shared_column():
    lines = line_chart([1, 2, 3, 4, 5, 6], width=3, height=3, markers={2: "B", 3: "S"})
    assert lines[1] == "     | S"


def test_labels_are_padded_to_the_wider_one():
    lines = line_chart([9.5, 100.25], width=5, height=2)
    assert lines == ["100.25 | *", "  9.50 |*", "       +--"]


def test_default_size_is_sixty_by_twelve():
    lines = line_chart(list(range(200)))
    assert len(lines) == 12 + 1
    assert lines[-1] == "       +" + "-" * 60
    assert lines[0].startswith("199.00 |")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"values": []},
        {"values": [1.0, float("nan")]},
        {"values": [1.0, float("inf")]},
        {"values": [1.0], "width": 0},
        {"values": [1.0], "height": 1},
        {"values": [1.0, 2.0], "markers": {2: "B"}},
        {"values": [1.0, 2.0], "markers": {-1: "B"}},
        {"values": [1.0, 2.0], "markers": {0: "BUY"}},
    ],
)
def test_bad_input_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        line_chart(**kwargs)


# --------------------------------------------------------------------------- --chart


def write_prices(path, closes):
    path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))
    return str(path)


def test_chart_flag_prints_chart_after_report(tmp_path, capsys):
    path = write_prices(tmp_path / "p.csv", [1, 2, 3])
    assert main([path, "--short", "1", "--long", "2", "--chart"]) == 0
    lines = capsys.readouterr().out.splitlines()
    report, _ = analyse([1.0, 2.0, 3.0], short=1, long=2)
    assert lines == report + ["Chart:   close, 3 bars"] + line_chart([1, 2, 3], 60, 12) + [
        "Research aid only. Not financial advice."
    ]


def test_chart_marks_backtest_fills(tmp_path, capsys):
    # A triangle wave (up 10, down 10, ...) so the 3/6 crossover fires both ways.
    closes = [float(100 + min(i % 20, 20 - i % 20)) for i in range(60)]
    path = write_prices(tmp_path / "p.csv", closes)
    assert main([path, "--backtest", "--short", "3", "--long", "6", "--chart"]) == 0
    out = capsys.readouterr().out.splitlines()
    result = run_backtest(closes, short=3, long=6)
    assert result.n_buys >= 1 and result.n_sells >= 1
    marks = {t.bar: "B" if t.side == "BUY" else "S" for t in result.trades}
    start = out.index("Chart:   close, 60 bars, B = buy, S = sell")
    assert out[start + 1 : start + 14] == line_chart(closes, 60, 12, marks)
    grid = "".join(out[start + 1 : start + 13])
    assert grid.count("B") == result.n_buys and grid.count("S") == result.n_sells


def test_without_chart_output_has_no_chart(tmp_path, capsys):
    path = write_prices(tmp_path / "p.csv", [1, 2, 3])
    assert main([path, "--short", "1", "--long", "2"]) == 0
    assert "Chart:" not in capsys.readouterr().out
