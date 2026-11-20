"""``python -m trading_assistant`` must behave exactly like ``python -m trading_assistant.cli``."""

import os
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

CSV = "date,close\n" + "".join(f"2026-01-{day:02d},{10 + day % 4}\n" for day in range(1, 21))


def run_module(module, *argv):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", module, *argv], capture_output=True, text=True, env=env)


def test_same_output_and_exit_code_on_success(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(CSV)
    args = (str(path), "--short", "2", "--long", "5", "--backtest")
    short = run_module("trading_assistant", *args)
    full = run_module("trading_assistant.cli", *args)
    assert short.returncode == full.returncode == 0
    assert short.stdout == full.stdout
    assert "Signal:" in short.stdout
    assert short.stderr == full.stderr == ""


def test_same_exit_code_for_data_problem(tmp_path):
    path = str(tmp_path / "missing.csv")
    short = run_module("trading_assistant", path)
    full = run_module("trading_assistant.cli", path)
    assert short.returncode == full.returncode == 1
    assert short.stdout == full.stdout == ""
    assert short.stderr == full.stderr
    assert short.stderr.startswith("Error:")


def test_same_exit_code_for_usage_problem(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(CSV)
    args = (str(path), "--short", "9", "--long", "3")
    short = run_module("trading_assistant", *args)
    full = run_module("trading_assistant.cli", *args)
    assert short.returncode == full.returncode == 2
    assert "must be smaller than --long" in short.stderr
    assert "must be smaller than --long" in full.stderr
