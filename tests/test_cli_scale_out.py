"""--scale-out PCT on the command line: the c.csv hand case of test_scale_out.py through the CLI.

c.csv (tests/data/c.csv, candles), cash 1000, --short 1 --long 2, close fills:
    no option: 925.00; 5: 995.95; 9: 1016.15; 10: 925.00 (never reached); 5 with --stop-loss 10: 991.45
(the arithmetic is in test_scale_out.py).

tests/data/cli_before_scale_out.json holds, for each command in UNCHANGED_RUNS, the exit code, stdout, stderr and
--export file the command gave before --scale-out existed (git HEAD 9ab3743, run from a separate worktree, in a
folder like the one ``folder`` makes, COLUMNS=80). "changed" holds three outputs that change on purpose: --help
(one new block), the "--s" ambiguity message (it now also names --scale-out and the hidden --sc and --sca) and
"--scal 5" (unrecognized before, now short for --scale-out).
"""

import contextlib
import csv
import io
import json
import re
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import build_parser, main

DATA = Path(__file__).parent / "data"
H = ["c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CL = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, as a close-only file


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


BEFORE = json.loads((DATA / "cli_before_scale_out.json").read_text())
USAGE = BEFORE["changed"]["s"]["err"].rsplit("trading_assistant.cli: error:", 1)[0]  # the usage line, as before


# ----------------------------------------------------------------- the hand case


HEAD = """\
Bars:    11
Last:    12.20
Signal:  HOLD
RSI:     n/a
Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting
  Start cash:  1,000.00
"""

SCALE_OUT_5 = HEAD + """\
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 5     SELL       45 @      11.55  value       519.75  cost     0.00  cash       529.75  scale_out
    #3   bar 7     SELL       45 @      10.00  value       450.00  cost     0.00  cash       979.75  signal
    #4   bar 9     BUY        81 @      12.00  value       972.00  cost     0.00  cash         7.75  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the average entry; 1 partial sell, not counted as round trips
  Round trips: 1 completed, 0 made money (0%)
  Comparison              Strategy    Buy & hold
    End equity              995.95      1,220.00
    Return                  -0.41%       +22.00%
    Max drawdown            -8.41%       -20.00%
    Trades                       4             1
    Costs paid                0.00          0.00
  End cash:    7.75
  End shares:  81 @ 12.20
  End equity:  995.95
  Return:      -0.41%
Research aid only. Not financial advice.
"""

SCALE_OUT_9 = HEAD + """\
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 5     SELL       45 @      11.99  value       539.55  cost     0.00  cash       549.55  scale_out
    #3   bar 7     SELL       45 @      10.00  value       450.00  cost     0.00  cash       999.55  signal
    #4   bar 9     BUY        83 @      12.00  value       996.00  cost     0.00  cash         3.55  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Scale out:   half the shares held (rounded down), once per position, when a high reaches 9.00% above the average entry; 1 partial sell, not counted as round trips
  Round trips: 1 completed, 0 made money (0%)
  Comparison              Strategy    Buy & hold
    End equity            1,016.15      1,220.00
    Return                  +1.61%       +22.00%
    Max drawdown            -8.26%       -20.00%
    Trades                       4             1
    Costs paid                0.00          0.00
  End cash:    3.55
  End shares:  83 @ 12.20
  End equity:  1,016.15
  Return:      +1.61%
Research aid only. Not financial advice.
"""

SCALE_OUT_10 = HEAD + """\
  Trades:      3 (2 buy, 1 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00  signal
    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Scale out:   half the shares held (rounded down), once per position, when a high reaches 10.00% above the average entry; 0 partial sells, not counted as round trips
  Round trips: 1 completed, 0 made money (0%)
  Comparison              Strategy    Buy & hold
    End equity              925.00      1,220.00
    Return                  -7.50%       +22.00%
    Max drawdown           -16.51%       -20.00%
    Trades                       3             1
    Costs paid                0.00          0.00
  End cash:    10.00
  End shares:  75 @ 12.20
  End equity:  925.00
  Return:      -7.50%
Research aid only. Not financial advice.
"""

SCALE_OUT_5_STOP_10 = HEAD + """\
  Trades:      4 (2 buy, 2 sell)
  Fills (bar index is 0-based):
    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal
    #2   bar 5     SELL       45 @      11.55  value       519.75  cost     0.00  cash       529.75  scale_out
    #3   bar 6     SELL       45 @       9.90  value       445.50  cost     0.00  cash       975.25  stop
    #4   bar 9     BUY        81 @      12.00  value       972.00  cost     0.00  cash         3.25  signal
  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)
  Exits:       stop 10.00% below entry
  Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the average entry; 1 partial sell, not counted as round trips
  Round trips: 1 completed, 0 made money (0%)
  Comparison              Strategy    Buy & hold
    End equity              991.45      1,220.00
    Return                  -0.86%       +22.00%
    Max drawdown            -8.83%       -20.00%
    Trades                       4             1
    Costs paid                0.00          0.00
  End cash:    3.25
  End shares:  81 @ 12.20
  End equity:  991.45
  Return:      -0.86%
Research aid only. Not financial advice.
"""


@pytest.mark.parametrize(
    "extra, expected",
    [
        (["--scale-out", "5"], SCALE_OUT_5),
        (["--scale-out", "9"], SCALE_OUT_9),
        (["--scale-out", "10"], SCALE_OUT_10),
        (["--scale-out", "5", "--stop-loss", "10"], SCALE_OUT_5_STOP_10),
        (["--stop-loss", "10", "--scale-out", "5"], SCALE_OUT_5_STOP_10),
    ],
    ids=["5", "9", "10", "5 stop 10", "stop 10 first"],
)
def test_hand_case(folder, extra, expected):
    assert run([*H, *extra]) == (0, expected, "")


def test_decimals_and_the_equals_form(folder):
    # 5.0 and --scale-out=5 are the same as 5. 9.5: level 11 * 1.095 = 12.045 is above every high while held
    # (12, 12, 10.2), and 12 * 1.095 = 13.14 above bar 10's 12.4: as without it, 925.00.
    assert run([*H, "--scale-out", "5.0"])[1] == SCALE_OUT_5
    assert run([*H, "--scale-out=5"])[1] == SCALE_OUT_5
    code, out, err = run([*H, "--scale-out", "9.5"])
    assert (code, err) == (0, "")
    assert "when a high reaches 9.50% above the average entry; 0 partial sells" in out
    assert "  End equity:  925.00\n" in out


def test_fill_open(folder):
    # Bar 4: int(1000 / 10.8) = 92 @ 10.80 = 993.60, cash 6.40; level 10.8 * 1.05 = 11.34.
    # Bar 5: opens 11 (below), high 12: 46 @ 11.34 = 521.64, cash 528.04.
    # Bar 7: signal SELL at the open, 46 @ 9.80 = 450.80, cash 978.84; round trip 521.64 + 450.80 - 993.60 = -21.16.
    # Bar 9: BUY at the open, int(978.84 / 10.8) = 90 @ 10.80 = 972, cash 6.84; level 11.34 again.
    # Bar 10: opens 12, above the level (a gap): 45 @ 12.00 = 540, cash 546.84.
    # End 546.84 + 45 * 12.2 = 546.84 + 549 = 1095.84.
    code, out, err = run([*H, "--fill", "open", "--scale-out", "5"])
    assert (code, err) == (0, "")
    fills = [line for line in out.splitlines() if line.startswith("    #")]
    assert [line.split()[2:5] + [line.split()[-1]] for line in fills] == [
        ["4", "BUY", "92", "signal"],
        ["5", "SELL", "46", "scale_out"],
        ["7", "SELL", "46", "signal"],
        ["9", "BUY", "90", "signal"],
        ["10", "SELL", "45", "scale_out"],
    ]
    assert "11.34" in fills[1] and "528.04" in fills[1]
    assert "12.00" in fills[4] and "546.84" in fills[4]
    assert "; 2 partial sells, not counted as round trips" in out
    assert "  Round trips: 1 completed, 0 made money (0%)\n" in out
    assert "  End equity:  1,095.84\n" in out


def test_works_with_a_stop_and_a_cooldown(folder):
    # --cooldown needs the stop, not the scale-out. The stop sells on bar 6, so bars 7 and 8 are blocked; the buy is
    # due on bar 9 and fills: the same fills as without the cooldown (991.45). The scale-out on bar 5 started none.
    code, out, err = run([*H, "--scale-out", "5", "--stop-loss", "10", "--cooldown", "2"])
    assert (code, err) == (0, "")
    assert "  Cooldown:    2 bars after a stop, trail or atr exit; 0 buys skipped\n" in out
    assert out.replace("  Cooldown:    2 bars after a stop, trail or atr exit; 0 buys skipped\n", "") == SCALE_OUT_5_STOP_10


def test_chart_marks_the_partial_sale(folder):
    code, out, err = run([*H, "--scale-out", "5", "--chart"])
    assert (code, err) == (0, "")
    assert "Chart:   close, 11 bars, B = buy, S = sell" in out


# ----------------------------------------------------------------- --json and --export


def test_json_only_adds_the_two_scale_out_keys(folder):
    code, out, err = run([*H, "--scale-out", "5", "--json"])
    assert (code, err) == (0, "")
    data = json.loads(out)["backtest"]
    plain = json.loads(run([*H, "--json"])[1])["backtest"]
    assert [k for k in data if k not in ("scale_out_pct", "scale_out_exits")] == list(plain)
    assert [f["reason"] for f in data["fills"]] == ["signal", "scale_out", "signal", "signal"]
    assert [f["shares"] for f in data["fills"]] == [90, 45, 45, 81]
    assert (data["trades"], data["buys"], data["sells"]) == (4, 2, 2)
    assert (data["round_trips"], data["winning_round_trips"]) == (1, 0)
    assert data["final_equity"] == pytest.approx(995.95)


def test_export_has_the_reason_column(folder):
    code, out, err = run([*H, "--scale-out", "5", "--export", "E.csv"])
    assert (code, err) == (0, "")
    assert "  Exported:    11 rows to E.csv\n" in out
    rows = list(csv.DictReader((folder / "E.csv").open()))
    assert [r["reason"] for r in rows] == ["", "", "", "", "signal", "scale_out", "", "signal", "", "signal", ""]
    assert (rows[5]["action"], rows[5]["shares"], rows[5]["price"], rows[5]["position"]) == ("SELL", "45", "11.55", "45")


# ----------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "argv, code, message",
    [
        (["c.csv", "--scale-out", "5"], 2, "trading_assistant.cli: error: --scale-out only makes sense together with --backtest"),
        ([*H, "--scale-out", "0"], 2, "trading_assistant.cli: error: --scale-out must be above 0, got 0"),
        ([*H, "--scale-out", "-1"], 2, "trading_assistant.cli: error: --scale-out must be above 0, got -1"),
        ([*H, "--scale-out", "-0.5"], 2, "trading_assistant.cli: error: --scale-out must be above 0, got -0.5"),
        ([*H, "--scale-out", "nan"], 2, "trading_assistant.cli: error: --scale-out must be above 0, got nan"),
        ([*H, "--scale-out", "inf"], 2, "trading_assistant.cli: error: --scale-out must be a finite number, got inf"),
        ([*H, "--scale-out", "abc"], 2, "trading_assistant.cli: error: argument --scale-out: invalid float value: 'abc'"),
        ([*H, "--scale-out", ""], 2, "trading_assistant.cli: error: argument --scale-out: invalid float value: ''"),
        ([*H, "--scale-out"], 2, "trading_assistant.cli: error: argument --scale-out: expected one argument"),
        ([*H, "--scale-out", "5", "--resample", "weekly"], 2,
         "trading_assistant.cli: error: --scale-out cannot be combined with --resample yet"),
        (["--scan", "scan", "--scale-out", "5"], 2, "trading_assistant.cli: error: --scale-out cannot be combined with --scan"),
        (["--sc", "scan", "--scale-out", "5"], 2, "trading_assistant.cli: error: --scale-out cannot be combined with --scan"),
        (["--scale-out", "5", "--scan", "scan"], 2, "trading_assistant.cli: error: --scale-out cannot be combined with --scan"),
        ([*H, "--scale-out", "5", "--cooldown", "2"], 2,
         "trading_assistant.cli: error: --cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop"),
    ],
)
def test_usage_errors(folder, argv, code, message):
    got_code, out, err = run(argv)
    assert (got_code, out) == (code, "")
    assert err.startswith("usage: trading_assistant.cli ")
    assert err.splitlines()[-1] == message


def test_usage_errors_print_the_usage_line_as_before(folder):
    assert run([*H, "--scale-out", "0"])[2] == USAGE + "trading_assistant.cli: error: --scale-out must be above 0, got 0\n"


def test_a_close_only_file_is_a_data_error(folder):
    code, out, err = run([*CL, "--scale-out", "5"])
    assert (code, out) == (1, "")
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")
    assert "\n" not in err.rstrip("\n")  # one line, no usage


# ----------------------------------------------------------------- help and usage


def _option_blocks(help_text):
    """{first option string: its help block, whitespace collapsed} for the options section."""
    section = help_text.split("\noptions:\n", 1)[1].split("\n\n", 1)[0]
    blocks = re.split(r"\n(?=  -)", section)
    return {block.split()[0].rstrip(","): " ".join(block.split()) for block in blocks}


def test_help_adds_only_the_scale_out_block_after_max_losses(folder):
    code, out, err = run(["--help"])
    assert (code, err) == (0, "")
    before_out = BEFORE["changed"]["help"]["out"]
    before, now = _option_blocks(before_out), _option_blocks(out)
    names = list(before)
    i = names.index("--max-losses") + 1
    expected = [*names[:i], "--scale-out", "--add-on", "--max-adds", *names[i:]]
    expected = [*expected[: expected.index("--stats") + 1], "--trade-list", *expected[expected.index("--stats") + 1 :]]
    assert list(now) == [*expected[: expected.index("--chart") + 1], "--explain", *expected[expected.index("--chart") + 1 :]]
    assert {k: v for k, v in now.items() if k not in ("--scale-out", "--add-on", "--max-adds", "--trade-list", "--explain")} == before
    assert out.split("\noptions:\n")[0] == before_out.split("\noptions:\n")[0]  # usage and description
    assert out.split("\n\n")[-1] == before_out.split("\n\n")[-1]  # the disclaimer epilog
    # Nothing else moved: taking the new block out gives the old help, character for character.
    out = out[: out.index("\n  --trade-list ")] + out[out.index("\n  --config FILE") :]  # added later, after --stats
    out = out[: out.index("\n  --explain ")] + out[out.index("\n  --candles") :]  # added later, after --chart
    start = out.index("\n  --scale-out PCT")
    end = out.index("\n  --export FILE")
    assert out[:start] + out[end:] == before_out


def test_help_describes_it(folder):
    text = _option_blocks(run(["--help"])[1])["--scale-out"]
    assert text.startswith("--scale-out PCT with --backtest, sell half the shares held (rounded down) once per position")
    assert "plus PCT% (above 0)" in text
    assert "A partial sale is not a round trip" in text and "Its fills say scale_out" in text
    assert "(reads a candle file; cannot be combined with --resample yet)" in text


def test_usage_line_does_not_list_it(folder):
    out = run(["--help"])[1]
    assert "--scale-out" not in out.split("\n\n", 1)[0]
    assert out.startswith(USAGE.rstrip("\n"))


def test_hidden_scan_aliases_are_not_in_help(folder):
    out = run(["--help"])[1]
    assert "--sc " not in out and "--sca " not in out and "--sc," not in out


# ----------------------------------------------------------------- runs without it: exactly as before


UNCHANGED_RUNS = [
    ["c.csv"],
    H,
    [*H, "--stop-loss", "10"],
    [*H, "--take-profit", "5", "--fill", "open"],
    [*H, "--trailing-stop", "10", "--stats"],
    [*H, "--breakeven", "5", "--stop-loss", "10", "--cooldown", "2"],
    [*H, "--max-hold", "1", "--export", "E.csv"],
    [*H, "--json"],
    [*H, "--json", "--stop-loss", "5", "--stats", "--export", "E.csv"],
    [*H, "--chart", "--atr-stop", "--atr-period", "2"],
    [*H, "--risk-pct", "1", "--atr-period", "2"],
    [*CL, "--max-drawdown", "5", "--min-hold", "2", "--max-losses", "1"],
    [*CL, "--resample", "weekly"],
    ["c.csv", "--b", "--short", "1", "--long", "2", "--sl", "1", "--str", "breakout"],
    ["c.csv", "--take-profit", "5"],
    [*CL, "--stop-loss", "5"],
    [*H, "--stop-loss", "0"],
    [*H, "--stop-loss", "5", "--resample", "weekly"],
    [*H, "--cooldown", "2"],
    [*H, "--st", "5"],
    ["--scan", "scan"],
    ["--sc", "scan"],
    ["--sca", "scan", "--json"],
    ["--sc=scan", "--top", "1"],
    ["--scan", "scan", "--stop-loss", "5"],
    ["--sc", "scan", "c.csv"],
]


def test_the_recorded_runs_are_all_checked():
    assert [entry["argv"] for entry in BEFORE["unchanged"]] == UNCHANGED_RUNS


@pytest.mark.parametrize("i", range(len(UNCHANGED_RUNS)), ids=[" ".join(a) for a in UNCHANGED_RUNS])
def test_runs_without_it_print_exactly_what_they_printed_before(folder, i):
    entry = BEFORE["unchanged"][i]
    assert list(run(entry["argv"])) == [entry["code"], entry["out"], entry["err"]]
    export = folder / "E.csv"
    assert (export.read_text() if export.exists() else None) == entry["export"]
    assert "Scale out" not in entry["out"]


# ----------------------------------------------------------------- shortened option names


def test_sc_and_sca_still_mean_scan(folder):
    scan = run(["--scan", "scan"])
    assert scan[0] == 0 and scan[1].startswith("Scan:    scan, 1 scored, 0 skipped")
    for argv in (["--sc", "scan"], ["--sca", "scan"], ["--sc=scan"], ["--sca=scan"]):
        assert run(argv) == scan, argv
    for scan_mode in (False, True):
        for token in ("--sc", "--sca"):
            args = build_parser(scan=scan_mode).parse_args(([] if scan_mode else ["x.csv"]) + [token, "scan"])
            assert args.scan == "scan" and args.scale_out is None, token


def test_sc_errors_still_say_scan(folder):
    assert run(["--sc"])[2].splitlines()[-1] == "trading_assistant.cli: error: argument --scan: expected one argument"


@pytest.mark.parametrize("token", ["--scal", "--scale", "--scale-", "--scale-o", "--scale-ou", "--scale-out"])
def test_scal_and_longer_mean_scale_out_now(folder, token):
    # Before, each of these was "unrecognized arguments" (exit 2); see the recorded "scal" run.
    assert run([*H, token, "5"]) == (0, SCALE_OUT_5, "")
    assert run([*H, f"{token}=5"]) == (0, SCALE_OUT_5, "")


def test_scal_was_unrecognized_before(folder):
    before = BEFORE["changed"]["scal"]
    assert (before["code"], before["out"]) == (2, "")
    assert before["err"] == USAGE + "trading_assistant.cli: error: unrecognized arguments: --scal 5\n"


def test_the_s_message_now_also_names_scale_out_and_the_hidden_scan_aliases(folder):
    # The one message that changes; before it read
    # "--s could match --short, --slippage, --stop-loss, --strategy, --stats, --scan".
    before = BEFORE["changed"]["s"]
    assert before["err"].splitlines()[-1] == (
        "trading_assistant.cli: error: ambiguous option: --s could match --short, --slippage, --stop-loss, "
        "--strategy, --stats, --scan"
    )
    assert run([*H, "--s", "5"]) == (2, "", USAGE + (
        "trading_assistant.cli: error: ambiguous option: --s could match --short, --slippage, --stop-loss, "
        "--scale-out, --strategy, --stats, --scan, --sc, --sca\n"
    ))


NEW = {"--scale-out", "--sc", "--sca"}


@pytest.mark.parametrize("scan_mode", [False, True])
def test_every_option_name_that_worked_before_still_means_the_same_option(scan_mode):
    # Before --scale-out the parser knew every option string it knows now except the three in NEW. argparse takes an
    # exact option string, or else a prefix of exactly one; every prefix that did so then must give the same dest.
    parser = build_parser(scan=scan_mode)
    known = parser._option_string_actions
    old = {name: action.dest for name, action in known.items() if name.startswith("--") and name not in NEW}
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
            value = [] if action.nargs == 0 else [sorted(action.choices)[0]] if action.choices else ["1"]
            argv = ([] if scan_mode else ["x.csv"]) + [token, *value]
            args, extra = build_parser(scan=scan_mode).parse_known_args(argv)
            assert extra == [], token
            assert getattr(args, dest) not in (None, False), (token, dest)
            assert args.scale_out is None, token
            checked += 1
    assert checked > 150
    # --sc and --sca were among them: prefixes of --scan only.
    assert [n for n in old if n.startswith("--sc")] == ["--scan"]


def test_names_that_were_ambiguous_before_are_still_errors(folder):
    old = [n for n in build_parser()._option_string_actions if n.startswith("--") and n not in NEW]
    prefixes = sorted({n[:e] for n in old for e in range(3, len(n)) if n[:e] not in old and sum(o.startswith(n[:e]) for o in old) > 1})
    assert "--s" in prefixes and "--st" in prefixes
    for prefix in prefixes:
        code, out, err = run(["c.csv", "--backtest", prefix, "5"])
        assert (code, out) == (2, ""), prefix
        assert "ambiguous option" in err.splitlines()[-1], prefix
