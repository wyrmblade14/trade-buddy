"""``python -m trading_assistant.walkforward ... --strategy NAME --grid KEY=LIST --param KEY=VALUE``.

``tests/data/wf_cli_before_strategy.json`` was recorded with the command as it was before the three options
existed (git 924f482, Python 3.12, COLUMNS=80), in a folder holding ``wf.csv`` (tests/data/wf.csv) and
``sideways.csv`` (the sideways sample): 25 commands (text, --json, --csv, --warmup, --help, usage errors, data
errors; stdout, stderr, exit code and the files left behind) and every shortened option name (134 runs: each
prefix of each option, old and new, with a separate value and with ``=``, after a valid command).

Hand-worked cases use wf.csv, 18 closes (bars 0-17: 10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 11, 10, 11, 13,
14, 15, 14), cash 1000. A signal on bar t fills at the close of bar t + 1.
"""

import contextlib
import io
import json
from pathlib import Path

import pytest

from trading_assistant import backtest as _backtest
from trading_assistant import walkforward
from trading_assistant.cli import DISCLAIMER, load_price_table
from trading_assistant.samples import sample_csv_rows
from trading_assistant.strategies import STRATEGIES
from trading_assistant.sweep import OVERFIT_WARNING
from trading_assistant.walkforward import run_walk_forward

DATA = Path(__file__).resolve().parent / "data"
BEFORE = json.loads((DATA / "wf_cli_before_strategy.json").read_text())
WF_TEXT = (DATA / "wf.csv").read_text()
PROG = "trading_assistant.walkforward: error: "
CHOICES = ", ".join(f"'{name}'" for name in STRATEGIES)
SHORT_REFUSED = ("cannot be combined with --strategy, --grid or --param; give sma_cross's windows as --strategy"
                 " sma_cross --grid short=LIST --grid long=LIST")
MOMENTUM = ["wf.csv", "--strategy", "momentum", "--param", "window=4", "--grid", "threshold=0,5", "--train", "4",
            "--test", "7", "--cash", "1000"]
TAIL = f"{OVERFIT_WARNING}\n{DISCLAIMER}\n"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")  # the width the help and usage lines were recorded at
    (tmp_path / "wf.csv").write_text(WF_TEXT)
    (tmp_path / "sideways.csv").write_text("".join(",".join(r) + "\n" for r in sample_csv_rows("sideways")))
    return tmp_path


def run(argv):
    """``(exit code, stdout, stderr)`` of the command, usage errors included."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = walkforward.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def leftovers(folder):
    """The files a run left in the folder besides the two price files (read, then removed), as recorded."""
    found = {}
    for path in sorted(folder.iterdir()):
        if path.name not in ("wf.csv", "sideways.csv"):
            found[path.name] = path.read_text()
            path.unlink()
    return found


def norm(text):
    return " ".join(text.split())


OLD_DESCRIPTION = ("Walk-forward test of the SMA crossover: pick the best window pair on each train block, then run it"
                   " on the test block that follows.")
NEW_DESCRIPTION = ("Walk-forward test of the SMA crossover (or of --strategy): pick the best window pair (or parameter"
                   " set) on each train block, then run it on the test block that follows.")
NEW_OPTIONS = (
    "--strategy NAME walk-forward this strategy instead of SMA crossover pairs, one of: sma_cross, rsi_reversion,"
    " breakout, ema_cross, momentum, zscore_reversion, hull_trend; --short and --long cannot be used with it, --grid"
    " or --param (with --warmup its signal is warmed up on the bars its first signal needs)"
    " --grid KEY=LIST values of one --strategy parameter to try on each train block, e.g. window=10,20,30"
    " (repeatable; every combination is tried)"
    " --param KEY=VALUE one fixed value for a --strategy parameter, e.g. threshold=0.5 (repeatable); parameters in"
    " neither --grid nor --param keep their defaults"
)


def test_without_the_new_options_every_command_is_unchanged_except_help(folder):
    assert len(BEFORE["commands"]) == 25
    for record in BEFORE["commands"]:
        code, out, err = run(record["argv"])
        files = leftovers(folder)
        if record["argv"][-1:] == ["--help"]:
            # The usage line is the old one, byte for byte; the rest is the old help with the new description and
            # the three new options last (argparse widens the option column for --param KEY=VALUE).
            assert (code, err, files) == (0, "", {})
            assert out.split("\n\n")[0] == record["stdout"].split("\n\n")[0]
            assert norm(out) == norm(record["stdout"]).replace(norm(OLD_DESCRIPTION), NEW_DESCRIPTION).replace(
                DISCLAIMER, NEW_OPTIONS + " " + DISCLAIMER)
            continue
        assert (code, out, err, files) == (record["code"], record["stdout"], record["stderr"], record["files"]), \
            record["argv"]


def parse(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            return vars(walkforward.build_parser().parse_args(argv))
        except SystemExit:
            return None


def test_shortened_option_names(folder):
    # Before: 134 runs. Changed: -h/--h.../--help with a separate value (the new help); "--=5" (the empty prefix
    # now also lists --st, --strategy, --grid, --param); --s/--s=5 (ambiguous as before, now also --st and
    # --strategy); --g.../--grid and --p.../--param (were unrecognized arguments, now the options: with the
    # base command's --short they are refused); --str.../--strategy (were unrecognized, now --strategy, and 5
    # is not a strategy). --st is a hidden exact alias of --step, so it still means --step.
    assert len(BEFORE["abbreviations"]) == 134
    help_now = run(["wf.csv", "--help"])[1]
    counts = dict.fromkeys(["same", "help", "empty", "s", "grid/param", "strategy"], 0)
    for record in BEFORE["abbreviations"]:
        argv, old_err = record["argv"], record["stderr"]
        option = argv[11].split("=")[0]
        code, out, err = run(argv)
        assert leftovers(folder) == record["files"], argv
        usage = old_err.split(PROG)[0]
        if record["stdout"].startswith("usage:"):
            assert (code, out, err) == (0, help_now, ""), argv
            counts["help"] += 1
        elif argv[11] == "--=5":
            assert (code, out) == (2, "") and err == old_err.replace(
                ", --step,", ", --step, --st,").replace("--csv\n", "--csv, --strategy, --grid, --param\n")
            counts["empty"] += 1
        elif option == "--s":
            assert (code, out) == (2, "") and err == old_err.replace(
                "could match --short, --step\n", "could match --short, --step, --st, --strategy\n")
            counts["s"] += 1
        elif option.startswith(("--g", "--p")):
            assert old_err.endswith(f"{PROG}unrecognized arguments: {' '.join(argv[11:])}\n")
            assert (code, out, err) == (2, "", f"{usage}{PROG}--short {SHORT_REFUSED}\n"), argv
            counts["grid/param"] += 1
        elif option.startswith("--str"):
            assert old_err.endswith(f"{PROG}unrecognized arguments: {' '.join(argv[11:])}\n")
            assert (code, out, err) == (
                2, "", f"{usage}{PROG}argument --strategy: invalid choice: '5' (choose from {CHOICES})\n"), argv
            counts["strategy"] += 1
        else:
            assert (code, out, err) == (record["code"], record["stdout"], old_err), argv
            namespace = parse(argv)
            if record["namespace"] is not None:
                assert {key: namespace[key] for key in record["namespace"]} == record["namespace"], argv
                assert (namespace["strategy"], namespace["grid_items"], namespace["param_items"]) == (None,) * 3
            counts["same"] += 1
    assert counts == {"same": 96, "help": 5, "empty": 1, "s": 2, "grid/param": 18, "strategy": 12}
    assert parse(["wf.csv", "--short", "1", "--long", "3", "--train", "12", "--test", "3", "--st", "5"])["step"] == 5


def test_momentum_hand_worked_cold_and_warm_text(folder):
    # --param window=4 --grid threshold=0,5, train 4, test 7: windows (train 0-3, test 4-10) and (7-10, 11-17).
    # A 4-bar train block gives no rate of change of 4 bars twice, so no trades: both thresholds 0.00%, a tie the
    # smaller threshold wins. Cold, a test block of 7 bars has its first two 4-bar rates of change on its last
    # two bars (20.00 and 44.44 in block 1; 27.27 and 50.00 in block 2): no crossing, no trades.
    # Buy and hold: 100 @ 10 on bar 4, worth 1,200 on bar 10: +20.00%; 90 @ 11 on bar 11 (10 left), worth
    # 1,270 on bar 17: +27.00%; compounded 1.2 * 1.27 - 1 = +52.40%.
    code, out, err = run(MOMENTUM)
    assert (code, err) == (0, "")
    assert out == (
        "Walk-forward: 2 windows; each momentum parameter set was chosen on its train bars only, then run on the"
        " test bars after them\n"
        "Window  Train bars   Test bars               Params     Train      Test  Buy&Hold Trades\n"
        "     1         0-3        4-10 window=4,threshold=0    +0.00%    +0.00%   +20.00%      0\n"
        "     2        7-10       11-17 window=4,threshold=0    +0.00%    +0.00%   +27.00%      0\n"
        "Test return, compounded over the windows: +0.00%\n"
        "Buy & hold, compounded over the windows:  +52.40%\n"
        "Mean test return per window: +0.00%\n"
        "Windows beating buy & hold: 0 of 2\n"
        "Windows without test trades: 2 of 2\n"
        "Note: 2 of 2 windows made no trades in the test block (no BUY signal on a test bar before its last, or"
        " too few test bars for a first signal); their 0.00% says nothing about the parameters.\n" + TAIL
    )
    # Warm (see the next test for the fills): -7.60% and +0.00%, one trade each; compounded -7.60%, mean -3.80%.
    code, out, err = run([*MOMENTUM, "--warmup"])
    assert (code, err) == (0, "")
    assert out == (
        "Walk-forward: 2 windows; each momentum parameter set was chosen on its train bars only, then traded and"
        " scored on the test bars after them, with its signal warmed up on the bars just before each test block,"
        " so that it can signal on the first test bar\n"
        "Window  Train bars   Test bars               Params     Train      Test  Buy&Hold Trades\n"
        "     1         0-3        4-10 window=4,threshold=0    +0.00%    -7.60%   +20.00%      1\n"
        "     2        7-10       11-17 window=4,threshold=0    +0.00%    +0.00%   +27.00%      1\n"
        "Test return, compounded over the windows: -7.60%\n"
        "Buy & hold, compounded over the windows:  +52.40%\n"
        "Mean test return per window: -3.80%\n"
        "Windows beating buy & hold: 0 of 2\n"
        "Windows without test trades: 0 of 2\n" + TAIL
    )


def test_momentum_partial_warm_up_near_the_start_of_the_data(folder, monkeypatch):
    # window=4 needs first_signal_bars - 1 = 5 warm-up bars. Block 1 starts on bar 4: only bars 0-3 (4 of 5)
    # exist, so it gets those. The 4-bar rate of change then exists from bar 4 (10 / 10: 0.00): bar 5 (9 / 11,
    # -18.18) crosses down (flat: nothing), bar 8 (12 / 10, +20.00) crosses up from bar 7's 0.00: 76 @ 13 on bar
    # 9 (12 left), 76 * 12 + 12 = 924 on bar 10: -7.60%, drawdown -7.60% (the peak is the starting 1,000).
    # Block 2 gets its full 5 bars, 6-10: bar 12 (10 / 12) crosses down, bar 14 (13 / 12, +8.33) crosses up from
    # -15.38: 71 @ 14 on bar 15 (6 left), 1,071 on bar 16, 1,000 on bar 17: +0.00%, drawdown -6.63%.
    calls = []
    real = _backtest.run_backtest

    def spy(prices, **kwargs):
        result = real(prices, **kwargs)
        calls.append((kwargs["warmup_closes"], [(t.bar, t.side, t.shares, t.price, t.cash_after) for t in result.trades]))
        return result

    monkeypatch.setattr(_backtest, "run_backtest", spy)
    code, out, err = run([*MOMENTUM, "--warmup", "--json"])
    assert (code, err) == (0, "")
    assert calls == [
        ([10.0, 11.0, 12.0, 11.0], [(5, "BUY", 76, 13.0, 12.0)]),  # bar 9 of the file is bar 5 of block 1
        ([10.0, 11.0, 12.0, 13.0, 12.0], [(4, "BUY", 71, 14.0, 6.0)]),  # bar 15 is bar 4 of block 2
    ]
    rows = json.loads(out)["windows"]
    assert [(r["test_return_pct"], r["test_max_drawdown_pct"], r["test_trades"]) for r in rows] == [
        (pytest.approx(-7.6), pytest.approx(-7.6), 1), (pytest.approx(0.0), pytest.approx((1000 - 1071) / 1071 * 100), 1)]


def test_json_has_strategy_first_and_params_in_each_row(folder):
    code, out, err = run([*MOMENTUM, "--warmup", "--json"])
    assert (code, err) == (0, "")
    assert out.startswith('{\n  "strategy": "momentum",\n  "warmup": true,\n  "windows": [\n')
    data = json.loads(out)
    assert list(data) == ["strategy", "warmup", "windows", "summary", "overfit_warning", "disclaimer"]
    closes = load_price_table("wf.csv")[1]
    rows, summary = run_walk_forward(closes, None, None, 4, 7, cash=1000, warmup=True, strategy="momentum",
                                     grid={"threshold": [0, 5]}, params={"window": 4})
    assert (data["windows"], data["summary"]) == (rows, summary)
    assert list(data["windows"][0]) == ["window", "train_start", "train_end", "test_start", "test_end", "params",
                                        "train_return_pct", "test_return_pct", "test_max_drawdown_pct", "test_trades",
                                        "buy_hold_return_pct"]
    assert data["windows"][0]["params"] == {"window": 4, "threshold": 0}
    # Without --warmup there is no warmup key; strategy still comes first.
    assert list(json.loads(run(MOMENTUM + ["--json"])[1])) == [
        "strategy", "windows", "summary", "overfit_warning", "disclaimer"]


def test_csv_has_one_param_column_per_parameter(folder):
    code, out, err = run([*MOMENTUM, "--warmup", "--csv", "out.csv"])
    assert (code, err) == (0, "")
    assert out.endswith(f"Wrote 2 rows to out.csv\n{TAIL}")
    assert (folder / "out.csv").read_text() == (
        "window,train_start,train_end,test_start,test_end,param_window,param_threshold,train_return_pct,"
        "test_return_pct,test_max_drawdown_pct,test_trades,buy_hold_return_pct\n"
        "1,0,4,4,11,4,0,0.0000,-7.6000,-7.6000,1,20.0000\n"
        "2,7,11,11,18,4,0,0.0000,0.0000,-6.6293,1,27.0000\n"
    )
    # Three parameters, floats as Python prints them, in registry order whatever the option order.
    argv = ["sideways.csv", "--strategy", "zscore_reversion", "--param", "exit=0.5", "--grid", "entry=-1.5,-1",
            "--grid", "window=5,10", "--train", "40", "--test", "20", "--json", "--csv", "z.csv"]
    code, out, _ = run(argv)
    assert code == 0
    header, *lines = (folder / "z.csv").read_text().splitlines()
    assert header.split(",")[5:8] == ["param_window", "param_entry", "param_exit"]
    windows = json.loads(out)["windows"]
    assert [line.split(",")[5:8] for line in lines] == [
        [str(w["params"][k]) for k in ("window", "entry", "exit")] for w in windows]
    assert {line.split(",")[7] for line in lines} == {"0.5"}
    assert {line.split(",")[6] for line in lines} <= {"-1.5", "-1"} and len(lines) == 5


def test_breakout_text_json_and_csv_hand_worked(folder):
    # --strategy breakout --grid window=2,3 --train 8 --test 6: one window, train 0-7, test 8-13.
    # window 2: bar 2 (12) is above 10 and 11: 90 @ 11 on bar 3 (10 left); bar 4 (10) is below 12 and 11: sold
    # @ 9 on bar 5: 820, -18.00%. window 3: no close above the three before it until bar 7, the last: 0.00%.
    # So window 3. Test bars 12, 13, 12, 11, 10, 11: its first signals are on bars 11 and 12, both SELL while
    # flat: no trades. Buy and hold 83 @ 12 (4 left), 83 * 11 + 4 = 917: -8.30%.
    argv = ["wf.csv", "--strategy", "breakout", "--grid", "window=2,3", "--train", "8", "--test", "6", "--cash", "1000"]
    code, out, err = run(argv)
    assert (code, err) == (0, "")
    assert out == (
        "Walk-forward: 1 window; each breakout parameter set was chosen on its train bars only, then run on the"
        " test bars after them\n"
        "Window  Train bars   Test bars   Params     Train      Test  Buy&Hold Trades\n"
        "     1         0-7        8-13 window=3    +0.00%    +0.00%    -8.30%      0\n"
        "Test return, compounded over the windows: +0.00%\n"
        "Buy & hold, compounded over the windows:  -8.30%\n"
        "Mean test return per window: +0.00%\n"
        "Windows beating buy & hold: 1 of 1\n"
        "Windows without test trades: 1 of 1\n"
        "Note: 1 of 1 windows made no trades in the test block (no BUY signal on a test bar before its last, or"
        " too few test bars for a first signal); their 0.00% says nothing about the parameters.\n" + TAIL
    )
    data = json.loads(run([*argv, "--json"])[1])
    assert data["strategy"] == "breakout" and data["windows"][0]["params"] == {"window": 3}
    assert data["windows"][0]["buy_hold_return_pct"] == pytest.approx(-8.3)
    assert run([*argv, "--csv", "out.csv"])[0] == 0
    assert (folder / "out.csv").read_text() == (
        "window,train_start,train_end,test_start,test_end,param_window,train_return_pct,test_return_pct,"
        "test_max_drawdown_pct,test_trades,buy_hold_return_pct\n1,0,8,8,14,3,0.0000,0.0000,0.0000,0,-8.3000\n"
    )


def test_usage_errors_exit_2(folder):
    base = ["wf.csv", "--train", "8", "--test", "6"]
    for extra, message in [
        (["--strategy", "sma_cross", "--short", "2"], f"--short {SHORT_REFUSED}"),
        (["--strategy", "breakout", "--long", "5"], f"--long {SHORT_REFUSED}"),
        (["--grid", "window=2", "--short", "1", "--long", "3"], f"--short {SHORT_REFUSED}"),
        (["--param", "threshold=1", "--long", "3"], f"--long {SHORT_REFUSED}"),
        (["--grid", "window=2"], "--grid needs --strategy"),
        (["--param", "window=2"], "--param needs --strategy"),
        (["--strategy", "breakout", "--grid", "window"], "--grid must look like KEY=LIST, got 'window'"),
        (["--strategy", "breakout", "--grid", "=2"], "--grid must look like KEY=LIST, got '=2'"),
        (["--strategy", "breakout", "--grid", "window=2,x"], "--grid window needs a comma list of finite numbers, got 'x'"),
        (["--strategy", "breakout", "--grid", "window=2,,3"], "--grid window needs a comma list of finite numbers, got ''"),
        (["--strategy", "momentum", "--grid", "threshold=nan"],
         "--grid threshold needs a comma list of finite numbers, got 'nan'"),
        (["--strategy", "breakout", "--param", "window=2,3"],
         "--param window takes one value, got '2,3'; give a list of values with --grid window=2,3"),
        (["--strategy", "breakout", "--param", "window=x"], "--param window needs a number, got 'x'"),
        (["--strategy", "breakout", "--param", "window"], "--param must look like KEY=VALUE, got 'window'"),
        (["--strategy", "breakout", "--grid", "window=2", "--grid", "window=3"], "--grid window given more than once"),
        (["--strategy", "breakout", "--param", "window=2", "--param", "window=3"], "--param window given more than once"),
        (["--strategy", "breakout", "--grid", "window=2", "--param", "window=3"],
         "window is in both --grid and --param; give only one"),
        (["--strategy", "breakout", "--grid", "period=2"],
         "unknown parameter 'period' for strategy 'breakout'; choose from: window"),
        (["--strategy", "breakout", "--grid", "window=2,0,3"], "window must be a whole number of at least 1, got 0"),
        (["--strategy", "breakout", "--grid", "window=2.5"], "window must be a whole number of at least 1, got 2.5"),
        (["--strategy", "rsi_reversion", "--grid", "oversold=20,120"], "oversold must be from 0 to 100, got 120"),
        (["--strategy", "zscore_reversion", "--grid", "window=1,5"], "window must be at least 2 for a z-score, got 1"),
        (["--strategy", "sma_cross", "--grid", "short=50", "--grid", "long=20"],
         "no parameter combination for sma_cross passes its checks: short window must be smaller than long window"),
        (["--strategy", "nope"], f"argument --strategy: invalid choice: 'nope' (choose from {CHOICES})"),
        (["--strategy", "breakout", "--test", "0"], "--test must be at least 1"),
        (["--strategy", "breakout", "--fee", "-1"], "--fee must not be negative, got -1"),
        (["--strategy", "breakout", "--csv", " "], "--csv needs a file name"),
    ]:
        code, out, err = run(base + extra)
        assert (code, out, leftovers(folder)) == (2, "", {}), extra
        assert err.startswith("usage: trading_assistant.walkforward [-h] --short LIST --long LIST --train N\n")
        assert err.endswith(f"{PROG}{message}\n"), (extra, err.splitlines()[-1])
    # With --strategy, --short and --long are not required; --train and --test still are.
    assert run(["wf.csv", "--strategy", "breakout"])[2].endswith(f"{PROG}the following arguments are required: --train, --test\n")


def test_zero_and_zero_point_zero_are_one_grid_value(folder):
    # 0 and 0.0 (and -0.0) compare equal, so they are one value, tried once. Of equal values the whole number is
    # kept, then 0.0 over -0.0, whatever the order they were typed in; a single 0.0 stays 0.0.
    base = ["sideways.csv", "--strategy", "momentum", "--param", "window=3", "--train", "40", "--test", "20", "--json"]
    shown = {}
    for values in ("0,0.0", "0.0,0", "-0.0,0.0,0", "0.0,-0.0", "-0.0,0.0", "0.0", "0"):
        data = json.loads(run([*base, "--grid", f"threshold={values}"])[1])
        shown[values] = {repr(w["params"]["threshold"]) for w in data["windows"]}
    assert shown == {"0,0.0": {"0"}, "0.0,0": {"0"}, "-0.0,0.0,0": {"0"}, "0.0,-0.0": {"0.0"}, "-0.0,0.0": {"0.0"},
                     "0.0": {"0.0"}, "0": {"0"}}
    # One set: every window shows the same threshold, and the numbers are those of that one fixed value.
    assert json.loads(run([*base, "--grid", "threshold=0.0,0"])[1])["windows"] == json.loads(
        run([*base, "--param", "threshold=0"])[1])["windows"]


def test_sma_cross_through_the_grid_gives_the_old_numbers(folder):
    old = json.loads(run(["sideways.csv", "--short", "2,3,5", "--long", "5,10,20", "--train", "40", "--test", "20",
                          "--warmup", "--json"])[1])
    new = json.loads(run(["sideways.csv", "--strategy", "sma_cross", "--grid", "short=2,3,5", "--grid", "long=5,10,20",
                          "--train", "40", "--test", "20", "--warmup", "--json"])[1])
    assert new["summary"] == old["summary"] and len(new["windows"]) == 5
    for a, b in zip(old["windows"], new["windows"]):
        assert b == {k: ({"short": a["short"], "long": a["long"]} if k == "params" else a[k]) for k in b}
    text = run(["sideways.csv", "--strategy", "sma_cross", "--grid", "short=2,3,5", "--grid", "long=5,10,20",
                "--train", "40", "--test", "20"])[1].splitlines()
    assert text[1].split()[5] == "Params"  # Window, Train bars, Test bars, Params
    assert [line.split()[3] for line in text[2:7]] == [f"short={w['short']},long={w['long']}" for w in old["windows"]]


def test_every_strategy_runs_through_the_command(folder):
    closes = load_price_table("sideways.csv")[1]
    cases = {
        "sma_cross": (["short=2,3", "long=5,10"], []),
        "rsi_reversion": (["period=3,5", "oversold=30,40"], ["overbought=60"]),
        "breakout": (["window=3,8"], []),
        "ema_cross": (["short=2,3"], ["long=8"]),
        "momentum": (["window=3,6", "threshold=0,1.5"], []),
        "zscore_reversion": (["window=5,10", "entry=-1.5,-1.0"], []),
        "hull_trend": (["window=4,9"], []),
    }
    for name, (grids, params) in cases.items():
        argv = ["sideways.csv", "--strategy", name, "--train", "40", "--test", "20", "--step", "15", "--fee", "1",
                "--warmup", "--json", "--csv", "out.csv"]
        for g in grids:
            argv += ["--grid", g]
        for p in params:
            argv += ["--param", p]
        code, out, err = run(argv)
        assert (code, err) == (0, ""), name
        grid = {g.split("=")[0]: [float(v) if "." in v else int(v) for v in g.split("=")[1].split(",")] for g in grids}
        fixed = {p.split("=")[0]: int(p.split("=")[1]) for p in params}
        rows, summary = run_walk_forward(closes, None, None, 40, 20, step=15, fee=1.0, warmup=True, strategy=name,
                                         grid=grid, params=fixed)
        assert json.loads(out) == json.loads(json.dumps(walkforward.json_data(rows, summary, True, name))), name
        header = (folder / "out.csv").read_text().splitlines()[0].split(",")
        assert header[5 : 5 + len(STRATEGIES[name][1])] == [f"param_{k}" for k in STRATEGIES[name][1]], name
        leftovers(folder)


def test_data_errors_with_a_strategy_exit_1(folder):
    base = ["wf.csv", "--strategy", "breakout", "--grid", "window=2,3", "--test", "6"]
    assert run([*base, "--train", "13"]) == (
        1, "", "Error: not enough prices for a walk-forward window: 18 bars, need at least train + test = 19\n")
    assert run([*base, "--train", "8", "--csv", "wf.csv"]) == (
        1, "", "Error: --csv refuses to overwrite the input file wf.csv\n")
    (folder / "bad.csv").write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n"
                                                             for i, c in enumerate([10, 11, 0, 12] + [11] * 16)))
    assert run(["bad.csv", *base[1:], "--train", "8"]) == (1, "", "Error: bar 2: price must be positive, got 0.0\n")
    (folder / "bad.csv").unlink()
    assert leftovers(folder) == {}  # no --csv file was written by any of them
