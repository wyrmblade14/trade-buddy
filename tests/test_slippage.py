"""Tests for slippage (``slippage_pct`` / ``--slippage``).

A buy fills ``slippage_pct`` percent above the bar's fill price and a sell
that much below it, before fees. Hand-worked on the LOSS sample of
test_backtest.py with short=2, long=3 (BUY signal at bar 4 -> fill bar 5,
SELL signal at bar 7 -> fill bar 8); opens as in test_fill_open.py.

    closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]
    opens  = [ 9,  9,  9,  9, 12, 13, 15, 9, 7, 8]

Close fills, 1 % slippage, no fees:
    BUY  bar 5 @ 14 * 1.01 = 14.14: floor(10000 / 14.14) = 707 shares,
         707 * 14.14 = 9,996.98, cash 3.02.
    SELL bar 8 @ 8 * 0.99 = 7.92: 707 * 7.92 = 5,599.44, cash 5,602.46.
    Without slippage: 714 @ 14 (cash 4), 714 @ 8 (cash 5,716).

Close fills, 1 % slippage, fee 5 + 1 %:
    BUY  bar 5 @ 14.14: budget (10000 - 5) / (14.14 * 1.01) = 699.8 -> 699 shares,
         value 699 * 14.14 = 9,883.86, fee 5 + 98.8386 = 103.8386,
         cash 10000 - 9883.86 - 103.8386 = 12.3014.
    SELL bar 8 @ 7.92: value 699 * 7.92 = 5,536.08, fee 5 + 55.3608 = 60.3608,
         cash 12.3014 + 5536.08 - 60.3608 = 5,488.0206.

Open fills, 1 % slippage, no fees:
    BUY  bar 5 @ 13 * 1.01 = 13.13: floor(10000 / 13.13) = 761 shares,
         761 * 13.13 = 9,991.93, cash 8.07.
    SELL bar 8 @ 7 * 0.99 = 6.93: 761 * 6.93 = 5,273.73, cash 5,281.80.

Open fills, 1 % slippage, fee 5 + 1 %:
    BUY  bar 5 @ 13.13: (10000 - 5) / (13.13 * 1.01) = 753.7 -> 753 shares,
         value 753 * 13.13 = 9,886.89, fee 5 + 98.8689 = 103.8689, cash 9.2411.
    SELL bar 8 @ 6.93: value 753 * 6.93 = 5,218.29, fee 5 + 52.1829 = 57.1829,
         cash 9.2411 + 5218.29 - 57.1829 = 5,170.3482.
"""

import pytest

from trading_assistant.backtest import format_result, run_backtest, run_buy_and_hold
from trading_assistant.cli import build_parser, check_costs, main, validate_args
from trading_assistant.signals import BUY, SELL

CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 15.0, 9.0, 7.0, 8.0]
SMA = dict(short=2, long=3)
FEES = dict(fee=5, fee_pct=1)
A = pytest.approx


def candle_text():
    rows = ["date,open,high,low,close,volume"]
    for t, (o, c) in enumerate(zip(OPENS, CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{o},{max(o, c) + 1},{min(o, c) - 1},{c},{(t + 1) * 1000}")
    return "\n".join(rows) + "\n"


def write_candles(tmp_path):
    path = tmp_path / "hand.csv"
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


def check_fill(trade, bar, side, shares, price, cash_after, cost=0.0):
    assert (trade.bar, trade.side, trade.shares) == (bar, side, shares)
    assert trade.price == A(price)
    assert trade.cash_after == A(cash_after)
    assert trade.cost == A(cost)


# --------------------------------------------------------------------------- engine, hand-worked


def test_close_fills_with_slippage_no_fees():
    r = run_backtest(CLOSES, slippage_pct=1, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 707, 14.14, 3.02)
    check_fill(sell, 8, SELL, 707, 7.92, 5602.46)
    assert r.slippage_pct == 1.0
    assert r.final_cash == A(5602.46) and r.final_position == 0
    assert r.total_costs == 0.0  # slippage is a worse price, not a fee
    (rt,) = r.round_trips
    assert rt.outlay == A(9996.98) and rt.proceeds == A(5599.44)


def test_close_fills_with_slippage_and_fees():
    r = run_backtest(CLOSES, slippage_pct=1, **FEES, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 699, 14.14, 12.3014, cost=103.8386)
    check_fill(sell, 8, SELL, 699, 7.92, 5488.0206, cost=60.3608)
    assert r.total_costs == A(103.8386 + 60.3608)
    assert r.final_equity == A(5488.0206)


def test_open_fills_with_slippage_no_fees():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, slippage_pct=1, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 761, 13.13, 8.07)
    check_fill(sell, 8, SELL, 761, 6.93, 5281.80)
    assert r.daily[5].equity == A(8.07 + 761 * 14.0)  # still marked at the close


def test_open_fills_with_slippage_and_fees():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, slippage_pct=1, **FEES, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 753, 13.13, 9.2411, cost=103.8689)
    check_fill(sell, 8, SELL, 753, 6.93, 5170.3482, cost=57.1829)


def test_percentage_fee_is_charged_on_the_slipped_price():
    r = run_backtest(CLOSES, slippage_pct=1, fee=0, fee_pct=1, **SMA)
    buy = r.trades[0]
    assert buy.cost == A(buy.shares * 14.14 * 0.01)  # 1 % of 14.14, not of 14


def test_slippage_makes_the_result_worse_than_without():
    plain = run_backtest(CLOSES, **SMA)
    slipped = run_backtest(CLOSES, slippage_pct=1, **SMA)
    assert slipped.trades[0].shares < plain.trades[0].shares
    assert slipped.final_equity < plain.final_equity


# --------------------------------------------------------------------------- zero / default unchanged


def test_no_slippage_and_zero_slippage_are_identical_to_before():
    for kw in ({}, FEES, dict(fill="open", opens=OPENS), dict(fill="open", opens=OPENS, **FEES)):
        base = run_backtest(CLOSES, **SMA, **kw)
        assert run_backtest(CLOSES, slippage_pct=0, **SMA, **kw) == base
        assert run_backtest(CLOSES, slippage_pct=0.0, **SMA, **kw) == base
        assert base.slippage_pct == 0.0
    plain = run_backtest(CLOSES, **SMA)
    assert [(t.bar, t.shares, t.price, t.cash_after) for t in plain.trades] == [(5, 714, 14.0, 4.0), (8, 714, 8.0, 5716.0)]


def test_report_lines_unchanged_without_slippage_and_name_slippage_with_it():
    plain = format_result(run_backtest(CLOSES, **SMA), 2, 3)
    assert not any("Slippage" in line for line in plain)
    assert "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)" in plain
    slipped = format_result(run_backtest(CLOSES, slippage_pct=1, **SMA), 2, 3)
    i = slipped.index("  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)")
    assert slipped[i + 1] == "  Slippage:    1.00% (buys fill higher, sells lower, before fees)"
    assert [line for line in slipped if line.startswith("    #")] == [
        "    #1   bar 5     BUY       707 @      14.14  value     9,996.98  cost     0.00  cash         3.02",
        "    #2   bar 8     SELL      707 @       7.92  value     5,599.44  cost     0.00  cash     5,602.46",
    ]
    # every other line is the same as without slippage, apart from the numbers that legitimately move
    assert len(slipped) == len(plain) + 1


def test_benchmark_pays_the_same_slippage():
    bench = run_backtest(CLOSES, slippage_pct=1, **SMA).benchmark
    assert bench.shares == 990 and bench.final_equity == A(7921.0)  # bought @ 10 * 1.01 = 10.10


@pytest.mark.parametrize("bad", [-0.01, -1, 100, 150])
def test_run_backtest_rejects_slippage_out_of_range(bad):
    with pytest.raises(ValueError) as excinfo:
        run_backtest(CLOSES, slippage_pct=bad, **SMA)
    assert str(excinfo.value) == f"slippage_pct must be between 0 and 100 (exclusive), got {bad}"


def test_run_backtest_accepts_large_but_valid_slippage():
    r = run_backtest(CLOSES, slippage_pct=99.99, **SMA)
    assert r.trades[0].price == A(14 * 1.9999)


# --------------------------------------------------------------------------- CLI


def test_cli_slippage_shows_paid_prices_and_slippage_line(tmp_path, capsys):
    code, out, err = run([write_closes(tmp_path), "--backtest", "--short", "2", "--long", "3", "--slippage", "1"], capsys)
    assert code == 0 and err == ""
    lines = out.splitlines()
    fills = [line.split() for line in lines if line.startswith("    #")]
    assert fills[0] == ["#1", "bar", "5", "BUY", "707", "@", "14.14", "value", "9,996.98", "cost", "0.00", "cash", "3.02"]
    assert fills[1] == ["#2", "bar", "8", "SELL", "707", "@", "7.92", "value", "5,599.44", "cost", "0.00", "cash", "5,602.46"]
    assert "  Slippage:    1.00% (buys fill higher, sells lower, before fees)" in lines
    assert "  End cash:    5,602.46" in lines


def test_cli_slippage_with_fees_and_open_fill(tmp_path, capsys):
    argv = [write_candles(tmp_path), "--backtest", "--short", "2", "--long", "3", "--fill", "open", "--slippage", "1", "--fee", "5", "--fee-pct", "1"]
    code, out, err = run(argv, capsys)
    assert code == 0 and err == ""
    fills = [line.split() for line in out.splitlines() if line.startswith("    #")]
    assert fills[0] == ["#1", "bar", "5", "BUY", "753", "@", "13.13", "value", "9,886.89", "cost", "103.87", "cash", "9.24"]
    assert fills[1] == ["#2", "bar", "8", "SELL", "753", "@", "6.93", "value", "5,218.29", "cost", "57.18", "cash", "5,170.35"]
    assert "  Slippage:    1.00% (buys fill higher, sells lower, before fees)" in out
    assert "  Costs:       161.05 paid (fee 5.00 per trade + 1.00% of value)" in out


def test_cli_zero_slippage_gives_identical_output_to_no_slippage(tmp_path, capsys):
    path = write_closes(tmp_path)
    argv = [path, "--backtest", "--short", "2", "--long", "3", "--stats", "--chart"]
    assert run(argv, capsys) == run(argv + ["--slippage", "0"], capsys)
    code, out, _ = run(argv, capsys)
    assert code == 0 and "Slippage" not in out


def test_cli_slippage_export_records_the_paid_price(tmp_path, capsys):
    export = tmp_path / "out.csv"
    code, _, err = run([write_closes(tmp_path), "--backtest", "--short", "2", "--long", "3", "--slippage", "1", "--export", str(export)], capsys)
    assert code == 0 and err == ""
    rows = [line.split(",") for line in export.read_text().splitlines()]
    header, bar5 = rows[0], rows[1 + 5]
    assert bar5[header.index("price")] == "14.14" and bar5[header.index("close")] == "14.00"
    assert bar5[header.index("shares")] == "707" and bar5[header.index("cash")] == "3.02"


@pytest.mark.parametrize("bad, shown", [("-1", "-1"), ("-0.5", "-0.5"), ("100", "100"), ("250", "250")])
def test_cli_slippage_out_of_range_is_a_usage_error(tmp_path, capsys, bad, shown):
    with pytest.raises(SystemExit) as excinfo:
        main([write_closes(tmp_path), "--backtest", "--slippage", bad])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == f"trading_assistant.cli: error: --slippage must be between 0 and 100 (exclusive), got {shown}"


@pytest.mark.parametrize("value", ["1", "0"])
def test_cli_slippage_without_backtest_is_a_usage_error(tmp_path, capsys, value):
    with pytest.raises(SystemExit) as excinfo:
        main([write_closes(tmp_path), "--slippage", value])
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == "trading_assistant.cli: error: --slippage only makes sense together with --backtest"


def test_cli_non_numeric_slippage_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([write_closes(tmp_path), "--backtest", "--slippage", "lots"])
    assert excinfo.value.code == 2
    assert "invalid float value: 'lots'" in capsys.readouterr().err


def test_check_costs_and_validate_args_handle_slippage():
    check_costs(slippage=0)
    check_costs(slippage=99.9)
    check_costs(10_000, 0, 0)  # the three-argument form used elsewhere still works
    with pytest.raises(ValueError, match="--slippage must be between 0 and 100"):
        check_costs(slippage=100)
    parser = build_parser()
    args = validate_args(parser, parser.parse_args(["p.csv", "--backtest"]))
    assert args.slippage == 0.0
    args = validate_args(parser, parser.parse_args(["p.csv", "--backtest", "--slippage", "0.25"]))
    assert args.slippage == 0.25


def test_help_mentions_slippage(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "--slippage" in capsys.readouterr().out
