"""--max-hold N on the command line: the hand case of test_max_hold.py through the CLI, closes only."""

import pytest

from trading_assistant.cli import build_parser, main

CLOSES = "date,close\n" + "".join(
    f"2026-01-{d:02d},{c}\n"
    for d, c in zip((1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15), (10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2))
)
CANDLES = "date,open,high,low,close,volume\n" + "".join(
    f"2026-01-{d:02d},{c},{c},{c},{c},1000\n"
    for d, c in zip((1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15), (10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2))
)
B = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]

# Captured from the command before --max-hold existed (git HEAD), for `B` without the option.
BEFORE = (
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
    "Research aid only. Not financial advice.\n"
)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "closes.csv").write_text(CLOSES)
    (tmp_path / "candles.csv").write_text(CANDLES)
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


def fill_tails(out):
    """(bar, side, price, reason) of each fill line."""
    rows = [line.split() for line in out.splitlines() if line.startswith("    #")]
    return [(int(r[2]), r[3], r[6], r[-1]) for r in rows]


@pytest.mark.parametrize(
    "n, fills, max_hold_line, equity",
    [
        (1, [(4, "BUY", "11.00", "signal"), (5, "SELL", "12.00", "time"), (9, "BUY", "12.00", "signal"),
             (10, "SELL", "12.20", "time")], "1 bar after a position's first buy, then sold at the bar's fill price; "
         "2 time exits", "1,108.00"),
        (2, [(4, "BUY", "11.00", "signal"), (6, "SELL", "10.00", "time"), (9, "BUY", "12.00", "signal")],
         "2 bars after a position's first buy, then sold at the bar's fill price; 1 time exit", "925.00"),
        (3, [(4, "BUY", "11.00", "signal"), (7, "SELL", "10.00", "signal"), (9, "BUY", "12.00", "signal")],
         "3 bars after a position's first buy, then sold at the bar's fill price; 0 time exits", "925.00"),
    ],
)
def test_hand_case_on_a_close_only_file(folder, capsys, n, fills, max_hold_line, equity):
    code, out, err = run([*B, "--max-hold", str(n)], capsys)
    assert (code, err) == (0, "")
    assert fill_tails(out) == fills
    assert f"  Max hold:    {max_hold_line}\n" in out
    assert f"  End equity:  {equity}\n" in out
    assert "Exits:" not in out


def test_without_the_option_the_output_is_exactly_as_before(folder, capsys):
    assert run(B, capsys) == (0, BEFORE, "")


@pytest.mark.parametrize(
    "argv, message",
    [
        ([*B, "--max-hold", "0"], "--max-hold must be a whole number of at least 1, got 0"),
        ([*B, "--max-hold", "-3"], "--max-hold must be a whole number of at least 1, got -3"),
        ([*B, "--max-hold", "1.5"], "argument --max-hold: invalid int value: '1.5'"),
        (["closes.csv", "--max-hold", "2"], "--max-hold only makes sense together with --backtest"),
        (["--scan", "scan", "--max-hold", "2"], "--max-hold cannot be combined with --scan"),
    ],
)
def test_usage_errors_exit_2(folder, capsys, argv, message):
    code, out, err = run(argv, capsys)
    assert (code, out) == (2, "")
    assert err.endswith(f"trading_assistant.cli: error: {message}\n")


def test_resample_and_fill_open_are_allowed(folder, capsys):
    code, out, err = run([*B, "--max-hold", "1", "--resample", "weekly"], capsys)
    assert (code, err) == (0, "") and "  Max hold:    1 bar " in out
    # --fill open reads the candle file as before; on flat candles the opens are the closes.
    code, out, err = run(["candles.csv", *B[1:], "--max-hold", "1", "--fill", "open"], capsys)
    assert (code, err) == (0, "")
    assert [f[:2] + (f[3],) for f in fill_tails(out)] == [
        (4, "BUY", "signal"), (5, "SELL", "time"), (9, "BUY", "signal"), (10, "SELL", "time"),
    ]
    code, out, err = run([*B, "--max-hold", "1", "--fill", "open"], capsys)  # closes only: still a data error
    assert code == 1 and "open" in err


def test_help_lists_it_but_the_usage_line_does_not_and_m_still_means_min_score(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    usage = out.split("\n\n", 1)[0]
    assert "--max-hold" not in usage
    assert "\n  --max-hold N " in out
    parser = build_parser(scan=True)
    assert parser.parse_args(["--scan", "scan", "--m", "2"]).min_score == 2
    assert parser.parse_args(["--scan", "scan", "--min", "2"]).min_score == 2
    assert build_parser().parse_args(["x.csv", "--ma", "4"]).max_hold == 4


# --------------------------------------------------------------------------- --json and --export


def json_backtest(argv, capsys):
    code, out, err = run([*argv, "--json"], capsys)
    assert (code, err) == (0, "")
    return __import__("json").loads(out)["backtest"]


# Keys of the backtest object before --max-hold existed (captured at git HEAD) for `B --json`.
BEFORE_KEYS = [
    "strategy", "params", "fill", "start_cash", "fee", "fee_pct", "slippage_pct", "position_size", "stop_loss_pct",
    "take_profit_pct", "trades", "buys", "sells", "fills", "total_costs", "round_trips", "winning_round_trips",
    "final_cash", "final_position", "final_price", "final_equity", "return_pct", "max_drawdown_pct", "benchmark",
]


@pytest.mark.parametrize("n, time_exits", [(1, 2), (2, 1), (3, 0)])
def test_json_has_the_max_hold_keys_and_matches_the_text_report(folder, capsys, n, time_exits):
    b = json_backtest([*B, "--max-hold", str(n)], capsys)
    keys = list(b)
    assert keys == [*BEFORE_KEYS[:10], "max_hold_bars", *BEFORE_KEYS[10:13], "time_exits", *BEFORE_KEYS[13:]]
    assert (b["max_hold_bars"], b["time_exits"]) == (n, time_exits)
    _, text, _ = run([*B, "--max-hold", str(n)], capsys)
    assert [(f["bar"], f["side"], f"{f['price']:.2f}", f["reason"]) for f in b["fills"]] == fill_tails(text)
    assert f"; {time_exits} time exit" in text
    assert f"  End equity:  {b['final_equity']:,.2f}\n" in text


def test_json_without_the_option_has_exactly_the_old_keys(folder, capsys):
    assert list(json_backtest(B, capsys)) == BEFORE_KEYS


def test_json_keys_sit_after_the_cooldown_keys(folder, capsys):
    b = json_backtest(["candles.csv", *B[1:], "--stop-loss", "50", "--cooldown", "2", "--max-hold", "1"], capsys)
    keys = list(b)
    assert keys[keys.index("cooldown_bars") + 1] == "max_hold_bars"
    assert keys[keys.index("cooldown_skipped_buys") + 1] == "time_exits"
    assert b["time_exits"] == 2 and b["cooldown_skipped_buys"] == 0  # the time exits start no cooldown


def test_export_gains_the_reason_column_only_with_the_option(folder, capsys):
    run([*B, "--export", "plain.csv"], capsys)
    run([*B, "--max-hold", "1", "--export", "held.csv"], capsys)
    plain = (folder / "plain.csv").read_text().splitlines()
    held = (folder / "held.csv").read_text().splitlines()
    assert not plain[0].endswith(",reason")
    assert held[0] == plain[0] + ",reason"
    assert [row.split(",")[-1] for row in held[1:]] == ["", "", "", "", "signal", "time", "", "", "", "signal", "time"]
