"""--max-losses N on the command line: the hand case of test_max_losses.py through the CLI, closes only.

losses.csv holds the LOSSES closes of test_max_losses.py. SMA 1/2, cash 1000, no option: BUY 90 @ 11 on bar 4,
SELL 90 @ 9 on bar 7 (-180), BUY 82 @ 10 on bar 10, SELL 82 @ 9 on bar 13 (-82), BUY 61 @ 12 on bar 15, end 799.
"""

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import build_parser, main

DATA = Path(__file__).parent / "data"
LOSSES = [10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13]
B = ["losses.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


def make_folder(path):
    """losses.csv (closes only), c.csv (tests/data/c.csv, candles) and an empty scan folder."""
    (path / "losses.csv").write_text("date,close\n" + "".join(f"2026-01-{d:02d},{c}\n" for d, c in enumerate(LOSSES, 1)))
    shutil.copy(DATA / "c.csv", path / "c.csv")
    (path / "scan").mkdir()
    (path / "scan" / "a.csv").write_text((path / "losses.csv").read_text())


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
    make_folder(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def losses_line(out):
    return [line for line in out.splitlines() if line.startswith("  Max losses:")]


# ----------------------------------------------------------------- the hand case


MAX_LOSSES_2 = """\
Bars:    17
Last:    13.00
Signal:  HOLD
RSI:     58.6 (neutral)
Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting
  Start cash:  1,000.00
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00
    #2   bar 7     SELL       90 @       9.00  value       810.00  cost     0.00  cash       820.00
    #3   bar 10    BUY        82 @      10.00  value       820.00  cost     0.00  cash         0.00
    #4   bar 13    SELL       82 @       9.00  value       738.00  cost     0.00  cash       738.00
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Max losses:  halt after 2 losing round trips in a row; triggered at bar 13, no buy fills after it; 1 buy skipped
  Round trips: 2 completed, 0 made money (0%)
  Comparison              Strategy    Buy & hold
    End equity              738.00      1,300.00
    Return                 -26.20%       +30.00%
    Max drawdown           -32.29%       -33.33%
    Trades                       4             1
    Costs paid                0.00          0.00
  End cash:    738.00
  End shares:  0 @ 13.00
  End equity:  738.00
  Return:      -26.20%
Research aid only. Not financial advice.
"""


def test_max_losses_2_word_for_word(folder):
    assert run([*B, "--max-losses", "2"]) == (0, MAX_LOSSES_2, "")


def test_max_losses_1_skips_the_bar_10_and_bar_15_buys(folder):
    code, out, err = run([*B, "--max-losses", "1"])
    assert (code, err) == (0, "")
    assert [line.split()[2:4] for line in out.splitlines() if line.startswith("    #")] == [["4", "BUY"], ["7", "SELL"]]
    assert losses_line(out) == [
        "  Max losses:  halt after 1 losing round trip in a row; triggered at bar 7, no buy fills after it; "
        "2 buys skipped"
    ]
    assert "\n  Trades:      2 (1 buy, 1 sell)\n" in out and "\n  End equity:  820.00\n" in out


def test_max_losses_3_is_the_run_without_it_plus_its_line(folder):
    _, plain, _ = run(B)
    code, out, err = run([*B, "--max-losses", "3"])
    assert (code, err) == (0, "")
    line = "  Max losses:  halt after 3 losing round trips in a row; not triggered; 0 buys skipped\n"
    assert out == plain.replace("  Round trips:", line + "  Round trips:")
    assert "\n  End equity:  799.00\n" in out


def test_resample_is_allowed(folder):
    # Weekly bars of losses.csv (Thursday 2026-01-01 to Saturday 2026-01-17): the ISO weeks end on Jan 4, 11 and
    # 17, closes 9, 11, 13. SMA 1/2 has no crossing (bar 0 has no signal, then it only rises): no trade, so the
    # halt never triggers. The option is accepted and reported.
    code, out, err = run([*B, "--max-losses", "1", "--resample", "weekly"])
    assert (code, err) == (0, "")
    assert out.startswith("Bars:    3\nLast:    13.00\n")
    assert "\n  Trades:      0 (0 buy, 0 sell)\n" in out
    assert losses_line(out) == [
        "  Max losses:  halt after 1 losing round trip in a row; not triggered; 0 buys skipped"
    ]


def test_candle_options_work_with_it(folder):
    # c.csv, stop 10 %: BUY 90 @ 11 on bar 4, the stop sells 90 @ 9.90 on bar 6 (-99): halt, bar 9 buy skipped.
    code, out, err = run(["c.csv", *B[1:], "--stop-loss", "10", "--max-losses", "1"])
    assert (code, err) == (0, "")
    assert losses_line(out) == [
        "  Max losses:  halt after 1 losing round trip in a row; triggered at bar 6, no buy fills after it; "
        "1 buy skipped"
    ]
    assert "\n  End equity:  901.00\n" in out


# ----------------------------------------------------------------- usage errors


@pytest.mark.parametrize(
    "argv, message",
    [
        ([*B, "--max-losses", "0"], "--max-losses must be a whole number of at least 1, got 0"),
        ([*B, "--max-losses", "-2"], "--max-losses must be a whole number of at least 1, got -2"),
        ([*B, "--max-losses", "2.5"], "argument --max-losses: invalid int value: '2.5'"),
        ([*B, "--max-losses", "two"], "argument --max-losses: invalid int value: 'two'"),
        (["losses.csv", "--max-losses", "2"], "--max-losses only makes sense together with --backtest"),
        (["--scan", "scan", "--max-losses", "2"], "--max-losses cannot be combined with --scan"),
    ],
)
def test_usage_errors_exit_2(folder, argv, message):
    code, out, err = run(argv)
    assert (code, out) == (2, "")
    assert err.endswith(f"error: {message}\n")


# ----------------------------------------------------------------- --help and option names


def test_help_lists_it_after_breakeven_but_the_usage_line_does_not(folder):
    _, out, _ = run(["--help"])
    assert "--max-losses" not in out.split("\n\n", 1)[0]
    starts = [line.split()[0] for line in out.splitlines() if line.startswith("  --")]
    i = starts.index("--max-losses")
    assert starts[i - 1 : i + 2] == ["--breakeven", "--max-losses", "--scale-out"]


@pytest.mark.parametrize("scan", [False, True])
def test_every_option_name_that_worked_before_still_means_the_same_option(scan):
    # Before --max-losses the parser knew every option string it knows now except --max-losses. argparse takes an
    # exact option string, or else a prefix of exactly one; every prefix that did so then must give the same dest.
    parser = build_parser(scan=scan)
    known = parser._option_string_actions
    old = {name: action.dest for name, action in known.items() if name.startswith("--") and name != "--max-losses"}
    checked = 0
    for name in old:
        for end in range(3, len(name) + 1):
            token = name[:end]
            matches = [n for n in old if n.startswith(token)]
            if token not in old and len(matches) != 1:
                continue  # was ambiguous before
            dest = old[token] if token in old else old[matches[0]]
            if dest == "help":
                continue
            action = known[token] if token in known else known[matches[0]]
            value = [] if action.nargs == 0 else [action.choices[0] if action.choices else "3"]
            args = parser.parse_args(([] if scan else ["x.csv"]) + [token] + value)
            assert getattr(args, dest) != parser.get_default(dest), (token, dest)
            checked += 1
    assert checked > 150
    for token in ("--ma", "--max", "--max-", "--max-h"):
        assert parser.parse_args(([] if scan else ["x.csv"]) + [token, "3"]).max_hold == 3


@pytest.mark.parametrize("token", ["--max-l", "--max-lo", "--max-los", "--max-loss", "--max-losse", "--max-losses"])
def test_max_l_and_longer_now_mean_max_losses(token):
    # Before --max-losses each of these was an unrecognized argument (exit 2).
    assert build_parser().parse_args(["x.csv", token, "2"]).max_losses == 2


# ----------------------------------------------------------------- --json and --export


@pytest.mark.parametrize(
    "n, trades, halt_bar, skipped, equity",
    [(1, 2, 7, 2, 820.0), (2, 4, 13, 1, 738.0), (3, 5, None, 0, 799.0)],
)
def test_json_keys_match_the_text_report(folder, n, trades, halt_bar, skipped, equity):
    _, plain, _ = run([*B, "--json"])
    code, out, err = run([*B, "--max-losses", str(n), "--json"])
    assert (code, err) == (0, "")
    before, now = list(json.loads(plain)["backtest"]), json.loads(out)["backtest"]
    # The keys without the option, plus max_losses after take_profit_pct and the two counts after sells.
    i, j = before.index("take_profit_pct") + 1, before.index("sells") + 1
    assert list(now) == [*before[:i], "max_losses", *before[i:j], "loss_halt_bar", "loss_skipped_buys", *before[j:]]
    values = [now[key] for key in ("max_losses", "trades", "loss_halt_bar", "loss_skipped_buys", "final_equity")]
    assert values == [n, trades, halt_bar, skipped, equity]
    # The same numbers as the text report of the same run.
    _, text, _ = run([*B, "--max-losses", str(n)])
    state = "not triggered" if halt_bar is None else f"triggered at bar {halt_bar}, no buy fills after it"
    assert losses_line(text) == [
        f"  Max losses:  halt after {n} losing round trip{'' if n == 1 else 's'} in a row; {state}; "
        f"{skipped} buy{'' if skipped == 1 else 's'} skipped"
    ]
    assert f"\n  Trades:      {trades} (" in text and f"\n  End equity:  {equity:,.2f}\n" in text


def test_json_keys_come_after_the_other_optional_keys(folder):
    argv = ["c.csv", *B[1:], "--stop-loss", "10", "--cooldown", "3", "--min-hold", "1", "--max-hold", "5",
            "--max-drawdown", "50", "--max-losses", "1", "--json"]
    code, out, err = run(argv)
    assert (code, err) == (0, "")
    keys = list(json.loads(out)["backtest"])
    i = keys.index("max_losses")
    assert keys[i - 4 : i + 2] == ["cooldown_bars", "min_hold_bars", "max_hold_bars", "max_drawdown_limit_pct",
                                   "max_losses", "trades"]
    j = keys.index("loss_halt_bar")
    assert keys[j - 6 : j + 3] == ["sells", "cooldown_skipped_buys", "min_hold_skipped_sells", "time_exits",
                                   "drawdown_halt_bar", "drawdown_skipped_buys", "loss_halt_bar", "loss_skipped_buys",
                                   "fills"]


def test_export_columns_do_not_change(folder):
    run([*B, "--export", "plain.csv"])
    code, _, err = run([*B, "--max-losses", "1", "--export", "out.csv"])
    assert (code, err) == (0, "")
    assert (folder / "out.csv").read_text().splitlines()[0] == (folder / "plain.csv").read_text().splitlines()[0]


# ----------------------------------------------------------------- runs without it are unchanged

# Exit code, stdout and stderr of these commands, recorded from the code as it was before --max-losses was added
# (git HEAD, run in a separate worktree). The last two are usage errors, so their stderr pins the usage line.
UNCHANGED_RUNS = [
    ["losses.csv"],
    B,
    [*B, "--json"],
    [*B, "--fee", "1", "--slippage", "0.5", "--position-size", "0.5", "--stats"],
    [*B, "--min-hold", "4", "--max-hold", "3", "--max-drawdown", "17"],
    [*B, "--resample", "weekly"],
    ["c.csv", *B[1:], "--fill", "open", "--stop-loss", "10", "--cooldown", "3", "--breakeven", "5"],
    ["losses.csv", "--max-drawdown", "10"],
    ["--scan", "scan", "--backtest"],
]


def before_runs():
    return json.loads((DATA / "cli_before_max_losses.json").read_text())


def test_the_recorded_runs_are_all_checked():
    assert [entry["argv"] for entry in before_runs()] == UNCHANGED_RUNS


@pytest.mark.parametrize("i", range(len(UNCHANGED_RUNS)))
def test_runs_without_it_print_exactly_what_they_printed_before(folder, i):
    entry = before_runs()[i]
    assert list(run(entry["argv"])) == [entry["code"], entry["out"], entry["err"]]
