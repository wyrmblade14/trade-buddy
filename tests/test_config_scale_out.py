"""Config key scale_out (the command's --scale-out PCT): same rules as the flag, the flag wins.

A value not above 0 is the flag's usage error (exit 2); a value that is not a finite number is a config error
(exit 1), also without --backtest and with --scan, where the key is otherwise ignored. The c.csv hand case
(cash 1000, --short 1 --long 2; arithmetic in test_scale_out.py) must give exactly what the flags give, in text
and in --json. CONFIG_RUNS (files without the key) are checked against a SHA-256 of [exit code, stdout, stderr]
recorded from the code before --scale-out existed (git HEAD 9ab3743); the CLI just before this key gave the same.
"""

import contextlib
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import main
from trading_assistant.config import load_config

DATA = Path(__file__).parent / "data"
HAND = "[cli]\nshort = 1\nlong = 2\ncash = 1000\n"
FLAGS = ["--short", "1", "--long", "2", "--cash", "1000"]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, as a close-only file


def run(argv):
    """(exit code, stdout, stderr) of ``main(argv)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def folder(tmp_path, monkeypatch):
    shutil.copy(DATA / "c.csv", tmp_path / "c.csv")
    (tmp_path / "closes.csv").write_text(
        "date,close\n" + "".join(f"2026-01-{i:02d},{c}\n" for i, c in enumerate(CLOSES, 1))
    )
    (tmp_path / "scan").mkdir()
    shutil.copy(DATA / "c.csv", tmp_path / "scan" / "c.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def with_file(folder, text, argv):
    (folder / "s.ini").write_text(text)
    return run([*argv, "--config", "s.ini"])


def test_load_config_reads_a_number(tmp_path):
    # A whole-number value is read as a float, like breakeven.
    (tmp_path / "s.ini").write_text("[cli]\nscale_out = 5\nbreakeven = 5\n")
    cli = load_config(tmp_path / "s.ini")["cli"]
    assert cli == {"scale_out": 5.0, "breakeven": 5.0}
    assert isinstance(cli["scale_out"], float)


@pytest.mark.parametrize(
    "keys, flags, equity",
    [
        ("scale_out = 5\n", ["--scale-out", "5"], "995.95"),
        ("scale_out = 9\n", ["--scale-out", "9"], "1,016.15"),
        ("scale_out = 10\n", ["--scale-out", "10"], "925.00"),
        ("scale_out = 5\nstop_loss = 10\n", ["--scale-out", "5", "--stop-loss", "10"], "991.45"),
    ],
    ids=["5", "9", "10", "5 stop 10"],
)
def test_the_file_gives_exactly_what_the_flags_give(folder, keys, flags, equity):
    for extra in ([], ["--json"]):
        by_file = with_file(folder, HAND + keys, ["c.csv", "--backtest", *extra])
        by_flags = run(["c.csv", "--backtest", *FLAGS, *flags, *extra])
        assert by_file == by_flags
        assert by_file[0] == 0 and by_file[2] == ""
    text = with_file(folder, HAND + keys, ["c.csv", "--backtest"])[1]
    assert f"  End equity:  {equity}\n" in text
    data = json.loads(with_file(folder, HAND + keys, ["c.csv", "--backtest", "--json"])[1])["backtest"]
    assert data["scale_out_pct"] == float(flags[1])


@pytest.mark.parametrize("in_file", ["5", "0", "-3", "2.5"])
def test_the_flag_wins_and_the_file_value_is_not_used(folder, in_file):
    # File 5 and --scale-out 9 runs at 9 (1,016.15), not 5 (995.95); a file value that would be a usage error
    # (0, -3) is not used either, so it is no error.
    got = with_file(folder, HAND + f"scale_out = {in_file}\n", ["c.csv", "--backtest", "--scale-out", "9"])
    assert got == run(["c.csv", "--backtest", *FLAGS, "--scale-out", "9"])
    assert "reaches 9.00% above the average entry" in got[1] and "  End equity:  1,016.15\n" in got[1]


@pytest.mark.parametrize("value", ["0", "-1", "-0.5", "0.0"])
def test_not_above_0_is_the_flags_usage_error(folder, value):
    code, out, err = with_file(folder, HAND + f"scale_out = {value}\n", ["c.csv", "--backtest"])
    assert (code, out) == (2, "")
    assert err.startswith("usage: trading_assistant.cli ")
    assert err.splitlines()[-1] == f"trading_assistant.cli: error: --scale-out must be above 0, got {float(value):g}"
    assert err == run(["c.csv", "--backtest", *FLAGS, "--scale-out", value])[2]


@pytest.mark.parametrize(
    "value, message",
    [
        ("abc", "scale_out needs a number, got 'abc'"),
        ("", "scale_out needs a number, got ''"),
        ("5%", "scale_out needs a number, got '5%'"),
        ("nan", "scale_out needs a finite number, got 'nan'"),
        ("inf", "scale_out needs a finite number, got 'inf'"),
        ("-inf", "scale_out needs a finite number, got '-inf'"),
    ],
)
@pytest.mark.parametrize(
    "argv",
    [["c.csv", "--backtest"], ["c.csv", "--backtest", "--scale-out", "9"], ["c.csv"], ["closes.csv"], ["--scan", "scan"]],
    ids=["backtest", "flag given", "no backtest", "closes only", "scan"],
)
def test_a_value_that_is_not_a_finite_number_is_a_config_error_everywhere(folder, value, message, argv):
    code, out, err = with_file(folder, HAND + f"scale_out = {value}\n", argv)
    assert (code, out, err) == (1, "", f"Error: s.ini line 5: {message}\n")


@pytest.mark.parametrize("value", ["5", "0", "-1"])
@pytest.mark.parametrize(
    "argv", [["c.csv"], ["closes.csv"], ["--scan", "scan"]], ids=["no backtest", "closes only", "scan"]
)
def test_ignored_without_backtest_and_with_scan(folder, value, argv):
    # Not used, so neither range-checked nor a reason to read a candle file: exactly as without the key.
    assert with_file(folder, HAND + f"scale_out = {value}\n", argv) == with_file(folder, HAND, argv)
    assert with_file(folder, HAND, argv)[0] == 0


def test_with_backtest_it_needs_a_candle_file_and_no_resample(folder):
    code, out, err = with_file(folder, HAND + "scale_out = 5\n", ["closes.csv", "--backtest"])
    assert (code, out) == (1, "")
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")
    code, out, err = with_file(folder, HAND + "scale_out = 5\n", ["closes.csv", "--backtest", "--resample", "weekly"])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1] == "trading_assistant.cli: error: --scale-out cannot be combined with --resample yet"


# Files without the key; recorded before --scale-out existed (see the module docstring).
CONFIG_RUNS = [
    (HAND, ["c.csv", "--backtest"], "b7be89bb678e42e40f942f3c301a55a183c606ab55967057bd8dd728699ea35d"),
    (HAND + "fee = 1\nfee_pct = 0.1\nslippage = 0.5\nposition_size = 0.5\nfill = open\nstop_loss = 5\ntake_profit = 20\n"
     "trailing_stop = 8\nstats = yes\n", ["c.csv", "--backtest"],
     "8d904e861b31972226e91c201c09199a470ce8650623514d4a3a271197c15f6c"),
    (HAND + "fee = 1\nfee_pct = 0.1\nslippage = 0.5\nposition_size = 0.5\nfill = open\nstop_loss = 5\ntake_profit = 20\n"
     "trailing_stop = 8\nstats = yes\n", ["c.csv", "--backtest", "--json"],
     "26736bc8ae86ea92633d1357de5c37d65d73cd7bc89cc91c1e11fdb08617f5f8"),
    (HAND + "risk_pct = 1\natr_mult = 2\natr_period = 2\natr_stop = yes\ncooldown = 2\nbreakeven = 5\n",
     ["c.csv", "--backtest", "--json"], "35ab918f29c116541d1c2b83bb5bf69b919bb9ae3868a1b274a4befbcf0182d2"),
    (HAND + "min_hold = 2\nmax_hold = 3\nmax_drawdown = 5\nmax_losses = 1\n", ["closes.csv", "--backtest"],
     "51c3fcc7635684257a8bda12fa53dfacfbd7c7c398503f545ce4c52fa090bf1c"),
    (HAND + "strategy = breakout\n\n[strategy.breakout]\nwindow = 1\n", ["c.csv", "--backtest"],
     "8495e06d953c5a622de2addc4c8abadbb5964ff77a8b5da048d19eef63acc21e"),
    (HAND + "top = 1\nmin_score = -4\nstop_loss = 5\n", ["--scan", "scan"],
     "4f5d25ea9c3bff023bd645c7dbb66cc37a8ce5afede473bd10be5f8012281e83"),
    (HAND + "stop_loss = 5\nbreakeven = 5\nmax_hold = 2\n", ["c.csv"],
     "eaad77ec5ed174ddb98271c9b9bfdb3ac95776c8c903ddd7a6cba1461eef8e0c"),
    (HAND + "stop_loss = 5\n", ["c.csv", "--backtest", "--stop-loss", "10"],
     "57f51ccf5e8673ecbd55ac8048a230d5fa62943efaa60691e925ac31f9456e85"),
    (HAND + "stop_loss = 0\n", ["c.csv", "--backtest"], "8816279e47984b39c48be5a243412808d9399a9d0c86df316b3f0a9ae68e5f3b"),
    (HAND + "breakeven = inf\n", ["c.csv", "--backtest"], "afb5c2143e132b9ba6b9c77527d95f21a0cefae31d58394b81f2f3d1d2702e88"),
    ("[cli]\nshort = 1.5\n", ["c.csv", "--backtest"], "1880e8291348a8e904346f8e77a93b3845d45813a6caea37fce90a95a4a24abe"),
    (HAND + "stop_loss = 5\n", ["closes.csv", "--backtest"], "ef2e06f5d6ba9607cd67a050d65910756a76897b8d4330b3e1520e4621045eb6"),
]


@pytest.mark.parametrize("i", range(len(CONFIG_RUNS)))
def test_files_without_the_key_behave_exactly_as_before(folder, i):
    text, argv, digest = CONFIG_RUNS[i]
    got = with_file(folder, text, argv)
    assert "scale_out" not in got[1] + got[2] and "Scale out" not in got[1]
    assert hashlib.sha256(json.dumps(list(got)).encode()).hexdigest() == digest
