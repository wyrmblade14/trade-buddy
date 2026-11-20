"""--cooldown N on the command line.

Hand case, the 11-bar candle file below, --cash 1000 --short 1 --long 2 --stop-loss 10
(volume 1000 on every bar; BUY signals on bars 3 and 8, SELL on bar 6):

    bar  date        open  high   low   close
     0   2026-01-01  10    10.5   9.5   10
     1   2026-01-02   9.2   9.5   8.5    9
     2   2026-01-05   8.3   8.5   7.5    8
     3   2026-01-06   8.8   9.5   8.5    9     BUY signal
     4   2026-01-07  10.8  11.5  10.5   11     BUY 90 @ 11, cash 10
     5   2026-01-08  11    12    10.8   12
     6   2026-01-09  11.5  12     9.5   10     stop level 9.90 -> SELL 90 @ 9.90, cash 901
     7   2026-01-12   9.8  10.2   9.6   10
     8   2026-01-13  10    11.5   9.9   11     BUY signal
     9   2026-01-14  10.8  12.5  10.5   12     BUY 75 @ 12, cash 1
    10   2026-01-15  12    12.4  11.8   12.2   end equity 916

--cooldown 3 blocks bars 7, 8, 9: the bar 9 buy is skipped and counted, end 901.
--cooldown 2 (or 1) ends before bar 9: the buy fills, end 916.
The other cases are worked out in test_cooldown.py.
"""

import pytest

from trading_assistant.cli import main

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
"""
CLOSES_ONLY = "date,close\n2026-01-01,10\n2026-01-02,9\n2026-01-05,8\n2026-01-06,9\n2026-01-07,11\n"
B = ["--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
STOP = ["--stop-loss", "10"]

BUY_1 = "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal"
STOP_SELL = "    #2   bar 6     SELL       90 @       9.90  value       891.00  cost     0.00  cash       901.00  stop"
BUY_2 = "    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash         1.00  signal"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
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


def ok(argv, capsys):
    code, out, err = run(argv, capsys)
    assert (code, err) == (0, ""), err
    return out.splitlines()


def usage_error(argv, capsys, message):
    code, out, err = run(argv, capsys)
    assert (code, out) == (2, "")
    assert err.startswith("usage: trading_assistant.cli ")
    assert err.endswith(f"\ntrading_assistant.cli: error: {message}\n")


def fill_lines(lines):
    return [line for line in lines if line.startswith("    #")]


def cooldown_line(lines):
    found = [line for line in lines if line.startswith("  Cooldown:")]
    assert len(found) == 1, found
    return found[0]


# --------------------------------------------------------------------------- the hand case


def test_cooldown_3_report(folder, capsys):
    code, out, err = run(["hand.csv", *B, *STOP, "--cooldown", "3"], capsys)
    assert (code, err) == (0, "")
    assert out == (
        "Bars:    11\n"
        "Last:    12.20\n"
        "Signal:  HOLD\n"
        "RSI:     n/a\n"
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
        "  Start cash:  1,000.00\n"
        "  Trades:      2 (1 buy, 1 sell)\n"
        "  Fills (bar index is 0-based):\n"
        f"{BUY_1}\n"
        f"{STOP_SELL}\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        "  Exits:       stop 10.00% below entry\n"
        "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              901.00      1,220.00\n"
        "    Return                  -9.90%       +22.00%\n"
        "    Max drawdown           -17.34%       -20.00%\n"
        "    Trades                       2             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    901.00\n"
        "  End shares:  0 @ 12.20\n"
        "  End equity:  901.00\n"
        "  Return:      -9.90%\n"
        "Research aid only. Not financial advice.\n"
    )


def test_cooldown_2_report(folder, capsys):
    code, out, err = run(["hand.csv", *B, *STOP, "--cooldown", "2"], capsys)
    assert (code, err) == (0, "")
    assert out == (
        "Bars:    11\n"
        "Last:    12.20\n"
        "Signal:  HOLD\n"
        "RSI:     n/a\n"
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
        "  Start cash:  1,000.00\n"
        "  Trades:      3 (2 buy, 1 sell)\n"
        "  Fills (bar index is 0-based):\n"
        f"{BUY_1}\n"
        f"{STOP_SELL}\n"
        f"{BUY_2}\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        "  Exits:       stop 10.00% below entry\n"
        "  Cooldown:    2 bars after a stop, trail or atr exit; 0 buys skipped\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              916.00      1,220.00\n"
        "    Return                  -8.40%       +22.00%\n"
        "    Max drawdown           -17.34%       -20.00%\n"
        "    Trades                       3             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    1.00\n"
        "  End shares:  75 @ 12.20\n"
        "  End equity:  916.00\n"
        "  Return:      -8.40%\n"
        "Research aid only. Not financial advice.\n"
    )


def test_the_only_difference_from_a_run_without_it_is_the_cooldown_line(folder, capsys):
    without = ok(["hand.csv", *B, *STOP], capsys)
    with_2 = ok(["hand.csv", *B, *STOP, "--cooldown", "2"], capsys)
    assert [line for line in with_2 if not line.startswith("  Cooldown:")] == without
    assert with_2.index(cooldown_line(with_2)) == with_2.index("  Exits:       stop 10.00% below entry") + 1


def test_cooldown_1_is_allowed_and_says_bar(folder, capsys):
    lines = ok(["hand.csv", *B, *STOP, "--cooldown", "1"], capsys)
    assert fill_lines(lines) == [BUY_1, STOP_SELL, BUY_2]
    assert cooldown_line(lines) == "  Cooldown:    1 bar after a stop, trail or atr exit; 0 buys skipped"


def test_a_cooldown_longer_than_the_file_is_fine(folder, capsys):
    lines = ok(["hand.csv", *B, *STOP, "--cooldown", "1000"], capsys)
    assert fill_lines(lines) == [BUY_1, STOP_SELL]
    assert cooldown_line(lines) == "  Cooldown:    1000 bars after a stop, trail or atr exit; 1 buy skipped"


def test_order_of_the_options_does_not_matter(folder, capsys):
    a = run(["hand.csv", *B, *STOP, "--cooldown", "3"], capsys)
    b = run(["--cooldown", "3", "hand.csv", "--stop-loss", "10", *B], capsys)
    c = run(["hand.csv", *B, *STOP, "--cooldown=3"], capsys)
    assert a == b == c


def test_shortened_name(folder, capsys):
    assert run(["hand.csv", *B, *STOP, "--coo", "3"], capsys) == run(["hand.csv", *B, *STOP, "--cooldown", "3"], capsys)


# --------------------------------------------------------------------------- which sells start a cooldown


def test_trailing_stop_starts_one(folder, capsys):
    lines = ok(["hand.csv", *B, "--trailing-stop", "10", "--cooldown", "3"], capsys)
    assert [line.split()[-3:] for line in fill_lines(lines)] == [["cash", "10.00", "signal"], ["cash", "982.00", "trail"]]
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped"
    assert "  End equity:  982.00" in lines


def test_atr_stop_starts_one(folder, capsys):
    lines = ok(["hand.csv", *B, "--atr-stop", "--atr-mult", "1", "--atr-period", "1", "--cooldown", "3"], capsys)
    assert [line.split()[-3:] for line in fill_lines(lines)] == [["cash", "10.00", "signal"], ["cash", "865.00", "atr"]]
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped"
    assert "  End equity:  865.00" in lines


def test_take_profit_sell_starts_none(folder, capsys):
    # The target sells on bar 5; a cooldown of 4 would block bars 6 to 9, but bar 9 still buys.
    lines = ok(["hand.csv", *B, *STOP, "--take-profit", "5", "--cooldown", "4"], capsys)
    assert [line.split()[1:3] + line.split()[-1:] for line in fill_lines(lines)] == [
        ["bar", "4", "signal"], ["bar", "5", "target"], ["bar", "9", "signal"],
    ]
    assert cooldown_line(lines) == "  Cooldown:    4 bars after a stop, trail or atr exit; 0 buys skipped"
    assert "  End equity:  1,066.90" in lines


def test_signal_sell_starts_none(folder, capsys):
    # A 50 % stop is never reached; the signal sells on bar 7 and bar 9 still buys.
    lines = ok(["hand.csv", *B, "--stop-loss", "50", "--cooldown", "3"], capsys)
    assert [line.split()[1:3] + line.split()[-1:] for line in fill_lines(lines)] == [
        ["bar", "4", "signal"], ["bar", "7", "signal"], ["bar", "9", "signal"],
    ]
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 0 buys skipped"
    assert "  End equity:  925.00" in lines


def test_open_fills(folder, capsys):
    lines = ok(["hand.csv", *B, *STOP, "--fill", "open", "--cooldown", "3"], capsys)
    assert [line.split()[-3:] for line in fill_lines(lines)] == [["cash", "6.40", "signal"], ["cash", "900.64", "stop"]]
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped"


# --------------------------------------------------------------------------- counting


def test_every_blocked_buy_is_counted(folder, capsys):
    # breakout window 1 has buys due on bars 9 and 10; a cooldown of 4 blocks both.
    lines = ok(["hand.csv", *B, *STOP, "--strategy", "breakout", "--param", "window=1", "--cooldown", "4"], capsys)
    assert fill_lines(lines) == [BUY_1, STOP_SELL]
    assert cooldown_line(lines) == "  Cooldown:    4 bars after a stop, trail or atr exit; 2 buys skipped"


def test_a_blocked_buy_that_would_get_no_shares_counts_as_cooldown_not_risk(folder, capsys):
    risk = ["--atr-stop", "--atr-mult", "1", "--atr-period", "1", "--risk-pct", "0.16"]
    without = ok(["hand.csv", *B, *risk], capsys)
    assert "  Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)" in without
    lines = ok(["hand.csv", *B, *risk, "--cooldown", "3"], capsys)
    assert not [line for line in lines if line.startswith("  Skipped:")]
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped"
    assert fill_lines(lines) == fill_lines(without)


# --------------------------------------------------------------------------- next to the other output options


def test_export(folder, capsys):
    lines = ok(["hand.csv", *B, *STOP, "--cooldown", "3", "--export", "E.csv"], capsys)
    assert lines[-2:] == ["  Exported:    11 rows to E.csv", "Research aid only. Not financial advice."]
    rows = (folder / "E.csv").read_text().splitlines()
    assert [row.split(",")[4] for row in rows[1:]] == ["", "", "", "", "BUY", "", "SELL", "", "", "", ""]


def test_stats_and_chart(folder, capsys):
    lines = ok(["hand.csv", *B, *STOP, "--cooldown", "3", "--stats", "--chart"], capsys)
    assert lines.index(cooldown_line(lines)) < lines.index("Risk and return") < lines.index(
        "Chart:   close, 11 bars, B = buy, S = sell"
    )


def test_json_fills_follow_the_cooldown(folder, capsys):
    import json

    data = json.loads("\n".join(ok(["hand.csv", *B, *STOP, "--cooldown", "3", "--json"], capsys)))
    assert [(f["bar"], f["side"], f["reason"]) for f in data["backtest"]["fills"]] == [(4, "BUY", "signal"), (6, "SELL", "stop")]
    assert data["backtest"]["final_equity"] == pytest.approx(901)


# --------------------------------------------------------------------------- config file


def test_a_stop_from_the_config_file_counts(folder, capsys):
    (folder / "stop.ini").write_text("[cli]\nstop_loss = 10\n")
    lines = ok(["hand.csv", *B, "--cooldown", "3", "--config", "stop.ini"], capsys)
    assert lines == ok(["hand.csv", *B, *STOP, "--cooldown", "3"], capsys)
    (folder / "atr.ini").write_text("[cli]\natr_stop = yes\natr_mult = 1\natr_period = 1\n")
    lines = ok(["hand.csv", *B, "--cooldown", "3", "--config", "atr.ini"], capsys)
    assert cooldown_line(lines) == "  Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped"


def test_a_config_file_with_only_a_target_is_not_enough(folder, capsys):
    (folder / "tp.ini").write_text("[cli]\ntake_profit = 5\n")
    usage_error(
        ["hand.csv", *B, "--cooldown", "3", "--config", "tp.ini"], capsys,
        "--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop",
    )


# --------------------------------------------------------------------------- usage errors (exit 2)

NEEDS_STOP = "--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop"


def test_needs_backtest(folder, capsys):
    usage_error(["hand.csv", "--cooldown", "3"], capsys, "--cooldown only makes sense together with --backtest")
    usage_error(["hand.csv", "--cooldown", "0"], capsys, "--cooldown only makes sense together with --backtest")
    # With a stop but no --backtest, the stop's own message comes first, as before.
    usage_error(["hand.csv", *STOP, "--cooldown", "3"], capsys, "--stop-loss only makes sense together with --backtest")


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--take-profit", "5"],
        ["--risk-pct", "2"],
        ["--fill", "open", "--slippage", "0.1", "--position-size", "0.5"],
    ],
    ids=["nothing", "take-profit", "risk-pct", "other settings"],
)
def test_needs_a_stop(folder, capsys, extra):
    usage_error(["hand.csv", *B, *extra, "--cooldown", "3"], capsys, NEEDS_STOP)


@pytest.mark.parametrize("stop", [["--stop-loss", "10"], ["--trailing-stop", "10"], ["--atr-stop"]])
def test_any_one_stop_is_enough(folder, capsys, stop):
    assert run(["hand.csv", *B, *stop, "--cooldown", "3"], capsys)[0] == 0


def test_needs_a_stop_comes_before_the_range_check(folder, capsys):
    usage_error(["hand.csv", *B, "--cooldown", "0"], capsys, NEEDS_STOP)


@pytest.mark.parametrize(
    "value, message",
    [
        ("0", "--cooldown must be a whole number of at least 1, got 0"),
        ("-2", "--cooldown must be a whole number of at least 1, got -2"),
        ("1.5", "argument --cooldown: invalid int value: '1.5'"),
        ("2.0", "argument --cooldown: invalid int value: '2.0'"),
        ("x", "argument --cooldown: invalid int value: 'x'"),
        ("", "argument --cooldown: invalid int value: ''"),
    ],
)
def test_must_be_a_whole_number_of_at_least_1(folder, capsys, value, message):
    usage_error(["hand.csv", *B, *STOP, f"--cooldown={value}"], capsys, message)


def test_needs_a_value(folder, capsys):
    usage_error(["hand.csv", *B, *STOP, "--cooldown"], capsys, "argument --cooldown: expected one argument")


def test_with_resample_the_stop_is_refused_as_before(folder, capsys):
    usage_error(
        ["hand.csv", *B, *STOP, "--cooldown", "3", "--resample", "weekly"], capsys,
        "--stop-loss cannot be combined with --resample yet",
    )


def test_not_with_scan(folder, capsys):
    usage_error(["--scan", "scan", "--cooldown", "3"], capsys, "--cooldown cannot be combined with --scan")


# --------------------------------------------------------------------------- data errors (exit 1)


def test_a_close_only_file_is_refused_as_with_the_stop_alone(folder, capsys):
    code, out, err = run(["closes.csv", *B, *STOP, "--cooldown", "3"], capsys)
    assert (code, out) == (1, "")
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")
    assert (code, out, err) == run(["closes.csv", *B, *STOP], capsys)
