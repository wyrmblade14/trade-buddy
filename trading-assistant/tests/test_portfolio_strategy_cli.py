"""``python -m trading_assistant.portfolio FOLDER --strategy NAME --param KEY=VALUE``.

``tests/data/portfolio_cli_before_strategy.json`` was recorded with the command as it was before
``--strategy``/``--param`` existed: 16 commands (stdout, stderr, exit code, --csv file) and every shortened
option name (106 parses: each prefix of each option, old and new, with a separate value and with ``=``),
all run in a folder holding ``pf`` (AAA and BBB below), ``one`` (AAA only) and ``samples`` (the
downtrend, sideways and uptrend samples).
"""

import contextlib
import io
import json
import os
from pathlib import Path

import pytest

from trading_assistant import cli, portfolio
from trading_assistant.samples import sample_csv_rows

DATES = [f"2026-04-{i:02d}" for i in range(1, 11)]
HAND = {"AAA": [10, 11, 12, 13, 12, 11, 10, 11, 13, 14], "BBB": [20, 19, 18, 19, 21, 22, 21, 19, 18, 20]}
BEFORE = json.loads((Path(__file__).parent / "data" / "portfolio_cli_before_strategy.json").read_text())
PROG = "trading_assistant.portfolio: error: "
CHOICES = "'sma_cross', 'rsi_reversion', 'breakout', 'ema_cross', 'momentum', 'zscore_reversion', 'hull_trend'"


def _csv(closes):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, closes))


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")  # the width the help was recorded at
    for folder, files in (
        ("pf", {f"{s}.csv": _csv(cs) for s, cs in HAND.items()}),
        ("one", {"AAA.csv": _csv(HAND["AAA"])}),
        ("samples", {f"{s}.csv": "".join(",".join(r) + "\n" for r in sample_csv_rows(s))
                     for s in ("downtrend", "sideways", "uptrend")}),
    ):
        os.mkdir(folder)
        for name, text in files.items():
            (tmp_path / folder / name).write_text(text)
    return tmp_path


def run(argv, main=portfolio.main):
    """``(exit code, stdout, stderr)`` of the command, usage errors included."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def parse(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            namespace, code = vars(portfolio.build_parser().parse_args(argv)), 0
        except SystemExit as exc:
            namespace, code = None, exc.code
    return code, out.getvalue(), err.getvalue(), namespace


OLD_DESCRIPTION = ("Backtest the SMA crossover on every .csv file in a folder, with the cash split\n"
                   "equally (or by --weights), on the dates every file shares.\n")
NEW_DESCRIPTION = ("Backtest the SMA crossover (or --strategy) on every .csv file in a folder,\n"
                   "with the cash split equally (or by --weights), on the dates every file shares.\n")
NEW_OPTIONS = """\
  --strategy NAME       rule every symbol trades (default: sma_cross), one of:
                        sma_cross, rsi_reversion, breakout, ema_cross,
                        momentum, zscore_reversion, hull_trend; --short and
                        --long only apply to sma_cross
  --param KEY=VALUE     override a parameter of the strategy, e.g. window=10
                        (repeatable); without --strategy it adjusts sma_cross
"""


def expected_help(old):
    """The old --help with the new description and the two new options after the old ones (usage line as it was)."""
    assert old.count(OLD_DESCRIPTION) == 1
    body, epilog = old.replace(OLD_DESCRIPTION, NEW_DESCRIPTION).rsplit("\n\n", 1)
    return body + "\n" + NEW_OPTIONS + "\n" + epilog


def test_commands_without_the_new_options_are_unchanged(folders):
    assert len(BEFORE["commands"]) == 16
    for record in BEFORE["commands"]:
        code, out, err = run(record["argv"])
        if record["argv"][-1] == "--help":
            assert (code, err) == (0, "") and out == expected_help(record["stdout"])
            continue
        assert (code, out, err) == (record["code"], record["stdout"], record["stderr"]), record["argv"]
        if "csv" in record:
            assert (folders / "out.csv").read_text() == record["csv"]
            (folders / "out.csv").unlink()


def test_shortened_option_names_keep_their_meaning(folders):
    # Before: 106 parses. --st ... --strategy and --p ... --param were unrecognized arguments; now they are
    # --strategy and --param. --s (now a hidden exact alias) and every other prefix means what it meant.
    help_now = run(["pf", "--help"])[1]
    assert len(BEFORE["abbreviations"]) == 106
    counts = {"same": 0, "help": 0, "strategy": 0, "param": 0}
    for record in BEFORE["abbreviations"]:
        argv = record["argv"]
        option = argv[1].split("=")[0]
        code, out, err, namespace = parse(argv)
        if "--strategy".startswith(option) and option.startswith("--st"):
            assert record["stderr"].endswith(f"{PROG}unrecognized arguments: {' '.join(argv[1:])}\n")
            assert (code, out) == (2, "") and err == record["stderr"].replace(
                f"unrecognized arguments: {' '.join(argv[1:])}",
                f"argument --strategy: invalid choice: '5' (choose from {CHOICES})")
            counts["strategy"] += 1
        elif "--param".startswith(option) and option.startswith("--p"):
            assert record["stderr"].endswith(f"{PROG}unrecognized arguments: {' '.join(argv[1:])}\n")
            assert code == 0 and namespace["param"] == ["5"] and namespace["strategy"] is None
            counts["param"] += 1
        elif record["stdout"].startswith("usage:"):  # -h, --h ... --help: the new help
            assert (code, out, err) == (0, help_now, "")
            counts["help"] += 1
        elif argv[1] == "--=5":  # the empty prefix: still ambiguous; the list now has the new names (and --s)
            assert (code, out) == (2, "") and err == record["stderr"].replace(
                "--help, --short, --long,", "--help, --short, --s, --long,").replace(
                "--csv\n", "--csv, --strategy, --param\n")
            counts["same"] += 1
        else:
            assert (code, out, err) == (record["code"], record["stdout"], record["stderr"]), argv
            if namespace is not None:
                assert {key: namespace[key] for key in record["namespace"]} == record["namespace"], argv
                assert namespace["strategy"] is None and namespace["param"] is None
            counts["same"] += 1
    # same: 77 (--=5 included); help: -h, --h, --he, --hel, --help; strategy: --st ... --strategy, each
    # with " 5" and "=5"; param: --p ... --param, the same.
    assert counts == {"same": 77, "help": 5, "strategy": 14, "param": 10}


BREAKOUT_TEXT = """\
Portfolio: 2 symbols, cash split equally, breakout (window=3), fee 0.00 + 0.00%, on the dates every file shares
Dates: 2026-04-01 to 2026-04-10 (10 shared dates)
Cash: 1,000.00  Final equity: 830.00
Return: -17.00%  Max drawdown: -17.00%  Buy & hold (equal weight): +20.00%
Symbol  Bars used  Bars lost   Return  Trades  Buy&Hold
AAA            10          0  -16.40%       3   +40.00%
BBB            10          0  -17.60%       2    +0.00%
Worst single-symbol drawdown: -17.60% (BBB)
Research aid only. Not financial advice.
"""
WEIGHTED_TEXT = """\
Portfolio: 2 symbols, cash split by weight (AAA 60%, BBB 40%), breakout (window=3), fee 0.00 + 0.00%, on the dates every file shares
Dates: 2026-04-01 to 2026-04-10 (10 shared dates)
Cash: 1,000.00  Final equity: 828.00
Return: -17.20%  Max drawdown: -17.20%  Buy & hold (same weights): +24.00%
Symbol  Weight  Bars used  Bars lost   Return  Trades  Buy&Hold
AAA        60%         10          0  -16.67%       3   +40.00%
BBB        40%         10          0  -18.00%       2    +0.00%
Worst single-symbol drawdown: -18.00% (BBB)
Research aid only. Not financial advice.
"""


def test_breakout_text_json_and_weights(folders):
    breakout = ["pf", "--strategy", "breakout", "--param", "window=3", "--cash", "1000"]
    assert run(breakout) == (0, BREAKOUT_TEXT, "")
    code, out, err = run([*breakout, "--json"])
    data = json.loads(out)
    assert (code, err) == (0, "") and list(data) == ["title", "summary", "skipped", "disclaimer"]
    assert data["title"] == BREAKOUT_TEXT.splitlines()[0]
    assert list(data["summary"])[:4] == ["strategy", "params", "fee", "fee_pct"]
    assert data["summary"]["strategy"] == "breakout" and data["summary"]["params"] == {"window": 3}
    assert "short" not in data["summary"] and "long" not in data["summary"]
    assert data["summary"]["final_equity"] == 830.0 and data["summary"]["buy_hold_return_pct"] == 20.0
    assert run([*breakout, "--weights", "AAA=60", "BBB=40"]) == (0, WEIGHTED_TEXT, "")
    # Every parameter is named, defaults included.
    code, out, _ = run(["pf", "--strategy", "momentum", "--param", "window=3", "--json"])
    assert code == 0 and json.loads(out)["summary"]["params"] == {"window": 3, "threshold": 0.0}


def test_sma_cross_params_print_exactly_what_short_and_long_print(folders):
    plain = ["pf", "--short", "2", "--long", "3", "--cash", "1000", "--csv", "out.csv"]
    spellings = [
        ["pf", "--strategy", "sma_cross", "--param", "short=2", "--param", "long=3", "--cash", "1000", "--csv", "out.csv"],
        ["pf", "--param", "long=3", "--param", "short=2", "--cash", "1000", "--csv", "out.csv"],
        ["pf", "--strategy", "sma_cross", "--short", "2", "--long", "3", "--cash", "1000", "--csv", "out.csv"],
        ["pf", "--short", "2", "--param", "short=2", "--long", "3", "--cash", "1000", "--csv", "out.csv"],
    ]
    for extra in ([], ["--json"]):
        expected = run(plain + extra), (folders / "out.csv").read_text()
        for argv in spellings:
            assert (run(argv + extra), (folders / "out.csv").read_text()) == expected, argv


ERRORS = [
    # (arguments after the folder, exit code, message, does the main command --backtest give the same?)
    (["--strategy", "breakout", "--short", "5"], 2,
     "--short only applies to --strategy sma_cross; set breakout's parameters with --param", False),
    (["--strategy", "momentum", "--s", "5", "--long", "9"], 2,
     "--short only applies to --strategy sma_cross; set momentum's parameters with --param", False),
    (["--strategy", "hull_trend", "--long", "9"], 2,
     "--long only applies to --strategy sma_cross; set hull_trend's parameters with --param", False),
    (["--short", "5", "--param", "short=6"], 2, "--param short=6 contradicts --short 5; give only one", True),
    (["--param", "short=2", "--param", "short=2"], 2, "--param short given more than once", True),
    (["--param", "window"], 2, "--param must look like KEY=VALUE, got 'window'", True),
    (["--param", "window=x"], 2, "--param window needs a number, got 'x'", True),
    (["--strategy", "breakout", "--param", "period=3"], 2,
     "unknown parameter 'period' for strategy 'breakout'; choose from: window", True),
    (["--strategy", "breakout", "--param", "window=0"], 2, "window must be a whole number of at least 1, got 0", True),
    (["--param", "short=60"], 2, "short window must be smaller than long window", True),
    (["--strategy", "nope"], 2, f"argument --strategy: invalid choice: 'nope' (choose from {CHOICES})", True),
    # Like the main command, a --param window that clashes with an explicit window is refused by the run.
    (["--short", "30", "--param", "long=25"], 1, "short window must be smaller than long window", True),
    (["--strategy", "breakout", "--param", "window=9"], 1,
     "only 10 dates shared by all 2 symbols; need at least 11 for breakout (window=9): 10 for its first signal"
     " + 1 to fill it", False),
    (["--strategy", "hull_trend"], 1,
     "only 10 dates shared by all 2 symbols; need at least 26 for hull_trend (window=20): 25 for its first signal"
     " + 1 to fill it", False),
]


@pytest.mark.parametrize("args, code, message, same_in_main", ERRORS, ids=[" ".join(e[0]) for e in ERRORS])
def test_errors(folders, args, code, message, same_in_main):
    got_code, out, err = run(["pf", *args])
    assert (got_code, out) == (code, "")
    if code == 2:
        usage = next(r["stderr"] for r in BEFORE["commands"] if r["argv"] == ["pf", "--bogus"]).split(PROG)[0]
        assert err == f"{usage}{PROG}{message}\n"  # the usage line as it was
    else:
        assert err == f"Error: {message}\n"
    if same_in_main:
        main_code, _, main_err = run(["pf/AAA.csv", "--backtest", *args], main=cli.main)
        last = main_err.splitlines()[-1]
        assert main_code == code
        assert last == (f"trading_assistant.cli: error: {message}" if code == 2 else f"Error: {message}")
