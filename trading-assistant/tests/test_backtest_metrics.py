"""Tests for the strategy-judging extensions of trading_assistant.backtest:
buy-and-hold benchmark, max drawdown, round-trip win count, trading costs
and CSV export, plus the matching CLI options.

All expected numbers are worked out by hand with short=2, long=3.

LOSS  closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]      (BUY t=4, SELL t=7)

  No costs, 10,000 cash
    strategy : BUY bar 5 @ 14 -> 714 sh (9,996), cash 4
               SELL bar 8 @ 8 -> 5,712, cash 5,716           -> -42.84 %
    equity   : 10000 x5, 10000 (bar 5: 4 + 714*14), 10000, 5716 (4 + 714*8), 5716, 5716
               peak 10,000 -> trough 5,716                    -> drawdown -42.84 %
    round trip: outlay 9,996, proceeds 5,712, pnl -4,284       -> 0 of 1 made money
    buy&hold : 1,000 sh @ 10 on bar 0, end 1000*8 = 8,000      -> -20.00 %
               equity 10000,10000,10000,10000,14000,14000,14000,8000,8000,8000
               peak 14,000 -> trough 8,000 = -6000/14000       -> drawdown -42.857 %

  Fee 5.00 per trade + 1 % of value, 10,000 cash
    BUY bar 5 @ 14: n*14*1.01 + 5 <= 10000 -> n <= 9995/14.14 = 706.86 -> 706 sh
               value 9,884.00, pct 98.84, fee 5 -> cost 103.84, outlay 9,987.84, cash 12.16
               (707 sh would need 9,898*1.01 + 5 = 10,001.98 > 10,000)
    SELL bar 8 @ 8: value 5,648.00, pct 56.48, fee 5 -> cost 61.48, net 5,586.52
               cash 12.16 + 5,586.52 = 5,598.68                -> -44.0132 %
    total costs 103.84 + 61.48 = 165.32
    round trip pnl 5,586.52 - 9,987.84 = -4,401.32 (loss)
    equity   : 10000 x5, 9896.16 (12.16 + 706*14), 9896.16, 5660.16 (12.16 + 706*8),
               5598.68, 5598.68   -> drawdown (5598.68 - 10000)/10000 = -44.01 %
    buy&hold : n <= 9995/10.1 = 989.6 -> 989 sh, value 9,890, pct 98.90, fee 5
               -> cost 103.90, cash 6.10; end 6.10 + 989*8 = 7,918.10 -> -20.819 %
               peak 6.10 + 989*14 = 13,852.10 -> (7918.10 - 13852.10)/13852.10 = -42.838 %

WIN   closes = [10, 10, 10, 10, 14, 14, 14, 20, 20, 16, 16]
    t=9: sma2 = 18, sma3 = (20+20+16)/3 = 18.67, prev sma2 = 20 >= sma3 = 18 -> SELL
    BUY bar 5 @ 14 -> 714 sh, cash 4; SELL bar 10 @ 16 -> 11,424, cash 11,428 -> +14.28 %
    round trip pnl 11,424 - 9,996 = +1,428 (win)               -> 1 of 1 made money
    equity peak 4 + 714*20 = 14,284 (bars 7, 8), trough 11,428 -> -2856/14284 = -19.994 %
    buy&hold 1,000 sh: end 16,000 (+60 %), peak 20,000 -> 16,000 = -20.00 %

TWO   closes = WIN + [22, 22, 22, 15, 15]
    t=11: sma2 = 19 > sma3 = 18 after sma2 16 <= sma3 17.33     -> BUY, fills bar 12 @ 22
          11,428 / 22 = 519.45 -> 519 sh (11,418), cash 10
    t=14: sma2 = 18.5 < sma3 = 19.67 after 22 >= 22             -> SELL, fills bar 15 @ 15
          519 * 15 = 7,785 -> cash 7,795                        -> -22.05 %
    round trips: +1,428 (win), 7,785 - 11,418 = -3,633 (loss)    -> 1 of 2 made money
    equity peak 14,284 -> trough 7,795 = -6489/14284             -> -45.43 %
    buy&hold: end 15,000 (+50 %), peak 22,000 -> 15,000          -> -31.82 %

EDGE  LOSS with cash 24 and fee 10 (no pct):
    BUY bar 5 @ 14: 14 + 10 = 24 -> 1 share, cash 0
    SELL bar 8 @ 8: 8 - 10 = -2 would make cash negative -> rejected, position kept
    -> 1 trade, 1 share held, equity 8, no completed round trip
"""

import csv
import os

import pytest

from trading_assistant.backtest import (
    EXPORT_COLUMNS,
    BacktestResult,
    BenchmarkResult,
    Portfolio,
    RoundTrip,
    Trade,
    drawdown_curve_pct,
    export_csv,
    format_result,
    max_drawdown_pct,
    run_backtest,
    run_buy_and_hold,
)
from trading_assistant.cli import load_closes, load_price_table, main
from trading_assistant.signals import BUY, SELL

LOSS = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
WIN = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 20.0, 20.0, 16.0, 16.0]
TWO = WIN + [22.0, 22.0, 22.0, 15.0, 15.0]
GAIN = [10.0, 10.0, 10.0, 10.0, 14.0, 16.0, 18.0, 20.0]


def write_csv(path, closes, with_dates=True):
    if with_dates:
        rows = [f"2026-01-{i + 1:02d},{c}" for i, c in enumerate(closes)]
        path.write_text("date,close\n" + "\n".join(rows) + "\n")
    else:
        path.write_text("close\n" + "\n".join(str(c) for c in closes) + "\n")
    return str(path)


def run(closes, **kwargs):
    kwargs.setdefault("initial_cash", 10_000)
    kwargs.setdefault("short", 2)
    kwargs.setdefault("long", 3)
    return run_backtest(closes, **kwargs)


# --------------------------------------------------------------------------- drawdown


def test_max_drawdown_hand_worked():
    # peaks 100 -> 120 -> 130; falls 120 -> 90 (-25 %) and 130 -> 65 (-50 %)
    assert max_drawdown_pct([100, 120, 90, 130, 65]) == pytest.approx(-50.0)
    assert max_drawdown_pct([100, 120, 90, 130, 100]) == pytest.approx(-25.0)


def test_max_drawdown_zero_when_never_falling_or_empty():
    assert max_drawdown_pct([]) == 0.0
    assert max_drawdown_pct([100]) == 0.0
    assert max_drawdown_pct([100, 100, 110, 120]) == 0.0


def test_drawdown_curve_hand_worked():
    curve = drawdown_curve_pct([100, 120, 90, 130, 65])
    assert curve == pytest.approx([0.0, 0.0, -25.0, 0.0, -50.0])


# --------------------------------------------------------------------------- Portfolio with costs


def test_trade_cost_fixed_plus_percentage():
    p = Portfolio(10_000, fee=5, fee_pct=1)
    assert p.trade_cost(706, 14.0) == pytest.approx(5 + 9884 * 0.01)  # 103.84
    assert Portfolio(10_000).trade_cost(706, 14.0) == 0.0


def test_buy_pays_fee_and_percentage():
    p = Portfolio(10_000, fee=5, fee_pct=1)
    cost = p.buy(706, 14.0)
    assert cost == pytest.approx(103.84)
    assert p.cash == pytest.approx(12.16)
    assert p.position == 706
    assert p.total_costs == pytest.approx(103.84)


def test_buy_must_afford_shares_plus_fee():
    p = Portfolio(100, fee=5)
    with pytest.raises(ValueError, match="exceeds cash"):
        p.buy(1, 100.0)  # 100 + 5 > 100
    assert p.cash == 100.0 and p.position == 0
    p.buy(1, 95.0)  # 95 + 5 = 100 exactly
    assert p.cash == 0.0 and p.position == 1


def test_sell_deducts_fee_and_percentage():
    p = Portfolio(10_000, fee=5, fee_pct=1)
    p.buy(706, 14.0)  # cash 12.16
    cost = p.sell(706, 8.0)
    assert cost == pytest.approx(61.48)
    assert p.cash == pytest.approx(5598.68)
    assert p.position == 0
    assert p.total_costs == pytest.approx(165.32)


def test_sell_rejected_when_fee_would_make_cash_negative():
    p = Portfolio(24, fee=10)
    p.buy(1, 14.0)  # 14 + 10 = 24 -> cash 0
    assert p.cash == 0.0
    with pytest.raises(ValueError, match="fees .* exceed proceeds"):
        p.sell(1, 8.0)  # 8 - 10 = -2
    assert p.cash == 0.0
    assert p.position == 1
    assert p.total_costs == 10.0  # the rejected sale charged nothing
    p.sell(1, 10.0)  # 10 - 10 = 0 -> allowed, cash stays exactly 0
    assert p.cash == 0.0 and p.position == 0


@pytest.mark.parametrize("fee, fee_pct, match", [(-1, 0, "fee must not be negative"), (0, -0.5, "fee_pct"), (0, 100, "fee_pct")])
def test_portfolio_rejects_bad_costs(fee, fee_pct, match):
    with pytest.raises(ValueError, match=match):
        Portfolio(1000, fee=fee, fee_pct=fee_pct)


@pytest.mark.parametrize(
    "cash, price, fee, fee_pct, expected",
    [
        (10_000, 14.0, 5, 1, 706),  # hand worked above
        (10_000, 10.0, 5, 1, 989),  # buy & hold with costs
        (10_000, 14.0, 0, 0, 714),  # no costs: unchanged
        (24, 14.0, 10, 0, 1),  # exactly shares + fee
        (23.99, 14.0, 10, 0, 0),
        (5, 14.0, 5, 0, 0),  # fee eats all the cash
        (4, 14.0, 5, 0, 0),  # cash below the fee
        (1000, 10.0, 0, 50, 66),  # 66 * 10 * 1.5 = 990 <= 1000 < 67 * 15 = 1005
    ],
)
def test_max_affordable_with_costs(cash, price, fee, fee_pct, expected):
    p = Portfolio(cash, fee=fee, fee_pct=fee_pct)
    shares = p.max_affordable(price)
    assert shares == expected
    if shares:
        p.buy(shares, price)  # must not raise
        assert p.cash >= 0.0
        with pytest.raises(ValueError):
            Portfolio(cash, fee=fee, fee_pct=fee_pct).buy(shares + 1, price)


def test_zero_costs_portfolio_behaves_exactly_as_before():
    a, b = Portfolio(10_000), Portfolio(10_000, fee=0, fee_pct=0)
    for p in (a, b):
        p.buy(714, 14.0)
        p.sell(714, 8.0)
    assert (a.cash, a.position, a.total_costs) == (b.cash, b.position, b.total_costs) == (5716.0, 0, 0.0)


# --------------------------------------------------------------------------- buy & hold benchmark


def test_buy_and_hold_loss_sample():
    b = run_buy_and_hold(LOSS, 10_000)
    assert isinstance(b, BenchmarkResult)
    assert b.shares == 1000
    assert b.final_cash == 0.0
    assert b.final_equity == 8000.0
    assert b.return_pct == pytest.approx(-20.0)
    assert b.equity_curve == [10000.0] * 4 + [14000.0] * 3 + [8000.0] * 3
    assert b.max_drawdown_pct == pytest.approx(-42.857, abs=0.001)
    assert b.n_trades == 1
    assert b.total_costs == 0.0


def test_buy_and_hold_with_costs():
    b = run_buy_and_hold(LOSS, 10_000, fee=5, fee_pct=1)
    assert b.shares == 989
    assert b.final_cash == pytest.approx(6.10)
    assert b.total_costs == pytest.approx(103.90)
    assert b.final_equity == pytest.approx(7918.10)
    assert b.return_pct == pytest.approx(-20.819, abs=0.001)
    assert b.max_drawdown_pct == pytest.approx(-42.838, abs=0.001)


def test_buy_and_hold_holds_cash_when_one_share_is_unaffordable():
    b = run_buy_and_hold([50.0, 60.0, 70.0], 40)
    assert b.shares == 0
    assert b.n_trades == 0
    assert b.equity_curve == [40.0, 40.0, 40.0]
    assert b.return_pct == 0.0


def test_buy_and_hold_uses_first_bar_price():
    b = run_buy_and_hold(GAIN, 10_000)  # 1,000 sh @ 10, end @ 20
    assert b.shares == 1000
    assert b.final_equity == 20_000.0
    assert b.return_pct == pytest.approx(100.0)
    assert b.max_drawdown_pct == 0.0


# --------------------------------------------------------------------------- strategy metrics, no costs


def test_loss_sample_metrics():
    r = run(LOSS)
    assert r.equity_curve == [10000.0] * 5 + [10000.0, 10000.0, 5716.0, 5716.0, 5716.0]
    assert r.max_drawdown_pct == pytest.approx(-42.84)
    assert r.round_trips == [RoundTrip(entry_bar=5, exit_bar=8, shares=714, outlay=9996.0, proceeds=5712.0)]
    assert r.round_trips[0].pnl == -4284.0
    assert not r.round_trips[0].is_win
    assert (r.n_round_trips, r.n_winning_round_trips) == (1, 0)
    assert r.total_costs == 0.0
    assert r.benchmark.final_equity == 8000.0


def test_win_sample_metrics():
    r = run(WIN)
    assert [(t.bar, t.side, t.shares, t.price) for t in r.trades] == [(5, BUY, 714, 14.0), (10, SELL, 714, 16.0)]
    assert r.final_cash == 11428.0
    assert r.return_pct == pytest.approx(14.28)
    assert r.round_trips[0].pnl == 1428.0
    assert (r.n_round_trips, r.n_winning_round_trips) == (1, 1)
    assert max(r.equity_curve) == 14284.0
    assert r.max_drawdown_pct == pytest.approx(-19.994, abs=0.001)
    assert r.benchmark.return_pct == pytest.approx(60.0)
    assert r.benchmark.max_drawdown_pct == pytest.approx(-20.0)


def test_two_round_trips_one_winner():
    r = run(TWO)
    assert [(t.bar, t.side, t.shares, t.price, t.cash_after) for t in r.trades] == [
        (5, BUY, 714, 14.0, 4.0),
        (10, SELL, 714, 16.0, 11428.0),
        (12, BUY, 519, 22.0, 10.0),
        (15, SELL, 519, 15.0, 7795.0),
    ]
    assert [rt.pnl for rt in r.round_trips] == [1428.0, -3633.0]
    assert [rt.is_win for rt in r.round_trips] == [True, False]
    assert (r.n_round_trips, r.n_winning_round_trips) == (2, 1)
    assert r.final_equity == 7795.0
    assert r.return_pct == pytest.approx(-22.05)
    assert r.max_drawdown_pct == pytest.approx(-45.428, abs=0.001)
    assert r.benchmark.final_equity == 15000.0
    assert r.benchmark.max_drawdown_pct == pytest.approx(-31.818, abs=0.001)


def test_open_position_at_end_is_not_a_round_trip():
    r = run(GAIN)
    assert r.final_position == 625
    assert r.round_trips == []
    assert (r.n_round_trips, r.n_winning_round_trips) == (0, 0)
    assert r.max_drawdown_pct == 0.0  # equity only ever rose


def test_daily_records_align_with_bars_and_fills():
    r = run(LOSS)
    assert [d.bar for d in r.daily] == list(range(10))
    assert [d.close for d in r.daily] == LOSS
    assert r.daily[4].signal == BUY and r.daily[4].trade is None  # signal at bar 4 ...
    assert r.daily[5].trade == r.trades[0]  # ... filled on bar 5
    assert r.daily[7].signal == SELL and r.daily[8].trade == r.trades[1]
    assert [d.position for d in r.daily] == [0] * 5 + [714] * 3 + [0] * 2
    assert r.daily[7].equity == 4 + 714 * 8  # 5716 before the sale fills


def test_explicit_zero_costs_give_identical_results():
    a = run(TWO)
    b = run(TWO, fee=0.0, fee_pct=0.0)
    assert a.trades == b.trades
    assert a.equity_curve == b.equity_curve
    assert a.round_trips == b.round_trips
    assert a.final_equity == b.final_equity == 7795.0


# --------------------------------------------------------------------------- strategy with costs


def test_loss_sample_with_costs_hand_worked():
    r = run(LOSS, fee=5, fee_pct=1)

    assert r.n_trades == 2
    buy, sell = r.trades
    assert (buy.bar, buy.side, buy.shares, buy.price) == (5, BUY, 706, 14.0)
    assert buy.value == 9884.0
    assert buy.cost == pytest.approx(103.84)
    assert buy.cash_after == pytest.approx(12.16)
    assert (sell.bar, sell.side, sell.shares, sell.price) == (8, SELL, 706, 8.0)
    assert sell.value == 5648.0
    assert sell.cost == pytest.approx(61.48)
    assert sell.cash_after == pytest.approx(5598.68)

    assert r.total_costs == pytest.approx(165.32)
    assert r.final_equity == pytest.approx(5598.68)
    assert r.return_pct == pytest.approx(-44.0132, abs=0.0001)
    assert r.equity_curve == pytest.approx([10000.0] * 5 + [9896.16, 9896.16, 5660.16, 5598.68, 5598.68])
    assert r.max_drawdown_pct == pytest.approx(-44.0132, abs=0.0001)

    rt = r.round_trips[0]
    assert rt.outlay == pytest.approx(9987.84)
    assert rt.proceeds == pytest.approx(5586.52)
    assert rt.pnl == pytest.approx(-4401.32)
    assert (r.n_round_trips, r.n_winning_round_trips) == (1, 0)

    assert r.fee == 5.0 and r.fee_pct == 1.0
    assert r.benchmark.shares == 989
    assert r.benchmark.final_equity == pytest.approx(7918.10)
    assert r.benchmark.total_costs == pytest.approx(103.90)


def test_costs_change_the_result_versus_no_costs():
    free, paid = run(LOSS), run(LOSS, fee=5, fee_pct=1)
    assert free.trades[0].shares == 714 and paid.trades[0].shares == 706
    assert free.final_equity == 5716.0
    assert paid.final_equity == pytest.approx(5598.68)
    assert free.final_equity - paid.final_equity == pytest.approx(117.32)  # 165.32 fees - 48 less exposure


def test_costs_can_turn_a_winning_round_trip_into_a_loser():
    # WIN: gross pnl +1,428 on 714 sh. With a 750 fee per trade the round trip costs 1,500.
    r = run(WIN, fee=750)
    # 9,250 / 14 = 660.7 -> 660 sh, outlay 9,240 + 750 = 9,990, cash 10
    # sell 660 * 16 = 10,560 - 750 = 9,810 -> pnl 9,810 - 9,990 = -180
    assert r.trades[0].shares == 660
    assert r.round_trips[0].outlay == 9990.0
    assert r.round_trips[0].proceeds == 9810.0
    assert r.round_trips[0].pnl == -180.0
    assert (r.n_round_trips, r.n_winning_round_trips) == (1, 0)
    assert r.final_equity == 9820.0  # 10 + 9,810


def test_sell_skipped_when_fee_would_make_cash_negative():
    r = run(LOSS, initial_cash=24, fee=10)
    assert [(t.bar, t.side, t.shares, t.cash_after, t.cost) for t in r.trades] == [(5, BUY, 1, 0.0, 10.0)]
    assert r.final_position == 1
    assert r.final_cash == 0.0
    assert r.final_equity == 8.0
    assert r.round_trips == []
    assert all(d.cash >= 0 for d in r.daily)


@pytest.mark.parametrize("kwargs, match", [({"fee": -1}, "fee must not be negative"), ({"fee_pct": -1}, "fee_pct"), ({"fee_pct": 100}, "fee_pct")])
def test_run_backtest_rejects_bad_costs(kwargs, match):
    with pytest.raises(ValueError, match=match):
        run(LOSS, **kwargs)


# --------------------------------------------------------------------------- export


def test_export_csv_rows_hand_checked(tmp_path):
    r = run(LOSS, fee=5, fee_pct=1)
    out = tmp_path / "report.csv"
    dates = [f"d{i}" for i in range(10)]
    assert export_csv(r, str(out), dates=dates) == 10

    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == EXPORT_COLUMNS
    assert len(rows) == 10

    bar4 = rows[4]  # signal generated, nothing filled yet
    assert (bar4["bar"], bar4["date"], bar4["close"], bar4["signal"], bar4["action"]) == ("4", "d4", "14.00", "BUY", "")
    assert (bar4["cash"], bar4["position"], bar4["equity"]) == ("10000.00", "0", "10000.00")
    assert bar4["buy_hold_equity"] == "13852.10"

    bar5 = rows[5]  # the fill
    assert (bar5["action"], bar5["shares"], bar5["price"], bar5["value"], bar5["cost"]) == ("BUY", "706", "14.00", "9884.00", "103.84")
    assert (bar5["cash"], bar5["position"], bar5["equity"], bar5["drawdown_pct"]) == ("12.16", "706", "9896.16", "-1.04")

    bar8 = rows[8]
    assert (bar8["action"], bar8["shares"], bar8["value"], bar8["cost"], bar8["cash"]) == ("SELL", "706", "5648.00", "61.48", "5598.68")
    assert (bar8["position"], bar8["equity"], bar8["drawdown_pct"], bar8["buy_hold_equity"]) == ("0", "5598.68", "-44.01", "7918.10")

    assert [row["action"] for row in rows] == ["", "", "", "", "", "BUY", "", "", "SELL", ""]


def test_export_csv_without_dates_leaves_column_blank(tmp_path):
    out = tmp_path / "report.csv"
    export_csv(run(GAIN), str(out))
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    assert all(row["date"] == "" for row in rows)
    assert rows[-1]["equity"] == "12500.00"
    assert rows[-1]["buy_hold_equity"] == "20000.00"


def test_export_csv_unwritable_path_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        export_csv(run(GAIN), str(tmp_path / "no-such-dir" / "report.csv"))


# --------------------------------------------------------------------------- format_result


def test_format_result_has_costs_round_trips_and_comparison():
    lines = format_result(run(LOSS), 2, 3)
    assert "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)" in lines
    assert "  Round trips: 1 completed, 0 made money (0%)" in lines
    i = lines.index("  Comparison              Strategy    Buy & hold")
    assert lines[i + 1] == "    End equity            5,716.00      8,000.00"
    assert lines[i + 2] == "    Return                 -42.84%       -20.00%"
    assert lines[i + 3] == "    Max drawdown           -42.84%       -42.86%"
    assert lines[i + 4] == "    Trades                       2             1"
    assert lines[i + 5] == "    Costs paid                0.00          0.00"
    # the closing block is still the last four lines
    assert lines[-4:] == ["  End cash:    5,716.00", "  End shares:  0 @ 8.00", "  End equity:  5,716.00", "  Return:      -42.84%"]


def test_format_result_with_costs():
    lines = format_result(run(LOSS, fee=5, fee_pct=1), 2, 3)
    assert "  Costs:       165.32 paid (fee 5.00 per trade + 1.00% of value)" in lines
    assert "    End equity            5,598.68      7,918.10" in lines
    assert "    Return                 -44.01%       -20.82%" in lines
    assert "    Max drawdown           -44.01%       -42.84%" in lines
    assert "    Costs paid              165.32        103.90" in lines
    assert any("cost   103.84" in line for line in lines)


def test_format_result_two_round_trips():
    lines = format_result(run(TWO), 2, 3)
    assert "  Round trips: 2 completed, 1 made money (50%)" in lines
    assert "    Max drawdown           -45.43%       -31.82%" in lines


def test_format_result_without_benchmark_or_round_trips():
    r = BacktestResult(initial_cash=100.0, final_cash=40.0, final_position=3, final_price=30.0)
    lines = format_result(r, 2, 3)
    assert "  Round trips: 0 completed" in lines
    assert not any("Comparison" in line for line in lines)
    assert r.max_drawdown_pct == 0.0


def test_trade_default_cost_keeps_old_constructor_working():
    assert Trade(5, BUY, 625, 16.0, 0.0) == Trade(bar=5, side=BUY, shares=625, price=16.0, cash_after=0.0, cost=0.0)


# --------------------------------------------------------------------------- load_price_table


def test_load_price_table_returns_dates_and_closes(tmp_path):
    path = write_csv(tmp_path / "p.csv", [1.5, 2.5])
    dates, closes = load_price_table(path)
    assert dates == ["2026-01-01", "2026-01-02"]
    assert closes == [1.5, 2.5]
    assert load_closes(path) == [1.5, 2.5]


def test_load_price_table_without_date_column(tmp_path):
    path = write_csv(tmp_path / "p.csv", [1.5, 2.5], with_dates=False)
    dates, closes = load_price_table(path)
    assert dates is None
    assert closes == [1.5, 2.5]


# --------------------------------------------------------------------------- CLI


def test_cli_backtest_shows_comparison_and_round_trips(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    assert main([path, "--short", "2", "--long", "3", "--backtest"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "  Round trips: 1 completed, 0 made money (0%)" in lines
    assert "    End equity            5,716.00      8,000.00" in lines
    assert "    Max drawdown           -42.84%       -42.86%" in lines
    assert lines[-1] == "Research aid only. Not financial advice."


def test_cli_backtest_with_costs(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    assert main([path, "--short", "2", "--long", "3", "--backtest", "--fee", "5", "--fee-pct", "1"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "  Costs:       165.32 paid (fee 5.00 per trade + 1.00% of value)" in lines
    assert "  End equity:  5,598.68" in lines
    assert "  Return:      -44.01%" in lines
    assert "    Return                 -44.01%       -20.82%" in lines


def test_cli_backtest_default_has_no_costs_and_matches_explicit_zero(tmp_path, capsys):
    path = write_csv(tmp_path / "two.csv", TWO)
    assert main([path, "--short", "2", "--long", "3", "--backtest"]) == 0
    plain = capsys.readouterr().out
    assert main([path, "--short", "2", "--long", "3", "--backtest", "--fee", "0", "--fee-pct", "0"]) == 0
    explicit = capsys.readouterr().out
    assert plain == explicit
    assert "  End equity:  7,795.00" in plain


def test_cli_without_backtest_is_unchanged(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    assert main([path, "--short", "2", "--long", "3"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Bars:    10",
        "Last:    8.00",
        "Signal:  HOLD",
        "RSI:     n/a",
        "Research aid only. Not financial advice.",
    ]


def test_cli_export_writes_file_with_dates(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    out = tmp_path / "report.csv"
    assert main([path, "--short", "2", "--long", "3", "--backtest", "--export", str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert f"  Exported:    10 rows to {out}" in lines
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    assert rows[5]["date"] == "2026-01-06"
    assert (rows[5]["action"], rows[5]["shares"], rows[5]["price"]) == ("BUY", "714", "14.00")
    assert rows[8]["action"] == "SELL"
    assert rows[9]["equity"] == "5716.00"


@pytest.mark.parametrize("extra", [["--fee", "5"], ["--fee-pct", "1"], ["--export", "x.csv"], ["--cash", "5000"]])
def test_cli_new_options_require_backtest(tmp_path, capsys, extra):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    with pytest.raises(SystemExit) as excinfo:
        main([path, *extra])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert f"{extra[0]} only makes sense together with --backtest" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--fee", "-1"], "--fee must not be negative"),
        (["--fee-pct", "-0.1"], "--fee-pct must be between 0 and 100"),
        (["--fee-pct", "100"], "--fee-pct must be between 0 and 100"),
        (["--fee", "abc"], "invalid float value"),
        (["--export", "  "], "--export needs a file name"),
    ],
)
def test_cli_bad_cost_and_export_values_are_usage_errors(tmp_path, capsys, extra, message):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--backtest", *extra])
    assert excinfo.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_export_to_missing_directory_is_one_line_error(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    target = tmp_path / "no-such-dir" / "report.csv"
    assert main([path, "--backtest", "--export", str(target)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert captured.err.startswith(f"Error: cannot write {target}")
    assert not target.exists()


def test_cli_export_refuses_to_overwrite_input(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    before = open(path).read()
    assert main([path, "--backtest", "--export", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [f"Error: --export refuses to overwrite the input file {path}"]
    assert open(path).read() == before
    # same file through a different spelling of the path is also caught
    assert main([path, "--backtest", "--export", os.path.join(str(tmp_path), ".", "loss.csv")]) == 1
    assert open(path).read() == before


def test_cli_help_mentions_new_options(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--fee", "--fee-pct", "--export"):
        assert flag in out
