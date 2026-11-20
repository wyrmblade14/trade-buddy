"""The ``trailing_stop`` config key (``[cli] trailing_stop = PCT``, like ``--trailing-stop PCT``).

It follows the rules of ``stop_loss`` and ``take_profit``: a number, used only
with --backtest (ignored otherwise), reads the price file as a candle file,
cannot be combined with --resample, must be above 0 and below 100, and a
--trailing-stop flag wins over it.

8-bar candle file (see test_cli_trailing_stop.py), cash 500, short 1, long 2:
    trail 10 %: BUY 45 @ 11 on bar 4; bar 6 level 13 * 0.9 = 11.7 -> SELL 45 @ 11.70, cash 531.50.
    trail 30 %: bar 6 level 13 * 0.7 = 9.1, low 10.0 stays above it; bar 7 opens at 9.0 <= 9.1
                -> SELL 45 @ 9.00 (the open) = 405, cash 410.00.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import main
from trading_assistant.config import ConfigError, load_config

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
CLOSES_ONLY = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
SETTINGS = "[cli]\nshort = 1\nlong = 2\ncash = 500\n"
TRAIL_CONFIG = SETTINGS + "trailing_stop = 10\n"
FLAGS = ["--backtest", "--cash", "500", "--short", "1", "--long", "2"]

# Captured from the command before the trailing_stop key existed.
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
Research aid only. Not financial advice.
"""

OLD_PLAIN_JSON = """\
{
  "bars": 8,
  "last_close": 8.0,
  "signal": "HOLD",
  "rsi": null,
  "rsi_label": null,
  "backtest": {
    "strategy": "sma_cross",
    "params": {
      "short": 1,
      "long": 2
    },
    "fill": "close",
    "start_cash": 500.0,
    "fee": 0.0,
    "fee_pct": 0.0,
    "slippage_pct": 0.0,
    "position_size": null,
    "stop_loss_pct": null,
    "take_profit_pct": null,
    "trades": 2,
    "buys": 1,
    "sells": 1,
    "fills": [
      {
        "bar": 4,
        "side": "BUY",
        "shares": 45,
        "price": 11.0,
        "value": 495.0,
        "cost": 0.0,
        "cash_after": 5.0,
        "reason": "signal"
      },
      {
        "bar": 7,
        "side": "SELL",
        "shares": 45,
        "price": 8.0,
        "value": 360.0,
        "cost": 0.0,
        "cash_after": 365.0,
        "reason": "signal"
      }
    ],
    "total_costs": 0.0,
    "round_trips": 1,
    "winning_round_trips": 0,
    "final_cash": 365.0,
    "final_position": 0,
    "final_price": 8.0,
    "final_equity": 365.0,
    "return_pct": -27.0,
    "max_drawdown_pct": -33.02752293577982,
    "benchmark": {
      "shares": 50,
      "final_cash": 0.0,
      "final_equity": 400.0,
      "return_pct": -20.0,
      "max_drawdown_pct": -33.33333333333333,
      "trades": 1,
      "total_costs": 0.0
    }
  },
  "disclaimer": "Research aid only. Not financial advice."
}
"""

OLD_STOP_LOSS_0_STDERR = """\
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
trading_assistant.cli: error: --stop-loss must be between 0 and 100 (both exclusive), got 0
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "c8.csv").write_text(CANDLES)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
    (tmp_path / "trail.ini").write_text(TRAIL_CONFIG)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def write_config(folder, text, name="t.ini"):
    (folder / name).write_text(text)
    return name


def run_cli(cwd, *argv, env_config=None):
    """The real command: ``python -m trading_assistant.cli`` in a child process."""
    env = dict(os.environ, COLUMNS="80")
    env.pop("TRADING_ASSISTANT_CONFIG", None)
    if env_config is not None:
        env["TRADING_ASSISTANT_CONFIG"] = env_config
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


# --------------------------------------------------------------------------- reading the key


@pytest.mark.parametrize("raw, value", [("10", 10.0), ("7.5", 7.5), (" 30 ", 30.0)])
def test_key_read_from_file_as_a_number(folder, raw, value):
    cli = load_config(write_config(folder, f"[cli]\ntrailing_stop = {raw}\n"))["cli"]
    assert cli == {"trailing_stop": value} and type(cli["trailing_stop"]) is float


@pytest.mark.parametrize(
    "raw, message",
    [
        ("10%", "t.ini line 3: trailing_stop needs a number, got '10%'"),
        ("ten", "t.ini line 3: trailing_stop needs a number, got 'ten'"),
        ("nan", "t.ini line 3: trailing_stop needs a finite number, got 'nan'"),
        ("inf", "t.ini line 3: trailing_stop needs a finite number, got 'inf'"),
    ],
)
def test_not_a_number_exits_1(folder, capsys, raw, message):
    name = write_config(folder, f"[cli]\nshort = 1\ntrailing_stop = {raw}\n")
    with pytest.raises(ConfigError, match="^" + re.escape(message) + "$"):
        load_config(name)
    code, out, err = run(["c8.csv", "--config", name, "--backtest"], capsys)
    assert (code, out, err) == (1, "", f"Error: {message}\n")


# --------------------------------------------------------------------------- the 8-bar case


@pytest.mark.parametrize("how", ["--config", "env"])
def test_8_bar_config_gives_the_same_result_as_the_flag(folder, how):
    if how == "--config":
        by_file = run_cli(folder, "c8.csv", "--config", "trail.ini", "--backtest")
    else:
        by_file = run_cli(folder, "c8.csv", "--backtest", env_config="trail.ini")
    by_flag = run_cli(folder, "c8.csv", *FLAGS, "--trailing-stop", "10")
    assert by_file.returncode == by_flag.returncode == 0
    assert by_file.stderr == by_flag.stderr == ""
    assert by_file.stdout == by_flag.stdout
    lines = by_file.stdout.splitlines()
    assert "  Exits:       trail 10.00% below the highest high since entry" in lines
    assert "    #2   bar 6     SELL       45 @      11.70  value       526.50  cost     0.00  cash       531.50  trail" in lines
    assert "  End equity:  531.50" in lines


def test_flag_wins_over_the_file(folder, capsys):
    code, out, _ = run(["c8.csv", "--config", "trail.ini", "--backtest", "--trailing-stop", "30"], capsys)
    assert code == 0
    lines = out.splitlines()
    assert "  Exits:       trail 30.00% below the highest high since entry" in lines
    assert "    #2   bar 7     SELL       45 @       9.00  value       405.00  cost     0.00  cash       410.00  trail" in lines
    code, out, _ = run(["c8.csv", "--config", "trail.ini", "--backtest", "--trailing-stop", "30", "--json"], capsys)
    assert code == 0 and json.loads(out)["backtest"]["trailing_stop_pct"] == 30.0
    code, out, _ = run(["c8.csv", "--config", "trail.ini", "--backtest", "--json"], capsys)
    assert code == 0 and json.loads(out)["backtest"]["trailing_stop_pct"] == 10.0


def test_a_valid_flag_wins_over_a_bad_file_value(folder, capsys):
    name = write_config(folder, SETTINGS + "trailing_stop = 0\n")
    code, out, _ = run(["c8.csv", "--config", name, "--backtest", "--trailing-stop", "10"], capsys)
    assert code == 0 and "cash       531.50  trail" in out


# --------------------------------------------------------------------------- same rules as stop_loss


@pytest.mark.parametrize("bad", ["0", "100", "-5", "150"])
def test_out_of_range_exits_2(folder, capsys, bad):
    name = write_config(folder, SETTINGS + f"trailing_stop = {bad}\n")
    code, out, err = run(["c8.csv", "--config", name, "--backtest"], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == (
        f"trading_assistant.cli: error: --trailing-stop must be between 0 and 100 (both exclusive), got {bad}"
    )


def test_not_with_resample_exits_2(folder, capsys):
    code, out, err = run(["c8.csv", "--config", "trail.ini", "--backtest", "--resample", "weekly"], capsys)
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == "trading_assistant.cli: error: --trailing-stop cannot be combined with --resample yet"


def test_needs_a_candle_file_exits_1_like_stop_loss(folder, capsys):
    code, out, err = run(["closes.csv", "--config", "trail.ini", "--backtest"], capsys)
    stop = write_config(folder, SETTINGS + "stop_loss = 10\n", "stop.ini")
    stop_code, _, stop_err = run(["closes.csv", "--config", stop, "--backtest"], capsys)
    assert code == stop_code == 1 and out == "" and err == stop_err
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")


@pytest.mark.parametrize("value", ["10", "0"])  # even a value that would be refused with --backtest
def test_ignored_without_backtest_and_with_scan(folder, capsys, value):
    name = write_config(folder, SETTINGS + f"trailing_stop = {value}\n")
    plain = write_config(folder, SETTINGS, "plain.ini")
    assert run(["c8.csv", "--config", name], capsys) == run(["c8.csv", "--config", plain], capsys)
    assert run(["c8.csv", "--config", name], capsys)[0] == 0
    assert run(["--scan", "scan", "--config", name], capsys) == run(["--scan", "scan", "--config", plain], capsys)


# --------------------------------------------------------------------------- old config files


def test_old_config_files_behave_the_same(folder):
    write_config(folder, SETTINGS + "stop_loss = 10\ntake_profit = 15\n", "stop.ini")
    write_config(folder, SETTINGS, "plain.ini")
    write_config(folder, "[cli]\nstop_loss = 0\n", "badrange.ini")

    proc = run_cli(folder, "c8.csv", "--config", "stop.ini", "--backtest")
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, OLD_STOP_TARGET_REPORT, "")
    proc = run_cli(folder, "c8.csv", "--config", "plain.ini", "--backtest", "--json")
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, OLD_PLAIN_JSON, "")
    proc = run_cli(folder, "c8.csv", "--config", "badrange.ini", "--backtest")
    assert (proc.returncode, proc.stdout, proc.stderr) == (2, "", OLD_STOP_LOSS_0_STDERR)


def test_unknown_key_message_now_lists_trailing_stop(folder, capsys):
    # The one agreed change for old files: the list of allowed keys gains trailing_stop.
    name = write_config(folder, "[cli]\ntrail = 10\n")
    code, out, err = run(["c8.csv", "--config", name, "--backtest"], capsys)
    assert (code, out) == (1, "")
    assert err == (
        "Error: t.ini line 2: unknown key 'trail' in [cli]; choose from: short, long, rsi_period, cash, fee, "
        "fee_pct, slippage, position_size, stop_loss, take_profit, trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, "
        "fill, strategy, stats, trade_list, explain, top, min_score\n"
    )
