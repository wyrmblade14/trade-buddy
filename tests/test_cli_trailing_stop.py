"""``--trailing-stop PCT`` on the command line (``run_backtest(trail_pct=...)``).

8-bar candle file, --cash 500 --short 1 --long 2 (the series of
test_trailing_stop.py; bar 6's low is 10.0 rather than 10.2 because the
candle check needs low <= close, and every bar needs an open):

    bar  date        open  high   low  close
     0   2026-01-01  10    10.5   9.5   10
     1   2026-01-02   9.5   9.5   8.5    9
     2   2026-01-03   8.5   8.5   7.5    8
     3   2026-01-04   8.8   9.5   8.5    9     BUY signal
     4   2026-01-05  10.8  11.5  10.5   11     BUY 45 @ 11, cash 5
     5   2026-01-06  11.5  13    11.2   12     level 11 * 0.9 = 9.9: open and low above it
     6   2026-01-07  12.0  12.5  10.0   10     level 13 * 0.9 = 11.7: opens above it, low 10 reaches it
                                               -> SELL 45 @ 11.70 = 526.50, cash 531.50, trail
     7   2026-01-08   9     9     7.5    8

Gap variant (bar 6 opens at 11.0 <= 11.7): SELL 45 @ 11.00 = 495, cash 500.00, trail.

The expected text in the "unchanged" tests was captured from the command
before --trailing-stop existed (with COLUMNS=80 for the usage line).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import main

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

CANDLES = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.5,9.5,8.5,9,1000
2026-01-03,8.5,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,11.5,13,11.2,12,1000
2026-01-07,12.0,12.5,10.0,10,1000
2026-01-08,9,9,7.5,8,1000
"""
CANDLES_GAP = CANDLES.replace("2026-01-07,12.0,", "2026-01-07,11.0,")
CLOSES_ONLY = "date,close\n" + "".join(
    f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8])
)
BASE = ["--backtest", "--cash", "500", "--short", "1", "--long", "2"]

TRAIL_REPORT = """\
Bars:    8
Last:    8.00
Signal:  HOLD
RSI:     n/a
Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting
  Start cash:  500.00
  Trades:      2 (1 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash         5.00  signal
    #2   bar 6     SELL       45 @      11.70  value       526.50  cost     0.00  cash       531.50  trail
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       trail 10.00% below the highest high since entry
  Round trips: 1 completed, 1 made money (100%)
  Comparison              Strategy    Buy & hold
    End equity              531.50        400.00
    Return                  +6.30%       -20.00%
    Max drawdown            -2.48%       -33.33%
    Trades                       2             1
    Costs paid                0.00          0.00
  End cash:    531.50
  End shares:  0 @ 8.00
  End equity:  531.50
  Return:      +6.30%
Research aid only. Not financial advice.
"""

# Captured before --trailing-stop existed.
OLD_STOP_TARGET_REPORT = """\
Bars:    8
Last:    8.00
Signal:  HOLD
RSI:     n/a
Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting
  Start cash:  500.00
  Trades:      2 (1 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash         5.00  signal
    #2   bar 5     SELL       45 @      12.65  value       569.25  cost     0.00  cash       574.25  target
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       stop 10.00% below entry, target 15.00% above entry (stop wins if a bar touches both)
  Round trips: 1 completed, 1 made money (100%)
  Comparison              Strategy    Buy & hold
    End equity              574.25        400.00
    Return                 +14.85%       -20.00%
    Max drawdown             0.00%       -33.33%
    Trades                       2             1
    Costs paid                0.00          0.00
  End cash:    574.25
  End shares:  0 @ 8.00
  End equity:  574.25
  Return:      +14.85%
  Exported:    8 rows to E.csv
Research aid only. Not financial advice.
"""

OLD_STOP_TARGET_EXPORT = """\
bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason
0,2026-01-01,10.00,HOLD,,,,,,500.00,0,500.00,0.00,500.00,
1,2026-01-02,9.00,HOLD,,,,,,500.00,0,500.00,0.00,450.00,
2,2026-01-03,8.00,HOLD,,,,,,500.00,0,500.00,0.00,400.00,
3,2026-01-04,9.00,BUY,,,,,,500.00,0,500.00,0.00,450.00,
4,2026-01-05,11.00,HOLD,BUY,45,11.00,495.00,0.00,5.00,45,500.00,0.00,550.00,signal
5,2026-01-06,12.00,HOLD,SELL,45,12.65,569.25,0.00,574.25,0,574.25,0.00,600.00,target
6,2026-01-07,10.00,SELL,,,,,,574.25,0,574.25,0.00,500.00,
7,2026-01-08,8.00,HOLD,,,,,,574.25,0,574.25,0.00,400.00,
"""

OLD_PLAIN_EXPORT = """\
bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity
0,2026-01-01,10.00,HOLD,,,,,,500.00,0,500.00,0.00,500.00
1,2026-01-02,9.00,HOLD,,,,,,500.00,0,500.00,0.00,450.00
2,2026-01-03,8.00,HOLD,,,,,,500.00,0,500.00,0.00,400.00
3,2026-01-04,9.00,BUY,,,,,,500.00,0,500.00,0.00,450.00
4,2026-01-05,11.00,HOLD,BUY,45,11.00,495.00,0.00,5.00,45,500.00,0.00,550.00
5,2026-01-06,12.00,HOLD,,,,,,5.00,45,545.00,0.00,600.00
6,2026-01-07,10.00,SELL,,,,,,5.00,45,455.00,-16.51,500.00
7,2026-01-08,8.00,HOLD,SELL,45,8.00,360.00,0.00,365.00,0,365.00,-33.03,400.00
"""

OLD_NEEDS_BACKTEST_STDERR = """\
usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]
                             [--rsi-period RSI_PERIOD] [--backtest]
                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]
                             [--slippage PCT] [--position-size FRACTION]
                             [--stop-loss PCT] [--take-profit PCT]
                             [--export FILE] [--fill {close,open}]
                             [--resample {weekly,monthly}]
                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]
                             [--param KEY=VALUE] [--stats] [--config FILE]
                             [--json] [--chart] [--candles] [--scan FOLDER]
                             [--min-score N] [--top N] [--report FILE]
                             csv_path
trading_assistant.cli: error: --stop-loss only makes sense together with --backtest
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A working folder holding the candle files; the usage line is wrapped at 80 columns."""
    (tmp_path / "c8.csv").write_text(CANDLES)
    (tmp_path / "gap.csv").write_text(CANDLES_GAP)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    return tmp_path


def run_cli(cwd, *argv):
    """The real command: ``python -m trading_assistant.cli`` in a child process."""
    env = dict(os.environ, COLUMNS="80")
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.cli", *argv], capture_output=True, text=True, env=env, cwd=cwd
    )


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:  # parser.error exits with 2
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- the 8-bar case


def test_real_command_8_bar_report(folder):
    proc = run_cli(folder, "c8.csv", *BASE, "--trailing-stop", "10")
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert proc.stdout == TRAIL_REPORT


def test_export_has_reason_column(folder, capsys):
    code, out, err = run(["c8.csv", *BASE, "--trailing-stop", "10", "--export", "E.csv"], capsys)
    assert code == 0 and err == ""
    assert "  Exported:    8 rows to E.csv" in out
    lines = (folder / "E.csv").read_text().splitlines()
    assert lines[0].endswith(",buy_hold_equity,reason")
    assert lines[5] == "4,2026-01-05,11.00,HOLD,BUY,45,11.00,495.00,0.00,5.00,45,500.00,0.00,550.00,signal"
    assert lines[7] == "6,2026-01-07,10.00,SELL,SELL,45,11.70,526.50,0.00,531.50,0,531.50,-2.48,500.00,trail"
    assert [line.rsplit(",", 1)[1] for line in lines[1:]] == ["", "", "", "", "signal", "", "trail", ""]


def test_gap_below_the_level_sells_at_the_open(folder, capsys):
    code, out, _ = run(["gap.csv", *BASE, "--trailing-stop", "10"], capsys)
    assert code == 0
    assert "    #2   bar 6     SELL       45 @      11.00  value       495.00  cost     0.00  cash       500.00  trail" in out
    assert "  End equity:  500.00" in out


def test_works_next_to_stop_loss_and_take_profit(folder, capsys):
    code, out, _ = run(["c8.csv", *BASE, "--trailing-stop", "10", "--stop-loss", "5", "--take-profit", "20"], capsys)
    assert code == 0
    assert (
        "  Exits:       stop 5.00% below entry, trail 10.00% below the highest high since entry,"
        " target 20.00% above entry"
        " (the higher of stop and trail is used; it wins if a bar also touches the target)"
    ) in out.splitlines()
    assert "cash       531.50  trail" in out  # the trail (11.7) is above the stop (10.45)


# --------------------------------------------------------------------------- usage errors (exit 2)


@pytest.mark.parametrize("bad", ["0", "100", "-5", "150", "nan"])
def test_pct_out_of_range_exits_2(folder, capsys, bad):
    code, out, err = run(["c8.csv", *BASE, "--trailing-stop", bad], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == (
        f"trading_assistant.cli: error: --trailing-stop must be between 0 and 100 (both exclusive), got {bad}"
    )


def test_pct_not_a_number_exits_2(folder, capsys):
    code, _, err = run(["c8.csv", *BASE, "--trailing-stop", "abc"], capsys)
    assert code == 2
    assert err.splitlines()[-1] == "trading_assistant.cli: error: argument --trailing-stop: invalid float value: 'abc'"


def test_needs_backtest(folder, capsys):
    code, out, err = run(["c8.csv", "--trailing-stop", "10"], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == "trading_assistant.cli: error: --trailing-stop only makes sense together with --backtest"


@pytest.mark.parametrize("resample", [["--resample", "weekly"], ["--re", "monthly"]])
def test_not_with_resample(folder, capsys, resample):
    code, out, err = run(["c8.csv", *BASE, "--trailing-stop", "10", *resample], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == "trading_assistant.cli: error: --trailing-stop cannot be combined with --resample yet"


def test_not_with_scan(folder, capsys):
    code, out, err = run(["--scan", "scan", "--trailing-stop", "10"], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == "trading_assistant.cli: error: --trailing-stop cannot be combined with --scan"


def test_needs_a_candle_file_exits_1_like_stop_loss(folder, capsys):
    code, out, err = run(["closes.csv", *BASE, "--trailing-stop", "10"], capsys)
    stop_code, _, stop_err = run(["closes.csv", *BASE, "--stop-loss", "10"], capsys)
    assert code == stop_code == 1 and out == ""
    assert err == stop_err
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")


# --------------------------------------------------------------------------- help, and old commands unchanged


def test_help_describes_it(folder, capsys):
    code, out, _ = run(["--help"], capsys)
    assert code == 0
    text = " ".join(out.split())
    assert "--trailing-stop PCT with --backtest, sell when a bar's low reaches the highest high since entry less PCT%" in text
    assert "works next to --stop-loss and --take-profit" in text


def test_old_commands_print_the_same(folder):
    proc = run_cli(folder, "c8.csv", *BASE, "--stop-loss", "10", "--take-profit", "15", "--export", "E.csv")
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, OLD_STOP_TARGET_REPORT, "")
    assert (folder / "E.csv").read_text() == OLD_STOP_TARGET_EXPORT

    proc = run_cli(folder, "c8.csv", *BASE, "--export", "E.csv")  # no exits: no reason column
    assert proc.returncode == 0 and "Exits:" not in proc.stdout and " signal\n" not in proc.stdout
    assert (folder / "E.csv").read_text() == OLD_PLAIN_EXPORT

    # Shortened names that worked before still mean the same options.
    short = run_cli(folder, "c8.csv", *BASE, "--sto", "10", "--ta", "15", "--export", "E.csv")
    assert (short.returncode, short.stdout, short.stderr) == (0, OLD_STOP_TARGET_REPORT, "")
    alias = run_cli(folder, "c8.csv", *BASE, "--t", "15")
    assert alias.returncode == 0 and "  Exits:       target 15.00% above entry" in alias.stdout

    # Usage errors print the same usage line and message, with the same exit code.
    proc = run_cli(folder, "c8.csv", "--stop-loss", "10")
    assert (proc.returncode, proc.stdout, proc.stderr) == (2, "", OLD_NEEDS_BACKTEST_STDERR)
