"""The config key ``explain`` (yes/no), read like ``stats``: yes turns --explain on, no leaves the flag as written.

Unlike stats it needs no --backtest, and unlike the --explain flag it is no error with --scan (it is ignored there).
c.csv (tests/data/c.csv) with --short 1 --long 3 ends in a HOLD; test_cli_explain.py has the sentence.
"""

import contextlib
import io
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import main
from trading_assistant.config import ConfigError, load_config

DATA = Path(__file__).parent / "data"
W = ["c.csv", "--short", "1", "--long", "3"]


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
    (tmp_path / "scan").mkdir()
    shutil.copy(DATA / "c.csv", tmp_path / "scan" / "c.csv")
    for word in ("yes", "no", "maybe"):
        (tmp_path / f"{word}.ini").write_text(f"[cli]\nexplain = {word}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.mark.parametrize("extra", [[], ["--backtest", "--json"]], ids=["text", "backtest-json"])
def test_explain_yes_is_the_flag(folder, extra):
    flag = run([*W, *extra, "--explain"])
    assert flag[0] == 0 and "HOLD because" in flag[1]
    assert run([*W, *extra, "--config", "yes.ini"]) == flag
    assert run([*W, *extra, "--config", "yes.ini", "--explain"]) == flag


def test_explain_no_leaves_the_flag_as_written(folder):
    assert run([*W, "--config", "no.ini"]) == run(W)  # off, as without the file
    assert run([*W, "--config", "no.ini", "--explain"]) == run([*W, "--explain"])  # the flag wins


def test_the_same_words_as_stats_are_accepted_and_rejected(tmp_path):
    def read(key, word):
        path = tmp_path / "w.ini"
        path.write_text(f"[cli]\n{key} = {word}\n")
        try:
            return load_config(path)["cli"][key]
        except ConfigError as exc:
            return str(exc)[len(str(path)) :].replace(key, "KEY")  # the path may hold the key's name

    words = ["yes", "No", "TRUE", "false", "on", "OFF", "1", "0", "maybe", "2", ""]
    results = {word: read("explain", word) for word in words}
    assert results == {word: read("stats", word) for word in words}
    assert [results[w] for w in words[:8]] == [True, False] * 4
    assert results["maybe"] == " line 2: KEY needs yes or no, got 'maybe'"


def test_bad_word_is_a_config_error(folder):
    assert run([*W, "--config", "maybe.ini"]) == (1, "", "Error: maybe.ini line 2: explain needs yes or no, got 'maybe'\n")


def test_explain_yes_is_ignored_with_scan(folder):
    plain = run(["--scan", "scan", "--short", "1", "--long", "3"])
    assert plain[0] == 0
    assert run(["--scan", "scan", "--short", "1", "--long", "3", "--config", "yes.ini"]) == plain
