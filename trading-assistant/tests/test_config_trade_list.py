"""The config key trade_list (a yes/no switch, like stats) against the --trade-list flag.

c.csv (tests/data/c.csv), short 1, long 2, cash 1000: the run of test_cli_trade_list.py. "yes" turns the trade list
on; "no" leaves it as the command line has it, so with --trade-list written the table is still printed (a flag on
the command line wins, and for a switch that means the file can only turn it on). Like the other backtest keys it is
not used without --backtest or with --scan. Without the key a config file gives what it gave before
(tests/data/cli_before_trade_list.json holds the flag run, recorded before --trade-list existed).
"""

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import main

DATA = Path(__file__).parent / "data"
BASE = "[cli]\nshort = 1\nlong = 2\ncash = 1000\n"
FLAGS = ["--short", "1", "--long", "2", "--cash", "1000"]
BEFORE = {tuple(r["argv"]): r for r in json.loads((DATA / "cli_before_trade_list.json").read_text())["unchanged"]}


def run(argv):
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
    (tmp_path / "scan").mkdir()
    shutil.copy(DATA / "c.csv", tmp_path / "scan" / "c.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def with_config(text, argv):
    Path("c.ini").write_text(text)
    return run([*argv, "--config", "c.ini"])


@pytest.mark.parametrize("extra", [[], ["--json"]], ids=["text", "json"])
def test_yes_gives_exactly_the_flag_run(folder, extra):
    from_file = with_config(BASE + "trade_list = yes\n", ["c.csv", "--backtest", *extra])
    assert from_file == run(["c.csv", "--backtest", *FLAGS, "--trade-list", *extra])
    assert from_file[0] == 0
    if extra:
        assert len(json.loads(from_file[1])["backtest"]["trade_list"]) == 2
    else:
        assert "Trade list (bar index is 0-based)" in from_file[1]


@pytest.mark.parametrize(
    "words, flag_run",
    [(["yes", "Yes", "TRUE", "on", "1"], True), (["no", "NO", "false", "off", "0"], False)],
    ids=["yes-words", "no-words"],
)
def test_the_words_stats_takes(folder, words, flag_run):
    for extra in ([], ["--json"]):
        expected = run(["c.csv", "--backtest", *FLAGS, *(["--trade-list"] if flag_run else []), *extra])
        for word in words:
            assert with_config(BASE + f"trade_list = {word}\n", ["c.csv", "--backtest", *extra]) == expected, word


def test_no_does_not_turn_off_the_flag(folder):
    # The flag wins; for a switch the file can only turn it on, so "no" changes nothing when --trade-list is written.
    got = with_config(BASE + "trade_list = no\n", ["c.csv", "--backtest", "--trade-list"])
    assert got == run(["c.csv", "--backtest", *FLAGS, "--trade-list"])
    assert "Trade list (bar index is 0-based)" in got[1]


def test_a_bad_word_is_a_config_error_like_stats(folder):
    assert with_config("[cli]\nstats = maybe\n", ["c.csv", "--backtest"]) == (
        1, "", "Error: c.ini line 2: stats needs yes or no, got 'maybe'\n"
    )
    assert with_config("[cli]\nshort = 1\ntrade_list = maybe\n", ["c.csv", "--backtest"]) == (
        1, "", "Error: c.ini line 3: trade_list needs yes or no, got 'maybe'\n"
    )


@pytest.mark.parametrize(
    "argv, without_key",
    [
        (["c.csv"], BASE),  # no --backtest: like the other backtest keys, not used
        (["--scan", "scan"], "[cli]\n"),  # --scan: not used either (and not an error)
    ],
    ids=["no-backtest", "scan"],
)
def test_not_used_without_backtest_or_with_scan(folder, argv, without_key):
    got = with_config(without_key + "trade_list = yes\n", argv)
    assert got == with_config(without_key, argv)
    assert got[0] == 0 and "Trade list" not in got[1]


def test_without_the_key_a_config_gives_what_it_gave_before(folder):
    before = BEFORE[("c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2")]
    assert with_config(BASE, ["c.csv", "--backtest"]) == (before["code"], before["out"], before["err"])
