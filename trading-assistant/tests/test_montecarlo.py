"""Tests for trading_assistant.montecarlo (function and ``python -m`` command)."""

import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.montecarlo import (
    BOOTSTRAP_NOTE,
    PERCENTILES,
    bootstrap_returns,
    main,
    percentile,
    returns_from_equity,
)

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CLOSES = [10, 10, 10, 11, 12, 13, 12, 10, 8, 6, 5, 4]


def write_prices(tmp_path, closes=CLOSES, name="prices.csv"):
    path = tmp_path / name
    path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))
    return str(path)


def test_percentile_interpolates_between_ranks():
    values = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 50) == pytest.approx(20.0)
    assert percentile(values, 25) == pytest.approx(10.0)
    assert percentile(values, 5) == pytest.approx(2.0)  # rank 0.2 between 0 and 10
    assert percentile(values, 95) == pytest.approx(38.0)  # rank 3.8 between 30 and 40
    assert percentile([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        percentile([], 50)


def test_returns_from_equity():
    assert returns_from_equity([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert returns_from_equity([100]) == []
    with pytest.raises(ValueError):
        returns_from_equity([100, 0, 5])


def test_constant_gain_gives_a_single_outcome():
    # Every draw is +10%; 2 bars: 1.1 * 1.1 = 1.21, so +21% on every path, no drawdown.
    out = bootstrap_returns([0.1], n_paths=5, seed=1, horizon=2)
    assert out["horizon"] == 2
    assert out["n_paths"] == 5
    for q in PERCENTILES:
        assert out["final_return_pct"][q] == pytest.approx(21.0)
        assert out["max_drawdown_pct"][q] == 0.0
    assert out["prob_loss_pct"] == 0.0


def test_constant_loss_always_loses():
    # -50% twice: 0.25, so -75% final and -75% drawdown on every path.
    out = bootstrap_returns([-0.5], n_paths=4, seed=1, horizon=2)
    assert out["final_return_pct"][50] == pytest.approx(-75.0)
    assert out["max_drawdown_pct"][5] == pytest.approx(-75.0)
    assert out["prob_loss_pct"] == 100.0


def test_flat_returns_are_not_a_loss():
    out = bootstrap_returns([0.0, 0.0, 0.0], n_paths=10, seed=3)
    assert out["horizon"] == 3
    assert out["final_return_pct"][50] == 0.0
    assert out["max_drawdown_pct"][50] == 0.0
    assert out["prob_loss_pct"] == 0.0


def test_same_seed_same_result_different_seed_differs():
    returns = [0.02, -0.03, 0.01, 0.04, -0.02, 0.005]
    a = bootstrap_returns(returns, n_paths=200, seed=42)
    b = bootstrap_returns(returns, n_paths=200, seed=42)
    c = bootstrap_returns(returns, n_paths=200, seed=43)
    assert a == b
    assert a != c


def test_percentiles_are_ordered():
    out = bootstrap_returns([0.02, -0.03, 0.01, 0.04, -0.02], n_paths=300, seed=5)
    finals = [out["final_return_pct"][q] for q in PERCENTILES]
    dds = [out["max_drawdown_pct"][q] for q in PERCENTILES]
    assert finals == sorted(finals)
    assert dds == sorted(dds)
    assert all(d <= 0 for d in dds)
    assert 0.0 <= out["prob_loss_pct"] <= 100.0


def test_input_list_is_not_changed():
    returns = [0.01, -0.01]
    bootstrap_returns(returns, n_paths=3, seed=1)
    assert returns == [0.01, -0.01]


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"per_bar_returns": []}, "at least one"),
        ({"per_bar_returns": [0.1], "n_paths": 0}, "n_paths"),
        ({"per_bar_returns": [0.1], "horizon": 0}, "horizon"),
        ({"per_bar_returns": [-1.0]}, "-100%"),
    ],
)
def test_bad_input_raises(kwargs, match):
    with pytest.raises(ValueError, match=match):
        bootstrap_returns(**kwargs)


# ---------------------------------------------------------------------- CLI


def test_cli_prints_report_and_exits_0(tmp_path, capsys):
    code = main([write_prices(tmp_path), "--short", "2", "--long", "3", "--paths", "50", "--seed", "7"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Bootstrap: 50 paths of 11 bars, seed 7" in out
    assert "Probability of a loss" in out
    assert BOOTSTRAP_NOTE in out
    assert "independent" in out and "does not predict the future" in out
    assert DISCLAIMER in out


def test_cli_same_seed_same_output(tmp_path, capsys):
    path = write_prices(tmp_path)
    main([path, "--paths", "40", "--seed", "9"])
    first = capsys.readouterr().out
    main([path, "--paths", "40", "--seed", "9"])
    assert capsys.readouterr().out == first


def test_cli_missing_file_exits_1(tmp_path, capsys):
    code = main([str(tmp_path / "nope.csv")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")
    assert captured.err.count("\n") == 1


def test_cli_single_row_exits_1(tmp_path, capsys):
    assert main([write_prices(tmp_path, [10])]) == 1
    assert capsys.readouterr().err.startswith("Error:")


def test_cli_non_positive_price_exits_1(tmp_path, capsys):
    assert main([write_prices(tmp_path, [10, -1, 12])]) == 1
    assert capsys.readouterr().err.startswith("Error:")


def test_cli_flat_prices_work(tmp_path, capsys):
    assert main([write_prices(tmp_path, [10] * 8), "--paths", "10"]) == 0
    assert "Probability of a loss: 0.0%" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra",
    [
        ["--paths", "0"],
        ["--seed", "abc"],
        ["--cash", "-5"],
        ["--fee", "-1"],
        ["--fee-pct", "150"],
        ["--strategy", "nope"],
        ["--param", "x=1"],
        ["--short", "9", "--long", "3"],
    ],
)
def test_cli_usage_errors_exit_2(tmp_path, capsys, extra):
    with pytest.raises(SystemExit) as exc:
        main([write_prices(tmp_path)] + extra)
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_module_runs_as_command(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "trading_assistant.montecarlo", write_prices(tmp_path), "--paths", "20"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC_DIR)},
    )
    assert proc.returncode == 0
    assert BOOTSTRAP_NOTE in proc.stdout
