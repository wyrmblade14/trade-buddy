"""Tests for filling at the next bar's open (``fill="open"`` / ``--fill open``).

Hand-worked candle series with short=2, long=3 (closes are the LOSS sample of
test_backtest.py, so the signals are already worked out there):

    bar   open  close            signal at close
     0      9    10
     1      9    10
     2      9    10
     3      9    10              sma2=10, sma3=10
     4     12    14              sma2=12, sma3=11.33 -> BUY
     5     13    14
     6     15    14
     7      9     8              sma2=11, sma3=12    -> SELL
     8      7     8
     9      8     8

Close fills (default, unchanged): BUY on bar 5 @ 14 -> 714 shares, cash 4;
    SELL on bar 8 @ 8 -> 5,712, cash 5,716.
Open fills: BUY on bar 5 @ open 13 -> floor(10000 / 13) = 769 shares,
    cost 9,997, cash 3. Equity at bar 5's close: 3 + 769 * 14 = 10,769.
    SELL on bar 8 @ open 7 -> 769 * 7 = 5,383, cash 5,386.
    End: 0 shares, equity 5,386, return (5386 - 10000) / 10000 = -46.14 %.
"""

import pytest

from trading_assistant.backtest import FILLS, format_result, run_backtest, run_buy_and_hold
from trading_assistant.cli import main
from trading_assistant.signals import BUY, SELL

OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 15.0, 9.0, 7.0, 8.0]
CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
SMA = dict(short=2, long=3)


def candle_text(opens=OPENS, closes=CLOSES):
    rows = ["date,open,high,low,close,volume"]
    for t, (o, c) in enumerate(zip(opens, closes)):
        rows.append(f"2026-01-{t + 1:02d},{o},{max(o, c) + 1},{min(o, c) - 1},{c},{(t + 1) * 1000}")
    return "\n".join(rows) + "\n"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.cash_after) for t in result.trades]


def run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- engine: hand-worked fills


def test_open_fills_hand_worked():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    assert fills(r) == [(5, BUY, 769, 13.0, 3.0), (8, SELL, 769, 7.0, 5386.0)]
    assert r.fill == "open"
    assert r.final_cash == 5386.0 and r.final_position == 0 and r.final_price == 8.0
    assert r.final_equity == 5386.0
    assert r.return_pct == pytest.approx(-46.14)
    (rt,) = r.round_trips
    assert (rt.entry_bar, rt.exit_bar, rt.shares, rt.outlay, rt.proceeds) == (5, 8, 769, 9997.0, 5383.0)


def test_open_fills_mark_account_value_at_the_close_not_the_open():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    day = r.daily[5]
    assert day.trade is not None and day.trade.price == 13.0  # filled at the open ...
    assert day.cash == 3.0 and day.position == 769
    assert day.equity == 3.0 + 769 * 14.0  # ... but valued at the close (10,769)
    assert r.daily[8].equity == 5386.0


def test_close_fills_are_the_default_and_unchanged():
    default = run_backtest(CLOSES, **SMA)
    assert default.fill == "close"
    assert fills(default) == [(5, BUY, 714, 14.0, 4.0), (8, SELL, 714, 8.0, 5716.0)]
    assert run_backtest(CLOSES, fill="close", **SMA) == default
    # opens are ignored when filling at the close
    assert run_backtest(CLOSES, fill="close", opens=OPENS, **SMA) == default


def test_signals_and_fill_bars_are_identical_for_both_fills_only_prices_differ():
    at_close = run_backtest(CLOSES, **SMA)
    at_open = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    assert [d.signal for d in at_close.daily] == [d.signal for d in at_open.daily]
    assert [t.bar for t in at_close.trades] == [t.bar for t in at_open.trades] == [5, 8]
    assert [t.price for t in at_close.trades] == [14.0, 8.0]
    assert [t.price for t in at_open.trades] == [13.0, 7.0]


def test_changing_the_fill_bars_close_does_not_change_an_open_fill():
    # The BUY signal is decided at bar 4 from closes[0..4]; the fill is at bar 5's open.
    base = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    for new_close in (11.0, 20.0, 100.0):
        changed = list(CLOSES)
        changed[5] = new_close
        r = run_backtest(changed, fill="open", opens=OPENS, **SMA)
        assert r.trades[0] == base.trades[0] == r.trades[0].__class__(5, BUY, 769, 13.0, 3.0, 0.0)
        assert r.daily[5].equity == 3.0 + 769 * new_close  # only the mark-to-market moves
        # ... whereas a close fill on the same bar does change with that close
        c = run_backtest(changed, **SMA)
        assert c.trades[0].bar == 5 and c.trades[0].price == new_close != 14.0


def test_changing_the_fill_bars_open_changes_only_the_open_fill_price():
    changed = list(OPENS)
    changed[5] = 10.0  # cheaper open on the fill bar: 1000 shares for 10,000
    r = run_backtest(CLOSES, fill="open", opens=changed, **SMA)
    assert r.trades[0].bar == 5 and r.trades[0].shares == 1000 and r.trades[0].price == 10.0
    assert [d.signal for d in r.daily] == [d.signal for d in run_backtest(CLOSES, fill="open", opens=OPENS, **SMA).daily]
    # a close fill never looks at the opens
    assert run_backtest(CLOSES, fill="close", opens=changed, **SMA) == run_backtest(CLOSES, **SMA)


def test_open_fills_with_costs_use_the_open_for_the_percentage_fee():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, fee=5, fee_pct=1, **SMA)
    buy = r.trades[0]
    # floor((10000 - 5) / (13 * 1.01)) = 761; 761 * 13 = 9,893; fee 5 + 98.93 = 103.93; total 9,996.93
    assert (buy.bar, buy.shares, buy.price) == (5, 761, 13.0)
    assert buy.cost == pytest.approx(103.93)
    assert buy.cash_after == pytest.approx(10000 - 9893 - 103.93)


def test_benchmark_buys_at_the_first_open_with_open_fills():
    at_close = run_backtest(CLOSES, **SMA)
    at_open = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    assert at_close.benchmark == run_buy_and_hold(CLOSES)
    assert at_open.benchmark.shares == 1111  # bought at opens[0] = 9, like the strategy's open fills


def test_format_result_names_open_fills_and_keeps_the_default_line():
    at_open = run_backtest(CLOSES, fill="open", opens=OPENS, **SMA)
    assert format_result(at_open, 2, 3)[0] == "Backtest: SMA 2/3 crossover, next-bar open fills, whole shares, no shorting"
    at_close = run_backtest(CLOSES, **SMA)
    assert format_result(at_close, 2, 3)[0] == "Backtest: SMA 2/3 crossover, next-bar fills, whole shares, no shorting"


def test_fills_constant():
    assert FILLS == ("close", "open")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(fill="open"), "fill on open needs the open price of every bar"),
        (dict(fill="open", opens=OPENS[:-1]), "9 opens but 10 closes"),
        (dict(fill="open", opens=OPENS[:5] + [0.0] + OPENS[6:]), "bar 5: open must be positive, got 0.0"),
        (dict(fill="open", opens=OPENS[:5] + [-1.0] + OPENS[6:]), "bar 5: open must be positive, got -1.0"),
        (dict(fill="midpoint", opens=OPENS), "unknown fill 'midpoint'; choose one of: close, open"),
    ],
    ids=["no opens", "wrong length", "zero open", "negative open", "unknown fill"],
)
def test_run_backtest_rejects_bad_fill_settings(kwargs, message):
    with pytest.raises(ValueError) as excinfo:
        run_backtest(CLOSES, **SMA, **kwargs)
    assert str(excinfo.value) == message


# --------------------------------------------------------------------------- CLI


def test_cli_fill_open_reports_hand_worked_fills(tmp_path, capsys):
    path = write(tmp_path, "hand.csv", candle_text())
    code, out, err = run([path, "--backtest", "--short", "2", "--long", "3", "--fill", "open"], capsys)
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert "Backtest: SMA 2/3 crossover, next-bar open fills, whole shares, no shorting" in lines
    fill_lines = [line for line in lines if line.startswith("    #")]
    assert len(fill_lines) == 2
    assert fill_lines[0].split() == ["#1", "bar", "5", "BUY", "769", "@", "13.00", "value", "9,997.00", "cost", "0.00", "cash", "3.00"]
    assert fill_lines[1].split() == ["#2", "bar", "8", "SELL", "769", "@", "7.00", "value", "5,383.00", "cost", "0.00", "cash", "5,386.00"]
    assert "  End cash:    5,386.00" in lines
    assert "  Return:      -46.14%" in lines


def test_cli_fill_close_is_the_default_and_gives_identical_output(tmp_path, capsys):
    path = write(tmp_path, "hand.csv", candle_text())
    argv = [path, "--backtest", "--short", "2", "--long", "3", "--stats", "--chart"]
    assert run(argv, capsys) == run(argv + ["--fill", "close"], capsys)
    code, out, _ = run(argv, capsys)
    assert code == 0 and "next-bar fills, whole shares" in out and "714 @" in out


def test_cli_fill_open_export_records_the_open_fill_price(tmp_path, capsys):
    path = write(tmp_path, "hand.csv", candle_text())
    export = tmp_path / "out.csv"
    code, _, err = run([path, "--backtest", "--short", "2", "--long", "3", "--fill", "open", "--export", str(export)], capsys)
    assert code == 0 and err == ""
    rows = [line.split(",") for line in export.read_text().splitlines()]
    header = rows[0]
    bar5 = rows[1 + 5]
    assert bar5[header.index("action")] == BUY
    assert bar5[header.index("price")] == "13.00"
    assert bar5[header.index("close")] == "14.00"
    assert bar5[header.index("equity")] == "10769.00"


def test_cli_fill_open_works_together_with_candles_flag(tmp_path, capsys):
    path = write(tmp_path, "hand.csv", candle_text())
    argv = [path, "--backtest", "--short", "2", "--long", "3", "--fill", "open"]
    assert run(argv, capsys) == run(argv + ["--candles"], capsys)


def test_cli_fill_open_on_close_only_file_is_one_error_line_exit_1(tmp_path, capsys):
    path = write(tmp_path, "closes.csv", "date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate(CLOSES)))
    code, out, err = run([path, "--backtest", "--short", "2", "--long", "3", "--fill", "open"], capsys)
    assert code == 1 and out == ""
    assert err == (
        f"Error: {path} has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); "
        "expected a header row like 'date,open,high,low,close,volume' followed by rows like "
        "'2026-01-02,100.5,103.0,99.5,101.5,12000'\n"
    )


def test_cli_fill_open_on_candle_file_without_open_column_is_one_error_line_exit_1(tmp_path, capsys):
    text = "date,high,low,close,volume\n" + "".join(f"2026-01-{t + 1:02d},{c + 1},{c - 1},{c},1000\n" for t, c in enumerate(CLOSES))
    path = write(tmp_path, "noopen.csv", text)
    code, out, err = run([path, "--backtest", "--short", "2", "--long", "3", "--fill", "open"], capsys)
    assert code == 1 and out == ""
    assert err.startswith(f"Error: {path} has no 'open' column (found columns: 'date', 'high', 'low', 'close', 'volume'); expected ")
    assert len(err.splitlines()) == 1 and "Traceback" not in err


@pytest.mark.parametrize("fill", ["open", "close"])
def test_cli_fill_without_backtest_is_a_usage_error(tmp_path, capsys, fill):
    path = write(tmp_path, "hand.csv", candle_text())
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--fill", fill])
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == "trading_assistant.cli: error: --fill only makes sense together with --backtest"


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_cli_fill_open_with_resample_is_a_usage_error(tmp_path, capsys, period):
    path = write(tmp_path, "hand.csv", candle_text())
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--backtest", "--fill", "open", "--resample", period])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == "trading_assistant.cli: error: --fill open cannot be combined with --resample yet"


def test_cli_fill_close_with_resample_is_allowed(tmp_path, capsys):
    path = write(tmp_path, "closes.csv", "date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate(CLOSES)))
    code, out, err = run([path, "--backtest", "--short", "1", "--long", "2", "--fill", "close", "--resample", "weekly"], capsys)
    assert code == 0 and err == ""


def test_cli_unknown_fill_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([write(tmp_path, "hand.csv", candle_text()), "--backtest", "--fill", "midpoint"])
    assert excinfo.value.code == 2
    assert "invalid choice: 'midpoint'" in capsys.readouterr().err


def test_help_mentions_fill(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "--fill" in capsys.readouterr().out
