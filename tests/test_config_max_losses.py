"""The config key max_losses (``[cli] max_losses = N``): the same as --max-losses N, and the flag wins.

losses.csv holds the LOSSES closes of test_max_losses.py (SMA 1/2, cash 1000: two losing round trips, end 799).
Like max_hold, the key is used only with --backtest and only when --max-losses is not written. A value that is
not a whole number is a config error (exit 1) wherever the key is; a value below 1 is the flag's error (exit 2),
but only where the key is used.
"""

import contextlib
import io
import json
from pathlib import Path

import pytest

from trading_assistant.cli import main

DATA = Path(__file__).parent / "data"
LOSSES = [10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13]
B = ["losses.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


def make_folder(path):
    (path / "losses.csv").write_text("date,close\n" + "".join(f"2026-01-{d:02d},{c}\n" for d, c in enumerate(LOSSES, 1)))
    (path / "scan").mkdir()
    (path / "scan" / "a.csv").write_text((path / "losses.csv").read_text())


def run(argv, config=None):
    """(exit code, stdout, stderr) of ``main``, with ``config`` written to c.ini and passed as --config."""
    if config is not None:
        Path("c.ini").write_text(config)
        argv = [*argv, "--config", "c.ini"]
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def folder(tmp_path, monkeypatch):
    make_folder(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.mark.parametrize("n", [1, 2, 3])
@pytest.mark.parametrize("extra", [[], ["--json"]], ids=["text", "json"])
def test_the_key_gives_exactly_what_the_flag_gives(folder, n, extra):
    from_file = run([*B, *extra], f"[cli]\nmax_losses = {n}\n")
    assert from_file == run([*B, *extra, "--max-losses", str(n)])
    assert from_file[0] == 0
    assert (f'"max_losses": {n},' if extra else f"  Max losses:  halt after {n} losing") in from_file[1]


@pytest.mark.parametrize("in_file, flag", [(1, 2), (2, 1)])
def test_the_flag_wins_over_the_file(folder, in_file, flag):
    # Both ways round, so neither the smaller nor the larger value wins by accident.
    code, out, err = run([*B, "--max-losses", str(flag), "--json"], f"[cli]\nmax_losses = {in_file}\n")
    assert (code, err) == (0, "")
    assert json.loads(out)["backtest"]["max_losses"] == flag
    assert (code, out, err) == run([*B, "--max-losses", str(flag), "--json"])


@pytest.mark.parametrize(
    "value, argv, code, message",
    [
        ("0", B, 2, "trading_assistant.cli: error: --max-losses must be a whole number of at least 1, got 0"),
        ("-1", B, 2, "trading_assistant.cli: error: --max-losses must be a whole number of at least 1, got -1"),
        ("2.5", B, 1, "Error: c.ini line 2: max_losses needs a whole number, got '2.5'"),
        ("abc", B, 1, "Error: c.ini line 2: max_losses needs a whole number, got 'abc'"),
        # Not a whole number: an error even where the key is not used.
        ("2.5", ["losses.csv"], 1, "Error: c.ini line 2: max_losses needs a whole number, got '2.5'"),
        ("abc", ["--scan", "scan"], 1, "Error: c.ini line 2: max_losses needs a whole number, got 'abc'"),
        ("2.5", [*B, "--max-losses", "2"], 1, "Error: c.ini line 2: max_losses needs a whole number, got '2.5'"),
    ],
)
def test_bad_values(folder, value, argv, code, message):
    got = run(argv, f"[cli]\nmax_losses = {value}\n")
    assert (got[0], got[1]) == (code, "")
    assert got[2].splitlines()[-1] == message


@pytest.mark.parametrize(
    "argv", [["losses.csv"], ["--scan", "scan"], [*B, "--max-losses", "2"]], ids=["no backtest", "scan", "flag"]
)
@pytest.mark.parametrize("value", ["0", "1"])
def test_ignored_without_backtest_with_scan_and_under_the_flag(folder, argv, value):
    # Not used there, so not range-checked either: 0 is ignored like 1, exactly like max_hold.
    assert run(argv, f"[cli]\nmax_losses = {value}\n") == run(argv)


# ----------------------------------------------------------------- config files without the key are unchanged

# Exit code, stdout and stderr of these config files and commands, recorded from the code as it was before the
# key was added (git HEAD, run in a separate worktree).
UNCHANGED_RUNS = [
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\n", ["losses.csv", "--backtest"]),
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\n", ["losses.csv", "--backtest", "--json"]),
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\nmin_hold = 4\nmax_hold = 3\nmax_drawdown = 17\n",
     ["losses.csv", "--backtest"]),
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\nmax_hold = 3\n", ["losses.csv", "--backtest", "--max-hold", "2"]),
    ("[cli]\nshort = 1\nlong = 2\nmax_hold = 0\n", ["losses.csv"]),
    ("[cli]\nshort = 1\nlong = 2\nmax_hold = 0\n", ["--scan", "scan"]),
    ("[cli]\nmax_hold = 0\n", ["losses.csv", "--backtest"]),
    ("[cli]\nmax_hold = 2.5\n", ["losses.csv", "--backtest"]),
]


def before_runs():
    return json.loads((DATA / "config_before_max_losses.json").read_text())


def test_the_recorded_runs_are_all_checked():
    assert [[entry["config"], entry["argv"]] for entry in before_runs()] == [list(r) for r in UNCHANGED_RUNS]


@pytest.mark.parametrize("i", range(len(UNCHANGED_RUNS)))
def test_config_files_without_the_key_behave_exactly_as_before(folder, i):
    entry = before_runs()[i]
    assert list(run(entry["argv"], entry["config"])) == [entry["code"], entry["out"], entry["err"]]
