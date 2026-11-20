"""Tests for the add-ons (``run_backtest(..., add_on_pct=..., max_adds=...)``): the engine and the text report.

All runs: cash 1000, SMA 1/2 (short=1, long=2) unless said otherwise, close fills unless said otherwise. With
SMA 1/2 a close above the one before it is "short above long": BUY on the first such bar, HOLD while it lasts;
a close below the one before is SELL on the first such bar, HOLD while it lasts. A signal on bar t fills on t+1.
"Trigger" below is the latest buy's fill price x (1 + add_on_pct / 100).

U (the request's case): closes 10 9 8 9 11 12 13 14 15 14 13 12, position_size 0.5. Signals: BUY bar 3, SELL bar 9.
  Off:  bar 4 buy int(0.5 x 1000 / 11) = 45 @ 11 = 495, cash 505. Bar 10 sell 45 @ 13 = 585, cash 1090.00.
  10 %: trigger 11 x 1.1 = 12.10. Bar 5 close 12 < 12.10; bar 6 close 13 >= 12.10 -> add-on on bar 7 @ 14:
        cap int(0.5 x (505 + 45 x 14) / 14) = int(567.5 / 14) = 40, cash allows int(505 / 14) = 36 -> 36 @ 14 = 504,
        cash 1. Bar 10 sell 81 @ 13 = 1053, cash 1054.00. One round trip: outlay 495 + 504 = 999, proceeds 1053.
  20 %: trigger 13.20. Bar 6 close 13 < 13.20; bar 7 close 14 -> add-on on bar 8 @ 15: cap int(0.5 x (505 + 675)
        / 15) = int(590 / 15) = 39, cash int(505 / 15) = 33 -> 33 @ 15 = 495, cash 10. Bar 10 sell 78 @ 13 = 1014,
        cash 1024.00. Round trip outlay 990, proceeds 1014.
  50 %: trigger 16.50, highest close 15: never; 1090.00.
  All-in (no position_size): bar 4 buy int(1000 / 11) = 90 @ 11 = 990, cash 10. Closes 13, 14, 15 (bars 6, 7, 8,
        HOLD) are all >= 12.10, so add-ons are due on bars 7, 8, 9; each gets int(10 / price) = 0 shares: skipped,
        counted, not one of max_adds, and the reference stays 11. Bar 9 (close 14) is a SELL: no add-on due on bar
        10. add_on_skipped_buys = 3, and the fills and equity are the plain run's: sell 90 @ 13, 1180.00.

S (max_adds spacing): closes 10 8 9 10 11.5 12 13 14 15 17 16 16.5, position_size 0.25. BUY bar 2, SELL bar 10.
  Bar 3 buy int(250 / 10) = 25 @ 10, cash 750; trigger 11.
  Bar 4 close 11.5 >= 11 -> add-on 1 on bar 5 @ 12: int(0.25 x (750 + 25 x 12) / 12) = int(262.5 / 12) = 21,
        252, cash 498; trigger now 12 x 1.1 = 13.2 (bar 5 close 12 and bar 6 close 13 are below it).
  Bar 7 close 14 >= 13.2 -> add-on 2 on bar 8 @ 15: int(0.25 x (498 + 46 x 15) / 15) = int(297 / 15) = 19, 285,
        cash 213; trigger now 16.5.
  max_adds 2: bar 9 close 17 >= 16.5, but 2 add-ons have filled: nothing. Bar 11 sell 65 @ 16.5 = 1072.5,
        cash 1285.50; outlay 250 + 252 + 285 = 787.
  max_adds 1 (and the default): only add-on 1; bar 11 sell 46 @ 16.5 = 759, cash 1257.00.
  max_adds 3: bar 9 close 17 -> add-on 3 on bar 10 @ 16: cap int(0.25 x (213 + 65 x 16) / 16) = int(313.25 / 16)
        = 19, cash int(213 / 16) = 13 -> 13 @ 16 = 208, cash 5; bar 11 sell 78 @ 16.5 = 1287, cash 1292.00.

B (a signal BUY resets the reference and is not one of max_adds): closes 10 8 9 10 9.5 11.2 11.5 12.4 13 13.5 13
  12.8, position_size 0.3, min_hold 4, add_on 10, max_adds 1 (default).
  Bar 3 buy int(300 / 10) = 30 @ 10, cash 700; trigger 11. Bar 4 close 9.5: SELL; bar 5 the sale is held back by
  min_hold (5 - 3 = 2 < 4). Bar 5 close 11.2: BUY signal (and >= 11, but a BUY leaves bar 6 to the signal).
  Bar 6 signal buy @ 11.5: int(0.3 x (700 + 30 x 11.5) / 11.5) = int(313.5 / 11.5) = 27, 310.5, cash 389.5;
  the reference is now 11.5, trigger 12.65. (With the old reference 10, bars 6 and 7, closes 11.5 and 12.4,
  would have set off an add-on.) Bar 8 close 13 >= 12.65 -> add-on on bar 9 @ 13.5: int(0.3 x (389.5 + 57 x
  13.5) / 13.5) = int(347.7 / 13.5) = 25, 337.5, cash 52 (max_adds 1 still allowed it: the signal buy did not
  count). Bar 10 close 13: SELL; bar 11 sell 82 @ 12.8 = 1049.6, cash 1101.60; outlay 300 + 310.5 + 337.5 = 948.

M (a SELL signal on the trigger bar drops the add-on, also when min_hold holds the sale back): strategy momentum,
  window 1, threshold 15 (ROC = close / previous close - 1, in %), position_size 0.3, min_hold 3, add_on 10.
  Closes 10 10 10 11.6 13.4 15 15.5 16 16. ROC: bar 3 16 % (crosses up through 15: BUY), bar 4 15.52 % (HOLD),
  bar 5 11.94 % (crosses down: SELL, on a rising close), bar 6 3.33 %, bar 7 3.23 % (HOLD).
  Bar 4 buy int(300 / 13.4) = 22 @ 13.4 = 294.8, cash 705.2; trigger 14.74. Bar 5 close 15 >= 14.74 but it is a
  SELL: no add-on on bar 6. Bar 6: the SELL is held back (6 - 4 = 2 < 3); nothing fills. Bar 6 close 15.5 (HOLD)
  -> add-on on bar 7 @ 16: int(0.3 x (705.2 + 22 x 16) / 16) = int(317.16 / 16) = 19, 304, cash 401.2.
  End 401.2 + 41 x 16 = 1057.20.

Time exit (U, position_size 0.5, add_on 10): the add-on is due on bar 7 (see U).
  max_hold 3: the clock runs from bar 4, so the time exit sells 45 @ 14 on bar 7 (cash 1135.00) and the add-on is
        dropped, not counted.
  max_hold 4: bar 7 add-on 36 @ 14 as in U (cash 1); the clock is not restarted, so bar 8 sells all 81 @ 15 = 1215
        ("time"), cash 1216.00, one bar after the add-on.

D (a drawdown sale takes the bar): closes 10 8 9 10 12 11.6 11.3 11.2 11.5, all-in, min_hold 10, max drawdown 5 %.
  Bar 3 buy 100 @ 10, cash 0. Bar 4 close 12 (HOLD, >= 11): add-on on bar 5 gets 0 shares (skipped 1); equity
  1200, the peak. Bar 5 close 11.6: SELL (held back on bar 6 by min_hold). Bar 6 close 11.3: HOLD, >= 11 -> add-on
  due on bar 7; equity 1130, (1130 - 1200) / 1200 = -5.83 % -> halt at bar 6. Bar 7: the drawdown sale sells 100
  @ 11.2 = 1120; the add-on is dropped and counted nowhere (add_on_skipped 1, drawdown_skipped 0).
  Without the halt: add-ons due on bars 5, 7 and 8 (closes 12, 11.3, 11.2), all 0 shares: skipped 3.

F (a halted add-on that gets its turn is counted in drawdown_skipped_buys): closes 10 8 9 10 12 12.5 16 16.5,
  all-in, fee 600, max drawdown 50 %. Bar 3 buy: int((1000 - 600) / 10) = 40 @ 10, cost 600, cash 0; equity 400,
  60 % below the first bar's 1000 -> halt at bar 3. The drawdown sale is refused while 40 x price - 600 < 0,
  i.e. below 15: bars 4 and 5. Bar 4 close 12 >= 11 (HOLD) -> add-on due on bar 5, where nothing fills: it is
  blocked by the halt and counted in drawdown_skipped_buys (1), before sizing (so not in add_on_skipped_buys).
  Bar 5 close 12.5 -> add-on due on bar 6, but the drawdown sale fills there (40 @ 16 = 640 - 600, cash 40): it
  is dropped, not counted. drawdown_skipped_buys = 1.

K (candles, for the scale-out, the breakeven stop and open fills), position_size 0.5:
    bar  open  high   low  close
     0   10    10.2   9.8  10
     1    8.5   8.6   7.9   8
     2    8.5   9.1   8.4   9     BUY signal
     3    9.8  10.1   9.7  10     close fills: buy 50 @ 10, cash 500
     4   10.5  11.6  10.4  11.5   close 11.5 >= 11: add-on due on bar 5
     5   11.6  12.6  11.5  12.5   add-on @ 12.5: cap int(0.5 x (500 + 625) / 12.5) = 45, cash int(500 / 12.5) = 40
     6   12.6  13.5  11.0  13.4
     7   13.5  14.6  13.3  14.5
     8   14.4  14.5  13.9  14.0   SELL signal
     9   13.9  14.0  13.4  13.5   signal sale
  After the add-on: 90 shares, average entry (500 + 500) / 90 = 11.1111, cash 0.
  Scale-out 30 %: before the add-on the level is 13 (bar 4 high 11.6, bar 5 high 12.6: not reached, so the add-on
        fills); after it, 11.1111 x 1.3 = 14.4444. Bar 6 high 13.5 < 14.4444; bar 7 high 14.6 -> sell 45 @ 14.4444 =
        650, cash 650. Bar 9 sell 45 @ 13.5 = 607.5, cash 1257.50; one round trip, outlay 1000, proceeds 1257.5.
        Without add-ons: level 13 reached on bar 6: 25 @ 13 = 325, cash 825; bar 9 25 @ 13.5, end 1162.50.
  Breakeven 10 %: bar 4 high 11.6 >= 11 arms it (level 10). The add-on on bar 5 moves the level to the new average
        11.1111, still armed. Bar 6 opens 12.6 above it and its low 11.0 reaches it: sell 90 @ 11.1111 = 1000, a
        round trip at exactly 0.00. Without add-ons the level stays 10, never reached; bar 9 sells 50 @ 13.5, 1175.00.
  Open fills: bar 3 buy @ open 9.8: int(500 / 9.8) = 51, 499.8, cash 500.2; trigger 10.78. Bar 3 close 10 < 10.78;
        bar 4 close 11.5 -> add-on at bar 5's open 11.6: cap int(0.5 x (500.2 + 51 x 11.6) / 11.6) = int(545.9 /
        11.6) = 47, cash int(500.2 / 11.6) = 43 -> 43 @ 11.6 = 498.8, cash 1.4. Bar 9 sells 94 @ open 13.9 =
        1306.6, cash 1308.00. Without add-ons: bar 9 sells 51 @ 13.9 = 708.9, cash 1209.10.
  With open fills the add-on fills at the open, like a signal buy; only what is known at the open drops it.
  Open fills, stop 5 %, bar 5's low changed to 9.0: the add-on fills at bar 5's open 11.6 as above, and bar 5's
        range is not checked (one fill per bar), so the low of 9.0 under the stop (9.8 x 0.95 = 9.31) sells nothing.
        From bar 6 the stop follows the new average: (499.8 + 498.8) / 94 = 10.6234, x 0.95 = 10.0922; the lows of
        bars 6 to 9 (11.0, 13.3, 13.9, 13.4) stay above it, so the run is the open-fill add-on run: 1308.00.
        Without add-ons the stop sells 51 @ 9.31 = 474.81 on bar 5, cash 975.01.
  Open fills, stop 5 %, bar 5 opening at 9.0 (low 8.9): a gap through the stop is known at the open, so the stop
        sells 51 @ 9.0 = 459 (cash 959.20) and the add-on is dropped, not counted: the same run as without add-ons.
  Open fills, max_hold 2: the time exit is due at bar 5's open (3 + 2) and sells 51 @ 11.6 = 591.6, cash 1091.80;
        the add-on is dropped.
  Close fills, stop 5 %, bar 5's low 9.0: the bar's range comes before the close, so the stop (10 x 0.95 = 9.5)
        sells 50 @ 9.5 = 475 (cash 975.00) and the add-on due at the close is dropped: the same run as without.

Fees and slippage: U with bar 5's close 12.15, position_size 0.5, fee 1.
  Fee only: bar 4 buy int((500 - 1) / 11) = 45 @ 11 (496 with the fee), cash 504; trigger 12.10. Bar 5 close 12.15
        -> add-on on bar 6 @ 13: min(0.5 x (504 + 585), 504) = 504, int((504 - 1) / 13) = 38 (495), cash 9. Bar 10
        sell 83 @ 13 = 1079 - 1, cash 1087.00; outlay 496 + 495 = 991, proceeds 1078.
  With slippage 1 %: bar 4 buy @ 11 x 1.01 = 11.11, int(499 / 11.11) = 44 (488.84 + 1), cash 510.16. The reference
        is the recorded 11.11, trigger 12.221: bar 5 close 12.15 is now below it. Bar 6 close 13 -> add-on on bar 7
        @ 14 x 1.01 = 14.14: min(0.5 x (510.16 + 44 x 14), 510.16) = 510.16, int(509.16 / 14.14) = 36 (509.04 + 1),
        cash 0.12. Bar 10 sell 80 @ 13 x 0.99 = 12.87 = 1029.6 - 1, cash 1028.72; outlay 999.88, proceeds 1028.6.

"Unchanged" is checked against tests/data/before_add_on.json, recorded from the engine before the add-ons were
added (0.19.0, git 9b8449f): 36 runs over U, c.csv (candles and closes only) and the built-in random_walk
candles, covering every setting the engine had. Each run keeps its fill count and final equity as they are and
everything else (fills, round trips, per-bar records, counters, statistics, report, trade list, export) as one
SHA-256, compared exactly.
"""

import hashlib
import json
from pathlib import Path

import pytest

from trading_assistant.backtest import (
    export_columns,
    export_rows,
    format_result,
    format_stats,
    format_trade_list,
    run_backtest,
    trade_list,
)
from trading_assistant.data import load_candles
from trading_assistant.samples import sample_candles

DATA = Path(__file__).resolve().parent / "data"
A = pytest.approx


def candle_kwargs(candles):
    return dict(
        closes=[c.close for c in candles],
        opens=[c.open for c in candles],
        highs=[c.high for c in candles],
        lows=[c.low for c in candles],
    )


C = candle_kwargs(load_candles(DATA / "c.csv"))
U = [10, 9, 8, 9, 11, 12, 13, 14, 15, 14, 13, 12]
BASE = dict(initial_cash=1000, short=1, long=2)


def run(closes, **kwargs):
    return run_backtest(closes, **BASE, **kwargs)


def fills(result):
    return [(t.bar, t.side, t.shares, A(t.price), t.reason) for t in result.trades]


def trips(result):
    return [(x.entry_bar, x.exit_bar, x.shares, A(x.outlay), A(x.proceeds)) for x in result.round_trips]


def test_the_requests_hand_worked_cases():
    off = run(U, position_size=0.5)
    assert fills(off) == [(4, "BUY", 45, 11, "signal"), (10, "SELL", 45, 13, "signal")]
    assert off.final_equity == A(1090.00)

    r10 = run(U, position_size=0.5, add_on_pct=10)
    assert fills(r10) == [(4, "BUY", 45, 11, "signal"), (7, "BUY", 36, 14, "add_on"), (10, "SELL", 81, 13, "signal")]
    assert r10.final_equity == A(1054.00)
    assert trips(r10) == [(4, 10, 81, 999.00, 1053.00)]
    assert (r10.max_adds, r10.n_add_on_buys, r10.add_on_skipped_buys) == (1, 1, 0)
    row = trade_list(r10)[0]
    assert (row["shares"], row["outlay"], row["proceeds"], row["reason"]) == (81, A(999), A(1053), "signal")

    r20 = run(U, position_size=0.5, add_on_pct=20)
    assert fills(r20) == [(4, "BUY", 45, 11, "signal"), (8, "BUY", 33, 15, "add_on"), (10, "SELL", 78, 13, "signal")]
    assert r20.final_equity == A(1024.00)
    assert trips(r20) == [(4, 10, 78, 990.00, 1014.00)]

    r50 = run(U, position_size=0.5, add_on_pct=50)
    assert fills(r50) == fills(off) and r50.final_equity == A(1090.00)
    assert (r50.n_add_on_buys, r50.add_on_skipped_buys) == (0, 0)

    # The report: a reason on every fill and the "Add-ons:" line after "Sizing:" (no scale-out line here).
    lines = format_result(r10, 1, 2)
    assert lines[5].endswith("cash         1.00  add_on")
    assert lines[8].startswith("  Sizing:")
    assert lines[9] == (
        "  Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest "
        "buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)"
    )
    assert lines[10] == "  Round trips: 1 completed, 1 made money (100%)"
    assert export_columns(r10)[-1] == "reason"
    assert [row[-1] for row in export_rows(r10)][4:11] == ["signal", "", "", "add_on", "", "", "signal"]


def test_all_in_sizing_skips_and_counts_and_changes_nothing_else():
    plain = run(U)
    r = run(U, add_on_pct=10)
    assert fills(r) == fills(plain) == [(4, "BUY", 90, 11, "signal"), (10, "SELL", 90, 13, "signal")]
    assert [d.equity for d in r.daily] == [d.equity for d in plain.daily]
    assert r.final_equity == A(1180.00)
    assert (r.n_add_on_buys, r.add_on_skipped_buys, r.risk_skipped_buys) == (0, 3, 0)
    assert "1 add-on buy" not in "\n".join(format_result(r, 1, 2))
    assert "0 add-on buys, 3 skipped (0 shares)" in "\n".join(format_result(r, 1, 2))


def test_max_adds_spaces_each_add_on_from_the_latest_buy():
    s = [10, 8, 9, 10, 11.5, 12, 13, 14, 15, 17, 16, 16.5]
    first = [(3, "BUY", 25, 10, "signal"), (5, "BUY", 21, 12, "add_on")]
    for max_adds in (None, 1):
        r = run(s, position_size=0.25, add_on_pct=10, max_adds=max_adds)
        assert fills(r) == first + [(11, "SELL", 46, 16.5, "signal")]
        assert r.final_equity == A(1257.00) and r.max_adds == 1
    r2 = run(s, position_size=0.25, add_on_pct=10, max_adds=2)
    assert fills(r2) == first + [(8, "BUY", 19, 15, "add_on"), (11, "SELL", 65, 16.5, "signal")]
    assert r2.final_equity == A(1285.50) and trips(r2) == [(3, 11, 65, 787.0, 1072.5)]
    r3 = run(s, position_size=0.25, add_on_pct=10, max_adds=3)
    assert fills(r3)[2:] == [(8, "BUY", 19, 15, "add_on"), (10, "BUY", 13, 16, "add_on"), (11, "SELL", 78, 16.5, "signal")]
    assert r3.final_equity == A(1292.00)
    assert "up to 3 per position" in "\n".join(format_result(r3, 1, 2))


def test_a_signal_buy_resets_the_reference_and_is_not_one_of_max_adds():
    b = [10, 8, 9, 10, 9.5, 11.2, 11.5, 12.4, 13, 13.5, 13, 12.8]
    r = run(b, position_size=0.3, min_hold=4, add_on_pct=10)
    assert fills(r) == [
        (3, "BUY", 30, 10, "signal"),
        (6, "BUY", 27, 11.5, "signal"),
        (9, "BUY", 25, 13.5, "add_on"),
        (11, "SELL", 82, 12.8, "signal"),
    ]
    assert r.min_hold_skipped_sells == 1
    assert r.final_equity == A(1101.60) and trips(r) == [(3, 11, 82, 948.0, 1049.6)]


def test_a_sell_signal_on_the_trigger_bar_drops_it_even_when_min_hold_holds_the_sale_back():
    m = [10, 10, 10, 11.6, 13.4, 15.0, 15.5, 16, 16]
    kw = dict(strategy="momentum", strategy_params={"window": 1, "threshold": 15}, position_size=0.3, add_on_pct=10)
    r = run(m, min_hold=3, **kw)
    assert [d.signal for d in r.daily][3:6] == ["BUY", "HOLD", "SELL"]
    assert fills(r) == [(4, "BUY", 22, 13.4, "signal"), (7, "BUY", 19, 16, "add_on")]
    assert (r.min_hold_skipped_sells, r.add_on_skipped_buys) == (1, 0)
    assert r.final_equity == A(1057.20)


def test_a_time_exit_takes_the_bar_and_the_add_on_does_not_restart_the_clock():
    r3 = run(U, position_size=0.5, add_on_pct=10, max_hold=3)
    assert fills(r3) == [(4, "BUY", 45, 11, "signal"), (7, "SELL", 45, 14, "time")]
    assert (r3.n_add_on_buys, r3.add_on_skipped_buys) == (0, 0) and r3.final_equity == A(1135.00)
    r4 = run(U, position_size=0.5, add_on_pct=10, max_hold=4)
    assert fills(r4) == [(4, "BUY", 45, 11, "signal"), (7, "BUY", 36, 14, "add_on"), (8, "SELL", 81, 15, "time")]
    assert r4.final_equity == A(1216.00) and trips(r4) == [(4, 8, 81, 999.0, 1215.0)]


def test_a_drawdown_sale_takes_the_bar_and_a_halted_add_on_is_counted_once():
    d = [10, 8, 9, 10, 12, 11.6, 11.3, 11.2, 11.5]
    r = run(d, add_on_pct=10, max_drawdown_limit_pct=5, min_hold=10)
    assert fills(r) == [(3, "BUY", 100, 10, "signal"), (7, "SELL", 100, 11.2, "drawdown")]
    assert (r.drawdown_halt_bar, r.drawdown_skipped_buys, r.add_on_skipped_buys) == (6, 0, 1)
    assert r.final_equity == A(1120.00)
    assert run(d, add_on_pct=10, min_hold=10).add_on_skipped_buys == 3

    f = [10, 8, 9, 10, 12, 12.5, 16, 16.5]
    r = run(f, fee=600, add_on_pct=10, max_drawdown_limit_pct=50)
    assert [(t.bar, t.side, t.shares, t.price, t.cost, t.reason) for t in r.trades] == [
        (3, "BUY", 40, 10, 600.0, "signal"), (6, "SELL", 40, 16, 600.0, "drawdown"),
    ]
    assert (r.drawdown_halt_bar, r.drawdown_skipped_buys, r.add_on_skipped_buys) == (3, 1, 0)
    assert r.final_equity == A(40.00)


K_ROWS = [  # open, high, low, close
    (10, 10.2, 9.8, 10), (8.5, 8.6, 7.9, 8), (8.5, 9.1, 8.4, 9), (9.8, 10.1, 9.7, 10),
    (10.5, 11.6, 10.4, 11.5), (11.6, 12.6, 11.5, 12.5), (12.6, 13.5, 11.0, 13.4),
    (13.5, 14.6, 13.3, 14.5), (14.4, 14.5, 13.9, 14.0), (13.9, 14.0, 13.4, 13.5),
]
K = dict(
    closes=[r[3] for r in K_ROWS], opens=[r[0] for r in K_ROWS], highs=[r[1] for r in K_ROWS], lows=[r[2] for r in K_ROWS]
)


def test_scale_out_and_breakeven_follow_the_average_after_an_add_on():
    add = [(3, "BUY", 50, 10, "signal"), (5, "BUY", 40, 12.5, "add_on")]
    r = run_backtest(**K, **BASE, position_size=0.5, scale_out_pct=30, add_on_pct=10)
    assert fills(r) == add + [(7, "SELL", 45, 1000 / 90 * 1.3, "scale_out"), (9, "SELL", 45, 13.5, "signal")]
    assert r.final_equity == A(1257.50) and trips(r) == [(3, 9, 90, 1000.0, 1257.5)]
    plain = run_backtest(**K, **BASE, position_size=0.5, scale_out_pct=30)
    assert fills(plain)[1] == (6, "SELL", 25, 13.0, "scale_out") and plain.final_equity == A(1162.50)

    r = run_backtest(**K, **BASE, position_size=0.5, breakeven_pct=10, add_on_pct=10)
    assert fills(r) == add + [(6, "SELL", 90, 1000 / 90, "breakeven")]
    assert r.final_equity == A(1000.00) and r.round_trips[0].pnl == A(0.0, abs=1e-9)
    plain = run_backtest(**K, **BASE, position_size=0.5, breakeven_pct=10)
    assert fills(plain)[1] == (9, "SELL", 50, 13.5, "signal") and plain.final_equity == A(1175.00)


def test_open_fills_buy_at_the_open_and_only_what_is_known_at_the_open_drops_it():
    kw = dict(BASE, position_size=0.5, add_on_pct=10)
    with_add_on = [(3, "BUY", 51, 9.8, "signal"), (5, "BUY", 43, 11.6, "add_on"), (9, "SELL", 94, 13.9, "signal")]
    r = run_backtest(**K, **kw, fill="open")
    assert fills(r) == with_add_on and r.final_equity == A(1308.00)
    assert run_backtest(**K, **BASE, position_size=0.5, fill="open").final_equity == A(1209.10)

    # A stop reached later in the add-on's bar does not undo it (no look-ahead), and sells nothing on that bar.
    low5 = dict(K, lows=K["lows"][:5] + [9.0] + K["lows"][6:])
    r = run_backtest(**low5, **kw, fill="open", stop_pct=5)
    assert fills(r) == with_add_on and r.final_equity == A(1308.00)
    plain = run_backtest(**low5, **BASE, position_size=0.5, fill="open", stop_pct=5)
    assert fills(plain) == [(3, "BUY", 51, 9.8, "signal"), (5, "SELL", 51, 9.31, "stop")]
    assert plain.final_equity == A(975.01)

    # Known at the open: a gap through the stop, or the time exit, takes the bar and drops it.
    gap5 = dict(K, opens=K["opens"][:5] + [9.0] + K["opens"][6:], lows=K["lows"][:5] + [8.9] + K["lows"][6:])
    r = run_backtest(**gap5, **kw, fill="open", stop_pct=5)
    assert fills(r) == [(3, "BUY", 51, 9.8, "signal"), (5, "SELL", 51, 9.0, "stop")] and r.final_equity == A(959.20)
    r = run_backtest(**K, **kw, fill="open", max_hold=2)
    assert fills(r) == [(3, "BUY", 51, 9.8, "signal"), (5, "SELL", 51, 11.6, "time")] and r.final_equity == A(1091.80)
    assert (r.n_add_on_buys, r.add_on_skipped_buys) == (0, 0)

    # With close fills the bar's range comes before the close: the stop during the bar still drops it.
    r = run_backtest(**low5, **kw, stop_pct=5)
    assert fills(r) == [(3, "BUY", 50, 10, "signal"), (5, "SELL", 50, 9.5, "stop")] and r.final_equity == A(975.00)


def test_fees_and_slippage_and_the_reference_is_the_slipped_fill():
    u2 = U[:5] + [12.15] + U[6:]
    r = run(u2, position_size=0.5, fee=1, add_on_pct=10)
    assert fills(r) == [(4, "BUY", 45, 11, "signal"), (6, "BUY", 38, 13, "add_on"), (10, "SELL", 83, 13, "signal")]
    assert r.final_equity == A(1087.00) and trips(r) == [(4, 10, 83, 991.0, 1078.0)]
    r = run(u2, position_size=0.5, fee=1, slippage_pct=1, add_on_pct=10)
    assert fills(r) == [
        (4, "BUY", 44, 11.11, "signal"), (7, "BUY", 36, 14.14, "add_on"), (10, "SELL", 80, 12.87, "signal"),
    ]
    assert r.final_equity == A(1028.72) and trips(r) == [(4, 10, 80, 999.88, 1028.6)]
    assert r.total_costs == A(3.0)


def test_bad_settings_are_refused():
    for bad in (0, -1, float("nan")):
        with pytest.raises(ValueError, match="add_on_pct must be positive"):
            run(U, add_on_pct=bad)
    with pytest.raises(ValueError, match="max_adds needs add_on_pct"):
        run(U, max_adds=2)
    for bad in (0, -1, 1.5, True, "2"):
        with pytest.raises(ValueError, match="max_adds must be a whole number of at least 1"):
            run(U, add_on_pct=10, max_adds=bad)


# --- runs without the option are unchanged --------------------------------------------------------------

WALK = candle_kwargs(sample_candles("random_walk"))
INPUTS = {"u": {"closes": U}, "c": C, "c_closes": {"closes": C["closes"]}, "w": WALK}
BASES = {
    "u": dict(initial_cash=1000, short=1, long=2),
    "c": dict(initial_cash=1000, short=1, long=2),
    "c_closes": dict(initial_cash=1000, short=1, long=2),
    "w": dict(initial_cash=10000, short=10, long=30),
}
# Settings that need only closes run on u, c_closes and w; candle settings on c and w.
CLOSE_SETTINGS = {
    "plain": {},
    "ps": dict(position_size=0.5),
    "fees_slip": dict(fee=1.0, fee_pct=0.1, slippage_pct=0.2, position_size=0.6),
    "holds": dict(min_hold=3, max_hold=5, position_size=0.5),
    "halts": dict(max_drawdown_limit_pct=8, max_losses=2, fee=2.0),
    "warmup": dict(warmup_closes=[9.5, 10.5, 10.0], position_size=0.7),
    "rsi": dict(strategy="rsi_reversion", strategy_params={"period": 3}, position_size=0.5),
    "breakout": dict(strategy="breakout", strategy_params={"window": 3}, position_size=0.4),
}
CANDLE_SETTINGS = {
    "open": dict(fill="open", position_size=0.5),
    "stops": dict(stop_pct=5, take_profit_pct=8, trail_pct=6, position_size=0.5),
    "atr": dict(risk_pct=2, atr_mult=2.0, atr_period=3, atr_stop=True, cooldown=2),
    "be_so": dict(breakeven_pct=3, scale_out_pct=5, position_size=0.5, fee_pct=0.1),
    "open_all": dict(fill="open", slippage_pct=0.3, stop_pct=4, breakeven_pct=2, scale_out_pct=4, max_hold=6,
                     max_drawdown_limit_pct=10, position_size=0.5),
    "breakout_so": dict(strategy="breakout", strategy_params={"window": 3}, scale_out_pct=3, trail_pct=5),
}
CASES = {}
for _name, _settings in CLOSE_SETTINGS.items():
    for _data in ("u", "c_closes", "w"):
        CASES[f"{_data}/{_name}"] = (_data, _settings)
for _name, _settings in CANDLE_SETTINGS.items():
    for _data in ("c", "w"):
        CASES[f"{_data}/{_name}"] = (_data, _settings)


def _digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def _record(r):
    """Everything a run shows (fills, round trips, per-bar records, counters, final values, statistics, report,
    trade list, export), the final equity as it is and the rest as one SHA-256."""
    short, long = r.strategy_params.get("short", 1), r.strategy_params.get("long", 2)
    whole = {
        "fills": [[t.bar, t.side, t.shares, t.price, t.cash_after, t.cost, t.reason] for t in r.trades],
        "round_trips": [[x.entry_bar, x.exit_bar, x.shares, x.outlay, x.proceeds] for x in r.round_trips],
        "daily": [[d.bar, d.close, d.signal, d.cash, d.position, d.equity] for d in r.daily],
        "counters": [r.risk_skipped_buys, r.cooldown_skipped_buys, r.min_hold_skipped_sells, r.drawdown_halt_bar,
                     r.drawdown_skipped_buys, r.loss_halt_bar, r.loss_skipped_buys],
        "final": [r.final_cash, r.final_position, r.final_equity, r.total_costs],
        "stats": r.stats,
        "report": format_result(r, short, long) + format_stats(r),
        "trade_list": trade_list(r),
        "trade_list_text": format_trade_list(r),
        "export": [export_columns(r)] + export_rows(r),
    }
    whole = json.loads(json.dumps(whole))
    return {"n_fills": len(r.trades), "final_equity": r.final_equity, "sha256": _digest(whole)}


def _run(name, **extra):
    data, settings = CASES[name]
    return run_backtest(**INPUTS[data], **BASES[data], **settings, **extra)


BEFORE = json.loads((DATA / "before_add_on.json").read_text())


def test_runs_without_the_option_are_exactly_as_before():
    # The 750-bar runs use the built-in random_walk sample; if the sample changes, the recording no longer applies.
    assert _digest(WALK) == BEFORE["inputs_sha256"]["w"]
    assert sorted(CASES) == sorted(BEFORE["cases"]) and len(CASES) == 36
    for name in CASES:
        for extra in ({}, {"add_on_pct": None}):
            result = _run(name, **extra)
            assert _record(result) == BEFORE["cases"][name], (name, extra)
            assert (result.add_on_pct, result.max_adds, result.add_on_skipped_buys) == (None, None, 0)
            assert "Add-ons" not in "\n".join(format_result(result, 1, 2))
