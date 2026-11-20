"""--breakeven PCT on the command line: the c.csv hand cases of test_breakeven.py through the CLI.

c.csv (tests/data/c.csv), --short 1 --long 2 --cash 1000. See test_breakeven.py for the worked numbers.
"""

import json
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import build_parser, main

DATA = Path(__file__).resolve().parent / "data"
B = ["c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    shutil.copy(DATA / "c.csv", tmp_path / "c.csv")
    (tmp_path / "closes.csv").write_text("date,close\n2026-01-01,10\n2026-01-02,11\n2026-01-03,12\n")
    (tmp_path / "scan").mkdir()
    (tmp_path / "cooldown.ini").write_text("[cli]\ncooldown = 3\n")
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


def fill_tails(out):
    """(bar, side, shares, price, reason) of each fill line."""
    rows = [line.split() for line in out.splitlines() if line.startswith("    #")]
    return [(int(r[2]), r[3], int(r[4]), r[6], r[-1]) for r in rows]


BREAKEVEN = [(4, "BUY", 90, "11.00", "signal"), (6, "SELL", 90, "11.00", "breakeven"), (9, "BUY", 83, "12.00", "signal")]
WITHOUT = [(4, "BUY", 90, "11.00", "signal"), (7, "SELL", 90, "10.00", "signal"), (9, "BUY", 75, "12.00", "signal")]
COOLDOWN_LINE = "  Cooldown:    3 bars after a stop, trail, atr or breakeven exit; 1 buy skipped"


@pytest.mark.parametrize(
    "extra, fills, equity, cooldown_line",
    [
        (["--breakeven", "5"], BREAKEVEN, "1,016.60", False),
        (["--breakeven", "9"], BREAKEVEN, "1,016.60", False),
        (["--breakeven", "10"], WITHOUT, "925.00", False),
        (["--breakeven", "5", "--cooldown", "3"], BREAKEVEN[:2], "1,000.00", True),
        (["--breakeven", "5", "--config", "cooldown.ini"], BREAKEVEN[:2], "1,000.00", True),  # the file's cooldown
        (["--br", "5"], BREAKEVEN, "1,016.60", False),  # a shortened name of the new option
    ],
)
def test_c_csv_hand_cases(folder, capsys, extra, fills, equity, cooldown_line):
    code, out, err = run([*B, *extra], capsys)
    assert (code, err) == (0, "")
    assert fill_tails(out) == fills
    assert f"  End equity:  {equity}" in out.splitlines()
    pct = float(extra[1])
    assert f"  Exits:       breakeven at entry once a later high is {pct:.2f}% above it" in out.splitlines()
    assert (COOLDOWN_LINE in out.splitlines()) is cooldown_line


@pytest.mark.parametrize(
    "argv, code, message",
    [
        ([*B, "--breakeven", "0"], 2, "error: --breakeven must be above 0, got 0"),
        ([*B, "--breakeven", "-1.5"], 2, "error: --breakeven must be above 0, got -1.5"),
        ([*B, "--breakeven", "nan"], 2, "error: --breakeven must be above 0, got nan"),
        ([*B, "--breakeven", "five"], 2, "error: argument --breakeven: invalid float value: 'five'"),
        (["c.csv", "--breakeven", "5"], 2, "error: --breakeven only makes sense together with --backtest"),
        ([*B, "--breakeven", "5", "--resample", "weekly"], 2, "error: --breakeven cannot be combined with --resample yet"),
        (["--scan", "scan", "--breakeven", "5"], 2, "error: --breakeven cannot be combined with --scan"),
        (["closes.csv", *B[1:], "--breakeven", "5"], 1, "Error: closes.csv has no 'open', 'high', 'low', 'volume' columns"),
    ],
)
def test_refused(folder, capsys, argv, code, message):
    got, out, err = run(argv, capsys)
    assert (got, out) == (code, "")
    assert message in err.splitlines()[-1]


def test_decimals_are_allowed_and_inf_is_refused(folder, capsys):
    code, out, _ = run([*B, "--breakeven", "0.5"], capsys)
    assert code == 0 and "once a later high is 0.50% above it" in out
    code, out, err = run([*B, "--breakeven", "inf"], capsys)  # unlike --take-profit; like the config key and the API
    assert (code, out) == (2, "") and err.splitlines()[-1].endswith("error: --breakeven must be a finite number, got inf")


def test_help_lists_it_but_the_usage_line_does_not_and_b_still_means_backtest(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert "--breakeven" not in out.split("\n\n", 1)[0]
    assert "  --breakeven PCT" in out
    assert "counts as a stop for --cooldown" in " ".join(out.split())
    # "--b" meant --backtest before --breakeven existed (an abbreviation); the hidden exact alias keeps it.
    args = build_parser().parse_args(["c.csv", "--b"])
    assert (args.backtest, args.breakeven) == (True, None)
    code, out, err = run(["c.csv", "--b", "--short", "1", "--long", "2"], capsys)
    assert (code, err) == (0, "") and "Backtest: SMA 1/2 crossover" in out


def test_cooldown_error_is_unchanged_without_a_stop(folder, capsys):
    # --breakeven counts as a stop for --cooldown, but the message for no stop at all still names only the old ones.
    code, out, err = run([*B, "--cooldown", "3"], capsys)
    assert (code, out) == (2, "")
    assert err.splitlines()[-1].endswith(
        "error: --cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop"
    )


# --- --json ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra, exits, equity",
    [
        (["--breakeven", "5"], 1, 1016.6),
        (["--breakeven", "9"], 1, 1016.6),
        (["--breakeven", "10"], 0, 925.0),
        (["--breakeven", "5", "--cooldown", "3"], 1, 1000.0),
    ],
)
def test_json_hand_cases_match_the_text_report(folder, capsys, extra, exits, equity):
    code, out, err = run([*B, *extra, "--json"], capsys)
    assert (code, err) == (0, "")
    bt = json.loads(out)["backtest"]
    keys = list(bt)
    # breakeven_pct with the exit settings (before cooldown_bars), breakeven_exits with the counts after sells.
    assert keys[keys.index("take_profit_pct") + 1] == "breakeven_pct"
    assert keys[keys.index("sells") + 1] == "breakeven_exits"
    assert bt["breakeven_pct"] == float(extra[1]) and bt["breakeven_exits"] == exits
    assert bt["final_equity"] == pytest.approx(equity)
    # The same numbers as the text report of the same command.
    code, text, _ = run([*B, *extra], capsys)
    lines = text.splitlines()
    assert [(f["bar"], f["side"], f["shares"], f"{f['price']:.2f}", f["reason"]) for f in bt["fills"]] == fill_tails(text)
    assert sum(f["reason"] == "breakeven" for f in bt["fills"]) == exits
    assert f"  Trades:      {bt['trades']} ({bt['buys']} buy, {bt['sells']} sell)" in lines
    assert f"  End equity:  {bt['final_equity']:,.2f}" in lines
    assert f"  Return:      {bt['return_pct']:+.2f}%" in lines


def test_json_key_order_with_every_exit_and_without_the_option(folder, capsys):
    everything = ["--risk-pct", "1", "--atr-period", "2", "--stop-loss", "5", "--take-profit", "30",
                  "--trailing-stop", "20", "--atr-stop", "--breakeven", "5", "--cooldown", "3", "--max-hold", "9",
                  "--max-drawdown", "50"]
    _, out, _ = run([*B, *everything, "--json"], capsys)
    keys = list(json.loads(out)["backtest"])
    assert keys[keys.index("stop_loss_pct") : keys.index("fills")] == [
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "atr_stop", "breakeven_pct", "cooldown_bars",
        "max_hold_bars", "max_drawdown_limit_pct", "trades", "buys", "sells", "risk_skipped_buys", "breakeven_exits",
        "cooldown_skipped_buys", "time_exits", "drawdown_halt_bar", "drawdown_skipped_buys",
    ]
    _, out, _ = run([*B, "--stop-loss", "5", "--json"], capsys)
    assert "breakeven" not in out


# --- config file key breakeven ------------------------------------------------------------------------------


def write_ini(folder, body):
    (folder / "be.ini").write_text("[cli]\n" + body)
    return "be.ini"


@pytest.mark.parametrize(
    "body, flags",
    [
        ("breakeven = 5\n", ["--breakeven", "5"]),
        ("breakeven = 9\n", ["--breakeven", "9"]),
        ("breakeven = 10\n", ["--breakeven", "10"]),
        ("breakeven = 5\ncooldown = 3\n", ["--breakeven", "5", "--cooldown", "3"]),
    ],
)
def test_config_key_matches_the_flag_in_text_and_json(folder, capsys, body, flags):
    ini = write_ini(folder, body)
    for extra in ([], ["--json"]):
        from_file = run([*B, "--config", ini, *extra], capsys)
        from_flag = run([*B, *flags, *extra], capsys)
        assert from_file == from_flag and from_file[0] == 0, extra
    assert "breakeven" in from_file[1]


@pytest.mark.parametrize("body", ["breakeven = 5\n", "breakeven = 0\n"])
def test_flag_wins_over_the_file(folder, capsys, body):
    # The file's value is not used at all, so its 0 is no error either.
    ini = write_ini(folder, body)
    code, out, err = run([*B, "--config", ini, "--breakeven", "9", "--json"], capsys)
    assert (code, err) == (0, "") and json.loads(out)["backtest"]["breakeven_pct"] == 9.0
    assert run([*B, "--config", ini, "--breakeven", "9"], capsys) == run([*B, "--breakeven", "9"], capsys)


@pytest.mark.parametrize(
    "value, argv, code, message",
    [
        ("0", B, 2, "trading_assistant.cli: error: --breakeven must be above 0, got 0"),
        ("-2", B, 2, "trading_assistant.cli: error: --breakeven must be above 0, got -2"),
        ("nan", B, 1, "Error: be.ini line 2: breakeven needs a finite number, got 'nan'"),
        ("inf", B, 1, "Error: be.ini line 2: breakeven needs a finite number, got 'inf'"),  # only the flag takes inf
        ("5%", B, 1, "Error: be.ini line 2: breakeven needs a number, got '5%'"),
        # Ignored without --backtest and with --scan, even 0; a value of the wrong kind is still an error.
        ("0", ["c.csv"], 0, None),
        ("0", ["--scan", "scan"], None, None),
        ("nan", ["c.csv"], 1, "Error: be.ini line 2: breakeven needs a finite number, got 'nan'"),
        ("inf", ["--scan", "scan"], 1, "Error: be.ini line 2: breakeven needs a finite number, got 'inf'"),
    ],
)
def test_config_values_are_checked_like_other_keys(folder, capsys, value, argv, code, message):
    ini = write_ini(folder, f"breakeven = {value}\n")
    got, out, err = run([*argv, "--config", ini], capsys)
    if message is None:
        # Ignored: the same as the run without the file (the empty scan folder is exit 1 either way).
        assert (got, out, err) == run(argv, capsys)
        assert code is None or got == code
    else:
        assert (got, out) == (code, "") and err.splitlines()[-1] == message
