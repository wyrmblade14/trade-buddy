"""--min-hold N on the command line: the hand case of test_min_hold.py through the CLI, closes only."""

import pytest

from trading_assistant.cli import build_parser, main

CLOSES = "date,close\n" + "".join(
    f"2026-01-{d:02d},{c}\n" for d, c in zip(range(1, 12), (10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2))
)
B = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]

# Both captured from the command before --min-hold existed (git HEAD): `B` and `B --max-hold 2`.
BEFORE = (
    'Bars:    11\n'
    'Last:    12.20\n'
    'Signal:  HOLD\n'
    'RSI:     n/a\n'
    'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
    '  Start cash:  1,000.00\n'
    '  Trades:      3 (2 buy, 1 sell)\n'
    '  Fills (bar index is 0-based):\n'
    '    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n'
    '    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00\n'
    '    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00\n'
    '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
    '  Round trips: 1 completed, 0 made money (0%)\n'
    '  Comparison              Strategy    Buy & hold\n'
    '    End equity              925.00      1,220.00\n'
    '    Return                  -7.50%       +22.00%\n'
    '    Max drawdown           -16.51%       -20.00%\n'
    '    Trades                       3             1\n'
    '    Costs paid                0.00          0.00\n'
    '  End cash:    10.00\n'
    '  End shares:  75 @ 12.20\n'
    '  End equity:  925.00\n'
    '  Return:      -7.50%\n'
    'Research aid only. Not financial advice.\n'
)
BEFORE_MAX_HOLD_2 = (
    'Bars:    11\n'
    'Last:    12.20\n'
    'Signal:  HOLD\n'
    'RSI:     n/a\n'
    'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
    '  Start cash:  1,000.00\n'
    '  Trades:      3 (2 buy, 1 sell)\n'
    '  Fills (bar index is 0-based):\n'
    '    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n'
    '    #2   bar 6     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00  time\n'
    '    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00  signal\n'
    '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
    "  Max hold:    2 bars after a position's first buy, then sold at the bar's fill price; 1 time exit\n"
    '  Round trips: 1 completed, 0 made money (0%)\n'
    '  Comparison              Strategy    Buy & hold\n'
    '    End equity              925.00      1,220.00\n'
    '    Return                  -7.50%       +22.00%\n'
    '    Max drawdown           -16.51%       -20.00%\n'
    '    Trades                       3             1\n'
    '    Costs paid                0.00          0.00\n'
    '  End cash:    10.00\n'
    '  End shares:  75 @ 12.20\n'
    '  End equity:  925.00\n'
    '  Return:      -7.50%\n'
    'Research aid only. Not financial advice.\n'
)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "closes.csv").write_text(CLOSES)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES)
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


def min_hold_line(n, skipped):
    return (
        f"  Min hold:    {n} bar{'' if n == 1 else 's'} after a position's first buy before a signal sell can fill; "
        f"{skipped} signal sell{'' if skipped == 1 else 's'} skipped\n"
    )


def test_without_the_option_the_output_is_exactly_as_before(folder, capsys):
    assert run(B, capsys) == (0, BEFORE, "")
    assert run([*B, "--max-hold", "2"], capsys) == (0, BEFORE_MAX_HOLD_2, "")


@pytest.mark.parametrize("n, skipped", [(1, 0), (3, 0)])
def test_min_hold_1_and_3_only_add_the_min_hold_line(folder, capsys, n, skipped):
    # Bar 7's sell is 3 bars after the buy on bar 4: it fills with 1 or 3, so only the new line differs.
    expected = BEFORE.replace("  Round trips:", min_hold_line(n, skipped) + "  Round trips:")
    assert run([*B, "--min-hold", str(n)], capsys) == (0, expected, "")


def test_min_hold_4_skips_the_bar_7_sell(folder, capsys):
    code, out, err = run([*B, "--min-hold", "4"], capsys)
    assert (code, err) == (0, "")
    assert "  Trades:      1 (1 buy, 0 sell)\n" in out
    assert min_hold_line(4, 1) in out
    assert "  End shares:  90 @ 12.20\n  End equity:  1,108.00\n" in out


def test_min_hold_4_with_max_hold_2_adds_only_the_min_hold_line(folder, capsys):
    # The time exit sells on bar 6, before the window ends; everything else is exactly the max-hold-2 output.
    expected = BEFORE_MAX_HOLD_2.replace("  Max hold:", min_hold_line(4, 0) + "  Max hold:")
    assert run([*B, "--min-hold", "4", "--max-hold", "2"], capsys) == (0, expected, "")


def test_works_with_resample(folder, capsys):
    # Weekly bars of a close-only file: no candle file is needed and --resample is allowed.
    code, out, err = run([*B, "--resample", "weekly", "--min-hold", "2"], capsys)
    assert (code, err) == (0, "")
    assert min_hold_line(2, 0) in out


@pytest.mark.parametrize(
    "argv, message",
    [
        ([*B, "--min-hold", "0"], "--min-hold must be a whole number of at least 1, got 0"),
        ([*B, "--min-hold", "x"], "argument --min-hold: invalid int value: 'x'"),
        ([*B, "--min-hold", "1.5"], "argument --min-hold: invalid int value: '1.5'"),
        (["closes.csv", "--min-hold", "4"], "--min-hold only makes sense together with --backtest"),
        (["--scan", "scan", "--min-hold", "4"], "--min-hold cannot be combined with --scan"),
    ],
)
def test_usage_errors_exit_2(folder, capsys, argv, message):
    code, out, err = run(argv, capsys)
    assert (code, out) == (2, "")
    assert err.endswith(f"error: {message}\n")


def test_help_lists_it_but_the_usage_line_does_not_and_the_old_short_names_still_mean_min_score(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert "--min-hold" not in out.split("\n\n", 1)[0]
    assert "\n  --min-hold N " in out
    parser = build_parser(scan=True)
    for token in ("--m", "--mi", "--min", "--min-", "--min-s"):
        assert parser.parse_args(["--scan", "scan", token, "2"]).min_score == 2, token
    assert build_parser().parse_args(["x.csv", "--min-h", "4"]).min_hold == 4
    # An old short name keeps its old error too.
    code, _, err = run(["closes.csv", "--min", "1"], capsys)
    assert code == 2 and err.endswith("error: --min-score only makes sense together with --scan\n")


# --------------------------------------------------------------------------- --json and --export

# The `B --json` and `B --max-hold 2 --json` objects, captured from the command before --min-hold existed (git HEAD).
JSON_BEFORE = __import__("json").loads(
    (__import__("pathlib").Path(__file__).resolve().parent / "data" / "closes_json_before_min_hold.json").read_text()
)


def run_json(argv, capsys):
    code, out, err = run([*argv, "--json"], capsys)
    assert (code, err) == (0, "")
    return __import__("json").loads(out)


def with_keys(data, setting_before, setting, counter_before, counter):
    """``data`` with ``min_hold_bars`` inserted before ``setting_before`` and ``min_hold_skipped_sells`` before
    ``counter_before`` in the backtest object, keeping every other key where it was."""
    backtest = {}
    for key, value in data["backtest"].items():
        if key == setting_before:
            backtest["min_hold_bars"] = setting
        if key == counter_before:
            backtest["min_hold_skipped_sells"] = counter
        backtest[key] = value
    return {**data, "backtest": backtest}


def test_json_without_the_option_is_exactly_as_before(folder, capsys):
    assert run_json(B, capsys) == JSON_BEFORE["plain"]
    assert run_json([*B, "--max-hold", "2"], capsys) == JSON_BEFORE["max_hold_2"]


@pytest.mark.parametrize("n", [1, 3])
def test_json_min_hold_1_and_3_only_add_the_two_keys(folder, capsys, n):
    data = run_json([*B, "--min-hold", str(n)], capsys)
    expected = with_keys(JSON_BEFORE["plain"], "trades", n, "fills", 0)
    assert data == expected and list(data["backtest"]) == list(expected["backtest"])


def test_json_min_hold_4_with_max_hold_2_puts_the_keys_next_to_the_max_hold_keys(folder, capsys):
    data = run_json([*B, "--min-hold", "4", "--max-hold", "2"], capsys)
    expected = with_keys(JSON_BEFORE["max_hold_2"], "max_hold_bars", 4, "time_exits", 0)
    assert data == expected and list(data["backtest"]) == list(expected["backtest"])


def test_json_min_hold_4_matches_the_text_report(folder, capsys):
    backtest = run_json([*B, "--min-hold", "4"], capsys)["backtest"]
    assert (backtest["min_hold_bars"], backtest["min_hold_skipped_sells"]) == (4, 1)
    assert (backtest["trades"], backtest["buys"], backtest["sells"]) == (1, 1, 0)
    assert [(f["bar"], f["side"], f["shares"], f["reason"]) for f in backtest["fills"]] == [(4, "BUY", 90, "signal")]
    assert (backtest["final_position"], backtest["final_equity"]) == (90, pytest.approx(1108.0))
    _, text, _ = run([*B, "--min-hold", "4"], capsys)
    assert min_hold_line(backtest["min_hold_bars"], backtest["min_hold_skipped_sells"]) in text
    assert f"  End equity:  {backtest['final_equity']:,.2f}\n" in text


def test_export_a_skipped_sell_leaves_no_row_and_no_reason_column(folder, capsys):
    run([*B, "--export", "none.csv"], capsys)
    run([*B, "--min-hold", "3", "--export", "three.csv"], capsys)
    run([*B, "--min-hold", "4", "--export", "four.csv"], capsys)
    none, four = (folder / "none.csv").read_text().splitlines(), (folder / "four.csv").read_text().splitlines()
    assert (folder / "three.csv").read_text() == "\n".join(none) + "\n"  # nothing skipped: byte for byte the same
    assert four[0] == none[0] and "reason" not in four[0]  # same header, no reason column
    assert len(four) == len(none) == 12  # one row per bar, no extra row for the skipped sell
    assert four[8].split(",")[:5] == ["7", "2026-01-08", "10.00", "HOLD", ""]  # bar 7: no action
    assert four[:8] == none[:8]  # everything before the skipped sell is unchanged
