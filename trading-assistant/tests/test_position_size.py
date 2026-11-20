"""Tests for position sizing (``position_size`` / ``--position-size``).

A buy spends at most ``position_size`` of the account value (cash plus shares
held, marked at the bar's fill price) on shares, costs and slippage included,
and never more than the cash. Hand-worked on the LOSS sample of
test_backtest.py with short=2, long=3 (BUY fills bar 5, SELL fills bar 8);
opens as in test_fill_open.py.

    closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]
    opens  = [ 9,  9,  9,  9, 12, 13, 15, 9, 7, 8]

Size 0.5, no fees:  budget 0.5 * 10000 = 5000.
    BUY  bar 5 @ 14: floor(5000 / 14) = 357 shares, 4,998, cash 5,002.
    SELL bar 8 @ 8:  357 * 8 = 2,856, cash 7,858.  (Without sizing: 714 / cash 4 / 5,716.)
Size 0.5, fee 5 + 1 %:  budget 5000.
    BUY  bar 5 @ 14: (5000 - 5) / (14 * 1.01) = 353.3 -> 353 shares, value 4,942,
         fee 5 + 49.42 = 54.42, spend 4,996.42 <= 5000, cash 5,003.58.
    SELL bar 8 @ 8:  value 2,824, fee 5 + 28.24 = 33.24, cash 5003.58 + 2824 - 33.24 = 7,794.34.
Size 0.5, slippage 1 %, no fees:  budget 5000, fill 14 * 1.01 = 14.14.
    BUY  bar 5: floor(5000 / 14.14) = 353 shares, 353 * 14.14 = 4,991.42, cash 5,008.58.
    SELL bar 8 @ 8 * 0.99 = 7.92: 353 * 7.92 = 2,795.76, cash 7,804.34.
Size 0.25, open fills, no fees:  budget 2500, fill at open 13.
    BUY  bar 5 @ 13: floor(2500 / 13) = 192 shares, 2,496, cash 7,504.
    SELL bar 8 @ 7:  192 * 7 = 1,344, cash 8,848.

Buying while already holding (breakout, window=2, closes 10..16 rising, so
every bar from t=2 is a BUY signal), size 0.5, no fees:
    bar 3 @ 13: account value 10,000, budget 5,000 -> 384 shares (4,992), cash 5,008.
    bar 4 @ 14: account value 5008 + 384 * 14 = 10,384, budget 5,192, but only
                5,008 cash -> floor(5008 / 14) = 357 shares (4,998), cash 10.
    bar 5, 6:   budget > cash = 10 < one share -> no fill.
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


def write_closes(tmp_path):
    path = tmp_path / "closes.csv"
    path.write_text("date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate(CLOSES)))
    return str(path)


def write_candles(tmp_path):
    rows = ["date,open,high,low,close,volume"]
    for t, (o, c) in enumerate(zip(OPENS, CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{o},{max(o, c) + 1},{min(o, c) - 1},{c},{(t + 1) * 1000}")
    path = tmp_path / "hand.csv"
    path.write_text("\n".join(rows) + "\n")
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


def test_half_size_no_fees():
    r = run_backtest(CLOSES, position_size=0.5, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 357, 14.0, 5002.0)
    check_fill(sell, 8, SELL, 357, 8.0, 7858.0)
    assert r.position_size == 0.5
    assert r.daily[5].equity == 5002.0 + 357 * 14.0  # == 10,000: sizing does not change the value
    assert r.final_equity == 7858.0


def test_half_size_with_fees_counts_costs_towards_the_limit():
    r = run_backtest(CLOSES, position_size=0.5, **FEES, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 353, 14.0, 5003.58, cost=54.42)
    assert buy.value + buy.cost == A(4996.42) and buy.value + buy.cost <= 5000.0
    # one more share would have cost 354 * 14 * 1.01 + 5 = 5,010.56 > 5,000
    check_fill(sell, 8, SELL, 353, 8.0, 7794.34, cost=33.24)


def test_half_size_with_slippage_counts_slippage_towards_the_limit():
    r = run_backtest(CLOSES, position_size=0.5, slippage_pct=1, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 353, 14.14, 5008.58)
    assert buy.value == A(4991.42) and buy.value <= 5000.0  # 354 * 14.14 = 5,005.56 would exceed the budget
    check_fill(sell, 8, SELL, 353, 7.92, 7804.34)


def test_quarter_size_with_open_fills():
    r = run_backtest(CLOSES, fill="open", opens=OPENS, position_size=0.25, **SMA)
    buy, sell = r.trades
    check_fill(buy, 5, BUY, 192, 13.0, 7504.0)
    check_fill(sell, 8, SELL, 192, 7.0, 8848.0)


def test_buying_while_holding_uses_cash_plus_position_as_account_value_capped_by_cash():
    r = run_backtest([10, 11, 12, 13, 14, 15, 16], strategy="breakout", strategy_params={"window": 2}, position_size=0.5)
    assert [(t.bar, t.side, t.shares, t.price, t.cash_after) for t in r.trades] == [
        (3, BUY, 384, 13, 5008.0),
        (4, BUY, 357, 14, 10.0),
    ]
    assert r.final_position == 741 and r.final_cash == 10.0


def test_sell_is_not_sized_the_whole_position_is_sold():
    r = run_backtest(CLOSES, position_size=0.5, **SMA)
    assert r.trades[1].shares == r.trades[0].shares == 357
    assert r.final_position == 0


def test_size_too_small_for_one_share_skips_the_buy():
    r = run_backtest(CLOSES, position_size=0.001, **SMA)  # budget 10 < one share at 14
    assert r.trades == []
    assert r.final_cash == 10000.0


def test_size_one_is_identical_to_no_sizing():
    for kw in ({}, FEES, dict(slippage_pct=1), dict(fill="open", opens=OPENS, **FEES)):
        base = run_backtest(CLOSES, **SMA, **kw)
        sized = run_backtest(CLOSES, position_size=1, **SMA, **kw)
        assert sized.trades == base.trades and sized.daily == base.daily
        assert sized.position_size == 1.0 and base.position_size is None


def test_no_sizing_is_unchanged():
    base = run_backtest(CLOSES, **SMA)
    assert [(t.bar, t.shares, t.price, t.cash_after) for t in base.trades] == [(5, 714, 14.0, 4.0), (8, 714, 8.0, 5716.0)]
    assert run_backtest(CLOSES, position_size=None, **SMA) == base


def test_benchmark_is_not_affected_by_sizing():
    assert run_backtest(CLOSES, position_size=0.5, **SMA).benchmark == run_buy_and_hold(CLOSES)


def test_report_names_the_sizing_only_when_given():
    plain = format_result(run_backtest(CLOSES, **SMA), 2, 3)
    assert not any("Sizing" in line for line in plain)
    sized = format_result(run_backtest(CLOSES, position_size=0.5, **SMA), 2, 3)
    i = sized.index("  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)")
    assert sized[i + 1] == "  Sizing:      each buy at most 50% of account value (costs and slippage included)"
    assert len(sized) == len(plain) + 1
    both = format_result(run_backtest(CLOSES, position_size=0.25, slippage_pct=1, **SMA), 2, 3)
    j = both.index("  Slippage:    1.00% (buys fill higher, sells lower, before fees)")
    assert both[j + 1] == "  Sizing:      each buy at most 25% of account value (costs and slippage included)"


@pytest.mark.parametrize("bad", [0, -0.5, 1.01, 2])
def test_run_backtest_rejects_size_out_of_range(bad):
    with pytest.raises(ValueError) as excinfo:
        run_backtest(CLOSES, position_size=bad, **SMA)
    assert str(excinfo.value) == f"position_size must be above 0 and at most 1, got {bad}"


# --------------------------------------------------------------------------- CLI


def test_cli_position_size_hand_worked_fills(tmp_path, capsys):
    code, out, err = run([write_closes(tmp_path), "--backtest", "--short", "2", "--long", "3", "--position-size", "0.5"], capsys)
    assert code == 0 and err == ""
    lines = out.splitlines()
    fills = [line.split() for line in lines if line.startswith("    #")]
    assert fills[0] == ["#1", "bar", "5", "BUY", "357", "@", "14.00", "value", "4,998.00", "cost", "0.00", "cash", "5,002.00"]
    assert fills[1] == ["#2", "bar", "8", "SELL", "357", "@", "8.00", "value", "2,856.00", "cost", "0.00", "cash", "7,858.00"]
    assert "  Sizing:      each buy at most 50% of account value (costs and slippage included)" in lines
    assert "  End cash:    7,858.00" in lines


def test_cli_position_size_with_fees(tmp_path, capsys):
    argv = [write_closes(tmp_path), "--backtest", "--short", "2", "--long", "3", "--position-size", "0.5", "--fee", "5", "--fee-pct", "1"]
    code, out, err = run(argv, capsys)
    assert code == 0 and err == ""
    fills = [line.split() for line in out.splitlines() if line.startswith("    #")]
    assert fills[0] == ["#1", "bar", "5", "BUY", "353", "@", "14.00", "value", "4,942.00", "cost", "54.42", "cash", "5,003.58"]
    assert fills[1] == ["#2", "bar", "8", "SELL", "353", "@", "8.00", "value", "2,824.00", "cost", "33.24", "cash", "7,794.34"]


def test_cli_position_size_with_open_fill_and_slippage(tmp_path, capsys):
    argv = [write_candles(tmp_path), "--backtest", "--short", "2", "--long", "3", "--fill", "open", "--position-size", "0.25"]
    code, out, err = run(argv, capsys)
    assert code == 0 and err == ""
    fills = [line.split() for line in out.splitlines() if line.startswith("    #")]
    assert fills[0][:7] == ["#1", "bar", "5", "BUY", "192", "@", "13.00"] and fills[0][-1] == "7,504.00"
    assert fills[1][:7] == ["#2", "bar", "8", "SELL", "192", "@", "7.00"] and fills[1][-1] == "8,848.00"


def test_cli_without_position_size_is_unchanged(tmp_path, capsys):
    path = write_closes(tmp_path)
    argv = [path, "--backtest", "--short", "2", "--long", "3", "--stats", "--chart"]
    code, out, err = run(argv, capsys)
    assert code == 0 and err == "" and "Sizing" not in out and "714 @" in out
    # --position-size 1 trades identically; it only adds the Sizing line to the report.
    code1, out1, err1 = run(argv + ["--position-size", "1"], capsys)
    assert code1 == 0 and err1 == ""
    assert out1.replace("  Sizing:      each buy at most 100% of account value (costs and slippage included)\n", "") == out


@pytest.mark.parametrize("bad, shown", [("0", "0"), ("-0.5", "-0.5"), ("1.5", "1.5"), ("100", "100")])
def test_cli_position_size_out_of_range_is_a_usage_error(tmp_path, capsys, bad, shown):
    with pytest.raises(SystemExit) as excinfo:
        main([write_closes(tmp_path), "--backtest", "--position-size", bad])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == f"trading_assistant.cli: error: --position-size must be above 0 and at most 1, got {shown}"


def test_cli_position_size_without_backtest_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([write_closes(tmp_path), "--position-size", "0.5"])
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == "trading_assistant.cli: error: --position-size only makes sense together with --backtest"


def test_check_costs_and_validate_args_handle_position_size():
    check_costs(position_size=1)
    check_costs(position_size=0.01)
    check_costs(10_000, 0, 0)  # the older forms still work
    check_costs(10_000, 0, 0, 0)
    with pytest.raises(ValueError, match="--position-size must be above 0 and at most 1"):
        check_costs(position_size=0)
    parser = build_parser()
    assert validate_args(parser, parser.parse_args(["p.csv", "--backtest"])).position_size is None
    assert validate_args(parser, parser.parse_args(["p.csv", "--backtest", "--position-size", "0.3"])).position_size == 0.3


def test_help_mentions_position_size(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "--position-size" in capsys.readouterr().out
