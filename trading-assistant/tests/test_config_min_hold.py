"""The config file key ``min_hold`` ([cli] section), the file form of --min-hold N.

Used with --backtest (it needs no stop); ignored without --backtest and with
--scan, like every backtest key. A value that is not a whole number is a config
error (exit 1) wherever the file is read; a value below 1 gets the flag's
message (exit 2) when the key is used. --min-hold on the command line wins over
the file. The price file is the close-only hand case of test_cli_min_hold.py.
"""

import json
from pathlib import Path

import pytest

from trading_assistant.cli import main
from trading_assistant.config import load_config

CLOSES = "date,close\n" + "".join(
    f"2026-01-{d:02d},{c}\n" for d, c in zip(range(1, 12), (10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2))
)
B = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
# `B --json` and `B --max-hold 2 --json`, captured from the command before --min-hold existed (git HEAD).
JSON_BEFORE = json.loads((Path(__file__).resolve().parent / "data" / "closes_json_before_min_hold.json").read_text())


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "closes.csv").write_text(CLOSES)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
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
    (folder / "c.ini").write_text("[cli]\nmin_hold = 3\n")
    assert load_config("c.ini")["cli"] == {"min_hold": 3}


@pytest.mark.parametrize(
    "keys, flags, skipped",
    [
        ("min_hold = 3\n", ["--min-hold", "3"], 0),
        ("min_hold = 4\n", ["--min-hold", "4"], 1),
        ("min_hold = 1\n", ["--min-hold", "1"], 0),
        ("min_hold = 4\nmax_hold = 2\n", ["--min-hold", "4", "--max-hold", "2"], 0),
    ],
)
def test_hand_case_from_the_file_is_the_flag_run(folder, capsys, keys, flags, skipped):
    # Text and --json (exit code, stdout and stderr) are exactly those of the flag run.
    for extra in ([], ["--json"]):
        from_file = with_config(folder, capsys, f"[cli]\n{keys}", [*B, *extra])
        assert from_file == run([*B, *flags, *extra], capsys) and from_file[0] == 0
    assert json.loads(from_file[1])["backtest"]["min_hold_skipped_sells"] == skipped


def test_the_flag_wins(folder, capsys):
    # File 3, flag 4: 4 is used (bar 7's sell is skipped), exactly as the flag alone.
    from_both = with_config(folder, capsys, "[cli]\nmin_hold = 3\n", [*B, "--min-hold", "4"])
    assert from_both == run([*B, "--min-hold", "4"], capsys)
    assert "  Min hold:    4 bars " in from_both[1] and "; 1 signal sell skipped" in from_both[1]
    assert "  End equity:  1,108.00\n" in from_both[1]
    # With the flag written the file's value is not used, so its 0 is no error; a bad flag still is.
    assert with_config(folder, capsys, "[cli]\nmin_hold = 0\n", [*B, "--min-hold", "4"]) == from_both
    code, out, err = with_config(folder, capsys, "[cli]\nmin_hold = 2\n", [*B, "--min-hold", "0"])
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --min-hold must be a whole number of at least 1, got 0\n")


def test_ignored_without_backtest_and_with_scan_but_a_non_number_is_still_an_error(folder, capsys):
    (folder / "c.ini").write_text("[cli]\nmin_hold = 0\n")  # even a value below 1
    assert run(["closes.csv", "--config", "c.ini"], capsys) == run(["closes.csv"], capsys)
    assert run(["--scan", "scan", "--config", "c.ini"], capsys) == run(["--scan", "scan"], capsys)
    (folder / "c.ini").write_text("[cli]\nmin_hold = abc\n")
    for argv in (["closes.csv"], ["--scan", "scan"]):
        assert run([*argv, "--config", "c.ini"], capsys) == (
            1, "", "Error: c.ini line 2: min_hold needs a whole number, got 'abc'\n"
        )


@pytest.mark.parametrize(
    "text, code, message",
    [
        ("[cli]\nmin_hold = 0\n", 2, "trading_assistant.cli: error: --min-hold must be a whole number of at least 1, got 0\n"),
        ("[cli]\nmin_hold = -1\n", 2, "trading_assistant.cli: error: --min-hold must be a whole number of at least 1, got -1\n"),
        ("[cli]\nmin_hold = 1.5\n", 1, "Error: c.ini line 2: min_hold needs a whole number, got '1.5'\n"),
        ("[cli]\nshort = 1\nmin_hold = abc\n", 1, "Error: c.ini line 3: min_hold needs a whole number, got 'abc'\n"),
    ],
)
def test_bad_values_are_errors(folder, capsys, text, code, message):
    got_code, out, err = with_config(folder, capsys, text, B)
    assert (got_code, out) == (code, "")
    assert err.endswith(message)


def test_files_without_the_key_are_unchanged(folder, capsys):
    for text, before in (("[cli]\ncash = 1000\n", "plain"), ("[cli]\nmax_hold = 2\n", "max_hold_2")):
        code, out, err = with_config(folder, capsys, text, [*B, "--json"])
        assert (code, err) == (0, "") and json.loads(out) == JSON_BEFORE[before]
