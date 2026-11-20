"""The config file key ``cooldown`` ([cli] section), the file form of --cooldown N.

Used only with --backtest and when a stop is on (stop_loss, trailing_stop or
atr_stop = yes, from the file or the flags); otherwise it is ignored quietly,
like atr_mult and atr_period. A value that is not a whole number is a config
error (exit 1); a value below 1 gets the flag's message (exit 2), even when the
key is ignored. --cooldown on the command line wins over the file.

The hand file is the 11-bar candle file of test_cli_cooldown.py (--cash 1000
--short 1 --long 2): with a 10 % stop, cooldown 3 skips the bar 9 buy (end 901),
cooldown 2 does not (end 916). Without a stop the signal sells on bar 7 (end 925).
"""

import pytest

from trading_assistant.cli import main
from trading_assistant.config import load_config

HAND = """\
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
B = ["--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(HAND)
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
    (folder / "c.ini").write_text("[cli]\ncooldown = 3\n")
    assert load_config("c.ini")["cli"] == {"cooldown": 3}


@pytest.mark.parametrize("n, end", [(3, "901.00"), (2, "916.00")])
def test_hand_case_from_the_file_is_the_flag_run(folder, capsys, n, end):
    # Text and --json are exactly those of the flag run.
    for extra in ([], ["--json"]):
        from_file = with_config(folder, capsys, f"[cli]\nstop_loss = 10\ncooldown = {n}\n", ["hand.csv", *B, *extra])
        from_flags = run(["hand.csv", *B, "--stop-loss", "10", "--cooldown", str(n), *extra], capsys)
        assert from_file == from_flags and from_file[0] == 0
    text = run(["hand.csv", *B, "--config", "c.ini"], capsys)[1].splitlines()
    skipped = "1 buy" if n == 3 else "0 buys"
    assert f"  Cooldown:    {n} bars after a stop, trail or atr exit; {skipped} skipped" in text
    assert f"  End equity:  {end}" in text


def test_the_flag_wins_and_a_stop_from_either_place_counts(folder, capsys):
    code, out, _ = with_config(folder, capsys, "[cli]\nstop_loss = 10\ncooldown = 3\n", ["hand.csv", *B, "--cooldown", "2"])
    assert code == 0 and "  Cooldown:    2 bars after a stop, trail or atr exit; 0 buys skipped" in out.splitlines()
    code, out, _ = with_config(folder, capsys, "[cli]\ncooldown = 3\n", ["hand.csv", *B, "--trailing-stop", "10"])
    assert code == 0 and "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped" in out.splitlines()


@pytest.mark.parametrize(
    "text, extra",
    [
        ("[cli]\ncooldown = 3\n", []),
        ("[cli]\ncooldown = 3\n", ["--take-profit", "5"]),
        ("[cli]\ntake_profit = 5\ncooldown = 3\n", []),
        ("[cli]\ncooldown = 3\n", ["--json"]),
    ],
    ids=["no stop", "target flag", "target in file", "json"],
)
def test_without_a_stop_the_key_is_ignored_quietly(folder, capsys, text, extra):
    (folder / "same.ini").write_text(text.replace("cooldown = 3\n", ""))
    assert with_config(folder, capsys, text, ["hand.csv", *B, *extra]) == run(
        ["hand.csv", *B, *extra, "--config", "same.ini"], capsys
    )
    assert "ooldown" not in run(["hand.csv", *B, *extra, "--config", "c.ini"], capsys)[1]


def test_ignored_without_backtest_and_with_scan(folder, capsys):
    (folder / "c.ini").write_text("[cli]\nstop_loss = 10\ncooldown = 3\n")
    assert run(["hand.csv", "--config", "c.ini"], capsys) == run(["hand.csv"], capsys)
    assert run(["--scan", "scan", "--config", "c.ini"], capsys) == run(["--scan", "scan"], capsys)


@pytest.mark.parametrize(
    "text, extra, code, message",
    [
        ("[cli]\nstop_loss = 10\ncooldown = 0\n", [], 2, "trading_assistant.cli: error: --cooldown must be a whole number of at least 1, got 0\n"),
        ("[cli]\ncooldown = 0\n", [], 2, "trading_assistant.cli: error: --cooldown must be a whole number of at least 1, got 0\n"),
        ("[cli]\ncooldown = -1\n", [], 2, "trading_assistant.cli: error: --cooldown must be a whole number of at least 1, got -1\n"),
        ("[cli]\ncooldown = 1.5\n", [], 1, "Error: c.ini line 2: cooldown needs a whole number, got '1.5'\n"),
        ("[cli]\nstop_loss = 10\ncooldown = abc\n", [], 1, "Error: c.ini line 3: cooldown needs a whole number, got 'abc'\n"),
        # The flag without a stop stays a usage error, whatever the file says.
        ("[cli]\ncooldown = 3\n", ["--cooldown", "2"], 2,
         "trading_assistant.cli: error: --cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop\n"),
    ],
)
def test_bad_values_are_errors_with_or_without_a_stop(folder, capsys, text, extra, code, message):
    got_code, out, err = with_config(folder, capsys, text, ["hand.csv", *B, *extra])
    assert (got_code, out) == (code, "")
    assert err.endswith(message)
