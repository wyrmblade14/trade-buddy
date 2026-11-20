"""Stop loss / take profit on a bar that *opens* past the level (an overnight gap).

A stop or target order that is resting when the market opens beyond it fills
near that open, not at the level the price jumped over. A bar that only
touches a level during the bar still fills at the level exactly.

Same closes as test_stop_take_profit.py, short=2, long=3: BUY signal at bar 4,
SELL signal at bar 7. Only bar 6 (and bar 7 in one open-fill case) changes
between the scenarios below; every other bar is the base series:

    bar   open  high   low  close
     0      9    11     8     10
     1      9    11     8     10
     2      9    11     8     10
     3      9    11     8     10
     4     12    15    11     14      BUY signal
     5     13    15  12.9     14
     6     14    17    12     14      base: opens between stop and target, touches both
     7      9    10   7.5      8      SELL signal
     8      7     9   6.9      8
     9      8     9   7.5      8

Bar 6 variants (each is a valid candle: low <= open, close <= high):

    GAP_DOWN          open 11.0  high 14.5  low 10.5  close 14
    GAP_UP            open 17.5  high 18.0  low 13.0  close 14
    GAP_UP_LOW_STOP   open 17.5  high 18.0  low 12.0  close 14   (opens above target, later falls to the stop)
    OPEN_AT_STOP      open 12.6  high 14.5  low 12.0  close 14
    OPEN_AT_TARGET    open 16.8  high 17.0  low 13.0  close 14

Close fills (the default): BUY at bar 5's close 14 -> int(10,000 / 14) = 714 shares,
cost 9,996, cash 4. Entry 14, stop 10 % -> 12.6, target 20 % -> 16.8.

    GAP_DOWN, stop 10 %:   open 11 <= 12.6 -> SELL 714 @ 11.00 = 7,854.00, cash 4 + 7,854 = 7,858.00
                           (round trip 7,854 - 9,996 = -2,142)
    GAP_UP, target 20 %:   open 17.5 >= 16.8 -> SELL 714 @ 17.50 = 12,495.00, cash 12,499.00
    GAP_UP_LOW_STOP, both: the open comes first and is already past the target ->
                           target @ 17.50, cash 12,499.00 (without opens: touches both -> stop @ 12.60)
    OPEN_AT_STOP, stop:    open 12.6 == level -> 12.60, cash 4 + 714 * 12.6 = 9,000.40
    OPEN_AT_TARGET, target: open 16.8 == level -> 16.80, cash 4 + 714 * 16.8 = 11,999.20
    base bar 6 (touch only): stop 12.60 / cash 9,000.40, target 16.80 / cash 11,999.20 - as before

Fees 5 + 1 %, stop 10 %, GAP_DOWN:
    BUY: int((10,000 - 5) / (14 * 1.01)) = 706 shares, 9,884 + fee (5 + 98.84) = 9,987.84, cash 12.16
    stop at the open 11: value 706 * 11 = 7,766.00, fee 5 + 77.66 = 82.66,
    cash 12.16 + 7,766 - 82.66 = 7,695.50; total costs 103.84 + 82.66 = 186.50

Slippage 1 %:
    BUY @ 14 * 1.01 = 14.14, int(10,000 / 14.14) = 707 shares (9,996.98), cash 3.02
    stop level 14.14 * 0.9 = 12.726, target level 14.14 * 1.2 = 16.968
    GAP_DOWN, stop:   open 11 slips to 11 * 0.99 = 10.89; 707 * 10.89 = 7,699.23, cash 7,702.25
    GAP_UP, target:   open 17.5 slips to 17.5 * 0.99 = 17.325; 707 * 17.325 = 12,248.775, cash 12,251.795

Open fills: BUY at bar 5's open 13 -> int(10,000 / 13) = 769 shares, cost 9,997, cash 3.
Entry 13, stop 10 % -> 11.7, target 20 % -> 15.6.

    GAP_DOWN, stop:   open 11 <= 11.7 -> SELL 769 @ 11.00 = 8,459.00, cash 8,462.00
    GAP_UP, target:   open 17.5 >= 15.6 -> SELL 769 @ 17.50 = 13,457.50, cash 13,460.50
    touch only (bar 7 open raised to 12, high 12): bar 6 low 12 > 11.7; bar 7 opens at 12 > 11.7,
                      low 7.5 reaches it -> SELL 769 @ 11.70 = 8,997.30, cash 9,000.30
"""

import pytest

from trading_assistant.backtest import export_rows, EXPORT_COLUMNS, run_backtest
from trading_assistant.cli import main
from trading_assistant.signals import BUY, SELL

CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0]
HIGHS = [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0]
LOWS = [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5]
SMA = dict(short=2, long=3)
A = pytest.approx

# (open, high, low) for bar 6; its close stays 14
GAP_DOWN = (11.0, 14.5, 10.5)
GAP_UP = (17.5, 18.0, 13.0)
GAP_UP_LOW_STOP = (17.5, 18.0, 12.0)
OPEN_AT_STOP = (12.6, 14.5, 12.0)
OPEN_AT_TARGET = (16.8, 17.0, 13.0)


def bars(bar6=None, bar7=None):
    """opens, highs, lows of the base series with bar 6 / bar 7 replaced by ``(open, high, low)``."""
    opens, highs, lows = list(OPENS), list(HIGHS), list(LOWS)
    for t, row in ((6, bar6), (7, bar7)):
        if row is not None:
            opens[t], highs[t], lows[t] = row
    return dict(opens=opens, highs=highs, lows=lows)


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.cash_after, t.reason) for t in result.trades]


def exit_fill(result):
    """The single exit of a run as (bar, shares, price, cash_after, reason); money rounded to 6 places (float noise)."""
    buy, sell = result.trades
    assert buy.side == BUY and sell.side == SELL
    return (sell.bar, sell.shares, round(sell.price, 6), round(sell.cash_after, 6), sell.reason)


# --------------------------------------------------------------------------- close fills (default)


def test_gap_down_through_the_stop_fills_at_the_open():
    r = run_backtest(CLOSES, stop_pct=10, **bars(GAP_DOWN), **SMA)
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (6, SELL, 714, 11.0, 7858.0, "stop")]
    assert r.final_cash == A(7858.0) and r.final_position == 0
    (rt,) = r.round_trips
    assert rt.proceeds == A(7854.0) and rt.outlay == A(9996.0) and rt.pnl == A(-2142.0)
    assert r.daily[6].equity == A(7858.0)


def test_gap_up_through_the_target_fills_at_the_open():
    r = run_backtest(CLOSES, take_profit_pct=20, **bars(GAP_UP), **SMA)
    assert fills(r) == [(5, BUY, 714, 14.0, 4.0, "signal"), (6, SELL, 714, 17.5, 12499.0, "target")]
    assert r.round_trips[0].pnl == A(2499.0)


def test_gap_up_with_both_exits_and_a_stop_touch_still_fills_at_the_open():
    r = run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, **bars(GAP_UP), **SMA)
    assert exit_fill(r) == (6, 714, 17.5, 12499.0, "target")


def test_bar_opening_past_the_target_is_a_target_even_if_it_later_reaches_the_stop():
    kw = bars(GAP_UP_LOW_STOP)
    assert kw["highs"][6] >= 16.8 and kw["lows"][6] <= 12.6  # the bar's range touches both levels
    r = run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, **kw, **SMA)
    assert exit_fill(r) == (6, 714, 17.5, 12499.0, "target")
    # without the opens the gap cannot be seen: touching both levels is a stop at the level, as before
    blind = run_backtest(CLOSES, stop_pct=10, take_profit_pct=20, highs=kw["highs"], lows=kw["lows"], **SMA)
    assert exit_fill(blind) == (6, 714, 12.6, 9000.4, "stop")


def test_without_opens_a_gap_cannot_be_seen_and_the_level_is_used():
    kw = bars(GAP_DOWN)
    r = run_backtest(CLOSES, stop_pct=10, highs=kw["highs"], lows=kw["lows"], **SMA)
    assert exit_fill(r) == (6, 714, 12.6, 9000.4, "stop")


@pytest.mark.parametrize(
    "bar6, kwargs, expected",
    [
        (OPEN_AT_STOP, dict(stop_pct=10), (6, 714, 12.6, 9000.4, "stop")),
        (OPEN_AT_TARGET, dict(take_profit_pct=20), (6, 714, 16.8, 11999.2, "target")),
    ],
    ids=["open exactly at the stop", "open exactly at the target"],
)
def test_open_exactly_at_the_level_fills_at_the_level(bar6, kwargs, expected):
    assert exit_fill(run_backtest(CLOSES, **kwargs, **bars(bar6), **SMA)) == expected


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(stop_pct=10), (6, 714, 12.6, 9000.4, "stop")),
        (dict(take_profit_pct=20), (6, 714, 16.8, 11999.2, "target")),
        (dict(stop_pct=10, take_profit_pct=20), (6, 714, 12.6, 9000.4, "stop")),
    ],
    ids=["stop", "target", "both: stop wins"],
)
def test_a_bar_that_only_touches_a_level_still_fills_at_the_level(kwargs, expected):
    # base bar 6 opens at 14, between the stop 12.6 and the target 16.8
    assert exit_fill(run_backtest(CLOSES, **kwargs, **bars(), **SMA)) == expected


def test_gap_stop_with_fees_hand_worked():
    r = run_backtest(CLOSES, stop_pct=10, fee=5, fee_pct=1, **bars(GAP_DOWN), **SMA)
    buy, stop = r.trades
    assert (buy.bar, buy.shares, buy.price) == (5, 706, 14.0) and buy.cash_after == A(12.16)
    assert (stop.bar, stop.shares, stop.price, stop.reason) == (6, 706, 11.0, "stop")
    assert stop.cost == A(82.66)
    assert stop.cash_after == A(7695.50)
    assert r.total_costs == A(186.50)


def test_gap_stop_with_slippage_hand_worked():
    r = run_backtest(CLOSES, stop_pct=10, slippage_pct=1, **bars(GAP_DOWN), **SMA)
    buy, stop = r.trades
    assert (buy.shares, buy.price, buy.cash_after) == (707, A(14.14), A(3.02))
    assert stop.price == A(10.89) and stop.reason == "stop"  # the open 11, slipped 1 % lower
    assert stop.cash_after == A(7702.25)


def test_gap_target_with_slippage_hand_worked():
    r = run_backtest(CLOSES, take_profit_pct=20, slippage_pct=1, **bars(GAP_UP), **SMA)
    _, target = r.trades
    assert target.price == A(17.325) and target.reason == "target"  # the open 17.5, slipped 1 % lower
    assert target.cash_after == A(12251.795)


def test_the_entry_bar_is_not_checked_even_if_it_opened_below_the_stop():
    kw = bars()
    kw["opens"][5] = kw["lows"][5] = 1.0  # bar 5 opened far below any stop, but the buy is at its close
    r = run_backtest(CLOSES, stop_pct=10, **kw, **SMA)
    assert [(t.bar, t.price, t.reason) for t in r.trades] == [(5, 14.0, "signal"), (6, 12.6, "stop")]


# --------------------------------------------------------------------------- open fills


def test_open_fills_gap_down_through_the_stop():
    r = run_backtest(CLOSES, fill="open", stop_pct=10, **bars(GAP_DOWN), **SMA)
    assert fills(r) == [(5, BUY, 769, 13.0, 3.0, "signal"), (6, SELL, 769, 11.0, 8462.0, "stop")]


def test_open_fills_gap_up_through_the_target():
    r = run_backtest(CLOSES, fill="open", take_profit_pct=20, **bars(GAP_UP), **SMA)
    assert fills(r) == [(5, BUY, 769, 13.0, 3.0, "signal"), (6, SELL, 769, 17.5, 13460.5, "target")]


def test_open_fills_touch_only_still_fills_at_the_level():
    r = run_backtest(CLOSES, fill="open", stop_pct=10, **bars(bar7=(12.0, 12.0, 7.5)), **SMA)
    buy, stop = r.trades
    assert (stop.bar, stop.shares, stop.reason) == (7, 769, "stop")
    assert stop.price == A(11.7) and stop.cash_after == A(9000.3)


# --------------------------------------------------------------------------- no gaps: nothing changes


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(stop_pct=10),
        dict(take_profit_pct=20),
        dict(stop_pct=10, take_profit_pct=20),
        dict(stop_pct=50),  # level 7; bar 8 opens exactly at 7, which fills at 7 either way
        dict(take_profit_pct=7),  # level 14.98; bar 6 opens at 14 and its high 17 reaches it
        dict(stop_pct=10, fee=5, fee_pct=1),
        dict(stop_pct=10, slippage_pct=1),
        dict(stop_pct=10, position_size=0.5),
    ],
)
def test_runs_without_gaps_are_identical_with_or_without_opens(kwargs):
    with_opens = run_backtest(CLOSES, **kwargs, **bars(), **SMA)
    without = run_backtest(CLOSES, **kwargs, highs=HIGHS, lows=LOWS, **SMA)
    assert with_opens == without


def test_opens_are_still_ignored_without_exits_on_close_fills():
    assert run_backtest(CLOSES, opens=[1.0], **SMA) == run_backtest(CLOSES, **SMA)


@pytest.mark.parametrize(
    "opens, message",
    [
        (OPENS[:-1], "9 opens but 10 closes"),
        (OPENS[:3] + [0.0] + OPENS[4:], "bar 3: open must be positive, got 0.0"),
    ],
    ids=["wrong length", "non-positive"],
)
def test_opens_used_for_exits_are_validated(opens, message):
    with pytest.raises(ValueError) as excinfo:
        run_backtest(CLOSES, stop_pct=10, opens=opens, highs=HIGHS, lows=LOWS, **SMA)
    assert str(excinfo.value) == message


def test_export_shows_the_open_as_the_fill_price():
    rows = export_rows(run_backtest(CLOSES, stop_pct=10, **bars(GAP_DOWN), **SMA))
    assert rows[6][EXPORT_COLUMNS.index("price")] == "11.00"
    assert rows[6][EXPORT_COLUMNS.index("cash")] == "7858.00"
    assert rows[6][-1] == "stop"


# --------------------------------------------------------------------------- CLI (default close fills)


def write_candles(tmp_path, bar6):
    kw = bars(bar6)
    rows = ["date,open,high,low,close,volume"]
    for t in range(len(CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{kw['opens'][t]},{kw['highs'][t]},{kw['lows'][t]},{CLOSES[t]},{(t + 1) * 1000}")
    path = tmp_path / "gap.csv"
    path.write_text("\n".join(rows) + "\n")
    return str(path)


@pytest.mark.parametrize(
    "bar6, option, fill_line, end_cash",
    [
        (GAP_DOWN, ["--stop-loss", "10"],
         ["#2", "bar", "6", "SELL", "714", "@", "11.00", "value", "7,854.00", "cost", "0.00", "cash", "7,858.00", "stop"],
         "7,858.00"),
        (GAP_UP, ["--take-profit", "20"],
         ["#2", "bar", "6", "SELL", "714", "@", "17.50", "value", "12,495.00", "cost", "0.00", "cash", "12,499.00", "target"],
         "12,499.00"),
    ],
    ids=["stop gap", "target gap"],
)
def test_cli_default_close_fills_see_the_gap(tmp_path, capsys, bar6, option, fill_line, end_cash):
    code = main([write_candles(tmp_path, bar6), "--backtest", "--short", "2", "--long", "3"] + option)
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    lines = captured.out.splitlines()
    fill_lines = [line.split() for line in lines if line.startswith("    #")]
    assert fill_lines[1] == fill_line
    assert f"  End cash:    {end_cash}" in lines
