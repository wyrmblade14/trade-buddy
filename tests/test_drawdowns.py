"""Tests for trading_assistant.drawdowns (functions and ``python -m`` command)."""

import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.drawdowns import drawdown_periods, format_table, main, top_drawdowns

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Bars:   0    1   2   3    4    5   6    7
CURVE = [100, 90, 80, 100, 110, 99, 110, 105]
# Episode 1: peak bar 0 (100), trough bar 2 (80), back to 100 on bar 3:
#   depth -20%, 2 bars down, 1 bar to recover.
# Bar 4 (110) sets a new peak. Episode 2: trough bar 5 (99), back on bar 6:
#   depth (99/110 - 1) = -10%, 1 bar down, 1 bar to recover.
# Episode 3: peak bar 6 (110), trough bar 7 (105), never recovered:
#   depth (105/110 - 1) = -4.5454...%, 1 bar down.
DATES = [f"2026-01-{i + 1:02d}" for i in range(8)]

# Closes that make a CLI run lose money: a rise then a long slide, so the
# 2/3 crossover buys high.
CLOSES = [10, 10, 10, 11, 12, 13, 12, 10, 8, 6, 5, 4]


def write_prices(tmp_path, closes=CLOSES, name="prices.csv"):
    path = tmp_path / name
    path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))
    return str(path)


def test_three_episodes_hand_checked():
    eps = drawdown_periods(CURVE, DATES)
    assert len(eps) == 3
    first, second, third = eps
    assert (first["peak_bar"], first["trough_bar"], first["recovery_bar"]) == (0, 2, 3)
    assert first["depth_pct"] == pytest.approx(-20.0)
    assert (first["length_bars"], first["recovery_bars"]) == (2, 1)
    assert (first["peak_date"], first["trough_date"], first["recovery_date"]) == (DATES[0], DATES[2], DATES[3])
    assert (second["peak_bar"], second["trough_bar"], second["recovery_bar"]) == (4, 5, 6)
    assert second["depth_pct"] == pytest.approx(-10.0)
    assert (third["peak_bar"], third["trough_bar"]) == (6, 7)
    assert third["depth_pct"] == pytest.approx((105 / 110 - 1) * 100)


def test_unrecovered_drawdown_has_no_recovery():
    third = drawdown_periods(CURVE, DATES)[-1]
    assert third["recovery_bar"] is None
    assert third["recovery_date"] is None
    assert third["recovery_bars"] is None
    assert third["length_bars"] == 1


def test_dates_are_optional():
    first = drawdown_periods(CURVE)[0]
    assert first["peak_date"] is None and first["trough_date"] is None and first["recovery_date"] is None


def test_date_count_must_match():
    with pytest.raises(ValueError, match="dates"):
        drawdown_periods(CURVE, DATES[:3])


def test_flat_rising_and_empty_curves_have_no_episodes():
    assert drawdown_periods([100.0] * 5) == []
    assert drawdown_periods([1, 2, 3]) == []
    assert drawdown_periods([]) == []
    assert top_drawdowns([100.0] * 5) == []


def test_deepest_is_the_max_drawdown():
    from trading_assistant.backtest import max_drawdown_pct

    assert top_drawdowns(CURVE)[0]["depth_pct"] == pytest.approx(max_drawdown_pct(CURVE))


def test_top_drawdowns_sorted_deepest_first_and_limited():
    eps = top_drawdowns(CURVE, DATES, n=2)
    assert [e["depth_pct"] for e in eps] == pytest.approx([-20.0, -10.0])
    assert len(top_drawdowns(CURVE, n=10)) == 3


def test_equal_depth_goes_to_earlier_peak():
    eps = top_drawdowns([100, 90, 100, 90, 100], n=2)
    assert [e["peak_bar"] for e in eps] == [0, 2]


def test_top_needs_positive_n():
    with pytest.raises(ValueError, match="at least 1"):
        top_drawdowns(CURVE, n=0)


def test_returning_to_the_peak_exactly_counts_as_recovery():
    (ep,) = drawdown_periods([100, 50, 100])
    assert ep["recovery_bar"] == 2
    assert ep["recovery_bars"] == 1


def test_table_marks_unrecovered_and_uses_bar_numbers_without_dates():
    lines = format_table(top_drawdowns(CURVE, n=3))
    assert len(lines) == 4
    assert "not recovered" in lines[3]
    assert "-20.00%" in lines[1]
    assert "bar 0" in lines[1]


# ---------------------------------------------------------------------- CLI


def test_cli_prints_table_and_exits_0(tmp_path, capsys):
    code = main([write_prices(tmp_path), "--short", "2", "--long", "3", "--top", "2"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Drawdowns of strategy sma_cross on 12 bars" in out
    assert "Depth" in out
    assert "%" in out
    assert DISCLAIMER in out


def test_cli_buy_and_hold_curve(tmp_path, capsys):
    # Buy and hold of 10 -> 4 with 10000 cash: 1000 shares, peak 13000 (bar 5),
    # trough 4000 (bar 11): -69.23%.
    code = main([write_prices(tmp_path), "--of", "buyhold", "--top", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "buy and hold" in out
    assert "-69.23%" in out
    assert "not recovered" in out


def test_cli_no_drawdown_message(tmp_path, capsys):
    code = main([write_prices(tmp_path, [10, 11, 12, 13]), "--of", "buyhold"])
    assert code == 0
    assert "No drawdowns" in capsys.readouterr().out


def test_cli_missing_file_exits_1(tmp_path, capsys):
    code = main([str(tmp_path / "nope.csv")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")
    assert captured.err.count("\n") == 1
    assert captured.out == ""


def test_cli_no_close_column_exits_1(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("date,price\n2026-01-01,5\n")
    assert main([str(path)]) == 1
    assert capsys.readouterr().err.startswith("Error:")


def test_cli_non_positive_price_exits_1(tmp_path, capsys):
    assert main([write_prices(tmp_path, [10, 0, 12])]) == 1
    assert capsys.readouterr().err.startswith("Error:")


@pytest.mark.parametrize(
    "extra",
    [
        ["--top", "0"],
        ["--cash", "0"],
        ["--fee", "-1"],
        ["--fee-pct", "100"],
        ["--strategy", "nope"],
        ["--param", "window"],
        ["--short", "5", "--long", "3"],
        ["--strategy", "breakout", "--short", "3"],
        ["--of", "sideways"],
    ],
)
def test_cli_usage_errors_exit_2(tmp_path, capsys, extra):
    with pytest.raises(SystemExit) as exc:
        main([write_prices(tmp_path)] + extra)
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_other_strategy_runs(tmp_path, capsys):
    code = main([write_prices(tmp_path), "--strategy", "breakout", "--param", "window=3"])
    assert code == 0
    assert "strategy breakout" in capsys.readouterr().out


def test_module_runs_as_command(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "trading_assistant.drawdowns", write_prices(tmp_path), "--of", "buyhold"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC_DIR)},
    )
    assert proc.returncode == 0
    assert "Depth" in proc.stdout
