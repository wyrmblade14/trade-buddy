"""Tests for the stop loss and take profit (``stop_pct`` / ``take_profit_pct``,
``--stop-loss`` / ``--take-profit``).

Hand-worked candle series, short=2, long=3 (closes are the LOSS sample of
test_backtest.py: BUY signal at bar 4 fills bar 5, SELL signal at bar 7
fills bar 8):

    bar   open  high   low  close
     0      9    11     8     10
     1      9    11     8     10
     2      9    11     8     10
     3      9    11     8     10
     4     12    15    11     14      BUY signal
     5     13    15  12.9     14      BUY fills @ 14 (close) -> 714 shares, cash 4; entry 14
     6     14    17    12     14      touches both: 17 >= 16.8 (target 20 %) and 12 <= 12.6 (stop 10 %)
     7      9    10   7.5      8      SELL signal
     8      7     9   6.9      8
     9      8     9   7.5      8

Stop 10 % (stop price 14 * 0.9 = 12.6), no target:
    bar 6 low 12 <= 12.6 -> SELL 714 @ 12.60 = 8,996.40, cash 9,000.40, reason stop.
Target 20 % (target 14 * 1.2 = 16.8), no stop:
    bar 6 high 17 >= 16.8 -> SELL 714 @ 16.80 = 11,995.20, cash 11,999.20, reason target.
Stop 10 % and target 20 %: bar 6 touches both -> the stop wins: 714 @ 12.60, cash 9,000.40.
Stop 50 % (stop price 7): bar 7 low 7.5 > 7; bar 8 low 6.9 <= 7 -> SELL 714 @ 7.00 =
    4,998, cash 5,002, reason stop; the signal sell due on bar 8 (@ 8) is cancelled.
Stop 10 % with fee 5 + 1 %: BUY 706 @ 14 (cash 12.16, from test_backtest_metrics);
    bar 6 stop @ 12.6: value 706 * 12.6 = 8,895.60, fee 5 + 88.956 = 93.956,
    cash 12.16 + 8895.60 - 93.956 = 8,813.804.
Open fills, stop 10 %: BUY bar 5 @ open 13 -> 769 shares, cash 3; entry 13, stop 11.7;
    bar 6 low 12 > 11.7; bar 7 gaps down, opening at 9 <= 11.7 -> the stop fills at that
    open, not at 11.7: SELL 769 @ 9.00 = 6,921.00, cash 6,924.00.
"""

import pytest

from trading_assistant.backtest import (
    EXPORT_COLUMNS,
    Trade,
    export_columns,
    export_rows,
    format_result,
    run_backtest,
    run_buy_and_hold,
)
from trading_assistant.cli import main
from trading_assistant.signals import BUY, SELL

OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0]
HIGHS = [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0]
LOWS = [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5]
CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
SMA = dict(short=2, long=3)
HL = dict(highs=HIGHS, lows=LOWS)
A = pytest.approx


def candle_text():
    rows = ["date,open,high,low,close,volume"]
    for t in range(len(CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{OPENS[t]},{HIGHS[t]},{LOWS[t]},{CLOSES[t]},{(t + 1) * 1000}")
    return "\n".join(rows) + "\n"


def write_candles(tmp_path):
    path = tmp_path / "exits.csv"
    path.write_text(candle_text())
    return str(path)


def write_closes(tmp_path):
    path = tmp_path / "closes.csv"
    path.write_text("date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate(CLOSES)))
    return str(path)


def run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.cash_after, t.reason) for t in result.trades]


# --------------------------------------------------------------------------- engine, hand-worked


def test_stop_loss_hand_worked():
    r = run_backtest(CLOSES, stop_pct=10, **HL, **SMA)
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (6, SELL, 714, 12.6, 9000.4, "stop")]
    assert r.final_cash == A(9000.4) and r.final_position == 0
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.shares) == (5, 6, 714) and rt.proceeds == A(8996.4)
    assert r.daily[6].equity == A(9000.4)


def test_take_profit_hand_worked():
    r = run_backtest(CLOSES, take_profit_pct=20, **HL, **SMA)
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (6, SELL, 714, 16.8, 11999.2, "target")]
    assert r.round_trips[0].is_win


def test_bar_touching_both_levels_is_a_stop():
    r = run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, **HL, **SMA)
    assert HIGHS[6] >= 14 * 1.2 and LOWS[6] <= 14 * 0.9  # bar 6 really touches both
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (6, SELL, 714, 12.6, 9000.4, "stop")]
    assert r.trades[1].reason == "stop"


def test_stop_on_a_bar_cancels_that_bars_signal_sell():
    # Stop 50 % -> stop price 7. Bar 7 low 7.5 does not reach it; bar 8 low 6.9 does,
    # so the stop fills at 7 and the signal sell that was due at bar 8's close (@ 8) is dropped.
    r = run_backtest(CLOSES, stop_pct=50, **HL, **SMA)
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (8, SELL, 714, 7.0, 5002.0, "stop")]
    assert r.daily[8].trade is r.trades[1]
    plain = run_backtest(CLOSES, **SMA)
    assert fills(plain)[1] == (8, SELL, 714, 8.0, 5716.0, "signal")


def test_stop_with_fees_hand_worked():
    r = run_backtest(CLOSES, stop_pct=10, fee=5, fee_pct=1, **HL, **SMA)
    buy, stop = r.trades
    assert (buy.bar, buy.shares, buy.price) == (5, 706, 14.0) and buy.cash_after == A(12.16)
    assert (stop.bar, stop.shares, stop.price, stop.reason) == (6, 706, 12.6, "stop")
    assert stop.cost == A(93.956)
    assert stop.cash_after == A(8813.804)
    assert r.total_costs == A(103.84 + 93.956)


def test_stop_with_open_fills_uses_the_open_entry_price():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, stop_pct=10, **HL, **SMA)
    buy, stop = r.trades
    assert (buy.bar, buy.side, buy.shares, buy.price, buy.cash_after, buy.reason) == (5, BUY, 769, 13.0, 3.0, "signal")
    assert (stop.bar, stop.side, stop.shares, stop.reason) == (7, SELL, 769, "stop")
    assert stop.price == A(9.0) and stop.cash_after == A(6924.0)  # bar 6 low 12 > 11.7; bar 7 opens at 9 < 11.7: fills at the open


def test_exit_is_not_checked_on_the_entry_bar():
    # Bar 5 low 12.9 is at or below a 7.9 % stop (14 * 0.921 = 12.894 > 12.9? no: use 8 %: 12.88 < 12.9 -> not hit;
    # use 10 % on a copy whose bar-5 low is 1.0): the buy happens at bar 5's close, so bar 5's range is ignored.
    lows = list(LOWS)
    lows[5] = 1.0
    r = run_backtest(CLOSES, stop_pct=10, highs=HIGHS, lows=lows, **SMA)
    assert [t.bar for t in r.trades] == [5, 6]  # still stopped at bar 6, not bar 5


def test_stop_and_target_prices_are_relative_to_the_price_paid_including_slippage():
    r = run_backtest(CLOSES, stop_pct=10, slippage_pct=1, **HL, **SMA)
    buy, stop = r.trades
    assert buy.price == A(14.14)
    # stop level 14.14 * 0.9 = 12.726 (bar 6 low 12 reaches it); the stop is a sell, so it slips 1 % lower
    assert stop.price == A(12.726 * 0.99)
    assert stop.reason == "stop"


def test_position_size_and_exits_work_together():
    r = run_backtest(CLOSES, position_size=0.5, stop_pct=10, **HL, **SMA)
    assert fills(r) == [(5, BUY, 357, 14.0, 5002.0, "signal"), (6, SELL, 357, 12.6, 5002.0 + 357 * 12.6, "stop")]


def test_no_exit_when_levels_are_never_reached():
    r = run_backtest(CLOSES, stop_pct=60, take_profit_pct=50, **HL, **SMA)
    assert fills(r) == fills(run_backtest(CLOSES, **SMA))  # trades identical, all signal
    assert r.has_exits and all(t.reason == "signal" for t in r.trades)


# --------------------------------------------------------------------------- unchanged without the options


def test_without_exits_everything_is_unchanged():
    base = run_backtest(CLOSES, **SMA)
    assert fills(base) == [(5, BUY, 714, 14.0, 4.0, "signal"), (8, SELL, 714, 8.0, 5716.0, "signal")]
    assert run_backtest(CLOSES, stop_pct=None, take_profit_pct=None, **HL, **SMA) == base
    assert base.stop_pct is None and base.take_profit_pct is None and not base.has_exits
    assert Trade(5, BUY, 714, 14.0, 4.0) == Trade(5, BUY, 714, 14.0, 4.0, 0.0, "signal")  # old constructor form
    assert export_columns(base) == EXPORT_COLUMNS
    assert all(len(row) == len(EXPORT_COLUMNS) for row in export_rows(base))
    lines = format_result(base, 2, 3)
    assert not any("Exits" in line or line.endswith("signal") for line in lines)


def test_benchmark_is_not_affected_by_exits():
    assert run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, **HL, **SMA).benchmark == run_buy_and_hold(CLOSES)


# --------------------------------------------------------------------------- report and export


def test_report_shows_reason_per_fill_and_the_exit_rule():
    lines = format_result(run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, **HL, **SMA), 2, 3)
    assert [line for line in lines if line.startswith("    #")] == [
        "    #1   bar 5     BUY       714 @      14.00  value     9,996.00  cost     0.00  cash         4.00  signal",
        "    #2   bar 6     SELL      714 @      12.60  value     8,996.40  cost     0.00  cash     9,000.40  stop",
    ]
    assert "  Exits:       stop 10.00% below entry, target 20.00% above entry (stop wins if a bar touches both)" in lines
    only_stop = format_result(run_backtest(CLOSES, stop_pct=10, **HL, **SMA), 2, 3)
    assert "  Exits:       stop 10.00% below entry" in only_stop
    only_target = format_result(run_backtest(CLOSES, take_profit_pct=20, **HL, **SMA), 2, 3)
    assert "  Exits:       target 20.00% above entry" in only_target
    assert any(line.endswith("  target") for line in only_target)


def test_export_has_a_reason_column_with_exits():
    r = run_backtest(CLOSES, stop_pct=10, **HL, **SMA)
    assert export_columns(r) == EXPORT_COLUMNS + ["reason"]
    rows = export_rows(r)
    assert [row[-1] for row in rows] == ["", "", "", "", "", "signal", "stop", "", "", ""]
    assert rows[6][EXPORT_COLUMNS.index("price")] == "12.60"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(stop_pct=0, **HL), "stop_pct must be between 0 and 100 (both exclusive), got 0"),
        (dict(stop_pct=100, **HL), "stop_pct must be between 0 and 100 (both exclusive), got 100"),
        (dict(take_profit_pct=0, **HL), "take_profit_pct must be positive, got 0"),
        (dict(take_profit_pct=-5, **HL), "take_profit_pct must be positive, got -5"),
        (dict(stop_pct=10), "a stop loss or take profit needs the high and low of every bar"),
        (dict(take_profit_pct=10, highs=HIGHS), "a stop loss or take profit needs the high and low of every bar"),
        (dict(stop_pct=10, highs=HIGHS[:-1], lows=LOWS), "9 highs and 10 lows but 10 closes"),
    ],
    ids=["stop 0", "stop 100", "target 0", "target negative", "no highs/lows", "no lows", "wrong length"],
)
def test_run_backtest_rejects_bad_exit_settings(kwargs, message):
    with pytest.raises(ValueError) as excinfo:
        run_backtest(CLOSES, **SMA, **kwargs)
    assert str(excinfo.value) == message


# --------------------------------------------------------------------------- CLI


def test_cli_stop_and_target_hand_worked(tmp_path, capsys):
    code, out, err = run([write_candles(tmp_path), "--backtest", "--short", "2", "--long", "3", "--stop-loss", "10", "--take-profit", "20"], capsys)
    assert code == 0 and err == ""
    lines = out.splitlines()
    fill_lines = [line.split() for line in lines if line.startswith("    #")]
    assert fill_lines[0] == ["#1", "bar", "5", "BUY", "714", "@", "14.00", "value", "9,996.00", "cost", "0.00", "cash", "4.00", "signal"]
    assert fill_lines[1] == ["#2", "bar", "6", "SELL", "714", "@", "12.60", "value", "8,996.40", "cost", "0.00", "cash", "9,000.40", "stop"]
    assert "  Exits:       stop 10.00% below entry, target 20.00% above entry (stop wins if a bar touches both)" in lines
    assert "  End cash:    9,000.40" in lines


def test_cli_take_profit_only(tmp_path, capsys):
    code, out, err = run([write_candles(tmp_path), "--backtest", "--short", "2", "--long", "3", "--take-profit", "20"], capsys)
    assert code == 0 and err == ""
    fill_lines = [line.split() for line in out.splitlines() if line.startswith("    #")]
    assert fill_lines[1] == ["#2", "bar", "6", "SELL", "714", "@", "16.80", "value", "11,995.20", "cost", "0.00", "cash", "11,999.20", "target"]


def test_cli_export_includes_reason_column(tmp_path, capsys):
    export = tmp_path / "out.csv"
    code, _, err = run([write_candles(tmp_path), "--backtest", "--short", "2", "--long", "3", "--stop-loss", "10", "--export", str(export)], capsys)
    assert code == 0 and err == ""
    rows = [line.split(",") for line in export.read_text().splitlines()]
    assert rows[0] == EXPORT_COLUMNS + ["reason"]
    assert rows[1 + 5][-1] == "signal" and rows[1 + 6][-1] == "stop" and rows[1 + 7][-1] == ""
    assert rows[1 + 6][rows[0].index("price")] == "12.60"


def test_cli_export_without_exits_has_no_reason_column(tmp_path, capsys):
    export = tmp_path / "out.csv"
    code, _, _ = run([write_candles(tmp_path), "--candles", "--backtest", "--short", "2", "--long", "3", "--export", str(export)], capsys)
    assert code == 0
    assert export.read_text().splitlines()[0].split(",") == EXPORT_COLUMNS


def test_cli_without_exit_options_is_unchanged(tmp_path, capsys):
    path = write_candles(tmp_path)
    code, out, err = run([path, "--candles", "--backtest", "--short", "2", "--long", "3"], capsys)
    assert code == 0 and err == ""
    assert "Exits" not in out and "signal" not in out
    assert [line.split()[-1] for line in out.splitlines() if line.startswith("    #")] == ["4.00", "5,716.00"]


def test_cli_exit_options_read_the_file_as_candles(tmp_path, capsys):
    code, out, err = run([write_closes(tmp_path), "--backtest", "--short", "2", "--long", "3", "--stop-loss", "10"], capsys)
    assert code == 1 and out == ""
    assert err.startswith(f"Error: {write_closes(tmp_path)} has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected ")
    assert len(err.splitlines()) == 1


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--backtest", "--stop-loss", "0"], "--stop-loss must be between 0 and 100 (both exclusive), got 0"),
        (["--backtest", "--stop-loss", "-5"], "--stop-loss must be between 0 and 100 (both exclusive), got -5"),
        (["--backtest", "--stop-loss", "100"], "--stop-loss must be between 0 and 100 (both exclusive), got 100"),
        (["--backtest", "--stop-loss", "150"], "--stop-loss must be between 0 and 100 (both exclusive), got 150"),
        (["--backtest", "--take-profit", "0"], "--take-profit must be positive, got 0"),
        (["--backtest", "--take-profit", "-1"], "--take-profit must be positive, got -1"),
        (["--stop-loss", "10"], "--stop-loss only makes sense together with --backtest"),
        (["--take-profit", "10"], "--take-profit only makes sense together with --backtest"),
        (["--backtest", "--stop-loss", "10", "--resample", "weekly"], "--stop-loss cannot be combined with --resample yet"),
        (["--backtest", "--take-profit", "10", "--resample", "monthly"], "--take-profit cannot be combined with --resample yet"),
    ],
)
def test_cli_exit_usage_errors(tmp_path, capsys, argv, message):
    with pytest.raises(SystemExit) as excinfo:
        main([write_candles(tmp_path)] + argv)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == f"trading_assistant.cli: error: {message}"


def test_help_mentions_stop_loss_and_take_profit(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--stop-loss" in out and "--take-profit" in out
