"""Tests for ``backtest.trade_list`` and ``backtest.format_trade_list`` (one row per round trip, plus the open one).

Main case: tests/data/c.csv, cash 1000, short=1, long=2, close fills (the default). Signals (SMA 1/2): BUY on
bar 3, SELL on bar 6, BUY on bar 8; each fills on the next bar.

    bar  open  high   low  close
     0   10    10.5   9.5   10
     1    9.2   9.5   8.5    9
     2    8.3   8.5   7.5    8
     3    8.8   9.5   8.5    9     BUY signal
     4   10.8  11.5  10.5   11     BUY fills @ 11
     5   11    12    10.8   12
     6   11.5  12     9.5   10     SELL signal
     7    9.8  10.2   9.6   10     SELL fills @ 10
     8   10    11.5   9.9   11     BUY signal
     9   10.8  12.5  10.5   12     BUY fills @ 12
    10   12    12.4  11.8   12.2   last close 12.2

No other option: BUY int(1000 / 11) = 90 @ 11 (990, cash 10), SELL 90 @ 10 on bar 7 (900, cash 910): one round
    trip 4 -> 7, 3 bars, pnl -90.00, -90 / 990 = -9.09 %, reason signal. BUY int(910 / 12) = 75 @ 12 on bar 9
    (900, cash 10), still held: 75 * 12.2 = 915.00, +15.00, +1.67 %, 1 bar (9 -> 10).
Scale-out 5: level 11.55; bar 5 sells 45 @ 11.55 = 519.75, bar 7 sells 45 @ 10 = 450: proceeds 969.75, pnl
    -20.25, -2.05 %. Bar 9: int(979.75 / 12) = 81 (972.00), open: 81 * 12.2 = 988.20, +16.20, +1.67 %.
Stop loss 10: stop 9.90; bar 6 low 9.5 (open 11.5 above it): 90 @ 9.90 = 891.00 on bar 6, 2 bars, -99.00,
    -10.00 %, reason stop. Bar 9: int(901 / 12) = 75, open as without the stop.
Add-on buy (position size 0.5, min hold 5): bar 4 buys int(500 / 11) = 45 (495, cash 505); the bar 7 SELL is
    inside the minimum holding time and dropped; bar 9 buys into the position: half of 505 + 45 * 12 = 1045 is
    522.50, capped by the cash 505: int(505 / 12) = 42 (504, cash 1). One position of 87 shares bought from bar
    4, outlay 999.00. Held to the end: 87 * 12.2 = 1,061.40, +62.40, +6.25 %, 6 bars. With max hold 6 it is
    sold on bar 10 (4 + 6) at the close 12.2 instead: a completed round trip with the same numbers, reason time.
Refused sale (fee 495): bar 4 buys int(505 / 11) = 45 (495 + 495 fee, cash 10). The bar 7 SELL of 45 @ 10 would
    leave 10 + 450 - 495 = -35: refused, the position stays. Nothing else fills: open, 45 shares, outlay 990.00,
    45 * 12.2 = 549.00, -441.00, -44.55 %, 6 bars. With max hold 3 the time exit is due from bar 7: refused there
    too, then bar 8 sells 45 @ 11 = 495 - 495 = 0.00 (cash 10): round trip 4 -> 8, -990.00, -100.00 %, time.
No trades: cash 5 cannot buy one share at 11 or 12.
"""

import re
from pathlib import Path

import pytest

from trading_assistant.backtest import (
    format_result,
    format_trade_list,
    run_backtest,
    trade_list,
)
from trading_assistant.data import load_candles
from trading_assistant.samples import sample_candles
from trading_assistant.signals import BUY, SELL
from trading_assistant.strategies import strategy_names

DATA = Path(__file__).parent / "data"


def _columns(candles):
    return {
        "closes": [c.close for c in candles],
        "opens": [c.open for c in candles],
        "highs": [c.high for c in candles],
        "lows": [c.low for c in candles],
    }


C = _columns(load_candles(DATA / "c.csv"))


def run_c(**kwargs):
    """Backtest c.csv with short=1, long=2, cash 1000 (unless given); candles passed only when an option needs them."""
    kwargs.setdefault("initial_cash", 1000)
    candles = {k: C[k] for k in ("opens", "highs", "lows")} if kwargs.pop("candles", False) else {}
    return run_backtest(C["closes"], short=1, long=2, **kwargs, **candles)


def completed(result):
    return [row for row in trade_list(result) if not row["open"]]


def open_rows(result):
    return [row for row in trade_list(result) if row["open"]]


# ---------------------------------------------------------------- hand-worked cases on c.csv


def test_plain_run_rows():
    rows = trade_list(run_c())
    assert len(rows) == 2
    done, still = rows
    assert done == {
        "open": False, "entry_bar": 4, "exit_bar": 7, "bars_held": 3, "shares": 90,
        "outlay": 990.0, "proceeds": 900.0, "pnl": -90.0, "return_pct": pytest.approx(-90 / 990 * 100),
        "reason": "signal", "win": False,
    }
    assert still["open"] is True
    assert (still["entry_bar"], still["exit_bar"], still["bars_held"]) == (9, None, 1)
    assert (still["shares"], still["held"]) == (75, 75)
    assert still["outlay"] == 900.0
    assert still["proceeds"] == pytest.approx(915.0)
    assert still["pnl"] == pytest.approx(15.0)
    assert still["return_pct"] == pytest.approx(15 / 900 * 100)
    assert still["reason"] is None and still["win"] is None


def test_plain_run_text():
    assert format_trade_list(run_c()) == [
        "Trade list (bar index is 0-based)",
        "  #     Entry  Exit  Bars   Shares        Outlay      Proceeds          P/L    Return  Reason",
        "  1         4     7     3       90        990.00        900.00       -90.00    -9.09%  signal",
        "  open      9  open     1       75        900.00        915.00       +15.00    +1.67%  -"
        "  (unrealized: marked at the last close, no selling costs)",
        "  1 completed, 0 made money (0%), 1 open (unrealized)",
    ]


def test_scale_out_rows_and_text():
    result = run_c(scale_out_pct=5, candles=True)
    done, still = trade_list(result)
    assert (done["entry_bar"], done["exit_bar"], done["bars_held"], done["shares"]) == (4, 7, 3, 90)
    assert done["outlay"] == 990.0
    assert done["proceeds"] == pytest.approx(969.75)
    assert done["pnl"] == pytest.approx(-20.25)
    assert done["reason"] == "signal"  # the sale that completed it, not the bar 5 scale-out
    assert (still["entry_bar"], still["shares"], still["held"], still["outlay"]) == (9, 81, 81, 972.0)
    assert still["proceeds"] == pytest.approx(988.20)
    assert still["pnl"] == pytest.approx(16.20)
    assert still["reason"] is None  # this position has not scaled out
    lines = format_trade_list(result)
    assert lines[2] == "  1         4     7     3       90        990.00        969.75       -20.25    -2.05%  signal"
    assert lines[3].startswith("  open      9  open     1       81        972.00        988.20       +16.20    +1.67%  -")


def test_open_row_that_has_scaled_out_says_scale_out():
    # Scale-out 1: level 11 * 1.01 = 11.11; bar 5 (high 12) sells 45 @ 11.11 = 499.95, cash 509.95; bar 7 sells
    # 45 @ 10, cash 959.95. Bar 9 buys int(959.95 / 12) = 79 (948.00); level 12 * 1.01 = 12.12, bar 10 opens at
    # 12 (below it) and its high 12.4 reaches it: 79 // 2 = 39 @ 12.12 = 472.68; 40 still held.
    # Open row: 79 bought, outlay 948.00, 472.68 + 40 * 12.2 = 960.68, +12.68.
    result = run_c(scale_out_pct=1, candles=True)
    still = open_rows(result)[0]
    assert (still["entry_bar"], still["shares"], still["held"], still["bars_held"]) == (9, 79, 40, 1)
    assert still["reason"] == "scale_out"
    assert still["outlay"] == 948.0
    assert still["proceeds"] == pytest.approx(960.68)
    assert still["pnl"] == pytest.approx(12.68)
    assert result.final_position == 40
    assert format_trade_list(result)[3].split()[9] == "scale_out"


def test_stop_loss_rows():
    done, still = trade_list(run_c(stop_pct=10, candles=True))
    assert (done["entry_bar"], done["exit_bar"], done["bars_held"], done["shares"]) == (4, 6, 2, 90)
    assert done["proceeds"] == pytest.approx(891.0)
    assert done["pnl"] == pytest.approx(-99.0)
    assert done["return_pct"] == pytest.approx(-10.0)
    assert done["reason"] == "stop"
    assert (still["entry_bar"], still["shares"], still["outlay"]) == (9, 75, 900.0)
    assert format_trade_list(run_c(stop_pct=10, candles=True))[2] == (
        "  1         4     6     2       90        990.00        891.00       -99.00   -10.00%  stop"
    )


def test_add_on_buy_held_to_the_end():
    result = run_c(position_size=0.5, min_hold=5)
    assert [(t.bar, t.side, t.shares) for t in result.trades] == [(4, BUY, 45), (9, BUY, 42)]
    assert result.round_trips == []
    (still,) = trade_list(result)
    assert (still["entry_bar"], still["bars_held"], still["shares"], still["held"]) == (4, 6, 87, 87)
    assert still["outlay"] == 999.0
    assert still["proceeds"] == pytest.approx(1061.40)
    assert still["pnl"] == pytest.approx(62.40)
    assert format_trade_list(result)[-1] == "  0 completed, 1 open (unrealized)"


def test_add_on_buy_completed():
    result = run_c(position_size=0.5, min_hold=5, max_hold=6)
    (done,) = trade_list(result)
    assert (done["entry_bar"], done["exit_bar"], done["bars_held"], done["shares"]) == (4, 10, 6, 87)
    assert done["outlay"] == 999.0
    assert done["proceeds"] == pytest.approx(1061.40)
    assert done["pnl"] == pytest.approx(62.40)
    assert (done["reason"], done["win"]) == ("time", True)
    assert format_trade_list(result)[-1] == "  1 completed, 1 made money (100%)"


def test_refused_sale_leaves_the_position_open():
    result = run_c(fee=495)
    assert [(t.bar, t.side) for t in result.trades] == [(4, BUY)]  # the bar 7 sale was refused
    (still,) = trade_list(result)
    assert (still["entry_bar"], still["bars_held"], still["shares"], still["outlay"]) == (4, 6, 45, 990.0)
    assert still["proceeds"] == pytest.approx(549.0)  # marked at the close, the 495 fee of a sale not charged
    assert still["pnl"] == pytest.approx(-441.0)
    assert still["reason"] is None


def test_refused_sale_then_completed_later():
    result = run_c(fee=495, max_hold=3)
    assert [(t.bar, t.side, t.reason) for t in result.trades] == [(4, BUY, "signal"), (8, SELL, "time")]
    (done,) = trade_list(result)
    assert (done["entry_bar"], done["exit_bar"], done["bars_held"]) == (4, 8, 4)
    assert (done["outlay"], done["proceeds"], done["pnl"]) == (990.0, 0.0, -990.0)
    assert done["return_pct"] == -100.0
    assert (done["reason"], done["win"]) == ("time", False)
    assert format_trade_list(result)[2] == (
        "  1         4     8     4       45        990.00          0.00      -990.00  -100.00%  time"
    )


def test_no_trades():
    result = run_c(initial_cash=5)
    assert result.trades == []
    assert trade_list(result) == []
    assert format_trade_list(result) == ["Trade list: no trades"]


def test_no_trades_when_the_only_signal_is_on_the_last_bar():
    result = run_backtest(C["closes"][:4], initial_cash=1000, short=1, long=2)  # BUY on bar 3, the last bar
    assert format_trade_list(result) == ["Trade list: no trades"]


def test_reason_column_is_shown_without_any_exit_option():
    result = run_c()
    assert not result.has_exits
    assert format_trade_list(result)[1].endswith("Reason")
    assert format_trade_list(result)[2].endswith("signal")


def test_trade_list_changes_nothing_on_the_result():
    result = run_c(scale_out_pct=5, candles=True)
    before_rts = list(result.round_trips)
    before_report = format_result(result, 1, 2)
    format_trade_list(result)
    trade_list(result)
    assert result.round_trips == before_rts
    assert format_result(result, 1, 2) == before_report


# ---------------------------------------------------------------- consistency with the round trip numbers

ROUND_TRIPS_LINE = re.compile(r"^  Round trips: (\d+ completed(?:, \d+ made money \(\d+%\))?)$")

RW = _columns(sample_candles("random_walk"))  # 750 bars
# The slower strategies (their signal is worked out from the whole prefix on every bar) get the first 250 bars,
# to keep this file quick; sma_cross and breakout get all 750.
RW_SHORT = {k: v[:250] for k, v in RW.items()}
FULL_LENGTH = ("sma_cross", "breakout")

SETTINGS = [
    {},
    {"fee": 5, "fee_pct": 0.1, "slippage_pct": 0.2},
    {"position_size": 0.3},  # room left in the cash, so later BUY signals add to a position
    {"position_size": 0.3, "min_hold": 15},
    {"fill": "open", "position_size": 0.5},
    {"stop_pct": 5, "take_profit_pct": 10},
    {"trail_pct": 4, "cooldown": 3},
    {"atr_stop": True, "risk_pct": 2},
    {"breakeven_pct": 3, "stop_pct": 8},
    {"scale_out_pct": 4},
    {"scale_out_pct": 3, "position_size": 0.4, "fill": "open"},
    {"max_hold": 5},
    {"max_drawdown_limit_pct": 10},
    {"max_losses": 2, "stop_pct": 3},
    {"fee": 200},  # large fees: buys and sales are refused on the way
]


def _needs_candles(settings):
    keys = ("stop_pct", "take_profit_pct", "trail_pct", "atr_stop", "risk_pct", "breakeven_pct", "scale_out_pct")
    return settings.get("fill") == "open" or any(k in settings for k in keys)


def _runs():
    for strategy in strategy_names():
        data = RW if strategy in FULL_LENGTH else RW_SHORT
        for i, settings in enumerate(SETTINGS):
            yield f"rw-{strategy}-{i}", data, strategy, 1, 2, settings
    for i, settings in enumerate(SETTINGS):
        yield f"c-{i}", C, "sma_cross", 1, 2, settings
    for cash in (5, 100, 1000):
        yield f"c-fee495-cash{cash}", C, "sma_cross", 1, 2, {"initial_cash": cash, "fee": 495, "max_hold": 3}


RUNS = list(_runs())


def _run(data, strategy, short, long, settings):
    candles = {k: data[k] for k in ("opens", "highs", "lows")} if _needs_candles(settings) else {}
    kwargs = dict(settings)
    if strategy == "sma_cross" and data is not C:
        short, long = 10, 30
    return run_backtest(
        data["closes"], initial_cash=kwargs.pop("initial_cash", 1000 if data is C else 10_000),
        short=short, long=long, strategy=strategy, **kwargs, **candles,
    )


@pytest.fixture(scope="module")
def results():
    return {name: _run(data, strategy, s, l, settings) for name, data, strategy, s, l, settings in RUNS}


@pytest.mark.parametrize("name", [run[0] for run in RUNS])
def test_rows_agree_with_the_round_trips(results, name):
    result = results[name]
    rows = trade_list(result)
    done = [row for row in rows if not row["open"]]
    still = [row for row in rows if row["open"]]

    # The same number of rows and wins as the "Round trips:" numbers, and the same round trips in order.
    assert len(done) == result.n_round_trips
    assert sum(1 for row in done if row["win"]) == result.n_winning_round_trips
    for row, rt in zip(done, result.round_trips):
        assert (row["entry_bar"], row["exit_bar"], row["shares"]) == (rt.entry_bar, rt.exit_bar, rt.shares)
        assert (row["outlay"], row["proceeds"], row["pnl"], row["win"]) == (rt.outlay, rt.proceeds, rt.pnl, rt.is_win)
        assert row["bars_held"] == rt.exit_bar - rt.entry_bar >= 1
        assert row["return_pct"] == rt.pnl / rt.outlay * 100.0
        (closing,) = [t for t in result.trades if t.bar == rt.exit_bar]
        assert closing.side == SELL and row["reason"] == closing.reason != "scale_out"

    # An open row exactly when shares are held at the end, holding those shares.
    assert len(still) == (1 if result.final_position else 0)
    if still:
        row = still[0]
        assert row["held"] == result.final_position
        assert row["bars_held"] == len(result.daily) - 1 - row["entry_bar"]
        assert row["entry_bar"] > (result.round_trips[-1].exit_bar if result.round_trips else -1)

    # Every cash movement is in exactly one row: start cash plus all the P/L is the end equity.
    total = result.initial_cash + sum(row["pnl"] for row in rows)
    assert total == pytest.approx(result.final_equity, rel=1e-9, abs=1e-6)

    # The footer repeats the "Round trips:" line's numbers; no rows, one "no trades" line.
    lines = format_trade_list(result)
    if not rows:
        assert result.trades == []
        assert lines == ["Trade list: no trades"]
        return
    assert len(lines) == 2 + len(rows) + 1
    (rt_line,) = [line for line in format_result(result, 1, 2) if line.startswith("  Round trips:")]
    expected = ROUND_TRIPS_LINE.match(rt_line).group(1) + (", 1 open (unrealized)" if still else "")
    assert lines[-1] == "  " + expected


def test_the_runs_cover_the_awkward_cases(results):
    """Guard against the sweep above going soft: the cases it is meant to check do occur in it."""
    all_rows = [(result, row) for result in results.values() for row in trade_list(result)]
    assert any(not row["open"] for _, row in all_rows)
    assert any(row["open"] for _, row in all_rows)
    assert any(row["open"] and row["reason"] == "scale_out" for _, row in all_rows)
    assert any(not row["open"] and row["win"] for _, row in all_rows)
    assert any(not row["open"] and not row["win"] for _, row in all_rows)
    reasons = {row["reason"] for _, row in all_rows if not row["open"]}
    assert {"signal", "stop", "target", "trail", "atr", "breakeven", "time", "drawdown"} <= reasons
    # add-on buys: a row with more shares than its first buy
    def first_buy(result, row):
        return next(t for t in result.trades if t.bar == row["entry_bar"]).shares
    assert any(row["shares"] > first_buy(result, row) for result, row in all_rows)
    assert any(not trade_list(result) for result in results.values())  # a run with no trades
