"""The config file key ``max_hold`` ([cli] section), the file form of --max-hold N.

Used with --backtest (it needs no stop); ignored without --backtest and with
--scan, like every backtest key. A value that is not a whole number is a config
error (exit 1); a value below 1 gets the flag's message (exit 2). --max-hold on
the command line wins over the file. The price file is the close-only hand case
of test_cli_max_hold.py.
"""

import pytest

from trading_assistant.cli import main
from trading_assistant.config import load_config

CLOSES = "date,close\n" + "".join(
    f"2026-01-{d:02d},{c}\n"
    for d, c in zip((1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15), (10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2))
)
# The 11-bar candle file of test_cli_cooldown.py: the same closes as CLOSES.
CANDLES = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
"""
B = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "closes.csv").write_text(CLOSES)
    (tmp_path / "hand.csv").write_text(CANDLES)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def with_config(folder, capsys, text, argv):
    (folder / "c.ini").write_text(text)
    return run([*argv, "--config", "c.ini"], capsys)


def test_the_key_reads_as_a_whole_number(folder):
    (folder / "c.ini").write_text("[cli]\nmax_hold = 3\n")
    assert load_config("c.ini")["cli"] == {"max_hold": 3}


@pytest.mark.parametrize("n, line", [(1, "1 bar"), (2, "2 bars"), (3, "3 bars")])
def test_hand_case_from_the_file_is_the_flag_run(folder, capsys, n, line):
    # No stop in the file or on the command line, and a close-only price file. Text and --json
    # are exactly those of the flag run.
    for extra in ([], ["--json"]):
        from_file = with_config(folder, capsys, f"[cli]\nmax_hold = {n}\n", [*B, *extra])
        assert from_file == run([*B, "--max-hold", str(n), *extra], capsys) and from_file[0] == 0
    assert f"  Max hold:    {line} after a position's first buy" in run([*B, "--config", "c.ini"], capsys)[1]


def test_the_flag_wins(folder, capsys):
    code, out, _ = with_config(folder, capsys, "[cli]\nmax_hold = 3\n", [*B, "--max-hold", "1"])
    assert code == 0 and "; 2 time exits" in out


def test_ignored_without_backtest_and_with_scan(folder, capsys):
    (folder / "c.ini").write_text("[cli]\nmax_hold = 0\n")  # even a value below 1
    assert run(["closes.csv", "--config", "c.ini"], capsys) == run(["closes.csv"], capsys)
    assert run(["--scan", "scan", "--config", "c.ini"], capsys) == run(["--scan", "scan"], capsys)


@pytest.mark.parametrize(
    "text, code, message",
    [
        ("[cli]\nmax_hold = 0\n", 2, "trading_assistant.cli: error: --max-hold must be a whole number of at least 1, got 0\n"),
        ("[cli]\nmax_hold = -1\n", 2, "trading_assistant.cli: error: --max-hold must be a whole number of at least 1, got -1\n"),
        ("[cli]\nmax_hold = 1.2\n", 1, "Error: c.ini line 2: max_hold needs a whole number, got '1.2'\n"),
        ("[cli]\nshort = 1\nmax_hold = abc\n", 1, "Error: c.ini line 3: max_hold needs a whole number, got 'abc'\n"),
    ],
)
def test_bad_values_are_errors(folder, capsys, text, code, message):
    got_code, out, err = with_config(folder, capsys, text, B)
    assert (got_code, out) == (code, "")
    assert err.endswith(message)


def test_the_flag_wins_over_a_bad_file_value_and_a_bad_flag_is_still_an_error(folder, capsys):
    # Like cooldown: with the flag written, the file's value is not used, so its 0 is no error.
    code, out, _ = with_config(folder, capsys, "[cli]\nmax_hold = 0\n", [*B, "--max-hold", "2"])
    assert code == 0 and "  Max hold:    2 bars " in out
    code, out, err = with_config(folder, capsys, "[cli]\nmax_hold = 2\n", [*B, "--max-hold", "0"])
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --max-hold must be a whole number of at least 1, got 0\n")


@pytest.mark.parametrize(
    "keys, flags, both, price",
    [
        ("stop_loss = 10\ncooldown = 3\n", ["--stop-loss", "10", "--cooldown", "3"], [], "hand.csv"),
        ("fill = open\ntrailing_stop = 8\ntake_profit = 20\n",
         ["--fill", "open", "--trailing-stop", "8", "--take-profit", "20"], [], "hand.csv"),
        ("fee = 1\nslippage = 0.5\nposition_size = 0.5\n",
         ["--fee", "1", "--slippage", "0.5", "--position-size", "0.5"], [], "closes.csv"),
        ("", [], ["--resample", "weekly"], "closes.csv"),
    ],
    ids=["stop and cooldown", "open fills, trail and target", "costs and sizing", "resample"],
)
def test_with_other_keys_in_the_file_it_is_the_flag_run(folder, capsys, keys, flags, both, price):
    # keys (file) and flags (command line) say the same; `both` is given to both runs.
    argv = [price, *B[1:], *both]
    for extra in ([], ["--json"]):
        from_file = with_config(folder, capsys, f"[cli]\n{keys}max_hold = 1\n", [*argv, *extra])
        from_flags = run([*argv, *flags, "--max-hold", "1", *extra], capsys)
        assert from_file == from_flags and from_file[0] == 0
        assert ('"max_hold_bars": 1' if extra else "  Max hold:    1 bar ") in from_file[1]
