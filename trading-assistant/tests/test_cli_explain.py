"""--explain on the command line: one sentence right after the Signal line, and nothing else changes.

c.csv (tests/data/c.csv, candles) has the closes 10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2 (2026-01-01 to
2026-01-11); closes.csv is the same as a close-only file. With --short 1 --long 3 the last bar is 12.2 against
(11 + 12 + 12.2) / 3 = 11.73 and the bar before 12 against (10 + 11 + 12) / 3 = 11.00: HOLD, no new crossover.
Weekly bars are the last close of each ISO week: 9 (week of Jan 1) and 12.2 (week of Jan 5), too few for a
crossover.
"""

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import main

DATA = Path(__file__).parent / "data"
W = ["--short", "1", "--long", "3"]
HOLD_ABOVE = (
    "HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: "
    "12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before."
)
HOLD_WEEKLY = (
    "HOLD because a crossover needs at least 4 bars and there are 2: "
    "12.20 against n/a on the last bar and 9.00 against n/a on the bar before."
)


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
    rows = (DATA / "c.csv").read_text().splitlines()[1:]
    closes = "".join(f"{r.split(',')[0]},{r.split(',')[4]}\n" for r in rows)
    (tmp_path / "closes.csv").write_text("date,close\n" + closes)
    (tmp_path / "scan").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.mark.parametrize(
    "argv, sentence",
    [
        (["closes.csv", *W], HOLD_ABOVE),
        (["closes.csv", *W, "--backtest", "--stats", "--chart"], HOLD_ABOVE),
        # --strategy changes the backtest only; the sentence still explains the SMA 1/3 Signal line.
        (["closes.csv", *W, "--backtest", "--strategy", "breakout", "--param", "window=2"], HOLD_ABOVE),
        (["closes.csv", *W, "--resample", "weekly", "--backtest"], HOLD_WEEKLY),
        (["c.csv", *W, "--candles", "--backtest"], HOLD_ABOVE),
    ],
    ids=["plain", "backtest-stats-chart", "strategy", "resample", "candles"],
)
def test_explain_adds_one_line_after_signal_and_nothing_else(folder, argv, sentence):
    code, out, err = run(argv)
    assert (code, err) == (0, "")
    with_explain = run([*argv, "--explain"])
    lines = out.splitlines(keepends=True)
    at = next(i for i, line in enumerate(lines) if line.startswith("Signal:  ")) + 1
    assert sentence.split()[0] == lines[at - 1].split()[1]  # same decision as the Signal line
    lines.insert(at, sentence + "\n")
    assert with_explain == (0, "".join(lines), "")


@pytest.mark.parametrize(
    "argv",
    [["closes.csv", *W], ["closes.csv", *W, "--backtest", "--stats", "--trade-list"]],
    ids=["plain", "backtest"],
)
def test_json_gets_the_same_sentence_right_after_signal_and_nothing_else(folder, argv):
    code, out, err = run([*argv, "--json"])
    assert (code, err) == (0, "")
    text = run([*argv, "--explain"])[1].splitlines()
    sentence = text[text.index("Signal:  HOLD") + 1]
    assert sentence == HOLD_ABOVE
    data = json.loads(out)
    expected = {}
    for key, value in data.items():
        expected[key] = value
        if key == "signal":
            expected["explanation"] = sentence
    # Byte for byte: the old object with one key added right after signal, printed the same way.
    assert run([*argv, "--json", "--explain"]) == (0, json.dumps(expected, indent=2) + "\n", "")


def test_explain_with_scan_is_a_usage_error(folder):
    code, out, err = run(["--scan", "scan", "--explain"])
    assert (code, out) == (2, "")
    assert err.startswith("usage: trading_assistant.cli ")
    assert err.endswith("error: --explain cannot be combined with --scan\n")


@pytest.mark.parametrize("alias", ["--e", "--ex", "--exp"])
def test_old_export_abbreviations_still_mean_export(folder, alias):
    argv = ["closes.csv", *W, "--backtest"]
    expected = run([*argv, "--export", "E.csv"])
    expected_file = (folder / "E.csv").read_text()
    (folder / "E.csv").unlink()
    assert run([*argv, alias, "E.csv"]) == expected
    assert (folder / "E.csv").read_text() == expected_file
    # Its errors still name --export.
    code, _, err = run(["closes.csv", alias, "E.csv"])
    assert code == 2 and err.endswith("error: --export only makes sense together with --backtest\n")


def test_help_lists_explain_but_the_usage_line_does_not(folder):
    code, out, err = run(["--help"])
    assert (code, err) == (0, "")
    usage, options = out.split("\noptions:\n")
    assert "--explain" not in usage
    assert "\n  --explain " in options and "Signal line" in options.split("\n  --explain ")[1]
    for alias in ("--e", "--ex", "--exp"):  # the aliases stay hidden
        assert f"\n  {alias} " not in out and f"{alias}," not in out
