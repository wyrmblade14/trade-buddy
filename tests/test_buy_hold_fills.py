"""Buy-and-hold benchmark follows the strategy's buy rules (fill price, slippage, costs).

The benchmark buys as many whole shares as it can on the first bar and holds
to the end. Its purchase is priced like a strategy buy: the first bar's fill
price (its close, or its open with ``fill="open"``), raised by the slippage,
with fees charged on that slipped price. It is always all-in (no position
sizing) and never exits. The account is marked at the closes.

Series (the LOSS sample used by test_fill_open.py / test_slippage.py), cash 10,000:

    bar     0   1   2   3   4   5   6   7   8   9
    open    9   9   9   9  12  13  15   9   7   8
    close  10  10  10  10  14  14  14   8   8   8

Hand-worked purchases (price paid -> shares -> cash left -> end value at the last close 8):

    A  close, no slippage, no fees (unchanged):
         10 -> floor(10,000 / 10) = 1,000 -> cost 10,000, cash 0 -> 0 + 1,000 * 8 = 8,000.00
    B  open fills:
         9 -> floor(10,000 / 9) = 1,111 -> cost 9,999, cash 1 -> 1 + 8,888 = 8,889.00
         bar 0 equity 1 + 1,111 * 10 = 11,111; peak bar 4: 1 + 1,111 * 14 = 15,555
    C  close fills, 1 % slippage:
         10 * 1.01 = 10.10 -> floor(10,000 / 10.10) = 990 (991 would cost 10,009.10)
         -> cost 9,999.00, cash 1 -> 1 + 990 * 8 = 7,921.00
    D  open fills + 1 % slippage:
         9 * 1.01 = 9.09 -> floor(10,000 / 9.09) = 1,100 (1,101 would cost 10,008.09)
         -> cost 9,999.00, cash 1 -> 1 + 1,100 * 8 = 8,801.00; bar 0 equity 1 + 11,000 = 11,001

With fees 5 + 1 % (shares = floor((10,000 - 5) / (price * 1.01)), fee = 5 + 1 % of value):

    E  close:  9,995 / 10.10 = 989.6 -> 989; value 9,890.00, fee 103.90, cash 6.10
               -> end 6.10 + 7,912 = 7,918.10          (unchanged; 990 would need 10,004.90)
    F  open:   9,995 / 9.09 = 1,099.6 -> 1,099; value 9,891.00, fee 103.91, cash 5.09
               -> end 5.09 + 8,792 = 8,797.09          (1,100 would need 10,004.00)
    G  close + 1 % slippage @ 10.10: 9,995 / 10.201 = 979.8 -> 979; value 9,887.90,
               fee 103.879, cash 8.221 -> end 8.221 + 7,832 = 7,840.221   (980 would need 10,001.98)
    H  open + 1 % slippage @ 9.09: 9,995 / 9.1809 = 1,088.7 -> 1,088; value 9,889.92,
               fee 103.8992, cash 6.1808 -> end 6.1808 + 8,704 = 8,710.1808   (1,089 would need 10,003.0001)
"""

import pytest

from trading_assistant.backtest import EXPORT_COLUMNS, export_rows, format_result, run_backtest, run_buy_and_hold
from trading_assistant.cli import main

CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 15.0, 9.0, 7.0, 8.0]
HIGHS = [max(o, c) + 1 for o, c in zip(OPENS, CLOSES)]
LOWS = [min(o, c) - 1 for o, c in zip(OPENS, CLOSES)]
SMA = dict(short=2, long=3)
FEES = dict(fee=5, fee_pct=1)
OPEN = dict(fill="open", opens=OPENS)
SLIP = dict(slippage_pct=1)
A = pytest.approx


def summary(bench):
    return (bench.shares, bench.final_cash, bench.total_costs, bench.final_equity)


# --------------------------------------------------------------------------- hand-worked purchases


@pytest.mark.parametrize(
    "kwargs, shares, cash, costs, end",
    [
        (dict(), 1000, 0.0, 0.0, 8000.0),  # A
        (OPEN, 1111, 1.0, 0.0, 8889.0),  # B
        (SLIP, 990, 1.0, 0.0, 7921.0),  # C
        ({**OPEN, **SLIP}, 1100, 1.0, 0.0, 8801.0),  # D
        (FEES, 989, 6.10, 103.90, 7918.10),  # E
        ({**OPEN, **FEES}, 1099, 5.09, 103.91, 8797.09),  # F
        ({**SLIP, **FEES}, 979, 8.221, 103.879, 7840.221),  # G
        ({**OPEN, **SLIP, **FEES}, 1088, 6.1808, 103.8992, 8710.1808),  # H
    ],
    ids=["A close", "B open", "C slippage", "D open+slippage", "E fees", "F open+fees", "G slippage+fees", "H open+slippage+fees"],
)
def test_buy_and_hold_purchase_hand_worked(kwargs, shares, cash, costs, end):
    bench = run_buy_and_hold(CLOSES, 10_000, **kwargs)
    assert summary(bench) == (shares, A(cash), A(costs), A(end))
    assert bench.n_trades == 1
    # the backtest's own benchmark is exactly this purchase
    assert run_backtest(CLOSES, **kwargs, **SMA).benchmark == bench


def test_open_fill_benchmark_curve_return_and_drawdown():
    bench = run_buy_and_hold(CLOSES, 10_000, **OPEN)
    assert bench.equity_curve == A([11111.0] * 4 + [15555.0] * 3 + [8889.0] * 3)  # marked at the closes
    assert bench.return_pct == A(-11.11)
    assert bench.max_drawdown_pct == A((8889 - 15555) / 15555 * 100)  # -42.854...


def test_open_fill_with_slippage_curve():
    bench = run_buy_and_hold(CLOSES, 10_000, **OPEN, **SLIP)
    assert bench.equity_curve == A([11001.0] * 4 + [15401.0] * 3 + [8801.0] * 3)
    assert bench.return_pct == A(-11.99)


def test_slippage_can_make_the_first_share_unaffordable():
    # 9 cash buys 1 share at the open 9, but not at the slipped 9.09: the cash is held
    assert summary(run_buy_and_hold(CLOSES, 9, **OPEN)) == (1, A(0.0), 0.0, A(8.0))
    bench = run_buy_and_hold(CLOSES, 9, **OPEN, **SLIP)
    assert summary(bench) == (0, 9.0, 0.0, 9.0) and bench.n_trades == 0


# --------------------------------------------------------------------------- unchanged with close fills and no slippage


def test_close_fill_without_slippage_is_unchanged():
    assert summary(run_buy_and_hold(CLOSES, 10_000)) == (1000, 0.0, 0.0, 8000.0)
    explicit = run_buy_and_hold(CLOSES, 10_000, fill="close", opens=OPENS, slippage_pct=0.0)
    assert explicit == run_buy_and_hold(CLOSES, 10_000)  # opens are not used with close fills
    assert run_backtest(CLOSES, **SMA).benchmark == run_buy_and_hold(CLOSES)
    assert run_backtest(CLOSES, **FEES, **SMA).benchmark == run_buy_and_hold(CLOSES, **FEES)


# --------------------------------------------------------------------------- all-in: no position size, no exits


def test_benchmark_ignores_position_size_and_exits():
    expected = run_buy_and_hold(CLOSES, 10_000, **OPEN, **SLIP)
    sized = run_backtest(CLOSES, position_size=0.5, **OPEN, **SLIP, **SMA)
    assert sized.benchmark == expected and sized.benchmark.shares == 1100  # all-in, not half
    exits = run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, highs=HIGHS, lows=LOWS, **OPEN, **SLIP, **SMA)
    assert exits.benchmark == expected  # held to the end, never stopped out


# --------------------------------------------------------------------------- report and export


def test_report_comparison_uses_the_same_fill_and_slippage():
    r = run_backtest(CLOSES, **OPEN, **SLIP, **SMA)
    lines = format_result(r, 2, 3)
    # strategy: open fills + 1 % slippage end at 5,281.80 (hand-worked in test_slippage.py)
    assert f"    {'End equity':<16s}{'5,281.80':>14s}{'8,801.00':>14s}" in lines
    assert f"    {'Return':<16s}{'-47.18%':>14s}{'-11.99%':>14s}" in lines


def test_export_buy_hold_column_uses_the_same_fill_and_slippage():
    rows = export_rows(run_backtest(CLOSES, **OPEN, **SLIP, **SMA))
    col = EXPORT_COLUMNS.index("buy_hold_equity")
    assert [row[col] for row in rows] == ["11001.00"] * 4 + ["15401.00"] * 3 + ["8801.00"] * 3


def test_cli_report_comparison_with_open_fills_and_slippage(tmp_path, capsys):
    rows = ["date,open,high,low,close,volume"]
    for t in range(len(CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{OPENS[t]},{HIGHS[t]},{LOWS[t]},{CLOSES[t]},{(t + 1) * 1000}")
    path = tmp_path / "candles.csv"
    path.write_text("\n".join(rows) + "\n")
    code = main([str(path), "--backtest", "--short", "2", "--long", "3", "--fill", "open", "--slippage", "1"])
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    assert f"    {'End equity':<16s}{'5,281.80':>14s}{'8,801.00':>14s}" in captured.out.splitlines()


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(fill="open"), "fill on open needs the open price of every bar"),
        (dict(fill="open", opens=OPENS[:-1]), "9 opens but 10 closes"),
        (dict(fill="open", opens=[0.0] + OPENS[1:]), "bar 0: open must be positive, got 0.0"),
        (dict(fill="midday"), "unknown fill 'midday'; choose one of: close, open"),
        (dict(slippage_pct=100), "slippage_pct must be between 0 and 100 (exclusive), got 100"),
        (dict(slippage_pct=-1), "slippage_pct must be between 0 and 100 (exclusive), got -1"),
    ],
    ids=["open without opens", "wrong length", "non-positive open", "unknown fill", "slippage 100", "slippage negative"],
)
def test_run_buy_and_hold_rejects_bad_settings(kwargs, message):
    with pytest.raises(ValueError) as excinfo:
        run_buy_and_hold(CLOSES, 10_000, **kwargs)
    assert str(excinfo.value) == message
