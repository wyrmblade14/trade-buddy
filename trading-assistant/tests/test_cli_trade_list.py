"""--trade-list on the command line: the c.csv hand cases of test_trade_list.py through the CLI.

c.csv (tests/data/c.csv, candles), cash 1000, --short 1 --long 2, close fills (the arithmetic is in
test_trade_list.py): one round trip 4 -> 7 and 75 shares bought on bar 9 still held; with --scale-out 5 the round
trip's proceeds are 969.75 and 81 shares are held; with --stop-loss 10 the round trip ends on bar 6 (stop).

tests/data/cli_before_trade_list.json holds what the code gave before --trade-list existed (git HEAD 145253b, run
from a separate worktree, in a folder like the one ``folder`` makes, COLUMNS=80):

* "unchanged": commands that must give exactly the same exit code, stdout, stderr and --export file now,
  among them every use of --tr and --tra (argparse abbreviations of --trailing-stop, which --trade-list would make
  ambiguous without the hidden aliases);
* "changed": commands that were rejected ("unrecognized arguments") and now mean --trade-list;
* "help": the --help text;
* "prefixes": what every abbreviation of every option name (and of --trade-list) resolved to, with a price file
  and with --scan (null: not an option name).
"""

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import build_parser, main

DATA = Path(__file__).parent / "data"
H = ["c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CL = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, as a close-only file
DISCLAIMER = "Research aid only. Not financial advice.\n"

BEFORE = json.loads((DATA / "cli_before_trade_list.json").read_text())
BEFORE_RUNS = {tuple(r["argv"]): r for r in BEFORE["unchanged"]}
USAGE = BEFORE_RUNS[("c.csv", "--tr", "5")]["err"].rsplit("trading_assistant.cli: error:", 1)[0]


def make_folder(path):
    shutil.copy(DATA / "c.csv", path / "c.csv")
    (path / "closes.csv").write_text("date,close\n" + "".join(f"2026-01-{i:02d},{c}\n" for i, c in enumerate(CLOSES, 1)))
    (path / "scan").mkdir()
    shutil.copy(DATA / "c.csv", path / "scan" / "c.csv")


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


def before_out(argv):
    run_ = BEFORE_RUNS[tuple(argv)]
    assert run_["code"] == 0 and run_["err"] == ""
    return run_["out"]


def with_table(out, table, before_line=DISCLAIMER):
    """``out`` with ``table`` put right before the first line equal to (or starting with) ``before_line``."""
    i = out.index("\n" + before_line) + 1 if not out.startswith(before_line) else 0
    return out[:i] + table + out[i:]


UNREALIZED = "  (unrealized: marked at the last close, no selling costs)"
HEADER = (
    "Trade list (bar index is 0-based)\n"
    "  #     Entry  Exit  Bars   Shares        Outlay      Proceeds          P/L    Return  Reason\n"
)
PLAIN_TABLE = (
    HEADER
    + "  1         4     7     3       90        990.00        900.00       -90.00    -9.09%  signal\n"
    + "  open      9  open     1       75        900.00        915.00       +15.00    +1.67%  -" + UNREALIZED + "\n"
    + "  1 completed, 0 made money (0%), 1 open (unrealized)\n"
)
SCALE_OUT_TABLE = (
    HEADER
    + "  1         4     7     3       90        990.00        969.75       -20.25    -2.05%  signal\n"
    + "  open      9  open     1       81        972.00        988.20       +16.20    +1.67%  -" + UNREALIZED + "\n"
    + "  1 completed, 0 made money (0%), 1 open (unrealized)\n"
)
STOP_TABLE = (
    HEADER
    + "  1         4     6     2       90        990.00        891.00       -99.00   -10.00%  stop\n"
    + "  open      9  open     1       75        900.00        915.00       +15.00    +1.67%  -" + UNREALIZED + "\n"
    + "  1 completed, 0 made money (0%), 1 open (unrealized)\n"
)


# ----------------------------------------------------------------- the hand cases: the report as before, then the table


@pytest.mark.parametrize(
    "extra, table",
    [([], PLAIN_TABLE), (["--scale-out", "5"], SCALE_OUT_TABLE), (["--stop-loss", "10"], STOP_TABLE)],
    ids=["plain", "scale-out-5", "stop-loss-10"],
)
def test_hand_cases(folder, extra, table):
    code, out, err = run(H + extra + ["--trade-list"])
    assert (code, err) == (0, "")
    assert out == with_table(before_out(H + extra), table)


def test_the_plain_run_line_for_line(folder):
    # The whole output, written out, so a change to the report around the table shows here too.
    code, out, _ = run(H + ["--trade-list"])
    assert code == 0
    assert out == (
        "Bars:    11\nLast:    12.20\nSignal:  HOLD\nRSI:     n/a\n"
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
        "  Start cash:  1,000.00\n"
        "  Trades:      3 (2 buy, 1 sell)\n"
        "  Fills (bar index is 0-based):\n"
        "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n"
        "    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00\n"
        "    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              925.00      1,220.00\n"
        "    Return                  -7.50%       +22.00%\n"
        "    Max drawdown           -16.51%       -20.00%\n"
        "    Trades                       3             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    10.00\n  End shares:  75 @ 12.20\n  End equity:  925.00\n  Return:      -7.50%\n"
        + PLAIN_TABLE
        + DISCLAIMER
    )


# ----------------------------------------------------------------- where the table goes


def test_after_the_risk_and_return_block_and_before_the_chart(folder):
    code, out, _ = run(H + ["--stats", "--chart", "--trade-list"])
    assert code == 0
    assert out == with_table(before_out(H + ["--stats", "--chart"]), PLAIN_TABLE, before_line="Chart:")
    assert out.index("Risk and return") < out.index("Trade list") < out.index("Chart:")


def test_before_the_chart_without_stats(folder):
    code, out, _ = run(H + ["--chart", "--trade-list"])
    assert code == 0
    assert out == with_table(before_out(H + ["--chart"]), PLAIN_TABLE, before_line="Chart:")


def test_after_the_risk_and_return_block(folder):
    code, out, _ = run(H + ["--stats", "--trade-list"])
    assert code == 0
    assert out == with_table(before_out(H + ["--stats"]), PLAIN_TABLE)


def test_with_export_the_file_is_unchanged(folder):
    argv = H + ["--export", "out.csv", "--stats"]
    code, out, _ = run(argv + ["--trade-list"])
    assert code == 0
    assert out == with_table(before_out(argv), PLAIN_TABLE)
    assert (folder / "out.csv").read_text() == BEFORE_RUNS[tuple(argv)]["export"]


@pytest.mark.parametrize(
    "argv",
    [
        H + ["--fee", "495", "--max-hold", "3", "--stats"],  # the bar 7 sale refused, bar 8 sells for 0.00
        H + ["--position-size", "0.5", "--min-hold", "5", "--stats"],  # an add-on buy, held to the end
    ],
    ids=["refused-sale", "add-on-buy"],
)
def test_other_hand_cases_only_add_the_table(folder, argv):
    code, out, _ = run(argv + ["--trade-list"])
    assert code == 0
    before = before_out(argv)
    assert out.startswith(before[: -len(DISCLAIMER)]) and out.endswith(DISCLAIMER)
    table = out[len(before) - len(DISCLAIMER) : -len(DISCLAIMER)]
    assert table.startswith(HEADER)
    if "--fee" in argv:
        assert "  1         4     8     4       45        990.00          0.00      -990.00  -100.00%  time\n" in table
        assert table.endswith("  1 completed, 0 made money (0%)\n")
    else:
        assert "  open      4  open     6       87        999.00      1,061.40       +62.40    +6.25%  -" in table
        assert table.endswith("  0 completed, 1 open (unrealized)\n")


def test_no_trades_is_one_line(folder):
    code, out, _ = run(["c.csv", "--backtest", "--cash", "5", "--short", "1", "--long", "2", "--trade-list"])
    assert code == 0
    assert "  Trades:      0 (0 buy, 0 sell)\n" in out
    assert out.endswith("  Return:      +0.00%\nTrade list: no trades\n" + DISCLAIMER)


# ----------------------------------------------------------------- no candle file needed, --resample allowed


def test_close_only_file(folder):
    code, out, err = run(CL + ["--trade-list"])
    assert (code, err) == (0, "")
    assert out == with_table(before_out(CL), PLAIN_TABLE)  # the same closes, so the same trades


def test_close_only_file_with_stats_and_chart(folder):
    code, out, _ = run(CL + ["--stats", "--chart", "--trade-list"])
    assert code == 0
    assert out == with_table(before_out(CL + ["--stats", "--chart"]), PLAIN_TABLE, before_line="Chart:")


def test_resample(folder):
    argv = ["closes.csv", "--backtest", "--resample", "weekly", "--stats"]
    code, out, err = run(argv + ["--trade-list"])
    assert (code, err) == (0, "")
    before = before_out(argv)
    assert out.startswith(before[: -len(DISCLAIMER)]) and out.endswith(DISCLAIMER)
    assert "Trade list" in out[len(before) - len(DISCLAIMER) :]


# ----------------------------------------------------------------- --json: a trade_list array, round_trips untouched

KEYS = ["open", "entry_bar", "exit_bar", "bars_held", "shares", "outlay", "proceeds", "pnl", "return_pct", "reason"]


def _row(open_, entry, exit_, bars, shares, outlay, proceeds, reason):
    pnl = proceeds - outlay
    values = [open_, entry, exit_, bars, shares, outlay, proceeds, pnl, pnl / outlay * 100, reason]
    return dict(zip(KEYS, values))


def _cells(row, number):
    """The text table's cells for a trade_list object, formatted as the table formats them."""
    return [
        "open" if row["open"] else str(number), str(row["entry_bar"]),
        "open" if row["exit_bar"] is None else str(row["exit_bar"]), str(row["bars_held"]), str(row["shares"]),
        f"{row['outlay']:,.2f}", f"{row['proceeds']:,.2f}", f"{row['pnl']:+,.2f}", f"{row['return_pct']:+.2f}%",
        row["reason"] or "-",
    ]


OPEN_75 = _row(True, 9, None, 1, 75, 900.0, 75 * 12.2, None)


@pytest.mark.parametrize(
    "extra, rows",
    [
        ([], [_row(False, 4, 7, 3, 90, 990.0, 900.0, "signal"), OPEN_75]),
        (["--scale-out", "5"], [_row(False, 4, 7, 3, 90, 990.0, 969.75, "signal"), _row(True, 9, None, 1, 81, 972.0, 81 * 12.2, None)]),
        (["--stop-loss", "10"], [_row(False, 4, 6, 2, 90, 990.0, 891.0, "stop"), OPEN_75]),
        (["--cash", "5"], []),  # no trades: an empty list (the later --cash wins)
        (["--stats", "--export", "out.csv"], [_row(False, 4, 7, 3, 90, 990.0, 900.0, "signal"), OPEN_75]),
    ],
    ids=["plain", "scale-out-5", "stop-loss-10", "no-trades", "stats-export"],
)
def test_json_trade_list(folder, extra, rows):
    code, out, err = run(H + extra + ["--json", "--trade-list"])
    assert (code, err) == (0, "")
    data = json.loads(out)
    backtest = data["backtest"]
    assert list(backtest)[-1] == "trade_list"  # the last key, after stats and export
    got = backtest.pop("trade_list")
    assert [list(row) for row in got] == [KEYS] * len(rows)
    assert got == [{k: pytest.approx(v) if isinstance(v, float) else v for k, v in row.items()} for row in rows]
    # Everything else, round_trips and winning_round_trips included, is the JSON of the run without --trade-list.
    exported = (folder / "out.csv").read_text() if "--export" in extra else None
    assert run(H + extra + ["--json"]) == (0, json.dumps(data, indent=2) + "\n", "")
    if exported is not None:
        assert (folder / "out.csv").read_text() == exported  # --export writes the same file either way
    done = [row for row in got if not row["open"]]
    assert (len(done), sum(row["pnl"] > 0 for row in done)) == (backtest["round_trips"], backtest["winning_round_trips"])
    # The numbers are the text table's, cell for cell.
    _, text, _ = run(H + extra + ["--trade-list"])
    if not got:
        assert "Trade list: no trades\n" in text
        return
    lines = text.split("Trade list (bar index is 0-based)\n", 1)[1].splitlines()[1 : 1 + len(got)]
    assert [line.split()[:10] for line in lines] == [_cells(row, i) for i, row in enumerate(got, 1)]


# ----------------------------------------------------------------- usage errors


@pytest.mark.parametrize("flag", ["--trade-list", "--trad", "--trade-l"])
def test_needs_backtest(folder, flag):
    code, out, err = run(["c.csv", flag])
    assert (code, out) == (2, "")
    assert err == USAGE + "trading_assistant.cli: error: --trade-list only makes sense together with --backtest\n"


@pytest.mark.parametrize("flag", ["--trade-list", "--trad"])
def test_not_with_scan(folder, flag):
    code, out, err = run(["--scan", "scan", flag])
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --trade-list cannot be combined with --scan\n")


def test_written_twice_is_fine(folder):
    assert run(H + ["--trade-list", "--trade-list"]) == run(H + ["--trade-list"])


# ----------------------------------------------------------------- nothing else changed


@pytest.mark.parametrize("record", BEFORE["unchanged"], ids=[" ".join(r["argv"]) for r in BEFORE["unchanged"]])
def test_commands_that_worked_before_are_unchanged(folder, record):
    code, out, err = run(record["argv"])
    assert (code, out, err) == (record["code"], record["out"], record["err"])
    export = folder / "out.csv"
    assert (export.read_text() if export.exists() else None) == record["export"]


@pytest.mark.parametrize("record", BEFORE["changed"], ids=[" ".join(r["argv"]) for r in BEFORE["changed"]])
def test_what_was_rejected_before_now_means_trade_list(folder, record):
    assert record["code"] == 2 and "unrecognized arguments" in record["err"]  # as recorded before
    argv = record["argv"]
    flag = argv[-1]
    code, out, err = run(argv)
    if "--scan" in argv:
        assert code == 2 and err.endswith("error: --trade-list cannot be combined with --scan\n")
    elif "--backtest" not in argv:
        assert code == 2 and err.endswith("error: --trade-list only makes sense together with --backtest\n")
    else:
        assert (code, err) == (0, "")
        assert out == with_table(before_out(H), PLAIN_TABLE), flag


def _resolve(parser, token):
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            r = parser._parse_optional(token)
    except SystemExit:
        return "error: " + err.getvalue().strip().splitlines()[-1].split("error: ", 1)[1]
    r = r[0] if isinstance(r, list) else r
    return None if r[0] is None else r[0].option_strings[0]


@pytest.mark.parametrize("mode", ["file", "scan"])
def test_every_shortened_option_name_means_what_it_meant(mode):
    parser = build_parser(scan=mode == "scan")
    before = BEFORE["prefixes"][mode]
    now = {token: _resolve(parser, token) for token in before}
    new = {"--trad", "--trade", "--trade-", "--trade-l", "--trade-li", "--trade-lis", "--trade-list"}
    assert {t: before[t] for t in new} == dict.fromkeys(new)  # not option names before
    assert {t: now[t] for t in new} == dict.fromkeys(new, "--trade-list")
    assert {t: now[t] for t in before if t not in new | {"--a"}} == {t: before[t] for t in before if t not in new | {"--a"}}
    assert now["--a"] == before["--a"] + ", --add-on"  # still ambiguous; --add-on came later and is named too
    assert now["--tr"] == now["--tra"] == now["--trai"] == "--trailing-stop"
    assert now["--e"] == now["--ex"] == now["--exp"] == "--export"  # hidden aliases, added with --explain
    explain = {"--expl", "--expla", "--explai", "--explain"}  # rejected before --explain existed
    assert {t: _resolve(parser, t) for t in explain} == dict.fromkeys(explain, "--explain")
    # ...and no option name has an abbreviation that was not there before, apart from --trade-list's and --explain's.
    names = [s for a in parser._actions for s in a.option_strings if s.startswith("--")]
    add_on = {"--ad", "--add", "--add-", "--add-o", "--add-on", "--max-a", "--max-ad", "--max-add", "--max-adds"}  # added later
    assert {n[:i] for n in names for i in range(3, len(n) + 1)} - set(before) == explain | add_on


def test_help_lists_it_after_stats_and_the_usage_line_is_unchanged(folder):
    code, out, err = run(["--help"])
    assert (code, err) == (0, "")
    before = BEFORE["help"]
    out = out[: out.index("\n  --explain ")] + out[out.index("\n  --candles") :]  # added later, after --chart
    out = out[: out.index("\n  --add-on ")] + out[out.index("\n  --export FILE") :]  # added later, after --scale-out
    start = out.index("\n  --trade-list ")
    end = out.index("\n  --config FILE")
    assert out[:start] + out[end:] == before  # taking the new block out gives the old help, character for character
    block = out[start:end]
    assert "with --backtest" in block and "--resample" in block and "unrealized" in block
    assert out[:start].endswith("statistics block")  # right after --stats
    assert "--trade-list" not in out.split("\noptions:\n")[0]  # not in the usage line
    assert "\n  --tr " not in out and "\n  --tra " not in out and "--tr," not in out  # the aliases stay hidden
