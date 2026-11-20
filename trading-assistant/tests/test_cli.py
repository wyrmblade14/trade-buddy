"""Tests for the command line entry point (trading_assistant.cli).

Covers CSV loading, argument parsing/validation (in particular the rule that
--short must be smaller than --long), the printed report, exit codes, and an
end-to-end run via ``python -m trading_assistant.cli``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import (
    DEFAULT_LONG,
    DEFAULT_RSI_PERIOD,
    DEFAULT_SHORT,
    DISCLAIMER,
    build_parser,
    load_closes,
    main,
    validate_args,
)
from trading_assistant.signals import BUY, HOLD, SELL, crossover_signal, rsi_filter

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Price paths that produce each signal with --short 2 --long 5.
BUY_CLOSES = [10.0] * 5 + [9.0, 9.0, 9.0, 9.0, 20.0]
SELL_CLOSES = [10.0] * 5 + [11.0, 11.0, 11.0, 11.0, 1.0]
FLAT_CLOSES = [10.0] * 12


# --------------------------------------------------------------------------- helpers


def write_csv(path, closes, header="date,close"):
    """Write a CSV with a header and one row per close value."""
    lines = [header] + [f"d{i},{c}" for i, c in enumerate(closes)]
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture
def csv_file(tmp_path):
    """Factory fixture: csv_file(closes) -> str path to a CSV with those closes."""

    def _make(closes, name="prices.csv", header="date,close"):
        return str(write_csv(tmp_path / name, closes, header=header))

    return _make


def parse_report(stdout):
    """Turn the 'Key:    value' lines of the report into a dict."""
    report = {}
    for line in stdout.splitlines():
        if ":" in line and not line.startswith(DISCLAIMER):
            key, _, value = line.partition(":")
            report[key.strip()] = value.strip()
    return report


# --------------------------------------------------------------------------- load_closes


def test_load_closes_reads_close_column(csv_file):
    path = csv_file([101.5, 102.1, 99.0])
    assert load_closes(path) == [101.5, 102.1, 99.0]


def test_load_closes_returns_floats(csv_file):
    path = csv_file([1, 2, 3])
    closes = load_closes(path)
    assert all(isinstance(c, float) for c in closes)


def test_load_closes_ignores_other_columns(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,open,close,volume\nd0,1.0,2.0,100\nd1,3.0,4.0,200\n")
    assert load_closes(str(path)) == [2.0, 4.0]


def test_load_closes_close_column_anywhere_in_header(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("close,date\n5.5,d0\n6.5,d1\n")
    assert load_closes(str(path)) == [5.5, 6.5]


def test_load_closes_header_only_is_empty(csv_file):
    assert load_closes(csv_file([])) == []


def test_load_closes_missing_close_column_raises(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,price\nd0,1.0\n")
    with pytest.raises(ValueError, match="no 'close' column"):
        load_closes(str(path))


def test_load_closes_empty_file_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(ValueError, match="no 'close' column"):
        load_closes(str(path))


def test_load_closes_non_numeric_value_raises_with_line_number(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,close\nd0,1.0\nd1,abc\n")
    with pytest.raises(ValueError, match=r"line 3: invalid close value 'abc'"):
        load_closes(str(path))


def test_load_closes_blank_value_raises(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,close\nd0,1.0\nd1,\n")
    with pytest.raises(ValueError, match="invalid close value"):
        load_closes(str(path))


def test_load_closes_missing_file_raises_oserror(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_closes(str(tmp_path / "does-not-exist.csv"))


# --------------------------------------------------------------------------- build_parser


def test_parser_defaults_match_readme():
    args = build_parser().parse_args(["prices.csv"])
    assert args.csv_path == "prices.csv"
    assert (args.short, args.long, args.rsi_period) == (20, 50, 14)
    assert (DEFAULT_SHORT, DEFAULT_LONG, DEFAULT_RSI_PERIOD) == (20, 50, 14)


def test_parser_reads_custom_windows():
    args = build_parser().parse_args(["p.csv", "--short", "5", "--long", "9", "--rsi-period", "7"])
    assert (args.short, args.long, args.rsi_period) == (5, 9, 7)


def test_parser_option_order_does_not_matter():
    """--short then --long must parse identically to --long then --short."""
    parser = build_parser()
    short_first = parser.parse_args(["p.csv", "--short", "3", "--long", "8"])
    long_first = parser.parse_args(["p.csv", "--long", "8", "--short", "3"])
    assert vars(short_first) == vars(long_first)


def test_parser_options_can_precede_positional():
    args = build_parser().parse_args(["--short", "3", "--long", "8", "p.csv"])
    assert (args.csv_path, args.short, args.long) == ("p.csv", 3, 8)


@pytest.mark.parametrize("argv", [["p.csv", "--short", "abc"], ["p.csv", "--long", "1.5"], []])
def test_parser_rejects_bad_arguments_with_exit_2(argv):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(argv)
    assert excinfo.value.code == 2


def test_help_exits_0_and_lists_options(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--short" in out
    assert "--long" in out
    assert "--rsi-period" in out
    assert DISCLAIMER in out


# --------------------------------------------------------------------------- validate_args


def test_validate_args_accepts_short_smaller_than_long():
    parser = build_parser()
    args = parser.parse_args(["p.csv", "--short", "2", "--long", "5"])
    assert validate_args(parser, args) is args


def test_validate_args_accepts_defaults():
    parser = build_parser()
    args = parser.parse_args(["p.csv"])
    assert validate_args(parser, args) is args


@pytest.mark.parametrize(
    "short, long",
    [
        (5, 5),  # equal
        (6, 5),  # short greater than long
        (50, 20),  # defaults swapped
    ],
)
def test_validate_args_rejects_short_not_smaller_than_long(short, long, capsys):
    parser = build_parser()
    args = parser.parse_args(["p.csv", "--short", str(short), "--long", str(long)])
    with pytest.raises(SystemExit) as excinfo:
        validate_args(parser, args)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert f"--short ({short}) must be smaller than --long ({long})" in err


@pytest.mark.parametrize(
    "argv, message",
    [
        (["p.csv", "--short", "0"], "--short must be at least 1"),
        (["p.csv", "--short", "-3"], "--short must be at least 1"),
        (["p.csv", "--short", "1", "--long", "0"], "--long must be at least 1"),
        (["p.csv", "--rsi-period", "0"], "--rsi-period must be at least 1"),
        (["p.csv", "--rsi-period", "-1"], "--rsi-period must be at least 1"),
    ],
)
def test_validate_args_rejects_windows_below_one(argv, message, capsys):
    parser = build_parser()
    args = parser.parse_args(argv)
    with pytest.raises(SystemExit) as excinfo:
        validate_args(parser, args)
    assert excinfo.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_short_long_rule_matches_signals_rule():
    """The CLI rejects exactly the (short, long) pairs crossover_signal rejects."""
    parser = build_parser()
    closes = [1.0] * 100
    for short in range(1, 6):
        for long in range(1, 6):
            args = parser.parse_args(["p.csv", "--short", str(short), "--long", str(long)])
            try:
                crossover_signal(closes, short=short, long=long)
                library_accepts = True
            except ValueError:
                library_accepts = False
            try:
                validate_args(parser, args)
                cli_accepts = True
            except SystemExit:
                cli_accepts = False
            assert cli_accepts == library_accepts, (short, long)


# --------------------------------------------------------------------------- main: report


def test_main_buy_signal(csv_file, capsys):
    assert main([csv_file(BUY_CLOSES), "--short", "2", "--long", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Signal"] == BUY


def test_main_sell_signal(csv_file, capsys):
    assert main([csv_file(SELL_CLOSES), "--short", "2", "--long", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Signal"] == SELL


def test_main_hold_signal_when_flat(csv_file, capsys):
    assert main([csv_file(FLAT_CLOSES), "--short", "2", "--long", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Signal"] == HOLD


def test_main_hold_when_not_enough_history_for_long_window(csv_file, capsys):
    # 10 bars but the default long window is 50 -> HOLD, never an error.
    assert main([csv_file(BUY_CLOSES)]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Signal"] == HOLD


def test_main_report_layout(csv_file, capsys):
    # RSI(5) on BUY_CLOSES by hand: seed avg_gain=0, avg_loss=0.2; Wilder decay
    # 0.16 -> 0.128 -> 0.1024; final bar gain 11 -> avg_gain=2.2, avg_loss=0.08192
    # -> RSI = 100 - 100/(1 + 2.2/0.08192) = 96.41
    assert main([csv_file(BUY_CLOSES), "--short", "2", "--long", "5", "--rsi-period", "5"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines == [
        "Bars:    10",
        "Last:    20.00",
        "Signal:  BUY",
        "RSI:     96.4 (overbought)",
        DISCLAIMER,
    ]


def test_main_report_layout_rsi_not_available(csv_file, capsys):
    # 10 bars < default RSI period of 14 -> the RSI line reads n/a.
    assert main([csv_file(BUY_CLOSES), "--short", "2", "--long", "5"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[3] == "RSI:     n/a"
    assert len(lines) == 5


def test_main_last_is_two_decimals(csv_file, capsys):
    assert main([csv_file([1.0, 2.0, 3.14159])]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Last"] == "3.14"
    assert report["Bars"] == "3"


def test_main_always_prints_disclaimer(csv_file, capsys):
    assert main([csv_file([1.0])]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith(DISCLAIMER)
    assert "Not financial advice" in out


@pytest.mark.parametrize(
    "closes",
    [BUY_CLOSES, SELL_CLOSES, FLAT_CLOSES, [float(i) for i in range(1, 30)]],
    ids=["buy", "sell", "flat", "rising"],
)
@pytest.mark.parametrize("short, long", [(2, 5), (3, 7), (2, 20), (20, 50)])
def test_main_signal_matches_crossover_signal(csv_file, capsys, closes, short, long):
    """Whatever --short/--long the user passes, the CLI must report the same
    signal as calling crossover_signal with those same windows."""
    expected = crossover_signal(closes, short=short, long=long)
    assert main([csv_file(closes), "--short", str(short), "--long", str(long)]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["Signal"] == expected


def test_main_same_output_regardless_of_option_order(csv_file, capsys):
    path = csv_file(BUY_CLOSES)
    assert main([path, "--short", "2", "--long", "5"]) == 0
    short_first = capsys.readouterr().out
    assert main([path, "--long", "5", "--short", "2"]) == 0
    long_first = capsys.readouterr().out
    assert short_first == long_first
    assert parse_report(short_first)["Signal"] == BUY


# --------------------------------------------------------------------------- main: RSI


def test_main_rsi_not_available_with_too_few_bars(csv_file, capsys):
    # rsi() needs more than `period` bars; 5 bars with period 14 -> None -> n/a.
    assert main([csv_file([1.0, 2.0, 3.0, 4.0, 5.0])]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["RSI"] == "n/a"


def test_main_rsi_overbought(csv_file, capsys):
    rising = [float(i) for i in range(1, 30)]
    assert main([csv_file(rising), "--rsi-period", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["RSI"] == "100.0 (overbought)"


def test_main_rsi_oversold(csv_file, capsys):
    falling = [float(30 - i) for i in range(30)]
    assert main([csv_file(falling), "--rsi-period", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["RSI"] == "0.0 (oversold)"


def test_main_rsi_matches_rsi_filter(csv_file, capsys):
    closes = [10.0, 10.5, 10.2, 10.8, 10.6, 11.0, 10.9, 11.3, 11.1, 11.6, 11.4, 11.9]
    value, label = rsi_filter(closes, period=5)
    assert value is not None
    assert main([csv_file(closes), "--rsi-period", "5"]) == 0
    report = parse_report(capsys.readouterr().out)
    assert report["RSI"] == f"{value:.1f} ({label})"


# --------------------------------------------------------------------------- main: errors


def test_main_no_rows_returns_1(csv_file, capsys):
    assert main([csv_file([])]) == 1
    captured = capsys.readouterr()
    assert "No price rows found." in captured.err
    assert captured.out == ""


def test_main_missing_file_returns_1(tmp_path, capsys):
    missing = str(tmp_path / "nope.csv")
    assert main([missing]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error:")
    assert "nope.csv" in captured.err
    assert captured.out == ""


def test_main_missing_close_column_returns_1(tmp_path, capsys):
    path = tmp_path / "prices.csv"
    path.write_text("date,price\nd0,1.0\n")
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert "no 'close' column" in captured.err
    assert captured.out == ""


def test_main_non_numeric_close_returns_1(tmp_path, capsys):
    path = tmp_path / "prices.csv"
    path.write_text("date,close\nd0,1.0\nd1,oops\n")
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert "invalid close value 'oops'" in captured.err
    assert captured.out == ""


def test_main_short_not_smaller_than_long_exits_2(csv_file, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([csv_file(BUY_CLOSES), "--short", "5", "--long", "2"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--short (5) must be smaller than --long (2)" in captured.err
    assert captured.out == ""


def test_main_validates_args_before_touching_file(tmp_path, capsys):
    # Bad windows are a usage error (2) even when the CSV does not exist.
    with pytest.raises(SystemExit) as excinfo:
        main([str(tmp_path / "nope.csv"), "--short", "9", "--long", "3"])
    assert excinfo.value.code == 2


def test_main_uses_sys_argv_when_argv_is_none(csv_file, capsys, monkeypatch):
    path = csv_file(SELL_CLOSES)
    monkeypatch.setattr(sys, "argv", ["trading_assistant.cli", path, "--short", "2", "--long", "5"])
    assert main() == 0
    assert parse_report(capsys.readouterr().out)["Signal"] == SELL


# --------------------------------------------------------------------------- python -m


def run_cli(*argv):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.cli", *argv],
        capture_output=True,
        text=True,
        env=env,
    )


def test_python_m_happy_path(csv_file):
    result = run_cli(csv_file(BUY_CLOSES), "--short", "2", "--long", "5")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = parse_report(result.stdout)
    assert report["Signal"] == BUY
    assert DISCLAIMER in result.stdout


def test_python_m_short_not_smaller_than_long_exits_2(csv_file):
    result = run_cli(csv_file(BUY_CLOSES), "--short", "50", "--long", "20")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "--short (50) must be smaller than --long (20)" in result.stderr
    assert "Traceback" not in result.stderr


def test_python_m_missing_file_exits_1(tmp_path):
    result = run_cli(str(tmp_path / "nope.csv"))
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error:")
    assert "Traceback" not in result.stderr
